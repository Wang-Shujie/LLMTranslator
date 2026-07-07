import pytest
from unittest.mock import patch

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.glm import GlmWebProvider, _sign


def test_health_without_token():
    p = GlmWebProvider("glm-web", CredentialStore())
    assert p.health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("glm-web", "token", "abc")
    p = GlmWebProvider("glm-web", creds)
    assert p.health() is True


def test_extract_text_snapshot_parts():
    # 智谱 SSE snapshot：parts[].content[](type==text)
    event = {"parts": [{"content": [{"type": "text", "text": "你好"}]}]}
    assert GlmWebProvider.extract_text(event) == "你好"


def test_extract_text_ignores_non_text():
    assert GlmWebProvider.extract_text({"parts": [{"content": [{"type": "image", "text": "x"}]}]}) == ""
    assert GlmWebProvider.extract_text({"unknown": 1}) == ""


def test_sign_format():
    ts, nonce, sign = _sign()
    import hashlib
    assert len(ts) == 13 and nonce and len(sign) == 32
    assert sign == hashlib.md5(f"{ts}-{nonce}-8a1317a7468aa3ad86e997d08f3f31cb".encode()).hexdigest()


# ---- translate() 两步流程（refresh -> stream）+ snapshot SSE 解析 ----

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
        # snapshot 模式：第二个事件是累积全文
        yield 'data: {"parts":[{"content":[{"type":"text","text":"你好"}]}]}'
        yield 'data: {"parts":[{"content":[{"type":"text","text":"你好吗"}]}]}'
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
        # refresh 接口返回 {result: {access_token: ...}}
        return _Resp({"result": {"access_token": "access-xyz"}})

    def stream(self, method, url, **k):
        return _StreamCM()


@pytest.mark.asyncio
async def test_translate_refresh_then_stream():
    """回归：refresh 换 access_token，再流式取译文（snapshot 只产出新增片段）。"""
    creds = CredentialStore()
    creds.set("glm-web", "token", "refresh-abc")
    p = GlmWebProvider("glm-web", creds)
    with patch("curl_cffi.requests.AsyncSession", _FakeSession):
        out = [t async for t in p.translate("hi", "en", "zh")]
    assert "".join(out) == "你好吗"
