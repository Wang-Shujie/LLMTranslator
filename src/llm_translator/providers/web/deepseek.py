"""DeepSeek 网页（chat.deepseek.com）逆向 Provider。

DeepSeek 网页接口恰好是 OpenAI 兼容风格的 SSE（choices[].delta.content），
但鉴权用 user token + device id，请求需带指纹绕 Cloudflare。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://chat.deepseek.com/api/v0/chat/completion"  # VERIFY
_IMPERSONATE = "chrome120"


class DeepSeekWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "DeepSeek 网页"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """DeepSeek 网页 SSE：OpenAI 风格 choices[].delta.content。"""
        if not isinstance(event, dict):
            return ""
        choices = event.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                return str(content)
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY: 字段以实测为准
            "message": messages[-1]["content"],  # DeepSeek 网页常用单条 message
            "model": "deepseek_chat",
            "stream": True,
            "chat_session_id": "",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            async with s.post(_CHAT_URL, json=payload, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    raw = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else line
                    if not raw.startswith("data:"):
                        continue
                    data = raw[len("data:"):].strip()
                    if data in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    chunk = self.extract_text(event)
                    if chunk:
                        yield chunk
