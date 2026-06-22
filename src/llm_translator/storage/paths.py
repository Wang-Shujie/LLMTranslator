"""跨平台用户数据目录解析（platformdirs）。"""
from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

_APP_NAME = "LLMTranslator"
# 测试通过 monkeypatch 覆盖 _data_dir。
_data_dir: Path | None = None


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
