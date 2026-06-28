import pytest
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.glm import GlmWebProvider


def test_health_without_token():
    p = GlmWebProvider("glm-web", CredentialStore())
    assert p.health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("glm-web", "token", "abc")
    p = GlmWebProvider("glm-web", creds)
    assert p.health() is True


def test_extract_text_from_event():
    # 智谱清言 SSE 事件中的文本片段提取逻辑（纯函数，可单测）
    event = {"parts": [{"content": "你好", "status": "success"}]}
    assert GlmWebProvider.extract_text(event) == "你好"


def test_extract_text_returns_empty_on_unknown_shape():
    assert GlmWebProvider.extract_text({"unknown": 1}) == ""


from unittest.mock import patch


class _FakeResp:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        # 智谱清言 SSE：content 字段为文本片段
        yield 'data: {"content": "你好"}'
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
    creds.set("glm-web", "token", "abc")
    p = GlmWebProvider("glm-web", creds)
    with patch("curl_cffi.requests.AsyncSession", _FakeSession):
        out = [t async for t in p.translate("hello", "en", "zh")]
    assert "".join(out) == "你好"
