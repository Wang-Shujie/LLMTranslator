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


def _is_cjk_char(ch: str) -> bool:
    """是否为 CJK 字符（中日韩统一表意文字 + 假名 + 韩文音节）。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF    # CJK Unified Ideographs（中文/日文汉字）
        or 0x3400 <= code <= 0x4DBF  # CJK Extension A
        or 0xF900 <= code <= 0xFAFF  # CJK Compatibility Ideographs
        or 0x3040 <= code <= 0x30FF  # 平假名 / 片假名
        or 0xAC00 <= code <= 0xD7AF  # 韩文音节
    )


def looks_like_chinese(text: str) -> bool:
    """文本是否含 CJK 字符（粗略判定为"中文侧"）。空串视为非中文。"""
    return any(_is_cjk_char(ch) for ch in text)


_CJK_LANGS = {"zh", "ja", "ko"}


def _script(text: str) -> str:
    """判定文本主要书写系统：'zh' | 'ja' | 'ko' | 'latin' | ''（空串）。

    优先级：假名→日、韩文音节→韩、汉字→中、ASCII 字母→拉丁。
    拉丁系（英/法/德…）无法细分，统一归 'latin'（实际默认语言多为中文，够用）。
    """
    has_han = has_kana = has_hangul = has_latin = False
    for ch in text:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            has_kana = True
        elif 0xAC00 <= code <= 0xD7AF:
            has_hangul = True
        elif (0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF
              or 0xF900 <= code <= 0xFAFF):
            has_han = True
        elif ch.isascii() and ch.isalpha():
            has_latin = True
    if has_kana:
        return "ja"
    if has_hangul:
        return "ko"
    if has_han:
        return "zh"
    if has_latin:
        return "latin"
    return ""


def selection_target(text: str, default_lang: str) -> str | None:
    """划词翻译的目标语言：源语言一律自动检测。

    - 文本非默认语言 → 返回 default_lang（译为默认语言）；
    - 文本已是默认语言 → 返回 None（**不翻译**，弹窗原样显示原文）。

    default_lang 是用户的目标语言（通常是母语，如 zh）。判定"是否默认语言"：
    CJK 系（zh/ja/ko）需书写系统精确匹配；拉丁系（en/fr/de…）统一按 latin 判定。
    """
    sc = _script(text)
    if not sc:
        return None  # 无可识别文字（空串/纯符号数字）→ 不翻译
    if default_lang in _CJK_LANGS:
        is_default = sc == default_lang
    else:
        is_default = sc == "latin"
    return None if is_default else default_lang


def code_to_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def name_to_code(name: str) -> str | None:
    for code, nm in LANGUAGES.items():
        if nm == name:
            return code
    return None
