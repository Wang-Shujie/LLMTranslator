import pytest
from unittest.mock import MagicMock
from llm_translator.auth.store import CredentialStore
from llm_translator.core.translator import Translator
from llm_translator.storage.history import HistoryStore


class _FakeProvider:
    kind = "api"
    name = "Fake"
    def __init__(self):
        self.logged_in = False
    async def login(self):
        self.logged_in = True
    async def translate(self, text, src, tgt, context=""):
        for tok in ["Hel", "lo"]:
            yield tok
    def health(self):
        return True


@pytest.mark.asyncio
async def test_translate_streams_tokens_and_writes_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="deepseek-api")

    tokens = []
    async for tok in t.translate("你好", "zh", "en"):
        tokens.append(tok)

    assert "".join(tokens) == "Hello"
    assert provider.logged_in is True
    rows = history.list(limit=10)
    assert len(rows) == 1
    assert rows[0].target_text == "Hello"


@pytest.mark.asyncio
async def test_sets_current_provider(data_dir):
    t = Translator(provider=_FakeProvider(), history=HistoryStore(), provider_label="p")
    new_p = _FakeProvider()
    t.set_provider(new_p, "new")
    assert t.provider_label == "new"


@pytest.mark.asyncio
async def test_save_history_true_by_default_writes_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="p")
    async for _ in t.translate("你好", "zh", "en"):
        pass
    assert len(history.list(limit=10)) == 1


@pytest.mark.asyncio
async def test_save_history_false_skips_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="p")
    async for _ in t.translate("你好", "zh", "en", save_history=False):
        pass
    assert len(history.list(limit=10)) == 0
