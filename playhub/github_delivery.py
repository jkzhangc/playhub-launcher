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
# GHProxy.net timed out in the latest sample and is not bundled.
MIRRORS = {'ghproxy': ('GH-Proxy', 'https://gh-proxy.com/'), 'ghfast': ('GHFast', 'https://ghfast.top/')}
ASSET_PATH = re.compile(r'^/[^/]+/[^/]+/releases/download/[^/]+/[^/]+$')

def public_release_url(url):
    try:
        u = parse.urlsplit(url)
        return (u.scheme == 'https' and u.hostname == 'github.com' and not u.username
                and not u.password and not u.query and not u.fragment and bool(ASSET_PATH.fullmatch(u.path)))
    except ValueError:
        return False

OFFICIAL_REPOSITORY = 'jkzhangc/playhub-launcher'

def update_files(repository=OFFICIAL_REPOSITORY, *, mirror_ids=('ghproxy',)):
    """Mirror results are discovery-only; never trust their digests for downloads."""
    import json
    from .sources import MAX_METADATA
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise DownloadError('GitHub 仓库名称无效。')
    api_url = 'https://api.github.com/repos/' + repository + '/releases?per_page=20'
    routes = [('GitHub 官方 API', api_url)] + [(MIRRORS[k][0]+' 镜像', MIRRORS[k][1]+api_url) for k in mirror_ids if k in MIRRORS]
    for index, (name, url) in enumerate(routes):
        try:
            with WebClient().open(url, timeout=5) as response:
                raw=response.read(MAX_METADATA+1)
            if len(raw)>MAX_METADATA:raise ValueError('版本清单过大')
            releases=json.loads(raw)
            eligible=[]
            for release in releases:
                tag=release.get('tag_name','')
                version=update_version(tag)
                if version is None or release.get('draft'):continue
                package='PlayHub-'+'.'.join(map(str,version[:3]))+'-alpha-win-x64.zip'
                official='https://github.com/'+repository+'/releases/download/'+tag+'/'+package
                asset=next((a for a in release.get('assets',[]) if a.get('name')==package and a.get('browser_download_url')==official and a.get('state')=='uploaded'),None)
                if asset:eligible.append((version,tag,asset))
            if not eligible:
                if index==0:raise DownloadError('尚无可用的 PlayHub 启动器发行附件。')
                continue
            _,tag,asset=max(eligible,key=lambda item:item[0]);digest=asset.get('digest') or ''
            sha=digest[7:] if index==0 and re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest) else ''
            return tag,name,FileEntry(str(asset['id']),asset['name'],int(asset['size']),asset['browser_download_url'],sha256=sha),index==0
        except (DownloadError,OSError,TypeError,ValueError,KeyError,AttributeError) as exc:
            if index==0 and isinstance(exc,DownloadError) and str(exc).startswith('尚无'):raise
    raise DownloadError('更新查询失败：GitHub 源站及所选镜像未返回有效版本。')

def update_version(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-alpha(?:[.-](\d+))?)?',value)
    if not match:return None
    a,b,c,n=match.groups()
    return int(a),int(b),int(c),(-1 if '-alpha' in value and n is None else int(n) if n else 2147483647)

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

def resolve_public_asset(url):
    _, owner, repo, _, _, tag, _ = parse.urlsplit(url).path.split('/')
    _, entries = release_files(owner+'/'+repo, parse.unquote(tag))
    match = next((entry for entry in entries if entry.url==url),None)
    if match is None:raise DownloadError('GitHub 未返回与该地址匹配的发行附件。')
    return match


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

class SlowOrigin(DownloadError):
    pass


def probe_source(name, url, size, stop, *, expected_size=None):
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
                if not m or int(m.group(1)) != sample_size-1 or ((size if expected_size is None else expected_size) >= 0 and int(m.group(2)) != (size if expected_size is None else expected_size)):
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
    if mode=='smart' and len(options)>1:
        options.append(options[0])  # One last origin attempt if the alternate fails.
    failures = []
    alternatives = {}
    slow_checked = False
    for attempt,(name,url) in enumerate(options):
        window_start = None
        window_bytes = 0
        def monitor(done, total, speed):
            nonlocal window_start, window_bytes, slow_checked
            if progress:progress(done,total,speed)
            if mode!='smart' or attempt!=0 or len(options)<2 or slow_checked or stop.is_set():return
            if limiter and 0 < limiter.rate <= 1024**2:return
            if total<=0 or total-done<2*1024*1024:return
            now=time.monotonic()
            if window_start is None:
                window_start,window_bytes=now,done
                return
            if now-window_start<8:return
            rate=(done-window_bytes)/(now-window_start)
            window_start,window_bytes=now,done
            if rate >= 1024**2:return
            slow_checked=True
            if on_route:on_route('源站持续低于 1 MiB/s，正在试测备用镜像。')
            for label,alternate in options[1:]:
                if alternate==entry.url:continue
                sample=probe_source(label,alternate,min(entry.size,262144) if entry.size>0 else 262144,stop,expected_size=entry.size)
                probes.append(sample)
                if sample['ok'] and sample['mib_per_second']*1024**2 >= max(128*1024,rate*1.5):
                    alternatives[alternate]=sample['mib_per_second']
            if alternatives:
                options[1:-1]=sorted(options[1:-1],key=lambda route:-alternatives.get(route[1],0))
                raise SlowOrigin('源站持续慢速，切换到更快的镜像；跨线路重新校验下载。')
        if stop.is_set():
            raise Paused()
        if on_route:
            on_route('当前下载线路：' + name + '；完成后校验 SHA-256。')
        try:
            if alternatives and url != entry.url and url not in alternatives:continue
            result = download_file(replace(entry,url=url),root,stop,limiter,monitor,WebClient())
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
