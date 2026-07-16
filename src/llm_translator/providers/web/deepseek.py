"""DeepSeek 网页（chat.deepseek.com）逆向 Provider。

完整流程（依 xtekky/deepseek4free 核实）：
1. POST /chat_session/create 取会话 id
2. POST /chat/create_pow_challenge 取 PoW 挑战
3. WASM 解 PoW（见 pow.py，需可选依赖 wasmtime+numpy）
4. POST /chat/completion（带 x-ds-pow-response 头）流式取译文

鉴权用登录后抓取的 token（Authorization: Bearer）。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.base import ProviderUnavailable
from llm_translator.providers.web._base import WebProviderBase

_BASE = "https://chat.deepseek.com/api/v0"
_IMPERSONATE = "chrome120"
_APP_VERSION = "20241129.1"


class DeepSeekWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "DeepSeek 网页"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """DeepSeek 网页 SSE：JSON-patch 流。
        首个内容片：{"p":"response/content","o":"APPEND","v":"<文本>"}
        后续内容片（简写，路径沿用上一条）：{"v":"<文本>"}（无 p，v 为字符串）
        """
        if not isinstance(event, dict):
            return ""
        v = event.get("v")
        if not isinstance(v, str):
            return ""  # 初始 {"v":{"response":{...}}} 等非文本事件
        if event.get("p") == "response/content" and event.get("o") == "APPEND":
            return v
        if "p" not in event:
            return v  # 简写续片（thinking 关闭时裸 v 即内容）
        return ""

    def _headers(self) -> dict:
        token = self.get_credential("token")
        return {
            "accept": "*/*",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": "https://chat.deepseek.com",
            "referer": "https://chat.deepseek.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "x-app-version": _APP_VERSION,
            "x-client-locale": "en_US",
            "x-client-platform": "web",
            "x-client-version": "1.0.0-always",
        }

    async def translate(self, text: str, src: str, tgt: str, context: str = "") -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore
        from llm_translator.providers.web.pow import solve_challenge

        headers = self._headers()
        # DeepSeek 网页 completion 只接受单条 prompt，把翻译指令与原文合并
        prompt = "\n\n".join(m["content"] for m in build_messages(text, src, tgt, context=context))

        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            # 1) 创建会话
            r = await s.post(f"{_BASE}/chat_session/create", json={"character_id": None},
                             headers=headers, timeout=30)
            r.raise_for_status()
            session_id = r.json()["data"]["biz_data"]["id"]

            # 2) 取 PoW 挑战
            r = await s.post(f"{_BASE}/chat/create_pow_challenge",
                             json={"target_path": "/api/v0/chat/completion"},
                             headers=headers, timeout=30)
            r.raise_for_status()
            challenge = r.json()["data"]["biz_data"]["challenge"]

            # 3) 解 PoW（WASM 同步且略重 → 放线程里跑，避免阻塞 UI 事件循环）
            try:
                pow_response = await asyncio.to_thread(solve_challenge, challenge)
            except RuntimeError as e:  # 缺 wasmtime/numpy 可选依赖
                raise ProviderUnavailable(str(e))

            # 4) 流式翻译
            payload = {
                "chat_session_id": session_id,
                "parent_message_id": None,
                "prompt": prompt,
                "ref_file_ids": [],
                "thinking_enabled": False,
                "search_enabled": False,
            }
            async with s.stream("POST", f"{_BASE}/chat/completion", json=payload,
                                headers={**headers, "x-ds-pow-response": pow_response},
                                timeout=60) as resp:
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
