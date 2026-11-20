"""PlayHub native Windows launcher."""
import argparse
import json
import os
import sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--capture-dir')
    args=parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from playhub.core import StateStore,FileEntry,VERSION
    from playhub.ui import Launcher,SelectionDialog
    app=QApplication(sys.argv[:1]);app.setApplicationName('PlayHub');app.setApplicationVersion(VERSION)
    from PySide6.QtGui import QFontDatabase,QFont
    for filename in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
        system_font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename
        if system_font.exists():QFontDatabase.addApplicationFont(str(system_font))
    app.setFont(QFont('Microsoft YaHei UI',10))
    store=StateStore(Path(args.data_dir) if args.data_dir else None)
    if args.smoke_test:
        store.data['name']='本地测试玩家'
    window=Launcher(store);window.show()
    if args.smoke_test:
        def checks():
            try:
                pages=['home','store','library','downloads','settings','profile','updates','about']
                out=Path(args.capture_dir) if args.capture_dir else None
                if out:out.mkdir(parents=True,exist_ok=True)
                for key in pages:
                    window.show_page(key);app.processEvents()
                    if out:window.grab().save(str(out/(key+'.png')))
                chosen=[FileEntry('0','Game/mobile.apk',1234,'https://example.com/mobile.apk'),FileEntry('1','Game/desktop.zip',5678,'https://example.com/desktop.zip')]
                dlg=SelectionDialog(chosen,store,parent=window)
                assert len(dlg.selected())==0
                dlg.set_all(True);assert len(dlg.selected())==2
                dlg.set_all(False);assert len(dlg.selected())==0
                from PySide6.QtCore import Qt
                dlg.table.item(0,0).setCheckState(Qt.Checked);assert dlg.selected()[0].path=='Game/mobile.apk'
                dlg.show();app.processEvents()
                if out:dlg.grab().save(str(out/'file-selection.png'))
                dlg.reject();window.manager.close();window.cloud.close()
                result={'native_pages':pages,'selection_checks':4,'version':VERSION,'passed':True}
                if out:(out/'smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
                print(json.dumps(result,ensure_ascii=False));app.exit(0)
            except Exception as exc:
                print('SMOKE TEST FAILED',repr(exc),file=sys.stderr);app.exit(1)
        QTimer.singleShot(250,checks)
    return app.exec()

if __name__=='__main__':
    raise SystemExit(main())
