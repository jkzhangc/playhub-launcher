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
from playhub.install import install_zip, install_archives

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

    def test_task_extracts_two_nested_versions_without_launch_registration(self):
        root=self.root/'downloads'; paths=['versions/one.zip','versions/two.zip']
        task=self.manager.add([FileEntry(str(i),name,4,'https://example.com/game.zip') for i,name in enumerate(paths)],root,deferred=True,install={'enabled':True,'game_id':'test'})
        def download(entry, folder, *_):
            dest=(folder/entry.path).resolve();dest.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(dest,'w') as archive:archive.writestr(dest.stem+'.exe',b'fixture')
            return {'path':str(dest),'bytes':dest.stat().st_size,'sha256':hash_file(dest)}
        with patch('playhub.manager.download_file',side_effect=download):
            self.manager._run(task,threading.Event())
        self.assertEqual(task['status'],'complete')
        self.assertEqual(len(task['extracted_packages']),2)
        self.assertEqual(self.store.data['library'],[])
        self.assertTrue(all((root/name).is_file() for name in paths))

    def versioned_task(self, enabled=True, files=None):
        old=self.root/'old-game';old.mkdir();(old/'Game.exe').write_bytes(b'old executable fixture')
        original={'id':'test','name':'My game name','custom_name':'My game name','version':'1.0',
                  'installed_version':'1.0','tracked_version':'1.0','executable':str(old/'Game.exe'),
                  'install_directory':str(old)}
        self.store.data['library']=[original]
        entries=files or [FileEntry('1','game.zip',4,'https://example.com/game.zip')]
        task=self.manager.add(entries,self.root/'new-download',deferred=True,
            install={'enabled':enabled,'game_id':'test','name':'Catalog game','executable':'Game.exe',
                     'version':'2.0','catalog_game':{'id':'test','name':'Catalog game','version':'2.0',
                     'description':'Latest description','source':'https://example.com/game.zip'}})
        return task,original,old

    def zip_download(self, entry, folder, *_):
        dest=folder/entry.path;dest.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(dest,'w') as archive:archive.writestr('Game.exe',b'new executable fixture')
        return {'path':str(dest),'bytes':dest.stat().st_size,'sha256':hash_file(dest)}

    def test_successful_registered_install_updates_version_and_keeps_old_files(self):
        task,original,old=self.versioned_task()
        with patch('playhub.manager.download_file',side_effect=self.zip_download):
            self.manager._run(task,threading.Event())
        self.assertEqual(task['status'],'complete');self.assertEqual(original['installed_version'],'2.0')
        self.assertEqual(original['tracked_version'],'2.0');self.assertEqual(original['name'],'My game name')
        self.assertEqual(original['description'],'Latest description')
        self.assertEqual((old/'Game.exe').read_bytes(),b'old executable fixture')
        self.assertNotEqual(Path(original['executable']).parent,old)
        reloaded=StateStore(self.store.root);self.assertEqual(reloaded.data['library'][0]['installed_version'],'2.0')

    def test_download_archive_without_installation_keeps_old_version(self):
        task,original,old=self.versioned_task(enabled=False)
        with patch('playhub.manager.download_file',side_effect=self.zip_download):
            self.manager._run(task,threading.Event())
        self.assertEqual(task['status'],'complete');self.assertEqual(original['installed_version'],'1.0')
        self.assertEqual(original['executable'],str(old/'Game.exe'))

    def test_missing_configured_launch_does_not_mark_updated(self):
        task,original,old=self.versioned_task();task['install']['executable']='Missing.exe'
        with patch('playhub.manager.download_file',side_effect=self.zip_download):
            self.manager._run(task,threading.Event())
        self.assertEqual(original['installed_version'],'1.0')
        self.assertEqual(original['executable'],str(old/'Game.exe'));self.assertNotIn('installed',task)

    def completed_seven_task(self):
        import py7zr
        task=self.make();folder=Path(task['directory']);folder.mkdir()
        archive=folder/'game.7z'
        with py7zr.SevenZipFile(archive,'w') as package:package.writestr(b'fixture-data','Game.exe')
        result={'path':str(archive),'bytes':archive.stat().st_size,'sha256':hash_file(archive)}
        task.update(status='complete',results=[result],install={'enabled':True},new_files=[str(archive)])
        return task,archive

    def test_completed_seven_extraction_never_requests_network(self):
        task,archive=self.completed_seven_task();before=hash_file(archive)
        with patch('playhub.manager.download_file') as network:
            self.manager._run_extract(task,threading.Event())
            network.assert_not_called()
        self.assertEqual(task['status'],'complete');self.assertEqual(len(task['extracted_packages']),1)
        package=task['extracted_packages'][0]
        self.assertEqual(package['executable'],'');self.assertEqual(hash_file(archive),before)
        self.assertEqual((Path(package['directory'])/'Game.exe').read_bytes(),b'fixture-data')

    def test_changed_completed_archive_is_not_extracted(self):
        task,archive=self.completed_seven_task()
        with archive.open('ab') as file:file.write(b'changed')
        self.manager._run_extract(task,threading.Event())
        self.assertEqual(task['status'],'complete');self.assertNotIn('extracted_packages',task)
        self.assertIn('发生变化',task['message']);self.assertTrue(archive.is_file())

    def test_archive_worker_does_not_overlap_existing_download(self):
        from unittest.mock import Mock
        task,archive=self.completed_seven_task();self.manager.worker=Mock();self.manager.worker.is_alive.return_value=True
        with self.assertRaises(DownloadError):self.manager.extract_completed(task['id'])
        self.manager.worker=None

    def test_legacy_task_without_version_preserves_update_baseline(self):
        from playhub.library_updates import update_status
        task,original,old=self.versioned_task();task['install'].pop('version');task['install'].pop('catalog_game')
        with patch('playhub.manager.download_file',side_effect=self.zip_download):
            self.manager._run(task,threading.Event())
        self.assertEqual(original['installed_version'],'')
        self.assertEqual(original['tracked_version'],'1.0')
        self.assertTrue(update_status(original,[{'id':'test','version':'2.0'}])['available'])

    def test_failed_second_archive_does_not_clear_existing_version(self):
        files=[FileEntry('1','one.zip',4,'https://example.com/one.zip'),FileEntry('2','two.zip',4,'https://example.com/two.zip')]
        task,original,old=self.versioned_task(files=files)
        def download(entry, folder, *args):
            if entry.path=='one.zip':return self.zip_download(entry,folder,*args)
            dest=folder/entry.path
            with zipfile.ZipFile(dest,'w') as archive:archive.writestr('../escape.exe',b'rejected')
            return {'path':str(dest),'bytes':dest.stat().st_size,'sha256':hash_file(dest)}
        with patch('playhub.manager.download_file',side_effect=download):
            self.manager._run(task,threading.Event())
        self.assertEqual(original['installed_version'],'1.0');self.assertNotIn('installed',task)
        self.assertEqual(original['executable'],str(old/'Game.exe'))

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
        result=install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})
        self.assertEqual(result['executable'],'')
        self.assertTrue((Path(result['directory'])/'Other.exe').is_file())
    def test_apk_not_extracted_as_windows_game(self):
        archive=self.root/'test.apk';archive.write_bytes(b'fake')
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})
    def test_case_collision_rejected(self):
        archive=self.archive([('Game.exe',b'a'),('game.exe',b'b')])
        with self.assertRaises(DownloadError):install_zip(archive,self.root,{'game_id':'x','executable':'Game.exe'})

    def test_nested_zip_selects_configured_game_not_first_archive(self):
        first=self.archive([('Other.exe',b'x')])
        folder=self.root/'downloads'/'windows';folder.mkdir(parents=True)
        for name in ('Game.ZIP','opaque.bin','opaque'):
            with self.subTest(name=name):
                nested=folder/name
                with zipfile.ZipFile(nested,'w') as z:z.writestr('Game/Start.exe',b'test fixture')
                picked=install_archives([{'path':str(first)},{'path':str(nested)}],self.root)
                self.assertEqual(picked,[first.resolve(),nested.resolve()])
                installed=install_zip(picked[1],self.root,{'executable':'Game/Start.exe'})
                self.assertEqual(Path(installed['executable']).read_bytes(),b'test fixture')

    def test_fake_zip_and_zip_based_apk_not_installable(self):
        fake=self.root/'fake.zip';fake.write_bytes(b'not an archive')
        apk=self.archive([('Game.exe',b'x')]).rename(self.root/'game.apk')
        self.assertEqual(install_archives([{'path':str(fake)},{'path':str(apk)}],self.root),[])

    def test_two_versions_extract_separately_without_executable(self):
        first=self.archive([('Game.exe',b'one')]);second=self.root/'other.zip'
        with zipfile.ZipFile(second,'w') as z:z.writestr('Other.exe',b'two')
        packages=[install_zip(path,self.root,{}) for path in install_archives([{'path':str(first)},{'path':str(second)}],self.root)]
        self.assertEqual(len(packages),2)
        self.assertNotEqual(packages[0]['directory'],packages[1]['directory'])
        self.assertEqual([p['executable'] for p in packages],['',''])
        self.assertEqual((Path(packages[0]['directory'])/'Game.exe').read_bytes(),b'one')
        self.assertEqual((Path(packages[1]['directory'])/'Other.exe').read_bytes(),b'two')

if __name__=='__main__':unittest.main(verbosity=2)
