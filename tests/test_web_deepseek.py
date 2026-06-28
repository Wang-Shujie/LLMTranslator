from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.deepseek import DeepSeekWebProvider

import pytest
from unittest.mock import patch


def test_health_requires_token():
    assert DeepSeekWebProvider("deepseek-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("deepseek-web", "token", "abc")
    assert DeepSeekWebProvider("deepseek-web", creds).health() is True


def test_extract_text_first_chunk():
    # 首个内容片：完整 JSON-patch
    event = {"p": "response/content", "o": "APPEND", "v": "译文"}
    assert DeepSeekWebProvider.extract_text(event) == "译文"


def test_extract_text_continuation_chunk():
    # 后续内容片：简写裸 v（路径沿用上一条）
    assert DeepSeekWebProvider.extract_text({"v": "续片"}) == "续片"


def test_extract_text_ignores_non_text_events():
    # 初始响应对象（v 是 dict）与状态事件都应忽略
    assert DeepSeekWebProvider.extract_text({"v": {"response": {}}}) == ""
    assert DeepSeekWebProvider.extract_text({"p": "response/status", "v": "FINISHED"}) == ""
    assert DeepSeekWebProvider.extract_text({"p": "response/accumulated_token_usage", "o": "SET", "v": 57}) == ""


# ---- translate() 用 mock 覆盖三步流程（创建会话 → PoW → 流式翻译）----

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
        yield 'data: {"p": "response/content", "o": "APPEND", "v": "你好"}'
        yield 'data: {"v": "吗"}'
        yield 'data: {"p": "response/status", "v": "FINISHED"}'


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
        if "chat_session/create" in url:
            return _Resp({"data": {"biz_data": {"id": "sid-123"}}})
        if "create_pow_challenge" in url:
            return _Resp({"data": {"biz_data": {"challenge": {"algorithm": "x"}}}})
        return _Resp({})

    def stream(self, method, url, **k):
        return _StreamCM()


@pytest.mark.asyncio
async def test_translate_full_flow_with_pow():
    """回归 BUG7：完整三步流程 + JSON-patch 流（首片+续片）解析。"""
    creds = CredentialStore()
    creds.set("deepseek-web", "token", "abc")
    p = DeepSeekWebProvider("deepseek-web", creds)
    with patch("curl_cffi.requests.AsyncSession", _FakeSession), \
         patch("llm_translator.providers.web.pow.solve_challenge", return_value="fakepow"):
        out = [t async for t in p.translate("hi", "en", "zh")]
    assert "".join(out) == "你好吗"
