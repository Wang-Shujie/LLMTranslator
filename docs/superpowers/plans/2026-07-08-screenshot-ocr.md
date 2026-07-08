# 截图 OCR 翻译 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全局热键 Ctrl+Shift+O → 自定义截图覆盖层（拖框选区 + 工具条）→ RapidOCR 离线识别文字+坐标 → 现有 provider 翻译 → 三种结果模式（原地覆盖/对照/直接翻译面板）。

**Architecture:** `core/ocr.py`（OcrBlock + OcrEngine 用 RapidOCR + OcrController 热键控制器）+ `core/screen_capture.py`（冻结截图）+ `ui/capture_overlay.py`（全屏选区+工具条）+ `ui/ocr_result.py`（paint_translated_blocks + 3 种结果窗口）。逐块并发翻译（原地覆盖/对照）；整段流式（直接翻译）。

**Tech Stack:** Python 3.12 · PySide6（QPainter/QScreen）· `rapidocr-onnxruntime` + `onnxruntime`（离线 OCR，~80-120MB）· `keyboard`（全局热键，已装）· 现有 worker 线程 + asyncio.run 模式。

**Spec:** `docs/superpowers/specs/2026-07-08-screenshot-ocr-design.md`
**约束：本地实现，不 push。**

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `src/llm_translator/core/ocr.py` | OcrBlock + OcrEngine（RapidOCR）+ OcrController（热键）| 新增 |
| `src/llm_translator/core/screen_capture.py` | `grab_screen() -> QPixmap`（主屏冻结快照）| 新增 |
| `src/llm_translator/ui/capture_overlay.py` | CaptureOverlay：全屏暗化 + 拖框 + 工具条 | 新增 |
| `src/llm_translator/ui/ocr_result.py` | paint_translated_blocks + 3 种结果窗口 | 新增 |
| `src/llm_translator/storage/settings.py` | 加 `ocr_hotkey`、`ocr_enabled` | 修改 |
| `src/llm_translator/ui/main_window.py` | 菜单 OCR 开关 + 控制器 + 接线 | 修改 |
| `tests/test_ocr.py` | bbox 4 点→(x,y,w,h) 转换单测 | 新增 |
| `pyproject.toml` | 依赖加 `rapidocr-onnxruntime` + `onnxruntime` | 修改 |
| `build.spec` | `collect_all("rapidocr_onnxruntime")` + `collect_all("onnxruntime")` | 修改 |
| `README.md` | OCR 功能 + 依赖体积注 | 修改 |

---

## Task 1: 加 rapidocr + onnxruntime 依赖

**Files:** Modify: `pyproject.toml`

- [ ] **Step 1: 在 `dependencies` 加两个包**

在 `keyboard>=0.13` 后追加：
```toml
    "rapidocr-onnxruntime>=1.3",
    "onnxruntime>=1.16",
```

- [ ] **Step 2: 安装并验证**（重，~80-120MB，Bash timeout 600000）

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Run: `.venv/Scripts/python.exe -c "from rapidocr_onnxruntime import RapidOCR; print('rapidocr ok')"`
Expected: `rapidocr ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(ocr): add rapidocr-onnxruntime + onnxruntime dependencies"
```

---

## Task 2: Settings 加 ocr_hotkey / ocr_enabled（TDD）

**Files:** Modify: `src/llm_translator/storage/settings.py`, `tests/test_settings.py`

- [ ] **Step 1: 追加测试到 `tests/test_settings.py`**

```python
def test_ocr_defaults(data_dir):
    s = Settings.load()
    assert s.ocr_hotkey == "ctrl+shift+o"
    assert s.ocr_enabled is True


def test_ocr_persist(data_dir):
    s = Settings.load()
    s.ocr_enabled = False
    s.ocr_hotkey = "ctrl+alt+o"
    s.save()
    reloaded = Settings.load()
    assert reloaded.ocr_enabled is False
    assert reloaded.ocr_hotkey == "ctrl+alt+o"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py -v`
Expected: FAIL — no attribute `ocr_hotkey`.

