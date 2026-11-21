"""Additional archive decoders. No extractall-to-disk, links, or execution."""
from __future__ import annotations
import bz2
import gzip
import lzma
import shutil
import stat
import tarfile
import threading
from pathlib import Path

from .core import DownloadError, safe_relative, safe_target

MAX_FILES=10000
MAX_UNPACKED=30*1024**3
CHUNK=1024**2


def archive_kind(path):
    path=Path(path)
    allowed={'.zip','.7z','.tar','.tgz','.tbz','.tbz2','.txz','.gz','.bz2','.xz','.bin',''}
    if not path.is_file() or path.suffix.lower() not in allowed:return None
    with path.open('rb') as source:magic=source.read(8)
    if magic.startswith(b'7z\xbc\xaf\x27\x1c'):return '7z'
    import zipfile
    if zipfile.is_zipfile(path):return 'zip'
    if magic.startswith(b'\x1f\x8b'):return 'gzip'
    if magic.startswith(b'BZh'):return 'bzip2'
    if magic.startswith(b'\xfd7zXZ\x00'):return 'xz'
    if path.suffix.lower() in ('.tar','.bin','') and tarfile.is_tarfile(path):return 'tar'
    return None


def _cancel(stop):
    if stop and stop.is_set():raise DownloadError('解压已中断，保留独立目录，未登记游戏。')


def _validate(entries, archive, parent, stop):
    if not entries or len(entries)>MAX_FILES:raise DownloadError('压缩包文件数量超出安全限制。')
    seen={};total=0
    for entry in entries:
        _cancel(stop)
        name,size,directory=entry
        relative=safe_relative(name).as_posix();key=relative.casefold()
        if key in seen:raise DownloadError('压缩包存在重复或大小写冲突路径。')
        if not isinstance(size,int) or size<0:raise DownloadError('压缩包大小清单无效。')
        seen[key]=directory;total+=size
        if total>MAX_UNPACKED:raise DownloadError('压缩包解压大小超出安全限制。')
    for key in seen:
        parts=key.split('/')
        for i in range(1,len(parts)):
            ancestor='/'.join(parts[:i])
            if ancestor in seen and not seen[ancestor]:raise DownloadError('压缩包文件与目录路径冲突。')
    if total>10*1024**2 and total/max(archive.stat().st_size,1)>500:
        raise DownloadError('压缩包压缩比超出安全限制。')
    if shutil.disk_usage(parent).free<total+64*1024**2:raise DownloadError('解压所需磁盘空间不足。')
    return total


def _copy(source, destination, size, stop):
    destination.parent.mkdir(parents=True,exist_ok=True);count=0
    with destination.open('xb') as output:
        while True:
            _cancel(stop);block=source.read(CHUNK)
            if not block:break
            count+=len(block)
            if count>size:raise DownloadError('解压长度超过清单或安全限额。')
            output.write(block)
    return count


