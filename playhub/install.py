"""Safe ZIP installation into a fresh per-game directory. Never run installers."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import stat
import uuid
import zipfile
from .core import DownloadError,hash_file,safe_relative,safe_target

MAX_FILES=10000
MAX_UNPACKED=30*1024**3

def _zip_candidate(path: Path) -> bool:
    # Some download providers return an opaque basename or a generic .bin name.
    # Do not treat APK, JAR, or other ZIP-based formats as Windows game packages.
    return path.suffix.lower() in ('.zip', '.bin', '') and path.is_file() and zipfile.is_zipfile(path)

def install_archives(results, root: Path):
    candidates = []
    for result in results:
        path = Path(result['path'])
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise DownloadError('下载结果含符号链接，已停止自动解压。')
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise DownloadError('下载结果不在任务目录内，已停止自动解压。') from exc
        path = safe_target(root, relative.as_posix())
        from .archive_formats import archive_kind
        if archive_kind(path) is None:
            continue
        candidates.append(path)
    return candidates

def install_archive(archive: Path, download_root: Path, config: dict, stop=None):
    from .archive_formats import archive_kind, extract_additional
    archive=Path(archive);kind=archive_kind(archive)
    if kind=='zip':return install_zip(archive,download_root,config,stop)
    if kind is None:raise DownloadError('压缩格式不支持或文件损坏；APK/JAR/安装器不自动解压，RAR与分卷包暂不支持。')
    expected=str(config.get('executable',''))
    relative=safe_relative(expected) if expected else None
    if relative is not None and relative.suffix.lower()!='.exe':
        raise DownloadError('Windows启动项必须是管理员配置的目录内相对EXE路径。')
    game_id=str(config.get('game_id','game'))
    if not game_id or any(not(c.isalnum() or c in '-_') for c in game_id):raise DownloadError('游戏ID无效。')
    if stop and stop.is_set():raise DownloadError('安装已取消，未解压。')
    parent=safe_target(download_root,'installed');parent.mkdir(exist_ok=True)
    target=safe_target(parent,game_id+'-'+archive.stem[:60]+'-'+uuid.uuid4().hex[:8]);target.mkdir()
    names=extract_additional(archive,target,kind,stop);files=[];executable=''
    wanted=relative.as_posix().casefold() if relative else None
    for name in names:
        if stop and stop.is_set():raise DownloadError('安装已中断，未登记游戏。')
        path=safe_target(target,name)
        if not path.is_file():raise DownloadError('解压文件与清单不一致。')
        files.append({'path':str(path),'bytes':path.stat().st_size,'sha256':hash_file(path)})
        if wanted and safe_relative(name).as_posix().casefold()==wanted:executable=str(path)
    return {'directory':str(target),'executable':executable,'files':files,'game_id':game_id,'name':config.get('name',game_id)}


def install_zip(archive: Path, download_root: Path, config: dict, stop=None):
    if not _zip_candidate(archive):
        raise DownloadError('文件不是可用的 Windows 游戏 ZIP；APK、RAR、7z 或安装器不会自动解压。')
    expected=str(config.get('executable',''))
    relative=safe_relative(expected) if expected else None
    if relative is not None and relative.suffix.lower()!='.exe':
        raise DownloadError('Windows 启动项必须是管理员配置的目录内相对 EXE 路径。')
    game_id=str(config.get('game_id','game'))
    if any(not(c.isalnum() or c in '-_') for c in game_id):raise DownloadError('游戏ID无效。')
    parent=safe_target(download_root,'installed');parent.mkdir(exist_ok=True)
    target=safe_target(parent,game_id+'-'+archive.stem[:60]+'-'+uuid.uuid4().hex[:8]);target.mkdir()
    files=[];total=0
    try:
        with zipfile.ZipFile(archive) as z:
            info=z.infolist()
            if not info or len(info)>MAX_FILES:raise DownloadError('ZIP文件数量超出安全限制。')
            seen=set()
            for f in info:
                name=f.filename.rstrip('/')
                if not name:continue
                safe_relative(name)
                if name.casefold() in seen:raise DownloadError('ZIP存在重复或大小写冲突路径。')
                seen.add(name.casefold())
                mode=(f.external_attr>>16)&0xffff
                if stat.S_ISLNK(mode) or (mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) and mode&0o170000):raise DownloadError('ZIP含链接或特殊文件。')
                if f.flag_bits&1:raise DownloadError('加密ZIP不自动解压。')
                total+=f.file_size
                if total>MAX_UNPACKED or (f.file_size>10*1024*1024 and f.file_size/max(f.compress_size,1)>500):raise DownloadError('ZIP体积或压缩比超出安全限制。')
            if shutil.disk_usage(parent).free<total+64*1024*1024:raise DownloadError('解压所需磁盘空间不足。')
            wanted=relative.as_posix().casefold() if relative else None
            executable=None
            for f in info:
                if stop and stop.is_set():raise DownloadError('安装已中断，保留独立安装目录，未登记游戏。')
                dest=safe_target(target,f.filename.rstrip('/'))
                if f.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(f) as source,dest.open('xb') as out:
                    count=0
                    while True:
                        if stop and stop.is_set():raise DownloadError('安装已中断，原压缩包和旧游戏未改动。')
                        data=source.read(1024*1024)
                        if not data:break
                        count+=len(data)
                        if count>f.file_size:raise DownloadError('解压长度超过清单。')
                        out.write(data)
                    if count!=f.file_size:raise DownloadError('ZIP文件未完整解压。')
                files.append({'path':str(dest),'bytes':dest.stat().st_size,'sha256':hash_file(dest)})
                if wanted and safe_relative(f.filename).as_posix().casefold()==wanted:
                    executable=dest
        return {'directory':str(target),'executable':str(executable) if executable else '', 'files':files,'game_id':game_id,'name':config.get('name',game_id)}
    except Exception:
        # No broad cleanup. Preserve unique staging output, never touch existing games.
        raise
