"""通用设置对话框（参考百度翻译设置：单列 + 分栏标题 + 左标签右控件行）。

三个分栏：
- 系统设置：翻译引擎与账号（API 填 base_url/key/model + 测试连接；网页登录/清除）；
- 划译设置：启用开关、快捷键、默认语言（外文译入此语言，已是此语言则不译）；
- 截译设置：启用开关、快捷键、默认目标语言。

引擎/账号凭据在各自的"保存/登录"按钮即时写入；划译/截译设置在点"确定"时
一次性写回 Settings 并保存，主窗口随后重新注册热键。
"""
from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.core.language import LANGUAGES
from llm_translator.providers.registry import all_providers
from llm_translator.storage.settings import Settings
from llm_translator.ui.widgets import HotkeyCapture, RoundedDialog, StyledComboBox, ToggleSwitch

# 设置行右侧控件统一宽度（下拉框 / 热键按钮一致）
_CTRL_W = 220


class SettingsDialog(RoundedDialog):
    def __init__(self, credentials: CredentialStore, settings: Settings, parent=None) -> None:
        super().__init__(title="通用设置", parent=parent)
        self.resize(440, 600)
        self.setMinimumSize(440, 380)
        self.credentials = credentials
        self.settings = settings

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content = QWidget()
        content.setStyleSheet("background: #ffffff;")
        self._content = QVBoxLayout(content)
        self._content.setContentsMargins(24, 18, 24, 18)
        self._content.setSpacing(0)

        self._build_system_section()
        self._content.addSpacing(20)
        self._build_selection_section()
        self._content.addSpacing(20)
        self._build_ocr_section()
        self._content.addStretch()
        scroll.setWidget(content)
        self.content_layout.addWidget(scroll, 1)

        # 底部按钮行（透明容器 + 内边距，避免方角盖住卡片圆角）
        btn_row = QWidget()
        btn_row.setObjectName("dlgBtnRow")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 8, 16, 14)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("确定")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        br.addWidget(btns)
        self.content_layout.addWidget(btn_row)

    # ---- 公共布局辅助 ----
    def _section_header(self, title: str) -> None:
        lbl = QLabel(title)
        lbl.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #000000; background: transparent;"
        )
        self._content.addWidget(lbl)

    def _row(self, text: str, control: QWidget) -> None:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(12)
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; color: #333333; background: transparent;")
        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(control)
        self._content.addWidget(w)

    def _hint(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #999999; background: transparent;")
        self._content.addWidget(lbl)

    def _lang_combo(self, current_code: str) -> StyledComboBox:
        cb = StyledComboBox()
        for code, name in LANGUAGES.items():
            if code == "auto":
                continue
            cb.addItem(name, code)
        idx = cb.findData(current_code)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.setFixedHeight(32)
        cb.setFixedWidth(_CTRL_W)
        return cb

    # ---- 系统设置 ----
    def _build_system_section(self) -> None:
        self._section_header("系统设置")
        self._hint("选择翻译引擎，配置 API 或网页登录。")

        # 引擎下拉行（与"默认语言"等下拉行风格一致）
        self._providers = all_providers()
        self.engine_combo = StyledComboBox()
        self.engine_combo.setFixedHeight(32)
        self.engine_combo.setFixedWidth(_CTRL_W)
        for p in self._providers:
            self.engine_combo.addItem(
                f"{p['label']}  ({'API' if p['kind']=='api' else '网页'})", p
            )
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self._row("翻译引擎", self.engine_combo)

        # 详情容器：按选中引擎重建为左标签右控件行
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(0, 4, 0, 0)
        self.detail_layout.setSpacing(0)
        self._content.addWidget(self.detail)
        if self._providers:
            # setCurrentIndex(0) 在组合框已处于 0 时不发信号，故显式构建首引擎面板
            self._on_engine_changed(0)

    def _clear_detail(self) -> None:
        # 递归清空布局（含子布局）并删除其中所有 widget，避免切换引擎残留孤儿按钮（BUG6）。
        self._clear_layout(self.detail_layout)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _on_engine_changed(self, idx: int) -> None:
        if idx < 0:
            return
        meta = self.engine_combo.itemData(idx)
        self._clear_detail()
        if meta["kind"] == "api":
            self._build_api_panel(meta)
        else:
            self._build_web_panel(meta)

    def _detail_input_row(self, text: str, edit: QWidget) -> None:
        """详情区：左标签（定宽对齐）+ 右输入框（展开占满）。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 8, 0, 8)
        h.setSpacing(12)
        lbl = QLabel(text)
        lbl.setFixedWidth(72)
        lbl.setStyleSheet("font-size: 14px; color: #333333; background: transparent;")
        edit.setFixedHeight(32)
        h.addWidget(lbl)
        h.addWidget(edit, 1)
        self.detail_layout.addWidget(w)

    def _detail_control_row(self, text: str, control: QWidget) -> None:
        """详情区：左标签 + 右控件（右对齐，用于按钮/状态等小控件）。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 8, 0, 8)
        h.setSpacing(12)
        lbl = QLabel(text)
        lbl.setFixedWidth(72)
        lbl.setStyleSheet("font-size: 14px; color: #333333; background: transparent;")
        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(control)
        self.detail_layout.addWidget(w)

    def _detail_hint(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #999999; background: transparent;")
        lbl.setContentsMargins(72, 0, 0, 0)
        self.detail_layout.addWidget(lbl)

    def _build_api_panel(self, meta: dict) -> None:
        pid = meta["id"]
        from llm_translator.providers.api.openai_compat import preset_for
        preset = preset_for(pid)
        self._api_base = QLineEdit(self.credentials.get(pid, "base_url") or preset["base_url"])
        self._api_key = QLineEdit(self.credentials.get(pid, "api_key") or "")
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_model = QLineEdit(self.credentials.get(pid, "model") or preset["model"])
        save_btn = QPushButton("保存")
        test_btn = QPushButton("测试连接")
        status = QLabel("")
        status.setStyleSheet("color: #666666; font-size: 12px; background: transparent;")

        self._detail_input_row("Base URL", self._api_base)
        self._detail_input_row("API Key", self._api_key)
        self._detail_input_row("模型名", self._api_model)
        # 凭据行：保存 + 测试连接 + 状态
        actions = QWidget()
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        ah.addWidget(save_btn)
        ah.addWidget(test_btn)
        ah.addWidget(status)
        self._detail_control_row("凭据", actions)

        save_btn.clicked.connect(lambda: self._save_api(pid, status))
        test_btn.clicked.connect(lambda: self._test_api(pid, status))

    def _save_api(self, pid: str, status: QLabel) -> None:
        for key, w in (("base_url", self._api_base), ("api_key", self._api_key), ("model", self._api_model)):
            self.credentials.set(pid, key, w.text().strip())
        status.setText("已保存")

    def _test_api(self, pid: str, status: QLabel) -> None:
        self._save_api(pid, status)
        from llm_translator.providers.registry import get_provider

        credentials = self.credentials

        def worker() -> None:
            async def go():
                p = get_provider(pid, credentials)
                await p.login()
                async for _ in p.translate("hello", "en", "zh"):
                    break  # 只取首 token 即说明连通
                status.setText("● 已连接")
            try:
                asyncio.run(go())
            except Exception as e:
                status.setText(f"✕ 失败：{e}")

        # httpx 要求真实 asyncio 循环，qasync 下会报 "no async event loop"，
        # 故在线程里 asyncio.run 跑；status 是 QLabel，setText 跨线程安全（Queued）。
        threading.Thread(target=worker, daemon=True).start()

    def _build_web_panel(self, meta: dict) -> None:
        pid = meta["id"]
        has = bool(self.credentials.get(pid, "token"))
        status = QLabel(f"{'● 已登录' if has else '○ 未登录'}")
        status.setStyleSheet(
            "font-size: 14px; color: #52c41a;" if has else
            "font-size: 14px; color: #999999;"
        )
        self._detail_control_row("登录状态", status)

        actions = QWidget()
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        login_btn = QPushButton("登录" if not has else "重新登录")
        clear_btn = QPushButton("清除登录")
        ah.addWidget(login_btn)
        ah.addWidget(clear_btn)
        self._detail_control_row("账号", actions)

        self._detail_hint(f"点击登录将打开 {meta['label']} 网页，登录后自动抓取凭据。")

        login_btn.clicked.connect(lambda: self._do_web_login(pid, status))
        clear_btn.clicked.connect(lambda: (self.credentials.delete(pid), status.setText("○ 未登录")))

    def _do_web_login(self, pid: str, status: QLabel) -> None:
        from llm_translator.ui.login_dialog import LoginDialog
        dlg = LoginDialog(provider_id=pid, credentials=self.credentials, parent=self)
        if dlg.exec() == LoginDialog.Accepted and self.credentials.get(pid, "token"):
            status.setText("状态：● 已登录")

    # ---- 划译设置 ----
    def _build_selection_section(self) -> None:
        self._section_header("划译设置")
        self._sel_enable = ToggleSwitch(checked=self.settings.selection_enabled)
        self._row("启用划词翻译", self._sel_enable)
        self._sel_hotkey = HotkeyCapture(value=self.settings.selection_hotkey)
        self._sel_hotkey.setFixedWidth(_CTRL_W)
        self._row("快捷键", self._sel_hotkey)
        self._sel_lang = self._lang_combo(self.settings.selection_default_lang)
        self._row("默认语言", self._sel_lang)
        self._hint("选中外文自动译为此语言；选中文本已是此语言时不翻译、原样显示。")

    # ---- 截译设置 ----
    def _build_ocr_section(self) -> None:
        self._section_header("截译设置")
        self._ocr_enable = ToggleSwitch(checked=self.settings.ocr_enabled)
        self._row("启用截图翻译", self._ocr_enable)
        self._ocr_hotkey = HotkeyCapture(value=self.settings.ocr_hotkey)
        self._ocr_hotkey.setFixedWidth(_CTRL_W)
        self._row("快捷键", self._ocr_hotkey)
        self._ocr_lang = self._lang_combo(self.settings.ocr_default_lang)
        self._row("默认目标语言", self._ocr_lang)
        self._hint("截图选区工具条的初始目标语言，可随时在工具条临时切换。")

    # ---- 确定：一次性写回划译/截译设置 ----
    def accept(self) -> None:
        self.settings.selection_enabled = self._sel_enable.isChecked()
        self.settings.selection_hotkey = self._sel_hotkey.value()
        self.settings.selection_default_lang = self._sel_lang.currentData()
        self.settings.ocr_enabled = self._ocr_enable.isChecked()
        self.settings.ocr_hotkey = self._ocr_hotkey.value()
        self.settings.ocr_default_lang = self._ocr_lang.currentData()
        self.settings.save()
        super().accept()