def extract_seven(archive,target,stop):
    import py7zr
    try:
        with py7zr.SevenZipFile(archive,'r',max_extract_size=MAX_UNPACKED) as package:
            if package.needs_password():raise DownloadError('加密7z暂不自动解压，请在可信工具中手动处理。')
            entries=[]
            for member in package.files:
                _cancel(stop)
                if (member.is_symlink or member.is_junction or member.is_socket
                        or not (member.is_directory or member.is_file)
                        or member.st_fmt not in (None,0,stat.S_IFREG,stat.S_IFDIR)):
                    raise DownloadError('7z含链接、重解析点或特殊文件，未解压。')
                entries.append((member.filename.rstrip('/'),member.uncompressed or 0,member.is_directory))
                if len(entries)>MAX_FILES:raise DownloadError('压缩包文件数量超出安全限制。')
            total=_validate(entries,archive,target.parent,stop)
            expected={safe_relative(name).as_posix():size for name,size,directory in entries if not directory}
            for name,_,directory in entries:
                if directory:safe_target(target,name).mkdir(parents=True,exist_ok=True)

            class Sink(py7zr.Py7zIO):
                def __init__(self,name):
                    self.name=name;self.length=0
                    dest=safe_target(target,name);dest.parent.mkdir(parents=True,exist_ok=True)
                    self.file=dest.open('x+b')
                def write(self,data):
                    with factory.lock:
                        _cancel(stop)
                        end=self.file.tell()+len(data)
                        if end>expected[self.name] or factory.written+len(data)>total:
                            raise DownloadError('7z解压长度超过清单。')
                        result=self.file.write(data);factory.written+=result;self.length=max(self.length,end)
                        return result
                def read(self,size=None):return self.file.read(-1 if size is None else size)
                def seek(self,offset,whence=0):
                    position=offset if whence==0 else self.file.tell()+offset if whence==1 else self.length+offset
                    if not 0<=position<=expected[self.name]:raise DownloadError('7z输出偏移无效。')
                    return self.file.seek(offset,whence)
                def flush(self):
                    if not self.file.closed:self.file.flush()
                def size(self):return self.length
                def close(self):self.file.close()

            class Factory(py7zr.WriterFactory):
                def __init__(self):self.products={};self.lock=threading.RLock();self.written=0
                def create(self,filename):
                    with self.lock:
                        _cancel(stop);name=safe_relative(filename).as_posix()
                        if name not in expected or name in self.products:raise DownloadError('7z输出路径与清单不一致。')
                        sink=Sink(name);self.products[name]=sink;return sink

            factory=Factory()
            try:
                package.extractall(factory=factory)
            finally:
                for sink in factory.products.values():sink.close()
            if set(factory.products)!=set(expected):raise DownloadError('7z未完整输出全部文件。')
            for name,size in expected.items():
                _cancel(stop)
                if safe_target(target,name).stat().st_size!=size:raise DownloadError('7z文件未完整解压。')
            return list(expected)
    except DownloadError:raise
    except Exception as exc:
        raise DownloadError('7z解析或校验失败：'+str(exc)[:300]) from exc


def extract_tar(archive,target,stop):
    try:
        with tarfile.open(archive,'r:*') as package:
            members=[];entries=[]
            for member in package:
                _cancel(stop)
                if not (member.isfile() or member.isdir()) or member.issparse():
                    raise DownloadError('TAR含链接、稀疏文件或特殊文件，未解压。')
                name=member.name.rstrip('/')
                while name.startswith('./'):name=name[2:]
                if not name and member.isdir():continue
                entries.append((name,member.size,member.isdir()));members.append((member,name))
                if len(entries)>MAX_FILES:raise DownloadError('压缩包文件数量超出安全限制。')
            _validate(entries,archive,target.parent,stop);names=[]
            for member,name in members:
                _cancel(stop);destination=safe_target(target,name)
                if member.isdir():destination.mkdir(parents=True,exist_ok=True);continue
                with package.extractfile(member) as source:
                    if _copy(source,destination,member.size,stop)!=member.size:raise DownloadError('TAR文件未完整解压。')
                names.append(safe_relative(name).as_posix())
            return names
    except DownloadError:raise
    except (tarfile.TarError,OSError,EOFError,lzma.LZMAError) as exc:
        raise DownloadError('TAR压缩包解析或校验失败：'+str(exc)[:300]) from exc


def extract_additional(archive,target,kind,stop):
    if kind=='7z':return extract_seven(archive,target,stop)
    if kind=='tar' or tarfile.is_tarfile(archive):return extract_tar(archive,target,stop)
    readers={'gzip':gzip.open,'bzip2':bz2.open,'xz':lzma.open}
    if kind not in readers:raise DownloadError('暂不支持该压缩格式。')
    name=archive.stem;safe_relative(name)
    limit=min(MAX_UNPACKED,max(10*1024**2,archive.stat().st_size*500))
    limit=min(limit,max(0,shutil.disk_usage(target.parent).free-64*1024**2))
    if limit<=0:raise DownloadError('解压所需磁盘空间不足。')
    try:
        with readers[kind](archive,'rb') as source:_copy(source,safe_target(target,name),limit,stop)
    except (OSError,EOFError,lzma.LZMAError) as exc:
        raise DownloadError('单文件压缩流校验失败：'+str(exc)[:300]) from exc
    return [name]