- [ ] **Step 3: 加字段到 `Settings` dataclass**（在 `selection_enabled` 后）

```python
    selection_hotkey: str = "ctrl+shift+t"
    selection_enabled: bool = True
    ocr_hotkey: str = "ctrl+shift+o"
    ocr_enabled: bool = True
```

- [ ] **Step 4: 运行确认通过 + 全套件**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py -v` → PASS（6 项）。
Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（69 + 2 = 71）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/storage/settings.py tests/test_settings.py
git commit -m "feat(settings): add ocr_hotkey + ocr_enabled"
```

---

## Task 3: core/ocr.py — OcrBlock + OcrEngine + OcrController

**Files:** Create: `src/llm_translator/core/ocr.py`, `tests/test_ocr.py`

- [ ] **Step 1: 写 `tests/test_ocr.py`（bbox 转换单测，不联网）**

```python
from llm_translator.core.ocr import OcrBlock, _polygon_to_bbox


def test_polygon_to_bbox_simple():
    poly = [[10, 20], [110, 20], [110, 50], [10, 50]]
    assert _polygon_to_bbox(poly) == (10, 20, 100, 30)


def test_polygon_to_bbox_rotated():
    poly = [[5, 5], [15, 8], [13, 18], [3, 15]]
    x, y, w, h = _polygon_to_bbox(poly)
    assert x == 3 and y == 5 and w == 12 and h == 13


def test_ocr_block_dataclass():
    b = OcrBlock(text="hello", bbox=(0, 0, 100, 20))
    assert b.text == "hello"
    assert b.bbox == (0, 0, 100, 20)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ocr.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: 实现 `src/llm_translator/core/ocr.py`**

```python
"""截图 OCR：OcrBlock + OcrEngine（RapidOCR 离线）+ OcrController（全局热键）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtGui import QGuiApplication


@dataclass
class OcrBlock:
    text: str
    bbox: tuple[int, int, int, int]  # x, y, w, h（选区内坐标）


def _polygon_to_bbox(poly: list[list[int]]) -> tuple[int, int, int, int]:
    """4 点多边形 → (x, y, w, h)。"""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class OcrEngine:
    """RapidOCR 封装：QPixmap → list[OcrBlock]。CPU/onnxruntime，跑 worker 线程。"""

    def __init__(self) -> None:
        self._engine = None  # 延迟初始化（首次 recognize 时加载模型，~1-2s）

    def _ensure_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def recognize(self, pixmap) -> list[OcrBlock]:
        """识别 QPixmap 中的文字 + 坐标框。"""
        import numpy as np
        from PySide6.QtGui import QImage

        engine = self._ensure_engine()
        img = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, bpl)
        arr = arr[:, : w * 3].reshape(h, w, 3)
        arr = arr[:, :, ::-1].copy()  # RGB → BGR（RapidOCR/OpenCV 惯例）

        result, _ = engine(arr)
        if not result:
            return []
        blocks: list[OcrBlock] = []
        for box, text, _score in result:
            blocks.append(OcrBlock(text=text, bbox=_polygon_to_bbox(box)))
        return blocks


class OcrController(QObject):
    """全局热键触发截图 OCR：按下 Ctrl+Shift+O → 发 triggered()。"""

    triggered = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hotkey: str | None = None
        if settings.ocr_enabled:
            self.enable()

    def enable(self) -> None:
        if self._hotkey is not None:
            return
        import keyboard
        hk = self._settings.ocr_hotkey
        try:
            keyboard.add_hotkey(hk, self._on_hotkey)
            self._hotkey = hk
        except Exception:
            self._hotkey = None

    def disable(self) -> None:
        if self._hotkey is None:
            return
        import keyboard
        try:
            keyboard.remove_hotkey(self._hotkey)
        except Exception:
            pass
        self._hotkey = None

    def _on_hotkey(self) -> None:
        self.triggered.emit()
```

- [ ] **Step 4: 运行确认通过 + 全套件**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ocr.py -v` → PASS（3 项）。
Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（71 + 3 = 74）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/core/ocr.py tests/test_ocr.py
git commit -m "feat(ocr): OcrBlock + OcrEngine (RapidOCR) + OcrController (hotkey)"
```

---

## Task 4: core/screen_capture.py — 冻结截图

**Files:** Create: `src/llm_translator/core/screen_capture.py`

- [ ] **Step 1: 实现**

```python
"""屏幕截图：抓取主屏整张 QPixmap（冻结帧，避免覆盖层入镜）。"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QPixmap


