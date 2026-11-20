import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage,QPainter,QIcon,QPixmap
from PySide6.QtCore import Qt
root=Path(__file__).resolve().parent.parent
app=QApplication([])
renderer=QSvgRenderer(str(root/'assets/playhub.svg'))
icon=QIcon()
for size in [16,24,32,48,64,128,256]:
    image=QImage(size,size,QImage.Format_ARGB32);image.fill(Qt.transparent);p=QPainter(image);p.setRenderHint(QPainter.Antialiasing);renderer.render(p);p.end();image.save(str(root/f'assets/playhub-{size}.png'));icon.addPixmap(QPixmap.fromImage(image))
image=QImage(256,256,QImage.Format_ARGB32);image.fill(Qt.transparent);p=QPainter(image);renderer.render(p);p.end();print('ico_saved',image.save(str(root/'assets/playhub.ico'),'ICO'))
