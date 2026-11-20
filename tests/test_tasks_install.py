import hashlib
import json
import threading
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch
from playhub.core import FileEntry,StateStore,hash_file,DownloadError
from playhub.manager import DownloadManager
from playhub.install import install_zip

ROOT=Path(__file__).resolve().parent.parent/'validation'
class FakeP2P:
    def __init__(self,*a,**kw):pass
    def close(self):pass
    def set_limit(self,*a):pass
class TaskTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/('tasks-'+uuid.uuid4().hex[:8]);self.root.mkdir()
        self.store=StateStore(self.root/'state')
        self.patch=patch('playhub.manager.TorrentEngine',FakeP2P);self.patch.start();self.manager=DownloadManager(self.store)
    def tearDown(self):self.manager.close();self.patch.stop()
    def make(self):return self.manager.add([FileEntry('a','file.bin',4,'https://example.com/file.bin')],self.root/'downloads',deferred=True)
    def test_deferred_auth_preserves_choice_and_directory(self):
        task=self.make();self.assertEqual(task['status'],'auth_required');self.assertEqual(task['files'][0]['path'],'file.bin');self.assertTrue(task['directory'].endswith('downloads'))
    def test_authorization_uses_existing_task_no_second_selection(self):
        task=self.make();entry=FileEntry('a','file.bin',4,'https://cdn.example.com/signed?token=ephemeral')
        with patch.object(self.manager,'start_next'):
            self.manager.authorize(task['id'],[entry],object())
        self.assertEqual(len(self.manager.tasks),1);self.assertEqual(task['status'],'queued');self.assertEqual(task['files'][0]['url'],'');self.assertNotIn('ephemeral',self.store.path.read_text('utf-8'))
    def test_auth_rejects_unselected_file(self):
        task=self.make()
        with self.assertRaises(ValueError):self.manager.authorize(task['id'],[FileEntry('x','other.bin',4,'https://example.com/x')],object())
    def test_remove_task_keeps_files_by_default(self):
        task=self.make();p=Path(task['directory']);p.mkdir();f=p/'file.bin';f.write_bytes(b'data');self.manager.remove(task['id']);self.assertTrue(f.exists());self.assertFalse(self.manager.tasks)
    def test_recycle_only_recorded_unchanged_task_files(self):
        task=self.make();p=Path(task['directory']);p.mkdir();f=p/'file.bin';f.write_bytes(b'data');other=p/'other.txt';other.write_bytes(b'keep');self.manager._record_outputs(task,[{'path':str(f),'bytes':4,'sha256':hash_file(f),'existing':False}]);self.assertEqual(self.manager.deletion_files(task['id']),[str(f)]);seen=[];self.manager.remove(task['id'],recycle=lambda name:seen.append(name) or True);self.assertEqual(seen,[str(f)]);self.assertTrue(other.exists())
    def test_modified_file_not_deleted(self):
        task=self.make();p=Path(task['directory']);p.mkdir();f=p/'file.bin';f.write_bytes(b'data');self.manager._record_outputs(task,[{'path':str(f),'bytes':4,'sha256':hash_file(f),'existing':False}]);f.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.manager.deletion_files(task['id'])
    def test_active_task_cannot_be_removed(self):
        task=self.make();task['status']='downloading'
        with self.assertRaises(ValueError):self.manager.remove(task['id'])
    def test_missing_task_auth_does_not_restart(self):
        task=self.make();self.manager.remove(task['id'])
        with self.assertRaises(ValueError):self.manager.authorize(task['id'],[],object())

class InstallTests(unittest.TestCase):
    def setUp(self):self.root=ROOT/('install-'+uuid.uuid4().hex[:8]);self.root.mkdir()
    def archive(self,names):
        p=self.root/'game.zip'
        with zipfile.ZipFile(p,'w') as z:
            for name,data in names:z.writestr(name,data)
        return p
    def test_safe_extract_configured_exe(self):
        archive=self.archive([('MyGame/Game.exe',b'controlled-not-executable-test'),('MyGame/data.txt',b'data')]);result=install_zip(archive,self.root,{'game_id':'test','executable':'MyGame/Game.exe','name':'Test'});self.assertTrue(Path(result['executable']).exists());self.assertEqual(len(result['files']),2)
    def test_traversal_zip_rejected(self):
        archive=self.archive([('../escape.exe',b'x')])
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})
        self.assertFalse((self.root/'escape.exe').exists())
    def test_unconfigured_exe_not_guessed(self):
        archive=self.archive([('Other.exe',b'x')])
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})
    def test_apk_not_extracted_as_windows_game(self):
        archive=self.root/'test.apk';archive.write_bytes(b'fake')
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})
    def test_case_collision_rejected(self):
        archive=self.archive([('Game.exe',b'a'),('game.exe',b'b')])
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})

if __name__=='__main__':unittest.main(verbosity=2)
