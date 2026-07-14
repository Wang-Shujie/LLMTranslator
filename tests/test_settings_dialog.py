"""回归测试：设置面板切换 provider 不残留旧按钮。

BUG6：_clear_detail 只删直接 widget，子布局里的按钮（保存/测试连接）残留为孤儿，
导致网页面板上出现无意义且点击失效的 API 按钮。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from llm_translator.ui.settings_dialog import SettingsDialog
from llm_translator.auth.store import CredentialStore
from llm_translator.storage.settings import Settings


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _buttons(dlg) -> list[str]:
    return [b.text() for b in dlg.detail.findChildren(QPushButton)]


def test_switching_panels_does_not_leave_orphan_buttons(qapp, data_dir):
    dlg = SettingsDialog(CredentialStore(), Settings())
    # 引擎顺序：deepseek-api, glm-api, openai（API）；glm-web, kimi-web, deepseek-web（网页）
    dlg.engine_combo.setCurrentIndex(0); qapp.processEvents()
    assert _buttons(dlg) == ["保存", "测试连接"]

    dlg.engine_combo.setCurrentIndex(3); qapp.processEvents()  # glm-web
    assert _buttons(dlg) == ["登录", "清除登录"]  # 不应残留 保存/测试连接

    dlg.engine_combo.setCurrentIndex(4); qapp.processEvents()  # kimi-web
    assert _buttons(dlg) == ["登录", "清除登录"]

    dlg.engine_combo.setCurrentIndex(1); qapp.processEvents()  # 切回 API
    assert _buttons(dlg) == ["保存", "测试连接"]
