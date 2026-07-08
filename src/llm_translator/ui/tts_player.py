"""TTS 播放控制器：worker 线程合成 mp3 → Qt 信号回主线程 → QMediaPlayer 播放。

代际计数 _gen：每次 play/stop 自增；worker 回来的旧结果 gen != _gen 即丢弃，
避免"停止后又突然响"。QMediaPlayer 只能在 Qt 主线程用，故合成在 worker 线程、
播放经 _synthesized 信号回到主线程。
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QMediaPlayer

from llm_translator.core.tts import TtsEngine, TtsError


class TtsPlayer(QObject):
    """朗读一段文本：合成（worker 线程）→ 临时 mp3 → QMediaPlayer 播放。

    信号：
      state_changed(str): "idle" | "loading" | "playing"
      error(str): 失败文案
    """

    state_changed = Signal(str)
    error = Signal(str)
    _synthesized = Signal(int, bytes)  # (gen, mp3 bytes) —— worker 线程→主线程

    def __init__(self, engine: TtsEngine, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._player = QMediaPlayer()
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._gen = 0
        self._tempfile: str | None = None
        self._synthesized.connect(self._play_bytes)

    def play(self, text: str, lang: str) -> None:
        """开始一次新朗读（旧的在途合成会被作废）。空文本无操作。"""
        text = (text or "").strip()
        if not text:
            return
        self._gen += 1
        gen = self._gen
        self.state_changed.emit("loading")
        engine = self._engine

        def worker() -> None:
            try:
                data = asyncio.run(engine.synthesize(text, lang))
                self._synthesized.emit(gen, data)
            except TtsError as e:
                self._emit_error(gen, str(e))
            except Exception as e:
                self._emit_error(gen, f"朗读失败：{e}")

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        """停止播放并作废在途合成。"""
        self._gen += 1
        self._player.stop()
        self._cleanup_temp()
        self.state_changed.emit("idle")

    @Slot(int, bytes)
    def _play_bytes(self, gen: int, data: bytes) -> None:
        if gen != self._gen:
            return  # 过期合成，丢弃
        self._cleanup_temp()
        fd, path = tempfile.mkstemp(suffix=".mp3")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        except OSError:
            self._emit_error(gen, "无法写入临时音频文件")
            return
        self._tempfile = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self.state_changed.emit("playing")

    def _emit_error(self, gen: int, msg: str) -> None:
        if gen != self._gen:
            return  # 过期，丢弃
        self.error.emit(msg)
        self.state_changed.emit("idle")

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self._cleanup_temp()
            self.state_changed.emit("idle")

    def _cleanup_temp(self) -> None:
        if self._tempfile:
            try:
                os.unlink(self._tempfile)
            except OSError:
                pass
            self._tempfile = None
