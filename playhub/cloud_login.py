"""Provider-isolated official login; credentials and signed URLs stay in memory."""
from __future__ import annotations
import http.cookiejar
import json
import shutil
import uuid
from PySide6.QtCore import QObject, QProcess, Signal
from .core import DownloadError, FileEntry, resource_dir
from .sources import WebClient

PROVIDERS = {'nutstore': ('坚果云', 'https://www.jianguoyun.com/d/login'),
             'baidu': ('百度网盘', 'https://pan.baidu.com/'),
             'quark': ('夸克网盘', 'https://pan.quark.cn/'),
             'lanzou': ('蓝奏云', 'https://www.lanzou.com/')}

class CloudBridge(QObject):
    authorized = Signal(object, object, str, str)
    status = Signal(str, str)
    error = Signal(str)
    needs_login = Signal(str, str, str)
    selection_complete = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.errorOccurred.connect(lambda e: self.error.emit('网盘组件无法启动：' + self.process.errorString()))
        self.buffer = b''
        self.requests = {}

    def ensure_started(self):
        if self.process.state() != QProcess.NotRunning:
            return
        base = resource_dir()
        node = base / 'vendor' / 'node.exe'
        executable = str(node) if node.exists() else shutil.which('node')
        if not executable:
            raise DownloadError('缺少网盘授权运行组件，请使用完整发行包。')
        self.process.setProgram(executable)
        self.process.setArguments([str(base / 'tools' / 'cloud_bridge.cjs')])
        self.process.setWorkingDirectory(str(base))
        self.process.start()
        if not self.process.waitForStarted(4000):
            raise DownloadError('无法启动网盘授权组件。')

    def command(self, provider, action='login', url='', password='', purpose='download', files=None, request_id=None):
        self.ensure_started()
        ident = request_id or uuid.uuid4().hex
        self.requests[ident] = {'provider': provider, 'purpose': purpose}
        payload = {'id': ident, 'provider': provider, 'action': action, 'url': url, 'password': password}
        if files is not None:
            payload['files'] = [f.to_dict() if hasattr(f, 'to_dict') else f for f in files]
        self.process.write((json.dumps(payload) + chr(10)).encode())
        return ident

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while bytes([10]) in self.buffer:
            line, self.buffer = self.buffer.split(bytes([10]), 1)
            try:
                msg = json.loads(line)
                provider, ident, event = msg.get('provider', ''), msg.get('id', ''), msg.get('event')
                if event == 'authorized':
                    web = WebClient()
                    web.user_agent = msg.get('user_agent') or ''
                    for c in msg.get('cookies', []):
                        web.cookies.set_cookie(http.cookiejar.Cookie(0, c['name'], c['value'], None, False, c['domain'], True, c['domain'].startswith('.'), c.get('path') or '/', True, c.get('secure', True), None, True, None, None, {'HttpOnly': c.get('httpOnly', False)}, False))
                    self.authorized.emit(FileEntry(**msg['entry']), web, provider, ident)
                elif event == 'needs_login':
                    self.needs_login.emit(provider, ident, msg.get('message', '需要登录'))
                elif event == 'selection_complete':
                    self.selection_complete.emit(provider, ident)
                    self.requests.pop(ident, None)
                elif event == 'error':
                    self.error.emit(msg.get('message', '网盘请求失败。'))
                elif event in ('opened', 'busy', 'login_ready', 'progress'):
                    self.status.emit(provider, msg.get('message', '正在处理'))
                elif event in ('logged_out', 'closed'):
                    self.status.emit(provider, '已退出本次会话')
            except (ValueError, KeyError, TypeError):
                self.error.emit('网盘组件返回了无法识别的消息。')

    def close(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.closeWriteChannel()
            if not self.process.waitForFinished(3000):
                self.process.terminate()
                self.process.waitForFinished(2000)
