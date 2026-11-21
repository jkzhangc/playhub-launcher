"""MediaFire public single-file shares; no authentication or challenge bypass."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib import parse, request

from .core import AuthorizationRequired, DownloadError
from .sources import MAX_METADATA, WebClient, direct_entry

_SHARE_HOSTS = {'mediafire.com', 'www.mediafire.com'}
_CDN = re.compile(r'download[0-9]*\.mediafire\.com', re.IGNORECASE)


def is_mediafire_host(host):
    return isinstance(host, str) and (host.lower() in _SHARE_HOSTS or bool(_CDN.fullmatch(host)))


def checked_mediafire_url(url):
    try:
        item = parse.urlsplit(url)
        if (len(url) > 16384 or any(ch.isspace() or ord(ch) < 32 for ch in url)
                or item.scheme != 'https' or not is_mediafire_host(item.hostname or '')
                or item.username or item.password or item.port not in (None, 443)
                or item.fragment):
            raise ValueError()
        return item
    except (ValueError, TypeError):
        raise DownloadError('MediaFire 地址必须是官方 HTTPS 分享链接或官方下载域名，不接受外站或降级跳转。') from None


class _ScopedRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_mediafire_url(parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MediaFireWebClient(WebClient):
    def __init__(self):
        super().__init__()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.cookies), _ScopedRedirect())

    def open(self, url, headers=None, method='GET', timeout=25):
        checked_mediafire_url(url)
        try:
            result = super().open(url, headers=headers, method=method, timeout=timeout)
        except AuthorizationRequired:
            raise AuthorizationRequired('MediaFire 要求登录或验证，请在官网完成；启动器不会绕过限制。') from None
        except DownloadError:
            raise DownloadError('MediaFire 请求失败或下载跳转不被允许，请检查分享状态和网络。') from None
        try:
            checked_mediafire_url(result.url)
        except DownloadError:
            result.close()
            raise
        return result


class _DownloadButton(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.restricted = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        identity = ' '.join(str(attrs.get(key) or '') for key in ('id', 'class', 'action')).lower()
        if tag == 'input' and (attrs.get('type') or '').lower() == 'password':
            self.restricted = True
        if tag in ('form', 'iframe', 'div') and ('captcha' in identity or 'password-form' in identity):
            self.restricted = True
        if tag == 'a' and ((attrs.get('id') or '').lower() == 'downloadbutton'
                or (attrs.get('aria-label') or '').strip().lower() == 'download file'):
            href = attrs.get('href')
            if href and href not in self.links:
                self.links.append(href)


def resolve_mediafire(url, web=None):
    """Return (direct FileEntry, in-memory session) without persisting CDN URLs."""
    parsed = checked_mediafire_url(url)
    web = web or MediaFireWebClient()
    if _CDN.fullmatch(parsed.hostname or ''):
        return direct_entry(url, web), web
    path = parse.unquote(parsed.path).lower()
    if path.startswith(('/folder/', '/folder')):
        raise DownloadError('当前仅支持 MediaFire 单文件公开分享；文件夹请提供其中每个文件的分享链接。')
    if not (path.startswith('/file/') or (path in ('', '/') and parsed.query)):
        raise DownloadError('请提供 MediaFire 单文件分享链接。')
    with web.open(url) as response:
        page_url = response.url
        final = checked_mediafire_url(page_url)
        if final.hostname not in _SHARE_HOSTS:
            raise DownloadError('MediaFire 分享页未返回可解析的官方下载按钮。')
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise DownloadError('MediaFire 分享页格式不受支持，请使用标准单文件分享链接。')
        page = response.read(MAX_METADATA + 1)
    if len(page) > MAX_METADATA:
        raise DownloadError('MediaFire 分享页超过大小限制，未解析。')
    parser = _DownloadButton()
    parser.feed(page.decode('utf-8-sig', errors='replace'))
    if parser.restricted:
        raise AuthorizationRequired('此 MediaFire 分享需要密码或验证码，请在官网完成；不会自动提交或绕过验证。')
    if not parser.links:
        raise DownloadError('未找到 MediaFire 官方下载按钮；分享可能失效、受限或需要浏览器验证。')
    if len(parser.links) != 1:
        raise DownloadError('MediaFire 返回多个不同下载按钮，已停止以避免选中错误来源。')
    target = parse.urljoin(page_url, parser.links[0])
    download = checked_mediafire_url(target)
    if not _CDN.fullmatch(download.hostname or ''):
        raise DownloadError('MediaFire 下载按钮未指向官方文件 CDN，未访问该链接。')
    return direct_entry(target, web), web
