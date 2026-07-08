# 划词翻译 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全局热键 `Ctrl+Shift+T` 在任意程序取词 → 光标处弹无边框置顶流式译文明信片（复制/展开主窗口），取词后强制恢复原剪贴板，主菜单可开关。

**Architecture:** `keyboard` 库注册全局热键 + 模拟 Ctrl+C；`SelectionController(QObject)` 跨线程（keyboard 线程→主线程信号）执行"QClipboard 保存→Ctrl+C→QTimer 延迟读→还原→发 captured(text,pos)"；`SelectionPopup(QWidget)` 复用 worker 线程翻译（`Translator.translate(save_history=False)`）流式显示；主窗口加菜单 checkable 开关 + 接线。

**Tech Stack:** Python 3.12 · PySide6（QClipboard/QGuiApplication/QCursor/QTimer）· `keyboard`（全局热键 + send ctrl+c）· 现有 worker 线程 + asyncio.run + Qt 信号模式。

**Spec:** `docs/superpowers/specs/2026-07-08-selection-translation-design.md`
**约束：本地实现，不 push。当前 main_window.py 已含 TTS 改动（~630 行）。**

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `src/llm_translator/core/selection.py` | `SelectionController(QObject)`：热键注册 + 取词/剪贴板恢复 + 发 `captured` | 新增 |
| `src/llm_translator/ui/selection_popup.py` | `SelectionPopup(QWidget)`：无边框置顶弹窗，流式译文 + 复制 + 展开 | 新增 |
| `src/llm_translator/core/translator.py` | `translate()` 加 `save_history` 参数（弹窗用 False） | 修改 |
| `src/llm_translator/storage/settings.py` | 加 `selection_hotkey`、`selection_enabled` | 修改 |
| `src/llm_translator/ui/main_window.py` | 菜单 checkable 开关 + 控制器 + 弹窗接线 | 修改 |
| `tests/test_translator.py` | `save_history` 单测 | 修改 |
| `tests/test_settings.py` | 新字段单测 | 修改 |
| `pyproject.toml` | 依赖加 `keyboard` | 修改 |
| `build.spec` | `collect_all("keyboard")` | 修改 |
| `README.md` | 划词功能 + 热键 + keyboard AV 注 | 修改 |

---

## Task 1: 加 keyboard 依赖

**Files:** Modify: `pyproject.toml`

- [ ] **Step 1: 在 `dependencies` 加 `keyboard`**

把 `pyproject.toml` 的 `dependencies` 改为（在 `edge-tts>=6.1` 后加 `keyboard`）：

```toml
dependencies = [
    "PySide6>=6.6",
    "PySide6-Addons>=6.6",
    "qasync>=0.27",
    "httpx>=0.27",
    "curl_cffi>=0.7",
    "cryptography>=42",
    "platformdirs>=4.2",
    "edge-tts>=6.1",
    "keyboard>=0.13",
]
```

- [ ] **Step 2: 安装并验证**

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]"` (Bash timeout 300000)
Run: `.venv/Scripts/python.exe -c "import keyboard; print('keyboard ok')"`
Expected: `keyboard ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(selection): add keyboard dependency"
```

---

## Task 2: Translator.translate() 加 save_history 参数（TDD）

**Files:**
- Modify: `src/llm_translator/core/translator.py`
- Test: `tests/test_translator.py`

- [ ] **Step 1: 在 `tests/test_translator.py` 末尾追加两个测试**

```python
@pytest.mark.asyncio
async def test_save_history_true_by_default_writes_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="p")
    async for _ in t.translate("你好", "zh", "en"):
        pass
    assert len(history.list(limit=10)) == 1


@pytest.mark.asyncio
async def test_save_history_false_skips_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="p")
    async for _ in t.translate("你好", "zh", "en", save_history=False):
        pass
    assert len(history.list(limit=10)) == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_translator.py -v`
Expected: FAIL — `save_history` 参数不存在（`TypeError: ... unexpected keyword argument 'save_history'`）。

- [ ] **Step 3: 改 `Translator.translate()` 签名 + 条件落库**

把 `src/llm_translator/core/translator.py` 的 `translate` 方法改为（加 `save_history: bool = True` 参数 + `if save_history:` 包住落库）：

