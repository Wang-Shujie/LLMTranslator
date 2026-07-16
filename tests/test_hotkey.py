"""GlobalHotkeyManager: 组合解析（RegisterHotKey 的 mod/vk）。"""
from llm_translator.core.hotkey import parse_combo

# Windows RegisterHotKey MOD_*
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008


def test_parse_basic():
    assert parse_combo("alt+shift+s") == (_MOD_ALT | _MOD_SHIFT, ord("S"))
    assert parse_combo("ctrl+d") == (_MOD_CONTROL, ord("D"))
    assert parse_combo("ctrl+shift+o") == (_MOD_CONTROL | _MOD_SHIFT, ord("O"))


def test_parse_win_key_and_function():
    assert parse_combo("win+shift+s") == (_MOD_WIN | _MOD_SHIFT, ord("S"))
    assert parse_combo("ctrl+f5") == (_MOD_CONTROL, 0x74)  # F5 = 0x70+5


def test_parse_digit_and_special():
    assert parse_combo("ctrl+1") == (_MOD_CONTROL, ord("1"))
    assert parse_combo("ctrl+space") == (_MOD_CONTROL, 0x20)


def test_parse_invalid():
    assert parse_combo("ctrl") is None      # 只有修饰键
    assert parse_combo("ctrl+,") is None    # 不支持的键名
    assert parse_combo("") is None
