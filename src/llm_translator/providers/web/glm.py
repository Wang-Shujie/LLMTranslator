"""智谱清言（chatglm.cn）网页逆向 Provider。

流程（依 xiaoY233/GLM-Free-API 核实）：
1. 用 refresh_token（cookie chatglm_refresh_token）POST /chatglm/user-api/user/refresh
   换 access_token
2. POST /chatglm/backend-api/assistant/stream（Bearer access_token + 签名头）流式取译文

每次请求需带签名：sign = md5("{timestamp}-{nonce}-{SECRET}")，其中 timestamp 是把
毫秒时间戳的倒数第二位换成 (各位数字之和 - 倒数第二位) % 10。SECRET 为公开逆向得到的常量。
SSE 是 snapshot 模式：每个事件带全量 parts，取 parts[].content[](type==text) 累积，
只产出相比上一次的新增片段。
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_BASE = "https://chatglm.cn"
_SECRET = "8a1317a7468aa3ad86e997d08f3f31cb"
_ASSISTANT_ID = "65940acff94777010aa6b796"

_FAKE_HEADERS = {
    "Accept": "text/event-stream",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "App-Name": "chatglm",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Origin": "https://chatglm.cn",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-App-Fr": "browser_extension",
    "X-App-Platform": "pc",
    "X-App-Version": "0.0.1",
    "X-Device-Brand": "",
    "X-Device-Model": "",
    "X-Exp-Groups": "na_android_config:exp:NA,na_4o_config:exp:4o_A",
    "X-Lang": "zh",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}


def _sign() -> tuple[str, str, str]:
    """生成智谱请求签名，返回 (timestamp, nonce, sign)。"""
    a_str = str(int(time.time() * 1000))
    n = len(a_str)
    digits = [int(c) for c in a_str]
    checksum = (sum(digits) - digits[n - 2]) % 10
    timestamp = a_str[: n - 2] + str(checksum) + a_str[-1]
    nonce = uuid.uuid4().hex
    sign = hashlib.md5(f"{timestamp}-{nonce}-{_SECRET}".encode()).hexdigest()
    return timestamp, nonce, sign


class GlmWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "智谱清言"

    def required_credential_keys(self) -> list[str]:
        return ["token"]  # 存的是 chatglm_refresh_token

    @staticmethod
    def extract_text(event: object) -> str:
        """智谱 SSE snapshot：{parts:[{content:[{type:'text',text:'...'}]}]}，累加全部文本。"""
        if not isinstance(event, dict):
            return ""
        parts = event.get("parts")
        if not isinstance(parts, list):
            return ""
        text = ""
        for part in parts:
            content = part.get("content") if isinstance(part, dict) else None
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        t = item.get("text")
                        if isinstance(t, str):
                            text += t
        return text

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        refresh_token = self.get_credential("token")
        prompt = "\n\n".join(m["content"] for m in build_messages(text, src, tgt))

        async with AsyncSession(impersonate="chrome120") as s:
            # 1) refresh_token 换 access_token
            ts, nonce, sign = _sign()
            r = await s.post(
                f"{_BASE}/chatglm/user-api/user/refresh", json={},
                headers={**_FAKE_HEADERS, "Authorization": f"Bearer {refresh_token}",
                         "X-Device-Id": uuid.uuid4().hex, "X-Nonce": nonce,
                         "X-Request-Id": uuid.uuid4().hex, "X-Sign": sign, "X-Timestamp": ts},
                timeout=30,
            )
            r.raise_for_status()
            access_token = r.json()["result"]["access_token"]

            # 2) 流式翻译
            ts, nonce, sign = _sign()
            payload = {
                "assistant_id": _ASSISTANT_ID,
                "conversation_id": "",
                "project_id": "",
                "chat_type": "user_chat",
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                "meta_data": {
                    "channel": "", "draft_id": "", "if_plus_model": True,
                    "input_question_type": "xxxx", "is_networking": True,
                    "is_test": False, "platform": "pc", "quote_log_id": "",
                },
            }
            headers = {**_FAKE_HEADERS, "Authorization": f"Bearer {access_token}",
                       "X-Device-Id": uuid.uuid4().hex, "X-Request-Id": uuid.uuid4().hex,
                       "X-Sign": sign, "X-Timestamp": ts, "X-Nonce": nonce}
            async with s.stream("POST", f"{_BASE}/chatglm/backend-api/assistant/stream",
                                json=payload, headers=headers, timeout=60) as resp:
                resp.raise_for_status()
                last = ""
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
                    full = self.extract_text(event)
                    if full and full != last:
                        # snapshot 模式：只产出新增部分
                        yield full[len(last):] if full.startswith(last) else full
                        last = full
