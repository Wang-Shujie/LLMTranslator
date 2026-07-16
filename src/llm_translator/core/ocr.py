"""截图 OCR：OcrBlock + OcrEngine（RapidOCR 离线）+ OcrController（全局热键）。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal



@dataclass
class OcrBlock:
    text: str
    bbox: tuple[int, int, int, int]  # x, y, w, h（选区内坐标）


def _polygon_to_bbox(poly: list[list[int]]) -> tuple[int, int, int, int]:
    """4 点多边形 → (x, y, w, h)。"""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def merge_line_blocks(blocks: list[OcrBlock]) -> list[OcrBlock]:
    """合并同一行（y 中心相近）的 OCR 块，减少碎片化。

    RapidOCR 常把一行文字拆成多个小块（甚至逐词），每块单独翻译会丢失上下文、
    分段不正确。合并后每块是一整行 → 翻译更连贯。
    """
    if len(blocks) <= 1:
        return list(blocks)

    def cy(b: OcrBlock) -> float:
        return b.bbox[1] + b.bbox[3] / 2

    # 按 y 中心排序 → 分行
    sorted_b = sorted(blocks, key=cy)
    lines: list[list[OcrBlock]] = [[sorted_b[0]]]
    for b in sorted_b[1:]:
        prev = lines[-1][-1]
        # y 中心差 < 较矮块高度的一半 → 视为同行
        if abs(cy(b) - cy(prev)) < min(b.bbox[3], prev.bbox[3]) * 0.5:
            lines[-1].append(b)
        else:
            lines.append([b])

    # 每行内按 x 排序，合并文本 + bbox 取并集
    result: list[OcrBlock] = []
    for line in lines:
        line.sort(key=lambda b: b.bbox[0])
        texts = [b.text.strip() for b in line if b.text.strip()]
        if not texts:
            continue
        xs = [b.bbox[0] for b in line]
        ys = [b.bbox[1] for b in line]
        x2s = [b.bbox[0] + b.bbox[2] for b in line]
        y2s = [b.bbox[1] + b.bbox[3] for b in line]
        result.append(OcrBlock(
            text=" ".join(texts),
            bbox=(min(xs), min(ys), max(x2s) - min(xs), max(y2s) - min(ys)),
        ))
    return result


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
        # PySide6：bits() 返回 memoryview（已按 sizeInBytes 定长），无 setsize；
        # 旧 PyQt5 sip.voidptr 才需要 setsize。
        ptr = img.bits()
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
    """全局热键触发截图 OCR：按下热键 → 发 triggered()。热键经 GlobalHotkeyManager。"""

    triggered = Signal()

    def __init__(self, settings, hotkey_mgr, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._mgr = hotkey_mgr
        self._handle = None
        if settings.ocr_enabled:
            self.enable()

    def enable(self) -> None:
        if self._handle is not None:
            return
        self._handle = self._mgr.register(self._settings.ocr_hotkey, self._on_hotkey)

    def disable(self) -> None:
        if self._handle is None:
            return
        self._mgr.unregister(self._handle)
        self._handle = None

    def _on_hotkey(self) -> None:
        # Windows: 主线程(nativeEvent)；其他: keyboard 钩子线程。延到主线程下一轮发信号。
        QTimer.singleShot(0, self._fire)

    def _fire(self) -> None:
        self.triggered.emit()

