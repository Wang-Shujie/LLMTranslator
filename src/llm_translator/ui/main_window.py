"""主窗口：顶部语言栏 + 上下输入输出双栏 + 状态栏。对照参考图。"""
from __future__ import annotations

import asyncio
import re
import threading

from PySide6.QtCore import QEvent, QObject, Qt, QByteArray, QPoint, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QKeySequence, QMouseEvent, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.core.language import LANGUAGES, selection_target
from llm_translator.core.translator import Translator
from llm_translator.providers.registry import all_providers, get_provider
from llm_translator.storage.history import HistoryStore
from llm_translator.storage.settings import Settings
from llm_translator.ui.async_bridge import TokenEmitter
from llm_translator.ui.settings_dialog import SettingsDialog
from llm_translator.ui.history_dialog import HistoryDialog
from llm_translator.core.tts import EdgeTtsEngine
from llm_translator.ui.tts_player import TtsPlayer
from llm_translator.core.selection import SelectionController
from llm_translator.ui.selection_popup import SelectionPopup
from llm_translator.core.ocr import OcrController, OcrEngine
from llm_translator.core.screen_capture import grab_screen
from llm_translator.ui.capture_overlay import CaptureOverlay
from llm_translator.ui.ocr_result import OverlayResultWindow, CompareResultWindow, OcrDirectPanel
from llm_translator.ui.document_dialog import DocumentDialog
from llm_translator.ui.widgets import ToggleSwitch

# 简洁黑白图标，按颜色渲染（小尺寸下也清晰）。
# 置顶：实心图钉（圆头 + 锥形针体）
_PIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}">'
    '<circle cx="12" cy="6" r="5"/>'
    '<path d="M8.5 10 L15.5 10 L13 22 L11 22 Z"/>'
    "</svg>"
)
# 最小化到托盘：下箭头 + 底线
_DOWN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="12" y1="4" x2="12" y2="15"/>'
    '<polyline points="7 11 12 16 17 11"/>'
    '<line x1="5" y1="20" x2="19" y2="20"/>'
    "</svg>"
)
# 菜单：三条横线（☰）
_MENU_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2.2" stroke-linecap="round">'
    '<line x1="4" y1="7" x2="20" y2="7"/>'
    '<line x1="4" y1="12" x2="20" y2="12"/>'
    '<line x1="4" y1="17" x2="20" y2="17"/>'
    "</svg>"
)


def _svg_icon(svg_template: str, color: str, size: int = 18) -> QIcon:
    """按颜色把 SVG 模板渲染为图标（2x 像素比，HiDPI 下清晰）。"""
    renderer = QSvgRenderer(QByteArray(svg_template.format(color=color).encode("utf-8")))
    scale = 2
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    # 必须显式给目标矩形，否则 QSvgRenderer 按默认尺寸绘制 → 内容偏到右下并被裁切
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pix)


def _toggle_label(text: str) -> QLabel:
    """右下角拨动开关旁的灰色小标签。"""
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #999999; font-size: 13px; background: transparent;")
    return lbl


class MenuButton(QPushButton):
    """按钮 + 弹出菜单，模拟 QComboBox 的常用接口（currentIndex/currentData/findData/
    currentIndexChanged），外观复用 QPushButton 样式 → 与 ☰ 菜单按钮一致。
    """

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, object]] = []
        self._index = -1
        self._menu = QMenu(self)  # 父对象 = 按钮，避免无主 QMenu 被 GC 回收
        self.setMenu(self._menu)
        self._menu.aboutToShow.connect(self._sync_menu)

    def addItems(self, items: list[tuple[str, object]]) -> None:
        self._items = list(items)

    def _sync_menu(self) -> None:
        self._menu.clear()
        for i, (label, _data) in enumerate(self._items):
            act = self._menu.addAction(label, lambda _checked=False, i=i: self.setCurrentIndex(i))
            act.setCheckable(True)
            act.setChecked(i == self._index)

    def currentIndex(self) -> int:
        return self._index

    def setCurrentIndex(self, idx: int) -> None:
        if idx == self._index or not (0 <= idx < len(self._items)):
            return
        self._index = idx
        self.setText(self._items[idx][0])
        self.currentIndexChanged.emit(idx)

    def currentData(self):
        return self._items[self._index][1] if 0 <= self._index < len(self._items) else None

    def findData(self, data) -> int:
        for i, (_label, d) in enumerate(self._items):
            if d == data:
                return i
        return -1


