from llm_translator.core.tts import (
    DEFAULT_VOICE,
    LANG_VOICE,
    EdgeTtsEngine,
    TtsEngine,
    TtsError,
    pick_voice,
)


def test_lang_voice_has_common_languages():
    assert LANG_VOICE["zh"].startswith("zh-CN")
    assert LANG_VOICE["en"].startswith("en-US")
    assert LANG_VOICE["ja"].startswith("ja-JP")


def test_pick_voice_known():
    assert pick_voice("zh") == LANG_VOICE["zh"]
    assert pick_voice("en") == LANG_VOICE["en"]


def test_pick_voice_unknown_and_auto_falls_back():
    assert pick_voice("xx") == DEFAULT_VOICE
    assert pick_voice("auto") == DEFAULT_VOICE  # src_lang=auto 兜底


def test_edge_engine_is_tts_engine():
    assert isinstance(EdgeTtsEngine(), TtsEngine)


def test_tts_error_is_exception():
    assert issubclass(TtsError, Exception)
