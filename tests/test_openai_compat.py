import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.api.openai_compat import OpenAICompatProvider, PRESETS, preset_for


@pytest.fixture(autouse=True)
def _isolate_credentials(data_dir):
    """每个用例使用独立临时凭据目录，避免污染真实用户数据 / 用例间互相串扰。"""
    yield


def _make_provider(provider_id="deepseek-api"):
    creds = CredentialStore()
    if provider_id == "deepseek-api":
        creds.set("deepseek-api", "api_key", "sk-test")
    return OpenAICompatProvider("deepseek-api", creds)


def test_presets_contain_expected():
    assert "deepseek" in PRESETS
    assert PRESETS["deepseek"]["base_url"].endswith("/v1")


def test_preset_for_returns_matching_defaults():
    # 每个 API provider_id 都能拿到对应的预设默认 base_url / model
    assert preset_for("deepseek-api")["base_url"] == PRESETS["deepseek"]["base_url"]
    assert preset_for("glm-api")["model"] == PRESETS["glm"]["model"]
    assert preset_for("openai")["base_url"] == PRESETS["openai"]["base_url"]


def test_preset_for_unknown_id_falls_back():
    # 未知 id 回落到 deepseek，而不是抛 KeyError（UI 预填不能崩）
    assert preset_for("does-not-exist") == PRESETS["deepseek"]


def test_health_requires_key():
    creds = CredentialStore()  # 空
    p = OpenAICompatProvider("deepseek-api", creds)
    assert p.health() is False


def test_health_true_with_key():
    p = _make_provider()
    assert p.health() is True


@pytest.mark.asyncio
async def test_login_with_valid_key_health_true():
    p = _make_provider()
    await p.login()  # 无网络环境下不抛错（login 仅做本地 Key 存在性校验）
    assert p.health() is True


@pytest.mark.asyncio
async def test_login_without_key_raises():
    from llm_translator.providers.base import AuthError
    creds = CredentialStore()
    p = OpenAICompatProvider("deepseek-api", creds)
    with pytest.raises(AuthError):
        await p.login()


@pytest.mark.asyncio
async def test_translate_yields_delta_tokens():
    p = _make_provider()
    sse = b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\ndata: {"choices":[{"delta":{"content":"lo"}}]}\n\ndata: [DONE]\n\n'

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self): pass
        async def aiter_lines(self):
            for line in sse.split(b"\n"):
                yield line
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=_FakeResponse())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("llm_translator.providers.api.openai_compat.httpx.AsyncClient", return_value=fake_client):
        tokens = [t async for t in p.translate("你好", "zh", "en")]
    assert "".join(tokens) == "Hello"
