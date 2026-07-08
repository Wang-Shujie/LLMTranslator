"""翻译编排：持当前 provider，流式产出 token，完成后写历史。"""
from __future__ import annotations

from typing import AsyncGenerator

from llm_translator.providers.base import BaseProvider
from llm_translator.storage.history import Entry, HistoryStore


class Translator:
    def __init__(self, provider: BaseProvider, history: HistoryStore, provider_label: str) -> None:
        self.provider = provider
        self.history = history
        self.provider_label = provider_label

    def set_provider(self, provider: BaseProvider, label: str) -> None:
        self.provider = provider
        self.provider_label = label

    async def translate(self, text: str, src: str, tgt: str, save_history: bool = True) -> AsyncGenerator[str, None]:
        text = text.strip()
        if not text:
            return
        await self.provider.login()
        collected: list[str] = []
        async for token in self.provider.translate(text, src, tgt):
            collected.append(token)
            yield token
        # 流结束后落库（划词弹窗等临时查询可传 save_history=False 跳过）
        if save_history:
            self.history.add(
                Entry(
                    src=src,
                    tgt=tgt,
                    source_text=text,
                    target_text="".join(collected),
                    provider=self.provider_label,
                )
            )
