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


def test_selection_defaults(data_dir):
    s = Settings.load()
    assert s.selection_hotkey == "ctrl+shift+t"
    assert s.selection_enabled is True


def test_selection_persist(data_dir):
    s = Settings.load()
    s.selection_enabled = False
    s.selection_hotkey = "ctrl+alt+d"
    s.save()
    reloaded = Settings.load()
    assert reloaded.selection_enabled is False
    assert reloaded.selection_hotkey == "ctrl+alt+d"


def test_ocr_defaults(data_dir):
    s = Settings.load()
    assert s.ocr_hotkey == "ctrl+shift+o"
    assert s.ocr_enabled is True


def test_ocr_persist(data_dir):
    s = Settings.load()
    s.ocr_enabled = False
    s.ocr_hotkey = "ctrl+alt+o"
    s.save()
    reloaded = Settings.load()
    assert reloaded.ocr_enabled is False
    assert reloaded.ocr_hotkey == "ctrl+alt+o"


def test_doc_defaults(data_dir):
    s = Settings.load()
    assert s.doc_concurrency == 8
    assert s.doc_output_dir == ""


def test_doc_persist(data_dir):
    s = Settings.load()
    s.doc_concurrency = 4
    s.doc_output_dir = "/tmp/out"
    s.save()
    reloaded = Settings.load()
    assert reloaded.doc_concurrency == 4
    assert reloaded.doc_output_dir == "/tmp/out"
