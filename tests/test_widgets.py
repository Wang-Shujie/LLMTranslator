"""热键捕获控件：Qt 按键事件 → keyboard 库字符串的转换。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from llm_translator.ui.widgets import qt_key_to_keyboard, qt_event_to_hotkey


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _press(key, mods=Qt.KeyboardModifier(0)):
    return QKeyEvent(QEvent.KeyPress, key, mods, "")


def test_key_name_letters_digits():
    assert qt_key_to_keyboard(Qt.Key_A) == "a"
    assert qt_key_to_keyboard(Qt.Key_1) == "1"
    assert qt_key_to_keyboard(Qt.Key_F5) == "f5"


def test_key_name_specials():
    assert qt_key_to_keyboard(Qt.Key_Space) == "space"
    assert qt_key_to_keyboard(Qt.Key_Return) == "enter"
    assert qt_key_to_keyboard(Qt.Key_Tab) == "tab"


def test_combo_ctrl_shift_t(qapp):
    e = _press(Qt.Key_T, Qt.ControlModifier | Qt.ShiftModifier)
    assert qt_event_to_hotkey(e) == "ctrl+shift+t"


def test_combo_alt_shift_s(qapp):
    e = _press(Qt.Key_S, Qt.AltModifier | Qt.ShiftModifier)
    assert qt_event_to_hotkey(e) == "alt+shift+s"


def test_modifier_only_returns_none(qapp):
    # 只按修饰键 → None（等待主键）
    assert qt_event_to_hotkey(_press(Qt.Key_Control, Qt.ControlModifier)) is None
    assert qt_event_to_hotkey(_press(Qt.Key_Shift, Qt.ShiftModifier)) is None


def test_bare_key_no_modifier(qapp):
    # 裸键也能转出（控件层会校验必须含修饰键，转换函数本身不拦）
    assert qt_event_to_hotkey(_press(Qt.Key_T)) == "t"
