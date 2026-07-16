"""屏幕截图：抓取主屏整张 QPixmap（冻结帧，避免覆盖层入镜）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap


def grab_screen() -> QPixmap:
    """抓取主屏当前画面，统一到逻辑分辨率（dpr=1）。

    高 DPI 下 grabWindow 返回物理分辨率像素，而截图覆盖层用逻辑坐标；
    两者不一致会导致选区裁剪错位（看到的和实际截到的不符）。统一缩到逻辑分辨率后，
    显示/裁剪/OCR 坐标一致。
    """
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QPixmap()
    pm = screen.grabWindow(0)
    if pm.isNull():
        return pm
    geo = screen.geometry()  # 逻辑坐标
    if pm.width() != geo.width() or pm.height() != geo.height():
        pm = pm.scaled(geo.width(), geo.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(1.0)
    return pm
