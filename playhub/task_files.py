"""Conservative user-confirmed recycling: explicit files, backup first, max 10."""
from datetime import datetime
from pathlib import Path
import json
import shutil
import uuid
from PySide6.QtCore import QFile
from .core import DownloadError,hash_file

def backup_and_recycle(state_root,files):
    if len(files)>10:raise DownloadError('每次最多处理10个明确文件。')
    records=[]
    for value in files:
        p=Path(value)
        if p.is_symlink() or not p.is_file():raise DownloadError('不是可安全回收的普通文件：'+str(p))
        records.append({'source':str(p),'size':p.stat().st_size,'sha256':hash_file(p)})
    total=sum(r['size'] for r in records)
    base=Path(state_root)/'recycle-backups';base.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(base).free<total+32*1024*1024:raise DownloadError('备份空间不足，未回收任何文件。')
    backup=base/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);backup.mkdir()
    for i,r in enumerate(records):
        target=backup/(str(i+1)+'-'+Path(r['source']).name)
        shutil.copy2(r['source'],target)
        if hash_file(target)!=r['sha256']:raise DownloadError('备份校验失败，未回收文件。')
        r['backup']=str(target)
    (backup/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    for r in records:
        source=Path(r['source'])
        if not source.is_file() or hash_file(source)!=r['sha256']:raise DownloadError('文件在确认后变化，已停止：'+str(source))
        result=QFile.moveToTrash(str(source))
        ok=result[0] if isinstance(result,tuple) else result
        if not ok or source.exists():raise DownloadError('回收站操作失败，已停止。备份位于：'+str(backup))
    return backup
