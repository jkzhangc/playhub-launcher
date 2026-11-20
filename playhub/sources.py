"""Read-only source discovery. No authentication or CAPTCHA bypass."""
from __future__ import annotations
import email.message
import http.cookiejar
import json
import re
from pathlib import Path
from urllib import parse, request, error
from .core import AuthorizationRequired, DownloadError, FileEntry, USER_AGENT, safe_relative

MAX_METADATA = 8 * 1024 * 1024

def check_url(url: str, local_test: bool = False):
    p = parse.urlsplit(url)
    local = p.hostname in ('127.0.0.1', 'localhost', '::1')
    if p.username or p.password or not p.hostname or not (p.scheme == 'https' or (local_test and local and p.scheme == 'http')):
        raise DownloadError('请提供 HTTPS 地址（仅本机测试允许 HTTP）。')
    return p

class WebClient:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.cookies))

    def open(self, url, headers=None, method='GET', timeout=25):
        check_url(url, local_test=True)
        req = request.Request(url, headers={'User-Agent': getattr(self, 'user_agent', '') or USER_AGENT, 'Accept-Encoding': 'identity', **(headers or {})}, method=method)
        try:
            result = self.opener.open(req, timeout=timeout)
        except error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthorizationRequired(f'来源返回 HTTP {e.code}，需要有效授权；不会绕过访问限制。') from e
            if e.code == 429:
                raise DownloadError('来源限制请求频率，请稍后重试。') from e
            raise DownloadError(f'来源返回 HTTP {e.code}。') from e
        except (error.URLError, TimeoutError, OSError) as e:
            raise DownloadError(f'连接失败：{e}') from e
        check_url(result.url, local_test=True)
        final = parse.urlsplit(result.url)
        if '/login' in final.path or '/signup' in final.path:
            result.close()
            raise AuthorizationRequired('来源要求登录后下载，请先使用该平台认可的授权方式。')
        return result

    def text(self, url, headers=None):
        with self.open(url, headers=headers) as r:
            data = r.read(MAX_METADATA + 1)
            if len(data) > MAX_METADATA:
                raise DownloadError('来源元数据过大。')
            return data.decode('utf-8-sig', errors='replace')

    def json(self, url):
        try:
            return json.loads(self.text(url))
        except ValueError as e:
            raise DownloadError('来源未返回有效 JSON。') from e


def direct_entry(url: str, web: WebClient | None = None) -> FileEntry:
    web = web or WebClient()
    with web.open(url, headers={'Range': 'bytes=0-0'}) as r:
        content_type = r.headers.get_content_type()
        if content_type in ('text/html', 'application/xhtml+xml'):
            raise DownloadError('这是网页地址，不是文件直链。请使用网盘适配器或合法文件地址。')
        msg = email.message.Message()
        msg['Content-Disposition'] = r.headers.get('Content-Disposition', '')
        name = msg.get_filename() or parse.unquote(Path(parse.urlsplit(r.url).path).name) or 'download.bin'
        safe_relative(name)
        size = -1
        cr = r.headers.get('Content-Range', '')
        if '/' in cr and cr.rsplit('/', 1)[1].isdigit():
            size = int(cr.rsplit('/', 1)[1])
        elif r.headers.get('Content-Length', '').isdigit() and r.status == 200:
            size = int(r.headers['Content-Length'])
        return FileEntry('0', name, size, url)

def manifest_entries(url: str, web: WebClient | None = None) -> list[FileEntry]:
    """Explicit PlayHub manifest, not archive contents or webpage scraping."""
    data = (web or WebClient()).json(url)
    if data.get('format') != 'playhub-files-v1' or not isinstance(data.get('files'), list):
        raise DownloadError('不是 PlayHub 多文件清单（playhub-files-v1）。')
    if not 1 <= len(data['files']) <= 10000:
        raise DownloadError('清单文件数量超出限制。')
    out, names = [], set()
    for i, f in enumerate(data['files']):
        name, target = str(f.get('path', '')), parse.urljoin(url, str(f.get('url', '')))
        safe_relative(name)
        check_url(target, local_test=True)
        if name.casefold() in names:
            raise DownloadError('清单中含重名文件，已停止。')
        names.add(name.casefold())
        sha = str(f.get('sha256', ''))
        if sha and not re.fullmatch('[a-fA-F0-9]{64}', sha):
            raise DownloadError('清单中的 SHA-256 无效。')
        out.append(FileEntry(str(i), name, int(f.get('size', -1)), target, sha256=sha))
    return out

class NutstoreShare:
    """Use public directory requests made by the standard share page.

    Listing is supported. If the normal share requires sign-in, resolution stops.
    An authenticated public-share download API is intentionally NOT guessed.
    """
    def __init__(self, url: str, web: WebClient | None = None):
        p = check_url(url)
        if p.hostname not in ('www.jianguoyun.com', 'jianguoyun.com') or not p.path.startswith('/p/'):
            raise DownloadError('请输入坚果云标准公开分享链接。')
        self.hash = p.path.split('/')[2]
        if not re.fullmatch('[a-zA-Z0-9_-]{10,100}', self.hash):
            raise DownloadError('无效的坚果云分享标识。')
        self.url = 'https://www.jianguoyun.com/p/' + self.hash
        self.web = web or WebClient()
        self.login_required = False
        self.disabled = False

    def inspect(self):
        text = self.web.text(self.url)
        self.login_required = bool(re.search(r'download_need_signin\s*:\s*true', text))
        self.disabled = bool(re.search(r'download_is_disabled\s*:\s*true', text))
        if self.disabled:
            raise AuthorizationRequired('分享所有者禁用了下载。')
        return {'login_required': self.login_required, 'disabled': self.disabled}

    def list_folder(self, relative='/'):
        if not relative.startswith('/') or '..' in relative.split('/'):
            raise DownloadError('分享目录路径无效。')
        url = 'https://www.jianguoyun.com/d/ajax/dirops/pubDIRBrowse?' + parse.urlencode({'hash': self.hash, 'relPath': relative})
        data = self.web.json(url)
        if 'objects' not in data:
            raise AuthorizationRequired('无法列出分享目录，可能需要登录、密码或分享已失效。')
        if data.get('isTruncated'):
            raise DownloadError('分享文件列表被截断；为避免遗漏，暂不开始下载。')
        return data['objects']

    def files(self, relative='/', max_files=3000):
        self.inspect()
        result, pending, visited = [], [relative], set()
        while pending:
            folder = pending.pop(0)
            if folder in visited:
                continue
            visited.add(folder)
            if len(visited) > 100:
                raise DownloadError('目录层级过多，请选择更小的分享。')
            for obj in self.list_folder(folder):
                rel = str(obj.get('relPath', ''))
                safe_relative(rel.lstrip('/'))
                if obj.get('type') == 'directory':
                    pending.append(rel)
                elif obj.get('type') == 'file':
                    result.append(FileEntry(rel, rel.lstrip('/'), int(obj.get('size', -1)), self.url, 'nutstore'))
                    if len(result) > max_files:
                        raise DownloadError('分享文件过多，请缩小范围。')
        return result

    def resolve(self, entry: FileEntry):
        if self.login_required:
            raise AuthorizationRequired('这份坚果云分享要求登录后下载；已验证可列目录，但未获得下载授权。请提供官方授权后得到的有效 HTTPS 直链，或调整分享权限后再测试。')
        raise DownloadError('此版本已支持坚果云目录选择，但尚未验证该类分享的下载接口；不猜测链接或绕过平台限制。')
