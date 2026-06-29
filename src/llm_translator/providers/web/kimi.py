"""Kimi（www.kimi.com）网页逆向 Provider。

完整流程（依 lorsque-sir/kimi2api 核实；Kimi 已由 kimi.moonshot.cn 迁至 www.kimi.com）：
1. POST /api/chat 创建会话 → 取 chat id
2. POST /api/chat/{id}/completion/stream 流式取译文
鉴权用登录后抓取的 access token（Authorization: Bearer）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_BASE = "https://www.kimi.com"
_IMPERSONATE = "chrome120"


class KimiWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "Kimi"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """Kimi SSE：{"event":"cmpl","text":"<文本>"}（text 为顶层字段）。"""
        if isinstance(event, dict) and event.get("event") == "cmpl":
            text = event.get("text")
            if isinstance(text, str):
                return text
        return ""

    def _headers(self) -> dict:
        token = self.get_credential("token")
        return {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        headers = self._headers()
        prompt = "\n\n".join(m["content"] for m in build_messages(text, src, tgt))

        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            # 1) 创建会话
            r = await s.post(
                f"{_BASE}/api/chat",
                json={"name": "未命名会话", "born_from": "home", "kimiplus_id": "kimi",
                      "is_example": False, "source": "web", "tags": []},
                headers=headers, timeout=30,
            )
            r.raise_for_status()
            chat_id = r.json()["id"]

            # 2) 流式翻译
            payload = {
                "model": "k2",
                "use_search": False,
                "messages": [{"role": "user", "content": prompt}],
                "kimiplus_id": "kimi",
                "extend": {"sidebar": True},
                "refs": [],
                "history": [],
                "scene_labels": [],
                "use_semantic_memory": False,
                "use_deep_research": False,
            }
            async with s.stream("POST", f"{_BASE}/api/chat/{chat_id}/completion/stream",
                                json=payload, headers=headers, timeout=60) as resp:
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