```python
    async def translate(self, text: str, src: str, tgt: str, save_history: bool = True) -> AsyncGenerator[str, None]:
        text = text.strip()
        if not text:
            return
        await self.provider.login()
        collected: list[str] = []
        async for token in self.provider.translate(text, src, tgt):
            collected.append(token)
            yield token
        # 流结束后落库（划词弹窗等临时查询可传 save_history=False 跳过）
        if save_history:
            self.history.add(
                Entry(
                    src=src,
                    tgt=tgt,
                    source_text=text,
                    target_text="".join(collected),
                    provider=self.provider_label,
                )
            )
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_translator.py -v`
Expected: PASS（原 2 + 新 2 = 4 项）。

- [ ] **Step 5: 全测试套件无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS（65 + 2 = 67）。

- [ ] **Step 6: Commit**

```bash
git add src/llm_translator/core/translator.py tests/test_translator.py
git commit -m "feat(translator): add save_history flag to translate()"
```

---

## Task 3: Settings 加 selection_hotkey / selection_enabled（TDD）

**Files:**
- Modify: `src/llm_translator/storage/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 在 `tests/test_settings.py` 末尾追加测试**

```python
def test_selection_defaults(data_dir):
    s = Settings.load()
    assert s.selection_hotkey == "ctrl+shift+t"
    assert s.selection_enabled is True


