"""Resolve supported Lanzou public shares using their normal password form.

No password guessing, CAPTCHA solving, login bypass or arbitrary JS execution.
"""
from __future__ import annotations
import json
import re
from urllib import parse, request, error
from .core import DownloadError, AuthorizationRequired, FileEntry, USER_AGENT, safe_relative
from .sources import WebClient, check_url, direct_entry, MAX_METADATA

SHARE_ROOTS = ('lanzou.com', 'lanzoui.com', 'lanzoux.com', 'lanzous.com', 'lanzouq.com',
               'lanzouw.com', 'lanzout.com', 'lanzouo.com', 'lanzouj.com', 'lanzoue.com',
               'lanzouu.com', 'lanzouv.com', 'lanzoup.com')

def is_lanzou_host(host: str) -> bool:
    host = host.lower()
    return any(host == root or host.endswith('.' + root) for root in SHARE_ROOTS)

class LanzouShare:
    def __init__(self, url, password='', web=None):
        p = check_url(url)
        if not is_lanzou_host(p.hostname):
            raise DownloadError('不是已支持的蓝奏云分享域名。')
        self.url, self.password = url, password
        self.web = web or WebClient()

    def files(self):
        html = self.web.text(self.url)
        # Support only the observed standard password form, not arbitrary page code.
        signs = re.findall(r"var\s+isngis\s*=\s*['\"]([^'\"]+)['\"]", html)
        endpoint = re.search(r"url\s*:\s*['\"](https://apifile\.woozooo\.com/ajaxfile\.php\?file=\d+)['\"]", html)
        kd = re.search(r'var\s+kdns\s*=\s*(\d+)', html)
        if not signs or not endpoint:
            raise DownloadError('此蓝奏云页面格式尚未适配，或需要手动验证码；不会猜测接口。可使用设置中的官方页面下载转接。')
        if not self.password:
            raise AuthorizationRequired('该蓝奏云文件需要提取码，请填写分享者提供的提取码。')
        body = parse.urlencode({'action': 'downprocess', 'sign': signs[-1], 'kd': kd.group(1) if kd else '1', 'p': self.password}).encode()
        req = request.Request(endpoint.group(1), data=body, headers={
            'User-Agent': USER_AGENT, 'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': self.url, 'Origin': parse.urlunsplit((parse.urlsplit(self.url).scheme, parse.urlsplit(self.url).netloc, '', '', ''))})
        try:
            with self.web.opener.open(req, timeout=25) as r:
                raw = r.read(MAX_METADATA + 1)
                if len(raw) > MAX_METADATA:
                    raise DownloadError('蓝奏云响应过大。')
                result = json.loads(raw)
        except (error.URLError, ValueError, TimeoutError) as e:
            raise DownloadError('蓝奏云提取码请求失败：' + str(e)) from e
        if str(result.get('zt')) != '1':
            raise AuthorizationRequired('蓝奏云未授权下载：' + str(result.get('inf', '请检查提取码、分享有效期或平台提示。')))
        domain = str(result.get('dom', ''))
        parsed = check_url(domain)
        # Download host is returned by the normal share form. Restrict known file-CDN families.
        if not any(parsed.hostname == root or parsed.hostname.endswith('.' + root) for root in ('lanrar.com', 'lanzou.com', 'woozooo.com', 'lanzoux.com', 'lanzoui.com', 'lanzouw.com')):
            raise DownloadError('蓝奏云返回未验证的下载域名，请通过官方页面确认。')
        token = str(result.get('url', ''))
        if not token or token.startswith(('http:', 'https:', '//')) or '\r' in token or '\n' in token:
            raise DownloadError('蓝奏云下载标识无效。')
        download_url = domain.rstrip('/') + '/file/' + token
        filename = str(result.get('inf', ''))
        safe_relative(filename)
        entry = direct_entry(download_url, self.web)
        entry.key = 'lanzou-authorized'
        entry.path = filename
        return [entry]
