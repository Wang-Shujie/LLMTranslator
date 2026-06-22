from llm_translator.storage.settings import Settings


def test_defaults(data_dir):
    s = Settings.load()
    assert s.src_lang == "auto"
    assert s.tgt_lang == "en"
    assert s.default_provider == "deepseek-api"
    assert s.font_size == 14
    assert s.enabled_providers == ["deepseek-api"]


def test_save_and_reload(data_dir):
    s = Settings.load()
    s.tgt_lang = "ja"
    s.enabled_providers = ["deepseek-api", "glm-web"]
    s.save()

    reloaded = Settings.load()
    assert reloaded.tgt_lang == "ja"
    assert reloaded.enabled_providers == ["deepseek-api", "glm-web"]
