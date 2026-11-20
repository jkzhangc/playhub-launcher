"""Public GitHub Releases only: short probes, bounded fallback, full integrity.

Mirrors are untrusted transports. Never send cookies or access tokens to them.
This module downloads assets; it does not install or execute updates.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import re
import threading
import time
from urllib import parse, request, error
from .core import DownloadError, FileEntry, USER_AGENT
from .http_engine import Paused, download_file
from .sources import WebClient

# These are third-party services, NOT official GitHub endpoints. Disabled unless selected.
# GHFast and GHProxy.net are omitted from defaults after the measured 403/timeout.
MIRRORS = {'ghproxy': ('GH-Proxy', 'https://gh-proxy.com/')}
ASSET_PATH = re.compile(r'^/[^/]+/[^/]+/releases/download/[^/]+/[^/]+$')

def public_release_url(url):
    try:
        u = parse.urlsplit(url)
        return (u.scheme == 'https' and u.hostname == 'github.com' and not u.username
                and not u.password and not u.query and not u.fragment and bool(ASSET_PATH.fullmatch(u.path)))
    except ValueError:
        return False

def release_files(repository, tag='latest', web=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise DownloadError('GitHub 仓库请填写 所有者/仓库名。')
    api = web or WebClient()
    suffix = '/latest' if tag == 'latest' else '/tags/' + parse.quote(tag, safe='')
    if tag == 'testing':
        releases = api.json('https://api.github.com/repos/' + repository + '/releases?per_page=20')
        data = next((r for r in releases if not r.get('draft') and r.get('assets')), None)
        if data is None:raise DownloadError('当前没有已发布且带附件的测试发行版。')
    else:
        data = api.json('https://api.github.com/repos/' + repository + '/releases' + suffix)
    assets = data.get('assets', [])
    if not isinstance(assets, list):
        raise DownloadError('GitHub 返回无效的 Release 附件清单。')
    entries = []
    from .core import safe_relative
    for asset in assets:
        url, name = str(asset.get('browser_download_url', '')), str(asset.get('name', ''))
        if not public_release_url(url):
            continue
        safe_relative(name)
        digest = str(asset.get('digest') or '')
        sha = digest[7:] if re.fullmatch('sha256:[0-9a-fA-F]{64}', digest) else ''
        entries.append(FileEntry(str(asset.get('id', name)), name, int(asset.get('size', -1)), url, sha256=sha))
    if not entries:
        raise DownloadError('此仓库当前没有可下载的 Release 附件；建好仓库不等于已经发布安装包。')
    return data, entries

def candidates(entry, mode='origin', mirror_ids=None):
    values = [('GitHub 源站', entry.url)]
    if mode == 'origin' or not public_release_url(entry.url) or not re.fullmatch('[a-fA-F0-9]{64}', entry.sha256 or ''):
        return values
    for key in (mirror_ids if mirror_ids is not None else ['ghproxy']):
        if key in MIRRORS:
            name, prefix = MIRRORS[key]
            values.append((name + '（第三方）', prefix + entry.url))
    if mode == 'mirror':
        values = values[1:] + values[:1]
    return values

def probe_source(name, url, size, stop):
    start = time.monotonic()
    sample_size = min(size if size > 0 else 1024 * 1024, 1024 * 1024)
    record = {'name': name, 'url': url, 'ok': False, 'bytes': 0}
    # An empty cookie jar, no auth headers, HTTPS certificate verification enabled.
    opener = request.build_opener(request.ProxyHandler(), request.HTTPSHandler())
    try:
        req = request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity', 'Range': f'bytes=0-{sample_size-1}'})
        with opener.open(req, timeout=4) as response:
            final = parse.urlsplit(response.url)
            if final.scheme != 'https' or final.username or final.password:
                raise DownloadError('测速跳转到非 HTTPS 来源。')
            if response.headers.get_content_type() in ('text/html', 'application/xhtml+xml'):
                raise DownloadError('测速返回网页而不是文件。')
            if response.status == 206:
                m = re.fullmatch(r'bytes 0-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                if not m or int(m.group(1)) != sample_size-1 or (size >= 0 and int(m.group(2)) != size):
                    raise DownloadError('测速 Range 或总文件大小不匹配。')
            elif response.status != 200:
                raise DownloadError('测速响应不正确。')
            got = 0
            while got < sample_size:
                if stop.is_set():
                    raise Paused()
                if time.monotonic() - start > 7:
                    raise TimeoutError('单来源测速超过 7 秒预算。')
                block = response.read(min(64*1024, sample_size-got))
                if not block:
                    break
                got += len(block)
            if got != sample_size:
                raise DownloadError('测速样本不足。')
            elapsed = time.monotonic() - start
            record.update(ok=True, bytes=got, seconds=round(elapsed,3), mib_per_second=round(got / 1024**2 / elapsed,3))
    except Paused:
        raise
    except Exception as exc:
        record.update(error=str(exc), seconds=round(time.monotonic()-start,3))
    return record

def ranked_sources(entry, mode, mirror_ids, stop, on_route=None):
    options = candidates(entry, mode, mirror_ids)
    if mode != 'auto' or len(options) <= 1:
        return options, []
    if on_route:
        on_route('正在短测速选路：每个来源最多读取 1 MiB，不代表完整文件已通过校验。')
    records = []
    with ThreadPoolExecutor(max_workers=min(3,len(options))) as executor:
        futures = [executor.submit(probe_source, name, url, entry.size, stop) for name,url in options]
        for future in as_completed(futures):
            records.append(future.result())
    if stop.is_set():
        raise Paused()
    good = sorted((x for x in records if x['ok']), key=lambda x:-x['mib_per_second'])
    if good:
        ordered = [(x['name'],x['url']) for x in good]
        # An unavailable mirror is not repeatedly retried. Origin remains the final safe route.
        if all(u != entry.url for _,u in ordered):
            ordered.append(('GitHub 源站',entry.url))
    else:
        ordered = [('GitHub 源站',entry.url)]
    return ordered, records

def download_release(entry, root, stop, limiter=None, progress=None, mode='origin', mirror_ids=None, on_route=None):
    if not public_release_url(entry.url):
        raise DownloadError('镜像功能仅适用于公开 GitHub Releases 附件。')
    options, probes = ranked_sources(entry, mode, mirror_ids, stop, on_route)
    failures = []
    for name,url in options:
        if stop.is_set():
            raise Paused()
        if on_route:
            on_route('当前下载线路：' + name + '；完成后校验 SHA-256。')
        try:
            result = download_file(replace(entry,url=url),root,stop,limiter,progress,WebClient())
            result['source_name'] = name
            result['mirror_used'] = url != entry.url
            result['fallbacks'] = list(failures)
            result['probes'] = [{k:v for k,v in p.items() if k!='url'} for p in probes]
            return result
        except Paused:
            raise
        except Exception as exc:
            failures.append({'name':name,'error':str(exc)})
            if on_route:
                on_route(name + ' 失败，切换下一个已允许的来源。')
    raise DownloadError('已尝试所有允许的 GitHub 线路：' + '；'.join(f['name']+'：'+f['error'] for f in failures))
