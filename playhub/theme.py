"""Shared native theme and motion preferences; no network or credential state."""
import os
import re
from PySide6.QtGui import QColor

THEMES=(('晴蓝','blue'),('墨青绿','green'))


def normalize_theme(value,default='blue'):
    return value if value in {key for _,key in THEMES} else default


def convert_color(value,theme):
    """Move the original green family to blue; preserve neutral and status red."""
    color=QColor(value)
    if theme!='blue' or not color.isValid():return color
    hue,saturation,lightness,alpha=color.getHslF()
    if 75/360<=hue<=185/360 and saturation>0.015:
        return QColor.fromHslF(210/360,saturation,lightness,alpha)
    return color


def themed_stylesheet(style,theme):
    return re.sub(r'#[0-9A-Fa-f]{6}\b',lambda match:convert_color(match[0],theme).name(),style)


def theme_color(widget,value):
    current=widget
    while current is not None:
        theme=current.property('themeColor')
        if theme:return convert_color(value,theme)
        current=current.parentWidget()
    return convert_color(value,'green')


def system_motion_enabled():
    if os.name=='nt':
        import ctypes
        enabled=ctypes.c_int(1)
        try:
            if ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0):
                return bool(enabled.value)
        except OSError:
            pass
    return True
