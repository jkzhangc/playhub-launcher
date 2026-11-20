import hashlib
import json
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playhub.core import DownloadError,FileEntry,safe_relative,hash_file
from playhub.sources import WebClient,direct_entry,manifest_entries,NutstoreShare
from playhub.http_engine import download_file,RateLimiter,Paused

ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=(b'PlayHub-controlled-test-'*100000)
ETAG='"playhub-v1"'
REQUESTS=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        REQUESTS.append((self.path,self.headers.get('Range'),self.headers.get('If-Range')))
        if self.path=='/files.json':
            data=json.dumps({'format':'playhub-files-v1','files':[{'path':'mobile/test.apk','url':'/mobile.bin','size':len(PAYLOAD),'sha256':hashlib.sha256(PAYLOAD).hexdigest()},{'path':'desktop/test.zip','url':'/desktop.bin','size':len(PAYLOAD)}]}).encode();mime='application/json'
        elif self.path=='/bad.json':data=json.dumps({'format':'playhub-files-v1','files':[{'path':'../outside.exe','url':'/mobile.bin'}]}).encode();mime='application/json'
        elif self.path=='/html':data=b'<html>login required</html>';mime='text/html'
        else:data=PAYLOAD;mime='application/octet-stream'
        start,end=0,len(data)-1
        if self.headers.get('Range') and self.path!='/ignore-range':
            spec=self.headers['Range'].split('=')[1];left,right=spec.split('-');start=int(left);end=min(int(right),end) if right else end
            self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
        else:self.send_response(200)
        body=data[start:end+1];self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('ETag',ETAG);self.end_headers()
        try:
            for i in range(0,len(body),65536):self.wfile.write(body[i:i+65536])
        except (ConnectionResetError,BrokenPipeError,ConnectionAbortedError):pass

class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_port}';cls.root=ROOT/'validation'/('http-tests-'+uuid.uuid4().hex[:8]);cls.root.mkdir(parents=True)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def folder(self):p=self.root/uuid.uuid4().hex[:6];p.mkdir();return p
    def test_direct_file_complete(self):
        f=direct_entry(self.base+'/file.bin');self.assertEqual(f.size,len(PAYLOAD));p=self.folder();r=download_file(f,p,threading.Event());self.assertEqual(r['sha256'],hashlib.sha256(PAYLOAD).hexdigest())
    def test_multifile_selection_downloads_only_selected(self):
        fs=manifest_entries(self.base+'/files.json');self.assertEqual(len(fs),2);p=self.folder();r=download_file(fs[0],p,threading.Event());self.assertTrue((p/'mobile/test.apk').exists());self.assertFalse((p/'desktop').exists());self.assertEqual(r['bytes'],len(PAYLOAD))
    def test_pause_resume_with_range(self):
        f=FileEntry('a','resume.bin',len(PAYLOAD),self.base+'/resume.bin');p=self.folder();stop=threading.Event()
        def tick(d,t,s):
            if d>0:stop.set()
        with self.assertRaises(Paused):download_file(f,p,stop,progress=tick)
        part=p/'resume.bin.playhub.part';offset=part.stat().st_size;self.assertGreater(offset,0);r=download_file(f,p,threading.Event());self.assertEqual(r['resumed_from'],offset);self.assertEqual(r['sha256'],hashlib.sha256(PAYLOAD).hexdigest());self.assertIn(('/resume.bin',f'bytes={offset}-',ETAG),REQUESTS)
    def test_ignored_range_restarts_without_corruption(self):
        f=FileEntry('a','restart.bin',len(PAYLOAD),self.base+'/ignore-range');p=self.folder();stop=threading.Event()
        def tick(d,t,s):stop.set()
        with self.assertRaises(Paused):download_file(f,p,stop,progress=tick)
        r=download_file(f,p,threading.Event());self.assertEqual(r['resumed_from'],0);self.assertEqual(r['sha256'],hashlib.sha256(PAYLOAD).hexdigest())
    def test_rate_limit_measured(self):
        p=self.folder();limit=len(PAYLOAD)*2;started=time.monotonic();download_file(FileEntry('a','limited.bin',len(PAYLOAD),self.base+'/limited'),p,threading.Event(),RateLimiter(limit));elapsed=time.monotonic()-started;self.assertGreaterEqual(elapsed,.48);self.assertLess(elapsed,4)
    def test_html_is_not_saved_as_game(self):
        p=self.folder()
        with self.assertRaises(DownloadError):download_file(FileEntry('a','fake.exe',-1,self.base+'/html'),p,threading.Event())
        self.assertFalse((p/'fake.exe').exists())
    def test_hash_mismatch_quarantined(self):
        p=self.folder()
        with self.assertRaises(DownloadError):download_file(FileEntry('a','bad.bin',len(PAYLOAD),self.base+'/bad',sha256='0'*64),p,threading.Event())
        self.assertFalse((p/'bad.bin').exists());self.assertTrue((p/'bad.bin.playhub.part').exists())
    def test_existing_file_not_overwritten(self):
        p=self.folder();target=p/'file.bin';target.write_bytes(b'original')
        with self.assertRaises(DownloadError):download_file(FileEntry('a','file.bin',len(PAYLOAD),self.base+'/x'),p,threading.Event())
        self.assertEqual(target.read_bytes(),b'original')
    def test_path_traversal_rejected(self):
        for bad in ['../x','a/../x','C:/outside','/abs','CON.txt','a./x','a//x']:
            with self.subTest(path=bad):
                with self.assertRaises(DownloadError):safe_relative(bad)
    def test_bad_manifest_rejected(self):
        with self.assertRaises(DownloadError):manifest_entries(self.base+'/bad.json')

if __name__=='__main__':unittest.main(verbosity=2)
