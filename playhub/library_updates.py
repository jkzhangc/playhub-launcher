"""Catalog-backed game details and version tracking; never inspect or change EXEs."""
from copy import deepcopy
import re

CATALOG_FIELDS = ('id','name','source','source_type','sources','cover','category','summary',
                  'developer','version','platform','screenshots','description',
                  'system_requirements','auto_install','changelog','author_notes')


def catalog_entry(game, catalog):
    if game.get('local_only'):return None
    return next((item for item in catalog if item.get('id') == game.get('id')),None)


def latest_details(game, catalog):
    latest=catalog_entry(game,catalog)
    return deepcopy(latest if latest is not None else game)


def catalog_snapshot(game):
    return {key:deepcopy(game[key]) for key in CATALOG_FIELDS if key in game}


def version_key(value):
    value=str(value or '').strip()
    match=re.fullmatch(r'[vV]?\s*(\d+(?:\.\d+)*)(?:[-_. ]?(dev|alpha|a|beta|b|rc|pre|preview)[-_. ]?(\d*))?(?:\+[0-9A-Za-z.-]+)?',value,re.I)
    if not match:return None
    numbers=tuple(int(part) for part in match[1].split('.'))
    while len(numbers)>1 and numbers[-1]==0:numbers=numbers[:-1]
    stage=(match[2] or '').lower()
    ranks={'dev':0,'alpha':1,'a':1,'beta':2,'b':2,'pre':2,'preview':2,'rc':3,'':4}
    return numbers,ranks[stage],int(match[3] or 0)


def compare_versions(remote, local):
    left,right=version_key(remote),version_key(local)
    if left is None or right is None:
        return 0 if str(remote).strip()==str(local).strip() else None
    width=max(len(left[0]),len(right[0]))
    left=(left[0]+(0,)*(width-len(left[0])),left[1],left[2])
    right=(right[0]+(0,)*(width-len(right[0])),right[1],right[2])
    return (left>right)-(left<right)


def update_status(game, catalog):
    remote=catalog_entry(game,catalog)
    installed=str(game.get('installed_version') or '').strip()
    baseline=installed or str(game.get('tracked_version') or game.get('version') or '').strip()
    latest=str((remote or {}).get('version') or '').strip()
    result={'available':False,'current':baseline,'latest':latest,
            'basis':'已安装版本' if installed else '记录版本'}
    if game.get('local_only') or (remote is None and not game.get('source') and not game.get('sources')):
        result.update(code='local',text='本地导入 · 未关联商店')
    elif remote is None:
        result.update(code='unlisted',text='商店暂无此游戏，保留本地记录')
    elif not latest:
        result.update(code='unversioned',text='管理员尚未填写版本')
    elif not baseline:
        result.update(code='unknown',text='本地版本未知 · 商店 '+latest)
    else:
        compared=compare_versions(latest,baseline)
        if compared is None:result.update(code='different',text='版本标识不同，请核对：'+baseline+' → '+latest)
        elif compared>0:result.update(code='update',available=True,text='发现新版本：'+baseline+' → '+latest)
        elif compared<0:result.update(code='ahead',text='本地记录 '+baseline+' 高于商店 '+latest)
        else:result.update(code='current',text=('已安装' if installed else '记录')+'版本与商店一致：'+latest)
    return result
