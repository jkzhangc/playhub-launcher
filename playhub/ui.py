from __future__ import annotations
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap, QPainter, QColor, QPolygonF, QIcon, QLinearGradient
from PySide6.QtCore import QPointF, QVariantAnimation, QEasingCurve
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QDialog, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QComboBox, QCheckBox, QDoubleSpinBox,
    QProgressBar, QSpinBox, QInputDialog, QTabWidget, QTextEdit, QStackedWidget, QLayout)
from .core import VERSION, DownloadError, FileEntry, StateStore, human_bytes, resource_dir, safe_target
from .sources import WebClient, NutstoreShare, direct_entry, manifest_entries
from .mediafire import is_mediafire_host, resolve_mediafire
from .library_updates import catalog_entry, latest_details, catalog_snapshot, update_status
from .lanzou import is_lanzou_host
from .manager import DownloadManager
from .cloud_login import CloudBridge, PROVIDERS
from .theme import THEMES,normalize_theme,themed_stylesheet,theme_color,system_motion_enabled

STYLE = '''
QWidget {font-family:'Microsoft YaHei UI','Segoe UI';font-size:13px;color:#2c403c;}
QMainWindow,QWidget#Main,QWidget#PageBody {background:#f3f6f4;}
QWidget#Sidebar {background:#ffffff;border-right:1px solid #e1e8e3;}
QLabel#Title {font-size:27px;font-weight:600;color:#214f47;}
QLabel#SectionTitle {font-size:15px;font-weight:600;color:#31554c;}
QLabel#Brand {font-size:23px;font-weight:700;color:#276b5e;}
QLabel#Eyebrow {font-size:10px;color:#718c81;letter-spacing:2px;}
QLabel#Muted {color:#657c72;}
QFrame#Panel {background:#ffffff;border:1px solid #dfe8e1;border-radius:11px;}
QFrame#Panel QLabel {background:transparent;border:0;}
QLabel#Notice,QFrame#Panel QLabel#Notice {background:#edf5ef;border:1px solid #d9e7dd;color:#496b5d;padding:12px;border-radius:7px;}
QPushButton {background:#ffffff;border:1px solid #d4e1d8;border-radius:7px;padding:10px 16px;min-height:19px;color:#3b6658;}
QPushButton:hover {background:#edf5ef;border-color:#9abfaf;}
QPushButton:pressed {background:#d8e9de;border-color:#6d9e88;}
QPushButton:disabled {color:#9baaa1;background:#f3f6f3;border-color:#e3e9e4;}
QPushButton:focus {border:1px solid #397f68;}
QPushButton#Primary,QPushButton#ViewGameUpdate {background:#327d67;border-color:#327d67;color:white;font-weight:600;}
QPushButton#Primary:hover,QPushButton#ViewGameUpdate:hover {background:#286b57;border-color:#286b57;}
QPushButton#Primary:pressed,QPushButton#ViewGameUpdate:pressed {background:#205744;color:white;}
QPushButton#Nav {border:0;border-left:3px solid transparent;text-align:left;color:#6a7e74;background:transparent;padding:14px 14px;font-size:13px;border-radius:6px;}
QPushButton#Nav:hover {background:#f0f6f1;color:#315e4b;}
QPushButton#Nav:checked {background:#e7f1e9;border-left:3px solid #327d67;color:#255c49;font-weight:600;}
QPushButton#Nav:checked:pressed {background:#dbeadf;}
QPushButton#Nav:focus {border-right:1px solid #90b69e;}
QPushButton#Filter {padding:7px 10px;background:transparent;border:1px solid transparent;color:#6b8276;}
QPushButton#Filter:hover {background:#edf4ee;color:#3b6953;}
QPushButton#Filter:checked {background:#e2eee5;color:#2d6d52;border-color:#d4e3d7;font-weight:600;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {background:#ffffff;border:1px solid #dce5de;border-radius:6px;padding:9px;min-height:20px;selection-background-color:#c3decf;selection-color:#203f31;}
QLineEdit:focus,QComboBox:focus,QTextEdit:focus,QPlainTextEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus {border-color:#79a58e;}
QComboBox QAbstractItemView {background:white;color:#304b3d;selection-background-color:#e2eee5;selection-color:#21523d;}
QListWidget,QTableWidget {background:white;border:1px solid #dfe7e0;border-radius:7px;gridline-color:#edf2ed;selection-background-color:#e6f0e8;selection-color:#294d38;}
QHeaderView::section {background:#f2f6f1;border:0;border-bottom:1px solid #e0e8df;padding:10px;color:#657e6d;}
QTableWidget::item {padding:8px;}
QProgressBar {background:#e4ece5;border:0;border-radius:4px;height:7px;text-align:center;color:#4a7057;}
QProgressBar::chunk {background:#6caa87;border-radius:4px;}
QScrollArea {border:0;background:transparent;}
QScrollArea > QWidget > QWidget {background:transparent;}
QScrollBar:vertical {background:#eef3ed;width:9px;border:0;}
QScrollBar::handle:vertical {background:#c3d3c4;border-radius:4px;min-height:35px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QTabWidget::pane {background:white;border:1px solid #dfe7de;border-radius:9px;}
QTabBar::tab {background:transparent;padding:13px 21px;color:#6a8070;border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#2d7353;border-bottom:2px solid #4d9571;}
QTabBar::tab:hover {background:#edf4ec;}
QDialog {background:#f3f6f2;}
QCheckBox {spacing:9px;}
QCheckBox::indicator {width:17px;height:17px;}
QFrame#Panel[updateAvailable="true"] {background:#fff7f7;border:2px solid #dd5c68;border-radius:11px;}
QLabel#GameUpdateBadge {color:#b82439;background:transparent;border:0;font-weight:600;}
'''

