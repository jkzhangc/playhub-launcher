import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from playhub.core import FileEntry,DownloadError
from playhub.http_engine import Paused
from playhub.github_delivery import candidates,public_release_url,ranked_sources,download_release,release_files

URL='https://github.com/example/game/releases/download/v1/game.zip'
ENTRY=FileEntry('1','game.zip',100,URL,sha256='a'*64)
class DeliveryTests(unittest.TestCase):
    def test_only_public_assets(self):
        self.assertTrue(public_release_url(URL))
        for value in [URL+'?token=secret',URL+'#fragment',URL.replace('github.com','github.com.evil.test'),URL.replace('https:','http:'),'https://user:pass@github.com/a/b/releases/download/v/a.zip']:
            self.assertFalse(public_release_url(value))
    def test_default_origin_only(self):
        self.assertEqual(candidates(ENTRY),[('GitHub 源站',URL)])
    def test_no_hash_no_mirror(self):
        self.assertEqual(len(candidates(FileEntry('1','x',100,URL),'auto')),1)
    def test_mirror_order_and_no_token(self):
        options=candidates(ENTRY,'mirror');self.assertTrue(options[0][1].startswith('https://gh-proxy.com/'));self.assertEqual(options[-1][1],URL)
    def test_short_probe_ranks_success(self):
        def fake(name,url,size,stop):return {'name':name,'url':url,'ok':True,'mib_per_second':5 if url==URL else 10}
        with patch('playhub.github_delivery.probe_source',side_effect=fake):
            ordered,records=ranked_sources(ENTRY,'auto',['ghproxy'],threading.Event());self.assertIn('gh-proxy.com',ordered[0][1]);self.assertEqual(len(records),2)
    def test_failed_probe_not_repeated(self):
        def fake(name,url,size,stop):return {'name':name,'url':url,'ok':False,'error':'timeout'}
        with patch('playhub.github_delivery.probe_source',side_effect=fake):
            ordered,_=ranked_sources(ENTRY,'auto',['ghproxy'],threading.Event());self.assertEqual(ordered,[('GitHub 源站',URL)])
    def test_mirror_failure_falls_back_once(self):
        with patch('playhub.github_delivery.download_file',side_effect=[DownloadError('mismatch'),{'bytes':100}]) as mocked:
            result=download_release(ENTRY,Path('.'),threading.Event(),mode='mirror');self.assertEqual(mocked.call_count,2);self.assertFalse(result['mirror_used']);self.assertEqual(len(result['fallbacks']),1)
    def test_pause_not_retried(self):
        with patch('playhub.github_delivery.download_file',side_effect=Paused()) as mocked:
            with self.assertRaises(Paused):download_release(ENTRY,Path('.'),threading.Event(),mode='mirror')
            self.assertEqual(mocked.call_count,1)
    def test_release_manifest_keeps_trusted_digest(self):
        class Fake:
            def json(self,url):return {'tag_name':'v1','assets':[{'id':3,'name':'game.zip','size':100,'browser_download_url':URL,'digest':'sha256:'+'a'*64}]}
        metadata,files=release_files('example/game',web=Fake());self.assertEqual(files[0].sha256,'a'*64);self.assertEqual(files[0].size,100)

    def test_slow_origin_switches_then_returns_if_mirror_fails(self):
        attempts=[]
        def fetch(entry, root, stop, limiter, progress, web):
            attempts.append(entry.url)
            if len(attempts)==1:
                progress(65536, 8*1024**2, 0)
                progress(131072, 8*1024**2, 0)
            elif len(attempts)==2:raise DownloadError('mirror unavailable')
            return {'bytes':100}
        with patch('playhub.github_delivery.download_file',side_effect=fetch), patch('playhub.github_delivery.time.monotonic',side_effect=[0,9]), patch('playhub.github_delivery.probe_source',return_value={'ok':True,'mib_per_second':1}):
            result=download_release(ENTRY,Path('.'),threading.Event(),mode='smart')
        self.assertEqual(len(attempts),3)
        self.assertEqual(attempts[0],attempts[2])
        self.assertIn('gh-proxy.com',attempts[1])
        self.assertFalse(result['mirror_used'])

    def test_smart_probes_sub_mib_origin_and_picks_fastest_mirror(self):
        attempts=[]
        def fetch(entry, root, stop, limiter, progress, web):
            attempts.append(entry.url)
            if entry.url==URL:
                progress(0, 16*1024**2, 0)
                progress(4*1024**2, 16*1024**2, 0)
            return {'bytes':100}
        def probe(name,url,size,stop,**kwargs):
            return {'ok':True,'mib_per_second':2 if 'ghfast.top' in url else 1}
        with patch('playhub.github_delivery.download_file',side_effect=fetch), patch('playhub.github_delivery.time.monotonic',side_effect=[0,9]), patch('playhub.github_delivery.probe_source',side_effect=probe):
            result=download_release(ENTRY,Path('.'),threading.Event(),mode='smart',mirror_ids=['ghproxy','ghfast'])
        self.assertEqual(attempts,[URL,'https://ghfast.top/'+URL])
        self.assertTrue(result['mirror_used'])

    def test_update_manifest_mirror_never_supplies_trusted_hash(self):
        import io,json
        from playhub.github_delivery import update_files, OFFICIAL_REPOSITORY
        package='PlayHub-0.2.2-alpha-win-x64.zip'
        url='https://github.com/'+OFFICIAL_REPOSITORY+'/releases/download/v0.2.2-alpha/'+package
        data=[{'tag_name':'v0.2.2-alpha','assets':[{'id':5,'size':100,'name':package,'state':'uploaded','browser_download_url':url,'digest':'sha256:'+'f'*64}]}]
        with patch('playhub.github_delivery.WebClient.open',side_effect=[DownloadError('offline'),io.BytesIO(json.dumps(data).encode())]) as opened:
            tag,line,entry,verified=update_files()
        self.assertEqual(tag,'v0.2.2-alpha');self.assertFalse(verified);self.assertEqual(entry.sha256,'')
        self.assertIn('gh-proxy.com',opened.call_args.args[0])

if __name__=='__main__':unittest.main(verbosity=2)
