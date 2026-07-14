"""跨平台用户数据目录解析（platformdirs）。"""
from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_data_dir

_APP_NAME = "LLMTranslator"
# 测试通过 monkeypatch 覆盖 _data_dir。
_data_dir: Path | None = None


def resource_root() -> Path:
    """打包内资源根：PyInstaller 打包后为 _MEIPASS；开发时为 src/。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # storage/paths.py → 上三级 = src/
    return Path(__file__).resolve().parent.parent.parent


def icon_file() -> Path:
    """应用图标路径（icon/icon.ico）。

    开发：src/icon/icon.ico；打包：_MEIPASS/icon/icon.ico（build.spec 把 src/icon 收进 icon/）。
    """
    ico = resource_root() / "icon" / "icon.ico"
    return ico


def data_dir() -> Path:
    global _data_dir
    if _data_dir is not None:
        return _data_dir
    _data_dir = Path(user_data_dir(_APP_NAME, appauthor=False))
    ensure_dir(_data_dir)
    return _data_dir


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def settings_file() -> Path:
    return data_dir() / "settings.json"


def history_file() -> Path:
    return data_dir() / "history.db"


def secrets_file() -> Path:
    return data_dir() / "secrets.enc"