def test_selection_persist(data_dir):
    s = Settings.load()
    s.selection_enabled = False
    s.selection_hotkey = "ctrl+alt+d"
    s.save()
    reloaded = Settings.load()
    assert reloaded.selection_enabled is False
    assert reloaded.selection_hotkey == "ctrl+alt+d"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py -v`
Expected: FAIL — `Settings has no attribute 'selection_hotkey'`。

- [ ] **Step 3: 给 `Settings` dataclass 加两个字段**

把 `src/llm_translator/storage/settings.py` 的 `Settings` dataclass 改为（在 `enabled_providers` 后加两行）：

```python
@dataclass
class Settings:
    src_lang: str = "auto"
    tgt_lang: str = "en"
    default_provider: str = "deepseek-api"
    font_size: int = 14
    enabled_providers: list[str] = field(default_factory=lambda: ["deepseek-api"])
    selection_hotkey: str = "ctrl+shift+t"
    selection_enabled: bool = True
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py -v`
Expected: PASS（原 2 + 新 2 = 4 项）。

- [ ] **Step 5: 全测试套件无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS（67 + 2 = 69）。

- [ ] **Step 6: Commit**

```bash
git add src/llm_translator/storage/settings.py tests/test_settings.py
git commit -m "feat(settings): add selection_hotkey + selection_enabled"
```

---

## Task 4: core/selection.py — 热键控制器 + 取词/剪贴板恢复

**Files:** Create: `src/llm_translator/core/selection.py`

> Qt + keyboard + clipboard — headless 构造验证（不写联网/全局钩子单测，与 TtsPlayer 一致）。

- [ ] **Step 1: 实现 `src/llm_translator/core/selection.py`**

```python
"""划词翻译控制器：全局热键（keyboard 库）+ 模拟 Ctrl+C 取词 + Qt QClipboard 保存/恢复。

热键回调在 keyboard 库的监听线程触发 → 发 triggered 信号（Qt 自动 QueuedConnection 跨
到主线程）→ 主线程执行"保存剪贴板 → send ctrl+c → QTimer 120ms → 读 + 还原 → 发 captured"。
QClipboard/QCursor/QTimer 只能在主线程用，故全在主线程槽里跑。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QGuiApplication


class SelectionController(QObject):
    """全局热键划词：触发后取选中文本 + 光标位置，发 captured(text, pos)。"""

    triggered = Signal()                       # keyboard 线程 → 主线程
    captured = Signal(str, QPoint)             # 取词完成（主线程发）

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hotkey: str | None = None
        self._saved_text: str = ""
        self._saved_pixmap = None
        self.triggered.connect(self._on_triggered)  # 跨线程自动 Queued
        if settings.selection_enabled:
            self.enable()

    def enable(self) -> None:
        if self._hotkey is not None:
            return  # 已注册
        import keyboard  # 延迟导入：缺依赖/打包时顶层不崩
        hk = self._settings.selection_hotkey
        try:
            keyboard.add_hotkey(hk, self._on_hotkey_thread)
            self._hotkey = hk
        except Exception:
            self._hotkey = None  # 注册失败（被占用等）→ 不崩，功能不可用

    def disable(self) -> None:
        if self._hotkey is None:
            return
        import keyboard
        try:
            keyboard.remove_hotkey(self._hotkey)
        except Exception:
            pass
        self._hotkey = None

    def _on_hotkey_thread(self) -> None:
        # keyboard 库监听线程 → 信号投到主线程
        self.triggered.emit()

    def _on_triggered(self) -> None:
        # 主线程：保存原剪贴板 → 模拟 Ctrl+C → 延迟读 + 还原
        clip = QGuiApplication.clipboard()
        self._saved_text = clip.text()
        self._saved_pixmap = clip.pixmap()
        import keyboard
        try:
            keyboard.send("ctrl+c")
        except Exception:
            pass
        QTimer.singleShot(120, self._finish_capture)

    def _finish_capture(self) -> None:
        # 主线程：读词 + 强制还原剪贴板（无论取词成败）
        clip = QGuiApplication.clipboard()
        captured = clip.text()
        if self._saved_pixmap is not None and not self._saved_pixmap.isNull():
            clip.setPixmap(self._saved_pixmap)
        else:
            clip.setText(self._saved_text)
        if captured and captured != self._saved_text:
            self.captured.emit(captured, QCursor.pos())
```

- [ ] **Step 2: headless 构造验证**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from llm_translator.core.selection import SelectionController
from llm_translator.storage.settings import Settings
s = Settings(selection_enabled=False)  # 不注册热键，仅验证构造
c = SelectionController(s)
print('selection ctrl ok')
"
```
Expected: `selection ctrl ok`（无 traceback）。

- [ ] **Step 3: 全测试套件无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS（69 项，本任务不加测试）。

- [ ] **Step 4: Commit**

```bash
git add src/llm_translator/core/selection.py
git commit -m "feat(selection): SelectionController (hotkey + clipboard capture/restore)"
```

---

## Task 5: ui/selection_popup.py — 译文明信片弹窗

**Files:** Create: `src/llm_translator/ui/selection_popup.py`

- [ ] **Step 1: 实现 `src/llm_translator/ui/selection_popup.py`**

```python
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
```

- [ ] **Step 2: headless 构造验证**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from llm_translator.ui.selection_popup import SelectionPopup
p = SelectionPopup()
print('popup ok')
"
```
Expected: `popup ok`。

- [ ] **Step 3: 全测试套件无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS（69 项）。

- [ ] **Step 4: Commit**

```bash
git add src/llm_translator/ui/selection_popup.py
git commit -m "feat(selection): SelectionPopup (streamed translation popup)"
```

---

## Task 6: 主窗口集成 — 菜单开关 + 控制器 + 弹窗接线

**Files:** Modify: `src/llm_translator/ui/main_window.py`

> 5 处改动：导入 QAction + 两个新类、菜单加 checkable 项、`__init__` 建控制器、`_wire_signals` 连开关、新增 3 个方法。

- [ ] **Step 1: 导入 QAction + 两个新类**

old（第 8 行 QtGui 导入）:
```python
from PySide6.QtGui import QColor, QCursor, QIcon, QKeySequence, QMouseEvent, QPainter, QPen, QPixmap, QShortcut
```
new:
```python
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QKeySequence, QMouseEvent, QPainter, QPen, QPixmap, QShortcut
```

old（TTS 的两行导入之后）:
```python
from llm_translator.core.tts import EdgeTtsEngine
from llm_translator.ui.tts_player import TtsPlayer
```
new:
```python
from llm_translator.core.tts import EdgeTtsEngine
from llm_translator.ui.tts_player import TtsPlayer
from llm_translator.core.selection import SelectionController
from llm_translator.ui.selection_popup import SelectionPopup
```

- [ ] **Step 2: `__init__` 建控制器 + 弹窗**

old:
```python
        self._build_translator()
        self.tts_player = TtsPlayer(EdgeTtsEngine(), self)

        self._build_ui()
```
new:
```python
        self._build_translator()
        self.tts_player = TtsPlayer(EdgeTtsEngine(), self)
        self._selection_popup: SelectionPopup | None = None
        self.selection_ctrl = SelectionController(self.settings, self)
        self.selection_ctrl.captured.connect(self._show_selection_popup)

        self._build_ui()
```

- [ ] **Step 3: 菜单加 checkable "划词翻译" 开关**

old（菜单三行）:
```python
        self._main_menu = menu = QMenu(self)  # 父对象 = 主窗口 + 存引用，避免无主 QMenu 被 GC 回收
        menu.addAction("设置", self.on_settings)
        menu.addAction("历史记录", self.open_history)
        menu.addAction("关于", self.on_about)
        self.menu_btn.setMenu(menu)
```
new:
```python
        self._main_menu = menu = QMenu(self)  # 父对象 = 主窗口 + 存引用，避免无主 QMenu 被 GC 回收
        menu.addAction("设置", self.on_settings)
        menu.addAction("历史记录", self.open_history)
        self._selection_action = QAction("划词翻译 (Ctrl+Shift+T)", self)
        self._selection_action.setCheckable(True)
        self._selection_action.setChecked(self.settings.selection_enabled)
        menu.addAction(self._selection_action)
        menu.addAction("关于", self.on_about)
        self.menu_btn.setMenu(menu)
```

- [ ] **Step 4: `_wire_signals` 连开关**

old:
```python
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self.emitter.token_received.connect(self._on_token)
```
new:
```python
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self._selection_action.toggled.connect(self.on_toggle_selection)
        self.emitter.token_received.connect(self._on_token)
```

- [ ] **Step 5: 新增 3 个方法**（在 `open_history` 方法之后插入）

```python
    def on_toggle_selection(self, on: bool) -> None:
        """开关划词翻译：持久化 + 实时注册/注销热键。"""
        self.settings.selection_enabled = on
        self.settings.save()
        if on:
            self.selection_ctrl.enable()
        else:
            self.selection_ctrl.disable()

    def _show_selection_popup(self, text: str, pos) -> None:
        """热键取词后：在光标处弹译文明信片并翻译。"""
        if self.translator is None:
            QMessageBox.warning(self, "未配置", "请先在设置中配置一个模型。")
            return
        if self._selection_popup is None:
            self._selection_popup = SelectionPopup(self)
            self._selection_popup.expand_to_main.connect(self._on_expand_to_main)
        src = self.settings.src_lang
        tgt = self.settings.tgt_lang
        self._selection_popup.show_at(pos)
        self._selection_popup.start_translate(text, src, tgt, self.translator)

    def _on_expand_to_main(self, source: str, target: str) -> None:
        """弹窗点'展开'：把原文/译文填回主界面并前置。"""
        self.src_edit.setPlainText(source)
        self.tgt_edit.setPlainText(target)
        self.showNormal()
        self.raise_()
        self.activateWindow()
```

- [ ] **Step 6: headless 整窗构造验证（含划词菜单项）**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from llm_translator.ui.main_window import MainWindow
w = MainWindow(); w.show()
assert w.selection_ctrl is not None
assert w._selection_action.isChecked() is True
assert w._selection_action.text() == '划词翻译 (Ctrl+Shift+T)'
print('MainWindow + selection OK')
"
```
Expected: `MainWindow + selection OK`（无 traceback）。

- [ ] **Step 7: 全测试套件无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS（69 项）。

- [ ] **Step 8: Commit**

```bash
git add src/llm_translator/ui/main_window.py
git commit -m "feat(selection): wire selection translation into main window"
```

---

## Task 7: build.spec — 打包 keyboard

**Files:** Modify: `build.spec`

- [ ] **Step 1: 加 keyboard 的 collect_all**

old:
```python
# edge-tts（TTS 朗读）在 EdgeTtsEngine 内延迟 import，静态分析看不见，整体收集
_edge_datas, _edge_binaries, _edge_hi = collect_all("edge_tts")
```
new:
```python
# edge-tts（TTS 朗读）在 EdgeTtsEngine 内延迟 import，静态分析看不见，整体收集
_edge_datas, _edge_binaries, _edge_hi = collect_all("edge_tts")

# keyboard（划词翻译全局热键）延迟 import，整体收集
_kb_datas, _kb_binaries, _kb_hi = collect_all("keyboard")
```

- [ ] **Step 2: binaries 加 keyboard 二进制**

old:
```python
    binaries=[*curl_cffi_binaries, *_wasmtime_binaries, *_edge_binaries],
```
new:
```python
    binaries=[*curl_cffi_binaries, *_wasmtime_binaries, *_edge_binaries, *_kb_binaries],
```

- [ ] **Step 3: datas 加 keyboard 数据**

old:
```python
        *_wasmtime_datas,
        *_edge_datas,
    ],
```
new:
```python
        *_wasmtime_datas,
        *_edge_datas,
        *_kb_datas,
    ],
```

- [ ] **Step 4: hiddenimports 加 keyboard 子模块**

old:
```python
        *collect_submodules("llm_translator"),
        *_wasmtime_hi,
        *_edge_hi,
    ],
```
new:
```python
        *collect_submodules("llm_translator"),
        *_wasmtime_hi,
        *_edge_hi,
        *_kb_hi,
    ],
```

- [ ] **Step 5: 语法校验**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('build.spec',encoding='utf-8').read()); print('build.spec syntax ok')"`
Expected: `build.spec syntax ok`。

- [ ] **Step 6: Commit**

```bash
git add build.spec
git commit -m "build(selection): bundle keyboard in PyInstaller spec"
```

---

## Task 8: README — 划词功能 + 热键 + keyboard AV 注

**Files:** Modify: `README.md`

- [ ] **Step 1: 功能区加划词条目**

old:
```markdown
- TTS 朗读：原文/译文各一个 🔊 按钮，点击朗读（在线）
- Windows 一键安装
```
new:
```markdown
- TTS 朗读：原文/译文各一个 🔊 按钮，点击朗读（在线）
- 划词翻译：任意程序选中文字 → Ctrl+Shift+T → 光标处弹译文明信片（可复制/展开到主窗口）
- Windows 一键安装
```

- [ ] **Step 2: 在"声明"段前加划词说明**

old:
```markdown
## TTS 朗读（在线）
TTS 朗读当前仅支持在线（使用 `edge-tts` / 微软语音），需要联网。代码已预留 `TtsEngine` 接口，后续版本将加入离线语音引擎（如 Windows 系统 SAPI）。

## 声明
```
new:
```markdown
## TTS 朗读（在线）
TTS 朗读当前仅支持在线（使用 `edge-tts` / 微软语音），需要联网。代码已预留 `TtsEngine` 接口，后续版本将加入离线语音引擎（如 Windows 系统 SAPI）。

## 划词翻译
全局热键 `Ctrl+Shift+T`（可在主菜单 ☰ 开关）。取词通过模拟 `Ctrl+C` 读取选中文字，**触发后会自动恢复你原有的剪贴板内容**（文本/图片）。依赖 `keyboard` 库（低级键盘钩子，极少数杀毒可能误报，自用项目可加白名单）。

## 声明
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(selection): document selection translation + hotkey + keyboard note"
```

---

## 完成后：整体验收

- [ ] **全测试套件**：`.venv/Scripts/python.exe -m pytest -q` → 全绿（69 项）。
- [ ] **headless 整窗**：Task 6 Step 6 的 smoke test 通过。
- [ ] **手动验收清单**（spec §12，需真实联网 + 真实 provider + 真实显示器）：
```
[ ] 浏览器/Word/记事本/PDF 选中文字 → Ctrl+Shift+T → 光标处弹窗流式译文
[ ] 复制一段内容 → 触发划词 → Ctrl+V → 粘贴出【原复制内容】（剪贴板已恢复）★核心
[ ] 剪贴板原是图片 → 划词后图片仍在
[ ] 弹窗点复制可用；点"展开"→ 主界面填入并前置
[ ] 点弹窗外 / Esc → 关闭
[ ] ☰ 菜单取消勾选"划词翻译" → Ctrl+Shift+T 不再触发；重启保持关闭
[ ] 未配置模型时弹窗提示
```

> 手动验收项需你本人在真实环境跑（自动测试覆盖不到全局热键/跨程序取词/音频）。
