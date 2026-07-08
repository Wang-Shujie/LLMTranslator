"""截图 OCR 结果渲染：原地覆盖 / 对照 / 直接翻译面板。

共享 paint_translated_blocks(painter, blocks, bg_mode)：
  每块 bbox 填底色 → 画译文（字号适配框宽高）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def paint_translated_blocks(
    painter: QPainter,
    canvas: QPixmap | QImage,
    blocks: list[tuple[str, tuple[int, int, int, int]]],
    cover_original: bool,
) -> None:
    """在 canvas 上绘制译文字块。cover_original=True 时先填底色盖原文。"""
    painter.drawPixmap(0, 0, canvas) if isinstance(canvas, QPixmap) else painter.drawImage(0, 0, canvas)
    for text, (x, y, w, h) in blocks:
        if cover_original:
            painter.fillRect(QRect(x, y, w, h), QColor("#ffffff"))
        # 字号适配框高
        font_size = max(8, min(int(h * 0.7), 20))
        font = QFont("Microsoft YaHei", font_size)
        painter.setFont(font)
        painter.setPen(QColor("#000000"))
        rect = QRect(x + 2, y, w - 4, h)
        painter.drawText(rect, Qt.TextWordWrap | Qt.AlignVCenter, text)


class _BaseResultWindow(QWidget):
    """结果窗口基类：无边框置顶 + Esc 关闭 + 自动隐藏。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        if QApplication.instance() is not None:
            QApplication.instance().installEventFilter(self)

    def eventFilter(self, _obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.hide()
        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


class OverlayResultWindow(_BaseResultWindow):
    """原地覆盖：译文叠在截图上，盖住原文。定位到截图原位置。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._blocks: list[tuple[str, tuple[int, int, int, int]]] = []

    def show_result(self, pixmap: QPixmap, blocks, pos) -> None:
        self._pixmap = pixmap
        self._blocks = blocks
        self.resize(pixmap.size())
        if pos is not None:
            self.move(pos)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        paint_translated_blocks(painter, self._pixmap, self._blocks, cover_original=True)
        painter.end()


class CompareResultWindow(_BaseResultWindow):
    """对照：白底画布按 bbox 画译文（镜像版面），与原图上下对比。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._blocks: list[tuple[str, tuple[int, int, int, int]]] = []

    def show_result(self, pixmap: QPixmap, blocks, pos) -> None:
        self._pixmap = pixmap
        self._blocks = blocks
        self.resize(pixmap.size())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        for text, (x, y, w, h) in self._blocks:
            font_size = max(8, min(int(h * 0.7), 20))
            painter.setFont(QFont("Microsoft YaHei", font_size))
            painter.setPen(QColor("#000000"))
            painter.drawText(QRect(x + 2, y, w - 4, h), Qt.TextWordWrap | Qt.AlignVCenter, text)
        painter.end()


class OcrDirectPanel(_BaseResultWindow):
    """直接翻译面板：上 OCR 原文，下流式译文。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR 翻译结果")
        self.resize(420, 360)
        lay = QVBoxLayout(self)
        self._src_edit = QTextEdit()
        self._src_edit.setReadOnly(True)
        self._src_edit.setPlaceholderText("OCR 原文")
        lay.addWidget(self._src_edit, stretch=1)
        self._tgt_edit = QTextEdit()
        self._tgt_edit.setReadOnly(True)
        self._tgt_edit.setPlaceholderText("译文")
        lay.addWidget(self._tgt_edit, stretch=1)
        row = QHBoxLayout()
        copy_btn = QPushButton("📋 复制译文")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._tgt_edit.toPlainText()))
        row.addWidget(copy_btn)
        row.addStretch()
        close_btn = QPushButton("✕ 关闭")
        close_btn.clicked.connect(self.hide)
        row.addWidget(close_btn)
        lay.addLayout(row)

    def set_source(self, text: str) -> None:
        self._src_edit.setPlainText(text)

    def append_token(self, tok: str) -> None:
        self._tgt_edit.insertPlainText(tok)

    def set_translation(self, full: str) -> None:
        self._tgt_edit.setPlainText(full)

    def set_error(self, msg: str) -> None:
        self._tgt_edit.setPlainText(f"❌ {msg}")
