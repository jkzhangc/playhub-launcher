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

def install_zip(archive: Path, download_root: Path, config: dict, stop=None):
    if archive.suffix.lower()!='.zip':
        raise DownloadError('自动安装当前仅支持ZIP；APK无需解压，RAR/7z/安装器暂需手动处理。')
    expected=str(config.get('executable',''))
    relative=safe_relative(expected)
    if relative.suffix.lower()!='.exe':
        raise DownloadError('Windows 启动项必须是管理员配置的目录内相对 EXE 路径。')
    game_id=str(config.get('game_id','game'))
    if any(not(c.isalnum() or c in '-_') for c in game_id):raise DownloadError('游戏ID无效。')
    parent=download_root.resolve()/'installed';parent.mkdir(exist_ok=True)
    target=parent/(game_id+'-'+uuid.uuid4().hex[:8]);target.mkdir()
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
            wanted=relative.as_posix().casefold()
            if not any(f.filename.replace(chr(92),'/').casefold()==wanted for f in info if not f.is_dir()):raise DownloadError('管理员设置的启动项不在ZIP包内，未自动选择其他EXE。')
            for f in info:
                if stop and stop.is_set():raise DownloadError('安装已中断，保留独立安装目录，未登记游戏。')
                dest=safe_target(target,f.filename.rstrip('/'))
                if f.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(f) as source,dest.open('xb') as out:
                    count=0
                    while True:
                        data=source.read(1024*1024)
                        if not data:break
                        count+=len(data)
                        if count>f.file_size:raise DownloadError('解压长度超过清单。')
                        out.write(data)
                    if count!=f.file_size:raise DownloadError('ZIP文件未完整解压。')
                files.append({'path':str(dest),'bytes':dest.stat().st_size,'sha256':hash_file(dest)})
        executable=safe_target(target,expected)
        if not executable.is_file():raise DownloadError('启动项不存在，未登记游戏。')
        return {'directory':str(target),'executable':str(executable),'files':files,'game_id':game_id,'name':config.get('name',game_id)}
    except Exception:
        # No broad cleanup. Preserve unique staging output, never touch existing games.
        raise
