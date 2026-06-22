import pytest
from llm_translator.utils.sse import parse_sse


@pytest.mark.asyncio
async def test_yields_data_events():
    raw = b"data: {\"a\":1}\n\ndata: {\"a\":2}\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == [{"a": 1}, {"a": 2}]


@pytest.mark.asyncio
async def test_ignores_done_and_comments():
    raw = b": ping\n\ndata: [DONE]\n\ndata: {\"a\":3}\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == [{"a": 3}]


@pytest.mark.asyncio
async def test_handles_plain_text_payload():
    raw = b"data: hello world\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == ["hello world"]


class _byte_stream:
    """把 bytes 模拟成 httpx 的 aiter_bytes()/aiter_lines() 行为：按行产出 bytes。"""
    def __init__(self, data: bytes):
        self._lines = data.split(b"\n")

    async def __aiter__(self):
        for line in self._lines:
            yield line
