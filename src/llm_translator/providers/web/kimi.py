"""Kimi（kimi.moonshot.cn）网页逆向 Provider。

凭据：登录后从 `https://kimi.moonshot.cn/api/auth/refresh_token` 取得的 access token。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://kimi.moonshot.cn/api/chat/completion"  # VERIFY
_IMPERSONATE = "chrome120"


class KimiWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "Kimi"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """Kimi SSE 事件：{event:'cmpl', data:'<json string with text>'}。"""
        if not isinstance(event, dict):
            return ""
        if event.get("event") != "cmpl":
            return ""
        data = event.get("data")
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                return ""
            return str(parsed.get("text", ""))
        if isinstance(data, dict):
            return str(data.get("text", ""))
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "use_search": False,
            "stream": True,
            "kimiplus_ids": [],
            "refs": [],
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
