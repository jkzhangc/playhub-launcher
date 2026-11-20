"""BitTorrent is P2P: resolve metadata first, select files, then download."""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import libtorrent as lt
from .core import DownloadError, FileEntry, safe_relative, safe_target, hash_file
from .http_engine import Paused

class TorrentEngine:
    def __init__(self, cache: Path, local_only=False, upload_kib=64):
        cache.mkdir(parents=True, exist_ok=True)
        self.cache = cache
        self.local_only = local_only
        self.session = lt.session({'listen_interfaces': '127.0.0.1:0' if local_only else '0.0.0.0:0',
                                   'enable_dht': not local_only, 'enable_lsd': False,
                                   'enable_upnp': False, 'enable_natpmp': False,
                                   'upload_rate_limit': max(1, int(upload_kib)) * 1024,
                                   'alert_mask': int(lt.alert.category_t.error_notification | lt.alert.category_t.status_notification)})
        self.handles = {}
        self.lock = threading.RLock()

    @staticmethod
    def entries(info):
        fs = info.files()
        result, names = [], set()
        for i in range(fs.num_files()):
            flags = fs.file_flags(i)
            if flags & lt.file_storage.flag_symlink:
                raise DownloadError('种子包含符号链接，不下载。')
            if flags & lt.file_storage.flag_pad_file:
                continue
            path = fs.file_path(i).replace(chr(92), '/')
            safe_relative(path)
            if path.casefold() in names:
                raise DownloadError('种子包含大小写冲突路径，不下载。')
            names.add(path.casefold())
            result.append(FileEntry(str(i), path, fs.file_size(i), provider='torrent', index=i))
        if not result:
            raise DownloadError('种子没有可选择的普通文件。')
        return result

    def load_torrent(self, path):
        try:
            if Path(path).stat().st_size > 16 * 1024 * 1024:
                raise DownloadError('种子元数据超过 16 MiB。')
            info = lt.torrent_info(str(path))
            self.entries(info)
            return info
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f'无法读取种子：{e}') from e

    def metadata(self, magnet: str, stop: threading.Event, timeout=90):
        try:
            params = lt.parse_magnet_uri(magnet)
        except Exception as e:
            raise DownloadError('磁力链接格式无效。') from e
        params.save_path = str(self.cache / 'metadata')
        # Fetch metadata, not payload. No file is selected until the user confirms.
        params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
        params.flags |= lt.torrent_flags.default_dont_download | lt.torrent_flags.upload_mode
        h = self.session.add_torrent(params)
        self._connect_explicit(h, magnet)
        started = time.monotonic()
        try:
            while not h.status().has_metadata:
                if stop.wait(0.2):
                    raise Paused()
                if time.monotonic() - started > timeout:
                    raise DownloadError('磁力元数据获取超时：没有可连接节点，或网络/DHT 不可用。未开始下载游戏文件。')
                status = h.status()
                if status.errc.value():
                    raise DownloadError(str(status.errc.message()))
            info = h.torrent_file()
            self.entries(info)
            encoded = lt.bencode(lt.create_torrent(info).generate())
            target = self.cache / (str(info.info_hashes().v1) + '.torrent')
            target.write_bytes(encoded)
            return info, str(target)
        finally:
            h.pause()
            self.session.remove_torrent(h)

    def _connect_explicit(self, handle, magnet):
        for value in parse_qs(urlsplit(magnet).query).get('x.pe', []):
            try:
                host, port = value.rsplit(':', 1)
                handle.connect_peer((host.strip('[]'), int(port)))
            except (ValueError, RuntimeError):
                continue

    def download(self, info, selected: list[FileEntry], root: Path, stop, progress=None,
                 magnet='', limit_mib=0, timeout=0):
        all_entries = self.entries(info)
        valid = {x.index: x for x in all_entries}
        if not selected or any(x.index not in valid or x.path != valid[x.index].path for x in selected):
            raise DownloadError('请选择种子中的有效文件。')
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        key = str(info.info_hashes().v1)
        marker = root / ('.playhub-torrent-' + key + '.json')
        owned = set()
        if marker.exists():
            try:
                owned = set(json.loads(marker.read_text('utf-8')).get('paths', []))
            except (ValueError, OSError):
                raise DownloadError('P2P 续传记录损坏，请换一个空目录。')
        for f in all_entries:
            target = safe_target(root, f.path)
            if target.exists() and f.path not in owned:
                raise DownloadError('种子目录存在不是本启动器创建的文件，拒绝覆盖：' + f.path)
        owned.update(f.path for f in selected)
        marker.write_text(json.dumps({'hash': key, 'paths': sorted(owned)}, ensure_ascii=False), 'utf-8')
        params = lt.add_torrent_params()
        params.ti, params.save_path = info, str(root)
        params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
        priorities = [0] * info.num_files()
        for f in selected:
            priorities[f.index] = 4
        params.file_priorities = priorities
        params.max_uploads = 2
        h = self.session.add_torrent(params)
        h.set_download_limit(max(0, int(limit_mib * 1024 * 1024)))
        with self.lock:
            self.handles[key] = h
        if magnet:
            self._connect_explicit(h, magnet)
        started = time.monotonic()
        try:
            while True:
                if stop.wait(0.2):
                    raise Paused()
                s = h.status()
                if s.errc.value():
                    raise DownloadError('P2P 下载错误：' + s.errc.message())
                amounts = h.file_progress()
                done = sum(min(amounts[f.index], f.size) for f in selected)
                total = sum(f.size for f in selected)
                if progress:
                    progress(done, total, s.download_payload_rate, s.num_peers)
                if s.is_finished:
                    break
                if timeout and time.monotonic() - started > timeout:
                    raise DownloadError('P2P 下载在限定时间内未完成。')
            h.pause()
            results = []
            for f in selected:
                target = safe_target(root, f.path)
                if not target.exists() or target.stat().st_size != f.size:
                    raise DownloadError('选中文件未完整写入磁盘。')
                results.append({'path': str(target), 'bytes': f.size, 'sha256': hash_file(target)})
            return results
        finally:
            h.pause()
            with self.lock:
                self.handles.pop(key, None)
            self.session.remove_torrent(h)

    def set_limit(self, mib):
        self.session.apply_settings({'download_rate_limit': max(0, int(mib * 1024 * 1024))})
        with self.lock:
            for handle in self.handles.values():
                handle.set_download_limit(max(0, int(mib * 1024 * 1024)))

    def close(self):
        self.session.pause()
