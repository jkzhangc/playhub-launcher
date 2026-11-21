import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.request import Request

from playhub.core import AuthorizationRequired, DownloadError
from playhub.mediafire import (MediaFireWebClient, _ScopedRedirect,
                               checked_mediafire_url, is_mediafire_host, resolve_mediafire)
from playhub.sources import MAX_METADATA

SHARE='https://www.mediafire.com/file/abc123/game.zip/file'
CDN='https://download123.mediafire.com/temporary/key/game.zip'


class Response(io.BytesIO):
    def __init__(self, content=b'', url=SHARE, mime='text/html', headers=None, status=200):
        super().__init__(content)
        self.url=url;self.status=status;self.headers=Message()
        self.headers['Content-Type']=mime
        for key,value in (headers or {}).items():self.headers[key]=value


class FixtureWeb:
    def __init__(self, responses):self.responses=list(responses);self.calls=[]
    def open(self, url, headers=None, **kwargs):
        self.calls.append((url,headers))
        if not self.responses:raise AssertionError('Unexpected network request')
        return self.responses.pop(0)


def file_response(url=CDN):
    return Response(b'x',url,'application/octet-stream',
                    {'Content-Range':'bytes 0-0/4321',
                     'Content-Disposition':"attachment; filename*=UTF-8''%E6%B8%B8%E6%88%8F.zip"},206)


class MediaFireTests(unittest.TestCase):
    def test_public_button_entities_and_real_filename(self):
        page=('<a href="https://ads.invalid/download">Ad</a>'
              '<a id="downloadButton" href="'+CDN+'?key=public&amp;dl=1">Download</a>')
        web=FixtureWeb([Response(page.encode()),file_response(CDN+'?key=public&dl=1')])
        entry,session=resolve_mediafire(SHARE,web)
        self.assertIs(session,web);self.assertEqual(entry.path,'游戏.zip')
        self.assertEqual(entry.size,4321);self.assertEqual(entry.provider,'direct')
        self.assertEqual(entry.url,CDN+'?key=public&dl=1')
        self.assertEqual(web.calls[1][1],{'Range':'bytes=0-0'})
        self.assertEqual(len(web.calls),2)

    def test_direct_cdn_and_aria_label(self):
        web=FixtureWeb([file_response()])
        entry,_=resolve_mediafire(CDN,web);self.assertEqual(entry.url,CDN)
        self.assertEqual(len(web.calls),1)
        web=FixtureWeb([Response(('<a aria-label="Download file" href="'+CDN+'">Get</a>').encode()),file_response()])
        entry,_=resolve_mediafire(SHARE,web);self.assertEqual(entry.size,4321)

    def test_untrusted_inputs_rejected_before_request(self):
        for url in ('https://mediafire.com.evil.test/file/a',
                    'https://evilmediafire.com/file/a','https://download.mediafire.com.evil.test/a',
                    'https://user:pass@www.mediafire.com/file/a','http://www.mediafire.com/file/a',
                    'https://www.mediafire.com:8443/file/a','javascript:alert(1)',
                    'https://www.mediafire.com/file/a#fragment',
                    'https://www.mediafire.com/file/a\nInjected'):
            web=FixtureWeb([])
            with self.subTest(url=url),self.assertRaises(DownloadError):resolve_mediafire(url,web)
            self.assertEqual(web.calls,[])
        self.assertTrue(is_mediafire_host('www.mediafire.com'))
        self.assertFalse(is_mediafire_host('evil.mediafire.com'))

    def test_untrusted_button_is_not_followed(self):
        for target in ('https://ads.invalid/game.zip','javascript:alert(1)',
                       'http://download123.mediafire.com/game.zip',
                       'https://www.mediafire.com/login','https://download.evil.mediafire.com/a'):
            web=FixtureWeb([Response(('<a id="downloadButton" href="'+target+'">Get</a>').encode())])
            with self.subTest(target=target),self.assertRaises(DownloadError):resolve_mediafire(SHARE,web)
            self.assertEqual(len(web.calls),1)

    def test_password_captcha_and_missing_button(self):
        for page in ('<input type="password">','<div class="g-recaptcha"></div>',
                     '<form action="/captcha"></form>'):
            web=FixtureWeb([Response(page.encode())])
            with self.subTest(page=page),self.assertRaises(AuthorizationRequired):resolve_mediafire(SHARE,web)
            self.assertEqual(len(web.calls),1)
        web=FixtureWeb([Response(b'<html>File unavailable</html>')])
        with self.assertRaises(DownloadError):resolve_mediafire(SHARE,web)

    def test_folders_and_oversized_pages(self):
        web=FixtureWeb([])
        with self.assertRaisesRegex(DownloadError,'单文件'):resolve_mediafire('https://www.mediafire.com/folder/abc',web)
        self.assertEqual(web.calls,[])
        web=FixtureWeb([Response(b'x'*(MAX_METADATA+1))])
        with self.assertRaisesRegex(DownloadError,'大小限制'):resolve_mediafire(SHARE,web)

    def test_conflicting_buttons_rejected(self):
        page='<a id="downloadButton" href="'+CDN+'">A</a><a id="downloadButton" href="'+CDN+'?other=1">B</a>'
        web=FixtureWeb([Response(page.encode())])
        with self.assertRaisesRegex(DownloadError,'多个'):resolve_mediafire(SHARE,web)
        self.assertEqual(len(web.calls),1)

    def test_redirect_validated_before_following(self):
        handler=_ScopedRedirect();req=Request(SHARE)
        for target in ('https://evil.test/a','http://download123.mediafire.com/a',
                       'https://download123.mediafire.com.evil.test/a'):
            with self.subTest(target=target),self.assertRaises(DownloadError):
                handler.redirect_request(req,None,302,'Found',{},target)
        following=handler.redirect_request(req,None,302,'Found',{},CDN)
        self.assertEqual(following.full_url,CDN)

    def test_download_session_stays_scoped(self):
        session=MediaFireWebClient()
        with patch.object(session.opener,'open') as opening:
            with self.assertRaises(DownloadError):session.open('https://external.invalid/file')
            opening.assert_not_called()
        with patch('playhub.mediafire.WebClient.open',side_effect=AuthorizationRequired('sensitive-url')):
            with self.assertRaises(AuthorizationRequired) as ctx:session.open(SHARE)
            self.assertNotIn('sensitive-url',str(ctx.exception))


if __name__=='__main__':unittest.main(verbosity=2)
