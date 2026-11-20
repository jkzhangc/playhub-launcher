"""Reproducible public client build. No private Studio source is required."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from playhub.core import VERSION
if sys.platform!='win32':raise SystemExit('Windows builder required.')
VENDOR=ROOT/'vendor';VENDOR.mkdir(exist_ok=True)
node=shutil.which('node')
if not node:raise SystemExit('Node.js is required for official cloud authorization.')
node_target=VENDOR/'node.exe'
if not node_target.exists():shutil.copy2(node,node_target)
package=ROOT/'node_modules/playwright-core'
if not package.exists():raise SystemExit('Install playwright-core in this repository: npm install --prefix . --no-save playwright-core')
if not (VENDOR/'playwright-core').exists():shutil.copytree(package,VENDOR/'playwright-core')
args=[sys.executable,'-m','PyInstaller','--windowed','--onedir','--noupx','--name','PlayHub','--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build'),'--specpath',str(ROOT/'build'),'--icon',str(ROOT/'assets/playhub.ico'),'--collect-all','libtorrent','--exclude-module','private','--exclude-module','playhub.admin_policy','--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets','--exclude-module','PySide6.QtWebView']
for source,dest in [('assets','assets'),('catalog','catalog'),('legal','legal'),('benchmark-results','benchmark-results'),('tools/cloud_bridge.cjs','tools'),('vendor','vendor')]:args+=['--add-data',str(ROOT/source)+';'+dest]
args.append(str(ROOT/'launch.py'));subprocess.run(args,cwd=ROOT,check=True)
subprocess.run([str(ROOT/'dist/PlayHub/PlayHub.exe'),'--smoke-test','--data-dir',str(ROOT/'validation/build-state'),'--capture-dir',str(ROOT/'validation/build-ui')],cwd=ROOT,check=True)
output=ROOT/'dist'/('PlayHub-'+VERSION+'-alpha-win-x64.zip')
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted((ROOT/'dist/PlayHub').rglob('*')):
        if p.is_file():z.write(p,str(Path('PlayHub')/p.relative_to(ROOT/'dist/PlayHub')))
sha=hashlib.sha256(output.read_bytes()).hexdigest();output.with_suffix('.zip.sha256').write_text(sha+'  '+output.name+chr(10),'utf-8')
print(json.dumps({'archive':str(output),'bytes':output.stat().st_size,'sha256':sha},indent=2))
