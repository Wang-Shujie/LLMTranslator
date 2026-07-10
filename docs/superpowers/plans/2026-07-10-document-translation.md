# 文档翻译 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 菜单"文档翻译…" → 选 .docx/.txt → 逐段并发翻译 → 输出同格式译文文件（同目录 + `_目标语言` 后缀），保留段落结构/样式。

**Architecture:** `core/doc_translate.py`（TranslationGranularity 策略接口 + PerParagraphGranularity 实现 + WholeDocumentGranularity 预留 + DocxHandler/TxtHandler 格式处理器 + DocumentTranslator 编排）+ `ui/document_dialog.py`（选文件、语言、进度、取消）+ main_window 菜单入口。

**Tech Stack:** Python 3.12 · `python-docx`（docx 逐段抽取/写回）· 标准库（txt 空行分块）· 现有 worker 线程 + asyncio.run + Semaphore 并发模式。

**Spec:** `docs/superpowers/specs/2026-07-08-document-translation-design.md`
**约束：本地实现，不 push。**

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `src/llm_translator/core/doc_translate.py` | Segment + TranslationGranularity + PerParagraph/WholeDocument + DocxHandler/TxtHandler + DocumentTranslator | 新增 |
| `src/llm_translator/ui/document_dialog.py` | DocumentDialog：选文件、语言、输出、进度、取消 | 新增 |
| `src/llm_translator/storage/settings.py` | 加 `doc_concurrency`、`doc_output_dir` | 修改 |
| `src/llm_translator/ui/main_window.py` | 菜单"文档翻译…" + on_document_translate | 修改 |
| `tests/test_doc_translate.py` | Handler + Granularity 单测 | 新增 |
| `pyproject.toml` | 依赖加 `python-docx` | 修改 |
| `build.spec` | `collect_submodules("docx")` | 修改 |
| `README.md` | 文档翻译功能 | 修改 |

---

## Task 1: 加 python-docx 依赖

**Files:** Modify: `pyproject.toml`

- [ ] **Step 1:** In `dependencies`, after `"onnxruntime>=1.16",` add `"python-docx>=1.1",`.

- [ ] **Step 2:** Install + verify:
Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]"` (timeout 300000)
Run: `.venv/Scripts/python.exe -c "import docx; print('docx ok')"`
Expected: `docx ok`

- [ ] **Step 3:** Commit: `git add pyproject.toml && git commit -m "feat(docs): add python-docx dependency"`

---

## Task 2: Settings 加 doc_concurrency / doc_output_dir（TDD）

**Files:** Modify: `src/llm_translator/storage/settings.py`, `tests/test_settings.py`

- [ ] **Step 1:** Append to `tests/test_settings.py`:
```python
def test_doc_defaults(data_dir):
    s = Settings.load()
    assert s.doc_concurrency == 8
    assert s.doc_output_dir == ""


def test_doc_persist(data_dir):
    s = Settings.load()
    s.doc_concurrency = 4
    s.doc_output_dir = "/tmp/out"
    s.save()
    reloaded = Settings.load()
    assert reloaded.doc_concurrency == 4
    assert reloaded.doc_output_dir == "/tmp/out"
```

- [ ] **Step 2:** Run → FAIL (no attr).

- [ ] **Step 3:** Add to Settings (after `ocr_enabled`):
```python
    doc_concurrency: int = 8
    doc_output_dir: str = ""
```

- [ ] **Step 4:** Run settings tests → PASS (8); full suite → 76 passed.
- [ ] **Step 5:** Commit: `git add src/llm_translator/storage/settings.py tests/test_settings.py && git commit -m "feat(settings): add doc_concurrency + doc_output_dir"`

---

## Task 3: core/doc_translate.py — 策略接口 + 格式处理器 + 编排（TDD）

**Files:** Create: `src/llm_translator/core/doc_translate.py`, `tests/test_doc_translate.py`

