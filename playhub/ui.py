from __future__ import annotations
import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap, QPainter, QColor, QPolygonF, QIcon, QLinearGradient
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QDialog, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QComboBox, QCheckBox, QDoubleSpinBox,
    QProgressBar, QSpinBox, QInputDialog, QTabWidget, QTextEdit, QStackedWidget, QLayout)
from .core import VERSION, DownloadError, FileEntry, StateStore, human_bytes, resource_dir, safe_target
from .sources import WebClient, NutstoreShare, direct_entry, manifest_entries
from .lanzou import is_lanzou_host
from .manager import DownloadManager
from .cloud_login import CloudBridge, PROVIDERS

STYLE = '''
QWidget {font-family:'Segoe UI','Microsoft YaHei';font-size:12px;color:#293b53;}
QMainWindow,QWidget#Main {background:#f2f4f7;}
QWidget#Sidebar {background:white;border-right:1px solid #e6ebf1;}
QLabel#Title {font-size:28px;font-weight:600;}
QLabel#Eyebrow {font-size:10px;color:#93a1b3;letter-spacing:2px;}
QLabel#Muted {color:#8798ac;}
QLabel#Brand {font-size:23px;font-weight:700;color:#294f66;}
QFrame#Panel {background:white;border:1px solid #e6ebf2;border-radius:10px;}
QLabel#Notice {background:#eaf2fd;border:1px solid #dce7f6;color:#52769c;padding:13px;border-radius:7px;}
QPushButton {background:white;border:1px solid #dee6f0;border-radius:6px;padding:10px 17px;min-height:18px;}
QPushButton:hover {background:#edf4fd;border-color:#b8cee7;}
QPushButton:pressed {background:#dceafa;}
QPushButton:disabled {color:#a9b5c4;background:#f6f8fb;}
QPushButton#Primary {background:#497fc1;border:1px solid #497fc1;color:white;}
QPushButton#Primary:hover {background:#3f72af;}
QPushButton#Nav {border:0;text-align:left;color:#8090a5;background:transparent;padding:13px 17px;}
QPushButton#Nav:checked {background:#eaf2fd;color:#497fc1;font-weight:600;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit {background:#fbfcfe;border:1px solid #dfe7f0;border-radius:6px;padding:9px;min-height:20px;selection-background-color:#8eb4e3;}
QLineEdit:focus,QComboBox:focus,QTextEdit:focus {border:1px solid #7da9db;}
QTableWidget {background:white;border:1px solid #e2e9f1;border-radius:6px;gridline-color:#eef2f7;selection-background-color:#edf4fd;}
QHeaderView::section {background:#f6f8fb;border:0;border-bottom:1px solid #e5ebf3;padding:10px;color:#8799ae;}
QTableWidget::item {padding:8px;}
QProgressBar {background:#e9eff5;border:0;border-radius:3px;height:6px;text-align:center;color:#55779a;}
QProgressBar::chunk {background:#88a9cf;border-radius:3px;}
QScrollArea {border:0;background:transparent;}
QTabWidget::pane {border:1px solid #e4eaf2;background:white;border-radius:6px;}
QTabBar::tab {padding:12px 20px;color:#8497af;}
QTabBar::tab:selected {color:#497fc1;border-bottom:2px solid #497fc1;}
QDialog {background:#f6f8fb;}
QCheckBox {spacing:9px;}
QCheckBox::indicator {width:17px;height:17px;}
QWidget {font-size:13px;color:#294963;}
QMainWindow,QWidget#Main,QWidget#PageBody {background:#f1f9fd;}
QWidget#Sidebar {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e7f6ff,stop:1 #f7fcff);border-right:1px solid #c9e4f3;}
QLabel#Title {font-size:27px;color:#246387;font-weight:600;}
QLabel#Muted {color:#728fa5;}
QLabel#Brand {color:#197daa;}
QLabel#Eyebrow {color:#7ba5bb;}
QFrame#Panel {background:#fff;border:1px solid #cfe5f1;border-radius:9px;}
QLabel#Notice {background:#e7f6fe;border-color:#c9e6f8;color:#4a84a5;}
QPushButton {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fff,stop:1 #edf8ff);border-color:#bcddec;color:#3984aa;min-height:19px;}
QPushButton:hover {background:#e1f4ff;border-color:#70bde4;}
QPushButton#Primary {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4dc5ee,stop:1 #2098d4);border-color:#249bd3;color:#fff;}
QPushButton#Primary:hover {background:#32afe3;}
QPushButton#Nav {border:0;background:transparent;color:#698da5;padding:14px 17px;font-size:13px;}
QPushButton#Nav:checked {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #66c7ef,stop:1 #319ee0);color:#fff;border:1px solid #2c9cda;}
QHeaderView::section {background:#eaf6fd;color:#6892aa;border-bottom:1px solid #c6e3f1;}
QProgressBar {background:#e4f3fb;border-radius:4px;}
QProgressBar::chunk {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3da7df,stop:1 #68d0ef);border-radius:4px;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:#fff;border-color:#c7e1ee;}
QScrollBar:vertical {background:#eef7fc;width:10px;border:0;}
QScrollBar::handle:vertical {background:#b6d9eb;border-radius:5px;min-height:35px;}
QWidget#PageBody {background:#f1f7fb;}
QLabel#SectionTitle {font-size:15px;font-weight:600;color:#315d78;}
QFrame#Panel {background:white;border:1px solid #dce9f2;border-radius:11px;}
QFrame#Panel QLabel {background:transparent;border:0;}
QFrame#Panel QLabel#Notice {background:#edf7fd;border:1px solid #d4e8f5;border-radius:7px;}
QPushButton#Filter {padding:7px 10px;background:transparent;border:0;color:#7794aa;}
QPushButton#Filter:hover {background:#e3f1fb;}
QPushButton#Filter:checked {background:#dceffa;color:#237eb6;font-weight:600;}
QTabWidget::pane {background:white;border:1px solid #dce9f2;border-radius:10px;}
QTabBar::tab {background:transparent;padding:13px 22px;}
QTabBar::tab:selected {color:#238ac4;border-bottom:2px solid #31a5df;}
QLabel#Title {font-size:27px;font-weight:600;}
QPushButton:focus {border:1px solid #238dc6;}
QScrollArea > QWidget > QWidget {background:transparent;}
'''

def label(text, name='', wrap=True):
    w=QLabel(text);w.setTextFormat(Qt.PlainText);w.setWordWrap(wrap)
    if name:w.setObjectName(name)
    return w

def button(text, callback, primary=False):
    w=QPushButton(text)
    if primary:w.setObjectName('Primary')
    w.clicked.connect(callback)
    return w

def panel():
    w=QFrame();w.setObjectName('Panel');lay=QVBoxLayout(w);lay.setContentsMargins(24,23,24,23);lay.setSpacing(14);return w,lay

def row(*widgets):
    lay=QHBoxLayout();lay.setSpacing(10)
    for w in widgets:
        if isinstance(w,QWidget):lay.addWidget(w)
        elif isinstance(w,int):lay.addStretch(w)
        else:lay.addLayout(w)
    return lay

class WorkSignals(QObject):
    done=Signal(object)
    error=Signal(str)

class Work(QRunnable):
    def __init__(self,func):super().__init__();self.func=func;self.signals=WorkSignals()
    def run(self):
        try:self.signals.done.emit(self.func())
        except Exception as exc:self.signals.error.emit(str(exc))

