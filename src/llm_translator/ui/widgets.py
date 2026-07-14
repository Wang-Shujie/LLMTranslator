"""跨 UI 复用的小控件：iOS 风格拨动开关、细分隔线、热键捕获。

热键捕获产物为 `keyboard` 库兼容的字符串（如 "ctrl+shift+t"），供
SelectionController / OcrController 直接 add_hotkey。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QPoint, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# Qt 键名 → keyboard 库键名（仅覆盖与默认 toString 不一致的）
_KEY_OVERRIDES = {
    "return": "enter",
    "enter": "enter",
    "esc": "esc",
    "delete": "delete",
    "backspace": "backspace",
    "tab": "tab",
    "space": "space",
}


def qt_key_to_keyboard(key: int) -> str:
    """单个 Qt key → keyboard 库键名（小写）。"""
    name = QKeySequence(key).toString().lower()
    return _KEY_OVERRIDES.get(name, name)


def qt_event_to_hotkey(event) -> str | None:
    """Qt 按键事件 → "ctrl+shift+t" 形式组合；仅修饰键时返回 None（等待主键）。"""
    key = event.key()
    if key in (0, Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
        return None
    mods = event.modifiers()
    parts: list[str] = []
    if mods & Qt.ControlModifier:
        parts.append("ctrl")
    if mods & Qt.AltModifier:
        parts.append("alt")
    if mods & Qt.ShiftModifier:
        parts.append("shift")
    if mods & Qt.MetaModifier:
        parts.append("win")
    parts.append(qt_key_to_keyboard(key))
    return "+".join(parts)


class HSeparator(QWidget):
    """细分隔线。"""

    def __init__(self, parent=None, color: str = "#ececec") -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(1)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(self._color), 1))
        painter.drawLine(0, 0, self.width(), 0)


class ToggleSwitch(QWidget):
    """iOS 风格拨动开关：蓝轨道（开）/ 灰轨道（关）+ 白色滑块。

    仅响应用户鼠标点击发 toggled；setChecked 为程序化同步，不发信号（避免回环）。
    """

    toggled = Signal(bool)

    def __init__(self, checked: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._knob = 12  # 滑块直径
        self.setFixedSize(30, 16)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, on: bool) -> None:
        """程序化设置：只刷新外观，不发信号。"""
        self._checked = on
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1890ff") if self._checked else QColor("#cccccc"))
        painter.drawRoundedRect(self.rect(), 8, 8)
        # 滑块：关→左，开→右
        x = self.width() - self._knob - 2 if self._checked else 2
        k = self._knob
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPoint(x + k // 2, self.height() // 2), k // 2, k // 2)


class HotkeyCapture(QWidget):
    """热键捕获：点击按钮 → 录制 → 按下组合键确认（产物为 keyboard 库格式）。

    - 录制中按 Esc 取消、按纯修饰键继续等待；
    - 要求至少一个 Ctrl/Shift/Alt/Win，避免裸键全局热键吞掉正常输入；
    - changed(combo) 在确认/清空时发出；combo=="" 表示清除；
    - 按钮填满本控件宽度，setFixedWidth 可与下拉框统一长度。
    """

    changed = Signal(str)

    def __init__(self, value: str = "", parent=None) -> None:
        super().__init__(parent)
        self._value = value
        self._recording = False
        self._btn = QPushButton(value or "点击设置快捷键")
        self._btn.setFixedHeight(32)
        self._btn.setMinimumWidth(160)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.installEventFilter(self)
        self._btn.clicked.connect(self._toggle_record)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._btn, 1)  # 按钮填满控件宽度

    def value(self) -> str:
        return self._value

    def setValue(self, v: str) -> None:
        self._value = v
        self._btn.setText(v or "点击设置快捷键")
        self._btn.setStyleSheet("")

    def _toggle_record(self) -> None:
        if self._recording:
            self._cancel_record()
        else:
            self._start_record()

    def _start_record(self) -> None:
        self._recording = True
        self._btn.setText("按下快捷键…（Esc 取消）")
        self._btn.setStyleSheet("QPushButton { color: #1890ff; }")
        self._btn.setFocus()
        self._btn.grabKeyboard()

    def _cancel_record(self) -> None:
        self._recording = False
        self._btn.releaseKeyboard()
        self._btn.setText(self._value or "点击设置快捷键")
        self._btn.setStyleSheet("")

    def _commit(self, combo: str) -> None:
        self._recording = False
        self._btn.releaseKeyboard()
        self._value = combo
        self._btn.setText(combo or "点击设置快捷键")
        self._btn.setStyleSheet("")
        self.changed.emit(combo)

    def eventFilter(self, _obj, event) -> bool:
        if not self._recording:
            return False
        et = event.type()
        if et == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._cancel_record()
                return True
            combo = qt_event_to_hotkey(event)
            if combo:
                parts = set(combo.split("+"))
                if not (parts & {"ctrl", "shift", "alt", "win"}):
                    self._btn.setText("需包含 Ctrl/Shift/Alt…")
                    return True
                self._commit(combo)
            return True
        if et == QEvent.FocusOut:
            self._cancel_record()
        return False


class StyledComboBox(QComboBox):
    """统一风格下拉框：隐藏 Windows 原生箭头，自绘一个美观的小倒三角 ▾。

    QSS 把 ::down-arrow 置空（原生箭头不画），drop-down 预留右侧箭头区，
    paintEvent 在原生绘制（边框/文字）之上补画一个小三角。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QComboBox { background: #ffffff; border: 1px solid #e0e0e0; "
            "border-radius: 6px; padding: 4px 26px 4px 10px; color: #333333; font-size: 14px; }"
            "QComboBox:hover { border-color: #1890ff; }"
            "QComboBox:focus { border-color: #1890ff; }"
            "QComboBox::drop-down { width: 24px; border: none; background: transparent; }"
            "QComboBox::down-arrow { image: none; width: 0; height: 0; }"
            "QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #e0e0e0; "
            "selection-background-color: #e6f7ff; selection-color: #1890ff; outline: none; }"
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#999999"))
        r = self.rect()
        cx = r.right() - 17
        cy = r.center().y()
        painter.drawPolygon(
            QPolygon([QPoint(cx - 4, cy - 2), QPoint(cx + 4, cy - 2), QPoint(cx, cy + 3)])
        )


class _RoundedCard(QWidget):
    """圆角白底卡片：自绘圆角白底 + 边框（配合窗口 WA_TranslucentBackground 实现真圆角）。

    与主窗口 _RoundedFrame 一致的画法。
    """

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#d0d0d0"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)


class _DialogTitleBar(QWidget):
    """对话框标题栏：左侧标题 + 右侧 ✕，按住空白区拖动窗口。"""

    def __init__(self, dialog: QDialog, title: str = "") -> None:
        super().__init__(dialog)
        self._dlg = dialog
        self._drag_pos: QPoint | None = None
        self.setObjectName("dlgTitleBar")
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 6, 0)
        lay.setSpacing(0)
        self._title = QLabel(title)
        self._title.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #000000; background: transparent;"
        )
        lay.addWidget(self._title)
        lay.addStretch()
        close = QPushButton("✕")
        close.setFixedSize(36, 28)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #888888; font-size: 14px; }"
            "QPushButton:hover { background: #e81123; color: #ffffff; border-radius: 4px; }"
        )
        close.clicked.connect(dialog.reject)
        lay.addWidget(close)

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._dlg.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self._dlg.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_pos = None


