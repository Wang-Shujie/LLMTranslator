"""截图 OCR 结果渲染：原地覆盖 / 对照 / 直接翻译面板。

共享 paint_translated_blocks(painter, blocks, bg_mode)：
  每块 bbox 填底色 → 画译文（字号适配框宽高）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm_translator.ui.selection_popup import _force_foreground_win, _get_foreground_win


def _luminance(c: QColor) -> int:
    return int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())


def _sample_bg(qimg: QImage, x: int, y: int, w: int, h: int) -> QColor:
    """采样块四角像素的均值作为背景色（用于盖原文时保留原背景，对标百度）。"""
    pts = [(x + 1, y + 1), (x + w - 2, y + 1), (x + 1, y + h - 2), (x + w - 2, y + h - 2)]
    rs = gs = bs = 0
    n = 0
    for px, py in pts:
        if 0 <= px < qimg.width() and 0 <= py < qimg.height():
            c = qimg.pixelColor(px, py)
            rs += c.red()
            gs += c.green()
            bs += c.blue()
            n += 1
    return QColor(rs // n, gs // n, bs // n) if n else QColor("#ffffff")


def paint_translated_blocks(
    painter: QPainter,
    canvas: QPixmap | QImage,
    blocks: list[tuple[str, tuple[int, int, int, int]]],
    cover_original: bool,
) -> None:
    """在 canvas 上原位绘制译文字块（对标百度翻译）。

    cover_original=True 时，按块四角采样的背景色填充盖住原文（保留原背景而非白块），
    译文字色按背景明暗自适应（深底白字 / 浅底黑字）。
    """
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.drawPixmap(0, 0, canvas) if isinstance(canvas, QPixmap) else painter.drawImage(0, 0, canvas)
    qimg = canvas.toImage() if isinstance(canvas, QPixmap) else canvas
    for text, (x, y, w, h) in blocks:
        if cover_original:
            bg = _sample_bg(qimg, x, y, w, h)
            painter.fillRect(QRect(x - 1, y - 1, w + 2, h + 2), bg)
            text_color = QColor("#222222") if _luminance(bg) > 140 else QColor("#ffffff")
        else:
            text_color = QColor("#000000")
        font_size = max(11, min(int(h * 0.72), 22))
        font = QFont("Microsoft YaHei", font_size)
        painter.setFont(font)
        painter.setPen(text_color)
        rect = QRect(x + 2, y, w - 4, h)
        painter.drawText(rect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignLeft, text)


class _BaseResultWindow(QWidget):
    """结果窗口基类：无边框置顶 + Esc 关闭 + 自动隐藏。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        if QApplication.instance() is not None:
            QApplication.instance().installEventFilter(self)

    def eventFilter(self, _obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if (
            self.isVisible()
            and self.isActiveWindow()
            and event.type() == QEvent.MouseButtonPress
            and not self.geometry().contains(event.globalPosition().toPoint())
        ):
            self.hide()
        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


class OverlayResultWindow(QWidget):
    """原地覆盖（对标百度翻译）：译文叠在截图上盖住原文，定位到选区位置。

    无边框 + WA_OpaquePaintEvent（paintEvent 画满，无白边，原位融入）；右上角小控件
    （复制/✕）；可靠关闭：点窗外（前台轮询，复用划词弹窗）+ ✕ + Esc。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)  # 自绘铺满，避免 app qss 白边
        self._pixmap: QPixmap | None = None
        self._blocks: list[tuple[str, tuple[int, int, int, int]]] = []
        # 右上角浮动小控件
        btn_qss = (
            "QPushButton { border: none; background: rgba(0,0,0,130); color: #ffffff; "
            "border-radius: 11px; font-size: 12px; }"
            "QPushButton:hover { background: #1890ff; }"
        )
        self._copy_btn = QPushButton("📋", self)
        self._copy_btn.setFixedSize(24, 24)
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setStyleSheet(btn_qss)
        self._copy_btn.setToolTip("复制全部译文")
        self._copy_btn.clicked.connect(self._copy_all)
        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { border: none; background: rgba(0,0,0,130); color: #ffffff; "
            "border-radius: 11px; font-size: 12px; }"
            "QPushButton:hover { background: #e81123; }"
        )
        self._close_btn.clicked.connect(self.hide)
        # 前台轮询：点窗外（含跨程序）→ 关闭
        self._armed = False
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.setInterval(150)
        self._arm_timer.timeout.connect(lambda: setattr(self, "_armed", True))
        self._popup_hwnd = 0
        self._was_fg = False
        self._fg_poll = QTimer(self)
        self._fg_poll.setInterval(150)
        self._fg_poll.timeout.connect(self._on_fg_poll)

    def _copy_all(self) -> None:
        QApplication.clipboard().setText("\n".join(t for t, _ in self._blocks))

    def show_result(self, pixmap: QPixmap, blocks, pos) -> None:
        self._pixmap = pixmap
        self._blocks = blocks
        self.resize(pixmap.size())
        if pos is not None:
            self.move(pos)
        # 控件定位到右上角
        self._close_btn.move(self.width() - 30, 6)
        self._copy_btn.move(self.width() - 58, 6)
        self._close_btn.show()
        self._copy_btn.show()
        # 启动失焦关闭轮询
        self._armed = False
        self._arm_timer.start()
        self._popup_hwnd = int(self.winId())
        self._was_fg = False
        self._fg_poll.start()
        self.show()
        self.raise_()
        self.activateWindow()
        _force_foreground_win(self._popup_hwnd)

    def _on_fg_poll(self) -> None:
        if not self.isVisible() or not self._armed or not self._popup_hwnd:
            return
        fg = _get_foreground_win()
        if not fg:
            return
        if not self._was_fg:
            if fg == self._popup_hwnd:
                self._was_fg = True
            else:
                self._fg_poll.stop()
            return
        if fg != self._popup_hwnd:
            self.hide()

    def paintEvent(self, _event) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        paint_translated_blocks(painter, self._pixmap, self._blocks, cover_original=True)
        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, _event) -> None:
        self._fg_poll.stop()
        self._arm_timer.stop()


class CompareResultWindow(_BaseResultWindow):
    """对照：上方白底译文画布 + 下方原图，同尺寸上下对比。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._blocks: list[tuple[str, tuple[int, int, int, int]]] = []

    def show_result(self, pixmap: QPixmap, blocks, pos) -> None:
        self._pixmap = pixmap
        self._blocks = blocks
        self.resize(pixmap.width(), pixmap.height() * 2)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        h = self._pixmap.height()
        # 上半：白底 + 译文
        painter.fillRect(0, 0, self.width(), h, QColor("#ffffff"))
        for text, (x, y, w, hb) in self._blocks:
            font_size = max(8, min(int(hb * 0.7), 20))
            painter.setFont(QFont("Microsoft YaHei", font_size))
            painter.setPen(QColor("#000000"))
            painter.drawText(QRect(x + 2, y, w - 4, hb), Qt.TextWordWrap | Qt.AlignVCenter, text)
        # 下半：原图
        painter.drawPixmap(0, h, self._pixmap)
        # 分隔线
        painter.setPen(QPen(QColor("#d0d0d0"), 1))
        painter.drawLine(0, h, self.width(), h)
        painter.end()


class OcrDirectPanel(_BaseResultWindow):
    """直接翻译面板：上 OCR 原文，下流式译文。"""

    # 跨线程信号：worker 线程 emit → 主线程更新（避免直接调用线程不安全）
    _source_ready = Signal(str)
    _token_ready = Signal(str)
    _translation_ready = Signal(str)
    _error_ready = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("截图翻译结果")
        self.resize(460, 420)
        self.setStyleSheet("OcrDirectPanel { background: #f5f6f8; }")
        self._source_ready.connect(self.set_source)
        self._token_ready.connect(self.append_token)
        self._translation_ready.connect(self.set_translation)
        self._error_ready.connect(self.set_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 头部
        header = QWidget()
        header.setStyleSheet("background: #ffffff; border-bottom: 1px solid #ececec;")
        hh = QHBoxLayout(header)
        hh.setContentsMargins(16, 10, 8, 10)
        title = QLabel("截图翻译结果")
        title.setStyleSheet("font-size: 15px; font-weight: 600; color: #000; background: transparent;")
        hh.addWidget(title)
        hh.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #888; font-size: 14px; padding: 0 8px; }"
            "QPushButton:hover { color: #e81123; }"
        )
        close_btn.clicked.connect(self.hide)
        hh.addWidget(close_btn)
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet("background: #f5f6f8;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(8)
        self._src_edit = self._make_edit("📷 原文（OCR）")
        bl.addWidget(self._src_edit, stretch=1)
        self._tgt_edit = self._make_edit("🌐 译文")
        bl.addWidget(self._tgt_edit, stretch=1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._copy_btn = QPushButton("📋 复制译文")
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setStyleSheet(
            "QPushButton { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 6px; "
            "padding: 6px 14px; color: #555; }"
            "QPushButton:hover { border-color: #1890ff; color: #1890ff; }"
        )
        self._copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._tgt_edit.toPlainText()))
        row.addWidget(self._copy_btn)
        row.addStretch()
        bl.addLayout(row)
        root.addWidget(body, stretch=1)

        self.set_source("识别中…")  # 立即反馈：OCR/翻译进行中

    @staticmethod
    def _make_edit(label: str) -> QTextEdit:
        ed = QTextEdit()
        ed.setReadOnly(True)
        ed.setStyleSheet(
            "QTextEdit { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; "
            "padding: 10px; color: #222; font-size: 14px; }"
        )
        ed.setPlaceholderText(label)
        return ed

    def set_source(self, text: str) -> None:
        self._src_edit.setPlainText(text)

    def append_token(self, tok: str) -> None:
        self._tgt_edit.insertPlainText(tok)

    def set_translation(self, full: str) -> None:
        self._tgt_edit.setPlainText(full)

    def set_error(self, msg: str) -> None:
        self._tgt_edit.setPlainText(f"❌ {msg}")

