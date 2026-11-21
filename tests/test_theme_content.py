import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import QCoreApplication,QEvent,QSettings
from PySide6.QtWidgets import QApplication,QPushButton,QComboBox,QLabel,QTabWidget
from playhub.core import StateStore
from playhub.theme import convert_color,themed_stylesheet
from playhub.ui import Launcher,PageReveal,STYLE

APP=QApplication.instance() or QApplication([])


def game():
    return {'id':'theme-test','name':'Theme fixture','version':'1.0','source':'https://example.com/game.zip',
            'source_type':'direct','category':'Test','developer':'Creator','changelog':'1.0: 修复问题\n新增内容',
            'author_notes':'感谢游玩，这是作者的话。','executable':''}


class LauncherAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=StateStore(Path(self.tmp.name)/'state');self.state.data['name']='Tester'
        self.fake=patch('playhub.manager.TorrentEngine',return_value=Mock());self.fake.start()
        self.window=Launcher(self.state);self.window.show();APP.processEvents()
        self.window.catalog=[game()];self.state.data['library']=[dict(game())]

    def tearDown(self):
        for dialog in list(self.window.dialogs):dialog.close()
        self.window.manager.close();self.window.cloud.close();self.window.close();APP.processEvents()
        self.fake.stop();self.tmp.cleanup()

    def test_default_blue_can_be_changed_and_persisted_without_changing_alert_red(self):
        self.assertEqual(self.window.property('themeColor'),'blue')
        self.assertEqual(convert_color('#b82439','blue').name(),'#b82439')
        self.assertGreater(convert_color('#327d67','blue').blue(),convert_color('#327d67','blue').green())
        self.window.show_page('settings');choice=self.window.body.findChild(QComboBox,'ThemeColor')
        choice.setCurrentIndex(choice.findData('green'))
        self.assertEqual(self.window.property('themeColor'),'green')
        self.assertEqual(StateStore(self.state.root).data['theme_color'],'green')
        choice.setCurrentIndex(choice.findData('blue'))
        self.assertEqual(self.window.property('themeColor'),'blue')

    def test_uninstalled_button_downloads_and_installed_button_launches(self):
        self.window.show_page('library')
        primary=next(b for b in self.window.body.findChildren(QPushButton) if b.property('libraryPrimaryAction'))
        self.assertEqual(primary.text(),'点击下载');self.assertTrue(primary.isEnabled())
        with patch.object(self.window,'download_game') as download:primary.click();self.assertEqual(download.call_args.args[0]['id'],'theme-test')
        exe=Path(self.tmp.name)/'Game.exe';exe.write_bytes(b'not runnable fixture');self.state.data['library'][0]['executable']=str(exe)
        self.window.show_page('library')
        primary=next(b for b in self.window.body.findChildren(QPushButton) if b.property('libraryPrimaryAction'))
        self.assertEqual(primary.text(),'开始游玩')
        with patch.object(self.window,'launch_game') as launch:primary.click();launch.assert_called_once()

    def test_details_show_author_words_and_changelog_plainly(self):
        self.window.detail(game());detail=self.window.dialogs[-1];tabs=detail.findChild(QTabWidget,'GameDetailTabs')
        titles=[tabs.tabText(i) for i in range(tabs.count())]
        self.assertIn('更新日志',titles);self.assertIn('作者的话',titles)
        self.assertIn(game()['author_notes'],[label.text() for label in detail.findChildren(QLabel)])

    def test_sort_rebuild_is_deferred_and_repeated_native_signals_survive(self):
        self.window.catalog=[{**game(),'id':str(i),'name':'Game '+str(20-i),'developer':str(i)} for i in range(20)]
        self.window.show_page('store');APP.processEvents()
        for index in (1,2,0)*20:
            combo=self.window.body.findChild(QComboBox,'StoreSort');old_body=self.window.body
            combo.setCurrentIndex(index)
            self.assertIs(self.window.body,old_body,'must not delete the sender inside its native signal')
            APP.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            self.assertEqual(self.window.store_sort,('recommended','name','developer')[index])
            self.assertIsNot(self.window.body,old_body)
        self.assertFalse(self.window._view_rebuild_pending)


@unittest.skipUnless((Path(__file__).resolve().parent.parent/'private/studio.py').is_file(),'Studio source is distributed separately')
class StudioAppearanceTests(unittest.TestCase):
    def test_studio_green_animated_tabs_and_content_roundtrip(self):
        from private.studio import Studio
        with tempfile.TemporaryDirectory() as temp:
            prefs=QSettings(str(Path(temp)/'appearance.ini'),QSettings.IniFormat)
            with patch('private.studio.QSettings',return_value=prefs):studio=Studio()
            try:
                studio.show();studio.locked(False);APP.processEvents()
                self.assertEqual(studio.property('themeColor'),'green')
                studio.new_game()
                for key in ('id','name','version'):studio.fields[key].setText(game()[key])
                studio.sources.item(0,1).setText(game()['source'])
                studio.changelog.setPlainText(game()['changelog']);studio.author_notes.setPlainText(game()['author_notes'])
                with patch.object(studio,'failed') as failed:studio.save_game();failed.assert_not_called()
                saved=studio.catalog['games'][0]
                self.assertEqual(saved['author_notes'],game()['author_notes']);self.assertEqual(saved['changelog'],game()['changelog'])
                self.assertEqual(studio.author_notes.toPlainText(),game()['author_notes'])
                for overlay in studio.findChildren(PageReveal):overlay.dismiss()
                with patch('private.studio.system_motion_enabled',return_value=True):
                    studio.tabs.setCurrentIndex(1);APP.processEvents()
                    overlays=[w for w in studio.findChildren(PageReveal) if w.isVisible()]
                    self.assertTrue(overlays)
                studio.theme_choice.setCurrentIndex(studio.theme_choice.findData('blue'))
                self.assertEqual(studio.property('themeColor'),'blue');self.assertEqual(prefs.value('theme_color'),'blue')
                studio.motion_choice.setChecked(False);self.assertFalse(any(w.isVisible() for w in studio.findChildren(PageReveal)))
            finally:studio.close();APP.processEvents()


if __name__=='__main__':unittest.main(verbosity=2)
