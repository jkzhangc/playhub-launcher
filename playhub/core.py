"""Shared models and safe local state for PlayHub."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

VERSION = '0.2.9'
USER_AGENT = 'PlayHub/' + VERSION + ' (+https://github.com/jkzhangc/playhub-launcher)'

class DownloadError(Exception):
    pass

class AuthorizationRequired(DownloadError):
    pass

@dataclass
class FileEntry:
    key: str
    path: str
    size: int = -1
    url: str = ''
    provider: str = 'direct'
    sha256: str = ''
    index: int = -1

    def to_dict(self):
        return asdict(self)


def safe_relative(value: str) -> Path:
    value = value.replace(chr(92), '/')
    if not value or value.startswith('/') or ':' in value:
        raise DownloadError('文件名必须是目录内的相对路径。')
    raw_parts = value.split('/')
    if any(x in ('', '.', '..') for x in raw_parts):
        raise DownloadError('文件路径包含不安全的层级。')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
    for part in raw_parts:
        if part.endswith((' ', '.')) or any(ord(c) < 32 or c in '<>"|?*' for c in part):
            raise DownloadError('文件名含 Windows 不支持的字符。')
        if part.split('.')[0].upper() in reserved:
            raise DownloadError('文件名属于 Windows 保留设备名。')
    return Path(*PurePosixPath(value).parts)

def safe_target(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = root / safe_relative(relative)
    try:
        target.resolve().relative_to(root)
    except ValueError as exc:
        raise DownloadError('文件路径越出了选择的目录。') from exc
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root.parent):
        raise DownloadError('不向符号链接或重解析目录写入。')
    return target

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def human_bytes(n: float) -> str:
    if n < 0:
        return '大小未知'
    for u in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if n < 1024 or u == 'TiB':
            return f'{n:.1f} {u}'
        n /= 1024
    return ''

def resource_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))

class StateStore:
    def __init__(self, root: Path | None = None):
        base = root or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PlayHub'
        base.mkdir(parents=True, exist_ok=True)
        self.root = base
        self.path = base / 'state.json'
        self.lock = threading.RLock()
        self.data = {'name': '', 'directory': str(Path.home() / 'Games' / 'PlayHub'), 'ask_directory': True,
                     'limit_mib': 0.0, 'upload_kib': 64, 'library': [], 'tasks': [], 'auto_check': True,
                     'catalog_url': 'https://raw.githubusercontent.com/jkzhangc/playhub-launcher/main/catalog/catalog.json', 'repository': 'jkzhangc/playhub-launcher', 'seed_after': False,
                     'github_mode': 'smart', 'github_mirrors': ['ghfast', 'ghproxy']}
        self.default_repository = self.data['repository']
        if self.path.exists():
            try:
                old = json.loads(self.path.read_text('utf-8'))
                if isinstance(old, dict):
                    self.data.update(old)
                    if old.get('github_mirrors') == ['ghproxy']:
                        self.data['github_mirrors'] = ['ghfast', 'ghproxy']
            except (ValueError, OSError):
                backup = base / 'state-unreadable.json'
                if not backup.exists():
                    import shutil
                    shutil.copy2(self.path, backup)
        for task in self.data.get('tasks', []):
            if task.get('status') in ('downloading', 'queued', 'resolving'):
                task['status'] = 'paused'
                task['message'] = '上次退出时中断，请继续。'

    def save(self):
        with self.lock:
            fd, tmp = tempfile.mkstemp(prefix='state-', suffix='.tmp', dir=self.root)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
