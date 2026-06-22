from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.deepseek import DeepSeekWebProvider


def test_health_requires_token():
    assert DeepSeekWebProvider("deepseek-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("deepseek-web", "token", "abc")
    assert DeepSeekWebProvider("deepseek-web", creds).health() is True


def test_extract_text():
    event = {"choices": [{"delta": {"content": "译文"}, "index": 0}]}
    assert DeepSeekWebProvider.extract_text(event) == "译文"


def test_extract_text_empty():
    assert DeepSeekWebProvider.extract_text({"choices": [{"delta": {}}]}) == ""
