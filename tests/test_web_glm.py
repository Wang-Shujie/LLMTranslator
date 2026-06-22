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