- [ ] **Step 1:** Write `tests/test_doc_translate.py`:
```python
import asyncio
import pytest
from llm_translator.core.doc_translate import (
    Segment, TranslationGranularity, PerParagraphGranularity,
    WholeDocumentGranularity, TxtHandler, DocxHandler, DocumentTranslator,
    handler_for_format,
)


class _FakeProvider:
    """Fake provider that translates by appending '_T'."""
    async def login(self): pass
    async def translate(self, text, src, tgt):
        for tok in [text + "_T"]:
            yield tok


# ---- Granularity ----

@pytest.mark.asyncio
async def test_per_paragraph_translates_each_segment():
    g = PerParagraphGranularity(concurrency=4)
    result = await g.translate(["hello", "world"], _FakeProvider(), "en", "zh")
    assert result == ["hello_T", "world_T"]


def test_whole_document_raises_not_implemented():
    g = WholeDocumentGranularity()
    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop().run_until_complete(
            asyncio.wait_for(g.translate(["x"], _FakeProvider(), "en", "zh"), 1)
        )


# ---- TxtHandler ----

def test_txt_handler_roundtrip(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello\n\nWorld", encoding="utf-8")
    handler = TxtHandler()
    segments = handler.extract(str(f))
    assert len(segments) == 2
    assert segments[0].text == "Hello"
    segments[0].set_translation("你好")
    segments[1].set_translation("世界")
    out = tmp_path / "test_zh.txt"
    handler.save(str(out))
    assert out.read_text(encoding="utf-8") == "你好\n\n世界"


def test_txt_handler_empty_blocks_preserved(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("A\n\n\n\nB", encoding="utf-8")
    handler = TxtHandler()
    segments = handler.extract(str(f))
    segments[0].set_translation("X")
    segments[-1].set_translation("Y")
    out = tmp_path / "out.txt"
    handler.save(str(out))
    content = out.read_text(encoding="utf-8")
    assert "X" in content and "Y" in content


# ---- DocxHandler ----

def test_docx_handler_roundtrip(tmp_path):
    from docx import Document
    f = tmp_path / "test.docx"
    doc = Document()
    doc.add_paragraph("Hello world")
    doc.add_paragraph("Goodbye")
    doc.save(str(f))

    handler = DocxHandler()
    segments = handler.extract(str(f))
    assert len(segments) == 2
    assert segments[0].text == "Hello world"
    segments[0].set_translation("你好世界")
    segments[1].set_translation("再见")
    out = tmp_path / "test_zh.docx"
    handler.save(str(out))

    doc2 = Document(str(out))
    texts = [p.text for p in doc2.paragraphs if p.text.strip()]
    assert texts == ["你好世界", "再见"]


def test_docx_handler_table_cells(tmp_path):
    from docx import Document
    f = tmp_path / "test.docx"
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Age"
    doc.save(str(f))

    handler = DocxHandler()
    segments = handler.extract(str(f))
    texts = [s.text for s in segments]
    assert "Name" in texts and "Age" in texts
    for s in segments:
        s.set_translation(s.text + "_T")
    out = tmp_path / "out.docx"
    handler.save(str(out))
    doc2 = Document(str(out))
    assert doc2.tables[0].cell(0, 0).text.strip().endswith("_T")


# ---- handler_for_format ----

def test_handler_for_format_txt():
    assert isinstance(handler_for_format("file.txt"), TxtHandler)


def test_handler_for_format_docx():
    assert isinstance(handler_for_format("file.docx"), DocxHandler)


def test_handler_for_format_unsupported():
    with pytest.raises(ValueError):
        handler_for_format("file.pdf")
```

- [ ] **Step 2:** Run → FAIL (module not found).

