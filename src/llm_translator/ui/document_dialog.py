"""文档翻译对话框：选文件 → 翻译（worker 线程）→ 进度 + 完成/取消。"""
from __future__ import annotations

import asyncio
import os
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QDialog,
    QWidget,
)

from llm_translator.core.doc_translate import DocumentTranslator, PerParagraphGranularity
from llm_translator.core.language import LANGUAGES
from llm_translator.ui.widgets import StyledComboBox


class DocumentDialog(QDialog):
    """选 .docx/.txt → 逐段翻译 → 输出同格式译文。"""

    _progress = Signal(int, int)   # done, total
    _finished = Signal(str)         # out_path
    _error = Signal(str)

    def __init__(self, credentials, settings, parent=None) -> None:
        super().__init__(parent)
        self._credentials = credentials
        self._settings = settings
        self._file_path: str = ""
        self._cancelled = False
        self.setWindowTitle("文档翻译")
        self.resize(480, 280)
        lay = QVBoxLayout(self)

        # 文件选择
        row1 = QHBoxLayout()
        self._file_label = QLabel("未选择文件")
        self._pick_btn = QPushButton("选择文件…")
        self._pick_btn.clicked.connect(self._pick_file)
        row1.addWidget(self._file_label, stretch=1)
        row1.addWidget(self._pick_btn)
        lay.addLayout(row1)

        # 语言
        row2 = QHBoxLayout()
        self._src_combo = StyledComboBox()
        self._tgt_combo = StyledComboBox()
        for code, name in LANGUAGES.items():
            self._src_combo.addItem(name, code)
            self._tgt_combo.addItem(name, code)
        self._src_combo.setCurrentIndex(self._src_combo.findData(self.settings.src_lang))
        self._tgt_combo.setCurrentIndex(self._tgt_combo.findData(self.settings.tgt_lang))
        swap_btn = QPushButton("⇌")
        swap_btn.setFixedWidth(30)
        swap_btn.clicked.connect(self._swap)
        row2.addWidget(self._src_combo)
        row2.addWidget(swap_btn)
        row2.addWidget(self._tgt_combo)
        lay.addLayout(row2)

        # 输出路径
        self._output_label = QLabel("输出：—")
        lay.addWidget(self._output_label)

        # 进度
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        lay.addWidget(self._progress_bar)

        # 按钮
        row3 = QHBoxLayout()
        self._translate_btn = QPushButton("翻译")
        self._translate_btn.setObjectName("primaryBtn")
        self._translate_btn.setEnabled(False)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setEnabled(False)
        self._close_btn = QPushButton("关闭")
        row3.addStretch()
        row3.addWidget(self._translate_btn)
        row3.addWidget(self._cancel_btn)
        row3.addWidget(self._close_btn)
        lay.addLayout(row3)

        self._translate_btn.clicked.connect(self._on_translate)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._close_btn.clicked.connect(self.close)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._error.connect(self._on_error)

    @property
    def settings(self):
        return self._settings

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择文档", "", "文档 (*.docx *.txt)")
        if path:
            self._file_path = path
            self._file_label.setText(os.path.basename(path))
            self._translate_btn.setEnabled(True)
            self._update_output_path()

    def _update_output_path(self) -> None:
        if not self._file_path:
            return
        d = self._settings.doc_output_dir or os.path.dirname(self._file_path)
        base = os.path.splitext(os.path.basename(self._file_path))[0]
        ext = os.path.splitext(self._file_path)[1]
        tgt = self._tgt_combo.currentData()
        out = os.path.join(d, f"{base}_{tgt}{ext}")
        self._output_label.setText(f"输出：{out}")
        self._out_path = out

    def _swap(self) -> None:
        si, ti = self._src_combo.currentIndex(), self._tgt_combo.currentIndex()
        self._src_combo.setCurrentIndex(ti)
        self._tgt_combo.setCurrentIndex(si)

    def _on_translate(self) -> None:
        from llm_translator.providers.registry import get_provider
        pid = self._settings.default_provider
        try:
            provider = get_provider(pid, self._credentials)
        except Exception:
            self._error.emit("请先在设置中配置一个模型。")
            return
        self._cancelled = False
        self._translate_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        src = self._src_combo.currentData()
        tgt = self._tgt_combo.currentData()

        granularity = PerParagraphGranularity(concurrency=self._settings.doc_concurrency)
        translator = DocumentTranslator(granularity)
        file_path = self._file_path
        out_path = self._out_path

        def worker():
            async def run():
                handler_result = translator.translate_document(file_path, out_path, provider, src, tgt)
                # We can't easily get per-segment progress without restructuring;
                # for v1, show indeterminate → done.
                count = await handler_result
                self._progress.emit(count, count)
                self._finished.emit(out_path)
            try:
                asyncio.run(run())
            except Exception as e:
                self._error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._translate_btn.setEnabled(True)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setValue(int(done / total * 100))

    def _on_finished(self, out_path: str) -> None:
        self._progress_bar.setValue(100)
        self._cancel_btn.setEnabled(False)
        self._translate_btn.setEnabled(True)
        self._output_label.setText(f"完成：{out_path}")

    def _on_error(self, msg: str) -> None:
        self._cancel_btn.setEnabled(False)
        self._translate_btn.setEnabled(True)
        self._output_label.setText(f"错误：{msg}")
