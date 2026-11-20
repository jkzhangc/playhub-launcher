from __future__ import annotations
import json
import os
import re
import threading
import time
from pathlib import Path
from .core import DownloadError, FileEntry, hash_file, safe_target
from .sources import WebClient

class Paused(Exception):
    pass

class RateLimiter:
    def __init__(self, bytes_per_second=0):
        self.rate = bytes_per_second
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.used = 0

    def set_limit(self, rate):
        with self.lock:
            self.rate = max(0, rate)
            self.started = time.monotonic()
            self.used = 0

    def account(self, count, stop):
        with self.lock:
            if self.rate <= 0:
                return
            now = time.monotonic()
            if now > self.started + self.used / self.rate:
                self.started = now
                self.used = 0
            self.used += count
            delay = self.used / self.rate - (now - self.started)
        if delay > 0 and stop.wait(delay):
            raise Paused()


def download_file(entry: FileEntry, root: Path, stop: threading.Event,
                  limiter: RateLimiter | None = None, progress=None, web=None):
    """Download only one selected file; never execute or extract it."""
    if stop.is_set():
        raise Paused()
    if entry.provider != 'direct':
        raise DownloadError('此任务没有经过有效的直链授权解析。')
    web = web or WebClient()
    target = safe_target(root, entry.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if entry.sha256 and hash_file(target).lower() == entry.sha256.lower():
            return {'path': str(target), 'bytes': target.stat().st_size, 'sha256': entry.sha256.lower(), 'existing': True}
        raise DownloadError('目标文件已经存在。为防止覆盖，请选择其他目录或自行确认已有文件。')
    part = target.with_name(target.name + '.playhub.part')
    meta_path = target.with_name(target.name + '.playhub.resume.json')
    if part.is_symlink() or meta_path.is_symlink():
        raise DownloadError('拒绝写入符号链接。')
    meta = {}
    if part.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text('utf-8'))
        except (OSError, ValueError):
            meta = {}
    offset = part.stat().st_size if part.exists() else 0
    validator = meta.get('etag') or meta.get('last_modified')
    source_id = __import__('hashlib').sha256(entry.url.encode('utf-8')).hexdigest()
    if meta.get('source_id') != source_id or not validator or str(validator).startswith('W/'):
        offset = 0
    headers = {}
    if offset:
        headers = {'Range': f'bytes={offset}-', 'If-Range': validator}
    response = web.open(entry.url, headers=headers)
    try:
        if response.headers.get_content_type() in ('text/html', 'application/xhtml+xml'):
            raise DownloadError('下载地址返回了网页/登录页，不保存为游戏文件。')
        total = entry.size
        expected_response = int(response.headers.get('Content-Length', -1))
        if offset and response.status == 206:
            m = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not m or int(m.group(1)) != offset:
                raise DownloadError('服务器续传范围不匹配，已停止。')
            total = int(m.group(3))
            new_validator = response.headers.get('ETag') or response.headers.get('Last-Modified')
            if new_validator and new_validator != validator:
                raise DownloadError('源文件在续传时变化，已停止以避免文件混合。')
        elif response.status == 200:
            offset = 0
            if expected_response >= 0:
                total = expected_response
        elif not offset and response.status == 206:
            m = re.fullmatch(r'bytes 0-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not m:
                raise DownloadError('服务器返回了错误的下载范围。')
            total = int(m.group(2))
        else:
            raise DownloadError(f'不支持的响应状态：{response.status}')
        if entry.size >= 0 and total >= 0 and entry.size != total:
            raise DownloadError(f'下载大小与清单不符：预期 {entry.size}，来源为 {total}。')
        if entry.size >= 0:
            total = entry.size
        meta_path.write_text(json.dumps({'source_id': source_id, 'etag': response.headers.get('ETag', ''),
                                         'last_modified': response.headers.get('Last-Modified', ''),
                                         'total': total}, ensure_ascii=False), 'utf-8')
        done, received = offset, 0
        started, last = time.monotonic(), 0
        with part.open('ab' if offset else 'wb') as f:
            while True:
                if stop.is_set():
                    raise Paused()
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)
                done += len(chunk)
                if total >= 0 and done > total:
                    raise DownloadError('响应超过声明长度，已停止。')
                if limiter:
                    limiter.account(len(chunk), stop)
                now = time.monotonic()
                if progress and (now - last > 0.15):
                    progress(done, total, received / max(now - started, 0.01))
                    last = now
            f.flush()
            os.fsync(f.fileno())
        if total >= 0 and done != total:
            raise DownloadError(f'下载不完整：已收到 {done} / {total} 字节，可继续重试。')
        if expected_response >= 0 and received != expected_response:
            raise DownloadError('响应被提前中断，保留部分数据供续传。')
        digest = hash_file(part)
        if entry.sha256 and digest.lower() != entry.sha256.lower():
            raise DownloadError('SHA-256 校验不匹配。已保留隔离的部分文件，不会启动或覆盖正式目标。')
        if stop.is_set():
            raise Paused()
        # On Windows rename fails when a target appeared in the meantime; do not replace.
        if target.exists():
            raise DownloadError('目标文件在下载期间出现，已停止，未覆盖。')
        part.rename(target)
        meta_path.unlink(missing_ok=True)
        if progress:
            progress(done, total, 0)
        return {'path': str(target), 'bytes': done, 'sha256': digest, 'existing': False, 'resumed_from': offset}
    finally:
        response.close()
