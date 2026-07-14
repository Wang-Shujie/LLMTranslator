"""划词译文明信片：无边框置顶小弹窗，流式译文 + 复制 + 展开主窗口。

视觉参考百度翻译划词：窗口透明（WA_TranslucentBackground）+ 自绘圆角白卡 +
QGraphicsDropShadowEffect 阴影；底栏用细分隔线隔开，左侧"划词"拨动开关 + 复制
图标（无边框），右侧蓝色"详细释义"文字链接。配色沿用主界面（强调蓝 #1890ff、
边框 #e0e0e0、圆角 10）。复用主窗口的 worker 线程 + asyncio.run + Qt 信号模式：
start_translate 在 worker 线程跑 translator.translate(...)，token 经信号回主线程
追加到 QLabel。关闭：点弹窗外（含跨程序，失焦自动关）/ Esc / ✕ / 译完 15s 自动隐藏。
"""
from __future__ import annotations

import asyncio
import ctypes
import sys
import threading

from PySide6.QtCore import Qt, QEvent, QPoint, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from llm_translator.ui.widgets import HSeparator, ToggleSwitch


def _get_foreground_win() -> int:
    """Windows：返回当前前台窗口句柄（GetForegroundWindow）；非 Windows / 失败返回 0。"""
    if sys.platform != "win32":
        return 0
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return 0


def _force_foreground_win(hwnd: int) -> None:
    """Windows：绕过前台锁，让弹窗成为前台活动窗口（AttachThreadInput + SetForegroundWindow）。

    划词弹窗由全局热键触发、出现在浏览器之上；Windows 前台锁常拒绝后台进程的
    SetForegroundWindow，导致弹窗虽显示却非活动窗口 → 收不到 WindowDeactivate，
    点走也关不掉。临时把本线程输入队列挂到前台线程即可成功夺焦。
    非 Windows 平台 no-op；任何失败静默（最差只是没拿到前台，不影响显示）。
    """
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_uint
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        cur_tid = kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        attached = False
        if fg_tid and fg_tid != cur_tid:
            attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
    except Exception:
        pass


class _PopupCard(QWidget):
    """圆角白底卡片：自绘圆角白底 + 边框（配合窗口 WA_TranslucentBackground 实现真圆角）。

    与主窗口 _RoundedFrame 一致的画法，QSS border-radius 无法裁剪透明背景，故自绘。
    """

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#d0d0d0"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)


