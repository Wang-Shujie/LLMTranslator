from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.kimi import KimiWebProvider

import pytest
from unittest.mock import patch


def test_health_requires_token():
    assert KimiWebProvider("kimi-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("kimi-web", "token", "abc")
    assert KimiWebProvider("kimi-web", creds).health() is True


def test_extract_text_cmpl_event():
    # Kimi SSE：event=cmpl，text 为顶层字段（依 kimi2api 核实）
    assert KimiWebProvider.extract_text({"event": "cmpl", "text": "译文"}) == "译文"


def test_extract_text_ignores_non_cmpl():
    assert KimiWebProvider.extract_text({"event": "ping"}) == ""
    assert KimiWebProvider.extract_text({"event": "search", "text": "x"}) == ""


# ---- translate() 用 mock 覆盖两步流程（创建会话 → 流式翻译）----

class _Resp:
    def __init__(self, payload):
        self._p = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._p


class _StreamResp:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        yield 'data: {"event": "cmpl", "text": "你好"}'
        yield 'data: {"event": "cmpl", "text": "吗"}'
        yield "data: [DONE]"


class _StreamCM:
    async def __aenter__(self):
        return _StreamResp()

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **k):
        # 创建会话返回 {"id": ...}
        return _Resp({"id": "chat-123"})

    def stream(self, method, url, **k):
        return _StreamCM()


@pytest.mark.asyncio
async def test_translate_two_step_flow():
    """回归：创建会话 + 流式翻译，解析 event:cmpl 顶层 text。"""
    creds = CredentialStore()
    creds.set("kimi-web", "token", "abc")
    p = KimiWebProvider("kimi-web", creds)
    with patch("curl_cffi.requests.AsyncSession", _FakeSession):
        out = [t async for t in p.translate("hi", "en", "zh")]
    assert "".join(out) == "你好吗"
