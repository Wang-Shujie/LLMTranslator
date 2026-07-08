"""截图覆盖层：全屏暗化 + 拖框选区 + 工具条（语言/对照/直接翻译/翻译/✕）。

选区确定后点"翻译" → 发 capture_selected(crop_image, mode, src, tgt)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)


class CaptureOverlay(QWidget):
    """全屏截图选区覆盖层。"""

    capture_selected = Signal(QPixmap, str, str, str)  # crop_image, mode, src, tgt

    def __init__(self, frozen: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._frozen = frozen
        self._origin: QPoint | None = None
        self._rect: QRect | None = None
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 工具条（选区确定后显示）
        self._toolbar = QWidget(self)
        self._toolbar.setFixedHeight(36)
        self._toolbar.hide()
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(4, 2, 4, 2)
        self._src_combo = QComboBox()
        self._src_combo.addItem("自动检测", "auto")
        for code, name in [("zh", "中文"), ("en", "英语"), ("ja", "日语")]:
            self._src_combo.addItem(name, code)
        self._swap_btn = QPushButton("⇌")
        self._swap_btn.setFixedWidth(30)
        self._tgt_combo = QComboBox()
        for code, name in [("zh", "中文"), ("en", "英语"), ("ja", "日语")]:
            self._tgt_combo.addItem(name, code)
        self._tgt_combo.setCurrentIndex(1)
        self._compare_btn = QToolButton()
        self._compare_btn.setText("对照")
        self._compare_btn.setCheckable(True)
        self._compare_btn.setChecked(True)
        self._direct_btn = QToolButton()
        self._direct_btn.setText("直接翻译")
        self._direct_btn.setCheckable(True)
        self._translate_btn = QPushButton("翻译")
        self._translate_btn.setStyleSheet("QPushButton { background: #1890ff; color: #fff; border-radius: 4px; padding: 2px 12px; }")
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedWidth(28)
        for w in (self._src_combo, self._swap_btn, self._tgt_combo, self._compare_btn, self._direct_btn, self._translate_btn, self._close_btn):
            tb.addWidget(w)
        self._direct_btn.toggled.connect(self._on_direct_toggled)
        self._swap_btn.clicked.connect(self._on_swap)
        self._translate_btn.clicked.connect(self._on_translate)
        self._close_btn.clicked.connect(self.close)

    def _on_direct_toggled(self, on: bool) -> None:
        self._compare_btn.setEnabled(not on)

    def _on_swap(self) -> None:
        si, ti = self._src_combo.currentIndex(), self._tgt_combo.currentIndex()
        self._src_combo.setCurrentIndex(ti)
        self._tgt_combo.setCurrentIndex(si)

    def _mode(self) -> str:
        if self._direct_btn.isChecked():
            return "direct"
        if self._compare_btn.isChecked():
            return "compare"
        return "overlay"

    def _on_translate(self) -> None:
        if self._rect is None or self._rect.width() < 5 or self._rect.height() < 5:
            return
        crop = self._frozen.copy(self._rect.normalized())
        self.capture_selected.emit(crop, self._mode(), self._src_combo.currentData(), self._tgt_combo.currentData())
        self.close()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._rect = QRect(self._origin, self._origin)
            self._toolbar.hide()
            self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._origin is not None and (e.buttons() & Qt.LeftButton):
            self._rect = QRect(self._origin, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self._rect is not None:
            if self._rect.width() > 5 and self._rect.height() > 5:
                self._toolbar.move(self._rect.x(), min(self._rect.bottom() + 4, self.height() - 40))
                self._toolbar.setFixedWidth(min(self._rect.width(), 600))
                self._toolbar.show()
            self._origin = None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._frozen)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # 暗化
        if self._rect is not None and self._rect.width() > 0:
            painter.drawPixmap(self._rect.topLeft(), self._frozen, self._rect)  # 选区清晰
            pen = QPen(QColor("#1890ff"), 2)
            painter.setPen(pen)
            painter.drawRect(self._rect)
        painter.end()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()
