"""跨平台全局热键管理器。

Windows 用原生 ``RegisterHotKey``：把整组合交给 OS 匹配，发 ``WM_HOTKEY`` 给主窗口，
由主窗口 ``nativeEvent`` 按 id 分发。OS 整组合匹配优先级高于系统级前缀快捷键
（如 ``Alt+Shift`` 切输入法），故 ``alt+shift+s`` 这类组合也能稳定触发（与百度翻译同机制）。

其他平台回落 ``keyboard`` 库（低级钩子 + 事件流匹配）。

热键字符串沿用 keyboard 库格式（``"ctrl+shift+o"`` / ``"alt+shift+s"``）。
"""
from __future__ import annotations

import sys


_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL

WM_HOTKEY = 0x0312

# keyboard 库修饰名 → RegisterHotKey MOD_*
_MOD = {
    "alt": 0x0001,
    "ctrl": 0x0002,
    "control": 0x0002,
    "shift": 0x0004,
    "win": 0x0008,
    "windows": 0x0008,
}

# 特殊键名 → 虚拟键码
_VK_SPECIAL = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "home": 0x24, "end": 0x23, "page up": 0x21, "page down": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
}


def _key_to_vk(name: str) -> int | None:
    """单个键名（小写）→ Windows 虚拟键码；不识别返回 None。"""
    if len(name) == 1 and name.isalpha():
        return ord(name.upper())  # A–Z = 0x41–0x5A
    if len(name) == 1 and name.isdigit():
        return ord(name)  # 0–9 = 0x30–0x39
    if name.startswith("f") and name[1:].isdigit():
        n = int(name[1:])
        if 1 <= n <= 24:
            return 0x6F + n  # F1=0x70 … F24=0x87
    return _VK_SPECIAL.get(name)


def parse_combo(combo: str) -> tuple[int, int] | None:
    """'alt+shift+s' → (mod_flags, vk)；无效返回 None。修饰键合并，最后一个非修饰为键。"""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    mod, key = 0, None
    for p in parts:
        if p in _MOD:
            mod |= _MOD[p]
        else:
            key = p
    if key is None:
        return None
    vk = _key_to_vk(key)
    if vk is None:
        return None
    return mod, vk


class GlobalHotkeyManager:
    """注册/注销全局热键；Windows 经主窗口 nativeEvent 分发 WM_HOTKEY。"""

    def __init__(self) -> None:
        self._hwnd = 0
        self._next_id = 1
        self._win_active: dict[int, object] = {}     # id → callback
        self._win_pending: list[tuple[int, tuple[int, int], object]] = []  # 待 hwnd 就绪后注册

    # ---- 主窗口接入 ----
    def set_hwnd(self, hwnd: int) -> None:
        """主窗口首次显示后传入其 HWND，触发待注册热键的实际注册（仅 Windows）。"""
        if not _IS_WIN or self._hwnd or not hwnd:
            return  # 非 Windows / 已设置 / 无效
        self._hwnd = hwnd
        for hid, parsed, cb in self._win_pending:
            self._register_win(hid, parsed, cb)
        self._win_pending.clear()

    # ---- 注册/注销 ----
    def register(self, combo: str, callback) -> object:
        """注册热键；返回不透明 handle（Windows=int id / 其他=('kb', handle)），失败 None。"""
        if _IS_WIN:
            parsed = parse_combo(combo)
            if parsed is None:
                return None
            hid = self._next_id
            self._next_id += 1
            if self._hwnd:
                if self._register_win(hid, parsed, callback):
                    return hid
                return None
            self._win_pending.append((hid, parsed, callback))  # hwnd 未就绪，排队
            return hid
        import keyboard
        try:
            h = keyboard.add_hotkey(combo, callback, suppress=True)
            return ("kb", h)
        except Exception as e:
            return None

    def unregister(self, handle) -> None:
        if handle is None:
            return
        if _IS_WIN:
            if isinstance(handle, int):
                if self._hwnd:
                    _user32.UnregisterHotKey(self._hwnd, handle)
                self._win_active.pop(handle, None)
                self._win_pending = [p for p in self._win_pending if p[0] != handle]
        elif isinstance(handle, tuple) and handle[0] == "kb":
            import keyboard
            try:
                keyboard.remove_hotkey(handle[1])
            except Exception:
                pass

    def _register_win(self, hid: int, parsed: tuple[int, int], callback) -> bool:
        mod, vk = parsed
        ok = bool(_user32.RegisterHotKey(self._hwnd, hid, mod, vk))
        if ok:
            self._win_active[hid] = callback
        return ok

    # ---- 主窗口 nativeEvent 调用 ----
    def dispatch_wm_hotkey(self, wparam: int) -> None:
        """WM_HOTKEY 的 wParam 即热键 id → 查表回调。"""
        cb = self._win_active.get(wparam)
        if cb is not None:
            cb()