class _Status(QLabel):
    """状态标签（替代 QStatusBar）。保留 showMessage 接口，方便沿用旧调用点。"""

    def showMessage(self, text: str, msec: int = 0) -> None:
        self.setText(text)


class _RoundedFrame(QFrame):
    """圆角白色容器：自绘圆角白底+边框（配合窗口 WA_TranslucentBackground 实现真圆角，
    QSS border-radius 无法裁剪透明）。"""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#d0d0d0"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)


class _ResizeFilter(QObject):
    """无边框窗口的边缘缩放：装在 QApplication 上，对所有"无边框 + 非 Tool"的
    顶层窗口（主窗口、圆角对话框等）生效；划词弹窗等 Qt.Tool 弹层不缩放。

    鼠标在窗口边缘 EDGE px 内按下 → startSystemResize 由系统接管缩放；
    悬停时换成缩放光标。"""

    EDGE = 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._overriding = False

    def _resizable_win(self, obj):
        """事件目标 obj 所在的、可缩放的无边框顶层窗口；否则 None。

        用标记属性 `_edge_resizable` 判定（主窗口、RoundedDialog 置 True），
        避免 PySide6 里 `bool(flags & Qt.Tool)` 等位运算对枚举恒真的陷阱。
        """
        if not isinstance(obj, QWidget):
            return None
        win = obj.window()
        if win is None or win.windowHandle() is None:
            return None
        if not getattr(win, "_edge_resizable", False):
            return None
        return win

    def _edges(self, gp: QPoint, win) -> Qt.Edge:
        wr = win.geometry()
        e = Qt.Edge(0)
        if 0 <= gp.x() - wr.left() <= self.EDGE:
            e |= Qt.LeftEdge
        if 0 <= wr.right() - gp.x() <= self.EDGE:
            e |= Qt.RightEdge
        if 0 <= gp.y() - wr.top() <= self.EDGE:
            e |= Qt.TopEdge
        if 0 <= wr.bottom() - gp.y() <= self.EDGE:
            e |= Qt.BottomEdge
        return e

    @staticmethod
    def _cursor_for(e: Qt.Edge):
        horiz = bool(e & (Qt.LeftEdge | Qt.RightEdge))
        vert = bool(e & (Qt.TopEdge | Qt.BottomEdge))
        if horiz and vert:
            return Qt.SizeFDiagCursor if (e & Qt.LeftEdge and e & Qt.TopEdge) or \
                (e & Qt.RightEdge and e & Qt.BottomEdge) else Qt.SizeBDiagCursor
        if horiz:
            return Qt.SizeHorCursor
        if vert:
            return Qt.SizeVerCursor
        return None

    def eventFilter(self, obj, event) -> bool:
        et = event.type()
        if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            win = self._resizable_win(obj)
            if win is not None:
                edges = self._edges(event.globalPosition().toPoint(), win)
                if edges:
                    win.windowHandle().startSystemResize(edges)
                    return True
        elif et == QEvent.MouseMove:
            win = self._resizable_win(obj)
            cur = self._cursor_for(self._edges(event.globalPosition().toPoint(), win)) if win else None
            if cur is not None:
                if not self._overriding:
                    QApplication.setOverrideCursor(QCursor(cur))
                    self._overriding = True
                else:
                    QApplication.changeOverrideCursor(QCursor(cur))
            elif self._overriding:
                QApplication.restoreOverrideCursor()
                self._overriding = False
        return False


