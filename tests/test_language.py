from llm_translator.core.language import (
    code_to_name,
    name_to_code,
    LANGUAGES,
    looks_like_chinese,
    selection_target,
)


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


def test_looks_like_chinese():
    assert looks_like_chinese("你好世界") is True
    assert looks_like_chinese("Hello 世界") is True   # 含汉字即视为中文侧
    assert looks_like_chinese("Hello world") is False
    assert looks_like_chinese("") is False
    assert looks_like_chinese("123 !?") is False


def test_selection_target_default_zh():
    """默认语言中文：外文→中文，中文→不翻译(None)。"""
    # 英文/日文/韩文 → 译为中文
    assert selection_target("Hello world", "zh") == "zh"
    assert selection_target("こんにちは", "zh") == "zh"   # 日文(假名)
    assert selection_target("안녕하세요", "zh") == "zh"   # 韩文
    # 中文 → 已是默认语言，不翻译
    assert selection_target("你好世界", "zh") is None
    assert selection_target("Hello 世界", "zh") is None   # 含汉字 → 视为中文


def test_selection_target_default_en():
    """默认语言英语：非英文→英文，英文→不翻译。"""
    assert selection_target("你好世界", "en") == "en"
    assert selection_target("Hello world", "en") is None   # 英文→不翻译


def test_selection_target_empty():
    assert selection_target("", "zh") is None   # 无文字内容→视为默认语言，不翻译
