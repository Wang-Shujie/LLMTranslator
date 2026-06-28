"""智谱清言（chatglm.cn）网页逆向 Provider。

依赖登录后获取的 token（由 auth/login.py 在登录流程中抓取存入 CredentialStore）。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://chatglm.cn/chatglm/backend-api/assistant/stream"  # VERIFY
_IMPERSONATE = "chrome120"


class GlmWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "智谱清言"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """从智谱清言 SSE 事件中提取文本片段。"""
        if not isinstance(event, dict):
            return ""
        parts = event.get("parts") or event.get("choices")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and part.get("content"):
                    return str(part["content"])
        if isinstance(event.get("content"), str):
            return event["content"]
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore
        from llm_translator.utils.sse import parse_sse

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY: 字段名以实测为准
            "assistant_id": "65940acff94777010aa6b796",  # VERIFY
            "conversation_id": "",
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "meta_data": {"channel": "", "draft": "", "input": text},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            async with s.stream("POST", _CHAT_URL, json=payload, headers=headers, timeout=60) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    # 直接行级解析（curl_cffi 流为字节行）
                    if not line:
                        continue
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
