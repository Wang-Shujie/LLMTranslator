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
