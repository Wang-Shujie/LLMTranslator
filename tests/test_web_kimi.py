from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.kimi import KimiWebProvider


def test_health_requires_token():
    assert KimiWebProvider("kimi-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("kimi-web", "token", "abc")
    assert KimiWebProvider("kimi-web", creds).health() is True


def test_extract_text():
    event = {"event": "cmpl", "data": "{\"text\":\"译文\"}"}
    assert KimiWebProvider.extract_text(event) == "译文"


def test_extract_text_empty():
    assert KimiWebProvider.extract_text({"event": "ping"}) == ""


import pytest
from unittest.mock import patch


class _FakeResp:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        # Kimi SSE：event=cmpl，data 是内含 text 的 JSON 字符串
        yield 'data: {"event": "cmpl", "data": "{\\"text\\": \\"你好\\"}"}'
        yield "data: [DONE]"


class _FakeStreamCM:
    async def __aenter__(self):
        return _FakeResp()

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, **k):
        return _FakeStreamCM()


@pytest.mark.asyncio
async def test_translate_uses_curl_cffi_stream_api():
    """回归 BUG7：translate 必须用 s.stream()（curl_cffi 0.15），而非 s.post()。"""
    creds = CredentialStore()
    creds.set("kimi-web", "token", "abc")
    p = KimiWebProvider("kimi-web", creds)
    with patch("curl_cffi.requests.AsyncSession", _FakeSession):
        out = [t async for t in p.translate("hello", "en", "zh")]
    assert "".join(out) == "你好"
