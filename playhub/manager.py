from __future__ import annotations
import threading
import uuid
import zipfile
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from .core import AuthorizationRequired, DownloadError, FileEntry, StateStore
from .http_engine import Paused, RateLimiter, download_file
from .p2p import TorrentEngine

class DownloadManager(QObject):
    changed = Signal()
    notification = Signal(str)

    def __init__(self, store: StateStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.limiter = RateLimiter(float(store.data.get('limit_mib', 0)) * 1024 * 1024)
        self.p2p = TorrentEngine(store.root / 'torrent-cache', upload_kib=store.data.get('upload_kib', 64))
        self.worker = None
        self.stop_event = threading.Event()
        self.web_sessions = {}
        self.lock = threading.RLock()

    @property
    def tasks(self):
        return self.store.data['tasks']

    def add(self, entries, directory, title='', torrent='', magnet='', web=None, deferred=False, install=None):
        task = {'id': uuid.uuid4().hex, 'title': title or entries[0].path.split('/')[0],
                'files': [f.to_dict() for f in entries], 'directory': str(directory), 'torrent': torrent,
                'magnet': magnet, 'status': 'queued', 'done': 0, 'total': sum(f.size for f in entries) if all(f.size >= 0 for f in entries) else -1,
                'install': install or {}, 'owned_files': [], 'created_files': [], 'new_files': [],
                'speed': 0, 'peers': 0, 'message': '等待下载', 'results': []}
        # Expiring cloud URLs and cookies are not written to disk.
        if web:
            self.web_sessions[task['id']] = (web, entries)
            task['authorized_session'] = True
            task['files'] = [{**f.to_dict(), 'url': ''} for f in entries]
        from .core import safe_target
        for f in entries:
            destination = safe_target(Path(directory), f.path)
            if not destination.exists():
                task['new_files'].append(str(destination))
        if deferred:
            task['status'] = 'auth_required'
            task['message'] = '已保留文件与目录，正在检查网盘授权'
        with self.lock:
            self.tasks.append(task)
            self.store.save()
        self.changed.emit()
        self.start_next()
        return task

    def start_next(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            task = next((t for t in self.tasks if t['status'] == 'queued'), None)
            if not task:
                return
            self.stop_event = threading.Event()
            self.worker = threading.Thread(target=self._run, args=(task, self.stop_event), daemon=True)
            self.worker.start()

    def _run(self, task, stop):
        self.update(task, status='downloading', message='正在连接来源')
        try:
            files = [FileEntry(**f) for f in task['files']]
            web = None
            if task.get('authorized_session'):
                if task['id'] not in self.web_sessions:
                    raise AuthorizationRequired('网盘临时授权会话已结束，请重新打开分享并选择文件。')
                web, files = self.web_sessions[task['id']]
            root = Path(task['directory'])
            if task['torrent']:
                info = self.p2p.load_torrent(task['torrent'])
                def tick(done, total, speed, peers):
                    self.update(task, done=done, total=total, speed=speed, peers=peers, message='P2P 正在下载与校验；上传上限 64 KiB/s')
                results = self.p2p.download(info, files, root, stop, tick, task.get('magnet', ''), self.store.data['limit_mib'])
            else:
                results = []
                done_before = 0
                total_all = sum(f.size for f in files) if all(f.size >= 0 for f in files) else -1
                completed = {item['path']: item for item in task.get('results', [])}
                from .core import safe_target, hash_file
                for f in files:
                    destination = safe_target(root, f.path)
                    prior = completed.get(str(destination))
                    if prior and destination.is_file() and hash_file(destination) == prior.get('sha256'):
                        results.append(prior)
                        done_before += prior['bytes']
                        continue
                    def tick(done, total, speed, offset=done_before):
                        self.update(task, done=offset + done, total=total_all if total_all >= 0 else total, speed=speed, message=f.path)
                    from .github_delivery import public_release_url, download_release
                    if web is None and public_release_url(f.url):
                        result = download_release(f, root, stop, self.limiter, tick,
                            mode=self.store.data.get('github_mode', 'origin'),
                            mirror_ids=self.store.data.get('github_mirrors', ['ghproxy']),
                            on_route=lambda message: self.update(task, message=message))
                    else:
                        result = download_file(f, root, stop, self.limiter, tick, web)
                    results.append(result)
                    self._record_outputs(task, [result])
                    done_before += result['bytes']
                    with self.lock:
                        task['results'] = list(results)
                        self.store.save()
            self._record_outputs(task, results)
            installation_message = ''
            if (task.get('install') or {}).get('enabled'):
                installation_message = self._extract_results(task, results, root, stop)
            self.update(task, status='complete', done=sum(x['bytes'] for x in results), total=sum(x['bytes'] for x in results),
                        speed=0, message='下载完成；已计算 SHA-256' + installation_message, results=results)
            self.notification.emit(task['title'] + ' 下载完成' + installation_message + '。不会自动运行。')
        except Paused:
            self.update(task, status='paused', speed=0, message='已暂停，可继续；P2P 恢复时重新核对现有分片')
        except AuthorizationRequired as exc:
            self.update(task, status='auth_required', speed=0, message=str(exc))
        except Exception as exc:
            self.update(task, status='error', speed=0, message=str(exc))
        finally:
            with self.lock:
                self.worker = None
            if not stop.is_set():
                self.start_next()

    def _extract_results(self, task, results, root, stop):
        from .install import install_archive, install_archives
        install=task.get('install') or {}
        archives=install_archives(results,root);packages=[];failures=[]
        for archive in archives:
            if stop.is_set():break
            self.update(task,status='installing',message='正在安全解压：'+archive.name)
            try:
                installed=install_archive(archive,root,{'name':task['title'],**install},stop)
            except (OSError,ValueError,RuntimeError,DownloadError,zipfile.BadZipFile) as exc:
                failures.append(archive.name+'：'+str(exc))
                if stop.is_set():break
                continue
            packages.append(installed);task.setdefault('owned_files',[]).extend(installed['files'])
        task['extracted_packages']=packages
        launches=[item for item in packages if item['executable']]
        if len(launches)==1 and install.get('game_id') and not failures and not stop.is_set():
            installed=launches[0];task['installed']=installed
            library=self.store.data['library']
            game=next((g for g in library if g.get('id')==installed['game_id']),None)
            from .library_updates import catalog_snapshot
            snapshot=catalog_snapshot(install.get('catalog_game') or {})
            version=str(install.get('version') or '')
            baseline=version or str((game or {}).get('installed_version') or (game or {}).get('tracked_version') or (game or {}).get('version') or '')
            fields={**snapshot,'id':installed['game_id'],'name':installed['name'],
                    'executable':installed['executable'],'install_directory':installed['directory'],
                    'installed_version':version,'tracked_version':baseline,'version':baseline,
                    'version_source':'download_install' if version else 'unknown'}
            if game is not None:
                fields['name']=game.get('custom_name') or game.get('name') or installed['name'];game.update(fields)
            else:library.append(fields)
        text=('；已分别解压 '+str(len(packages))+' 个压缩包到 installed 目录') if archives else '；所选文件中未找到支持的压缩包（ZIP/7z/TAR/GZ/BZ2/XZ）'
        if packages and (len(launches)!=1 or failures or stop.is_set()):text+='；未自动登记启动项，可在游戏库手动选择'
        if failures:text+='；解压失败：'+'；'.join(failures)
        if stop.is_set():text+='；解压已取消，原压缩包和旧游戏未改动'
        return text

    def extract_completed(self, ident):
        with self.lock:
            if self.worker and self.worker.is_alive():raise DownloadError('请等待当前下载/解压结束后再解压已下载文件。')
            task=next((t for t in self.tasks if t['id']==ident),None)
            if not task or task.get('status')!='complete' or not task.get('results'):
                raise DownloadError('请先完成下载，再解压已有文件。')
            task.setdefault('install',{})['enabled']=True
            self.stop_event=threading.Event()
            self.update(task,status='installing',message='正在校验已下载压缩包，不重新下载。')
            self.worker=threading.Thread(target=self._run_extract,args=(task,self.stop_event),daemon=True)
            self.worker.start()

    def _run_extract(self, task, stop):
        from .core import hash_file
        try:
            root=Path(task['directory']);results=task['results']
            from .install import install_archives
            archives=install_archives(results,root)
            if not archives:raise DownloadError('没有支持的压缩包；RAR、分卷包和安装器暂不支持。')
            for archive in archives:
                if stop.is_set():raise DownloadError('已取消解压，原文件未改动。')
                record=next(item for item in results if Path(item['path']).resolve()==archive.resolve())
                if archive.stat().st_size!=record['bytes'] or not record.get('sha256') or hash_file(archive)!=record['sha256']:
                    raise DownloadError('已下载压缩包发生变化或缺少校验记录，未解压：'+archive.name)
            message=self._extract_results(task,results,root,stop)
            self.update(task,status='complete',speed=0,message='已有下载文件处理完成'+message)
            self.notification.emit(task['title']+' 解压处理结束。不会自动运行。')
        except Exception as exc:
            self.update(task,status='complete',speed=0,message='下载文件保留；解压未完成：'+str(exc))
        finally:
            with self.lock:self.worker=None
            if not stop.is_set():self.start_next()

    def update(self, task, **values):
        with self.lock:
            task.update(values)
            if 'status' in values:
                if task.get('status') in ('paused', 'error', 'auth_required'):
                    self._record_partial_files(task)
                self.store.save()
        self.changed.emit()

    def pause(self, ident):
        task = next((t for t in self.tasks if t['id'] == ident), None)
        if task:
            if task['status'] == 'installing':
                self.stop_event.set()
                self.update(task, message='正在取消解压，保留原压缩包和独立输出目录…')
            elif task['status'] == 'downloading':
                self.stop_event.set()
                self.update(task, message='正在暂停，等待网络读操作结束…')
            elif task['status'] == 'queued':
                self.update(task, status='paused', message='已暂停')

    def resume(self, ident):
        task = next((t for t in self.tasks if t['id'] == ident), None)
        if task and task['status'] in ('paused', 'error', 'auth_required'):
            self.update(task, status='queued', message='已加入队列')
            self.start_next()

    def authorize(self, ident, entries, web):
        task = next((t for t in self.tasks if t['id'] == ident), None)
        if not task:
            raise ValueError('原下载任务已被删除，已取消授权转接。')
        if len(entries) != len(task['files']):
            raise ValueError('授权文件与原选择数量不一致。')
        if {f.path for f in entries} != {f['path'] for f in task['files']}:
            raise ValueError('授权文件与原选择不匹配。')
        self.web_sessions[ident] = (web, entries)
        task['authorized_session'] = True
        task['files'] = [{**f.to_dict(), 'url': ''} for f in entries]
        self.update(task, status='queued', message='网盘已授权，沿用原文件和目录开始下载')
        self.start_next()

    def _record_outputs(self, task, results):
        owned = {x['path']: x for x in task.get('owned_files', [])}
        for result in results:
            if result['path'] in task.get('new_files', []) and not result.get('existing'):
                owned[result['path']] = {k: result[k] for k in ('path', 'bytes', 'sha256')}
        task['owned_files'] = list(owned.values())

    def _record_partial_files(self, task):
        from .core import hash_file
        records = {x['path']: x for x in task.get('created_files', [])}
        for target in task.get('new_files', []):
            for suffix in ('.playhub.part', '.playhub.resume.json'):
                p = Path(target).with_name(Path(target).name + suffix)
                if p.is_file() and not p.is_symlink():
                    records[str(p)] = {'path': str(p), 'bytes': p.stat().st_size, 'sha256': hash_file(p)}
        task['created_files'] = list(records.values())

    def deletion_files(self, ident):
        from .core import hash_file
        task = next((t for t in self.tasks if t['id'] == ident), None)
        if not task:
            return []
        if task['status'] in ('downloading', 'installing'):
            raise ValueError('请先暂停任务，等待磁盘写入停止后再删除。')
        root = Path(task['directory']).resolve()
        files = []
        for record in task.get('owned_files', []) + task.get('created_files', []):
            p = Path(record['path'])
            if not p.exists():
                continue
            try:
                p.resolve().relative_to(root)
            except ValueError as exc:
                raise ValueError('删除记录越出下载目录，已停止。') from exc
            if p.is_symlink() or any(x.is_symlink() for x in p.parents if x != root.parent):
                raise ValueError('不回收符号链接中的文件。')
            if not p.is_file() or p.stat().st_size != record['bytes'] or hash_file(p) != record['sha256']:
                raise ValueError('文件在下载后发生变化，为避免误删已停止：' + str(p))
            if str(p) not in files:
                files.append(str(p))
        if len(files) > 10:
            raise ValueError('此次超过10个文件，暂不提供整批删除；可仅移除任务并自行整理。')
        return files

    def remove(self, ident, recycle=None):
        task = next((t for t in self.tasks if t['id'] == ident), None)
        if not task:
            return
        if task['status'] in ('downloading', 'installing'):
            raise ValueError('请先暂停下载，等待任务停止。')
        if recycle:
            for filename in self.deletion_files(ident):
                result = recycle(filename)
                if isinstance(result, tuple):
                    result = result[0]
                if not result:
                    raise ValueError('无法移入回收站，已停止，未移除任务：' + filename)
        with self.lock:
            self.tasks.remove(task)
            self.web_sessions.pop(ident, None)
            self.store.save()
        self.changed.emit()

    def limits(self, mib):
        self.limiter.set_limit(mib * 1024 * 1024)
        self.p2p.set_limit(mib)

    def close(self):
        self.stop_event.set()
        self.p2p.close()
        self.store.save()
