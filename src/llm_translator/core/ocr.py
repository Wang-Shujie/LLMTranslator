"""截图 OCR：OcrBlock + OcrEngine（RapidOCR 离线）+ OcrController（全局热键）。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


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
            # suppress=True：吞掉原按键不发给前台程序，避免热键触发目标程序自身快捷键
            keyboard.add_hotkey(hk, self._on_hotkey, suppress=True)
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
