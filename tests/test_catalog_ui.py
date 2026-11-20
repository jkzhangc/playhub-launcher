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
    def test_packaged_catalog_has_no_games(self):
        data=json.loads((resource_dir()/'catalog/catalog.json').read_text('utf-8'));self.assertEqual(data['games'],[]);self.assertEqual(data['merchandising']['weekly_ids'],[])
    def test_empty_store_preserves_preview_sections(self):
        self.window.show_page('store');texts=[x.text() for x in self.window.body.findChildren(QLabel)];self.assertIn('本周推荐榜',texts);self.assertIn('等待新世界上架',texts);self.assertIsNotNone(self.window.body.findChild(QPushButton,'Filter'))
    def test_weekly_order_from_admin_config(self):
        first=self.sample();second={**first,'id':'second','name':'第二款'};self.window.catalog=[first,second];self.window.catalog_meta={'merchandising':{'weekly_ids':['second','ui-test'],'hero':{}}};self.assertEqual(self.window.recommended_games()[0]['id'],'second')
    def test_hero_strings_not_individually_framed(self):
        self.window.catalog_meta={'merchandising':{'weekly_ids':[],'hero':{'title':'管理员设置标题','subtitle':'管理员设置说明'}}};hero=self.window.hero();labels=hero.findChildren(QLabel);target=next(x for x in labels if x.text()=='管理员设置标题');self.assertIn('border:none',target.styleSheet())
    def test_detail_has_real_tabs_no_fake_reviews(self):
        self.window.catalog=[self.sample()];self.window.detail(self.sample());dialog=self.window.dialogs[-1];tabs=dialog.findChild(QTabWidget,'GameDetailTabs');self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],['介绍','系统需求','评论与评分']);all_text=' '.join(x.text() for x in dialog.findChildren(QLabel));self.assertIn('尚未上线',all_text);self.assertNotIn('4.8',all_text)
    def test_duplicate_ids_rejected(self):
        with self.assertRaises(Exception):Launcher.validate_catalog({'games':[self.sample(),self.sample()]})
    def test_source_and_install_configuration_passed(self):
        game={**self.sample(),'executable':'MyGame/Game.exe','auto_install':True}
        self.window.catalog=[game]
        with patch.object(self.window,'resolve') as resolve:
            self.window.download_game(game);self.assertEqual(resolve.call_args.kwargs['install']['executable'],'MyGame/Game.exe');self.assertTrue(resolve.call_args.kwargs['install']['enabled'])

if __name__=='__main__':unittest.main(verbosity=2)