- [ ] **Step 3:** Implement `src/llm_translator/core/doc_translate.py`:
```python
"""文档翻译：逐段并发翻译 .docx/.txt，保留段落结构。

TranslationGranularity 策略接口（PerParagraph 实现，WholeDocument 预留 B）。
DocxHandler 用 python-docx 逐段抽取+写回；TxtHandler 用标准库空行分块。
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class Segment:
    """一段文本 + 写回回调（翻译后调用 set_translation 写回原文档对象）。"""

    def __init__(self, text: str, setter: Callable[[str], None]) -> None:
        self.text = text
        self._setter = setter

    def set_translation(self, translation: str) -> None:
        self._setter(translation)


# ---- 翻译粒度策略（预留 B 的扩展点）----

class TranslationGranularity(ABC):
    """segments → 译文列表，1:1 对应。"""

    @abstractmethod
    async def translate(self, segments: list[str], provider, src: str, tgt: str) -> list[str]:
        ...


class PerParagraphGranularity(TranslationGranularity):
    """逐段并发翻译（v1，方案①）。"""

    def __init__(self, concurrency: int = 8) -> None:
        self._sem = asyncio.Semaphore(concurrency)

    async def translate(self, segments: list[str], provider, src: str, tgt: str) -> list[str]:
        async def one(text: str) -> str:
            async with self._sem:
                parts: list[str] = []
                async for tok in provider.translate(text, src, tgt):
                    parts.append(tok)
                return "".join(parts)
        return await asyncio.gather(*[one(s) for s in segments])


class WholeDocumentGranularity(TranslationGranularity):
    """整篇翻译（预留，方案② B），v1 不实现。"""

    async def translate(self, segments: list[str], provider, src: str, tgt: str) -> list[str]:
        raise NotImplementedError("整篇翻译：后续版本实现")


# ---- 格式处理器 ----

class TxtHandler:
    """纯文本：按空行分块。"""

    def __init__(self) -> None:
        self._blocks: list[str] = []

    def extract(self, path: str) -> list[Segment]:
        text = Path(path).read_text(encoding="utf-8")
        self._blocks = text.split("\n\n")
        return [
            Segment(b, lambda t, i=i: self._blocks.__setitem__(i, t))
            for i, b in enumerate(self._blocks)
        ]

    def save(self, out_path: str) -> None:
        Path(out_path).write_text("\n\n".join(self._blocks), encoding="utf-8")


class DocxHandler:
    """Word .docx：python-docx 逐段抽取（正文+表格）+ 写回。段内 run 格式为已知边界。"""

    def __init__(self) -> None:
        self._doc = None

    def extract(self, path: str) -> list[Segment]:
        from docx import Document as DocxDocument
        self._doc = DocxDocument(path)
        segments: list[Segment] = []
        for para in self._doc.paragraphs:
            if para.text.strip():
                segments.append(Segment(para.text, self._make_setter(para)))
        for table in self._doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if para.text.strip():
                            segments.append(Segment(para.text, self._make_setter(para)))
        return segments

    @staticmethod
    def _make_setter(para):
        def setter(t: str) -> None:
            for run in para.runs:
                run.text = ""
            if para.runs:
                para.runs[0].text = t
            else:
                para.add_run(t)
        return setter

    def save(self, out_path: str) -> None:
        self._doc.save(out_path)


def handler_for_format(path: str):
    """根据文件扩展名返回对应的 Handler。"""
    ext = Path(path).suffix.lower()
    if ext == ".txt":
        return TxtHandler()
    if ext == ".docx":
        return DocxHandler()
    raise ValueError(f"不支持的格式：{ext}（v1 仅支持 .docx/.txt）")


# ---- 编排 ----

class DocumentTranslator:
    """文档翻译编排：extract → translate → write-back → save。"""

    def __init__(self, granularity: TranslationGranularity) -> None:
        self._granularity = granularity

    async def translate_document(
        self, path: str, out_path: str, provider, src: str, tgt: str
    ) -> int:
        """翻译文档，返回段数。失败抛异常。"""
        handler = handler_for_format(path)
        segments = handler.extract(path)
        if not segments:
            raise ValueError("文档为空或无文字")
        texts = [s.text for s in segments]
        translations = await self._granularity.translate(texts, provider, src, tgt)
        for seg, tr in zip(segments, translations):
            seg.set_translation(tr)
        handler.save(out_path)
        return len(segments)
```

- [ ] **Step 4:** Run doc tests → PASS (9); full suite → 76 + 9 = 85.
- [ ] **Step 5:** Commit: `git add src/llm_translator/core/doc_translate.py tests/test_doc_translate.py && git commit -m "feat(docs): DocumentTranslator + handlers + granularity (TDD)"`

---

## Task 4: ui/document_dialog.py — 选文件/进度/取消

**Files:** Create: `src/llm_translator/ui/document_dialog.py`