class PageReveal(QWidget):
    """Animate a viewport snapshot so the live page layout never moves."""
    def __init__(self, viewport, direction):
        snapshot=viewport.grab()
        super().__init__(viewport)
        self.snapshot=snapshot;self.direction=direction;self.progress=0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(viewport.rect())
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(210);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self.dismiss)

    def frame(self, value):
        self.progress=float(value);self.update()

    def dismiss(self):
        self.animation.stop();self.hide();self.deleteLater()

    def paintEvent(self, event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),theme_color(self,'#f3f6f4'))
        painter.setOpacity(0.28+0.72*self.progress)
        painter.drawPixmap(QPointF(0,self.direction*17*(1-self.progress)),self.snapshot)


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
        gradient=QLinearGradient(0,0,self.width(),self.height());gradient.setColorAt(0,theme_color(self,'#e6efe7'));gradient.setColorAt(1,theme_color(self,'#cbded0'));painter.fillRect(self.rect(),gradient)
        if self.pixmap and not self.pixmap.isNull():
            scaled=self.pixmap.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation);painter.drawPixmap((self.width()-scaled.width())//2,(self.height()-scaled.height())//2,scaled)
            if self.layout():
                shade=QLinearGradient(0,0,self.width(),0)
                for position,alpha in ((0,245),(.62,215),(1,10)):
                    color=theme_color(self,'#eff6ef');color.setAlpha(alpha);shade.setColorAt(position,color)
                painter.fillRect(self.rect(),shade)
        elif self.caption:
            painter.setPen(theme_color(self,'#607d68'));painter.drawText(self.rect(),Qt.AlignCenter,self.caption)
        else:
            painter.setPen(Qt.NoPen);painter.setBrush(theme_color(self,'#dce9d8'));painter.drawEllipse(int(self.width()*.73),30,150,150)
            painter.setBrush(theme_color(self,'#b9d0bd'));painter.drawPolygon(QPolygonF([QPointF(self.width()*.5,self.height()),QPointF(self.width()*.68,75),QPointF(self.width()*.88,self.height())]))
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
        self.auto_install=QCheckBox('下载后安全解压 ZIP / 7z / TAR / GZ / BZ2 / XZ（不运行程序）')
        self.auto_install.setChecked(bool(self.install_config.get('enabled', True)))
        lay.addWidget(self.auto_install)
        if self.install_config.get('executable'):
            lay.addWidget(label('可选启动项：'+self.install_config['executable'],'Muted'))
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
        if self.is_p2p and not self.p2p_notice.isChecked():
            self.error.setText('请先勾选 P2P 上传说明，再开始下载。');self.p2p_notice.setFocus();return
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
        super().__init__();self.store=store or StateStore();self.setWindowTitle('PlayHub · 游戏启动器 '+VERSION+' Alpha');self.resize(1380,920);self.setMinimumSize(1000,690);self.apply_theme(self.store.data.get('theme_color','blue'));self.setWindowIcon(QIcon(str(resource_dir()/'assets/playhub.ico')))
        self.manager=DownloadManager(self.store,self);self.manager.notification.connect(self.notify);self.manager.changed.connect(self.queue_changed)
        self.cloud=CloudBridge(self);self.cloud.authorized.connect(self.cloud_authorized);self.cloud.error.connect(self.cloud_error);self.cloud.status.connect(self.cloud_status);self.cloud.needs_login.connect(self.cloud_needs_login);self.cloud.selection_complete.connect(self.cloud_selection_complete)
        self.pending_cloud={};self.cloud_busy=set();self.cloud_authorized_files={}
        self.provider_states={k:'尚未验证登录' for k in PROVIDERS};self.route='home';self.jobs=[];self.dialogs=[];self.stop_metadata=threading.Event();self.catalog=self.load_catalog()
        self.root=QWidget();self.root.setObjectName('Main');self.setCentralWidget(self.root);outer=QHBoxLayout(self.root);outer.setSpacing(0);outer.setContentsMargins(0,0,0,0)
        sidebar=QWidget();sidebar.setObjectName('Sidebar');sidebar.setFixedWidth(210);sl=QVBoxLayout(sidebar);sl.setContentsMargins(18,32,18,24);sl.setSpacing(8);sl.addWidget(label('P  PlayHub','Brand'));sl.addWidget(label('PLAY SOMETHING GOOD','Eyebrow'));sl.addSpacing(32);self.navs={}
        for key,text in [('home','主页'),('store','游戏商店'),('library','我的游戏库'),('downloads','下载管理')]:
            w=button(text,lambda checked=False,k=key:self.show_page(k));w.setObjectName('Nav');w.setCheckable(True);self.navs[key]=w;sl.addWidget(w)
        self.library_update_dot=QLabel(self.navs['library']);self.library_update_dot.setObjectName('LibraryUpdateDot')
        self.library_update_dot.setFixedSize(9,9);self.library_update_dot.move(151,19)
        self.library_update_dot.setStyleSheet('background:#d63245;border:1px solid white;border-radius:4px;')
        self.library_update_dot.setAttribute(Qt.WA_TransparentForMouseEvents);self.library_update_dot.hide()
        self.library_check_message='尚未联网检查；当前按已缓存的商店版本比对。'
        self.catalog_checked_monotonic=None;self.library_monitor_started=False
        self._library_update_signature=None
        sl.addStretch(1)
        for key,text in [('profile','用户设置'),('settings','设置与网盘登录'),('updates','启动器更新'),('about','关于')]:
            w=button(text,lambda checked=False,k=key:self.show_page(k));w.setObjectName('Nav');w.setCheckable(True);self.navs[key]=w;sl.addWidget(w)
        self.user_label=label(self.store.data['name'] or '新玩家','Muted');sl.addSpacing(15);sl.addWidget(self.user_label);outer.addWidget(sidebar)
        area=QVBoxLayout();area.setContentsMargins(30,24,30,16);area.setSpacing(18);outer.addLayout(area,1)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索游戏、类型或开发者');self.search.returnPressed.connect(lambda:self.show_page('store'));area.addLayout(row(self.search,button('新建下载',self.new_download),button('下载队列',lambda:self.show_page('downloads'))))
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);area.addWidget(self.scroll,1);self.status=label('Alpha 测试版 · 本地档案 · 安全解压需确认 · 不自动执行程序','Muted');area.addWidget(self.status)
        self.refresh_timer=QTimer(self);self.refresh_timer.timeout.connect(self.refresh_downloads);self.refresh_timer.start(700)
        self.refresh_library_indicators();self.show_page('home')
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
        self.refresh_library_indicators()
        previous=self.route
        for overlay in self.scroll.viewport().findChildren(PageReveal):overlay.dismiss()
        self.route=key
        for k,w in self.navs.items():w.setChecked(k==key)
        body=QWidget();body.setObjectName('PageBody');lay=QVBoxLayout(body);lay.setSpacing(18);lay.setContentsMargins(0,6,0,20);self.body=body;self.page_layout=lay
        functions={'home':self.home_page,'store':self.store_page,'library':self.library_page,'downloads':self.download_page,'settings':self.settings_page,'profile':self.profile_page,'updates':self.updates_page,'about':self.about_page}
        functions.get(key,self.home_page)(lay);lay.addStretch(1);lay.setSizeConstraint(QLayout.SetMinAndMaxSize)
        # Build children before setWidget: Qt otherwise leaves late-created children hidden
        # until the event loop runs, so a synchronous viewport snapshot is blank.
        self.scroll.setWidget(body);body.show();body.ensurePolished();lay.activate()
        if key!=previous and self.isVisible() and self.motion_enabled():
            lay.activate()
            order=list(self.navs)
            direction=-1 if key in order and previous in order and order.index(key)<order.index(previous) else 1
            reveal=PageReveal(self.scroll.viewport(),direction);reveal.show();reveal.raise_();reveal.animation.start()

    def apply_theme(self,value):
        theme=normalize_theme(value);self.setProperty('themeColor',theme)
        self.setStyleSheet(themed_stylesheet(STYLE,theme))
        for artwork in self.findChildren(Artwork):artwork.update()

    def set_theme_color(self,value):
        theme=normalize_theme(value);self.store.data['theme_color']=theme;self.store.save();self.apply_theme(theme)
        self.notify('主题色已保存，立即生效。')

    def motion_enabled(self):
        return self.store.data.get('interface_motion',True) and system_motion_enabled()

    def set_interface_motion(self, enabled):
        self.store.data['interface_motion']=enabled;self.store.save()
        if not enabled:
            for overlay in self.scroll.viewport().findChildren(PageReveal):overlay.dismiss()

    def heading(self,lay,title,desc='',eyebrow='YOUR NEXT ADVENTURE'):
        lay.addWidget(label(eyebrow,'Eyebrow'));lay.addWidget(label(title,'Title'))
        if desc:lay.addWidget(label(desc,'Muted'))

    def section(self,lay,title,action='',callback=None):
        text=label(title,'SectionTitle');text.setStyleSheet('font-size:18px;font-weight:600;');bar=row(text,1)
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

    def refresh_library_indicators(self):
        states=[(game,update_status(game,self.catalog)) for game in self.store.data['library']]
        available=[item for item,state in states if state['available']]
        signature=tuple((game.get('id'),state['code'],state['current'],state['latest'],game.get('executable',''),game.get('name','')) for game,state in states)
        changed=signature!=self._library_update_signature;self._library_update_signature=signature
        self.library_update_dot.setVisible(bool(available));self.library_update_dot.raise_()
        tip=(str(len(available))+' 款游戏有新版本，进入游戏库查看') if available else '游戏库暂无已确认的新版本'
        self.navs['library'].setToolTip(tip);self.navs['library'].setAccessibleName('我的游戏库；'+tip)
        self.library_update_dot.setToolTip(tip)
        return changed

    def start_library_monitor(self):
        if self.library_monitor_started:return
        self.library_monitor_started=True
        self.library_update_timer=QTimer(self);self.library_update_timer.setInterval(15*60*1000)
        self.library_update_timer.timeout.connect(lambda:self.check_library_updates(quiet=True))
        self.library_update_timer.start()
        QTimer.singleShot(800,lambda:self.check_library_updates(quiet=True))

    def check_library_updates(self,quiet=False,force=True):
        last=getattr(self,'catalog_attempt_monotonic',None)
        if not force and last is not None and time.monotonic()-last<300:return
        self.refresh_catalog(quiet=quiet)

    def refresh_open_details(self):
        for dialog in list(self.dialogs):
            if dialog.objectName()=='GameDetail' and hasattr(dialog,'detail_fallback'):
                self.populate_game_detail(dialog)

    def register_library_version(self,game):
        version,ok=QInputDialog.getText(self,'登记本地游戏版本','仅在你已手动安装/更新后填写；这不会检查文件或安装游戏。',text=str(game.get('installed_version') or game.get('tracked_version') or game.get('version') or ''))
        if not ok or not version.strip():return
        version=version.strip()
        if len(version)>80 or any(ord(c)<32 for c in version):self.notify('版本号过长或含无效字符。');return
        if QMessageBox.question(self,'确认本地版本','确认本地游戏已安装为 '+version+'？这里只登记记录，不下载、不覆盖文件。',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        game.update(installed_version=version,tracked_version=version,version=version,version_source='user_confirmed')
        self.store.save();self.refresh_library_indicators();self.refresh_open_details()
        if self.route in ('library','home'):self.show_page(self.route)
        self.notify('已按你的确认登记本地版本：'+version)

    def library_installed(self,game):
        path=game.get('executable','');return bool(path and Path(path).is_file() and Path(path).suffix.lower()=='.exe')

    def game_tasks(self,game):
        return [task for task in self.manager.tasks if task.get('install',{}).get('game_id')==game['id'] or task.get('title')==game['name']]

    def cards(self,lay,games,library=False,columns=3):
        if not games:
            self.empty(lay,'这里还没有游戏' if library else '等待新世界上架','导入本地游戏，或从商店收藏你喜欢的作品。' if library else '商店只展示管理员发布的真实作品；当前没有符合条件的游戏。','导入本地游戏' if library else '刷新商店',self.import_game if library else self.refresh_catalog);return
        grid=QGridLayout();grid.setSpacing(16)
        for i,original in enumerate(games):
            g=latest_details(original,self.catalog) if library else original
            box,bl=panel();box.setProperty('gameId',original['id']);bl.setContentsMargins(12,12,12,14);bl.setSpacing(10)
            bl.addWidget(self.artwork(g.get('cover',''),138));bl.addWidget(label(original.get('custom_name') or original['name'] if library else g['name'],'SectionTitle'))
            bl.addLayout(row(label(g.get('category') or '未分类','Muted'),1,label('Android' if g.get('platform')=='android' else 'Windows','Muted')))
            if library:
                check=update_status(original,self.catalog);box.setProperty('updateAvailable',check['available'])
                badge=label(check['text'],'GameUpdateBadge' if check['available'] else 'Muted');badge.setProperty('gameId',original['id']);bl.addWidget(badge)
                if check['available']:
                    open_update=button('查看新版本',lambda checked=False,item=original:self.detail(item),True)
                    open_update.setObjectName('ViewGameUpdate');bl.addWidget(open_update)
                tasks=[t for t in self.game_tasks(original) if t['status']!='complete'];state=self.task_status(tasks[-1]) if tasks else '已安装' if self.library_installed(original) else '已收藏 · 尚未安装';bl.addWidget(label(state,'Muted'))
                if tasks:bl.addWidget(self.task_bar(tasks[-1]))
                installed=self.library_installed(original)
                launch=button('开始游玩' if installed else '点击下载',lambda checked=False,item=original:self.launch_game(item) if self.library_installed(item) else self.download_game(latest_details(item,self.catalog)),True)
                launch.setProperty('libraryPrimaryAction',True)
                launch.setEnabled(installed or bool(g.get('source') or g.get('sources')))
                if not installed and not launch.isEnabled():launch.setToolTip('未安装，且管理员尚未配置下载来源。')
                bl.addWidget(launch);bl.addLayout(row(button('启动设置',lambda checked=False,item=original:self.set_executable(item)),button('详情',lambda checked=False,item=original:self.detail(item)),button('管理',lambda checked=False,item=original:self.manage_library_game(item))))
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
        tools.addStretch();sort=QComboBox();sort.setObjectName('StoreSort');sort.addItem('综合推荐','recommended');sort.addItem('名称排序','name');sort.addItem('开发者排序','developer');sort.setCurrentIndex(max(0,sort.findData(self.store_sort)));sort.currentIndexChanged.connect(lambda index:self.set_view_filter('store_sort',sort.itemData(index),'store'));tools.addWidget(sort);lay.addLayout(tools)
        query=self.search.text().strip().casefold();games=[g for g in self.catalog if (self.store_filter=='全部' or (g.get('category') or '未分类')==self.store_filter) and (not query or query in ' '.join(str(g.get(k,'')) for k in ('name','summary','category','developer')).casefold())]
        if self.store_sort=='recommended':games=[g for g in self.recommended_games() if g in games]
        else:games.sort(key=lambda game:str(game.get(self.store_sort,'')).casefold())
        content=QHBoxLayout();content.setSpacing(18);main=QVBoxLayout();main.setSpacing(15);self.cards(main,games);main.addWidget(label('已展示 '+str(len(games))+' 款游戏 · 仅显示真实上架内容','Muted'));main.addStretch();content.addLayout(main,4)
        aside=QWidget();aside.setMinimumWidth(210);aside.setMaximumWidth(260);al=QVBoxLayout(aside);al.setContentsMargins(0,0,0,0);al.setSpacing(16);rank,rl=panel();rl.setContentsMargins(17,20,17,20);rl.addWidget(label('本周推荐榜','SectionTitle'));rl.addWidget(label('管理员精选 · 非玩家评分','Muted'));ids=self.catalog_meta.get('merchandising',{}).get('weekly_ids',[]);weekly=[g for ident in ids for g in self.catalog if g['id']==ident][:5]
        for index,game in enumerate(weekly):
            line=QHBoxLayout();line.addWidget(label(str(index+1).zfill(2),'Muted'));image=self.artwork(game.get('cover',''),45,'');image.setFixedWidth(46);line.addWidget(image);entry=button(game['name'],lambda checked=False,item=game:self.detail(item));entry.setMinimumWidth(0);line.addWidget(entry,1);rl.addLayout(line)
        if not weekly:rl.addSpacing(12);rl.addWidget(label('本周推荐尚未发布','Muted'));rl.addWidget(label('新作品上架后，由管理员选择展示。','Muted'));rl.addSpacing(24)
        al.addWidget(rank);create,cl=panel();cl.addWidget(label('你的作品，也值得被看见','SectionTitle'));cl.addWidget(label('原创或已获分发授权的游戏，审核通过后才能上架。','Muted'));cl.addWidget(button('创作与投稿说明',self.online_unavailable));al.addWidget(create);al.addWidget(button('刷新商店清单',self.refresh_catalog));al.addStretch();content.addWidget(aside,1);lay.addLayout(content)

    def set_view_filter(self,name,value,route):
        if getattr(self,name,None)==value:return
        setattr(self,name,value)
        # Rebuilding synchronously inside QComboBox's signal destroys the emitting
        # combobox before its native popup/event handler returns (intermittent crash).
        self._pending_view_route=route
        if getattr(self,'_view_rebuild_pending',False):return
        self._view_rebuild_pending=True
        QTimer.singleShot(0,self.flush_view_filter)

    def flush_view_filter(self):
        self._view_rebuild_pending=False
        route=getattr(self,'_pending_view_route',None)
        if route and self.route==route:self.show_page(route)

    def download_game(self,game,source=None):
        sources=[item for item in game.get('sources',[]) if isinstance(item,dict) and item.get('url')]
        selected=source or (sources[0] if sources else {'url':game.get('source',''),'type':game.get('source_type','auto')})
        if not selected.get('url'):self.notify('管理员尚未配置此游戏的下载来源。');return
        configured=next((item for item in self.catalog if item['id']==game['id']),game);executable=configured.get('executable','')
        if executable and Path(executable).is_absolute():executable=''
        install={'game_id':game['id'],'name':game['name'],'executable':executable,'enabled':bool(configured.get('auto_install',True)),
                 'version':str(game.get('version') or ''),'catalog_game':catalog_snapshot(game)}
        self.resolve(selected['url'],selected.get('type','auto'),selected.get('password',''),title=game['name'],install=install)

    def detail(self,g):
        dlg=QDialog(self);dlg.setObjectName('GameDetail');dlg.resize(1110,810);dlg.setMinimumSize(880,640)
        dlg.detail_fallback=dict(g);dlg.detail_return_route=self.route
        outer=QVBoxLayout(dlg);outer.setContentsMargins(25,22,25,22);outer.setSpacing(16)
        outer.addLayout(row(button('返回游戏库' if self.route=='library' else '关闭详情',dlg.accept),1,label('GAME DETAIL / PLAYHUB','Eyebrow')))
        dlg.detail_scroll=QScrollArea();dlg.detail_scroll.setWidgetResizable(True);outer.addWidget(dlg.detail_scroll,1)
        self.populate_game_detail(dlg);self.dialogs.append(dlg)
        dlg.finished.connect(lambda:self.dialogs.remove(dlg) if dlg in self.dialogs else None)
        dlg.setAttribute(Qt.WA_DeleteOnClose);dlg.open()
        if self.library_monitor_started:QTimer.singleShot(0,lambda:self.check_library_updates(quiet=True,force=False))

    def populate_game_detail(self,dlg):
        fallback=dlg.detail_fallback
        local=next((item for item in self.store.data['library'] if item['id']==fallback['id']),None)
        g=latest_details(local or fallback,self.catalog)
        check=update_status(local,self.catalog) if local else None
        dlg.setWindowTitle(g['name']+' · 游戏详情');dlg.setProperty('catalogVersion',str(g.get('version','')))
        scroll=dlg.detail_scroll;scroll_position=scroll.verticalScrollBar().value()
        old_tabs=scroll.findChild(QTabWidget,'GameDetailTabs');tab_index=old_tabs.currentIndex() if old_tabs else 0
        body=QWidget();body.setObjectName('PageBody');layout=QVBoxLayout(body);layout.setSpacing(18)
        if local:
            status_label=label(check['text'],'GameUpdateBadge' if check['available'] else 'Notice')
            status_label.setObjectName('LibraryGameVersionStatus');layout.addWidget(status_label)
            layout.addWidget(label('已安装版本：'+(str(local.get('installed_version') or '') or '未知（未自动验证）')+'；'+check['basis']+'：'+(check['current'] or '未知')+'。'+self.library_check_message,'Muted'))
        top=QHBoxLayout();top.setSpacing(20);visual=QVBoxLayout();cover=self.artwork(g.get('cover',''),320);visual.addWidget(cover);screenshots=g.get('screenshots',[])
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
        download=button('下载新版本（保留旧版）' if check and check['available'] else '选择文件并下载',lambda:self.download_game(g,choices.currentData() if sources else None),True);download.setObjectName('DownloadGameVersion');download.setEnabled(bool(sources or g.get('source')));il.addWidget(download)
        if local:
            il.addWidget(button('登记已手动安装的版本',lambda:self.register_library_version(local)))
        for title,value in [('游戏版本',g.get('version') or '尚未填写'),('运行平台','Android' if g.get('platform')=='android' else 'Windows'),('游戏分类',g.get('category') or '未分类'),('来源数量',str(len(sources) or int(bool(g.get('source')))))]:il.addLayout(row(label(title,'Muted'),1,label(str(value))))
        il.addWidget(label('下载前先选择文件与目录。安全解压仅按配置和用户确认执行，完成后不会自动运行程序。','Notice'));il.addStretch();top.addWidget(info,1);layout.addLayout(top);tabs=QTabWidget();tabs.setObjectName('GameDetailTabs')
        for title,text in [('介绍',g.get('description') or g.get('summary') or '开发者尚未提供详细介绍。'),('系统需求',g.get('system_requirements') or '开发者尚未提供系统配置要求，请在下载前确认设备兼容性。'),('更新日志',g.get('changelog') or '作者尚未填写更新日志。'),('作者的话',g.get('author_notes') or '作者尚未留下寄语。'),('评论与评分','评论与评分尚未上线。当前没有线上评价数据；不会展示示例评分、虚构评论或未验证的玩家数量。')]:
            page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(24,22,24,22);page_layout.addWidget(label(title,'SectionTitle'));page_layout.addWidget(label(str(text),'Muted'));page_layout.addStretch();tabs.addTab(page,title)
        tabs.setMinimumHeight(190);tabs.setCurrentIndex(min(tab_index,tabs.count()-1));layout.addWidget(tabs)
        scroll.setWidget(body);body.show();scroll.verticalScrollBar().setValue(scroll_position)

    def detail_add_library(self,game,control):
        # add_library refreshes the detail body; its old button may be deleted.
        self.add_library(game)

    def add_library(self,g):
        if any(x.get('id')==g['id'] for x in self.store.data['library']):self.notify('已经在你的游戏库中。');return
        latest=latest_details(g,self.catalog)
        self.store.data['library'].append({**catalog_snapshot(latest),'executable':'','tracked_version':str(latest.get('version') or '')})
        self.store.save();self.refresh_library_indicators();self.refresh_open_details();self.notify('已加入我的游戏库。')

    def library_page(self,lay):
        self.heading(lay,'我的游戏库','你的世界，在这里相遇。已收藏 '+str(len(self.store.data['library']))+' 款游戏。','YOUR COLLECTION')
        check_button=button('正在检查…' if getattr(self,'catalog_loading',False) else '检查游戏更新',lambda:self.check_library_updates())
        check_button.setObjectName('CheckLibraryUpdates');check_button.setEnabled(not getattr(self,'catalog_loading',False))
        lay.addLayout(row(button('导入本地游戏',self.import_game),check_button,1))
        status_label=label(self.library_check_message,'Muted');status_label.setObjectName('LibraryCheckStatus');lay.addWidget(status_label)
        tabs=QHBoxLayout()
        for name in ('全部游戏','有更新','已安装','下载中'):
            control=button(name,lambda checked=False,value=name:self.set_view_filter('library_filter',value,'library'));control.setObjectName('Filter');control.setCheckable(True);control.setChecked(self.library_filter==name);tabs.addWidget(control)
        tabs.addStretch();lay.addLayout(tabs)
        games=[game for game in self.store.data['library'] if self.library_filter=='全部游戏' or (self.library_filter=='有更新' and update_status(game,self.catalog)['available']) or (self.library_filter=='已安装' and self.library_installed(game)) or (self.library_filter=='下载中' and any(t['status'] in ('queued','downloading','installing','paused','auth_required') for t in self.game_tasks(game)))]
        if not games and self.library_filter=='有更新':
            self.empty(lay,'当前没有已确认的新版本','未知版本的游戏请先在管理中登记本地版本；检查失败时保留缓存结果。')
        else:self.cards(lay,games,library=True,columns=3)
        lay.addWidget(label('启动后及每15分钟检查已关联商店的游戏。仅提示更新，不自动覆盖游戏或存档；实际启动项存在时才显示已安装。','Muted'))

    def manage_library_game(self, game):
        menu=QMessageBox(self);menu.setWindowTitle('管理游戏');menu.setTextFormat(Qt.PlainText);menu.setText(game['name'])
        rename=menu.addButton('改名',QMessageBox.ActionRole)
        folder=menu.addButton('打开游戏目录',QMessageBox.ActionRole)
        version_button=menu.addButton('登记本地版本',QMessageBox.ActionRole)
        remove=menu.addButton('从游戏库移除',QMessageBox.ActionRole)
        menu.addButton(QMessageBox.Cancel)
        location=game.get('install_directory') or (str(Path(game['executable']).parent) if game.get('executable') else '')
        folder.setEnabled(bool(location and Path(location).is_dir()))
        menu.exec();chosen=menu.clickedButton()
        if chosen==rename:
            name,ok=QInputDialog.getText(self,'修改库内名称','新名称：',text=game['name'])
            if ok and name.strip():
                game['name']=name.strip()[:100];game['custom_name']=game['name'];self.store.save();self.refresh_library_indicators();self.show_page(self.route)
        elif chosen==version_button:self.register_library_version(game)
        elif chosen==folder:QDesktopServices.openUrl(QUrl.fromLocalFile(location))
        elif chosen==remove and QMessageBox.question(self,'移除游戏条目','仅移除本地游戏库记录，保留游戏文件、下载任务和商店条目。确定移除？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self.store.data['library']=[item for item in self.store.data['library'] if item['id']!=game['id']]
            self.store.save();self.refresh_library_indicators();self.refresh_open_details();self.show_page(self.route);self.notify('已移除游戏条目，文件未改动。')

    def import_game(self):
        exe,_=QFileDialog.getOpenFileName(self,'选择你信任的游戏启动程序','','Windows 程序 (*.exe)')
        if not exe:return
        name,ok=QInputDialog.getText(self,'导入游戏','显示名称：',text=Path(exe).stem)
        if ok and name.strip():self.store.data['library'].append({'id':uuid.uuid4().hex,'name':name.strip(),'executable':exe,'source':'','local_only':True});self.store.save();self.show_page('library')

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
        dlg=QDialog(self);dlg.setWindowTitle('新建下载 · 选择来源');dlg.resize(640,410);l=QVBoxLayout(dlg);l.setContentsMargins(24,24,24,24);l.setSpacing(14);l.addWidget(label('添加下载来源','Title'));kind=QComboBox();kinds=[('自动识别','auto'),('HTTPS 文件直链','direct'),('GitHub Release 附件清单','github'),('PlayHub 多文件清单 JSON','manifest'),('BitTorrent 种子 / 磁力 P2P','torrent'),('坚果云','nutstore'),('MediaFire 公开分享','mediafire'),('百度网盘','baidu'),('夸克网盘','quark'),('蓝奏云 / lanzoui','lanzou')];[kind.addItem(t,k) for t,k in kinds];url=QLineEdit();url.setPlaceholderText('HTTPS 分享、文件直链、magnet:? 或本地 .torrent');pwd=QLineEdit();pwd.setPlaceholderText('分享提取码（如需要）');pwd.setEchoMode(QLineEdit.Password);l.addWidget(kind);l.addLayout(row(url,button('选种子',lambda:self.pick_torrent(url))));l.addWidget(pwd);l.addWidget(label('多文件会先列出清单。直链单文件和 ZIP/APK 不提供虚假的包内勾选；网盘仅使用官方授予的访问权限。','Notice'))
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
        if is_mediafire_host(host):return 'mediafire'
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
        if kind=='mediafire':
            parent=next((d for d in reversed(self.dialogs) if d.isVisible() and d.objectName()=='GameDetail'),self)
            def done(result):
                entry,session=result
                from shiboken6 import isValid
                if isValid(parent):self.choose_files([entry],title=title or 'MediaFire 下载',web=session,install=install,parent=parent)
            def failed(message):
                self.notify(message)
                from shiboken6 import isValid
                if isValid(parent):QMessageBox.warning(parent,'MediaFire 来源未就绪',message)
            self.job(lambda:resolve_mediafire(url),done,failed);return
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
        if kind=='torrent' and url.lower().startswith('magnet:'):
            self.resolve_magnet('magnet:'+url[7:], title, install);return
        if kind=='torrent':
            def work():
                if url.startswith('https:'):
                    entry=direct_entry(url);entry.path='metadata-'+uuid.uuid4().hex+'.torrent';result=__import__('playhub.http_engine',fromlist=['download_file']).download_file(entry,self.store.root/'torrent-cache',threading.Event());p=result['path']
                else:p=url
                info=self.manager.p2p.load_torrent(p);return self.manager.p2p.entries(info),p,''
            self.job(work,lambda result:self.choose_files(result[0],title=title,torrent=result[1],magnet=result[2],install=install));return
        def discover():
            from .github_delivery import public_release_url, resolve_public_asset
            if kind=='manifest':return manifest_entries(url)
            if public_release_url(url):
                try:return [resolve_public_asset(url)]
                except DownloadError:pass  # Without a trusted digest, only the origin can be used.
            return [direct_entry(url)]
        self.job(discover,lambda files:self.choose_files(files,title=title,install=install))

    def resolve_magnet(self, url, title, install):
        from shiboken6 import isValid
        if getattr(self,'magnet_wait',None) is not None:
            self.magnet_wait.raise_();self.magnet_wait.activateWindow();return
        parent=next((d for d in reversed(self.dialogs) if d.isVisible() and d.objectName()=='GameDetail'),self)
        dlg=QDialog(parent);dlg.setWindowTitle('正在读取磁力链接');dlg.setWindowModality(Qt.WindowModal)
        layout=QVBoxLayout(dlg);layout.addWidget(label('正在连接做种节点，获取文件列表。尚未开始下载游戏文件。'))
        bar=QProgressBar();bar.setRange(0,0);layout.addWidget(bar)
        peer_status=label('同机测试无需等待公网发现：可手动填写做种端的 BT 监听端口。','Muted');layout.addWidget(peer_status)
        def add_peer():
            endpoint,ok=QInputDialog.getText(dlg,'指定做种节点','同机填 127.0.0.1:端口；局域网填做种端 IP:端口。\n端口见 qBittorrent「选项 → 连接」，不是 Web UI 端口。')
            if not ok or not endpoint.strip():return
            try:
                self.manager.p2p.add_peer_hint(url,endpoint)
                peer_status.setText('已加入直连节点，正在尝试。此地址只保存在本次运行的内存中。')
            except DownloadError as exc:peer_status.setText(str(exc))
        layout.addLayout(row(button('指定做种节点',add_peer),1,button('取消',dlg.reject)));dlg.resize(520,240)
        stop=threading.Event();dlg.rejected.connect(stop.set);self.stop_metadata=stop;self.magnet_wait=dlg
        def work():
            info,cache=self.manager.p2p.metadata(url,stop,timeout=45)
            return self.manager.p2p.entries(info),cache
        dlg.destroyed.connect(lambda *_:stop.set())
        def finish():
            self.magnet_wait=None
            if isValid(dlg):dlg.accept();dlg.deleteLater()
        def done(result):
            finish()
            if not stop.is_set() and isValid(parent):self.choose_files(result[0],title=title,torrent=result[1],magnet=url,install=install,parent=parent)
        def failed(message):
            finish()
            if stop.is_set():self.notify('已取消读取磁力文件列表。');return
            self.notify(message);QMessageBox.warning(parent,'未能获取磁力文件列表',message)
        dlg.open();self.job(work,done,failed)

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
        task=next((t for t in self.manager.tasks if t['id']==ident),None)
        if task:self.download_added(task)

    def choose_files(self,files,title='',torrent='',magnet='',web=None,install=None,parent=None):
        dlg=SelectionDialog(files,self.store,p2p=bool(torrent),parent=parent or self,install=install)
        if dlg.exec()==QDialog.Accepted:
            task=self.manager.add(dlg.selected(),dlg.path.text(),title,torrent,magnet,web,install={**(install or {}),'enabled':dlg.auto_install.isChecked()})
            self.download_added(task)

    def download_added(self, task):
        detail=next((d for d in reversed(self.dialogs) if d.isVisible() and d.objectName()=='GameDetail'),None)
        if detail is None:
            self.show_page('downloads');self.raise_();self.activateWindow();return
        dialog=QMessageBox(detail)
        dialog.setWindowTitle('下载提醒');dialog.setTextFormat(Qt.PlainText)
        title={'queued':'游戏已加入下载队列','complete':'游戏下载完成了','error':'游戏已加入下载，任务执行失败'}.get(task['status'],'游戏开始下载了')
        dialog.setText(title);dialog.setInformativeText(task['title']+'。关闭本提示不会取消下载。')
        view=dialog.addButton('查看下载游戏',QMessageBox.AcceptRole)
        cancel=dialog.addButton('取消',QMessageBox.RejectRole)
        dialog.setEscapeButton(cancel);dialog.setWindowModality(Qt.WindowModal)
        detail.raise_();detail.activateWindow();dialog.exec()
        if dialog.clickedButton()==view:
            detail.accept();self.download_filter='全部任务';self.show_page('downloads');self.raise_();self.activateWindow()

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
        library_changed=self.refresh_library_indicators()
        if library_changed:
            self.refresh_open_details()
            if self.route in ('home','library'):
                self.show_page(self.route);return
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
            if task['status']=='installing':actions.addWidget(button('取消解压',lambda checked=False,i=task['id']:self.manager.pause(i)))
            elif task['status'] in ('downloading','queued'):actions.addWidget(button('暂停',lambda checked=False,i=task['id']:self.manager.pause(i)))
            elif task['status']=='auth_required' and task['id'] in self.pending_cloud:actions.addWidget(button('登录并继续',lambda checked=False,i=task['id']:self.resume_cloud_task(i)))
            elif task['status'] in ('paused','error','auth_required'):actions.addWidget(button('继续 / 重试',lambda checked=False,i=task['id']:self.manager.resume(i)))
            if task['status']=='complete' and task.get('results'):
                extract=button('解压已下载文件',lambda checked=False,i=task['id']:self.extract_downloaded_task(i))
                extract.setObjectName('ExtractDownloadedTask');actions.addWidget(extract)
            if task.get('torrent') and task['status'] not in ('complete','installing'):
                actions.addWidget(button('指定做种节点',lambda checked=False,i=task['id']:self.specify_task_peer(i)))
            delete_button=button('删除任务',lambda checked=False,i=task['id']:self.delete_task(i));delete_button.setObjectName('DeleteDownloadTask');delete_button.setEnabled(task['status'] not in ('downloading','installing'));actions.addWidget(delete_button);actions.addWidget(button('打开目录',lambda checked=False,p=task['directory']:QDesktopServices.openUrl(QUrl.fromLocalFile(p))));bl.addLayout(actions);self.download_box.addWidget(box)
        if not tasks:self.empty(self.download_box,'下载队列为空' if not self.manager.tasks else '当前分类暂无任务','选择游戏或添加你有权访问的下载来源。','新建下载',self.new_download)

    def specify_task_peer(self, ident):
        task=next((t for t in self.manager.tasks if t['id']==ident),None)
        if not task or not task.get('torrent'):return
        endpoint,ok=QInputDialog.getText(self,'指定做种节点','填写做种端的 IP:BT监听端口。\n同机使用 127.0.0.1:端口；不是 Web UI 端口。')
        if not ok or not endpoint.strip():return
        try:
            magnet=task.get('magnet','')
            if not magnet:
                import libtorrent as lt
                magnet=lt.make_magnet_uri(self.manager.p2p.load_torrent(task['torrent']))
            self.manager.p2p.add_peer_hint(magnet,endpoint)
            self.notify('已加入直连节点。运行中任务将尝试连接；暂停或失败的任务请点继续。节点不保存到磁盘。')
        except DownloadError as exc:self.notify(str(exc))

    def resume_cloud_task(self,ident):
        context=self.pending_cloud.get(ident)
        if not context:self.notify('本次授权记录已结束，请重新选择来源。');return
        try:self.cloud.command(context['provider'],'continue',request_id=ident)
        except Exception as exc:self.notify(str(exc))

    def extract_downloaded_task(self,ident):
        task=next((item for item in self.manager.tasks if item['id']==ident),None)
        if not task:return
        text='校验并解压已下载的支持格式到新的 installed 子目录。不会重新下载，不覆盖已有游戏或存档，也不自动运行程序。加密包、RAR、分卷包暂不支持。是否继续？'
        if QMessageBox.question(self,'解压已有下载文件',text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:self.manager.extract_completed(ident)
        except DownloadError as exc:self.notify(str(exc))

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
        appearance=QWidget();appearance_layout=QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(20,20,20,20)
        appearance_layout.addWidget(label('主题色','SectionTitle'));themes=QComboBox();themes.setObjectName('ThemeColor')
        for title,value in THEMES:themes.addItem(title,value)
        themes.setCurrentIndex(max(0,themes.findData(normalize_theme(self.store.data.get('theme_color','blue')))))
        themes.currentIndexChanged.connect(lambda:self.set_theme_color(themes.currentData()));appearance_layout.addWidget(themes)
        appearance_layout.addWidget(label('玩家启动器默认晴蓝；切换只改变当前程序外观，不影响游戏库的更新红点。','Muted'))
        motion=QCheckBox('启用界面切换动画');motion.setChecked(self.store.data.get('interface_motion',True))
        motion.toggled.connect(self.set_interface_motion);appearance_layout.addWidget(motion)
        appearance_layout.addWidget(label('Windows 关闭动画效果时，PlayHub 也会跳过过渡。','Muted'))
        tabs.addTab(appearance,'外观')
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
        for text,value in [('源站优先，持续慢速自动切换（默认）','smart'),('仅 GitHub 源站','origin'),('下载前短测速，选择较快线路','auto'),('镜像优先，失败回退源站','mirror')]:self.github_mode.addItem(text,value)
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

    def refresh_catalog(self,quiet=False):
        if getattr(self,'catalog_loading',False):
            if not quiet:self.notify('正在检查商店与游戏版本，请稍候。')
            return
        u=self.store.data.get('catalog_url') or self.DEFAULT_CATALOG_URL
        if urlsplit(u).scheme!='https':self.notify('商店清单必须使用 HTTPS。');return
        self.catalog_attempt_monotonic=time.monotonic();self.catalog_loading=True
        self.library_check_message='正在后台检查游戏版本；现有更新提示继续保留。'
        if not quiet:self.notify(self.library_check_message)
        if self.route=='library':self.show_page('library')
        def fetch():
            data=self.validate_catalog(WebClient().json(u));path=self.store.root/'catalog-cache.json';temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,path);return data
        def done(data):
            if u!=(self.store.data.get('catalog_url') or self.DEFAULT_CATALOG_URL):
                self.catalog_loading=False;return
            self.catalog_loading=False;self.catalog_meta=data;self.catalog=data['games'];self.catalog_base=u;self.image_failed.clear()
            self.catalog_checked_monotonic=time.monotonic()
            count=sum(update_status(game,self.catalog)['available'] for game in self.store.data['library'])
            stamp=time.strftime('%H:%M:%S')
            self.library_check_message=stamp+' 检查完成；'+str(count)+' 款游戏有更新。仅提示，不自动覆盖游戏或存档。'
            self.refresh_library_indicators();self.refresh_open_details()
            if self.route in ('home','store','library'):self.show_page(self.route)
            if not quiet or count:self.notify(self.library_check_message)
        def failed(message):
            self.catalog_loading=False;self.library_check_message='检查失败，仍显示缓存结果（不是最新状态）：'+str(message)
            self.refresh_library_indicators();self.refresh_open_details()
            if self.route=='library':self.show_page('library')
            if not quiet:self.notify(self.library_check_message)
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
        self.heading(lay,'启动器更新','每一次更新，都是一次更好的出发。','KEEP MOVING FORWARD');hero,hl=panel();intro=QVBoxLayout();intro.addWidget(label('VERSION / ALPHA CHANNEL','Eyebrow'));intro.addWidget(label('当前版本 v'+VERSION+' Alpha','Title'));intro.addWidget(label(getattr(self,'update_check_status','尚未检查远程版本'),'Muted'));hl.addLayout(row(intro,1,button('检查 GitHub Releases',self.check_update,True)));lay.addWidget(hero);columns=QHBoxLayout();release,rl=panel();rl.addWidget(label('版本与下载','SectionTitle'));rl.addWidget(label('通过 GitHub 官方接口查询发布说明、附件名称、大小与可用哈希。没有发布版本或网络失败时会如实提示。','Muted'));rl.addWidget(button('选择并下载安装包',self.download_launcher_update));rl.addWidget(label('安装包遵循设置中的源站 / 短测速 / 镜像优先模式。','Notice'));rl.addStretch();columns.addWidget(release,1);security,sl=panel();sl.addWidget(label('更新与安全','SectionTitle'));sl.addWidget(label('手动检查 · 手动选择下载 · 不自动执行','Muted'));sl.addWidget(label('尚未实现可信签名更新器，不自动替换正在运行的程序。下载完成后由你决定是否运行。','Notice'));sl.addWidget(label('自动更新仍需可信签名清单、原子替换与失败回滚；当前不提供无效开关。','Muted'));sl.addStretch();columns.addWidget(security,1);lay.addLayout(columns)

    def download_launcher_update(self):
        from .github_delivery import OFFICIAL_REPOSITORY, update_files
        repo=self.store.data.get('repository') or OFFICIAL_REPOSITORY
        self.notify('正在通过 GitHub 官方 API 确认启动器附件…')
        def done(result):
            tag,_,entry,_=result
            self.choose_files([entry],title='PlayHub '+tag,install={'enabled':False})
        self.job(lambda:update_files(repo,mirror_ids=()),done)

    def check_update(self, quiet=False):
        from .github_delivery import OFFICIAL_REPOSITORY, update_files, update_version
        if getattr(self,'update_check_running',False):return
        self.update_check_running=True
        repo=self.store.data.get('repository') or OFFICIAL_REPOSITORY
        mode=self.store.data.get('github_mode','smart')
        mirrors=self.store.data.get('github_mirrors',['ghproxy']) if mode!='origin' else []
        def done(result):
            self.update_check_running=False
            tag,line,entry,verified=result
            newer=update_version(tag) > update_version(VERSION+'-alpha')
            text=('发现新版本 '+tag if newer else '没有发现比当前版本更新的发行版')+'（'+line+'）'
            if not verified:text+='。镜像结果仅供提示，下载安装包前须由 GitHub 官方 API 确认。'
            self.update_check_status=text;self.notify(text)
            if self.route=='updates':self.show_page('updates')
            if not quiet:QMessageBox.information(self,'启动器更新',text)
        def failed(message):
            self.update_check_running=False;self.update_check_status=message;self.notify(message)
            if self.route=='updates':self.show_page('updates')
        self.job(lambda:update_files(repo,mirror_ids=mirrors),done,failed)

    def online_unavailable(self):QMessageBox.information(self,'尚未上线','在线投稿、审核、评论评分的受控服务尚未部署。此 Alpha 不包含管理员写入令牌。')

    def about_page(self,lay):
        self.heading(lay,'关于 PlayHub','让好游戏，被更多人看见。','BUILT FOR PLAYERS');brand,bl=panel();bl.setContentsMargins(35,30,35,30);bl.addWidget(label('P  PlayHub','Title'));bl.addWidget(label('一个轻量、开放、属于玩家的游戏启动器。','SectionTitle'));bl.addWidget(label('收藏想玩的游戏，管理每一次下载，开启下一段冒险。','Muted'));bl.addWidget(label('v'+VERSION+' Alpha · Python + PySide6 原生桌面客户端','Eyebrow'));bl.addLayout(row(label('本地玩家档案','Muted'),label('多来源真实下载','Muted'),label('独立官方管理工具','Muted')));lay.addWidget(brand);columns=QHBoxLayout();capability,cl=panel();cl.addWidget(label('已经可以使用','SectionTitle'));cl.addWidget(label('本地昵称与游戏库、真实安装状态、文件勾选、系统目录选择、限速、暂停恢复、磁力 / 种子 P2P，以及网盘官方授权转接。','Muted'));cl.addWidget(label('ZIP 安全解压需明确配置和用户确认，不自动执行游戏。商店封面和截图由目录提供，缺失时保持真实空态。','Notice'));cl.addWidget(button('查看下载设置',lambda:self.show_page('settings')));cl.addStretch();columns.addWidget(capability,1);rights,rl=panel();rl.addWidget(label('权利与安全','SectionTitle'));rl.addWidget(label('仅使用你有权访问和分发的内容。公开玩家客户端不包含管理员令牌。网盘会话仅用于平台授予的访问权限，不绕过验证或付费限制。','Muted'));rl.addWidget(label('在线投稿审核、评论评分、可信签名自动更新尚未上线；没有虚构游戏、评分或社区记录。','Notice'));rl.addWidget(button('查看启动器更新',lambda:self.show_page('updates')));rl.addStretch();columns.addWidget(rights,1);lay.addLayout(columns)

    def closeEvent(self,event):
        if any(t['status'] in ('downloading','installing') for t in self.manager.tasks):
            if QMessageBox.question(self,'退出启动器','退出会暂停下载或取消解压并结束网盘授权会话；原压缩包与旧游戏保留，继续吗？')!=QMessageBox.Yes:event.ignore();return
        self.stop_metadata.set();self.manager.close();self.cloud.close();event.accept()
