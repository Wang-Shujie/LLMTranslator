import pytest
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.registry import all_providers, get_provider
from llm_translator.providers.api.openai_compat import OpenAICompatProvider


def test_all_providers_lists_mvp_ids():
    ids = {p["id"] for p in all_providers()}
    assert {"deepseek-api", "glm-api", "openai", "glm-web", "kimi-web", "deepseek-web"} <= ids


def test_all_providers_has_metadata_fields():
    for p in all_providers():
        assert {"id", "label", "kind"} <= set(p.keys())


def test_get_provider_api_returns_instance():
    creds = CredentialStore()
    p = get_provider("deepseek-api", creds)
    assert isinstance(p, OpenAICompatProvider)
    assert p.kind == "api"


def test_get_provider_unknown_raises():
    creds = CredentialStore()
    with pytest.raises(KeyError):
        get_provider("does-not-exist", creds)
