import json
from llm_translator.auth.store import CredentialStore


def test_roundtrip(data_dir):
    store = CredentialStore()
    store.set("deepseek-api", "api_key", "sk-xxx")
    assert store.get("deepseek-api", "api_key") == "sk-xxx"


def test_missing_returns_none(data_dir):
    store = CredentialStore()
    assert store.get("nope", "api_key") is None


def test_stored_value_is_encrypted_not_plaintext(data_dir):
    store = CredentialStore()
    store.set("p", "api_key", "sk-secret-plaintext")
    raw = paths_secrets_read()
    assert "sk-secret-plaintext" not in raw


def paths_secrets_read() -> str:
    from llm_translator.storage import paths
    return paths.secrets_file().read_bytes().decode("utf-8", errors="ignore")
