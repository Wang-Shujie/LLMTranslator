"""划词翻译控制器：全局热键 + 模拟 Ctrl+C 取词 + Qt QClipboard 保存/恢复。

热键经 GlobalHotkeyManager（Windows: RegisterHotKey→主线程；其他: keyboard 钩子线程），
_on_hotkey 统一用 QTimer.singleShot(0) 延到主线程执行取词。QClipboard/QCursor/QTimer
只能在主线程用，故取词全程在主线程。ctrl+c 模拟仍用 keyboard 库（模拟按键与检测热键分开）。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication



class SelectionController(QObject):
    """全局热键划词：触发后取选中文本 + 光标位置，发 captured(text, pos)。"""

    captured = Signal(str, QPoint)             # 取词完成（主线程发）

    def __init__(self, settings, hotkey_mgr, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._mgr = hotkey_mgr
        self._handle = None                    # GlobalHotkeyManager 的不透明 handle
        self._saved_text: str = ""
        self._saved_pixmap = None
        if settings.selection_enabled:
            self.enable()

    def enable(self) -> None:
        if self._handle is not None:
            return  # 已注册
        self._handle = self._mgr.register(self._settings.selection_hotkey, self._on_hotkey)

    def disable(self) -> None:
        if self._handle is None:
            return
        self._mgr.unregister(self._handle)
        self._handle = None

    def _on_hotkey(self) -> None:
        # Windows: 主线程(nativeEvent)；其他: keyboard 钩子线程。
        # 统一延到主线程下一轮取词，避免在 nativeEvent 内做剪贴板操作/模拟按键。
        QTimer.singleShot(0, self._do_capture)

    def _do_capture(self) -> None:
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
