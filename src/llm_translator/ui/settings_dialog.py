"""设置对话框：左 provider 列表 + 右详情面板。

API 类：填 base_url / api_key / model + 测试连接。
Web 类：显示登录状态 + 登录按钮（弹 LoginDialog）。
"""
from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.registry import all_providers
from llm_translator.storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, credentials: CredentialStore, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(640, 460)
        self.credentials = credentials
        self.settings = settings

        layout = QHBoxLayout(self)
        # 左：provider 列表
        self.list_widget = QListWidget()
        self._providers = all_providers()
        for p in self._providers:
            it = QListWidgetItem(f"{p['label']}  ({'API' if p['kind']=='api' else '网页'})")
            it.setData(Qt.UserRole, p)
            self.list_widget.addItem(it)
        self.list_widget.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list_widget, 1)

        # 右：详情容器
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        layout.addWidget(self.detail, 2)
        self._placeholder = QLabel("选择左侧的模型进行配置")
        self.detail_layout.addWidget(self._placeholder)

        if self._providers:
            self.list_widget.setCurrentRow(0)

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        meta = self.list_widget.item(row).data(Qt.UserRole)
        self._clear_detail()
        if meta["kind"] == "api":
            self._build_api_panel(meta)
        else:
            self._build_web_panel(meta)

    def _build_api_panel(self, meta: dict) -> None:
        pid = meta["id"]
        self._api_base = QLineEdit(self.credentials.get(pid, "base_url") or "")
        self._api_key = QLineEdit(self.credentials.get(pid, "api_key") or "")
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_model = QLineEdit(self.credentials.get(pid, "model") or "")
        save_btn = QPushButton("保存")
        test_btn = QPushButton("测试连接")
        status = QLabel("")

        for lbl, w in [("Base URL", self._api_base), ("API Key", self._api_key), ("模型名", self._api_model)]:
            self.detail_layout.addWidget(QLabel(lbl))
            self.detail_layout.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(save_btn)
        row.addWidget(test_btn)
        row.addStretch()
        self.detail_layout.addLayout(row)
        self.detail_layout.addWidget(status)
        self.detail_layout.addStretch()

        save_btn.clicked.connect(lambda: self._save_api(pid, status))
        test_btn.clicked.connect(lambda: self._test_api(pid, status))

    def _save_api(self, pid: str, status: QLabel) -> None:
        for key, w in (("base_url", self._api_base), ("api_key", self._api_key), ("model", self._api_model)):
            self.credentials.set(pid, key, w.text().strip())
        status.setText("已保存")

    def _test_api(self, pid: str, status: QLabel) -> None:
        self._save_api(pid, status)
        from llm_translator.providers.registry import get_provider

        async def go():
            try:
                p = get_provider(pid, self.credentials)
                await p.login()
                async for _ in p.translate("hello", "en", "zh"):
                    break  # 只取首 token 即说明连通
                status.setText("● 已连接")
            except Exception as e:
                status.setText(f"✕ 失败：{e}")

        asyncio.get_event_loop().create_task(go())

    def _build_web_panel(self, meta: dict) -> None:
        pid = meta["id"]
        has = bool(self.credentials.get(pid, "token"))
        status = QLabel(f"状态：{'● 已登录' if has else '○ 未登录'}")
        login_btn = QPushButton("登录" if not has else "重新登录")
        clear_btn = QPushButton("清除登录")
        hint = QLabel(f"点击登录将打开 {meta['label']} 网页，登录后自动抓取凭据。")
        hint.setWordWrap(True)

        self.detail_layout.addWidget(QLabel(f"<b>{meta['label']}</b>（网页免费）"))
        self.detail_layout.addWidget(status)
        row = QHBoxLayout()
        row.addWidget(login_btn)
        row.addWidget(clear_btn)
        row.addStretch()
        self.detail_layout.addLayout(row)
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

        login_btn.clicked.connect(lambda: self._do_web_login(pid, status))
        clear_btn.clicked.connect(lambda: (self.credentials.delete(pid), status.setText("状态：○ 未登录")))

    def _do_web_login(self, pid: str, status: QLabel) -> None:
        from llm_translator.ui.login_dialog import LoginDialog
        dlg = LoginDialog(provider_id=pid, credentials=self.credentials, parent=self)
        if dlg.exec() == LoginDialog.Accepted and self.credentials.get(pid, "token"):
            status.setText("状态：● 已登录")
