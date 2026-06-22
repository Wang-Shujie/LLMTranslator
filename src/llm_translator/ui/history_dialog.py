"""历史记录对话框：列表 + 搜索框 + 清空。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from llm_translator.storage.history import HistoryStore


class HistoryDialog(QDialog):
    def __init__(self, history: HistoryStore, parent=None) -> None:
        super().__init__(parent)
        self.history = history
        self.setWindowTitle("历史记录")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索原文/译文…")
        self.search.textChanged.connect(self._reload)
        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.clicked.connect(self._clear)
        top.addWidget(self.search)
        top.addWidget(self.clear_btn)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)
        self._reload()

    def _reload(self) -> None:
        q = self.search.text().strip()
        rows = self.history.search(q, limit=200) if q else self.history.list(limit=200)
        self.list_widget.clear()
        for e in rows:
            text = f"[{e.provider}] {e.source_text}  →  {e.target_text}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, e)
            self.list_widget.addItem(it)

    def _clear(self) -> None:
        self.history.clear()
        self._reload()
