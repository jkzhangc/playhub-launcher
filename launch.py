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
    if not args.smoke_test:
        QTimer.singleShot(500,lambda:window.check_update(quiet=True))
        window.start_library_monitor()
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
                dlg.reject()
                assert window.detect('https://www.mediafire.com/file/test/game.zip/file')=='mediafire'
                assert window.detect('https://www.mediafire.com.evil.test/file/test')=='direct'
                from playhub.ui import PageReveal
                window.show_page('store');app.processEvents()
                for overlay in window.scroll.viewport().findChildren(PageReveal):overlay.dismiss()
                reveal=PageReveal(window.scroll.viewport(),1);reveal.show()
                frame_images=[]
                for number,phase in enumerate((0.0,0.5,1.0)):
                    reveal.frame(phase);image=reveal.grab().toImage();frame_images.append(image)
                    if out:image.save(str(out/('motion-frame-'+str(number)+'.png')))
                assert frame_images[0]!=frame_images[1] and frame_images[1]!=frame_images[2]
                reveal.dismiss()
                from PySide6.QtWidgets import QFrame,QPushButton,QLabel
                from playhub.library_updates import update_status
                import py7zr,uuid
                from playhub.install import install_archive
                archive_root=store.root/('archive-smoke-'+uuid.uuid4().hex[:8]);archive_root.mkdir()
                seven=archive_root/'fixture.7z'
                with py7zr.SevenZipFile(seven,'w') as package:package.writestr(b'non-executable archive smoke fixture','Game.exe')
                extracted=install_archive(seven,archive_root,{})
                assert extracted['executable']==''
                assert (Path(extracted['directory'])/'Game.exe').read_bytes()==b'non-executable archive smoke fixture'
                assert window.property('themeColor')=='blue'
                from PySide6.QtWidgets import QComboBox,QTabWidget
                window.show_page('store');app.processEvents()
                for index in (1,2,0)*4:
                    combo=window.body.findChild(QComboBox,'StoreSort');old_body=window.body
                    combo.setCurrentIndex(index);assert window.body is old_body
                    app.processEvents()
                original_library=store.data['library'];original_catalog=window.catalog
                old={'id':'smoke-library-update','name':'离线版本检查测试','version':'1.0','installed_version':'1.0',
                     'description':'旧版说明','source':'https://example.com/old.zip','executable':''}
                latest={**old,'version':'2.0','name':'最新商店详情测试','description':'最新说明：仅用于离线自检，不包含在商店中。',
                        'summary':'游戏库详情与商店一致','source':'https://example.com/new.zip','screenshots':[],'installed_version':'',
                        'changelog':'2.0：更新日志离线自检。','author_notes':'感谢游玩，这是作者的话。'}
                store.data['library']=[old];window.catalog=[latest]
                window.show_page('library');app.processEvents()
                for overlay in window.scroll.viewport().findChildren(PageReveal):overlay.dismiss()
                assert window.library_update_dot.isVisible()
                primary=next(w for w in window.body.findChildren(QPushButton) if w.property('libraryPrimaryAction'))
                assert primary.text()=='点击下载' and primary.isEnabled()
                assert any(w.property('updateAvailable') for w in window.body.findChildren(QFrame))
                if out:window.grab().save(str(out/'library-update.png'))
                window.detail(old);app.processEvents();detail=window.dialogs[-1]
                assert detail.property('catalogVersion')=='2.0'
                assert any('最新说明' in w.text() for w in detail.findChildren(QLabel))
                assert window.library_update_dot.isVisible() and old['installed_version']=='1.0'
                if out:detail.grab().save(str(out/'game-detail-latest.png'))
                tabs=detail.findChild(QTabWidget,'GameDetailTabs')
                for title in ('更新日志','作者的话'):
                    index=next(i for i in range(tabs.count()) if tabs.tabText(i)==title);tabs.setCurrentIndex(index)
                    detail.detail_scroll.verticalScrollBar().setValue(detail.detail_scroll.verticalScrollBar().maximum());app.processEvents()
                    if out:detail.grab().save(str(out/('game-changelog.png' if title=='更新日志' else 'game-author-notes.png')))
                assert latest['author_notes'] in [w.text() for w in detail.findChildren(QLabel)]
                detail.accept();app.processEvents()
                old['installed_version']='2.0';window.queue_changed()
                assert window.library_update_dot.isHidden()
                store.data['library']=original_library;window.catalog=original_catalog
                window.refresh_library_indicators();window.manager.close();window.cloud.close()
                result={'native_pages':pages,'selection_checks':4,'mediafire_detection':True,'motion_frames_differ':True,'seven_zip_extraction':True,
                        'library_update_dot':True,'library_update_highlight':True,'latest_library_details':True,
                        'update_clears_after_version_registration':True,'default_blue_theme':True,'uninstalled_download_button':True,
                        'changelog_and_author_notes':True,'sort_signal_rebuild_safe':True,'version':VERSION,'passed':True}
                if out:(out/'smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
                print(json.dumps(result,ensure_ascii=False));app.exit(0)
            except Exception as exc:
                print('SMOKE TEST FAILED',repr(exc),file=sys.stderr);app.exit(1)
        QTimer.singleShot(250,checks)
    return app.exec()

if __name__=='__main__':
    raise SystemExit(main())
