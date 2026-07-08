"""屏幕截图：抓取主屏整张 QPixmap（冻结帧，避免覆盖层入镜）。"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QPixmap


def grab_screen() -> QPixmap:
    """抓取主屏当前画面。"""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QPixmap()
    return screen.grabWindow(0)
