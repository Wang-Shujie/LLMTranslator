"""主窗口：顶部语言栏 + 上下输入输出双栏 + 状态栏。对照参考图。"""
from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.core.language import LANGUAGES
from llm_translator.core.translator import Translator
from llm_translator.providers.registry import all_providers, get_provider
from llm_translator.storage.history import HistoryStore
from llm_translator.storage.settings import Settings
from llm_translator.ui.async_bridge import TokenEmitter
from llm_translator.ui.settings_dialog import SettingsDialog
from llm_translator.ui.history_dialog import HistoryDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LLM 翻译")
        self.resize(720, 560)

        # 持久化与编排
        self.settings = Settings.load()
        self.credentials = CredentialStore()
        self.history = HistoryStore()
        self.emitter = TokenEmitter()
        self._current_task = None
        self._build_translator()

        self._build_ui()
        self._wire_signals()

    def _build_translator(self) -> None:
        pid = self.settings.default_provider
        try:
            provider = get_provider(pid, self.credentials)
        except KeyError:
            provider = None
        if provider is None:
            self.translator = None
            return
        self.translator = Translator(provider=provider, history=self.history, provider_label=pid)

    # ---- UI 构建 ----
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        # 顶部语言栏
        top = QHBoxLayout()
        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.src_combo.addItem(name, code)
            self.tgt_combo.addItem(name, code)
        self.src_combo.setCurrentIndex(self.src_combo.findData(self.settings.src_lang))
        self.tgt_combo.setCurrentIndex(self.tgt_combo.findData(self.settings.tgt_lang))
        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setFixedWidth(40)
        self.provider_combo = QComboBox()
        for p in all_providers():
            self.provider_combo.addItem(p["label"], p["id"])
        idx = self.provider_combo.findData(self.settings.default_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.menu_btn = QPushButton("☰")
        menu = QMenu(self)  # 父对象 = 主窗口，避免无主 QMenu 被 GC 回收导致菜单丢失
        menu.addAction("设置", self.on_settings)
        menu.addAction("历史记录", self.open_history)
        menu.addAction("关于", self.on_about)
        self.menu_btn.setMenu(menu)
        top.addWidget(self.src_combo)
        top.addWidget(self.swap_btn)
        top.addWidget(self.tgt_combo)
        top.addStretch()
        top.addWidget(self.provider_combo)
        top.addWidget(self.menu_btn)
        root.addLayout(top)

        # 源文本输入
        self.src_edit = QPlainTextEdit()
        self.src_edit.setPlaceholderText("输入要翻译的文本，按 Ctrl+Enter 翻译")
        self.clear_btn = QPushButton("✕ 清空")
        input_row = QHBoxLayout()
        input_row.addWidget(self.src_edit)
        col = QVBoxLayout()
        col.addWidget(self.clear_btn)
        col.addStretch()
        input_row.addLayout(col)
        root.addLayout(input_row, stretch=5)

        # 翻译按钮
        self.translate_btn = QPushButton("翻译  (Ctrl+Enter)")
        self.translate_btn.setObjectName("primaryBtn")
        root.addWidget(self.translate_btn)

        # 译文输出
        self.tgt_edit = QPlainTextEdit()
        self.tgt_edit.setReadOnly(True)
        self.tgt_edit.setPlaceholderText("译文将在此显示")
        out_row = QHBoxLayout()
        out_row.addWidget(self.tgt_edit, stretch=1)
        out_col = QVBoxLayout()
        self.copy_btn = QPushButton("📋 复制")
        out_col.addWidget(self.copy_btn)
        out_col.addStretch()
        out_row.addLayout(out_col)
        root.addLayout(out_row, stretch=5)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_status()

        self.setCentralWidget(central)

    # ---- 信号 ----
    def _wire_signals(self) -> None:
        self.translate_btn.clicked.connect(self.on_translate)
        self.clear_btn.clicked.connect(lambda: self.src_edit.clear())
        self.copy_btn.clicked.connect(self.on_copy)
        self.swap_btn.clicked.connect(self.on_swap)
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self.emitter.token_received.connect(self._on_token)
        self.emitter.finished.connect(self._on_finished)
        self.emitter.error.connect(self._on_error)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.on_translate)

    # ---- 动作 ----
    def on_translate(self) -> None:
        if self.translator is None:
            QMessageBox.warning(self, "未配置", "请先在设置中选择并配置一个模型。")
            return
        text = self.src_edit.toPlainText().strip()
        if not text:
            return
        self.tgt_edit.clear()
        self.translate_btn.setEnabled(False)
        self.status.showMessage("翻译中…")

        src = self.src_combo.currentData()
        tgt = self.tgt_combo.currentData()

        # 网页 provider 用 curl_cffi，其异步客户端要求真实 asyncio 事件循环；
        # 而 qasync 不是标准 asyncio loop，curl_cffi 会 RuntimeError(no running event loop)。
        # 故网页翻译放进 worker 线程里用 asyncio.run 跑，token 经 Qt 信号回到主线程。
        if self.translator.provider.kind == "web":
            self._run_web_translate(text, src, tgt)
            return

        async def run():
            collected = []
            try:
                async for tok in self.translator.translate(text, src, tgt):
                    collected.append(tok)
                    self.emitter.token_received.emit(tok)
                self.emitter.finished.emit("".join(collected))
            except Exception as e:  # Provider 隔离：错误只反馈给 UI
                self.emitter.error.emit(str(e))

        loop = asyncio.get_event_loop()
        self._current_task = loop.create_task(run())

    def _run_web_translate(self, text: str, src: str, tgt: str) -> None:
        translator = self.translator
        emitter = self.emitter

        def worker() -> None:
            async def drain():
                collected = []
                async for tok in translator.translate(text, src, tgt):
                    collected.append(tok)
                    emitter.token_received.emit(tok)
                emitter.finished.emit("".join(collected))
            try:
                asyncio.run(drain())
            except Exception as e:  # Provider 隔离：错误只反馈给 UI
                emitter.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_token(self, tok: str) -> None:
        self.tgt_edit.insertPlainText(tok)

    def _on_finished(self, _full: str) -> None:
        self.translate_btn.setEnabled(True)
        self.status.showMessage("完成", 3000)
        self._update_status()

    def _on_error(self, msg: str) -> None:
        self.translate_btn.setEnabled(True)
        self.status.showMessage(f"错误：{msg}", 5000)

    def on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.tgt_edit.toPlainText())

    def on_swap(self) -> None:
        si, ti = self.src_combo.currentIndex(), self.tgt_combo.currentIndex()
        self.src_combo.setCurrentIndex(ti)
        self.tgt_combo.setCurrentIndex(si)

    def on_provider_changed(self, _idx: int) -> None:
        pid = self.provider_combo.currentData()
        self.settings.default_provider = pid
        self.settings.save()
        try:
            provider = get_provider(pid, self.credentials)
        except KeyError:
            return
        if self.translator is None:
            self.translator = Translator(provider=provider, history=self.history, provider_label=pid)
        else:
            self.translator.set_provider(provider, pid)
        self._update_status()

    def on_settings(self) -> None:
        dlg = SettingsDialog(self.credentials, self.settings, self)
        dlg.exec()
        self._build_translator()
        self._update_status()

    def on_about(self) -> None:
        from llm_translator import __version__
        QMessageBox.information(
            self, "关于", f"LLMTranslator v{__version__}\n基于大语言模型的桌面翻译软件。"
        )

    def _update_status(self) -> None:
        pid = self.settings.default_provider
        label = next((p["label"] for p in all_providers() if p["id"] == pid), pid)
        healthy = self.translator.provider.health() if self.translator else False
        dot = "●" if healthy else "○"
        self.status.showMessage(f"{dot} {label} {'已就绪' if healthy else '未配置/未登录'}")

    def open_history(self) -> None:
        HistoryDialog(self.history, self).exec()