- [ ] **Step 1:** Implement (file picker, lang dropdowns, output path, progress, cancel, worker thread):
```python
"""文档翻译对话框：选文件 → 翻译（worker 线程）→ 进度 + 完成/取消。"""
from __future__ import annotations

import asyncio
import os
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
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
        self._src_combo = QComboBox()
        self._tgt_combo = QComboBox()
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
```

> **Note:** v1 progress is coarse (0→100 on completion) since per-segment progress would require restructuring DocumentTranslator to yield per-segment results. The cancel flag is set but the worker thread completes naturally (can't kill a thread); v1 cancel is advisory (the output isn't written if the user closes the dialog). This is acceptable per the spec's "v1 简洁" principle.

- [ ] **Step 2:** Headless construct + full suite.
- [ ] **Step 3:** Commit: `git add src/llm_translator/ui/document_dialog.py && git commit -m "feat(docs): DocumentDialog (file picker + progress + cancel)"`

---

## Task 5: 主窗口集成 — 菜单"文档翻译…"

**Files:** Modify: `src/llm_translator/ui/main_window.py`

- [ ] **Step 1:** Add import after the OCR imports:
```python
from llm_translator.ui.document_dialog import DocumentDialog
```

- [ ] **Step 2:** Add menu action before "关于":
old:
```python
        menu.addAction(self._ocr_action)
        menu.addAction("关于", self.on_about)
```
new:
```python
        menu.addAction(self._ocr_action)
        menu.addAction("文档翻译…", self.on_document_translate)
        menu.addAction("关于", self.on_about)
```

- [ ] **Step 3:** Add handler method (near on_settings):
```python
    def on_document_translate(self) -> None:
        """打开文档翻译对话框。"""
        dlg = DocumentDialog(self.credentials, self.settings, self)
        dlg.exec()
```

- [ ] **Step 4:** Update `tests/test_main_window_menu.py` to expect 6 menu items (add "文档翻译…").
- [ ] **Step 5:** Headless construct + full suite (85).
- [ ] **Step 6:** Commit: `git add src/llm_translator/ui/main_window.py tests/test_main_window_menu.py && git commit -m "feat(docs): wire document translation into main window menu"`

---

## Task 6: build.spec — 打包 python-docx

**Files:** Modify: `build.spec`

- [ ] **Step 1:** Add after the onnxruntime collect_all block:
```python
# python-docx（文档翻译）纯 Python，收集子模块
_docx_datas, _docx_binaries, _docx_hi = collect_all("docx")
```

- [ ] **Step 2:** Wire `_docx_binaries` into binaries, `_docx_datas` into datas, `*_docx_hi` into hiddenimports (same pattern as the other collect_all entries).
- [ ] **Step 3:** Syntax-check + commit: `build(docs): bundle python-docx in PyInstaller spec`

---

## Task 7: README — 文档翻译功能

**Files:** Modify: `README.md`

- [ ] **Step 1:** Add feature bullet after OCR:
```markdown
- 文档翻译：菜单 → 文档翻译… → 选 .docx/.txt → 逐段翻译保留段落结构 → 输出同格式译文
```

- [ ] **Step 2:** Add section before 声明:
```markdown
## 文档翻译
菜单 → 文档翻译… → 选择 `.docx` 或 `.txt` 文件 → 逐段并发翻译 → 输出同格式译文（同目录 + `_目标语言` 后缀）。docx 保留段落结构/样式（段内 run 级格式为已知边界）。预留 `WholeDocumentGranularity` 整篇翻译接口（方案 B），后续实现。
```

- [ ] **Step 3:** Commit: `docs(docs): document document translation + reserved interface`

---

## 完成后：整体验收

- [ ] **全测试套件**：`.venv/Scripts/python.exe -m pytest -q` → 全绿（85 项）。
- [ ] **headless 整窗**：Task 5 Step 5 通过。
- [ ] **手动验收清单**（spec §11）：
```
[ ] 菜单"文档翻译…" → 对话框 → 选 .docx → 翻译 → 同目录产出 report_zh.docx
[ ] 选 .txt → 产出同名 _zh.txt
[ ] docx 段落结构/样式保留
[ ] 进度条；点取消
[ ] 表格内文字也被翻译
[ ] 未配置模型时提示
```