def grab_screen() -> QPixmap:
    """抓取主屏当前画面。"""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QPixmap()
    return screen.grabWindow(0)
```

- [ ] **Step 2: headless 验证 + 全套件**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "from PySide6.QtWidgets import QApplication; app=QApplication([]); from llm_translator.core.screen_capture import grab_screen; pm=grab_screen(); print('screen_capture ok', pm.width(), pm.height())"`
Expected: `screen_capture ok <w> <h>`。
Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（74）。

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/core/screen_capture.py
git commit -m "feat(ocr): screen capture (freeze primary screen)"
```

---

## Task 5: ui/ocr_result.py — 三种结果窗口 + 共享绘制函数

**Files:** Create: `src/llm_translator/ui/ocr_result.py`

- [ ] **Step 1: 实现**（含 `paint_translated_blocks` + `OverlayResultWindow` + `CompareResultWindow` + `OcrDirectPanel`）

```python
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
```

- [ ] **Step 2: headless 验证 + 全套件**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "from PySide6.QtWidgets import QApplication; app=QApplication([]); from llm_translator.ui.ocr_result import OverlayResultWindow, CompareResultWindow, OcrDirectPanel; print('ocr_result ok')"`
Expected: `ocr_result ok`。
Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（74）。

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/ui/ocr_result.py
git commit -m "feat(ocr): result views (overlay / compare / direct panel)"
```

---

## Task 6: ui/capture_overlay.py — 截图覆盖层 + 工具条

**Files:** Create: `src/llm_translator/ui/capture_overlay.py`

- [ ] **Step 1: 实现**（CaptureOverlay：全屏暗化 + 拖框选区 + 工具条 + 模式判定）

```python
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
```

- [ ] **Step 2: headless 验证 + 全套件**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QPixmap; app=QApplication([]); from llm_translator.ui.capture_overlay import CaptureOverlay; o=CaptureOverlay(QPixmap(100,100)); print('overlay ok')"`
Expected: `overlay ok`。
Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（74）。

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/ui/capture_overlay.py
git commit -m "feat(ocr): CaptureOverlay (fullscreen select + toolbar)"
```

---

## Task 7: 主窗口集成 — OCR 热键 + 菜单开关 + 接线

**Files:** Modify: `src/llm_translator/ui/main_window.py`

- [ ] **Step 1: 导入 OcrController + CaptureOverlay + 结果窗口**

old:
```python
from llm_translator.core.selection import SelectionController
from llm_translator.ui.selection_popup import SelectionPopup
```
new:
```python
from llm_translator.core.selection import SelectionController
from llm_translator.ui.selection_popup import SelectionPopup
from llm_translator.core.ocr import OcrController, OcrEngine
from llm_translator.core.screen_capture import grab_screen
from llm_translator.ui.capture_overlay import CaptureOverlay
from llm_translator.ui.ocr_result import OverlayResultWindow, CompareResultWindow, OcrDirectPanel
```

- [ ] **Step 2: `__init__` 建 OcrController**

old:
```python
        self.selection_ctrl = SelectionController(self.settings, self)
        self.selection_ctrl.captured.connect(self._show_selection_popup)

        self._build_ui()
```
new:
```python
        self.selection_ctrl = SelectionController(self.settings, self)
        self.selection_ctrl.captured.connect(self._show_selection_popup)
        self.ocr_ctrl = OcrController(self.settings, self)
        self.ocr_ctrl.triggered.connect(self._start_ocr_capture)
        self._ocr_engine = OcrEngine()

        self._build_ui()
```

- [ ] **Step 3: 菜单加 checkable "截图 OCR" 开关**

old:
```python
        menu.addAction(self._selection_action)
        menu.addAction("关于", self.on_about)
