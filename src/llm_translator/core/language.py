"""支持的语言码 ↔ 显示名称映射。"""
from __future__ import annotations

LANGUAGES: dict[str, str] = {
    "auto": "自动检测",
    "zh": "中文(简体)",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "th": "泰语",
    "vi": "越南语",
    "ar": "阿拉伯语",
}


def code_to_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def name_to_code(name: str) -> str | None:
    for code, nm in LANGUAGES.items():
        if nm == name:
            return code
    return None
