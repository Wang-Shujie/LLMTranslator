"""TTS 引擎接口 + 在线 edge-tts 实现（离线引擎为预留扩展点）。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class TtsError(Exception):
    """TTS 合成失败。"""


class TtsEngine(ABC):
    """语音合成引擎接口。

    v1 仅有在线实现 EdgeTtsEngine。后续离线引擎（如 OfflineSapiEngine，基于
    pyttsx3 / Windows SAPI）实现同一接口即可接入，调用方（TtsPlayer）无需改动。
    """

    @abstractmethod
    async def synthesize(self, text: str, lang: str) -> bytes:
        """合成语音，返回完整 mp3 字节。lang=语言码(zh/en/ja...)。失败抛 TtsError。"""


# 语言码 → edge-tts 音色（默认自然女声）
LANG_VOICE: dict[str, str] = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "ru": "ru-RU-DariyaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "th": "th-TH-PremwadeeNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "ar": "ar-SA-ZariyahNeural",
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # lang 未命中或 "auto" 时兜底


def pick_voice(lang: str) -> str:
    """语言码 → edge-tts 音色；未命中/auto → DEFAULT_VOICE。"""
    return LANG_VOICE.get(lang, DEFAULT_VOICE)


class EdgeTtsEngine(TtsEngine):
    """在线 TTS 引擎（edge-tts / 微软语音）。"""

    async def synthesize(self, text: str, lang: str) -> bytes:
        import edge_tts  # 延迟导入：便于打包收集 + 缺失时清晰报错

        voice = pick_voice(lang)
        try:
            comm = edge_tts.Communicate(text, voice)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            if not buf:
                raise TtsError("edge-tts 返回空音频")
            return bytes(buf)
        except TtsError:
            raise
        except Exception as e:  # 网络/解析等
            raise TtsError(f"edge-tts 合成失败：{e}") from e