class SelectionPopup(QWidget):
    """流式译文明信片。"""

    expand_to_main = Signal(str, str)          # source_text, target_text
    toggle_selection = Signal(bool)            # 用户拨动"划动"开关
    _token = Signal(str, int)                  # tok, gen（代际，作废旧 worker 输出）
    _finished = Signal(str, int)               # full, gen
    _error = Signal(str, int)                  # msg, gen

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(460)
        # 点击本应用内弹窗外 → 关闭（跨程序点击由 Esc/✕/自动隐藏兜底）
        if QApplication.instance() is not None:
            QApplication.instance().installEventFilter(self)

        self._src: str = ""
        self._tgt: str = ""
        self._translator = None
        # 代际计数：每次新翻译/show_source 自增；旧 worker 的输出 gen 不匹配即丢弃，
        # 避免复用弹窗时上一条未完成的翻译与新内容串在一起。
        self._gen = 0

        # 外层留出阴影绘制空间；卡片承载内容 + 圆角 + 阴影
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 14)
        outer.setSpacing(0)

        self._card = _PopupCard(self)
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        self._card.setGraphicsEffect(shadow)

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(14, 12, 14, 10)
        card_lay.setSpacing(10)

        # ---- 译文 + 右上角关闭 ----
        top = QHBoxLayout()
        top.setSpacing(8)
        self._label = QLabel("翻译中…")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.PlainText)
        self._label.setStyleSheet("color: #000000; font-size: 13px; background: transparent;")
        self._label.setMinimumHeight(20)
        top.addWidget(self._label, stretch=1)
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #bbb; "
            "font-size: 12px; padding: 0; }"
            "QPushButton:hover { color: #e81123; }"
        )
        top.addWidget(self._close_btn, alignment=Qt.AlignTop | Qt.AlignRight)
        card_lay.addLayout(top)

        # ---- 细分隔线 ----
        card_lay.addWidget(HSeparator(self._card))

        # ---- 底部操作栏：[拨动开关] 划词 | 📋 | …… | 详细释义 ----
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._toggle = ToggleSwitch(checked=True, parent=self._card)
        self._toggle.toggled.connect(self._on_toggle)
        self._toggle_label = QLabel("划词")
        self._toggle_label.setStyleSheet("color: #666; font-size: 12px; background: transparent;")

        self._copy_btn = QPushButton("📋")
        self._copy_btn.setFixedSize(24, 24)
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setToolTip("复制译文")
        self._copy_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; font-size: 14px; "
            "padding: 0; border-radius: 4px; }"
            "QPushButton:hover { background: #f0f0f0; }"
        )

        self._expand_btn = QPushButton("详细释义")
        self._expand_btn.setCursor(Qt.PointingHandCursor)
        self._expand_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #1890ff; "
            "font-size: 12px; padding: 0 2px; }"
            "QPushButton:hover { color: #40a9ff; }"
        )

        bar.addWidget(self._toggle)
        bar.addWidget(self._toggle_label)
        bar.addSpacing(4)
        bar.addWidget(self._copy_btn)
        bar.addStretch()
        bar.addWidget(self._expand_btn)
        card_lay.addLayout(bar)

        outer.addWidget(self._card)

        self._copy_btn.clicked.connect(self._on_copy)
        self._expand_btn.clicked.connect(self._on_expand)
        self._close_btn.clicked.connect(self.hide)
        self._token.connect(self._on_token)
        self._finished.connect(self._on_finished)
        self._error.connect(self._on_error)

        # 失焦关闭靠 150ms 防抖：show_at 后 _armed=False，150ms 后才武装；
        # 弹出瞬间若被前台锁弹回（Qt 乐观派发 WindowActivate 随即 WindowDeactivate），
        # 此时的失活在防抖窗口内被忽略，弹窗稳定显示、不会"闪一下就没了"。
        # 自动隐藏复用同一个 QTimer，避免 singleShot 产生孤儿定时器（复用时误关新内容）。
        self._armed = False
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.setInterval(150)
        self._arm_timer.timeout.connect(self._arm)
        self._autohide = QTimer(self)
        self._autohide.setSingleShot(True)
        self._autohide.timeout.connect(self.hide)
        # 前台轮询（Windows）：force_foreground 让本弹窗成为前台后，每 150ms 查 GetForegroundWindow，
        # 前台一旦不再是本弹窗（用户点了别的程序/窗口）→ 立即隐藏。不依赖 Qt 的 WindowDeactivate
        #（Qt.Tool 跨程序切换常不派发），故可靠。非 Windows 或夺焦失败时本机制 no-op。
        self._popup_hwnd = 0
        self._was_fg = False
        self._fg_poll = QTimer(self)
        self._fg_poll.setInterval(150)
        self._fg_poll.timeout.connect(self._on_fg_poll)
        # 尺寸自适应：译文变长时弹窗随之增高（节流 60ms，避免逐 token 重排卡顿）。
        self._refit_timer = QTimer(self)
        self._refit_timer.setSingleShot(True)
        self._refit_timer.setInterval(60)
        self._refit_timer.timeout.connect(self._refit)

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
        # 取消上一轮残留的自动隐藏定时器；重置防抖并重新计时（弹出 150ms 后才武装）
        self._autohide.stop()
        self._armed = False
        self._arm_timer.start()
        self.show()
        self.raise_()
        self.activateWindow()
        # Windows 前台夺焦：确保弹窗真正成为前台活动窗口，点走时才能收到
        # WindowDeactivate 从而关闭（非 Windows 平台 no-op）。
        _force_foreground_win(int(self.winId()))
        # 启动前台轮询（首次轮询里确认是否夺焦成功）
        self._popup_hwnd = int(self.winId())
        self._was_fg = False
        self._fg_poll.start()

    def _arm(self) -> None:
        self._armed = True

    def _refit(self) -> None:
        """按当前译文重算尺寸：宽度夹在 [min,max]，高度按 label 换行需求 + 固定开销。

        adjustSize 对嵌套布局（card→label）的 wordWrap height 不传递，故改为直接量
        "除 label 外的固定开销"（margins+顶栏+底栏，近似常量）+ label.heightForWidth。
        """
        self.adjustSize()
        self.layout().activate()
        w = min(max(self.width(), self.minimumWidth()), self.maximumWidth())
        h_overhead = max(0, self.width() - self._label.width())   # 左右 margins 等
        v_overhead = max(0, self.height() - self._label.height())  # 顶/底栏等
        label_w = max(60, w - h_overhead)
        lh = self._label.heightForWidth(label_w)
        if lh <= 0:
            lh = self._label.sizeHint().height()
        lh = max(lh, self._label.minimumHeight())
        self.resize(w, lh + v_overhead)
        # 夹回屏幕（增高后底部溢出则上移）
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = min(max(self.x(), geo.left()), geo.right() - self.width())
        y = min(max(self.y(), geo.top()), geo.bottom() - self.height())
        self.move(x, y)

    def event(self, event) -> bool:
        # 武装后窗口失活（用户点了别处，含跨程序）→ 隐藏。跨平台：Windows/X11/Wayland 均派发此事件。
        t = event.type()
        if t == QEvent.WindowActivate:
            pass
        elif t == QEvent.WindowDeactivate:
            if self._armed:
                self.hide()
        return super().event(event)

    def _on_fg_poll(self) -> None:
        # 前台轮询：夺焦成功后，前台一旦不再是本弹窗 → 隐藏（权威，跨程序可靠）。
        if not self.isVisible() or not self._armed or not self._popup_hwnd:
            return
        fg = _get_foreground_win()
        if not fg:
            return  # 非 Windows 或取前台失败 → 本机制 no-op
        if not self._was_fg:
            # 首次：确认夺焦是否成功。成功则记录并继续轮询；失败则停止（本机制无效）
            if fg == self._popup_hwnd:
                self._was_fg = True
            else:
                self._fg_poll.stop()
            return
        if fg != self._popup_hwnd:
            self.hide()

    def set_selection_enabled(self, on: bool) -> None:
        """主窗口同步全局划词开关状态到弹窗（不回发信号）。"""
        self._toggle.setChecked(on)

    def show_source(self, text: str) -> None:
        """已是默认语言（无需翻译）：原样显示选中文本，不启动 worker 线程。

        复制按钮复制原文；"详细释义"仍可展开到主窗口。15s 后自动隐藏。
        """
        self._gen += 1  # 作废可能仍在跑的翻译 worker，避免其 token 串入原文显示
        self._src = text
        self._tgt = text  # 复制即复制原文
        self._translator = None
        self._label.setText(text)
        self._refit()
        self._autohide.start(15000)

    def start_translate(self, text: str, src: str, tgt: str, translator) -> None:
        self._src = text
        self._tgt = ""
        self._translator = translator
        self._label.setText("翻译中…")
        self._gen += 1
        gen = self._gen
        translator_ref = translator

        def worker() -> None:
            async def drain():
                collected: list[str] = []
                async for tok in translator_ref.translate(text, src, tgt, save_history=False):
                    if gen != self._gen:  # 已有更新的翻译开始 → 丢弃本旧 worker 输出
                        return
                    collected.append(tok)
                    self._token.emit(tok, gen)
                if gen == self._gen:
                    self._finished.emit("".join(collected), gen)

            try:
                asyncio.run(drain())
            except Exception as e:
                if gen == self._gen:
                    self._error.emit(str(e), gen)

        threading.Thread(target=worker, daemon=True).start()

    def _on_token(self, tok: str, gen: int) -> None:
        if gen != self._gen:
            return  # 旧 worker 的迟到 token，丢弃，避免和新内容串在一起
        if self._label.text() == "翻译中…":
            self._label.setText("")
        self._label.setText(self._label.text() + tok)
        # 内容变长 → 节流重排尺寸（避免逐 token 重排卡顿）
        if not self._refit_timer.isActive():
            self._refit_timer.start()

    def _on_finished(self, full: str, gen: int) -> None:
        if gen != self._gen:
            return  # 旧 worker 的完成，丢弃，避免覆盖 _tgt
        self._tgt = full
        self._refit()  # 终态按完整译文定尺寸
        # 译完 15s 后自动隐藏，避免遗忘时长期置顶
        self._autohide.start(15000)

    def _on_error(self, msg: str, gen: int) -> None:
        if gen != self._gen:
            return
        self._label.setText(f"❌ {msg}")
        self._autohide.start(8000)

    def _on_copy(self) -> None:
        if self._tgt:
            QApplication.clipboard().setText(self._tgt)

    def _on_expand(self) -> None:
        if self._tgt or self._src:
            self.expand_to_main.emit(self._src, self._tgt)
        self.hide()

    def _on_toggle(self, on: bool) -> None:
        self.toggle_selection.emit(on)

    def eventFilter(self, _obj, event) -> bool:
        # 本应用内点弹窗外 → 关闭（跨程序点击 Qt 收不到事件，靠 Esc/✕/自动隐藏）
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.hide()
        return False

    def hideEvent(self, _event) -> None:
        # 任何方式隐藏都取消挂起的定时器，避免隐藏后再误触发（也清掉上一轮残留）
        self._autohide.stop()
        self._arm_timer.stop()
        self._fg_poll.stop()
        self._refit_timer.stop()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
