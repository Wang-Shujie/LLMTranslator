from llm_translator.core.prompt import build_messages


def test_messages_structure():
    msgs = build_messages("你好", src="zh", tgt="en")
    assert isinstance(msgs, list)
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert "你好" in msgs[-1]["content"]


def test_system_prompt_constrains_output():
    msgs = build_messages("x", src="zh", tgt="en")
    sys_text = msgs[0]["content"]
    assert "ONLY" in sys_text or "只" in sys_text
    assert "en" in sys_text.lower() or "English" in sys_text or "英语" in sys_text


def test_user_content_carries_text():
    msgs = build_messages("世界", src="zh", tgt="ja")
    assert "世界" in msgs[-1]["content"]


def test_auto_source_uses_phrasing():
    msgs = build_messages("hello", src="auto", tgt="zh")
    assert isinstance(msgs, list) and len(msgs) >= 2
