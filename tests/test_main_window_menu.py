"""回归测试：☰ 菜单按钮的 QMenu 不可被 GC 回收。

BUG：main_window 里 `menu = QMenu()` 无父对象，只被局部变量持有。
在真实 MainWindow 中（_build_ui 创建大量兄弟控件 + show/事件循环搅动）
被 Python GC 回收，导致 menu_btn.menu() 为 None，点击按钮无菜单可弹。

修复：menu = QMenu(self) 给主窗口当父对象。
"""
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from llm_translator.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_menu_button_keeps_its_menu(qapp, data_dir):
    win = MainWindow()
    win.show()
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()

    menu = win._main_menu
    assert menu is not None, "菜单按钮的 QMenu 被回收"
    assert [a.text() for a in menu.actions()] == [
        "设置",
        "历史记录",
        "划词翻译 (Ctrl+Shift+T)",
        "截图 OCR (Ctrl+Shift+O)",
        "文档翻译…",
        "关于",
    ]