```
new:
```python
        menu.addAction(self._selection_action)
        self._ocr_action = QAction("截图 OCR (Ctrl+Shift+O)", self)
        self._ocr_action.setCheckable(True)
        self._ocr_action.setChecked(self.settings.ocr_enabled)
        menu.addAction(self._ocr_action)
        menu.addAction("关于", self.on_about)
```

- [ ] **Step 4: `_wire_signals` 连 OCR 开关**

old:
```python
        self._selection_action.toggled.connect(self.on_toggle_selection)
        self.emitter.token_received.connect(self._on_token)
```
new:
```python
        self._selection_action.toggled.connect(self.on_toggle_selection)
        self._ocr_action.toggled.connect(self.on_toggle_ocr)
        self.emitter.token_received.connect(self._on_token)
```

- [ ] **Step 5: 新增 OCR 方法**（在 `_on_expand_to_main` 之后插入）

```python
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
        self._ocr_overlay = CaptureOverlay(frozen, self)
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
        import threading, asyncio
        engine = self._ocr_engine
        translator = self.translator
        panel = OcrDirectPanel(self)
        panel.show()

        def worker():
            async def run():
                blocks = engine.recognize(crop_image)
                if not blocks:
                    panel.set_error("未识别到文字")
                    return
                ocr_text = "\n".join(b.text for b in blocks)
                panel.set_source(ocr_text)
                collected = []
                async for tok in translator.translate(ocr_text, src, tgt, save_history=False):
                    collected.append(tok)
                    panel.append_token(tok)
                panel.set_translation("".join(collected))
            try:
                asyncio.run(run())
            except Exception as e:
                panel.set_error(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _ocr_overlay_translate(self, crop_image, mode: str, src: str, tgt: str) -> None:
        """原地覆盖 / 对照模式：OCR → 逐块并发翻译 → 按模式渲染。"""
        import threading, asyncio
        engine = self._ocr_engine
        translator = self.translator

        def worker():
            async def run():
                blocks = engine.recognize(crop_image)
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
                if mode == "overlay":
                    QApplication.instance().postEvent(self, _OcrResultEvent(crop_image, blocks_with_t, "overlay"))
                else:
                    QApplication.instance().postEvent(self, _OcrResultEvent(crop_image, blocks_with_t, "compare"))
            try:
                asyncio.run(run())
            except Exception as e:
                self.status.showMessage(f"OCR 翻译失败：{e}", 5000)

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
```

> **注**：`_OcrResultEvent` 是一个用于跨线程传递结果的自定义 QEvent。在文件顶部（class MainWindow 之前）加：
```python
from PySide6.QtCore import QEvent

class _OcrResultEvent(QEvent):
    def __init__(self, crop_image, blocks, mode):
        super().__init__(QEvent.User)
        self.crop_image = crop_image
        self.blocks = blocks
        self.mode = mode
```
并在 MainWindow `event(self, event)` 中处理：
```python
    def event(self, event):
        if event.type() == QEvent.User and isinstance(event, _OcrResultEvent):
            self._on_ocr_result(event.crop_image, event.blocks, event.mode)
            return True
        return super().event(event)
```

- [ ] **Step 6: headless 整窗验证**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from llm_translator.ui.main_window import MainWindow
w = MainWindow(); w.show()
assert w.ocr_ctrl is not None
assert w._ocr_action.isChecked() is True
print('MainWindow + OCR OK')
"
```
Expected: `MainWindow + OCR OK`。

- [ ] **Step 7: 全套件 + Commit**

Run: `.venv/Scripts/python.exe -m pytest -q` → 全 PASS（74）。
Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "from PySide6.QtWidgets import QApplication; app=QApplication([]); from llm_translator.ui.main_window import MainWindow; w=MainWindow(); w.show(); print('ok')"` → `ok`。

```bash
git add src/llm_translator/ui/main_window.py
git commit -m "feat(ocr): wire screenshot OCR into main window"
```

---

## Task 8: build.spec — 打包 rapidocr + onnxruntime

**Files:** Modify: `build.spec`

- [ ] **Step 1: 加 collect_all**

old:
```python
# keyboard（划词翻译全局热键）延迟 import，整体收集
_kb_datas, _kb_binaries, _kb_hi = collect_all("keyboard")
```
new:
```python
# keyboard（划词翻译全局热键）延迟 import，整体收集
_kb_datas, _kb_binaries, _kb_hi = collect_all("keyboard")

# RapidOCR + onnxruntime（截图 OCR）重依赖，整体收集
_rapid_datas, _rapid_binaries, _rapid_hi = collect_all("rapidocr_onnxruntime")
_ort_datas, _ort_binaries, _ort_hi = collect_all("onnxruntime")
```

- [ ] **Step 2: binaries 行加 rapidocr + ort**

old:
```python
    binaries=[*curl_cffi_binaries, *_wasmtime_binaries, *_edge_binaries, *_kb_binaries],
```
new:
```python
    binaries=[*curl_cffi_binaries, *_wasmtime_binaries, *_edge_binaries, *_kb_binaries, *_rapid_binaries, *_ort_binaries],
```

- [ ] **Step 3: datas 加 rapidocr + ort**

old:
```python
        *_kb_datas,
    ],
