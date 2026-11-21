import bz2
import gzip
import io
import lzma
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

import py7zr
from playhub.core import DownloadError,hash_file
from playhub.install import install_archive,install_archives
from playhub.archive_formats import archive_kind


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.download=self.root/'download';self.download.mkdir()

    def tearDown(self):self.temp.cleanup()

    def seven(self,members=None,password=None):
        path=self.download/'游戏包.7z'
        with py7zr.SevenZipFile(path,'w',password=password) as package:
            for name,data in (members or [('Game/Game.exe',b'not executable fixture'),('Game/data.bin',b'game data')]):
                package.writestr(data,name)
        return path

    def tar(self,suffix='.tar',mode='w',bad=None):
        path=self.download/('game'+suffix)
        with tarfile.open(path,mode) as package:
            for name,data in [('Game/Game.exe',b'not executable fixture'),('Game/data.bin',b'data')]:
                member=tarfile.TarInfo(name);member.size=len(data);package.addfile(member,io.BytesIO(data))
            if bad is not None:package.addfile(bad,io.BytesIO(b'x') if bad.isreg() else None)
        return path

    def test_seven_real_files_exact_launch_and_no_source_change(self):
        path=self.seven();before=hash_file(path)
        result=install_archive(path,self.download,{'game_id':'game','executable':'Game/Game.exe'})
        self.assertEqual(Path(result['executable']).read_bytes(),b'not executable fixture')
        self.assertEqual(len(result['files']),2);self.assertEqual(hash_file(path),before)
        self.assertEqual(archive_kind(path),'7z')

    def test_seven_missing_launch_does_not_guess_and_old_directory_untouched(self):
        path=self.seven();first=install_archive(path,self.download,{'game_id':'game'})
        second=install_archive(path,self.download,{'game_id':'game','executable':'Missing.exe'})
        self.assertEqual(first['executable'],'');self.assertEqual(second['executable'],'')
        self.assertNotEqual(first['directory'],second['directory'])
        self.assertTrue((Path(first['directory'])/'Game/Game.exe').is_file())

    def test_seven_rejects_password_duplicate_case_and_bad_names(self):
        for members in ([('Game.exe',b'a'),('game.exe',b'b')],[('CON.txt',b'x')],[('a/Game.exe',b'a'),('A/game.exe',b'b')]):
            with self.subTest(members=members):
                path=self.seven(members)
                with self.assertRaises(DownloadError):install_archive(path,self.download,{})
        path=self.seven(password='fixture-password')
        with self.assertRaisesRegex(DownloadError,'加密'):install_archive(path,self.download,{})

    def test_tar_variants_and_unicode(self):
        for suffix,mode in (('.tar','w'),('.tar.gz','w:gz'),('.tgz','w:gz'),('.tar.bz2','w:bz2'),('.tar.xz','w:xz')):
            with self.subTest(suffix=suffix):
                result=install_archive(self.tar(suffix,mode),self.download,{'executable':'Game/Game.exe'})
                self.assertEqual(len(result['files']),2);self.assertTrue(Path(result['executable']).is_file())

    def test_tar_rejects_links_absolute_paths_and_traversal(self):
        for name,kind in (('../escape.exe',tarfile.REGTYPE),('/absolute.exe',tarfile.REGTYPE),('symlink',tarfile.SYMTYPE),('hardlink',tarfile.LNKTYPE),('device',tarfile.CHRTYPE)):
            member=tarfile.TarInfo(name);member.type=kind;member.size=1 if kind==tarfile.REGTYPE else 0;member.linkname='Game/Game.exe'
            with self.subTest(name=name):
                with self.assertRaises(DownloadError):install_archive(self.tar(bad=member),self.download,{})
        self.assertFalse((self.root/'escape.exe').exists())

    def test_single_file_compression(self):
        for suffix,encode in (('.gz',gzip.compress),('.bz2',bz2.compress),('.xz',lzma.compress)):
            path=self.download/('Game.exe'+suffix);path.write_bytes(encode(b'not executable fixture'))
            result=install_archive(path,self.download,{'executable':'Game.exe'})
            self.assertEqual(Path(result['executable']).read_bytes(),b'not executable fixture')

    def test_size_file_limit_disk_space_and_cancel(self):
        path=self.seven()
        with patch('playhub.archive_formats.MAX_UNPACKED',5):
            with self.assertRaises(DownloadError):install_archive(path,self.download,{})
        with patch('playhub.archive_formats.MAX_FILES',1):
            with self.assertRaises(DownloadError):install_archive(path,self.download,{})
        stop=threading.Event();stop.set()
        with self.assertRaisesRegex(DownloadError,'取消'):install_archive(path,self.download,{},stop)
        usage=type('Usage',(),{'free':0})()
        with patch('playhub.archive_formats.shutil.disk_usage',return_value=usage):
            with self.assertRaisesRegex(DownloadError,'空间'):install_archive(path,self.download,{})

    def test_apk_rar_selfextract_and_unsupported_files_are_not_candidates(self):
        seven=self.seven();raw=seven.read_bytes()
        for name in ('android.apk','installer.exe','lib.jar','archive.rar','archive.7z.001'):
            path=self.download/name;path.write_bytes(raw)
            self.assertIsNone(archive_kind(path))
            with self.assertRaises(DownloadError):install_archive(path,self.download,{})
        opaque=self.download/'opaque.bin';opaque.write_bytes(raw)
        self.assertEqual(archive_kind(opaque),'7z')
        self.assertEqual(install_archives([{'path':str(seven)},{'path':str(opaque)}],self.download),[seven.resolve(),opaque.resolve()])

    def test_external_result_path_rejected(self):
        path=self.root/'outside.7z';path.write_bytes(b'x')
        with self.assertRaises(DownloadError):install_archives([{'path':str(path)}],self.download)


if __name__=='__main__':unittest.main(verbosity=2)
