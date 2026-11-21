import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QFrame, QTabWidget
from playhub.core import StateStore
from playhub.library_updates import latest_details, compare_versions, update_status
from playhub.ui import Launcher

APP=QApplication.instance() or QApplication([])


def fixture(version='1.0'):
    return {'id':'library-regression','name':'Catalog game','version':version,
            'summary':'New summary '+version,'description':'Current description '+version,
            'developer':'Test developer','platform':'windows','category':'Adventure',
            'source':'https://example.com/new-'+version+'.zip','source_type':'direct',
            'sources':[{'type':'direct','label':'New source '+version,'url':'https://example.com/new-'+version+'.zip'}],
            'screenshots':[],'system_requirements':'Current requirements','auto_install':True,'executable':'Game.exe'}


class VersionTests(unittest.TestCase):
    def test_natural_order_and_no_downgrade(self):
        for remote,local,expected in [('0.44.10','0.44.9',1),('v1.0.0','1',0),('1.0-beta2','1.0-beta1',1),
                ('1.0','1.0-rc1',1),('1.0-alpha','1.0-beta',-1),('2.0','10.0',-1),
                ('1.0+build2','1.0+build1',0),('winter','summer',None)]:
            with self.subTest(remote=remote,local=local):self.assertEqual(compare_versions(remote,local),expected)

    def test_latest_details_do_not_mutate_local_or_retain_stale_sources(self):
        original={**fixture(),'name':'My custom game','executable':'C:/old/Game.exe','description':'Old description'}
        before=copy.deepcopy(original);latest=fixture('2.0');latest['screenshots']=['https://example.com/new.png']
        resolved=latest_details(original,[latest])
        self.assertEqual(resolved,latest);self.assertEqual(original,before)
        resolved['sources'][0]['label']='edited';self.assertNotEqual(resolved['sources'],latest['sources'])

    def test_installed_version_not_catalog_snapshot_determines_update(self):
        local={**fixture('9.0'),'installed_version':'1.0','tracked_version':'1.5'}
        status=update_status(local,[fixture('2.0')]);self.assertTrue(status['available']);self.assertEqual(status['current'],'1.0')

    def test_missing_version_local_import_and_unlisted_never_claim_latest(self):
        self.assertEqual(update_status({'id':'library-regression','source':'x'},[fixture('2.0')])['code'],'unknown')
        self.assertFalse(update_status({'id':'library-regression','local_only':True,'version':'1.0'},[fixture('2.0')])['available'])
        self.assertEqual(update_status(fixture(),[])['code'],'unlisted')
        self.assertEqual(update_status(fixture(),[{**fixture(),'version':''}])['code'],'unversioned')
        self.assertFalse(update_status(fixture('release-a'),[fixture('release-b')])['available'])


class LibraryUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=StateStore(Path(self.tmp.name)/'state');self.state.data['name']='Test player'
        self.p2p=patch('playhub.manager.TorrentEngine',return_value=Mock());self.p2p.start()
        self.window=Launcher(self.state);self.window.set_interface_motion(False)
        self.original={**fixture('1.0'),'name':'My local name','custom_name':'My local name',
                       'executable':str(Path(self.tmp.name)/'OldGame.exe'),'installed_version':'1.0'}
        Path(self.original['executable']).write_bytes(b'not executable test fixture')
        self.state.data['library']=[self.original];self.window.catalog=[fixture('2.0')]
        self.window.show();APP.processEvents()

    def tearDown(self):
        if hasattr(self.window,'library_update_timer'):self.window.library_update_timer.stop()
        self.window.library_monitor_started=False
        for dialog in list(self.window.dialogs):dialog.close()
        self.state.data['tasks']=[]
        self.window.close();APP.processEvents();self.p2p.stop();self.tmp.cleanup()

    def test_detail_from_library_and_store_share_latest_contents_and_sources(self):
        before=copy.deepcopy(self.original)
        self.window.show_page('library')
        launch=next(b for b in self.window.body.findChildren(QPushButton) if b.text()=='开始游玩')
        self.assertTrue(launch.isEnabled())
        detail_button=next(b for b in self.window.body.findChildren(QPushButton) if b.text()=='详情');detail_button.click()
        detail=self.window.dialogs[-1]
        texts=[w.text() for w in detail.findChildren(QLabel)]
        self.assertIn('Current description 2.0',texts);self.assertNotIn('Current description 1.0',texts)
        self.assertEqual(detail.property('catalogVersion'),'2.0')
        with patch.object(self.window,'resolve') as resolve:
            detail.findChild(QPushButton,'DownloadGameVersion').click()
            self.assertEqual(resolve.call_args.args[0],'https://example.com/new-2.0.zip')
            self.assertEqual(resolve.call_args.kwargs['install']['version'],'2.0')
        self.assertEqual(self.original,before)

    def test_red_dot_highlight_and_details_never_clear_update(self):
        self.window.show_page('library')
        self.assertTrue(self.window.library_update_dot.isVisible())
        cards=[w for w in self.window.body.findChildren(QFrame) if w.objectName()=='Panel' and w.property('gameId')==self.original['id']]
        self.assertEqual(len(cards),1);self.assertTrue(cards[0].property('updateAvailable'))
        self.assertTrue(any(w.objectName()=='GameUpdateBadge' for w in cards[0].findChildren(QLabel)))
        self.window.detail(self.original);self.window.dialogs[-1].accept();APP.processEvents()
        self.assertTrue(self.window.library_update_dot.isVisible())
        self.original['installed_version']='2.0';self.window.queue_changed()
        self.assertTrue(self.window.library_update_dot.isHidden())
        self.assertFalse(any(w.property('updateAvailable') for w in self.window.body.findChildren(QFrame)))

    def test_catalog_refresh_keeps_local_version_and_refreshes_open_dialog_in_place(self):
        self.window.show_page('library');self.window.detail(self.original);dialog=self.window.dialogs[-1]
        dialog.findChild(QTabWidget,'GameDetailTabs').setCurrentIndex(1)
        before=copy.deepcopy(self.original)
        with patch.object(self.window,'job') as job:
            self.window.refresh_catalog(quiet=True)
            self.window.refresh_catalog(quiet=True);job.assert_called_once()
            job.call_args.args[1]({'games':[fixture('3.0')],'merchandising':{}})
        self.assertEqual(len(self.window.dialogs),1);self.assertIs(self.window.dialogs[0],dialog)
        self.assertEqual(dialog.property('catalogVersion'),'3.0')
        self.assertEqual(dialog.findChild(QTabWidget,'GameDetailTabs').currentIndex(),1)
        self.assertEqual(self.original,before);self.assertTrue(self.window.library_update_dot.isVisible())

    def test_failed_check_keeps_cached_update_and_red_dot(self):
        self.window.show_page('library');self.window.detail(self.original)
        with patch.object(self.window,'job') as job:
            self.window.check_library_updates()
            job.call_args.args[2]('offline fixture')
        self.assertEqual(self.window.catalog[0]['version'],'2.0')
        self.assertTrue(self.window.library_update_dot.isVisible())
        self.assertIn('缓存',self.window.library_check_message);self.assertIn('offline fixture',self.window.library_check_message)
        self.assertFalse(self.window.catalog_loading)

    def test_update_filter_and_unknown_versions(self):
        self.state.data['library'].append({'id':'local-only','name':'Local EXE','local_only':True,'source':''})
        self.window.library_filter='有更新';self.window.show_page('library')
        self.assertEqual(len(self.window.body.findChildren(QPushButton,'ViewGameUpdate')),1)
        self.original.pop('installed_version');self.original.pop('version');self.original.pop('tracked_version',None)
        self.window.show_page('library')
        self.assertTrue(self.window.library_update_dot.isHidden())
        self.assertEqual(len(self.window.body.findChildren(QPushButton,'ViewGameUpdate')),0)

    def test_new_collection_baseline_is_not_an_installed_version(self):
        self.state.data['library']=[];self.window.add_library(fixture('2.0'))
        game=self.state.data['library'][0]
        self.assertEqual(game['tracked_version'],'2.0');self.assertNotIn('installed_version',game)
        self.window.catalog=[fixture('2.1')];self.window.refresh_library_indicators()
        self.assertTrue(self.window.library_update_dot.isVisible())

    def test_monitor_starts_once_and_checks_every_fifteen_minutes(self):
        with patch('playhub.ui.QTimer.singleShot') as shot,patch.object(self.window,'check_library_updates') as check:
            self.window.start_library_monitor();self.window.start_library_monitor()
            self.assertEqual(shot.call_count,1);self.assertEqual(self.window.library_update_timer.interval(),900000)
            shot.call_args.args[1]();check.assert_called_once_with(quiet=True)

    def test_manual_version_registration_requires_confirmation(self):
        from PySide6.QtWidgets import QMessageBox
        self.window.show_page('library')
        with patch('playhub.ui.QInputDialog.getText',return_value=('2.0',True)),patch('playhub.ui.QMessageBox.question',return_value=QMessageBox.No):
            self.window.register_library_version(self.original)
        self.assertEqual(self.original['installed_version'],'1.0');self.assertTrue(self.window.library_update_dot.isVisible())
        with patch('playhub.ui.QInputDialog.getText',return_value=('2.0',True)),patch('playhub.ui.QMessageBox.question',return_value=QMessageBox.Yes):
            self.window.register_library_version(self.original)
        self.assertEqual(self.original['installed_version'],'2.0');self.assertTrue(self.window.library_update_dot.isHidden())


if __name__=='__main__':unittest.main(verbosity=2)