```
new:
```python
        *_kb_datas,
        *_rapid_datas,
        *_ort_datas,
    ],
```

- [ ] **Step 4: hiddenimports 加 rapidocr + ort**

old:
```python
        *_kb_hi,
    ],
```
new:
```python
        *_kb_hi,
        *_rapid_hi,
        *_ort_hi,
    ],
```

- [ ] **Step 5: 语法校验 + Commit**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('build.spec',encoding='utf-8').read()); print('ok')"` → `ok`。
```bash
git add build.spec
git commit -m "build(ocr): bundle rapidocr + onnxruntime in PyInstaller spec"
```

---

## Task 9: README — OCR 功能 + 依赖注

**Files:** Modify: `README.md`

- [ ] **Step 1: 功能区加 OCR 条目 + 说明段**

old:
```markdown
- 划词翻译：任意程序选中文字 → Ctrl+Shift+T → 光标处弹译文明信片（可复制/展开到主窗口）
- Windows 一键安装
```
new:
```markdown
- 划词翻译：任意程序选中文字 → Ctrl+Shift+T → 光标处弹译文明信片（可复制/展开到主窗口）
- 截图 OCR：Ctrl+Shift+O 截图选区 → RapidOCR 识别 → 翻译（原地覆盖 / 对照 / 直接翻译三种模式）
- Windows 一键安装
```

old:
```markdown
## 声明
```
new:
```markdown
## 截图 OCR
全局热键 `Ctrl+Shift+O`（可在主菜单 ☰ 开关）。使用 `RapidOCR`（ONNX 离线引擎）识别截图中的文字 + 坐标，再用翻译模型译。三种结果模式：原地覆盖（译文贴在原文位置）、对照（上方同尺寸译文画布 + 下方原图）、直接翻译（面板显示原文 + 译文）。依赖 `onnxruntime` + `rapidocr-onnxruntime`（~80-120MB，首次 OCR 有模型加载耗时 ~1-2s）。

## 声明
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(ocr): document screenshot OCR + dependencies"
```

---

## 完成后：整体验收

- [ ] **全测试套件**：`.venv/Scripts/python.exe -m pytest -q` → 全绿（74 项）。
- [ ] **headless 整窗**：Task 7 Step 6 通过。
- [ ] **手动验收清单**（spec §11）：
```
[ ] Ctrl+Shift+O → 暗化覆盖层，能拖框选区，工具条出现
[ ] 工具条对照/直接翻译互斥（直接翻译开时对照禁用）
[ ] 原地覆盖：译文按原位置盖原文
[ ] 对照：上方同尺寸译文画布 + 下方原图
[ ] 直接翻译：面板显示 OCR 原文 + 流式译文
[ ] 各模式 Esc/点外关闭
[ ] 无文字提示；未配置模型提示
[ ] 菜单开关"截图 OCR"，状态持久化
```
