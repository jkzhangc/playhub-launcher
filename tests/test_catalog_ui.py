import copy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QPushButton,QLabel,QTabWidget
from playhub.core import StateStore,resource_dir
from playhub.ui import Launcher

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parent.parent
class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.state=StateStore(ROOT/'validation'/('catalog-ui-'+uuid.uuid4().hex[:8]));self.state.data['name']='测试玩家';self.window=Launcher(self.state)
    def tearDown(self):
        for d in list(self.window.dialogs):d.close()
        self.window.manager.close();self.window.cloud.close();self.window.close();APP.processEvents()
    def sample(self):
        return {'id':'ui-test','name':'界面回归专用','category':'冒险探索','developer':'本地测试','version':'1.0','source':'https://example.com/game.zip','source_type':'direct','platform':'windows','description':'测试资料，不写入发行包。','summary':'本地UI测试'}
    @unittest.skipUnless((ROOT/'private/studio.py').is_file(),'public repository retains the administrator-maintained live catalog')
    def test_packaged_catalog_has_no_games(self):
        data=json.loads((resource_dir()/'catalog/catalog.json').read_text('utf-8'));self.assertEqual(data['games'],[]);self.assertEqual(data['merchandising']['weekly_ids'],[])
    def test_empty_store_preserves_preview_sections(self):
        self.window.catalog=[];self.window.catalog_meta={'merchandising':{'weekly_ids':[],'hero':{}}};self.window.show_page('store');texts=[x.text() for x in self.window.body.findChildren(QLabel)];self.assertIn('本周推荐榜',texts);self.assertIn('等待新世界上架',texts);self.assertIsNotNone(self.window.body.findChild(QPushButton,'Filter'))
    def test_weekly_order_from_admin_config(self):
        first=self.sample();second={**first,'id':'second','name':'第二款'};self.window.catalog=[first,second];self.window.catalog_meta={'merchandising':{'weekly_ids':['second','ui-test'],'hero':{}}};self.assertEqual(self.window.recommended_games()[0]['id'],'second')
    def test_hero_strings_not_individually_framed(self):
        self.window.catalog_meta={'merchandising':{'weekly_ids':[],'hero':{'title':'管理员设置标题','subtitle':'管理员设置说明'}}};hero=self.window.hero();labels=hero.findChildren(QLabel);target=next(x for x in labels if x.text()=='管理员设置标题');self.assertIn('border:none',target.styleSheet())
    def test_detail_has_real_tabs_no_fake_reviews(self):
        self.window.catalog=[self.sample()];self.window.detail(self.sample());dialog=self.window.dialogs[-1];tabs=dialog.findChild(QTabWidget,'GameDetailTabs');self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],['介绍','系统需求','更新日志','作者的话','评论与评分']);all_text=' '.join(x.text() for x in dialog.findChildren(QLabel));self.assertIn('尚未上线',all_text);self.assertNotIn('4.8',all_text)
    def test_duplicate_ids_rejected(self):
        with self.assertRaises(Exception):Launcher.validate_catalog({'games':[self.sample(),self.sample()]})
    def test_source_and_install_configuration_passed(self):
        game={**self.sample(),'executable':'MyGame/Game.exe','auto_install':True}
        self.window.catalog=[game]
        with patch.object(self.window,'resolve') as resolve:
            self.window.download_game(game);self.assertEqual(resolve.call_args.kwargs['install']['executable'],'MyGame/Game.exe');self.assertTrue(resolve.call_args.kwargs['install']['enabled'])

    def test_magnet_wait_and_file_selection_stay_above_details(self):
        self.window.detail(self.sample());detail=self.window.dialogs[-1]
        with patch.object(self.window,'job') as job, patch.object(self.window,'choose_files') as choose:
            magnet='magnet:?xt=urn:btih:'+'a'*40
            self.window.resolve(magnet,'torrent')
            waiting=self.window.magnet_wait
            self.assertIs(waiting.parent(),detail);self.assertTrue(waiting.isVisible())
            self.window.resolve(magnet,'torrent');job.assert_called_once()
            job.call_args.args[1]((['fixture'],'cached.torrent'))
            self.assertIsNone(self.window.magnet_wait)
            self.assertIs(choose.call_args.kwargs['parent'],detail)

    def test_cancel_magnet_never_opens_file_selector(self):
        with patch.object(self.window,'job') as job, patch.object(self.window,'choose_files') as choose:
            self.window.resolve_magnet('magnet:?xt=urn:btih:'+'a'*40,'',None)
            self.window.magnet_wait.reject()
            self.assertTrue(self.window.stop_metadata.is_set())
            job.call_args.args[1]((['fixture'],'cached.torrent'))
            choose.assert_not_called()

    def test_page_motion_rapid_switch_and_disabled(self):
        from playhub.ui import PageReveal
        self.window.show();APP.processEvents()
        with patch.object(self.window,'motion_enabled',return_value=True):
            self.window.show_page('store');viewport=self.window.scroll.viewport()
            self.assertEqual(sum(w.isVisible() for w in viewport.findChildren(PageReveal)),1)
            self.window.show_page('library')
            self.assertEqual(sum(w.isVisible() for w in viewport.findChildren(PageReveal)),1)
        self.window.set_interface_motion(False)
        self.window.show_page('downloads')
        self.assertFalse(any(w.isVisible() for w in viewport.findChildren(PageReveal)))
        self.assertFalse(self.window.motion_enabled())

    def test_motion_snapshot_contains_new_page_and_frames_change(self):
        from playhub.ui import PageReveal
        from PySide6.QtCore import Qt
        self.window.show();APP.processEvents()
        def marked_page(layout):
            marker=QLabel('MOTION CONTENT MARKER')
            marker.setObjectName('MotionMarker')
            marker.setFixedSize(280,120)
            marker.setStyleSheet('background-color:#e02838;color:white;')
            layout.addWidget(marker)
        with patch.object(self.window,'store_page',side_effect=marked_page),patch.object(self.window,'motion_enabled',return_value=True):
            self.window.show_page('store')
            marker=self.window.body.findChild(QLabel,'MotionMarker')
            self.assertTrue(marker.isVisible(),'new page children must be visible before snapshot')
            reveal=next(w for w in self.window.scroll.viewport().findChildren(PageReveal) if w.isVisible())
            image=reveal.snapshot.toImage()
            red=sum(image.pixelColor(x,y).red()>180 and image.pixelColor(x,y).green()<90 for y in range(0,image.height(),4) for x in range(0,image.width(),4))
            self.assertGreater(red,100,'transition must contain real page content, not background')
            reveal.animation.pause()
            frames=[]
            for value in (0.0,0.5,1.0):
                reveal.frame(value);frames.append(reveal.grab().toImage())
            self.assertNotEqual(frames[0],frames[1]);self.assertNotEqual(frames[1],frames[2])
            self.assertTrue(reveal.testAttribute(Qt.WA_TransparentForMouseEvents))
            reveal.dismiss();self.assertTrue(marker.isVisible())

    def test_mediafire_detect_and_details_use_parsed_session(self):
        from playhub.core import FileEntry
        url='https://www.mediafire.com/file/abc/game.zip/file'
        self.assertEqual(self.window.detect(url),'mediafire')
        self.assertEqual(self.window.detect('https://download123.mediafire.com/key/game.zip'),'mediafire')
        self.assertEqual(self.window.detect('https://mediafire.com.evil.test/file/x'),'direct')
        self.window.detail(self.sample());detail=self.window.dialogs[-1]
        session=object();entry=FileEntry('0','game.zip',123,'https://download123.mediafire.com/key/game.zip')
        with patch.object(self.window,'job') as job,patch.object(self.window,'choose_files') as choose,patch('playhub.ui.resolve_mediafire',return_value=(entry,session)) as resolve:
            self.window.resolve(url,'auto',title='MediaFire game',install={'enabled':True})
            work,done,failed=job.call_args.args
            done(work());resolve.assert_called_once_with(url)
            self.assertEqual(choose.call_args.args[0],[entry])
            self.assertIs(choose.call_args.kwargs['web'],session)
            self.assertIs(choose.call_args.kwargs['parent'],detail)
            self.assertTrue(choose.call_args.kwargs['install']['enabled'])

if __name__=='__main__':unittest.main(verbosity=2)