class TitleBar(QWidget):
    """自绘标题栏：左侧应用控制按钮（外部 addWidget），右侧窗口控制；
    按住拖动移动窗口，双击最大化/还原。仅响应空白区域（点到按钮不触发拖动）。"""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._win = window
        self._drag_pos: QPoint | None = None
        self.setObjectName("titleBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 2, 2)
        lay.setSpacing(4)
        self._left = QHBoxLayout()
        self._left.setSpacing(4)
        self._right = QHBoxLayout()
        self._right.setSpacing(0)
        lay.addLayout(self._left)
        lay.addStretch()
        lay.addLayout(self._right)

    def add_left(self, w: QWidget) -> None:
        self._left.addWidget(w)

    def add_right(self, w: QWidget) -> None:
        self._right.addWidget(w)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.pos()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        self._win.showNormal() if self._win.isMaximized() else self._win.showMaximized()


class _OcrResultEvent(QEvent):
    """跨线程传递 OCR + 翻译结果给主线程（worker 线程 postEvent → 主线程 event()）。"""

    def __init__(self, crop_image, blocks, mode):
        super().__init__(QEvent.User)
        self.crop_image = crop_image
        self.blocks = blocks
        self.mode = mode


class MainWindow(QMainWindow):
    # 跨线程 OCR 错误：worker 线程 emit → 主线程显示状态消息
    _ocr_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LLM 翻译")
        # 无边框 + 透明背景：自绘标题栏与圆角
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # widget 级样式优先级最高：强制主窗口透明，否则 app 级 QWidget{background:#fff}
        # 会把窗口画成不透明白底，圆角失效。
        self.setStyleSheet("QMainWindow { background: transparent; }")
        self.resize(480, 360)
        self.setMinimumSize(380, 300)
        # 标记为可边缘缩放的无边框窗口（供 _ResizeFilter 识别）
        self._edge_resizable = True

        # 持久化与编排
        self.settings = Settings.load()
        self.credentials = CredentialStore()
        self.history = HistoryStore()
        self.emitter = TokenEmitter()
        self._current_task = None
        self._tray: QSystemTrayIcon | None = None
        self._active_speak_btn: QPushButton | None = None
        self._build_translator()
        self.tts_player = TtsPlayer(EdgeTtsEngine(), self)
        self._selection_popup: SelectionPopup | None = None
        self.selection_ctrl = SelectionController(self.settings, self)
        self.selection_ctrl.captured.connect(self._show_selection_popup)
        self.ocr_ctrl = OcrController(self.settings, self)
        self.ocr_ctrl.triggered.connect(self._start_ocr_capture)
        self._ocr_engine = OcrEngine()

        self._build_ui()
        self._wire_signals()
        self._build_tray()
        # 无边框窗口边缘缩放（任何边/角都可拖动缩放）
        if QApplication.instance() is not None:
            self._resize_filter = _ResizeFilter(self)
            QApplication.instance().installEventFilter(self._resize_filter)

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
        # central = 圆角白色容器（窗口本身透明，由它承载内容 + 圆角）
        central = _RoundedFrame()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 自绘标题栏：左 [最小化到托盘][置顶][☰]，右 [—][☐][✕] ----
        self.title_bar = TitleBar(self)
        icon_qss = (
            "QToolButton { border: 1px solid #e0e0e0; border-radius: 8px; background: #ffffff; padding: 0; }"
            "QToolButton:hover { border-color: #1890ff; }"
        )
        self.tray_min_btn = QToolButton()
        self.tray_min_btn.setObjectName("iconBtn")
        self.tray_min_btn.setFixedSize(28, 28)
        self.tray_min_btn.setIcon(_svg_icon(_DOWN_SVG, "#333333"))
        self.tray_min_btn.setIconSize(QSize(18, 18))
        self.tray_min_btn.setToolTip("最小化到系统托盘")
        self.tray_min_btn.setStyleSheet(icon_qss)
        self.pin_btn = QToolButton()
        self.pin_btn.setObjectName("pinBtn")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setIcon(_svg_icon(_PIN_SVG, "#333333"))
        self.pin_btn.setIconSize(QSize(18, 18))
        self.pin_btn.setToolTip("置顶（始终显示在最前）")
        self.pin_btn.setStyleSheet(
            "QToolButton { border: 1px solid #e0e0e0; border-radius: 8px; background: #ffffff; padding: 0; }"
            "QToolButton:checked { background: #1890ff; border: none; }"
        )
        self.menu_btn = QToolButton()
        self.menu_btn.setObjectName("menuBtn")
        self.menu_btn.setFixedSize(28, 28)
        self.menu_btn.setIcon(_svg_icon(_MENU_SVG, "#333333"))
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # 与置顶/最小化图标按钮同款（QToolButton 图标居中）；隐藏菜单指示箭头
        self.menu_btn.setStyleSheet(
            "QToolButton { border: 1px solid #e0e0e0; border-radius: 8px; background: #ffffff; padding: 0; }"
            "QToolButton:hover { border-color: #1890ff; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        self._main_menu = menu = QMenu(self)  # 父对象 = 主窗口 + 存引用，避免无主 QMenu 被 GC 回收
        menu.addAction("设置", self.on_settings)
        menu.addAction("历史记录", self.open_history)
        menu.addAction("关于", self.on_about)
        self.menu_btn.setMenu(menu)
        for w in (self.tray_min_btn, self.pin_btn, self.menu_btn):
            self.title_bar.add_left(w)
        # 窗口控制按钮（无边框文字按钮）
        ctl_qss = "QPushButton { border: none; background: transparent; font-size: 13px; padding: 0 8px; } QPushButton:hover { background: #e5e5e5; }"
        self.win_min_btn = QPushButton("—"); self.win_min_btn.setFixedSize(40, 26); self.win_min_btn.setStyleSheet(ctl_qss)
        self.win_max_btn = QPushButton("☐"); self.win_max_btn.setFixedSize(40, 26); self.win_max_btn.setStyleSheet(ctl_qss)
        self.win_close_btn = QPushButton("✕"); self.win_close_btn.setFixedSize(40, 26)
        self.win_close_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 13px; padding: 0 8px; } QPushButton:hover { background: #e81123; color: #ffffff; }")
        for w in (self.win_min_btn, self.win_max_btn, self.win_close_btn):
            self.title_bar.add_right(w)
        root.addWidget(self.title_bar)

        # ---- 内容区 ----
        body = QWidget()
        body.setObjectName("body")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 4, 12, 8)
        body_lay.setSpacing(8)

        # 语言栏（控制键已移到标题栏，这里只剩语言/模型）
        top = QHBoxLayout()
        lang_items = [(name, code) for code, name in LANGUAGES.items()]
        self.src_combo = MenuButton()
        self.src_combo.addItems(lang_items)
        self.src_combo.setCurrentIndex(self.src_combo.findData(self.settings.src_lang))
        self.tgt_combo = MenuButton()
        self.tgt_combo.addItems(lang_items)
        self.tgt_combo.setCurrentIndex(self.tgt_combo.findData(self.settings.tgt_lang))
        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setFixedWidth(40)
        self.provider_combo = MenuButton()
        self.provider_combo.addItems([(p["label"], p["id"]) for p in all_providers()])
        idx = self.provider_combo.findData(self.settings.default_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        top.addWidget(self.src_combo)
        top.addWidget(self.swap_btn)
        top.addWidget(self.tgt_combo)
        top.addStretch()
        top.addWidget(self.provider_combo)
        body_lay.addLayout(top)

        # 源文本输入
        self.src_edit = QPlainTextEdit()
        self.src_edit.setPlaceholderText("输入要翻译的文本，按 Ctrl+Enter 翻译")
        self.clear_btn = QPushButton("✕ 清空")
        input_row = QHBoxLayout()
        input_row.addWidget(self.src_edit)
        col = QVBoxLayout()
        col.addWidget(self.clear_btn)
        self.src_speak_btn = QPushButton("🔊 原文")
        col.addWidget(self.src_speak_btn)
        col.addStretch()
        input_row.addLayout(col)
        body_lay.addLayout(input_row, stretch=5)

        # 翻译按钮
        self.translate_btn = QPushButton("翻译  (Ctrl+Enter)")
        self.translate_btn.setObjectName("primaryBtn")
        body_lay.addWidget(self.translate_btn)

        # 译文输出
        self.tgt_edit = QPlainTextEdit()
        self.tgt_edit.setReadOnly(True)
        self.tgt_edit.setPlaceholderText("译文将在此显示")
        out_row = QHBoxLayout()
        out_row.addWidget(self.tgt_edit, stretch=1)
        out_col = QVBoxLayout()
        self.copy_btn = QPushButton("📋 复制")
        out_col.addWidget(self.copy_btn)
        self.tgt_speak_btn = QPushButton("🔊 译文")
        out_col.addWidget(self.tgt_speak_btn)
        out_col.addStretch()
        out_row.addLayout(out_col)
        body_lay.addLayout(out_row, stretch=5)

        # 状态 + 右下角功能入口 + 缩放手柄
        # 顺序（左→右）：文档翻译（动作）→ 划译（小开关）→ 截译（小开关）
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self.status = _Status()
        self.status.setStyleSheet("color: #888; font-size: 12px;")
        bottom.addWidget(self.status)
        bottom.addStretch()

        # 文档翻译：文字动作按钮（灰，hover 蓝）
        self._doc_btn = QPushButton("文档翻译")
        self._doc_btn.setCursor(Qt.PointingHandCursor)
        self._doc_btn.setToolTip("文档翻译")
        self._doc_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #999999; "
            "font-size: 13px; padding: 2px 6px; }"
            "QPushButton:hover { color: #1890ff; }"
        )
        bottom.addWidget(self._doc_btn)
        bottom.addSpacing(8)

        # 划译：标签 + 百度同款小拨动开关
        self._selection_btn = ToggleSwitch(checked=self.settings.selection_enabled)
        self._selection_btn.setToolTip("划词翻译（选中文字 + Ctrl+Shift+T）")
        bottom.addWidget(_toggle_label("划译"))
        bottom.addWidget(self._selection_btn)
        bottom.addSpacing(8)

        # 截译：标签 + 小拨动开关
        self._ocr_btn = ToggleSwitch(checked=self.settings.ocr_enabled)
        self._ocr_btn.setToolTip("截图翻译（Ctrl+Shift+O）")
        bottom.addWidget(_toggle_label("截译"))
        bottom.addWidget(self._ocr_btn)

        body_lay.addLayout(bottom)
        self._update_status()

        root.addWidget(body, stretch=1)
        self.setCentralWidget(central)

    # ---- 信号 ----
    def _wire_signals(self) -> None:
        self.translate_btn.clicked.connect(self.on_translate)
        self.clear_btn.clicked.connect(lambda: self.src_edit.clear())
        self.copy_btn.clicked.connect(self.on_copy)
        self.src_speak_btn.clicked.connect(self.on_speak_source)
        self.tgt_speak_btn.clicked.connect(self.on_speak_target)
        self.tts_player.state_changed.connect(self._on_tts_state)
        self.tts_player.error.connect(self._on_tts_error)
        self.swap_btn.clicked.connect(self.on_swap)
        self.pin_btn.toggled.connect(self.on_pin)
        self.tray_min_btn.clicked.connect(self._minimize_to_tray)
        self.win_min_btn.clicked.connect(self.showMinimized)
        self.win_max_btn.clicked.connect(self._toggle_maximize)
        self.win_close_btn.clicked.connect(QApplication.quit)
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self._selection_btn.toggled.connect(self.on_toggle_selection)
        self._ocr_btn.toggled.connect(self.on_toggle_ocr)
        self._doc_btn.clicked.connect(self.on_document_translate)
        self.emitter.token_received.connect(self._on_token)
        self.emitter.finished.connect(self._on_finished)
        self.emitter.error.connect(self._on_error)
        self._ocr_error.connect(lambda msg: self.status.showMessage(f"OCR 翻译失败：{msg}", 5000))
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
        self._run_translate(text, src, tgt)

    def _run_translate(self, text: str, src: str, tgt: str) -> None:
        # 所有 provider（API 用 httpx、网页用 curl_cffi）的异步客户端都要求真实 asyncio
        # 事件循环；而 qasync 不是标准 asyncio loop，会报 "no running event loop" /
        # "Not currently running on any asynchronous event loop"。故统一放进 worker 线程
        # 用 asyncio.run 跑，token 经 Qt 信号（跨线程自动 QueuedConnection）回到主线程。
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
        QApplication.clipboard().setText(self.tgt_edit.toPlainText())

    def on_speak_source(self) -> None:
        """朗读原文：点当前在播按钮=停止；否则切换到原文。"""
        if self._active_speak_btn is self.src_speak_btn:
            self.tts_player.stop()
            return
        text = self.src_edit.toPlainText().strip()
        if not text:
            self.status.showMessage("没有可朗读的原文", 2000)
            return
        if self._active_speak_btn is not None:  # 切换：先还原旧活动按钮文字
            self._reset_speak_btn(self._active_speak_btn)
        self._active_speak_btn = self.src_speak_btn
        self.tts_player.play(text, self.src_combo.currentData())

    def on_speak_target(self) -> None:
        """朗读译文：点当前在播按钮=停止；否则切换到译文。"""
        if self._active_speak_btn is self.tgt_speak_btn:
            self.tts_player.stop()
            return
        text = self.tgt_edit.toPlainText().strip()
        if not text:
            self.status.showMessage("没有可朗读的译文", 2000)
            return
        if self._active_speak_btn is not None:  # 切换：先还原旧活动按钮文字
            self._reset_speak_btn(self._active_speak_btn)
        self._active_speak_btn = self.tgt_speak_btn
        self.tts_player.play(text, self.tgt_combo.currentData())

    def _on_tts_state(self, state: str) -> None:
        """按播放状态切换活动按钮的图标/文字。"""
        btn = self._active_speak_btn
        if btn is None:
            return
        if state == "playing":
            btn.setText("⏹ 停止")
        elif state == "loading":
            btn.setText("⏳ …")
        elif state == "idle":
            self._reset_speak_btn(btn)
            self._active_speak_btn = None

    def _on_tts_error(self, msg: str) -> None:
        self.status.showMessage(f"朗读失败：{msg}", 5000)

    def _reset_speak_btn(self, btn: QPushButton) -> None:
        if btn is self.src_speak_btn:
            btn.setText("🔊 原文")
        elif btn is self.tgt_speak_btn:
            btn.setText("🔊 译文")

    def on_swap(self) -> None:
        si, ti = self.src_combo.currentIndex(), self.tgt_combo.currentIndex()
        self.src_combo.setCurrentIndex(ti)
        self.tgt_combo.setCurrentIndex(si)

    def on_pin(self, on: bool) -> None:
        """切换窗口始终置顶。改变窗口标志后需重新 show 才生效；图标随状态变色。"""
        self.pin_btn.setIcon(_svg_icon(_PIN_SVG, "#ffffff" if on else "#333333"))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _toggle_maximize(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ---- 系统托盘（最小化到托盘）----
    def _build_tray(self) -> None:
        """构建系统托盘图标。无系统托盘（如 offscreen/测试）时跳过，不影响主功能。"""
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self._tray = None
                return
            self._tray = QSystemTrayIcon(_svg_icon(_PIN_SVG, "#1890ff", 32), self)
            self._tray.setToolTip("LLMTranslator")
            menu = QMenu(self)
            menu.addAction("显示主窗口", self._restore_from_tray)
            menu.addSeparator()
            menu.addAction("退出", QApplication.quit)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
        except Exception:
            self._tray = None  # 托盘是可选的，任何失败都不影响主窗口

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()

    def _minimize_to_tray(self) -> None:
        if self._tray is not None:
            self.hide()
            self._tray.showMessage("LLMTranslator", "已最小化到托盘，双击托盘图标恢复")
        else:
            self.showMinimized()  # 无系统托盘 → 退化为普通最小化

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
        # 设置里可能改了快捷键 / 开关 / 默认语言 → 重新注册热键并同步右下角按钮
        self._reload_hotkeys()
        self._update_status()

    def _reload_hotkeys(self) -> None:
        """设置对话框关闭后：按最新设置重新注册全局热键 + 同步字符按钮勾选。"""
        self.selection_ctrl.disable()
        self.ocr_ctrl.disable()
        if self.settings.selection_enabled:
            self.selection_ctrl.enable()
        if self.settings.ocr_enabled:
            self.ocr_ctrl.enable()
        for btn, on in (
            (self._selection_btn, self.settings.selection_enabled),
            (self._ocr_btn, self.settings.ocr_enabled),
        ):
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)

    def on_document_translate(self) -> None:
        """打开文档翻译对话框。"""
        dlg = DocumentDialog(self.credentials, self.settings, self)
        dlg.exec()

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

    def on_toggle_selection(self, on: bool) -> None:
        """右下角"划词"按钮开关：持久化 + 实时注册/注销热键。"""
        self._apply_selection_enabled(on)

    def _apply_selection_enabled(self, on: bool) -> None:
        """统一落地：持久化 + 注册/注销全局热键。"""
        self.settings.selection_enabled = on
        self.settings.save()
        if on:
            self.selection_ctrl.enable()
        else:
            self.selection_ctrl.disable()

    def _on_popup_toggle_selection(self, on: bool) -> None:
        """弹窗内拨动"划词"开关：落地 + 同步右下角按钮（屏蔽信号避免重复触发）。"""
        self._apply_selection_enabled(on)
        self._selection_btn.blockSignals(True)
        self._selection_btn.setChecked(on)
        self._selection_btn.blockSignals(False)

    def _show_selection_popup(self, text: str, pos) -> None:
        """热键取词后：在光标处弹译文明信片并翻译。"""
        # 多行选区：换行/连续空白规范为单个空格。内嵌换行会让翻译 prompt 的"指令+原文"
        # 边界模糊，模型/provider 处理不稳定（常不返回有效译文）→ 弹窗卡住不翻译。
        text = re.sub(r"\s+", " ", text).strip()
        if self.translator is None:
            QMessageBox.warning(self, "未配置", "请先在设置中配置一个模型。")
            return
        if self._selection_popup is None:
            # parent=None：作为独立的 Tool 顶层窗口，避免 show/activate 连带抬升主窗口
            self._selection_popup = SelectionPopup(None)
            self._selection_popup.expand_to_main.connect(self._on_expand_to_main)
            self._selection_popup.toggle_selection.connect(self._on_popup_toggle_selection)
        # 同步全局划词开关状态到弹窗（用户可能在菜单里关过）
        self._selection_popup.set_selection_enabled(self.settings.selection_enabled)
        # 划词翻译：源语言自动检测。文本非默认语言 → 译为默认语言；
        # 已是默认语言 → 不翻译，弹窗原样显示原文。
        tgt = selection_target(text, self.settings.selection_default_lang)
        if tgt is None:
            self._selection_popup.show_source(text)
            self._selection_popup.show_at(pos)
        else:
            self._selection_popup.start_translate(text, "auto", tgt, self.translator)
            self._selection_popup.show_at(pos)

    def _on_expand_to_main(self, source: str, target: str) -> None:
        """弹窗点'展开'：把原文/译文填回主界面并前置。"""
        self.src_edit.setPlainText(source)
        self.tgt_edit.setPlainText(target)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---- 截图 OCR ----
    def event(self, event):
        """处理跨线程 OCR 结果事件（worker 线程 postEvent → 主线程渲染）。"""
        if event.type() == QEvent.User and isinstance(event, _OcrResultEvent):
            self._on_ocr_result(event.crop_image, event.blocks, event.mode)
            return True
        return super().event(event)

    def on_toggle_ocr(self, on: bool) -> None:
        """开关截图 OCR：持久化 + 实时注册/注销热键。"""
        self.settings.ocr_enabled = on
        self.settings.save()
        if on:
            self.ocr_ctrl.enable()
        else:
            self.ocr_ctrl.disable()

    def _start_ocr_capture(self) -> None:
        """热键触发：拍冻结帧 → 显示截图覆盖层。"""
        frozen = grab_screen()
        self._ocr_overlay = CaptureOverlay(frozen, self.settings.ocr_default_lang, self)
        self._ocr_overlay.capture_selected.connect(self._on_ocr_captured)
        self._ocr_overlay.show()

    def _on_ocr_captured(self, crop_image, mode: str, src: str, tgt: str) -> None:
        """选区确定：OCR → 翻译 → 按模式渲染。"""
        if self.translator is None:
            QMessageBox.warning(self, "未配置", "请先在设置中配置一个模型。")
            return
        if mode == "direct":
            self._ocr_direct(crop_image, src, tgt)
        else:
            self._ocr_overlay_translate(crop_image, mode, src, tgt)

    def _ocr_direct(self, crop_image, src: str, tgt: str) -> None:
        """直接翻译模式：OCR → 整段流式翻译 → 面板显示。"""
        import asyncio
        import threading
        engine = self._ocr_engine
        translator = self.translator
        panel = OcrDirectPanel(self)
        panel.show()

        def worker():
            async def run():
                try:
                    blocks = await asyncio.to_thread(engine.recognize, crop_image)
                    if not blocks:
                        panel._error_ready.emit("未识别到文字")
                        return
                    ocr_text = "\n".join(b.text for b in blocks)
                    panel._source_ready.emit(ocr_text)
                    collected = []
                    async for tok in translator.translate(ocr_text, src, tgt, save_history=False):
                        collected.append(tok)
                        panel._token_ready.emit(tok)
                    panel._translation_ready.emit("".join(collected))
                except Exception as e:
                    panel._error_ready.emit(str(e))
            asyncio.run(run())

        threading.Thread(target=worker, daemon=True).start()

    def _ocr_overlay_translate(self, crop_image, mode: str, src: str, tgt: str) -> None:
        """原地覆盖 / 对照模式：OCR → 逐块并发翻译 → 按模式渲染。"""
        import threading, asyncio
        engine = self._ocr_engine
        translator = self.translator

        def worker():
            async def run():
                blocks = await asyncio.to_thread(engine.recognize, crop_image)
                if not blocks:
                    return
                sem = asyncio.Semaphore(8)

                async def one(b):
                    async with sem:
                        parts = []
                        async for tok in translator.translate(b.text, src, tgt, save_history=False):
                            parts.append(tok)
                        return "".join(parts)

                translations = await asyncio.gather(*[one(b) for b in blocks])
                blocks_with_t = list(zip(translations, [b.bbox for b in blocks]))
                # 在主线程渲染
                QApplication.instance().postEvent(
                    self, _OcrResultEvent(crop_image, blocks_with_t, mode)
                )
            try:
                asyncio.run(run())
            except Exception as e:
                self._ocr_error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ocr_result(self, crop_image, blocks, mode: str) -> None:
        """主线程：按模式显示结果窗口。"""
        if mode == "overlay":
            pos = self._ocr_overlay.geometry().topLeft() if hasattr(self, "_ocr_overlay") else None
            win = OverlayResultWindow(self)
            win.show_result(crop_image, blocks, pos)
        elif mode == "compare":
            win = CompareResultWindow(self)
            win.show_result(crop_image, blocks, None)
