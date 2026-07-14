"""划词翻译控制器：全局热键（keyboard 库）+ 模拟 Ctrl+C 取词 + Qt QClipboard 保存/恢复。

热键回调在 keyboard 库的监听线程触发 → 发 triggered 信号（Qt 自动 QueuedConnection 跨
到主线程）→ 主线程执行“保存剪贴板 → send ctrl+c → QTimer 120ms → 读 + 还原 → 发 captured”。
QClipboard/QCursor/QTimer 只能在主线程用，故全在主线程槽里跑。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication


class SelectionController(QObject):
    """全局热键划词：触发后取选中文本 + 光标位置，发 captured(text, pos)。"""

    triggered = Signal()                       # keyboard 线程 → 主线程
    captured = Signal(str, QPoint)             # 取词完成（主线程发）

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hotkey: str | None = None
        self._saved_text: str = ""
        self._saved_pixmap = None
        self.triggered.connect(self._on_triggered)  # 跨线程自动 Queued
        if settings.selection_enabled:
            self.enable()

    def enable(self) -> None:
        if self._hotkey is not None:
            return  # 已注册
        import keyboard  # 延迟导入：缺依赖/打包时顶层不崩
        hk = self._settings.selection_hotkey
        try:
            # suppress=True：吞掉原按键，不发给前台程序。否则热键（如 ctrl+d）会
            # 同时触发浏览器自身快捷键（Ctrl+D=加书签）→ 抢焦点/丢选区，导致随后
            # 模拟的 ctrl+c 复制到错误的文本（选中 ≠ 翻译）。
            keyboard.add_hotkey(hk, self._on_hotkey_thread, suppress=True)
            self._hotkey = hk
        except Exception:
            self._hotkey = None  # 注册失败（被占用等）→ 不崩，功能不可用

    def disable(self) -> None:
        if self._hotkey is None:
            return
        import keyboard
        try:
            keyboard.remove_hotkey(self._hotkey)
        except Exception:
            pass
        self._hotkey = None

    def _on_hotkey_thread(self) -> None:
        # keyboard 库监听线程 → 信号投到主线程
        self.triggered.emit()

    def _on_triggered(self) -> None:
        # 主线程：保存原剪贴板 → 清空（哨兵）→ 模拟 Ctrl+C → 延迟读 + 还原
        clip = QGuiApplication.clipboard()
        self._saved_text = clip.text()
        self._saved_pixmap = clip.pixmap()
        # 清空剪贴板作哨兵：之后只要非空即说明 ctrl+c 复制到了选区。
        # 不能用"剪贴板是否变化"判定——当选区恰好等于旧剪贴板（如多行先复制过）
        # 会假阴性、漏翻。
        clip.setText("")
        import keyboard
        try:
            keyboard.send("ctrl+c")
        except Exception:
            pass
        QTimer.singleShot(120, self._finish_capture)

    def _finish_capture(self) -> None:
        # 主线程：读词 + 强制还原剪贴板（无论取词成败）
        clip = QGuiApplication.clipboard()
        captured = clip.text()
        if self._saved_pixmap is not None and not self._saved_pixmap.isNull():
            clip.setPixmap(self._saved_pixmap)
        else:
            clip.setText(self._saved_text)
        # 哨兵法：ctrl+c 前已清空，故 captured 非空 == 取到选区（与旧剪贴板是否相同无关）
        if captured:
            self.captured.emit(captured, QCursor.pos())
