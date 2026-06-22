from llm_translator.core.language import code_to_name, name_to_code, LANGUAGES


def test_known_languages():
    assert code_to_name("en") == "英语"
    assert code_to_name("zh") == "中文(简体)"
    assert code_to_name("auto") == "自动检测"


def test_reverse_lookup():
    assert name_to_code("英语") == "en"
    assert name_to_code("日语") == "ja"


def test_unknown_fallback():
    assert code_to_name("xx") == "xx"
    assert name_to_code("不存在的语言") is None


def test_auto_is_present():
    assert "auto" in LANGUAGES
