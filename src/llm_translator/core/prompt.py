"""构建翻译 prompt，约束 LLM 只输出译文。"""
from __future__ import annotations

from llm_translator.core.language import code_to_name


def build_messages(text: str, src: str, tgt: str) -> list[dict[str, str]]:
    src_name = code_to_name(src)
    tgt_name = code_to_name(tgt)
    if src == "auto":
        src_phrase = "the source language (auto-detect it)"
    else:
        src_phrase = src_name

    system = (
        f"You are a professional translator. "
        f"Translate the user's text from {src_phrase} to {tgt_name}. "
        f"Output ONLY the translation. Do not add any explanation, notes, or quotation marks. "
        f"Preserve original formatting and line breaks."
    )
    user = f"Text:\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