class Artwork(QFrame):
    def __init__(self, text='', height=150, parent=None):
        from PySide6.QtWidgets import QSizePolicy
        super().__init__(parent);self.pixmap=None;self.caption=text;self.setMinimumWidth(0);self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

    def setPixmap(self,pixmap):
        self.pixmap=pixmap;self.update()

    def paintEvent(self,event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),10,10);painter.setClipPath(path)
        gradient=QLinearGradient(0,0,self.width(),self.height());gradient.setColorAt(0,QColor('#deeff8'));gradient.setColorAt(1,QColor('#b7ddeb'));painter.fillRect(self.rect(),gradient)
        if self.pixmap and not self.pixmap.isNull():
            scaled=self.pixmap.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation);painter.drawPixmap((self.width()-scaled.width())//2,(self.height()-scaled.height())//2,scaled)
            if self.layout():
                shade=QLinearGradient(0,0,self.width(),0);shade.setColorAt(0,QColor(233,247,255,245));shade.setColorAt(.62,QColor(233,247,255,215));shade.setColorAt(1,QColor(233,247,255,10));painter.fillRect(self.rect(),shade)
        elif self.caption:
            painter.setPen(QColor('#658ca1'));painter.drawText(self.rect(),Qt.AlignCenter,self.caption)
        else:
            painter.setPen(Qt.NoPen);painter.setBrush(QColor('#cee8f0'));painter.drawEllipse(int(self.width()*.73),30,150,150)
            painter.setBrush(QColor('#b6d8e6'));painter.drawPolygon(QPolygonF([QPointF(self.width()*.5,self.height()),QPointF(self.width()*.68,75),QPointF(self.width()*.88,self.height())]))
        painter.end()


class SelectionDialog(QDialog):
    def __init__(self,files,store,p2p=False,notice='',parent=None,install=None):
        super().__init__(parent);self.files=files;self.store=store;self.setWindowTitle('选择要下载的文件 · PlayHub');self.resize(840,620)
        lay=QVBoxLayout(self);lay.setSpacing(15);lay.setContentsMargins(24,24,24,24)
        lay.addWidget(label('选择你需要的文件','Title'));lay.addWidget(label(notice or '只下载勾选项。单个 ZIP / APK / EXE 作为一个文件，不能假装可选择包内内容。','Notice'))
        self.table=QTableWidget(len(files),3);self.table.setHorizontalHeaderLabels(['选择','文件 / 相对目录','大小']);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);self.table.setColumnWidth(0,56);self.table.setColumnWidth(2,110);self.table.verticalHeader().hide();self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.setObjectName('FileSelectionTable')
        for i,f in enumerate(files):
            c=QTableWidgetItem();c.setFlags(Qt.ItemIsUserCheckable|Qt.ItemIsEnabled);c.setCheckState(Qt.Checked if len(files)==1 else Qt.Unchecked);self.table.setItem(i,0,c);self.table.setItem(i,1,QTableWidgetItem(f.path));self.table.setItem(i,2,QTableWidgetItem(human_bytes(f.size)));self.table.setRowHeight(i,39)
        lay.addLayout(row(button('全选',lambda:self.set_all(True)),button('取消全选',lambda:self.set_all(False)),1));lay.addWidget(self.table,1)
        self.summary=label('','Muted');lay.addWidget(self.summary);self.table.itemChanged.connect(self.update_summary)
        self.path=QLineEdit(store.data['directory']);self.path.setObjectName('DownloadDirectory');self.path.setPlaceholderText('请选择保存目录')
        self.ask=store.data['ask_directory']
        lay.addWidget(label('本次保存到' if self.ask else '默认保存目录（设置中可更改）','Muted'))
        lay.addLayout(row(self.path,button('选择文件夹',self.choose_directory)))
        self.remember=QCheckBox('将本次目录设为默认目录');lay.addWidget(self.remember)
        self.p2p_notice=QCheckBox('我理解 P2P 下载期间会向节点上传，上传上限 64 KiB/s；下载结束默认停止。')
        if p2p:lay.addWidget(self.p2p_notice);lay.addWidget(label('BT 为校验跨文件分片，可能取得少量未选文件边界数据并保存在内部 partfile。','Muted'))
        self.is_p2p=p2p
        self.install_config=dict(install or {})
        self.auto_install=QCheckBox('下载完成后安全解压ZIP，并按官方配置设置启动程序（不会自动运行）')
        self.auto_install.setChecked(bool(self.install_config.get('enabled')))
        if self.install_config.get('executable'):
            lay.addWidget(self.auto_install);lay.addWidget(label('配置的相对启动项：'+self.install_config['executable'],'Muted'))
        else:self.auto_install.setChecked(False)
        self.error=label('');self.error.setStyleSheet('color:#b4665a');lay.addWidget(self.error)
        self.confirm=button('开始下载',self.confirm_selection,True);self.confirm.setObjectName('ConfirmDownload')
        lay.addLayout(row(1,button('取消',self.reject),self.confirm));self.update_summary()

    def choose_directory(self):
        target=QFileDialog.getExistingDirectory(self,'选择游戏下载文件夹',self.path.text())
        if target:self.path.setText(target)

    def set_all(self,checked):
        for i in range(self.table.rowCount()):self.table.item(i,0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def selected(self):return [f for i,f in enumerate(self.files) if self.table.item(i,0).checkState()==Qt.Checked]

    def update_summary(self):
        chosen=self.selected();known=sum(max(0,f.size) for f in chosen);self.summary.setText(f'已选择 {len(chosen)} / {len(self.files)} 个文件 · '+human_bytes(known)+('（部分大小待下载确认）' if any(f.size<0 for f in chosen) else ''));self.confirm.setEnabled(bool(chosen))

    def confirm_selection(self):
        chosen=self.selected()
        if not chosen:self.error.setText('请至少勾选一个文件。');return
        if self.is_p2p and not self.p2p_notice.isChecked():self.error.setText('请确认 P2P 上传说明。');return
        root=Path(self.path.text().strip())
        if not root.is_absolute():self.error.setText('请选择绝对文件夹路径。');return
        try:
            for f in chosen:safe_target(root,f.path)
            probe=root
            while not probe.exists():probe=probe.parent
            need=sum(max(0,f.size) for f in chosen)
            if shutil.disk_usage(probe).free<need+32*1024*1024:self.error.setText('所选磁盘剩余空间不足。');return
            root.mkdir(parents=True,exist_ok=True)
            if self.remember.isChecked():self.store.data['directory']=str(root);self.store.save()
            self.accept()
        except Exception as e:self.error.setText(str(e))

class Launcher(QMainWindow):
    def __init__(self,store=None):
        super().__init__();self.store=store or StateStore();self.setWindowTitle('PlayHub · 游戏启动器 '+VERSION+' Alpha');self.resize(1380,920);self.setMinimumSize(1000,690);self.setStyleSheet(STYLE);self.setWindowIcon(QIcon(str(resource_dir()/'assets/playhub.ico')))
        self.manager=DownloadManager(self.store,self);self.manager.notification.connect(self.notify);self.manager.changed.connect(self.queue_changed)
        self.cloud=CloudBridge(self);self.cloud.authorized.connect(self.cloud_authorized);self.cloud.error.connect(self.cloud_error);self.cloud.status.connect(self.cloud_status);self.cloud.needs_login.connect(self.cloud_needs_login);self.cloud.selection_complete.connect(self.cloud_selection_complete)
        self.pending_cloud={};self.cloud_busy=set();self.cloud_authorized_files={}
        self.provider_states={k:'尚未验证登录' for k in PROVIDERS};self.route='home';self.jobs=[];self.dialogs=[];self.stop_metadata=threading.Event();self.catalog=self.load_catalog()
        self.root=QWidget();self.root.setObjectName('Main');self.setCentralWidget(self.root);outer=QHBoxLayout(self.root);outer.setSpacing(0);outer.setContentsMargins(0,0,0,0)
        sidebar=QWidget();sidebar.setObjectName('Sidebar');sidebar.setFixedWidth(210);sl=QVBoxLayout(sidebar);sl.setContentsMargins(18,32,18,24);sl.setSpacing(8);sl.addWidget(label('P  PlayHub','Brand'));sl.addWidget(label('PLAY SOMETHING GOOD','Eyebrow'));sl.addSpacing(32);self.navs={}
        for key,text in [('home','主页'),('store','游戏商店'),('library','我的游戏库'),('downloads','下载管理')]:
            w=button(text,lambda checked=False,k=key:self.show_page(k));w.setObjectName('Nav');w.setCheckable(True);self.navs[key]=w;sl.addWidget(w)
        sl.addStretch(1)
        for key,text in [('profile','用户设置'),('settings','设置与网盘登录'),('updates','启动器更新'),('about','关于')]:
            w=button(text,lambda checked=False,k=key:self.show_page(k));w.setObjectName('Nav');w.setCheckable(True);self.navs[key]=w;sl.addWidget(w)
        self.user_label=label(self.store.data['name'] or '新玩家','Muted');sl.addSpacing(15);sl.addWidget(self.user_label);outer.addWidget(sidebar)
        area=QVBoxLayout();area.setContentsMargins(30,24,30,16);area.setSpacing(18);outer.addLayout(area,1)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索游戏、类型或开发者');self.search.returnPressed.connect(lambda:self.show_page('store'));area.addLayout(row(self.search,button('新建下载',self.new_download),button('下载队列',lambda:self.show_page('downloads'))))
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);area.addWidget(self.scroll,1);self.status=label('Alpha 测试版 · 本地档案 · 安全解压需确认 · 不自动执行程序','Muted');area.addWidget(self.status)
        self.refresh_timer=QTimer(self);self.refresh_timer.timeout.connect(self.refresh_downloads);self.refresh_timer.start(700)
        self.show_page('home')
        if not self.store.data['name']:QTimer.singleShot(100,self.first_run)

    DEFAULT_CATALOG_URL='https://raw.githubusercontent.com/jkzhangc/playhub-launcher/main/catalog/catalog.json'

    @staticmethod
    def validate_catalog(data):
        if not isinstance(data,dict) or not isinstance(data.get('games'),list):raise DownloadError('商店清单必须包含 games 数组。')
        if data.get('format','playhub-catalog-v1')!='playhub-catalog-v1':raise DownloadError('不支持的商店清单格式。')
        seen=set()
        for game in data['games']:
            if not isinstance(game,dict) or not isinstance(game.get('id'),str) or not game['id'] or not isinstance(game.get('name'),str) or not game['name'].strip():raise DownloadError('商店游戏缺少有效的 ID 或名称。')
            if game['id'] in seen:raise DownloadError('商店游戏 ID 重复。')
            seen.add(game['id'])
        merchandising=data.get('merchandising',{})
        if not isinstance(merchandising,dict) or not isinstance(merchandising.get('hero',{}),dict) or not isinstance(merchandising.get('weekly_ids',[]),list):raise DownloadError('商店展示配置格式无效。')
        return data

    def load_catalog(self):
        self.catalog_meta={};self.catalog_base=self.store.data.get('catalog_url') or self.DEFAULT_CATALOG_URL
        self.store_filter='全部';self.store_sort='recommended';self.library_filter='全部游戏';self.download_filter='全部任务';self.image_waiters={};self.image_failed=set()
        for path in (self.store.root/'catalog-cache.json',resource_dir()/'catalog/catalog.json'):
            try:
                data=self.validate_catalog(json.loads(path.read_text('utf-8-sig')));self.catalog_meta=data;return data['games']
            except (OSError,ValueError,DownloadError):continue
        return []

    def artwork(self,source='',height=145,caption='暂未提供封面'):
        widget=Artwork(caption,height)
        if source:self.load_image(widget,source)
        return widget

    def load_image(self,widget,source):
        import hashlib
        import weakref
        from urllib.parse import urljoin
        from shiboken6 import isValid
        source=str(source).strip()
        if not source:return
        parsed=urlsplit(source)
        local=None
        if not parsed.scheme:
            candidates=[resource_dir()/'catalog'/source,resource_dir()/source,self.store.root/source]
            local=next((p for p in candidates if p.is_file()),None)
            if local is None:source=urljoin(self.catalog_base,source)
        elif len(parsed.scheme)==1 or parsed.scheme=='file':
            from urllib.request import url2pathname
            local=Path(url2pathname(parsed.path)) if parsed.scheme=='file' else Path(source)
        elif parsed.scheme!='https':return
        key=str(local) if local is not None else source
        if key in self.image_failed:return
        def apply(path):
            target=weak()
            if target is None or not isValid(target):return
            from PySide6.QtGui import QImageReader
            reader=QImageReader(str(path));size=reader.size()
            if size.width()<=0 or size.height()<=0 or size.width()*size.height()>40000000:target.setToolTip('图片格式无效或分辨率超出限制');return
            if size.width()>1800 or size.height()>1200:reader.setScaledSize(size.scaled(1800,1200,Qt.KeepAspectRatio))
            reader.setAutoTransform(True);image=reader.read()
            if image.isNull():target.setToolTip('图片无法解码');return
            target.setPixmap(QPixmap.fromImage(image))
        weak=weakref.ref(widget)
        if key in self.image_waiters:self.image_waiters[key].append(apply);return
        self.image_waiters[key]=[apply]
        def fetch():
            cache=self.store.root/'image-cache';cache.mkdir(parents=True,exist_ok=True)
            target=cache/(hashlib.sha256(key.encode('utf-8')).hexdigest()+'.img')
            if target.is_file() and target.stat().st_size<=8*1024*1024:return target
            if local is not None:
                with local.open('rb') as stream:data=stream.read(8*1024*1024+1)
            else:
                if urlsplit(source).scheme!='https':raise DownloadError('封面仅支持本地文件或 HTTPS。')
                with WebClient().open(source,timeout=15) as stream:
                    if urlsplit(stream.url).scheme!='https':raise DownloadError('封面重定向必须保持 HTTPS。')
                    if int(stream.headers.get('Content-Length') or 0)>8*1024*1024:raise DownloadError('封面超过 8 MiB 限额。')
                    data=stream.read(8*1024*1024+1)
            if len(data)>8*1024*1024:raise DownloadError('封面超过 8 MiB 限额。')
            temporary=target.with_suffix('.tmp');temporary.write_bytes(data);os.replace(temporary,target);return target
        def done(path):
            for callback in self.image_waiters.pop(key,[]):callback(path)
        def failed(message):
            self.image_failed.add(key);self.image_waiters.pop(key,None)
            target=weak()
            if target is not None and isValid(target):target.setToolTip('图片加载失败：'+message)
        self.job(fetch,done,failed)

    def first_run(self):
        n,ok=QInputDialog.getText(self,'欢迎来到 PlayHub','不需要密码，输入昵称即可建立本地档案：')
        if ok and n.strip():self.store.data['name']=n.strip()[:20];self.store.save();self.user_label.setText(self.store.data['name']);self.show_page(self.route)

    def job(self,fn,done,error=None):
        worker=Work(fn);self.jobs.append(worker)
        def cleanup(*args):
            if worker in self.jobs:self.jobs.remove(worker)
        worker.signals.done.connect(done);worker.signals.error.connect(error or self.notify);worker.signals.done.connect(cleanup);worker.signals.error.connect(cleanup);QThreadPool.globalInstance().start(worker)

    def notify(self,text):self.status.setText(str(text))

    def show_page(self,key):
        self.route=key
        for k,w in self.navs.items():w.setChecked(k==key)
        body=QWidget();body.setObjectName('PageBody');lay=QVBoxLayout(body);lay.setSpacing(18);lay.setContentsMargins(0,6,0,20);self.body=body;self.page_layout=lay;self.scroll.setWidget(body)
        functions={'home':self.home_page,'store':self.store_page,'library':self.library_page,'downloads':self.download_page,'settings':self.settings_page,'profile':self.profile_page,'updates':self.updates_page,'about':self.about_page}
        functions.get(key,self.home_page)(lay);lay.addStretch(1);lay.setSizeConstraint(QLayout.SetMinAndMaxSize)

    def heading(self,lay,title,desc='',eyebrow='YOUR NEXT ADVENTURE'):
        lay.addWidget(label(eyebrow,'Eyebrow'));lay.addWidget(label(title,'Title'))
        if desc:lay.addWidget(label(desc,'Muted'))

    def section(self,lay,title,action='',callback=None):
        text=label(title,'SectionTitle');text.setStyleSheet('font-size:18px;font-weight:600;color:#2e5c77;');bar=row(text,1)
        if action:bar.addWidget(button(action,callback))
        lay.addLayout(bar)

    def empty(self,lay,title,description,action='',callback=None):
        box,bl=panel();box.setMinimumHeight(205);bl.addStretch();heading=label(title,'SectionTitle');heading.setAlignment(Qt.AlignCenter);bl.addWidget(heading);detail=label(description,'Muted');detail.setAlignment(Qt.AlignCenter);bl.addWidget(detail)
        if action:bl.addLayout(row(1,button(action,callback,True),1))
        bl.addStretch();lay.addWidget(box)

    def hero(self,store=False):
        config=self.catalog_meta.get('merchandising',{}).get('hero',{});game=next((g for g in self.catalog if g['id']==config.get('game_id')),None)
        source=config.get('image') or (game or {}).get('cover','');hero=self.artwork(source,248 if store else 258,'');hero.setObjectName('StoreHero' if store else 'HomeHero');hl=QVBoxLayout(hero);hl.setContentsMargins(30,25,30,25);hl.setSpacing(12)
        title=config.get('title') or (game or {}).get('name') or ('好游戏，值得被发现。' if store else '下一段冒险，从这里开始。')
        subtitle=config.get('subtitle') or (game or {}).get('summary') or ('商店正在准备中，管理员发布后将在这里展示真实作品。' if store else '收藏喜欢的世界，管理每一次下载，把时间留给游玩。')
        for text,name in [(config.get('eyebrow') or 'PLAYHUB / YOUR NEXT WORLD','Eyebrow'),(title,'Title'),(subtitle,'')]:
            item=label(str(text),name);item.setStyleSheet('background:transparent;border:none;border-radius:0;padding:0;');item.setMaximumWidth(610);hl.addWidget(item)
        hl.addStretch();hl.addLayout(row(button('查看精选游戏' if game else '刷新商店' if store else '探索游戏商店',lambda:self.detail(game) if game else self.refresh_catalog() if store else self.show_page('store'),True),1));return hero

    def home_page(self,lay):
        from datetime import datetime
        greeting='早上好' if datetime.now().hour<12 else '下午好' if datetime.now().hour<18 else '晚上好'
        self.heading(lay,greeting+'，'+(self.store.data['name'] or '玩家'),'好故事，值得再出发。今天也找一个喜欢的世界。','WELCOME BACK')
        top=QHBoxLayout();top.setSpacing(18);top.addWidget(self.hero(),3);queue,ql=panel();queue.setMinimumWidth(245);queue.setMaximumWidth(315);ql.addLayout(row(label('下载队列','SectionTitle'),1,label(str(len(self.manager.tasks))+' 项任务','Muted')));self.home_queue=QVBoxLayout();ql.addLayout(self.home_queue);ql.addStretch();ql.addWidget(button('查看所有下载',lambda:self.show_page('downloads')));top.addWidget(queue,1);lay.addLayout(top);self.refresh_home_queue()
        self.section(lay,'继续你的冒险','全部游戏',lambda:self.show_page('library'));self.cards(lay,self.store.data['library'][:4],library=True,columns=4)
        self.section(lay,'为你发现','探索商店',lambda:self.show_page('store'));self.cards(lay,self.recommended_games()[:4],columns=4)

    def recommended_games(self):
        weekly=self.catalog_meta.get('merchandising',{}).get('weekly_ids',[]);positions={str(value):index for index,value in enumerate(weekly)}
        return sorted(self.catalog,key=lambda game:positions.get(game['id'],len(positions)))

    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
            elif item.layout():self.clear_layout(item.layout())

    def refresh_home_queue(self):
        if self.route!='home' or not hasattr(self,'home_queue'):return
        self.clear_layout(self.home_queue)
        tasks=sorted(self.manager.tasks,key=lambda task:task['status']=='complete')[:3]
        if not tasks:self.home_queue.addWidget(label('还没有下载任务','SectionTitle'));self.home_queue.addWidget(label('选择游戏后，真实进度和速度将在这里显示。','Muted'))
        for task in tasks:
            self.home_queue.addLayout(row(label(task['title']),1,label(self.task_status(task),'Muted')));bar=self.task_bar(task);self.home_queue.addWidget(bar);self.home_queue.addWidget(label(human_bytes(task.get('done',0))+' · '+human_bytes(task.get('speed',0))+'/s','Muted'))

    def library_installed(self,game):
        path=game.get('executable','');return bool(path and Path(path).is_file() and Path(path).suffix.lower()=='.exe')

    def game_tasks(self,game):
        return [task for task in self.manager.tasks if task.get('install',{}).get('game_id')==game['id'] or task.get('title')==game['name']]

    def cards(self,lay,games,library=False,columns=3):
        if not games:
            self.empty(lay,'这里还没有游戏' if library else '等待新世界上架','导入本地游戏，或从商店收藏你喜欢的作品。' if library else '商店只展示管理员发布的真实作品；当前没有符合条件的游戏。','导入本地游戏' if library else '刷新商店',self.import_game if library else self.refresh_catalog);return
        grid=QGridLayout();grid.setSpacing(16)
        for i,original in enumerate(games):
            metadata=next((g for g in self.catalog if g['id']==original['id']),{});g={**metadata,**original};box,bl=panel();bl.setContentsMargins(12,12,12,14);bl.setSpacing(10);bl.addWidget(self.artwork(g.get('cover',''),138));bl.addWidget(label(g['name'],'SectionTitle'));bl.addLayout(row(label(g.get('category') or '未分类','Muted'),1,label('Android' if g.get('platform')=='android' else 'Windows','Muted')))
            if library:
                tasks=[t for t in self.game_tasks(g) if t['status']!='complete'];state=self.task_status(tasks[-1]) if tasks else '已安装' if self.library_installed(g) else '已收藏 · 尚未安装';bl.addWidget(label(state,'Muted'))
                if tasks:bl.addWidget(self.task_bar(tasks[-1]))
                launch=button('开始游玩',lambda checked=False,item=original:self.launch_game(item),True);launch.setEnabled(self.library_installed(original));bl.addWidget(launch);bl.addLayout(row(button('启动设置',lambda checked=False,item=original:self.set_executable(item)),button('详情',lambda checked=False,item=g:self.detail(item))))
            else:
                summary=label(g.get('summary') or '开发者尚未提供简介。','Muted');summary.setMaximumHeight(44);bl.addWidget(summary);bl.addWidget(button('查看详情',lambda checked=False,item=g:self.detail(item)))
            grid.addWidget(box,i//columns,i%columns)
        for column in range(columns):grid.setColumnStretch(column,1)
        lay.addLayout(grid)

    def store_page(self,lay):
        self.heading(lay,'发现下一段冒险','独立创意，小众佳作，还有属于你的新世界。','DISCOVER / STORE');lay.addWidget(self.hero(True))
        tools=QHBoxLayout();tools.setSpacing(7);categories=['全部']+sorted({str(g.get('category') or '未分类') for g in self.catalog})
        if len(categories)==1:categories+=['冒险探索','休闲治愈','模拟经营','剧情解谜','动作冒险']
        for category in categories:
            item=button(category,lambda checked=False,value=category:self.set_view_filter('store_filter',value,'store'));item.setObjectName('Filter');item.setCheckable(True);item.setChecked(self.store_filter==category);tools.addWidget(item)
        tools.addStretch();sort=QComboBox();sort.setObjectName('StoreSort');sort.addItem('综合推荐','recommended');sort.addItem('名称排序','name');sort.addItem('开发者排序','developer');sort.setCurrentIndex(max(0,sort.findData(self.store_sort)));sort.currentIndexChanged.connect(lambda:self.set_view_filter('store_sort',sort.currentData(),'store'));tools.addWidget(sort);lay.addLayout(tools)
        query=self.search.text().strip().casefold();games=[g for g in self.catalog if (self.store_filter=='全部' or (g.get('category') or '未分类')==self.store_filter) and (not query or query in ' '.join(str(g.get(k,'')) for k in ('name','summary','category','developer')).casefold())]
        if self.store_sort=='recommended':games=[g for g in self.recommended_games() if g in games]
        else:games.sort(key=lambda game:str(game.get(self.store_sort,'')).casefold())
        content=QHBoxLayout();content.setSpacing(18);main=QVBoxLayout();main.setSpacing(15);self.cards(main,games);main.addWidget(label('已展示 '+str(len(games))+' 款游戏 · 仅显示真实上架内容','Muted'));main.addStretch();content.addLayout(main,4)
        aside=QWidget();aside.setMinimumWidth(210);aside.setMaximumWidth(260);al=QVBoxLayout(aside);al.setContentsMargins(0,0,0,0);al.setSpacing(16);rank,rl=panel();rl.setContentsMargins(17,20,17,20);rl.addWidget(label('本周推荐榜','SectionTitle'));rl.addWidget(label('管理员精选 · 非玩家评分','Muted'));ids=self.catalog_meta.get('merchandising',{}).get('weekly_ids',[]);weekly=[g for ident in ids for g in self.catalog if g['id']==ident][:5]
        for index,game in enumerate(weekly):
            line=QHBoxLayout();line.addWidget(label(str(index+1).zfill(2),'Muted'));image=self.artwork(game.get('cover',''),45,'');image.setFixedWidth(46);line.addWidget(image);entry=button(game['name'],lambda checked=False,item=game:self.detail(item));entry.setMinimumWidth(0);line.addWidget(entry,1);rl.addLayout(line)
        if not weekly:rl.addSpacing(12);rl.addWidget(label('本周推荐尚未发布','Muted'));rl.addWidget(label('新作品上架后，由管理员选择展示。','Muted'));rl.addSpacing(24)
        al.addWidget(rank);create,cl=panel();create.setStyleSheet('QFrame#Panel{background:#eaf5fc;border:1px solid #d3e6f2;}');cl.addWidget(label('你的作品，也值得被看见','SectionTitle'));cl.addWidget(label('原创或已获分发授权的游戏，审核通过后才能上架。','Muted'));cl.addWidget(button('创作与投稿说明',self.online_unavailable));al.addWidget(create);al.addWidget(button('刷新商店清单',self.refresh_catalog));al.addStretch();content.addWidget(aside,1);lay.addLayout(content)

    def set_view_filter(self,name,value,route):
        setattr(self,name,value);self.show_page(route)

    def download_game(self,game,source=None):
        sources=[item for item in game.get('sources',[]) if isinstance(item,dict) and item.get('url')]
        selected=source or (sources[0] if sources else {'url':game.get('source',''),'type':game.get('source_type','auto')})
        if not selected.get('url'):self.notify('管理员尚未配置此游戏的下载来源。');return
        configured=next((item for item in self.catalog if item['id']==game['id']),game);executable=configured.get('executable','')
        if executable and Path(executable).is_absolute():executable=''
        install={'game_id':game['id'],'name':game['name'],'executable':executable,'enabled':bool(configured.get('auto_install',False)) and bool(executable)}
        self.resolve(selected['url'],selected.get('type','auto'),selected.get('password',''),title=game['name'],install=install)

    def detail(self,g):
        dlg=QDialog(self);dlg.setObjectName('GameDetail');dlg.setWindowTitle(g['name']+' · 游戏详情');dlg.resize(1110,810);dlg.setMinimumSize(880,640);outer=QVBoxLayout(dlg);outer.setContentsMargins(25,22,25,22);outer.setSpacing(16);outer.addLayout(row(button('返回游戏商店',dlg.accept),1,label('GAME DETAIL / PLAYHUB','Eyebrow')))
        scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll,1);body=QWidget();body.setObjectName('PageBody');layout=QVBoxLayout(body);layout.setSpacing(18);scroll.setWidget(body);top=QHBoxLayout();top.setSpacing(20);visual=QVBoxLayout();cover=self.artwork(g.get('cover',''),320);visual.addWidget(cover);screenshots=g.get('screenshots',[])
        if screenshots:
            strip=QHBoxLayout()
            for number,source in enumerate(screenshots[:5]):
                cell=QVBoxLayout();cell.addWidget(self.artwork(source,70,'截图加载中'));cell.addWidget(button('查看截图 '+str(number+1),lambda checked=False,value=source:self.load_image(cover,value)));strip.addLayout(cell)
            visual.addLayout(strip)
        else:visual.addWidget(label('开发者尚未提供游戏截图。','Muted'))
        visual.addStretch();top.addLayout(visual,3);info,il=panel();info.setMinimumWidth(285);info.setMaximumWidth(350);il.addWidget(label(g.get('category') or '独立游戏','Eyebrow'));il.addWidget(label(g['name'],'Title'));il.addWidget(label(g.get('developer') or '开发者尚未填写','Muted'));il.addWidget(label(g.get('summary') or '简介尚未提供。','Muted'));owned=any(item['id']==g['id'] for item in self.store.data['library']);add=button('已加入游戏库' if owned else '加入我的游戏库',lambda:self.detail_add_library(g,add));add.setEnabled(not owned);il.addWidget(add)
        sources=[source for source in g.get('sources',[]) if isinstance(source,dict) and source.get('url')];choices=QComboBox()
        for source in sources:choices.addItem(str(source.get('label') or source.get('type') or '下载来源'),source)
        if sources:il.addWidget(label('选择下载来源','Muted'));il.addWidget(choices)
        download=button('选择文件并下载',lambda:self.download_game(g,choices.currentData() if sources else None),True);download.setEnabled(bool(sources or g.get('source')));il.addWidget(download)
        for title,value in [('游戏版本',g.get('version') or '尚未填写'),('运行平台','Android' if g.get('platform')=='android' else 'Windows'),('游戏分类',g.get('category') or '未分类'),('来源数量',str(len(sources) or int(bool(g.get('source')))))]:il.addLayout(row(label(title,'Muted'),1,label(str(value))))
        il.addWidget(label('下载前先选择文件与目录。安全解压仅按配置和用户确认执行，完成后不会自动运行程序。','Notice'));il.addStretch();top.addWidget(info,1);layout.addLayout(top);tabs=QTabWidget();tabs.setObjectName('GameDetailTabs')
        for title,text in [('介绍',g.get('description') or g.get('summary') or '开发者尚未提供详细介绍。'),('系统需求',g.get('system_requirements') or '开发者尚未提供系统配置要求，请在下载前确认设备兼容性。'),('评论与评分','评论与评分尚未上线。当前没有线上评价数据；不会展示示例评分、虚构评论或未验证的玩家数量。')]:
            page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(24,22,24,22);page_layout.addWidget(label(title,'SectionTitle'));page_layout.addWidget(label(str(text),'Muted'));page_layout.addStretch();tabs.addTab(page,title)
        tabs.setMinimumHeight(190);layout.addWidget(tabs);self.dialogs.append(dlg);dlg.finished.connect(lambda:self.dialogs.remove(dlg) if dlg in self.dialogs else None);dlg.setAttribute(Qt.WA_DeleteOnClose);dlg.open()

    def detail_add_library(self,game,control):
        self.add_library(game);control.setText('已加入游戏库');control.setEnabled(False)

    def add_library(self,g):
        if any(x.get('id')==g['id'] for x in self.store.data['library']):self.notify('已经在你的游戏库中。');return
        self.store.data['library'].append({key:g[key] for key in ('id','name','source','source_type','sources','cover','category','summary','developer','version','platform','screenshots','description','system_requirements','auto_install') if key in g}|{'executable':''});self.store.save();self.notify('已加入我的游戏库。')

    def library_page(self,lay):
        self.heading(lay,'我的游戏库','你的世界，在这里相遇。已收藏 '+str(len(self.store.data['library']))+' 款游戏。','YOUR COLLECTION');lay.addLayout(row(button('导入本地游戏',self.import_game),1));tabs=QHBoxLayout()
        for name in ('全部游戏','已安装','下载中'):
            control=button(name,lambda checked=False,value=name:self.set_view_filter('library_filter',value,'library'));control.setObjectName('Filter');control.setCheckable(True);control.setChecked(self.library_filter==name);tabs.addWidget(control)
        tabs.addStretch();lay.addLayout(tabs);games=[game for game in self.store.data['library'] if self.library_filter=='全部游戏' or (self.library_filter=='已安装' and self.library_installed(game)) or (self.library_filter=='下载中' and any(t['status'] in ('queued','downloading','installing','paused','auth_required') for t in self.game_tasks(game)))];self.cards(lay,games,library=True,columns=3);lay.addWidget(label('实际启动项存在时才显示已安装；Android 安装包不能在 Windows 中直接启动。','Muted'))

    def import_game(self):
        exe,_=QFileDialog.getOpenFileName(self,'选择你信任的游戏启动程序','','Windows 程序 (*.exe)')
        if not exe:return
        name,ok=QInputDialog.getText(self,'导入游戏','显示名称：',text=Path(exe).stem)
        if ok and name.strip():self.store.data['library'].append({'id':uuid.uuid4().hex,'name':name.strip(),'executable':exe,'source':''});self.store.save();self.show_page('library')

    def set_executable(self,g):
        exe,_=QFileDialog.getOpenFileName(self,'选择该游戏的 Windows 启动程序','','Windows 程序 (*.exe)')
        if exe:g['executable']=exe;self.store.save();self.show_page('library')

    def launch_game(self,g):
        p=Path(g.get('executable',''))
        if not p.is_file() or p.suffix.lower()!='.exe':QMessageBox.information(self,'尚不能启动','请先配置你信任的本地 Windows 游戏 EXE。APK 不能直接在 Windows 启动。');return
        if QMessageBox.question(self,'确认启动',f'将运行你配置的游戏程序：{p}')!=QMessageBox.Yes:return
        try:subprocess.Popen([str(p)],cwd=str(p.parent));self.notify('已启动：'+g['name'])
        except OSError as e:self.notify(str(e))

    def new_download(self):
        dlg=QDialog(self);dlg.setWindowTitle('新建下载 · 选择来源');dlg.resize(640,410);l=QVBoxLayout(dlg);l.setContentsMargins(24,24,24,24);l.setSpacing(14);l.addWidget(label('添加下载来源','Title'));kind=QComboBox();kinds=[('自动识别','auto'),('HTTPS 文件直链','direct'),('GitHub Release 附件清单','github'),('PlayHub 多文件清单 JSON','manifest'),('BitTorrent 种子 / 磁力 P2P','torrent'),('坚果云','nutstore'),('百度网盘','baidu'),('夸克网盘','quark'),('蓝奏云 / lanzoui','lanzou')];[kind.addItem(t,k) for t,k in kinds];url=QLineEdit();url.setPlaceholderText('HTTPS 分享、文件直链、magnet:? 或本地 .torrent');pwd=QLineEdit();pwd.setPlaceholderText('分享提取码（如需要）');pwd.setEchoMode(QLineEdit.Password);l.addWidget(kind);l.addLayout(row(url,button('选种子',lambda:self.pick_torrent(url))));l.addWidget(pwd);l.addWidget(label('多文件会先列出清单。直链单文件和 ZIP/APK 不提供虚假的包内勾选；网盘仅使用官方授予的访问权限。','Notice'))
        def go():
            u=url.text().strip()
            if not u:return
            k=kind.currentData();password=pwd.text();dlg.accept();self.resolve(u,k,password)
        l.addLayout(row(1,button('取消',dlg.reject),button('读取文件清单',go,True)));dlg.exec()

    def pick_torrent(self,target):
        p,_=QFileDialog.getOpenFileName(self,'选择种子文件','','BitTorrent (*.torrent)')
        if p:target.setText(p)

    def detect(self,url):
        if url.lower().startswith('magnet:') or url.lower().endswith('.torrent'):return 'torrent'
        host=(urlsplit(url).hostname or '').lower()
        if host in ('www.jianguoyun.com','jianguoyun.com'):return 'nutstore'
        if host=='pan.baidu.com':return 'baidu'
        if host=='pan.quark.cn':return 'quark'
        if is_lanzou_host(host):return 'lanzou'
        return 'direct'

    def resolve(self,url,kind='auto',password='',title='',install=None):
        if not url:self.new_download();return
        if kind=='auto':kind=self.detect(url)
        if kind=='github':
            name=url.strip()
            if name.startswith('https://github.com/'):name=name[len('https://github.com/'):].rstrip('/')
            if '/releases/tag/' in name:repository,tag=name.split('/releases/tag/',1)
            else:
                repository,separator,tag=name.partition('@')
                if not separator:tag='latest'
            self.resolve_release(repository,tag,title=title,install=install);return
        self.notify('正在读取来源与文件清单；尚未开始下载。')
        if kind in ('baidu','quark'):
            QMessageBox.information(self,'需要官方授权','将打开该网盘官方页面。请自行登录并按平台要求完成验证。只有平台提供有效文件下载地址，才会转回启动器。要求外部专用客户端的资源暂不承诺支持。');self.cloud_open(kind,'share',url);return
        if kind=='lanzou':
            if not password:
                password,ok=QInputDialog.getText(self,'蓝奏云提取码','如分享需要提取码，请输入（可留空）：')
                if not ok:return
            try:self.cloud.command('lanzou','resolve_lanzou',url,password);self.notify('正在使用正常分享流程读取蓝奏云授权文件…')
            except Exception as e:self.notify(str(e))
            return
        if kind=='nutstore':
            if 'nutstore' in self.cloud_busy:
                self.notify('坚果云请求正在处理，已保留原选择，不重复打开窗口。')
                try:self.cloud.command('nutstore','focus')
                except Exception:pass
                return
            self.cloud_busy.add('nutstore')
            def work():
                s=NutstoreShare(url);return s,s.files()
            def failed(message):
                self.cloud_busy.discard('nutstore');self.notify(message)
            worker=Work(work);self.jobs.append(worker);worker.signals.done.connect(lambda result:self.nutstore_selection(result,title,install));worker.signals.error.connect(failed);QThreadPool.globalInstance().start(worker);return
        if kind=='torrent':
            def work():
                if url.startswith('magnet:'):info,cache=self.manager.p2p.metadata(url,self.stop_metadata);return self.manager.p2p.entries(info),cache,url
                if url.startswith('https:'):
                    entry=direct_entry(url);entry.path='metadata-'+uuid.uuid4().hex+'.torrent';result=__import__('playhub.http_engine',fromlist=['download_file']).download_file(entry,self.store.root/'torrent-cache',threading.Event());p=result['path']
                else:p=url
                info=self.manager.p2p.load_torrent(p);return self.manager.p2p.entries(info),p,''
            self.job(work,lambda result:self.choose_files(result[0],title=title,torrent=result[1],magnet=result[2],install=install));return
        self.job(lambda:manifest_entries(url) if kind=='manifest' else [direct_entry(url)],lambda files:self.choose_files(files,title=title,install=install))

    def nutstore_selection(self,result,title,install=None):
        source,files=result
        dlg=SelectionDialog(files,self.store,notice='只下载勾选文件。已有授权会话则直接下载；未登录会先询问，再只打开官方登录页面。',parent=self,install=install)
        if dlg.exec()!=QDialog.Accepted:
            self.cloud_busy.discard('nutstore');return
        chosen=dlg.selected()
        task=self.manager.add(chosen,dlg.path.text(),title or '坚果云下载',deferred=True,install={**(install or {}),'enabled':dlg.auto_install.isChecked()})
        self.pending_cloud[task['id']]={'files':chosen,'directory':dlg.path.text(),'title':title,'provider':'nutstore','url':source.url,'task':task['id']}
        self.show_page('downloads')
        try:self.cloud.command('nutstore','share',source.url,files=chosen,request_id=task['id'])
        except Exception as exc:
            self.cloud_busy.discard('nutstore');self.notify(str(exc))

    def cloud_needs_login(self,provider,ident,message):
        self.cloud_busy.discard(provider)
        task=next((t for t in self.manager.tasks if t['id']==ident),None)
        if task:self.manager.update(task,status='auth_required',message='需要官方登录，已保留原文件、目录与任务')
        self.showNormal();self.raise_();self.activateWindow();QApplication.alert(self,3000)
        answer=QMessageBox.question(self,'需要登录'+PROVIDERS[provider][0],message+chr(10)+'是否打开官方登录页？验证成功会自动关闭并继续下载。')
        if answer==QMessageBox.Yes:
            try:self.cloud.command(provider,'login',request_id=ident)
            except Exception as exc:self.notify(str(exc))

    def cloud_selection_complete(self,provider,ident):
        self.cloud_busy.discard(provider)
        expected=self.pending_cloud.get(ident)
        authorized=self.cloud_authorized_files.get(ident,{})
        if not expected:return
        files=expected['files']
        if len(authorized)!=len(files):self.notify('部分文件尚未取得授权，原任务继续等待；不会重新选择文件。');return
        chosen=[authorized[f.path][0] for f in files]
        web=authorized[files[0].path][1]
        for _,session in authorized.values():
            for cookie in session.cookies:web.cookies.set_cookie(cookie)
        try:self.manager.authorize(ident,chosen,web)
        except Exception as exc:self.notify(str(exc));return
        self.pending_cloud.pop(ident,None);self.cloud_authorized_files.pop(ident,None)
        self.showNormal();self.raise_();self.activateWindow();self.show_page('downloads');self.notify('授权完成，沿用之前的文件与目录，已自动开始下载。')

    def choose_files(self,files,title='',torrent='',magnet='',web=None,install=None):
        dlg=SelectionDialog(files,self.store,p2p=bool(torrent),parent=self,install=install)
        if dlg.exec()==QDialog.Accepted:
            self.manager.add(dlg.selected(),dlg.path.text(),title,torrent,magnet,web,install={**(install or {}),'enabled':dlg.auto_install.isChecked()});self.show_page('downloads')

    def cloud_open(self,provider,action='login',url=''):
        try:self.cloud.command(provider,action,url);self.notify('已请求打开 '+PROVIDERS[provider][0]+' 官方页面。不会读取密码。')
        except Exception as e:self.cloud_error(str(e))

    def cloud_status(self,provider,message):
        self.provider_states[provider]=message;self.notify(PROVIDERS.get(provider,(provider,''))[0]+'：'+message)
        if self.route=='settings':self.show_page('settings')

    def cloud_error(self,message):
        self.notify('网盘：'+message);QMessageBox.warning(self,'网盘下载暂未继续',message+chr(10)+'不会绕过平台限制，也不会把错误网页保存为游戏。')

    def cloud_authorized(self,entry,web,provider,ident=''):
        self.provider_states[provider]='本次下载已获平台授权'
        if ident in self.pending_cloud:
            expected={f.path for f in self.pending_cloud[ident]['files']}
            if entry.path not in expected:self.notify('收到未选择的文件，已拒绝下载。');return
            self.cloud_authorized_files.setdefault(ident,{})[entry.path]=(entry,web)
            return
        self.showNormal();self.raise_();self.activateWindow();QApplication.alert(self,3000)
        self.choose_files([entry],title=entry.path,web=web)

    def queue_changed(self):
        if self.route=='downloads':self.refresh_downloads()
        elif self.route=='home':self.refresh_home_queue()

    def task_status(self,task):
        return {'queued':'等待中','downloading':'下载中','installing':'安全解压中','paused':'已暂停','complete':'已完成','error':'失败','auth_required':'需要授权'}.get(task['status'],task['status'])

    def task_bar(self,task):
        bar=QProgressBar();total=task.get('total',-1);bar.setRange(0,1000 if total>0 or task['status']!='downloading' else 0);bar.setValue(int(min(1000,max(0,task.get('done',0))/max(total,1)*1000)));bar.setTextVisible(False);bar.setFixedHeight(7);return bar

    def download_page(self,lay):
        self.heading(lay,'下载管理','每一次出发，都在这里准备就绪。真实任务、真实字节数。','DOWNLOAD CENTER');lay.addLayout(row(button('暂停所有任务',self.pause_all),button('新建下载',self.new_download,True),1));stats=QHBoxLayout();self.download_stats={}
        for key,title in [('speed','当前下载速度'),('active','进行中的任务'),('limit','全局下载限速')]:
            box,bl=panel();bl.addWidget(label(title,'Muted'));value=label('','Title');bl.addWidget(value);self.download_stats[key]=value;stats.addWidget(box)
        lay.addLayout(stats);filters=QHBoxLayout()
        for name in ('下载中','已完成','全部任务'):
            control=button(name,lambda checked=False,value=name:self.set_view_filter('download_filter',value,'downloads'));control.setObjectName('Filter');control.setCheckable(True);control.setChecked(self.download_filter==name);filters.addWidget(control)
        filters.addStretch();lay.addLayout(filters);lay.addWidget(label('P2P 下载期间上传上限 64 KiB/s，完成即停止。网盘会话仅在本次运行内保留，退出后需重新授权。','Notice'));self.download_box=QVBoxLayout();lay.addLayout(self.download_box);self.refresh_downloads()

    def pause_all(self):
        for task in list(self.manager.tasks):
            if task['status'] in ('queued','downloading'):self.manager.pause(task['id'])
        self.refresh_downloads()

    def refresh_downloads(self):
        if self.route=='home':self.refresh_home_queue();return
        if self.route!='downloads' or not hasattr(self,'download_box'):return
        self.download_stats['speed'].setText(human_bytes(sum(t.get('speed',0) for t in self.manager.tasks if t['status']=='downloading'))+'/s');self.download_stats['active'].setText(str(sum(t['status'] not in ('complete','error') for t in self.manager.tasks))+' 项');limit=self.store.data.get('limit_mib',0);self.download_stats['limit'].setText(str(limit)+' MiB/s' if limit else '不限速');self.clear_layout(self.download_box)
        tasks=[t for t in self.manager.tasks if self.download_filter=='全部任务' or (self.download_filter=='已完成' and t['status']=='complete') or (self.download_filter=='下载中' and t['status']!='complete')]
        for task in tasks:
            box,bl=panel();bl.addLayout(row(label(task['title'],'SectionTitle'),1,label(self.task_status(task),'Muted')));bl.addWidget(label(human_bytes(task.get('done',0))+' / '+human_bytes(task.get('total',-1))+' · '+human_bytes(task.get('speed',0))+'/s','Muted'));bl.addWidget(self.task_bar(task));bl.addWidget(label(task.get('message',''),'Muted'));bl.addWidget(label(task['directory'],'Muted'));actions=row(1)
            if task['status'] in ('downloading','queued'):actions.addWidget(button('暂停',lambda checked=False,i=task['id']:self.manager.pause(i)))
            elif task['status']=='auth_required' and task['id'] in self.pending_cloud:actions.addWidget(button('登录并继续',lambda checked=False,i=task['id']:self.resume_cloud_task(i)))
            elif task['status'] in ('paused','error','auth_required'):actions.addWidget(button('继续 / 重试',lambda checked=False,i=task['id']:self.manager.resume(i)))
            delete_button=button('删除任务',lambda checked=False,i=task['id']:self.delete_task(i));delete_button.setObjectName('DeleteDownloadTask');delete_button.setEnabled(task['status'] not in ('downloading','installing'));actions.addWidget(delete_button);actions.addWidget(button('打开目录',lambda checked=False,p=task['directory']:QDesktopServices.openUrl(QUrl.fromLocalFile(p))));bl.addLayout(actions);self.download_box.addWidget(box)
        if not tasks:self.empty(self.download_box,'下载队列为空' if not self.manager.tasks else '当前分类暂无任务','选择游戏或添加你有权访问的下载来源。','新建下载',self.new_download)

    def resume_cloud_task(self,ident):
        context=self.pending_cloud.get(ident)
        if not context:self.notify('本次授权记录已结束，请重新选择来源。');return
        try:self.cloud.command(context['provider'],'continue',request_id=ident)
        except Exception as exc:self.notify(str(exc))

    def delete_task(self,ident):
        task=next((t for t in self.manager.tasks if t['id']==ident),None)
        if not task:return
        dlg=QDialog(self);dlg.setWindowTitle('确认删除下载任务');dlg.resize(660,360);l=QVBoxLayout(dlg);l.setContentsMargins(24,24,24,24);l.setSpacing(14);l.addWidget(label('删除“'+task['title']+'”的任务记录？','Title'));l.addWidget(label('默认只移除任务，保留已下载文件和部分文件。删除后不再自动续传。','Muted'));remove_files=QCheckBox('同时将此任务下载的文件移入回收站');remove_files.setObjectName('DeleteTaskFiles');remove_files.setChecked(False);l.addWidget(remove_files);details=label('');details.setStyleSheet('color:#a56c4c');l.addWidget(details);listing=QTextEdit();listing.setReadOnly(True);listing.hide();l.addWidget(listing,1)
        def preview(on):
            listing.setVisible(on)
            if not on:details.setText('');return
            try:
                filenames=self.manager.deletion_files(ident)
                details.setText('此操作会移走以下文件；如有修改或无法回收将停止。未记录的文件和其他游戏不会处理。')
                listing.setPlainText(chr(10).join(filenames) if filenames else '没有可回收的任务自有文件；只删除任务记录。')
            except Exception as exc:
                details.setText(str(exc));remove_files.setChecked(False)
        remove_files.toggled.connect(preview)
        def confirm():
            try:
                if remove_files.isChecked():
                    files=self.manager.deletion_files(ident)
                    warning=QMessageBox(self);warning.setIcon(QMessageBox.Warning);warning.setWindowTitle('确认回收所列文件');warning.setTextFormat(Qt.RichText);warning.setText('<b>此操作会移走所列文件，请确认已保留需要的数据。</b>');warning.setInformativeText(chr(10).join(files));warning.setStandardButtons(QMessageBox.Yes|QMessageBox.No);warning.setDefaultButton(QMessageBox.No)
                    if warning.exec()!=QMessageBox.Yes:return
                    from .task_files import backup_and_recycle
                    backup=backup_and_recycle(self.store.root,files)
                    self.manager.remove(ident);self.notify('任务已删除，文件已回收；备份位于：'+str(backup))
                else:self.manager.remove(ident);self.notify('任务已删除，下载文件保持不变。')
                context=self.pending_cloud.pop(ident,None);self.cloud_authorized_files.pop(ident,None)
                if context:
                    self.cloud_busy.discard(context['provider'])
                    self.cloud.command(context['provider'],'cancel',request_id=ident)
                dlg.accept()
            except Exception as exc:details.setText(str(exc))
        l.addLayout(row(1,button('保留任务',dlg.reject),button('确认删除',confirm,True)));dlg.exec();self.refresh_downloads()

    def settings_page(self,lay):
        self.heading(lay,'设置','让 PlayHub 按照你的习惯运行。','MAKE IT YOURS');tabs=QTabWidget();tabs.setObjectName('SettingsTabs');content=QVBoxLayout();self.settings_content(content);pages=[]
        for title in ('下载与带宽','网盘授权','商店与更新'):
            page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(18,20,18,20);page_layout.setSpacing(18);tabs.addTab(page,title);pages.append(page_layout)
        destinations=[0,1,2,0]
        for destination in destinations:
            item=content.takeAt(0)
            if item and item.widget():pages[destination].addWidget(item.widget())
        for page_layout in pages:page_layout.addStretch()
        lay.addWidget(tabs)

    def settings_content(self,lay):
        box,bl=panel();bl.addWidget(label('下载位置与带宽'));self.directory=QLineEdit(self.store.data['directory']);bl.addLayout(row(self.directory,button('选择文件夹',self.choose_default)));self.ask=QCheckBox('每次开始下载时询问保存到哪个文件夹');self.ask.setChecked(self.store.data['ask_directory']);bl.addWidget(self.ask);self.limit=QDoubleSpinBox();self.limit.setRange(0,100000);self.limit.setDecimals(2);self.limit.setSuffix(' MiB/s');self.limit.setValue(float(self.store.data['limit_mib']));bl.addLayout(row(label('全局下载限速（0 = 不限速；队列一次处理一个任务）'),self.limit));bl.addWidget(button('保存下载设置',self.save_settings,True));lay.addWidget(box)
        login,ll=panel();ll.addWidget(label('网盘登录与会话'));ll.addWidget(label('分别使用官方 HTTPS 页面登录。密码只交给平台，启动器不保存密码、Cookie 或临时直链到磁盘；退出启动器后会话清除。','Notice'))
        for provider,(name,url) in PROVIDERS.items():
            line=QVBoxLayout();line.addWidget(label(name));line.addWidget(label(self.provider_states.get(provider,'未验证'),'Muted'));rr=QHBoxLayout();rr.addLayout(line,1);rr.addWidget(button('官方登录 / 管理',lambda checked=False,k=provider:self.cloud_open(k)));rr.addWidget(button('退出此会话',lambda checked=False,k=provider:self.cloud_logout(k)));ll.addLayout(rr)
        ll.addWidget(label('百度网盘、夸克：登录入口已接入；是否能下载取决于平台网页权限/会员/专用客户端要求，尚未用你的文件实测。蓝奏云：已通过你提供的文件下载测试。','Muted'));lay.addWidget(login)
        repo,rl=panel();rl.addWidget(label('GitHub 商店配置'));self.catalog_url=QLineEdit(self.store.data.get('catalog_url',''));self.catalog_url.setPlaceholderText('已审核的商店 catalog.json HTTPS 地址');self.repository=QLineEdit(self.store.data.get('repository',''));self.repository.setPlaceholderText('所有者/启动器仓库名');rl.addWidget(self.catalog_url);rl.addWidget(self.repository);rl.addWidget(button('保存远程配置',self.save_remote));lay.addWidget(repo)
        delivery,dl=panel();dl.addWidget(label('GitHub 下载加速与回退'));self.github_mode=QComboBox();self.github_mode.setObjectName('GitHubDownloadMode')
        for text,value in [('仅 GitHub 源站（默认）','origin'),('下载前短测速，选择较快线路','auto'),('镜像优先，失败回退源站','mirror')]:self.github_mode.addItem(text,value)
        self.github_mode.setCurrentIndex(max(0,self.github_mode.findData(self.store.data.get('github_mode','origin'))));dl.addWidget(self.github_mode);dl.addWidget(label('自动模式每个来源最多读取 1 MiB 样本；当前可选第三方线路 GH-Proxy。只对 GitHub 官方 API 提供 SHA-256 的公开 Release 附件启用镜像。无参考哈希、网盘 Cookie 和带 Token 的链接不发给镜像。','Notice'));dl.addWidget(button('保存下载线路',self.save_github_delivery,True));dl.addLayout(row(button('读取 GitHub Release 文件清单',self.github_release_dialog),button('查看本机完整测速记录',self.show_benchmark),1));lay.addWidget(delivery)

    def save_github_delivery(self):
        mode=self.github_mode.currentData()
        if mode!='origin' and self.store.data.get('github_mode','origin')=='origin':
            answer=QMessageBox.question(self,'启用第三方镜像？','公开 Release 的地址和访问 IP 会被第三方镜像看到。镜像仅作为不可信传输，完成后核对 GitHub 官方 SHA-256，不向其发送令牌、Cookie 或密码。是否启用？')
            if answer!=QMessageBox.Yes:return
        self.store.data['github_mode']=mode;self.store.save();self.notify('GitHub 下载线路已保存。单文件最多按允许线路各尝试一次，不会循环重试。')

    def show_benchmark(self):
        path=resource_dir()/'validation/github-large-benchmark.json'
        if not path.exists():path=resource_dir()/'benchmark-results/github-large-benchmark.json'
        try:
            data=json.loads(path.read_text('utf-8'));lines=['实测时间：'+str(data.get('tested_at','')),'同一完整文件：'+str(data.get('expected_bytes',''))+' 字节','速度包含连接和 TLS 开销；本机当时结果，不保证其他网络。','']
            for item in data.get('results',[]):
                text=item['name']+' · '+str(item['connections'])+'连接 · 第'+str(item['round'])+'次：'
                text+=(str(item['mib_per_second'])+' MiB/s · 官方SHA256一致') if item.get('completed') else item.get('error','失败')
                lines.append(text)
            QMessageBox.information(self,'本机完整文件测速记录',chr(10).join(lines))
        except Exception as exc:self.notify('无法读取测速记录：'+str(exc))

    def github_release_dialog(self):
        repository,ok=QInputDialog.getText(self,'选择 GitHub Release','填写 所有者/仓库名，可附 @版本号；不附则读取 latest：',text=self.store.data.get('repository') or 'jkzhangc/playhub-launcher')
        if not ok or not repository.strip():return
        repository=repository.strip()
        if repository.startswith('https://github.com/'):repository=repository[len('https://github.com/'):].rstrip('/')
        name,separator,tag=repository.partition('@')
        self.resolve_release(name,tag if separator else 'latest')

    def resolve_release(self,repository,tag='latest',title='',install=None):
        from .github_delivery import release_files
        self.notify('正在从 GitHub 官方 API 读取附件名、大小和 SHA-256；未开始下载。')
        def done(result):
            metadata,files=result
            self.choose_files(files,title=title or repository+' · '+str(metadata.get('tag_name',tag)),install=install)
        self.job(lambda:release_files(repository,tag),done)

    def cloud_logout(self,k):
        try:self.cloud.command(k,'logout');self.provider_states[k]='正在清除本次会话'
        except Exception as e:self.notify(str(e))

    def choose_default(self):
        p=QFileDialog.getExistingDirectory(self,'选择默认下载目录',self.directory.text())
        if p:self.directory.setText(p)

    def save_settings(self):
        p=Path(self.directory.text().strip())
        if not p.is_absolute():self.notify('请选择绝对文件夹路径。');return
        self.store.data.update(directory=str(p),ask_directory=self.ask.isChecked(),limit_mib=self.limit.value());self.store.save();self.manager.limits(self.limit.value());self.notify('默认目录、询问选项与限速已保存。')

    def save_remote(self):
        u=self.catalog_url.text().strip();r=self.repository.text().strip()
        if u and not u.startswith('https://'):self.notify('商店地址必须为 HTTPS。');return
        if r and (r.count('/')!=1 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.' for c in r)):self.notify('仓库请填写 所有者/仓库名。');return
        self.store.data.update(catalog_url=u,repository=r);self.store.save();self.notify('远程配置已保存，不涉及管理令牌。')

    def refresh_catalog(self):
        if getattr(self,'catalog_loading',False):self.notify('正在刷新商店，请稍候。');return
        u=self.store.data.get('catalog_url') or self.DEFAULT_CATALOG_URL
        if urlsplit(u).scheme!='https':self.notify('商店清单必须使用 HTTPS。');return
        self.catalog_loading=True;self.notify('正在后台读取商店清单，已有内容继续保留。')
        def fetch():
            data=self.validate_catalog(WebClient().json(u));path=self.store.root/'catalog-cache.json';temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,path);return data
        def done(data):
            self.catalog_loading=False;self.catalog_meta=data;self.catalog=data['games'];self.catalog_base=u;self.image_failed.clear()
            if self.route in ('home','store'):self.show_page(self.route)
            self.notify('商店清单已刷新并缓存，共 '+str(len(self.catalog))+' 款游戏。未经选择的来源不会自动执行。')
        def failed(message):
            self.catalog_loading=False;self.notify('商店刷新失败，保留已有目录与缓存：'+message)
        self.job(fetch,done,failed)

    def profile_page(self,lay):
        self.heading(lay,'用户设置','一个名字，就是你冒险的开始。','PLAYER PROFILE');header,hl=panel();identity=QVBoxLayout();identity.addWidget(label(self.store.data['name'] or '新玩家','Title'));identity.addWidget(label('本地玩家档案 · 无需密码','Muted'));line=row(identity,1)
        for title,value in [('收藏游戏',len(self.store.data['library'])),('下载任务',len(self.manager.tasks)),('实际安装',sum(self.library_installed(g) for g in self.store.data['library']))]:
            stat=QVBoxLayout();stat.addWidget(label(str(value),'Title'));stat.addWidget(label(title,'Muted'));line.addLayout(stat)
        hl.addLayout(line);lay.addWidget(header);columns=QHBoxLayout();box,bl=panel();bl.addWidget(label('个人资料','SectionTitle'));bl.addWidget(label('昵称仅保存在本机，不具备网络账号恢复能力。','Muted'));name=QLineEdit(self.store.data['name']);name.setMaxLength(20);bl.addWidget(label('玩家昵称'));bl.addWidget(name)
        def save():
            if not name.text().strip():self.notify('昵称不能为空。');return
            self.store.data['name']=name.text().strip();self.store.save();self.user_label.setText(self.store.data['name']);self.show_page('profile');self.notify('本地昵称已保存。')
        bl.addWidget(button('保存昵称',save,True));bl.addStretch();columns.addWidget(box,1);community,cl=panel();cl.addWidget(label('社区身份','SectionTitle'));cl.addWidget(label('本地昵称不等于可验证的线上身份。','Muted'));cl.addWidget(label('在线评论与评分 · 尚未上线','Notice'));cl.addWidget(label('在线投稿需要独立的身份认证与官方审核服务；当前客户端不提交或伪造投稿记录。','Muted'));cl.addWidget(button('查看社区说明',self.online_unavailable));cl.addStretch();columns.addWidget(community,1);lay.addLayout(columns);creation,cr=panel();cr.addWidget(label('我的创作','SectionTitle'));cr.addWidget(label('把原创或已获分发授权的作品带给更多玩家。投稿服务尚未开放，商店由管理员维护。','Muted'));cr.addLayout(row(button('创作与投稿说明',self.online_unavailable),1));lay.addWidget(creation)

    def updates_page(self,lay):
        self.heading(lay,'启动器更新','每一次更新，都是一次更好的出发。','KEEP MOVING FORWARD');hero,hl=panel();intro=QVBoxLayout();intro.addWidget(label('VERSION / ALPHA CHANNEL','Eyebrow'));intro.addWidget(label('当前版本 v'+VERSION+' Alpha','Title'));intro.addWidget(label('尚未检查远程版本 · 不虚构发现新版本','Muted'));hl.addLayout(row(intro,1,button('检查 GitHub Releases',self.check_update,True)));lay.addWidget(hero);columns=QHBoxLayout();release,rl=panel();rl.addWidget(label('版本与下载','SectionTitle'));rl.addWidget(label('通过 GitHub 官方接口查询发布说明、附件名称、大小与可用哈希。没有发布版本或网络失败时会如实提示。','Muted'));rl.addWidget(button('选择并下载安装包',lambda:self.resolve_release(self.store.data.get('repository') or 'jkzhangc/playhub-launcher','testing')));rl.addWidget(label('安装包遵循设置中的源站 / 短测速 / 镜像优先模式。','Notice'));rl.addStretch();columns.addWidget(release,1);security,sl=panel();sl.addWidget(label('更新与安全','SectionTitle'));sl.addWidget(label('手动检查 · 手动选择下载 · 不自动执行','Muted'));sl.addWidget(label('尚未实现可信签名更新器，不自动替换正在运行的程序。下载完成后由你决定是否运行。','Notice'));sl.addWidget(label('自动更新仍需可信签名清单、原子替换与失败回滚；当前不提供无效开关。','Muted'));sl.addStretch();columns.addWidget(security,1);lay.addLayout(columns)

    def check_update(self):
        repo=self.store.data.get('repository','')
        if not repo:self.notify('尚未配置官方启动器仓库。');return
        from .github_delivery import release_files
        self.job(lambda:release_files(repo,'testing'),lambda result:QMessageBox.information(self,'测试通道版本查询','GitHub 返回版本：'+str(result[0].get('tag_name','未知'))+chr(10)+str(result[0].get('body',''))[:1800]+chr(10)+'当前版本不会自动安装未签名更新。'))

    def online_unavailable(self):QMessageBox.information(self,'尚未上线','在线投稿、审核、评论评分的受控服务尚未部署。此 Alpha 不包含管理员写入令牌。')

    def about_page(self,lay):
        self.heading(lay,'关于 PlayHub','让好游戏，被更多人看见。','BUILT FOR PLAYERS');brand,bl=panel();bl.setContentsMargins(35,30,35,30);bl.addWidget(label('P  PlayHub','Title'));bl.addWidget(label('一个轻量、开放、属于玩家的游戏启动器。','SectionTitle'));bl.addWidget(label('收藏想玩的游戏，管理每一次下载，开启下一段冒险。','Muted'));bl.addWidget(label('v'+VERSION+' Alpha · Python + PySide6 原生桌面客户端','Eyebrow'));bl.addLayout(row(label('本地玩家档案','Muted'),label('多来源真实下载','Muted'),label('独立官方管理工具','Muted')));lay.addWidget(brand);columns=QHBoxLayout();capability,cl=panel();cl.addWidget(label('已经可以使用','SectionTitle'));cl.addWidget(label('本地昵称与游戏库、真实安装状态、文件勾选、系统目录选择、限速、暂停恢复、磁力 / 种子 P2P，以及网盘官方授权转接。','Muted'));cl.addWidget(label('ZIP 安全解压需明确配置和用户确认，不自动执行游戏。商店封面和截图由目录提供，缺失时保持真实空态。','Notice'));cl.addWidget(button('查看下载设置',lambda:self.show_page('settings')));cl.addStretch();columns.addWidget(capability,1);rights,rl=panel();rl.addWidget(label('权利与安全','SectionTitle'));rl.addWidget(label('仅使用你有权访问和分发的内容。公开玩家客户端不包含管理员令牌。网盘会话仅用于平台授予的访问权限，不绕过验证或付费限制。','Muted'));rl.addWidget(label('在线投稿审核、评论评分、可信签名自动更新尚未上线；没有虚构游戏、评分或社区记录。','Notice'));rl.addWidget(button('查看启动器更新',lambda:self.show_page('updates')));rl.addStretch();columns.addWidget(rights,1);lay.addLayout(columns)

    def closeEvent(self,event):
        if any(t['status']=='downloading' for t in self.manager.tasks):
            if QMessageBox.question(self,'退出启动器','退出会暂停下载并结束网盘授权会话，继续吗？')!=QMessageBox.Yes:event.ignore();return
        self.stop_metadata.set();self.manager.close();self.cloud.close();event.accept()
