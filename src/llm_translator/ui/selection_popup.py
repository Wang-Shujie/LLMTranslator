"""划词译文明信片：无边框置顶小弹窗，流式译文 + 复制 + 展开主窗口。

复用主窗口的 worker 线程 + asyncio.run + Qt 信号模式：start_translate 在 worker 线程
跑 translator.translate(text, src, tgt, save_history=False)，token 经信号回主线程追加
到 QLabel。关闭方式：本应用内点弹窗外 / Esc / ✕ / 译完 15s 自动隐藏。
"""
from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import Qt, QEvent, QPoint, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SelectionPopup(QWidget):
    """流式译文明信片。"""

    expand_to_main = Signal(str, str)          # source_text, target_text
    _token = Signal(str)
    _finished = Signal(str)
    _error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("background: #ffffff; border: 1px solid #d0d0d0; border-radius: 8px;")
        self.setMinimumWidth(220)
        self.setMaximumWidth(480)
        # 点击本应用内弹窗外区域 → 关闭（跨程序点击由 Esc/✕/自动隐藏兜底）
        if QApplication.instance() is not None:
            QApplication.instance().installEventFilter(self)

        self._src: str = ""
        self._tgt: str = ""
        self._translator = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        self._label = QLabel("翻译中…")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.PlainText)
        self._label.setStyleSheet("color: #000000; font-size: 13px;")
        self._label.setMinimumHeight(20)
        lay.addWidget(self._label)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._copy_btn = QPushButton("📋 复制")
        self._expand_btn = QPushButton("↗ 展开")
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedWidth(28)
        for b in (self._copy_btn, self._expand_btn):
            b.setStyleSheet(
                "QPushButton { border: 1px solid #e0e0e0; border-radius: 6px; padding: 2px 8px; }"
                "QPushButton:hover { border-color: #1890ff; }"
            )
        self._close_btn.setStyleSheet(
            "QPushButton { border: none; color: #888; } QPushButton:hover { color: #e81123; }"
        )
        row.addWidget(self._copy_btn)
        row.addWidget(self._expand_btn)
        row.addStretch()
        row.addWidget(self._close_btn)
        lay.addLayout(row)

        self._copy_btn.clicked.connect(self._on_copy)
        self._expand_btn.clicked.connect(self._on_expand)
        self._close_btn.clicked.connect(self.hide)
        self._token.connect(self._on_token)
        self._finished.connect(self._on_finished)
        self._error.connect(self._on_error)

    def show_at(self, pos: QPoint) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x, y = pos.x() + 16, pos.y() + 16
            if x + self.width() > geo.right():
                x = pos.x() - 16 - self.width()
            if y + self.height() > geo.bottom():
                y = pos.y() - 16 - self.height()
            x = max(geo.left(), min(x, geo.right() - self.width()))
            y = max(geo.top(), min(y, geo.bottom() - self.height()))
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def start_translate(self, text: str, src: str, tgt: str, translator) -> None:
        self._src = text
        self._tgt = ""
        self._translator = translator
        self._label.setText("翻译中…")
        translator_ref = translator

        def worker() -> None:
            async def drain():
                collected: list[str] = []
                async for tok in translator_ref.translate(text, src, tgt, save_history=False):
                    collected.append(tok)
                    self._token.emit(tok)
                self._finished.emit("".join(collected))

            try:
                asyncio.run(drain())
            except Exception as e:
                self._error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_token(self, tok: str) -> None:
        if self._label.text() == "翻译中…":
            self._label.setText("")
        self._label.setText(self._label.text() + tok)

    def _on_finished(self, full: str) -> None:
        self._tgt = full
        # 译完 15s 后自动隐藏，避免遗忘时长期置顶
        QTimer.singleShot(15000, self.hide)

    def _on_error(self, msg: str) -> None:
        self._label.setText(f"❌ {msg}")
        QTimer.singleShot(8000, self.hide)

    def _on_copy(self) -> None:
        if self._tgt:
            QApplication.clipboard().setText(self._tgt)

    def _on_expand(self) -> None:
        if self._tgt or self._src:
            self.expand_to_main.emit(self._src, self._tgt)
        self.hide()

    def eventFilter(self, _obj, event) -> bool:
        # 本应用内点弹窗外 → 关闭（跨程序点击 Qt 收不到事件，靠 Esc/✕/自动隐藏）
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.hide()
        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
