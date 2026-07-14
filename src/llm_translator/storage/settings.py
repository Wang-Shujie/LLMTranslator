"""JSON 设置文件读写。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from llm_translator.storage import paths


@dataclass
class Settings:
    src_lang: str = "auto"
    tgt_lang: str = "en"
    default_provider: str = "deepseek-api"
    font_size: int = 14
    enabled_providers: list[str] = field(default_factory=lambda: ["deepseek-api"])
    selection_hotkey: str = "ctrl+shift+t"
    selection_enabled: bool = True
    selection_default_lang: str = "zh"      # 划译：外文译入此语言；已是此语言则不译
    ocr_hotkey: str = "ctrl+shift+o"
    ocr_enabled: bool = True
    ocr_default_lang: str = "en"            # 截译工具条默认目标语言
    doc_concurrency: int = 8
    doc_output_dir: str = ""

    @classmethod
    def load(cls) -> "Settings":
        f = paths.settings_file()
        if not f.exists():
            return cls()
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        f = paths.settings_file()
        paths.ensure_dir(f.parent)
        f.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
