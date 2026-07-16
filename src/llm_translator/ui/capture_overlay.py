"""截图覆盖层：全屏暗化 + 拖框选区（可移动/缩放/重画）+ 工具条（语言/翻译/✕）。

选区交互（对标百度翻译）：
- 框外按下 → 重新画一个选区；
- 选区内按下 → 拖动移动选区；
- 选区边缘/四角把手按下 → 缩放选区；
- 鼠标悬停把手/选区 → 对应光标提示。

就地翻译流程（百度同款）：点"翻译"后覆盖层不关闭，
- 按钮 → "翻译中…"（红、禁用）；
- 译完 → 按钮恢复"翻译"（灰、禁用），选区内原位替换为译文（不弹新窗）；
发 translate_requested(crop, src, tgt)，主窗口 OCR+翻译后回调 apply_translation(blocks)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from llm_translator.ui.ocr_result import paint_translated_blocks
from llm_translator.ui.widgets import StyledComboBox

HANDLE = 8  # 把手边长（逻辑像素）

# 把手方位 → 缩放光标
_HANDLE_CURSOR = {
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
}

# 翻译按钮三态样式
_BTN_IDLE = (
    "QPushButton { background: #1890ff; color: #ffffff; border: none; "
    "border-radius: 6px; padding: 4px 16px; font-weight: 600; }"
    "QPushButton:hover { background: #40a9ff; }"
)
_BTN_DOING = (
    "QPushButton { background: #e81123; color: #ffffff; border: none; "
    "border-radius: 6px; padding: 4px 16px; font-weight: 600; }"
)
_BTN_DONE = (
    "QPushButton { background: #d9d9d9; color: #999999; border: none; "
    "border-radius: 6px; padding: 4px 16px; font-weight: 600; }"
)


class CaptureOverlay(QWidget):
    """全屏截图选区覆盖层。"""

    translate_requested = Signal(QPixmap, str, str)  # crop_image, src, tgt

    def __init__(self, frozen: QPixmap, default_tgt: str = "en", parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)  # 悬停（不按按键）也能触发 mouseMove → 实时切换光标
        self._drag_cursor_set = False  # 拖动期间的全局 override 光标是否已设置
        self._frozen = frozen
        self._rect: QRect | None = None
        # 交互状态：("new",None)/("move",None)/("resize",which)；None=空闲
        self._action = None
        self._origin = QPoint()
        self._rect0 = QRect()
        # 就地翻译状态：idle / translating / done
        self._ocr_state = "idle"
        self._result_pixmap: QPixmap | None = None  # 译完后选区内的原位结果图（缓存）
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 工具条（选区确定后显示）——白色圆角浮条
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("ocrToolbar")
        self._toolbar.setFixedHeight(40)
        self._toolbar.setStyleSheet("QWidget#ocrToolbar { background: #ffffff; border-radius: 8px; }")
        self._toolbar.hide()
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(10, 4, 8, 4)
        tb.setSpacing(8)
        self._src_combo = StyledComboBox()
        self._src_combo.addItem("自动检测", "auto")
        for code, name in [("zh", "中文"), ("en", "英语"), ("ja", "日语")]:
            self._src_combo.addItem(name, code)
        self._swap_btn = QPushButton("⇌")
        self._swap_btn.setFixedWidth(30)
        self._tgt_combo = StyledComboBox()
        for code, name in [("zh", "中文"), ("en", "英语"), ("ja", "日语")]:
            self._tgt_combo.addItem(name, code)
        idx = self._tgt_combo.findData(default_tgt)
        self._tgt_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self._translate_btn = QPushButton("翻 译")
        self._translate_btn.setCursor(Qt.PointingHandCursor)
        self._translate_btn.setStyleSheet(_BTN_IDLE)
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedWidth(30)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #888; font-size: 14px; }"
            "QPushButton:hover { color: #e81123; }"
        )
        for w in (self._src_combo, self._swap_btn, self._tgt_combo,
                  self._translate_btn, self._close_btn):
            tb.addWidget(w)
        self._swap_btn.clicked.connect(self._on_swap)
        self._translate_btn.clicked.connect(self._on_translate)
        self._close_btn.clicked.connect(self.close)

    # ---- 工具条 ----
    def _on_swap(self) -> None:
        si, ti = self._src_combo.currentIndex(), self._tgt_combo.currentIndex()
        self._src_combo.setCurrentIndex(ti)
        self._tgt_combo.setCurrentIndex(si)

    def _on_translate(self) -> None:
        """点"翻译"：覆盖层不关，按钮变"翻译中…"(红)，发 translate_requested。"""
        if self._rect is None or self._rect.width() < 5 or self._rect.height() < 5:
            return
        if self._ocr_state != "idle":
            return  # 翻译中/已译完，不重复触发
        self._ocr_state = "translating"
        self._set_btn_state("translating")
        crop = self._frozen.copy(self._rect.normalized())
        self.translate_requested.emit(crop, self._src_combo.currentData(), self._tgt_combo.currentData())

    def apply_translation(self, blocks) -> None:
        """译完：选区内原位替换为译文，按钮变"翻译"(灰、禁用)。blocks 的 bbox 相对 crop。"""
        if self._rect is None:
            return
        crop = self._frozen.copy(self._rect.normalized())
        tmp = QPixmap(crop.size())
        tmp.fill(Qt.transparent)
        p = QPainter(tmp)
        paint_translated_blocks(p, crop, blocks, cover_original=True)
        p.end()
        self._result_pixmap = tmp
        self._ocr_state = "done"
        self._set_btn_state("done")
        self.update()

    def reset_translate(self) -> None:
        """异常时回退到 idle，允许重试。"""
        self._ocr_state = "idle"
        self._result_pixmap = None
        self._set_btn_state("idle")
        self.update()

    def _set_btn_state(self, state: str) -> None:
        if state == "translating":
            self._translate_btn.setText("翻译中…")
            self._translate_btn.setEnabled(False)
            self._translate_btn.setStyleSheet(_BTN_DOING)
        elif state == "done":
            self._translate_btn.setText("翻 译")
            self._translate_btn.setEnabled(False)
            self._translate_btn.setStyleSheet(_BTN_DONE)
        else:  # idle
            self._translate_btn.setText("翻 译")
            self._translate_btn.setEnabled(True)
            self._translate_btn.setStyleSheet(_BTN_IDLE)

    def _show_toolbar(self) -> None:
        """把工具条放到选区下方/上方，按内容宽度，不溢屏。"""
        self._toolbar.adjustSize()
        tw = min(self._toolbar.sizeHint().width(), 720)
        th = self._toolbar.height()
        tx = max(4, min(self._rect.x(), self.width() - tw - 4))
        ty = self._rect.bottom() + 4
        if ty + th > self.height():
            ty = max(4, self._rect.top() - th - 4)
        self._toolbar.setFixedWidth(tw)
        self._toolbar.move(tx, ty)
        self._toolbar.show()

    # ---- 把手检测 ----
    def _handle_points(self, r: QRect) -> list[tuple[str, int, int]]:
        L, R, T, B = r.left(), r.right(), r.top(), r.bottom()
        cx, cy = r.center().x(), r.center().y()
        return [
            ("nw", L, T), ("n", cx, T), ("ne", R, T),
            ("w", L, cy), ("e", R, cy),
            ("sw", L, B), ("s", cx, B), ("se", R, B),
        ]

    def _handle_at(self, pos: QPoint) -> str | None:
        if self._rect is None or self._rect.width() < 5:
            return None
        z = HANDLE
        for name, hx, hy in self._handle_points(self._rect):
            if abs(pos.x() - hx) <= z and abs(pos.y() - hy) <= z:
                return name
        return None

    def _update_cursor(self, pos: QPoint) -> None:
        h = self._handle_at(pos)
        if h:
            self.setCursor(_HANDLE_CURSOR[h])
        elif self._rect and self._rect.contains(pos) and self._rect.width() > 5:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def _action_cursor_shape(self):
        """当前拖动动作对应的光标形状。"""
        if self._action is None:
            return Qt.CrossCursor
        kind = self._action[0]
        if kind == "move":
            return Qt.SizeAllCursor
        if kind == "resize":
            return _HANDLE_CURSOR.get(self._action[1], Qt.SizeAllCursor)
        return Qt.CrossCursor  # new

    def _begin_drag_cursor(self) -> None:
        """拖动开始：grabMouse 独占鼠标并锁定光标形状。

        系统在拖动时可能强行显示"禁止"光标（OLE 拖放等），setCursor / setOverrideCursor
        都压不住；grabMouse(cursor) 把鼠标输入独占给本窗口并锁定光标，系统能被它覆盖。
        同时 setCursor 做双重保险。
        """
        shape = self._action_cursor_shape()
        self.setCursor(shape)
        self.grabMouse(QCursor(shape))
        self._drag_cursor_set = True

    def _end_drag_cursor(self) -> None:
        if self._drag_cursor_set:
            self.releaseMouse()
            self._drag_cursor_set = False

    # ---- 选区交互 ----
    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        # 点击落在工具条上 → 不启动选区（交给工具条按钮处理），避免点按钮触发重截图
        if self._toolbar.isVisible() and self._toolbar.geometry().contains(pos):
            return
        h = self._handle_at(pos)
        if h is not None:
            self._action = ("resize", h)
        elif self._rect is not None and self._rect.contains(pos) and self._rect.width() > 5:
            self._action = ("move", None)
        else:
            self._action = ("new", None)
            self._rect = QRect(pos, pos)
            # 新选区：重置翻译状态（可再次翻译）
            self._ocr_state = "idle"
            self._result_pixmap = None
            self._set_btn_state("idle")
        self._origin = pos
        self._rect0 = QRect(self._rect) if self._rect is not None else QRect()
        self._toolbar.hide()
        self._begin_drag_cursor()
        self.update()

    def mouseMoveEvent(self, e) -> None:
        pos = e.position().toPoint()
        if not (e.buttons() & Qt.LeftButton):
            self._update_cursor(pos)
            return
        kind = self._action[0] if self._action else None
        if kind == "new":
            self._rect = QRect(self._origin, pos).normalized()
        elif kind == "move":
            dx, dy = pos.x() - self._origin.x(), pos.y() - self._origin.y()
            self._rect = self._clamp_move(self._rect0.translated(dx, dy))
        elif kind == "resize":
            which = self._action[1]
            self._rect = self._clamp(self._resized(self._rect0, which, self._origin, pos))
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        self._end_drag_cursor()
        if self._rect is not None and self._rect.width() > 5 and self._rect.height() > 5:
            self._show_toolbar()
        self._action = None
        self._update_cursor(e.position().toPoint())

    def _resized(self, r0: QRect, which: str, start: QPoint, pos: QPoint) -> QRect:
        dx, dy = pos.x() - start.x(), pos.y() - start.y()
        r = QRect(r0)
        if "w" in which:
            r.setLeft(r0.left() + dx)
        if "e" in which:
            r.setRight(r0.right() + dx)
        if "n" in which:
            r.setTop(r0.top() + dy)
        if "s" in which:
            r.setBottom(r0.bottom() + dy)
        return r.normalized()

    def _clamp(self, r: QRect) -> QRect:
        return r.intersected(self.rect())

    def _clamp_move(self, r: QRect) -> QRect:
        b = self.rect()
        x = min(max(r.x(), b.left()), b.right() - r.width())
        y = min(max(r.y(), b.top()), b.bottom() - r.height())
        r.moveTo(x, y)
        return r

    # ---- 绘制 ----
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._frozen)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # 暗化
        if self._rect is not None and self._rect.width() > 0:
            r = self._rect.normalized()
            if self._ocr_state == "done" and self._result_pixmap is not None:
                painter.drawPixmap(r.topLeft(), self._result_pixmap)  # 选区内原位译文
            else:
                painter.drawPixmap(r.topLeft(), self._frozen, r)  # 选区清晰（原文）
            painter.setPen(QPen(QColor("#1890ff"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)
            # 8 把手
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#1890ff"), 1))
            for _name, hx, hy in self._handle_points(r):
                painter.drawRect(hx - HANDLE // 2, hy - HANDLE // 2, HANDLE, HANDLE)
            # 尺寸标签
            painter.setPen(QColor("#ffffff"))
            painter.setFont(self.font())
            label = f"{r.width()} × {r.height()}"
            fm = painter.fontMetrics()
            lw = fm.horizontalAdvance(label) + 10
            lh = fm.height() + 4
            lx = r.left()
            ly = r.top() - lh - 4 if r.top() - lh - 4 > 0 else r.bottom() + 4
            painter.fillRect(lx, ly, lw, lh, QColor(0, 0, 0, 160))
            painter.drawText(QRect(lx, ly, lw, lh), Qt.AlignCenter, label)
        painter.end()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self._end_drag_cursor()
            self.close()

    def hideEvent(self, _event) -> None:
        # 关闭/隐藏时若仍在拖动，恢复 override 光标，避免泄漏
        self._end_drag_cursor()