class RoundedDialog(QDialog):
    """无边框圆角对话框（与主窗口风格一致）：透明窗口 + 自绘圆角白卡 + 可拖动标题栏。

    子类把内容加到 self.content_layout（标题栏 + 分隔线下方）。
    圆角靠"窗口透明 + 卡片自绘圆角白底"实现，结构层（卡片/标题栏/内容/按钮行）
    背景透明，避免方角盖住卡片圆角。
    """

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 标记为可边缘缩放的无边框窗口（供 _ResizeFilter 识别；划词弹窗等不置此标记）
        self._edge_resizable = True
        self.setStyleSheet(
            "QDialog { background: transparent; }"
            "QWidget#dlgCard, QWidget#dlgTitleBar, QWidget#dlgContent, "
            "QWidget#dlgBtnRow { background: transparent; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = _RoundedCard()
        self._card.setObjectName("dlgCard")
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        self._title_bar = _DialogTitleBar(self, title)
        card_lay.addWidget(self._title_bar)
        card_lay.addWidget(HSeparator(self._card, color="#ececec"))

        self.content = QWidget()
        self.content.setObjectName("dlgContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        card_lay.addWidget(self.content, 1)

        outer.addWidget(self._card)

    def set_dialog_title(self, title: str) -> None:
        self._title_bar.set_title(title)

