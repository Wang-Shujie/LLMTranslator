"""qasync 桥接：token 经 Qt 信号投递到主线程（asyncio 协程由调用方投递到 qasync 事件循环）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class TokenEmitter(QObject):
    token_received = Signal(str)
    finished = Signal(str)      # 完整译文
    error = Signal(str)
