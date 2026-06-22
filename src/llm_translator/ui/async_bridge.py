"""qasync 桥接：把 asyncio 协程跑在 Qt 事件循环里，token 经 Qt 信号投递到主线程。"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from PySide6.QtCore import QObject, Signal

try:
    import qasync  # type: ignore
    from PySide6.QtWidgets import QApplication
    _HAS_QASYNC = True
except Exception:  # pragma: no cover
    _HAS_QASYNC = False


class TokenEmitter(QObject):
    token_received = Signal(str)
    finished = Signal(str)      # 完整译文
    error = Signal(str)


def install_asyncio_loop(app):
    """在 QApplication 上安装 qasync 事件循环，返回 loop。"""
    if not _HAS_QASYNC:
        raise RuntimeError("未安装 qasync")
    return qasync.QEventLoop(app)


def run_coro(coro: Awaitable, emitter: TokenEmitter) -> asyncio.Task:
    """把翻译协程投到 asyncio loop 运行；token 通过 emitter 信号发出。"""
    loop = asyncio.get_event_loop()
    return loop.create_task(coro)
