"""SSE（Server-Sent Events）流解析。

接受异步字节行或字符串行迭代器，产出每个 `data:` 事件的反序列化载荷：
JSON 字符串 → dict；其余 → 原始字符串；`[DONE]` 与注释行跳过。

注意：httpx 的 aiter_lines() 产出 str（非 bytes），故对 bytes 行先解码。
"""
from __future__ import annotations

import json
from typing import AsyncIterator


async def parse_sse(lines: AsyncIterator) -> AsyncIterator[object]:
    buffer = ""
    async for raw_line in lines:
        if isinstance(raw_line, (bytes, bytearray)):
            raw_line = raw_line.decode("utf-8", errors="replace")
        line = raw_line.rstrip("\r")
        buffer += line
        # 空行 = 事件分隔（按 SSE 规范，空行结束一个事件）
        if line == "":
            event = _parse_event(buffer)
            buffer = ""
            if event is not None:
                yield event
            continue
        buffer += "\n"


def _parse_event(buf: str) -> object | None:
    data_lines: list[str] = []
    for text_line in buf.splitlines():
        if not text_line or text_line.startswith(":"):
            continue
        if text_line.startswith("data:"):
            data_lines.append(text_line[len("data:"):].lstrip())
    if not data_lines:
        return None
    payload = "\n".join(data_lines)
    if payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return payload
