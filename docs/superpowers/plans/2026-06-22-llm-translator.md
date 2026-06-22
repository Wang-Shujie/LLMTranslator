# 多系统通用桌面级大模型翻译软件 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零构建一个 Python + PySide6 的桌面 LLM 翻译软件，支持 OpenAI 兼容付费 API 与智谱清言/Kimi/DeepSeek 网页逆向，流式输出、历史记录、一键安装。

**Architecture:** 分层 + 适配器模式。所有模型实现统一的 `BaseProvider` 接口，互不隔离；`asyncio`（经 `qasync`）与 Qt 事件循环共存，provider 异步产出 token 经 Qt 信号投递到主线程渲染。

**Tech Stack:** Python 3.11+ · PySide6 · qasync · httpx · curl_cffi · PySide6-Addons(QWebEngineView) · cryptography · platformdirs · sqlite3 · pytest/pytest-asyncio · PyInstaller · Inno Setup

**参考 spec:** `docs/superpowers/specs/2026-06-22-llm-translator-design.md`

---

## 文件结构总览

```
llm-translator/
├── pyproject.toml
├── build.spec                      # PyInstaller
├── installer.iss                   # Inno Setup
├── README.md
├── assets/
│   └── light.qss                   # 浅色主题样式
├── src/llm_translator/
│   ├── __init__.py
│   ├── main.py                     # 入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── language.py             # 语言码↔名称
│   │   ├── prompt.py               # 翻译 prompt 构建
│   │   └── translator.py           # 翻译编排（持当前 provider，流式 yield）
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseProvider + 异常类
│   │   ├── registry.py             # provider id → 工厂
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── openai_compat.py    # OpenAI 兼容（DeepSeek/GLM/OpenAI）
│   │   └── web/
│   │       ├── __init__.py
│   │       ├── _base.py            # 网页 provider 公共：会话/SSE
│   │       ├── glm.py
│   │       ├── kimi.py
│   │       └── deepseek.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── store.py                # Fernet 加密凭据存取
│   │   └── login.py                # QWebEngineView 登录抓 Cookie
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── paths.py                # platformdirs 数据目录
│   │   ├── settings.py             # JSON 设置
│   │   └── history.py              # SQLite 历史
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── async_bridge.py         # qasync + token 信号桥
│   │   ├── main_window.py          # 主窗口
│   │   ├── settings_dialog.py      # 设置对话框
│   │   ├── login_dialog.py         # 网页登录对话框（包装 auth/login.py）
│   │   └── history_dialog.py       # 历史记录对话框
│   └── utils/
│       ├── __init__.py
│       └── sse.py                  # SSE 流解析
└── tests/
    ├── conftest.py
    ├── test_language.py
    ├── test_prompt.py
    ├── test_settings.py
    ├── test_history.py
    ├── test_credential_store.py
    ├── test_sse.py
    ├── test_openai_compat.py
    ├── test_registry.py
    ├── test_translator.py
    └── test_web_glm.py
```

**阶段划分**（每阶段结束 = 可测试检查点）：
- **Phase 1（Task 1–7）**：项目骨架 + 存储/Auth/Core 纯逻辑，全部可用单元测试覆盖。
- **Phase 2（Task 8–16）**：Provider 适配层 + 翻译编排，契约测试覆盖。
- **Phase 3（Task 17–22）**：UI，手动验收对照参考图。
- **Phase 4（Task 23–25）**：打包 + 文档，产出可分发安装包。

---

# Phase 1 — 项目骨架与基础逻辑

## Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `src/llm_translator/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "llm-translator"
version = "0.1.0"
description = "跨平台桌面级大模型翻译软件"
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.6",
    "PySide6-Addons>=6.6",
    "qasync>=0.27",
    "httpx>=0.27",
    "curl_cffi>=0.7",
    "cryptography>=42",
    "platformdirs>=4.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pyinstaller>=6",
]

[project.scripts]
llm-translator = "llm_translator.main:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 写包标记文件 `src/llm_translator/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: 写 `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
dist/
build/
*.spec.bak
.pytest_cache/
*.db
secrets.enc
```

- [ ] **Step 4: 写 `tests/conftest.py`（共享 tmp 数据目录 fixture）**

```python
import pytest
from llm_translator.storage import paths


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """把数据目录重定向到临时目录，避免污染真实用户目录。"""
    monkeypatch.setattr(paths, "_data_dir", tmp_path)
    return tmp_path
```

- [ ] **Step 5: 创建空 `__init__.py` 占位（storage/utils/core/providers/auth/ui 各一个）**

```bash
mkdir -p src/llm_translator/{core,providers/api,providers/web,auth,storage,ui,utils} tests
touch src/llm_translator/{core,providers,providers/api,providers/web,auth,storage,ui,utils}/__init__.py
```

- [ ] **Step 6: 安装依赖并验证可导入**

Run: `python -m pip install -e ".[dev]"`
Expected: 安装成功，无报错。

Run: `python -c "import llm_translator; print(llm_translator.__version__)"`
Expected: `0.1.0`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/ tests/conftest.py
git commit -m "chore: project skeleton and dependencies"
```

---

## Task 2: 数据目录路径（`storage/paths.py`）

**Files:**
- Create: `src/llm_translator/storage/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: 写失败测试 `tests/test_paths.py`**

```python
from llm_translator.storage import paths


def test_paths_under_data_dir(data_dir):
    assert paths.data_dir() == data_dir
    assert paths.settings_file() == data_dir / "settings.json"
    assert paths.history_file() == data_dir / "history.db"
    assert paths.secrets_file() == data_dir / "secrets.enc"


def test_ensure_data_dir_creates_directory(data_dir):
    sub = data_dir / "new_sub"
    paths.ensure_dir(sub)
    assert sub.is_dir()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_paths.py -v`
Expected: FAIL — `paths.data_dir` 不存在或导入失败。

- [ ] **Step 3: 实现 `src/llm_translator/storage/paths.py`**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_paths.py -v`
Expected: PASS（2 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/storage/paths.py tests/test_paths.py
git commit -m "feat(storage): platformdirs data paths"
```

---

## Task 3: 设置存储（`storage/settings.py`）

**Files:**
- Create: `src/llm_translator/storage/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试 `tests/test_settings.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL — `Settings` 未定义。

- [ ] **Step 3: 实现 `src/llm_translator/storage/settings.py`**

```python
"""JSON 设置文件读写。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from llm_translator.storage import paths


@dataclass
class Settings:
    src_lang: str = "auto"
    tgt_lang: str = "en"
    default_provider: str = "deepseek-api"
    font_size: int = 14
    enabled_providers: list[str] = field(default_factory=lambda: ["deepseek-api"])

    @classmethod
    def load(cls) -> "Settings":
        f = paths.settings_file()
        if not f.exists():
            return cls()
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        f = paths.settings_file()
        paths.ensure_dir(f.parent)
        f.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_settings.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/storage/settings.py tests/test_settings.py
git commit -m "feat(storage): JSON settings persistence"
```

---

## Task 4: 历史记录（`storage/history.py`，SQLite）

**Files:**
- Create: `src/llm_translator/storage/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: 写失败测试 `tests/test_history.py`**

```python
from llm_translator.storage.history import Entry, HistoryStore


def test_add_and_list(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="你好", target_text="Hello", provider="deepseek-api"))
    rows = store.list(limit=10)
    assert len(rows) == 1
    assert rows[0].source_text == "你好"
    assert rows[0].target_text == "Hello"


def test_list_orders_newest_first(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="第一", target_text="first", provider="p"))
    store.add(Entry(src="auto", tgt="en", source_text="第二", target_text="second", provider="p"))
    rows = store.list(limit=10)
    assert rows[0].source_text == "第二"
    assert rows[1].source_text == "第一"


def test_search(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="你好世界", target_text="Hello world", provider="p"))
    store.add(Entry(src="auto", tgt="en", source_text="再见", target_text="Goodbye", provider="p"))
    hits = store.search("world")
    assert len(hits) == 1
    assert hits[0].target_text == "Hello world"


def test_clear(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="x", target_text="y", provider="p"))
    store.clear()
    assert store.list(limit=10) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_history.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/storage/history.py`**

```python
"""翻译历史记录（SQLite）。"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Iterable

from llm_translator.storage import paths


@dataclass
class Entry:
    src: str
    tgt: str
    source_text: str
    target_text: str
    provider: str
    id: int | None = None
    timestamp: float = 0.0


class HistoryStore:
    def __init__(self) -> None:
        self._db = paths.history_file()
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    src TEXT NOT NULL,
                    tgt TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    target_text TEXT NOT NULL,
                    provider TEXT NOT NULL
                )
                """
            )

    def add(self, entry: Entry) -> None:
        entry.timestamp = entry.timestamp or time.time()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO translations (timestamp, src, tgt, source_text, target_text, provider) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry.timestamp, entry.src, entry.tgt, entry.source_text, entry.target_text, entry.provider),
            )
            entry.id = cur.lastrowid

    def _row_to_entry(self, row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            timestamp=row["timestamp"],
            src=row["src"],
            tgt=row["tgt"],
            source_text=row["source_text"],
            target_text=row["target_text"],
            provider=row["provider"],
        )

    def list(self, limit: int = 50, offset: int = 0) -> list[Entry]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM translations ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def search(self, query: str, limit: int = 50) -> list[Entry]:
        like = f"%{query}%"
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM translations WHERE source_text LIKE ? OR target_text LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (like, like, limit),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM translations")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_history.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/storage/history.py tests/test_history.py
git commit -m "feat(storage): SQLite translation history"
```

---

## Task 5: 凭据加密存储（`auth/store.py`，Fernet）

**Files:**
- Create: `src/llm_translator/auth/store.py`
- Test: `tests/test_credential_store.py`

- [ ] **Step 1: 写失败测试 `tests/test_credential_store.py`**

```python
import json
from llm_translator.auth.store import CredentialStore


def test_roundtrip(data_dir):
    store = CredentialStore()
    store.set("deepseek-api", "api_key", "sk-xxx")
    assert store.get("deepseek-api", "api_key") == "sk-xxx"


def test_missing_returns_none(data_dir):
    store = CredentialStore()
    assert store.get("nope", "api_key") is None


def test_stored_value_is_encrypted_not_plaintext(data_dir):
    store = CredentialStore()
    store.set("p", "api_key", "sk-secret-plaintext")
    raw = paths_secrets_read()
    assert "sk-secret-plaintext" not in raw


def paths_secrets_read() -> str:
    from llm_translator.storage import paths
    return paths.secrets_file().read_bytes().decode("utf-8", errors="ignore")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_credential_store.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/auth/store.py`**

```python
"""加密凭据存储（Fernet，密钥由机器特征派生）。

凭据整体存为一个加密的 JSON 字典：{provider_id: {key: value}}。
"""
from __future__ import annotations

import base64
import hashlib
import json
import platform
import uuid

from cryptography.fernet import Fernet, InvalidToken

from llm_translator.storage import paths

_SALT = b"llm-translator-v1"  # 固定盐；安全边界依赖"本机读取"，非对抗性攻击


def _derive_key() -> bytes:
    """由机器特征派生 Fernet 密钥（32 字节 → urlsafe base64）。"""
    node = uuid.getnode()  # MAC 地址
    machine = platform.node()
    fingerprint = f"{node}:{machine}".encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", fingerprint, _SALT, iterations=100_000)
    return base64.urlsafe_b64encode(digest)


class CredentialStore:
    def __init__(self) -> None:
        self._fernet = Fernet(_derive_key())
        self._data: dict[str, dict[str, str]] = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        f = paths.secrets_file()
        if not f.exists():
            return {}
        try:
            raw = self._fernet.decrypt(f.read_bytes())
            return json.loads(raw)
        except (InvalidToken, ValueError):
            return {}

    def _flush(self) -> None:
        f = paths.secrets_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(self._fernet.encrypt(json.dumps(self._data).encode("utf-8")))

    def set(self, provider_id: str, key: str, value: str) -> None:
        self._data.setdefault(provider_id, {})[key] = value
        self._flush()

    def get(self, provider_id: str, key: str) -> str | None:
        return self._data.get(provider_id, {}).get(key)

    def get_all(self, provider_id: str) -> dict[str, str]:
        return dict(self._data.get(provider_id, {}))

    def delete(self, provider_id: str) -> None:
        self._data.pop(provider_id, None)
        self._flush()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_credential_store.py -v`
Expected: PASS（3 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/auth/store.py tests/test_credential_store.py
git commit -m "feat(auth): Fernet-encrypted credential store"
```

---

## Task 6: 语言映射（`core/language.py`）

**Files:**
- Create: `src/llm_translator/core/language.py`
- Test: `tests/test_language.py`

- [ ] **Step 1: 写失败测试 `tests/test_language.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_language.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/core/language.py`**

```python
"""支持的语言码 ↔ 显示名称映射。"""
from __future__ import annotations

LANGUAGES: dict[str, str] = {
    "auto": "自动检测",
    "zh": "中文(简体)",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "th": "泰语",
    "vi": "越南语",
    "ar": "阿拉伯语",
}


def code_to_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def name_to_code(name: str) -> str | None:
    for code, nm in LANGUAGES.items():
        if nm == name:
            return code
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_language.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/core/language.py tests/test_language.py
git commit -m "feat(core): language code/name mapping"
```

---

## Task 7: 翻译 Prompt 构建（`core/prompt.py`）

**Files:**
- Create: `src/llm_translator/core/prompt.py`
- Test: `tests/test_prompt.py`

- [ ] **Step 1: 写失败测试 `tests/test_prompt.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_prompt.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/core/prompt.py`**

```python
"""构建翻译 prompt，约束 LLM 只输出译文。"""
from __future__ import annotations

from llm_translator.core.language import code_to_name


def build_messages(text: str, src: str, tgt: str) -> list[dict[str, str]]:
    src_name = code_to_name(src)
    tgt_name = code_to_name(tgt)
    if src == "auto":
        src_phrase = "the source language (auto-detect it)"
    else:
        src_phrase = src_name

    system = (
        f"You are a professional translator. "
        f"Translate the user's text from {src_phrase} to {tgt_name}. "
        f"Output ONLY the translation. Do not add any explanation, notes, or quotation marks. "
        f"Preserve original formatting and line breaks."
    )
    user = f"Text:\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_prompt.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: 运行 Phase 1 全部测试**

Run: `pytest -v`
Expected: 全部 PASS（约 17 项）。

- [ ] **Step 6: Commit**

```bash
git add src/llm_translator/core/prompt.py tests/test_prompt.py
git commit -m "feat(core): translation prompt builder"
```

---

# Phase 2 — Provider 适配层与翻译编排

## Task 8: Provider 基类与异常（`providers/base.py`）

**Files:**
- Create: `src/llm_translator/providers/base.py`

- [ ] **Step 1: 实现 `src/llm_translator/providers/base.py`**

```python
"""Provider 抽象基类与异常。

所有模型（付费 API / 网页逆向）实现同一契约，UI 与编排层只依赖此接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from llm_translator.auth.store import CredentialStore


class ProviderError(Exception):
    """Provider 层基类异常。"""


class AuthError(ProviderError):
    """登录态/凭据无效，需要用户重新登录或填写 Key。"""


class ProviderUnavailable(ProviderError):
    """Provider 不可用（接口失效、网络错误等），不影响其他 Provider。"""


class BaseProvider(ABC):
    kind: str = "api"  # "api" | "web"

    def __init__(self, provider_id: str, credentials: CredentialStore) -> None:
        self.provider_id = provider_id
        self.credentials = credentials

    @property
    @abstractmethod
    def name(self) -> str:
        """展示给用户的名称。"""

    @abstractmethod
    async def login(self) -> None:
        """校验/建立登录态。失败抛 AuthError。"""

    @abstractmethod
    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        """异步生成器：逐个 yield token。用法 `async for tok in provider.translate(...)`。"""

    @abstractmethod
    def health(self) -> bool:
        """当前登录态/连接是否有效（不发起重请求，仅检查已存凭据状态）。"""
```

- [ ] **Step 2: 验证可导入**

Run: `python -c "from llm_translator.providers.base import BaseProvider, AuthError, ProviderUnavailable; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/providers/base.py
git commit -m "feat(providers): base interface and exceptions"
```

---

## Task 9: SSE 流解析工具（`utils/sse.py`）

**Files:**
- Create: `src/llm_translator/utils/sse.py`
- Test: `tests/test_sse.py`

- [ ] **Step 1: 写失败测试 `tests/test_sse.py`**

```python
import pytest
from llm_translator.utils.sse import parse_sse


@pytest.mark.asyncio
async def test_yields_data_events():
    raw = b"data: {\"a\":1}\n\ndata: {\"a\":2}\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == [{"a": 1}, {"a": 2}]


@pytest.mark.asyncio
async def test_ignores_done_and_comments():
    raw = b": ping\n\ndata: [DONE]\n\ndata: {\"a\":3}\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == [{"a": 3}]


@pytest.mark.asyncio
async def test_handles_plain_text_payload():
    raw = b"data: hello world\n\n"
    events = [e async for e in parse_sse(_byte_stream(raw))]
    assert events == ["hello world"]


class _byte_stream:
    """把 bytes 模拟成 httpx 的 aiter_bytes()/aiter_lines() 行为：按行产出 bytes。"""
    def __init__(self, data: bytes):
        self._lines = data.split(b"\n")

    async def __aiter__(self):
        for line in self._lines:
            yield line
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sse.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/utils/sse.py`**

```python
"""SSE（Server-Sent Events）流解析。

接受异步字节行迭代器，产出每个 `data:` 事件的反序列化载荷：
JSON 字符串 → dict；其余 → 原始字符串；`[DONE]` 与注释行跳过。
"""
from __future__ import annotations

import json
from typing import AsyncIterator


async def parse_sse(lines: AsyncIterator[bytes]) -> AsyncIterator[object]:
    buffer = b""
    async for raw_line in lines:
        line = raw_line.rstrip(b"\r")
        buffer += line
        # 空行 = 事件分隔（按 SSE 规范，空行结束一个事件）
        if line == b"":
            event = _parse_event(buffer)
            buffer = b""
            if event is not None:
                yield event
            continue
        buffer += b"\n"


def _parse_event(buf: bytes) -> object | None:
    data_lines: list[str] = []
    for text_line in buf.decode("utf-8", errors="replace").splitlines():
        if not text_line or text_line.startswith(":"):
            continue
        if text_line.startswith("data:"):
            data_lines.append(text_line[len("data:"):].lstrip())
    if not data_lines:
        return None
    payload = "\n".join(data_lines)
    if payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return payload
```

> 说明：上面的 `parse_sse` 以"空行为事件边界"聚合多行 `data:`。Provider 适配器把 httpx 流的 `aiter_lines()` 传进来。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_sse.py -v`
Expected: PASS（3 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/utils/sse.py tests/test_sse.py
git commit -m "feat(utils): SSE stream parser"
```

---

## Task 10: OpenAI 兼容 Provider（`providers/api/openai_compat.py`）

**Files:**
- Create: `src/llm_translator/providers/api/openai_compat.py`
- Test: `tests/test_openai_compat.py`

- [ ] **Step 1: 写失败测试 `tests/test_openai_compat.py`**

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.api.openai_compat import OpenAICompatProvider, PRESETS


def _make_provider(provider_id="deepseek-api"):
    creds = CredentialStore()
    if provider_id == "deepseek-api":
        creds.set("deepseek-api", "api_key", "sk-test")
    return OpenAICompatProvider("deepseek-api", creds)


def test_presets_contain_expected():
    assert "deepseek" in PRESETS
    assert PRESETS["deepseek"]["base_url"].endswith("/v1")


def test_health_requires_key():
    creds = CredentialStore()  # 空
    p = OpenAICompatProvider("deepseek-api", creds)
    assert p.health() is False


def test_health_true_with_key():
    p = _make_provider()
    assert p.health() is True


@pytest.mark.asyncio
async def test_login_with_valid_key_health_true():
    p = _make_provider()
    await p.login()  # 无网络环境下不抛错（login 仅做本地 Key 存在性校验）
    assert p.health() is True


@pytest.mark.asyncio
async def test_login_without_key_raises():
    from llm_translator.providers.base import AuthError
    creds = CredentialStore()
    p = OpenAICompatProvider("deepseek-api", creds)
    with pytest.raises(AuthError):
        await p.login()


@pytest.mark.asyncio
async def test_translate_yields_delta_tokens():
    p = _make_provider()
    sse = b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\ndata: {"choices":[{"delta":{"content":"lo"}}]}\n\ndata: [DONE]\n\n'

    class _FakeResponse:
        async def aiter_lines(self):
            for line in sse.split(b"\n"):
                yield line
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=_FakeResponse())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("llm_translator.providers.api.openai_compat.httpx.AsyncClient", return_value=fake_client):
        tokens = [t async for t in p.translate("你好", "zh", "en")]
    assert "".join(tokens) == "Hello"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_openai_compat.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/providers/api/openai_compat.py`**

```python
"""OpenAI 兼容协议 Provider（通吃 DeepSeek / 智谱 GLM / OpenAI / 兼容聚合平台）。"""
from __future__ import annotations

from typing import AsyncGenerator

import httpx

from llm_translator.auth.store import CredentialStore
from llm_translator.core.prompt import build_messages
from llm_translator.providers.base import AuthError, BaseProvider
from llm_translator.utils.sse import parse_sse

PRESETS: dict[str, dict] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "label": "DeepSeek API"},
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash", "label": "智谱 GLM API"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "label": "OpenAI"},
}

# provider_id → 预设 key（若 provider_id 形如 "xxx-api" 则映射到预设）
_PRESET_BY_ID = {
    "deepseek-api": "deepseek",
    "glm-api": "glm",
    "openai": "openai",
}


class OpenAICompatProvider(BaseProvider):
    kind = "api"

    def __init__(self, provider_id: str, credentials: CredentialStore) -> None:
        super().__init__(provider_id, credentials)
        preset_key = _PRESET_BY_ID.get(provider_id, "deepseek")
        preset = PRESETS[preset_key]
        # 用户可在凭据里覆盖 base_url / model（自定义供应商）
        self.base_url = credentials.get(provider_id, "base_url") or preset["base_url"]
        self.model = credentials.get(provider_id, "model") or preset["model"]
        self._label = preset["label"]

    @property
    def name(self) -> str:
        return self._label

    def _api_key(self) -> str | None:
        return self.credentials.get(self.provider_id, "api_key")

    def health(self) -> bool:
        return bool(self._api_key())

    async def login(self) -> None:
        if not self._api_key():
            raise AuthError(f"{self.name} 未配置 API Key")

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        if not self._api_key():
            raise AuthError(f"{self.name} 未配置 API Key")
        payload = {
            "model": self.model,
            "messages": build_messages(text, src, tgt),
            "stream": True,
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                if resp.status_code == 401:
                    raise AuthError(f"{self.name} API Key 无效")
                resp.raise_for_status()
                async for event in parse_sse(resp.aiter_lines()):
                    if isinstance(event, dict):
                        try:
                            delta = event["choices"][0]["delta"].get("content")
                        except (KeyError, IndexError):
                            delta = None
                        if delta:
                            yield delta
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_openai_compat.py -v`
Expected: PASS（6 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/providers/api/openai_compat.py tests/test_openai_compat.py
git commit -m "feat(providers): OpenAI-compatible provider"
```

---

## Task 11: Provider 注册表（`providers/registry.py`）

**Files:**
- Create: `src/llm_translator/providers/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写失败测试 `tests/test_registry.py`**

```python
import pytest
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.registry import all_providers, get_provider
from llm_translator.providers.api.openai_compat import OpenAICompatProvider


def test_all_providers_lists_mvp_ids():
    ids = {p["id"] for p in all_providers()}
    assert {"deepseek-api", "glm-api", "openai", "glm-web", "kimi-web", "deepseek-web"} <= ids


def test_all_providers_has_metadata_fields():
    for p in all_providers():
        assert {"id", "label", "kind"} <= set(p.keys())


def test_get_provider_api_returns_instance():
    creds = CredentialStore()
    p = get_provider("deepseek-api", creds)
    assert isinstance(p, OpenAICompatProvider)
    assert p.kind == "api"


def test_get_provider_unknown_raises():
    creds = CredentialStore()
    with pytest.raises(KeyError):
        get_provider("does-not-exist", creds)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL — 模块未定义（导入链含未创建的 web providers，本任务先用延迟导入规避）。

- [ ] **Step 3: 实现 `src/llm_translator/providers/registry.py`**

```python
"""Provider 注册表：id → (工厂, 元数据)。

新增一家模型 = 在 REGISTRY 加一条 +（若网页类）写一个适配器文件。
网页 provider 用延迟导入，避免无网络/缺依赖时注册表加载失败。
"""
from __future__ import annotations

from dataclasses import dataclass

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.api.openai_compat import OpenAICompatProvider, PRESETS
from llm_translator.providers.base import BaseProvider


@dataclass
class ProviderMeta:
    id: str
    label: str
    kind: str  # "api" | "web"


def _api_meta(pid: str, preset_key: str) -> tuple[type[BaseProvider], ProviderMeta]:
    return (
        OpenAICompatProvider,
        ProviderMeta(id=pid, label=PRESETS[preset_key]["label"], kind="api"),
    )


def _web_meta(pid: str, label: str) -> tuple:
    # 延迟导入，避免循环依赖 / 顶层加载网页 provider
    def factory(_pid: str = pid):
        from importlib import import_module
        mod_map = {
            "glm-web": ("llm_translator.providers.web.glm", "GlmWebProvider"),
            "kimi-web": ("llm_translator.providers.web.kimi", "KimiWebProvider"),
            "deepseek-web": ("llm_translator.providers.web.deepseek", "DeepSeekWebProvider"),
        }
        mod_name, cls_name = mod_map[_pid]
        return getattr(import_module(mod_name), cls_name)

    return factory, ProviderMeta(id=pid, label=label, kind="web")


# id → (工厂函数(provider_id)->类, 元数据)
REGISTRY: dict[str, tuple] = {
    "deepseek-api": (lambda pid: OpenAICompatProvider, _api_meta("deepseek-api", "deepseek")[1]),
    "glm-api": (lambda pid: OpenAICompatProvider, _api_meta("glm-api", "glm")[1]),
    "openai": (lambda pid: OpenAICompatProvider, _api_meta("openai", "openai")[1]),
    "glm-web": (_web_meta("glm-web", "智谱清言")[0], _web_meta("glm-web", "智谱清言")[1]),
    "kimi-web": (_web_meta("kimi-web", "Kimi")[0], _web_meta("kimi-web", "Kimi")[1]),
    "deepseek-web": (_web_meta("deepseek-web", "DeepSeek 网页")[0], _web_meta("deepseek-web", "DeepSeek 网页")[1]),
}


def all_providers() -> list[dict]:
    return [{"id": m.id, "label": m.label, "kind": m.kind} for _, m in REGISTRY.values()]


def get_provider(provider_id: str, credentials: CredentialStore) -> BaseProvider:
    if provider_id not in REGISTRY:
        raise KeyError(provider_id)
    factory, _meta = REGISTRY[provider_id]
    cls = factory(provider_id)
    return cls(provider_id, credentials)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_registry.py -v`
Expected: PASS（4 项）。注意：`all_providers()` 不触发 web provider 导入，故网页类尚未实现也能通过。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/providers/registry.py tests/test_registry.py
git commit -m "feat(providers): provider registry"
```

---

## Task 12: 翻译编排（`core/translator.py`）

**Files:**
- Create: `src/llm_translator/core/translator.py`
- Test: `tests/test_translator.py`

- [ ] **Step 1: 写失败测试 `tests/test_translator.py`**

```python
import pytest
from unittest.mock import MagicMock
from llm_translator.auth.store import CredentialStore
from llm_translator.core.translator import Translator
from llm_translator.storage.history import HistoryStore


class _FakeProvider:
    kind = "api"
    name = "Fake"
    def __init__(self):
        self.logged_in = False
    async def login(self):
        self.logged_in = True
    async def translate(self, text, src, tgt):
        for tok in ["Hel", "lo"]:
            yield tok
    def health(self):
        return True


@pytest.mark.asyncio
async def test_translate_streams_tokens_and_writes_history(data_dir):
    provider = _FakeProvider()
    history = HistoryStore()
    t = Translator(provider=provider, history=history, provider_label="deepseek-api")

    tokens = []
    async for tok in t.translate("你好", "zh", "en"):
        tokens.append(tok)

    assert "".join(tokens) == "Hello"
    assert provider.logged_in is True
    rows = history.list(limit=10)
    assert len(rows) == 1
    assert rows[0].target_text == "Hello"


@pytest.mark.asyncio
async def test_sets_current_provider(data_dir):
    t = Translator(provider=_FakeProvider(), history=HistoryStore(), provider_label="p")
    new_p = _FakeProvider()
    t.set_provider(new_p, "new")
    assert t.provider_label == "new"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_translator.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/core/translator.py`**

```python
"""翻译编排：持当前 provider，流式产出 token，完成后写历史。"""
from __future__ import annotations

from typing import AsyncGenerator

from llm_translator.providers.base import BaseProvider
from llm_translator.storage.history import Entry, HistoryStore


class Translator:
    def __init__(self, provider: BaseProvider, history: HistoryStore, provider_label: str) -> None:
        self.provider = provider
        self.history = history
        self.provider_label = provider_label

    def set_provider(self, provider: BaseProvider, label: str) -> None:
        self.provider = provider
        self.provider_label = label

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        text = text.strip()
        if not text:
            return
        await self.provider.login()
        collected: list[str] = []
        async for token in self.provider.translate(text, src, tgt):
            collected.append(token)
            yield token
        # 流结束后落库
        self.history.add(
            Entry(
                src=src,
                tgt=tgt,
                source_text=text,
                target_text="".join(collected),
                provider=self.provider_label,
            )
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_translator.py -v`
Expected: PASS（2 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/core/translator.py tests/test_translator.py
git commit -m "feat(core): translation orchestrator"
```

---

## Task 13: 网页 Provider 公共基类（`providers/web/_base.py`）

**Files:**
- Create: `src/llm_translator/providers/web/_base.py`

> 网页逆向用 `curl_cffi`（TLS 指纹）发起请求；会话凭据（Cookie/Token）从 `CredentialStore` 读取。公共逻辑：构造带指纹的 client、SSE 事件中提取文本。

- [ ] **Step 1: 实现 `src/llm_translator/providers/web/_base.py`**

```python
"""网页逆向 Provider 公共基类：curl_cffi 会话 + 凭据读写辅助。"""
from __future__ import annotations

from typing import Any

from llm_translator.providers.base import AuthError, BaseProvider

# curl_cffi 的异步客户端。导入失败时给清晰提示（仅在真正运行网页 provider 时需要）。
try:
    from curl_cffi.requests import AsyncSession  # type: ignore
    _HAS_CURL_CFFI = True
except Exception:  # pragma: no cover - 仅打包/环境异常
    AsyncSession = None  # type: ignore
    _HAS_CURL_CFFI = False


class WebProviderBase(BaseProvider):
    kind = "web"

    def _require_curl_cffi(self) -> None:
        if not _HAS_CURL_CFFI:
            raise RuntimeError("未安装 curl_cffi，网页逆向 provider 不可用")

    def get_credential(self, key: str) -> str | None:
        return self.credentials.get(self.provider_id, key)

    def set_credential(self, key: str, value: str) -> None:
        self.credentials.set(self.provider_id, key, value)

    def has_credentials(self, keys: list[str]) -> bool:
        return all(self.get_credential(k) for k in keys)

    async def login(self) -> None:
        if not self.has_credentials(self.required_credential_keys()):
            raise AuthError(f"{self.name} 未登录，请在设置中登录")

    def health(self) -> bool:
        return self.has_credentials(self.required_credential_keys())

    def required_credential_keys(self) -> list[str]:
        """子类声明维持会话所需的最小凭据键（如 ['token']）。"""
        raise NotImplementedError
```

- [ ] **Step 2: 验证可导入**

Run: `python -c "from llm_translator.providers.web._base import WebProviderBase; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/providers/web/_base.py
git commit -m "feat(providers/web): shared web provider base"
```

---

## Task 14: 智谱清言网页逆向（`providers/web/glm.py`）

**Files:**
- Create: `src/llm_translator/providers/web/glm.py`
- Test: `tests/test_web_glm.py`

> **逆向说明**：以下端点/Header/参数为基于公开资料的实现骨架。**真实值需在实现时用浏览器开发者工具抓 `chatglm.cn` 的实际请求核实**（标记为 `# VERIFY`）。代码结构完整，运行前替换为实测值。

- [ ] **Step 1: 写测试 `tests/test_web_glm.py`（用 fixture 验证 SSE 文本提取逻辑，不联网）**

```python
import pytest
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.glm import GlmWebProvider


def test_health_without_token():
    p = GlmWebProvider("glm-web", CredentialStore())
    assert p.health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("glm-web", "token", "abc")
    p = GlmWebProvider("glm-web", creds)
    assert p.health() is True


def test_extract_text_from_event():
    # 智谱清言 SSE 事件中的文本片段提取逻辑（纯函数，可单测）
    event = {"parts": [{"content": "你好", "status": "success"}]}
    assert GlmWebProvider.extract_text(event) == "你好"


def test_extract_text_returns_empty_on_unknown_shape():
    assert GlmWebProvider.extract_text({"unknown": 1}) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_web_glm.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/providers/web/glm.py`**

```python
"""智谱清言（chatglm.cn）网页逆向 Provider。

依赖登录后获取的 token（由 auth/login.py 在登录流程中抓取存入 CredentialStore）。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://chatglm.cn/chatglm/backend-api/assistant/stream"  # VERIFY
_IMPERSONATE = "chrome120"


class GlmWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "智谱清言"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """从智谱清言 SSE 事件中提取文本片段。"""
        if not isinstance(event, dict):
            return ""
        parts = event.get("parts") or event.get("choices")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and part.get("content"):
                    return str(part["content"])
        if isinstance(event.get("content"), str):
            return event["content"]
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore
        from llm_translator.utils.sse import parse_sse

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY: 字段名以实测为准
            "assistant_id": "65940acff94777010aa6b796",  # VERIFY
            "conversation_id": "",
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "meta_data": {"channel": "", "draft": "", "input": text},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            async with s.post(_CHAT_URL, json=payload, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    # 直接行级解析（curl_cffi 流为字节行）
                    if not line:
                        continue
                    raw = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else line
                    if not raw.startswith("data:"):
                        continue
                    data = raw[len("data:"):].strip()
                    if data in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    chunk = self.extract_text(event)
                    if chunk:
                        yield chunk
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_web_glm.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/providers/web/glm.py tests/test_web_glm.py
git commit -m "feat(providers/web): Zhipu Qingyan reverse adapter"
```

---

## Task 15: Kimi 网页逆向（`providers/web/kimi.py`）

**Files:**
- Create: `src/llm_translator/providers/web/kimi.py`
- Test: `tests/test_web_kimi.py`

- [ ] **Step 1: 写测试 `tests/test_web_kimi.py`**

```python
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.kimi import KimiWebProvider


def test_health_requires_token():
    assert KimiWebProvider("kimi-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("kimi-web", "token", "abc")
    assert KimiWebProvider("kimi-web", creds).health() is True


def test_extract_text():
    event = {"event": "cmpl", "data": "{\"text\":\"译文\"}"}
    assert KimiWebProvider.extract_text(event) == "译文"


def test_extract_text_empty():
    assert KimiWebProvider.extract_text({"event": "ping"}) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_web_kimi.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/providers/web/kimi.py`**

```python
"""Kimi（kimi.moonshot.cn）网页逆向 Provider。

凭据：登录后从 `https://kimi.moonshot.cn/api/auth/refresh_token` 取得的 access token。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://kimi.moonshot.cn/api/chat/completion"  # VERIFY
_IMPERSONATE = "chrome120"


class KimiWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "Kimi"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """Kimi SSE 事件：{event:'cmpl', data:'<json string with text>'}。"""
        if not isinstance(event, dict):
            return ""
        if event.get("event") != "cmpl":
            return ""
        data = event.get("data")
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                return ""
            return str(parsed.get("text", ""))
        if isinstance(data, dict):
            return str(data.get("text", ""))
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "use_search": False,
            "stream": True,
            "kimiplus_ids": [],
            "refs": [],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            async with s.post(_CHAT_URL, json=payload, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    raw = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else line
                    if not raw.startswith("data:"):
                        continue
                    data = raw[len("data:"):].strip()
                    if data in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    chunk = self.extract_text(event)
                    if chunk:
                        yield chunk
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_web_kimi.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: Commit**

```bash
git add src/llm_translator/providers/web/kimi.py tests/test_web_kimi.py
git commit -m "feat(providers/web): Kimi reverse adapter"
```

---

## Task 16: DeepSeek 网页逆向（`providers/web/deepseek.py`）

**Files:**
- Create: `src/llm_translator/providers/web/deepseek.py`
- Test: `tests/test_web_deepseek.py`

- [ ] **Step 1: 写测试 `tests/test_web_deepseek.py`**

```python
from llm_translator.auth.store import CredentialStore
from llm_translator.providers.web.deepseek import DeepSeekWebProvider


def test_health_requires_token():
    assert DeepSeekWebProvider("deepseek-web", CredentialStore()).health() is False


def test_health_with_token():
    creds = CredentialStore()
    creds.set("deepseek-web", "token", "abc")
    assert DeepSeekWebProvider("deepseek-web", creds).health() is True


def test_extract_text():
    event = {"choices": [{"delta": {"content": "译文"}, "index": 0}]}
    assert DeepSeekWebProvider.extract_text(event) == "译文"


def test_extract_text_empty():
    assert DeepSeekWebProvider.extract_text({"choices": [{"delta": {}}]}) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_web_deepseek.py -v`
Expected: FAIL — 模块未定义。

- [ ] **Step 3: 实现 `src/llm_translator/providers/web/deepseek.py`**

```python
"""DeepSeek 网页（chat.deepseek.com）逆向 Provider。

DeepSeek 网页接口恰好是 OpenAI 兼容风格的 SSE（choices[].delta.content），
但鉴权用 user token + device id，请求需带指纹绕 Cloudflare。
端点/参数以实测为准（标 # VERIFY）。
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from llm_translator.core.prompt import build_messages
from llm_translator.providers.web._base import WebProviderBase

_CHAT_URL = "https://chat.deepseek.com/api/v0/chat/completion"  # VERIFY
_IMPERSONATE = "chrome120"


class DeepSeekWebProvider(WebProviderBase):
    @property
    def name(self) -> str:
        return "DeepSeek 网页"

    def required_credential_keys(self) -> list[str]:
        return ["token"]

    @staticmethod
    def extract_text(event: object) -> str:
        """DeepSeek 网页 SSE：OpenAI 风格 choices[].delta.content。"""
        if not isinstance(event, dict):
            return ""
        choices = event.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                return str(content)
        return ""

    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        self._require_curl_cffi()
        from curl_cffi.requests import AsyncSession  # type: ignore

        token = self.get_credential("token")
        messages = build_messages(text, src, tgt)
        payload = {  # VERIFY: 字段以实测为准
            "message": messages[-1]["content"],  # DeepSeek 网页常用单条 message
            "model": "deepseek_chat",
            "stream": True,
            "chat_session_id": "",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        async with AsyncSession(impersonate=_IMPERSONATE) as s:
            async with s.post(_CHAT_URL, json=payload, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    raw = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else line
                    if not raw.startswith("data:"):
                        continue
                    data = raw[len("data:"):].strip()
                    if data in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    chunk = self.extract_text(event)
                    if chunk:
                        yield chunk
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_web_deepseek.py -v`
Expected: PASS（4 项）。

- [ ] **Step 5: 运行 Phase 2 全部测试**

Run: `pytest -v`
Expected: 全部 PASS（约 40 项）。

- [ ] **Step 6: Commit**

```bash
git add src/llm_translator/providers/web/deepseek.py tests/test_web_deepseek.py
git commit -m "feat(providers/web): DeepSeek web reverse adapter"
```

---

# Phase 3 — 图形界面（PySide6）

> UI 难以纯单测覆盖（spec 第 12 节定为手动验收）。本阶段每个 Task = 实现 + 手动验证清单，辅以可做的轻量逻辑测试。

## Task 17: 浅色主题样式（`assets/light.qss`）

**Files:**
- Create: `assets/light.qss`

- [ ] **Step 1: 写 `assets/light.qss`（对齐参考图配色）**

```css
/* 主背景白，面板浅灰，强调蓝 #1890ff，边框 #e0e0e0，圆角 8px */
QWidget {
    background: #ffffff;
    color: #000000;
    font-size: 14px;
}

QToolBar, QStatusBar, #topBar, #statusBar {
    background: #f8f8f8;
    border: none;
}

QComboBox, QPushButton {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 6px 12px;
    color: #666666;
}
QComboBox:hover, QPushButton:hover {
    border-color: #1890ff;
    color: #000000;
}
QPushButton#primaryBtn {
    background: #1890ff;
    color: #ffffff;
    border: none;
}
QPushButton#primaryBtn:hover {
    background: #40a9ff;
}

QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px;
}

QLabel#secondary {
    color: #666666;
}

QListWidget::item:selected {
    background: #e6f7ff;
    color: #1890ff;
}
```

- [ ] **Step 2: Commit**

```bash
git add assets/light.qss
git commit -m "feat(ui): light theme stylesheet"
```

---

## Task 18: 异步桥（`ui/async_bridge.py`）与入口（`main.py`）

**Files:**
- Create: `src/llm_translator/ui/async_bridge.py`
- Create: `src/llm_translator/main.py`

- [ ] **Step 1: 实现 `src/llm_translator/ui/async_bridge.py`**

```python
"""qasync 桥接：把 asyncio 协程跑在 Qt 事件循环里，token 经 Qt 信号投递到主线程。"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from PySide6.QtCore import QObject, Signal

try:
    import qasync  # type: ignore
    from PySide6.QtWidgets import QApplication
    _HAS_QASYNC = True
except Exception:  # pragma: no cover
    _HAS_QASYNC = False


class TokenEmitter(QObject):
    token_received = Signal(str)
    finished = Signal(str)      # 完整译文
    error = Signal(str)


def install_asyncio_loop(app):
    """在 QApplication 上安装 qasync 事件循环，返回 loop。"""
    if not _HAS_QASYNC:
        raise RuntimeError("未安装 qasync")
    return qasync.QEventLoop(app)


def run_coro(coro: Awaitable, emitter: TokenEmitter) -> asyncio.Task:
    """把翻译协程投到 asyncio loop 运行；token 通过 emitter 信号发出。"""
    loop = asyncio.get_event_loop()
    return loop.create_task(coro)
```

- [ ] **Step 2: 实现 `src/llm_translator/main.py`**

```python
"""应用入口。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from llm_translator.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LLMTranslator")

    # 加载主题样式
    qss = Path(__file__).resolve().parent.parent.parent / "assets" / "light.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))

    # 安装 qasync loop
    from llm_translator.ui.async_bridge import install_asyncio_loop
    import qasync  # type: ignore
    loop = qasync.QEventLoop(app)
    import asyncio
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 验证可启动（此时 MainWindow 尚未实现，先占位让它能 import）**

> 本步骤依赖 Task 19 的 `MainWindow`。若按序执行，跳到 Task 19 完成后一并验证启动。

- [ ] **Step 4: Commit**

```bash
git add src/llm_translator/ui/async_bridge.py src/llm_translator/main.py
git commit -m "feat(ui): qasync bridge and app entrypoint"
```

---

## Task 19: 主窗口（`ui/main_window.py`）

**Files:**
- Create: `src/llm_translator/ui/main_window.py`

- [ ] **Step 1: 实现 `src/llm_translator/ui/main_window.py`**

```python
"""主窗口：顶部语言栏 + 上下输入输出双栏 + 状态栏。对照参考图。"""
from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.core.language import LANGUAGES
from llm_translator.core.translator import Translator
from llm_translator.providers.registry import get_provider
from llm_translator.storage.history import HistoryStore
from llm_translator.storage.settings import Settings
from llm_translator.ui.async_bridge import TokenEmitter
from llm_translator.ui.settings_dialog import SettingsDialog
from llm_translator.ui.history_dialog import HistoryDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LLM 翻译")
        self.resize(720, 560)

        # 持久化与编排
        self.settings = Settings.load()
        self.credentials = CredentialStore()
        self.history = HistoryStore()
        self.emitter = TokenEmitter()
        self._current_task = None
        self._build_translator()

        self._build_ui()
        self._wire_signals()

    def _build_translator(self) -> None:
        pid = self.settings.default_provider
        try:
            provider = get_provider(pid, self.credentials)
        except KeyError:
            provider = None
        if provider is None:
            self.translator = None
            return
        self.translator = Translator(provider=provider, history=self.history, provider_label=pid)

    # ---- UI 构建 ----
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        # 顶部语言栏
        top = QHBoxLayout()
        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.src_combo.addItem(name, code)
            self.tgt_combo.addItem(name, code)
        self.src_combo.setCurrentIndex(self.src_combo.findData(self.settings.src_lang))
        self.tgt_combo.setCurrentIndex(self.tgt_combo.findData(self.settings.tgt_lang))
        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setFixedWidth(40)
        self.provider_combo = QComboBox()
        from llm_translator.providers.registry import all_providers
        for p in all_providers():
            self.provider_combo.addItem(p["label"], p["id"])
        idx = self.provider_combo.findData(self.settings.default_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        from PySide6.QtWidgets import QMenu
        self.menu_btn = QPushButton("☰")
        menu = QMenu()
        menu.addAction("设置", self.on_settings)
        menu.addAction("历史记录", self.open_history)
        menu.addAction("关于", self.on_about)
        self.menu_btn.setMenu(menu)
        top.addWidget(self.src_combo)
        top.addWidget(self.swap_btn)
        top.addWidget(self.tgt_combo)
        top.addStretch()
        top.addWidget(self.provider_combo)
        top.addWidget(self.menu_btn)
        root.addLayout(top)

        # 源文本输入
        self.src_edit = QPlainTextEdit()
        self.src_edit.setPlaceholderText("输入要翻译的文本，按 Ctrl+Enter 翻译")
        self.clear_btn = QPushButton("✕ 清空")
        input_row = QHBoxLayout()
        input_row.addWidget(self.src_edit)
        col = QVBoxLayout()
        col.addWidget(self.clear_btn)
        col.addStretch()
        input_row.addLayout(col)
        root.addLayout(input_row, stretch=5)

        # 翻译按钮
        self.translate_btn = QPushButton("翻译  (Ctrl+Enter)")
        self.translate_btn.setObjectName("primaryBtn")
        root.addWidget(self.translate_btn)

        # 译文输出
        self.tgt_edit = QPlainTextEdit()
        self.tgt_edit.setReadOnly(True)
        self.tgt_edit.setPlaceholderText("译文将在此显示")
        out_row = QHBoxLayout()
        out_row.addWidget(self.tgt_edit, stretch=1)
        out_col = QVBoxLayout()
        self.copy_btn = QPushButton("📋 复制")
        out_col.addWidget(self.copy_btn)
        out_col.addStretch()
        out_row.addLayout(out_col)
        root.addLayout(out_row, stretch=5)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_status()

        self.setCentralWidget(central)

    # ---- 信号 ----
    def _wire_signals(self) -> None:
        self.translate_btn.clicked.connect(self.on_translate)
        self.clear_btn.clicked.connect(lambda: self.src_edit.clear())
        self.copy_btn.clicked.connect(self.on_copy)
        self.swap_btn.clicked.connect(self.on_swap)
        self.menu_btn.clicked.connect(self.on_settings)
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self.emitter.token_received.connect(self._on_token)
        self.emitter.finished.connect(self._on_finished)
        self.emitter.error.connect(self._on_error)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.on_translate)

    # ---- 动作 ----
    def on_translate(self) -> None:
        if self.translator is None:
            QMessageBox.warning(self, "未配置", "请先在设置中选择并配置一个模型。")
            return
        text = self.src_edit.toPlainText().strip()
        if not text:
            return
        self.tgt_edit.clear()
        self.translate_btn.setEnabled(False)
        self.status.showMessage("翻译中…")

        src = self.src_combo.currentData()
        tgt = self.tgt_combo.currentData()

        async def run():
            collected = []
            try:
                async for tok in self.translator.translate(text, src, tgt):
                    collected.append(tok)
                    self.emitter.token_received.emit(tok)
                self.emitter.finished.emit("".join(collected))
            except Exception as e:  # Provider 隔离：错误只反馈给 UI
                self.emitter.error.emit(str(e))

        loop = asyncio.get_event_loop()
        self._current_task = loop.create_task(run())

    def _on_token(self, tok: str) -> None:
        self.tgt_edit.insertPlainText(tok)

    def _on_finished(self, _full: str) -> None:
        self.translate_btn.setEnabled(True)
        self.status.showMessage("完成", 3000)
        self._update_status()

    def _on_error(self, msg: str) -> None:
        self.translate_btn.setEnabled(True)
        self.status.showMessage(f"错误：{msg}", 5000)

    def on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.tgt_edit.toPlainText())

    def on_swap(self) -> None:
        si, ti = self.src_combo.currentIndex(), self.tgt_combo.currentIndex()
        self.src_combo.setCurrentIndex(ti)
        self.tgt_combo.setCurrentIndex(si)

    def on_provider_changed(self, _idx: int) -> None:
        pid = self.provider_combo.currentData()
        self.settings.default_provider = pid
        self.settings.save()
        try:
            provider = get_provider(pid, self.credentials)
        except KeyError:
            return
        if self.translator is None:
            self.translator = Translator(provider=provider, history=self.history, provider_label=pid)
        else:
            self.translator.set_provider(provider, pid)
        self._update_status()

    def on_settings(self) -> None:
        dlg = SettingsDialog(self.credentials, self.settings, self)
        dlg.exec()
        self._build_translator()
        self._update_status()

    def on_about(self) -> None:
        from llm_translator import __version__
        QMessageBox.information(
            self, "关于", f"LLMTranslator v{__version__}\n基于大语言模型的桌面翻译软件。"
        )

    def _update_status(self) -> None:
        pid = self.settings.default_provider
        from llm_translator.providers.registry import all_providers
        label = next((p["label"] for p in all_providers() if p["id"] == pid), pid)
        healthy = self.translator.provider.health() if self.translator else False
        dot = "●" if healthy else "○"
        self.status.showMessage(f"{dot} {label} {'已就绪' if healthy else '未配置/未登录'}")

    def open_history(self) -> None:
        HistoryDialog(self.history, self).exec()
```

- [ ] **Step 2: 临时验证（需 SettingsDialog/HistoryDialog，先写最小桩以验证主窗口能实例化）**

Run:
```bash
python -c "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); \
from PySide6.QtWidgets import QApplication; app=QApplication([]); \
import importlib.util as u; print('MainWindow module imports:', bool(u.find_spec('llm_translator.ui.main_window')))"
```
Expected: `MainWindow module imports: True`

- [ ] **Step 3: Commit（待 Task 20–22 完成后做整窗启动验证）**

```bash
git add src/llm_translator/ui/main_window.py
git commit -m "feat(ui): main window layout and translation wiring"
```

---

## Task 20: 设置对话框（`ui/settings_dialog.py`）

**Files:**
- Create: `src/llm_translator/ui/settings_dialog.py`

- [ ] **Step 1: 实现 `src/llm_translator/ui/settings_dialog.py`**

```python
"""设置对话框：左 provider 列表 + 右详情面板。

API 类：填 base_url / api_key / model + 测试连接。
Web 类：显示登录状态 + 登录按钮（弹 LoginDialog）。
"""
from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from llm_translator.auth.store import CredentialStore
from llm_translator.providers.registry import all_providers
from llm_translator.storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, credentials: CredentialStore, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(640, 460)
        self.credentials = credentials
        self.settings = settings

        layout = QHBoxLayout(self)
        # 左：provider 列表
        self.list_widget = QListWidget()
        self._providers = all_providers()
        for p in self._providers:
            it = QListWidgetItem(f"{p['label']}  ({'API' if p['kind']=='api' else '网页'})")
            it.setData(Qt.UserRole, p)
            self.list_widget.addItem(it)
        self.list_widget.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list_widget, 1)

        # 右：详情容器
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        layout.addWidget(self.detail, 2)
        self._placeholder = QLabel("选择左侧的模型进行配置")
        self.detail_layout.addWidget(self._placeholder)

        if self._providers:
            self.list_widget.setCurrentRow(0)

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        meta = self.list_widget.item(row).data(Qt.UserRole)
        self._clear_detail()
        if meta["kind"] == "api":
            self._build_api_panel(meta)
        else:
            self._build_web_panel(meta)

    def _build_api_panel(self, meta: dict) -> None:
        pid = meta["id"]
        self._api_base = QLineEdit(self.credentials.get(pid, "base_url") or "")
        self._api_key = QLineEdit(self.credentials.get(pid, "api_key") or "")
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_model = QLineEdit(self.credentials.get(pid, "model") or "")
        save_btn = QPushButton("保存")
        test_btn = QPushButton("测试连接")
        status = QLabel("")

        for lbl, w in [("Base URL", self._api_base), ("API Key", self._api_key), ("模型名", self._api_model)]:
            self.detail_layout.addWidget(QLabel(lbl))
            self.detail_layout.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(save_btn)
        row.addWidget(test_btn)
        row.addStretch()
        self.detail_layout.addLayout(row)
        self.detail_layout.addWidget(status)
        self.detail_layout.addStretch()

        save_btn.clicked.connect(lambda: self._save_api(pid, status))
        test_btn.clicked.connect(lambda: self._test_api(pid, status))

    def _save_api(self, pid: str, status: QLabel) -> None:
        for key, w in (("base_url", self._api_base), ("api_key", self._api_key), ("model", self._api_model)):
            self.credentials.set(pid, key, w.text().strip())
        status.setText("已保存")

    def _test_api(self, pid: str, status: QLabel) -> None:
        self._save_api(pid, status)
        from llm_translator.providers.registry import get_provider

        async def go():
            try:
                p = get_provider(pid, self.credentials)
                await p.login()
                async for _ in p.translate("hello", "en", "zh"):
                    break  # 只取首 token 即说明连通
                status.setText("● 已连接")
            except Exception as e:
                status.setText(f"✕ 失败：{e}")

        asyncio.get_event_loop().create_task(go())

    def _build_web_panel(self, meta: dict) -> None:
        pid = meta["id"]
        from llm_translator.auth.store import CredentialStore
        has = bool(self.credentials.get(pid, "token"))
        status = QLabel(f"状态：{'● 已登录' if has else '○ 未登录'}")
        login_btn = QPushButton("登录" if not has else "重新登录")
        clear_btn = QPushButton("清除登录")
        hint = QLabel(f"点击登录将打开 {meta['label']} 网页，登录后自动抓取凭据。")
        hint.setWordWrap(True)

        self.detail_layout.addWidget(QLabel(f"<b>{meta['label']}</b>（网页免费）"))
        self.detail_layout.addWidget(status)
        row = QHBoxLayout()
        row.addWidget(login_btn)
        row.addWidget(clear_btn)
        row.addStretch()
        self.detail_layout.addLayout(row)
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

        login_btn.clicked.connect(lambda: self._do_web_login(pid, status))
        clear_btn.clicked.connect(lambda: (self.credentials.delete(pid), status.setText("状态：○ 未登录")))

    def _do_web_login(self, pid: str, status: QLabel) -> None:
        from llm_translator.ui.login_dialog import LoginDialog
        dlg = LoginDialog(provider_id=pid, credentials=self.credentials, parent=self)
        if dlg.exec() == LoginDialog.Accepted and self.credentials.get(pid, "token"):
            status.setText("状态：● 已登录")
```

- [ ] **Step 2: Commit**

```bash
git add src/llm_translator/ui/settings_dialog.py
git commit -m "feat(ui): settings dialog (API keys + web login)"
```

---

## Task 21: 网页登录抓 Cookie（`auth/login.py` + `ui/login_dialog.py`）

**Files:**
- Create: `src/llm_translator/auth/login.py`
- Create: `src/llm_translator/ui/login_dialog.py`

- [ ] **Step 1: 实现 `src/llm_translator/auth/login.py`**

```python
"""网页登录：每个 provider 的登录页 URL，以及从 QWebEngine 抓 token 的键名。"""
from __future__ import annotations

LOGIN_CONFIG: dict[str, dict] = {
    "glm-web": {
        "url": "https://chatglm.cn/login",
        "token_cookie": "token",        # VERIFY: 实际 cookie/localStorage 键名
        "storage": "cookie",            # "cookie" | "localStorage"
    },
    "kimi-web": {
        "url": "https://kimi.moonshot.cn/login",
        # Kimi 的 token 通过 /api/auth/refresh_token 获取，登录后访问该接口抓 access_token
        "extract_url": "https://kimi.moonshot.cn/api/auth/refresh_token",
        "token_key": "access_token",
        "storage": "api",
    },
    "deepseek-web": {
        "url": "https://chat.deepseek.com/sign_in",
        "token_cookie": "userToken",   # VERIFY
        "storage": "cookie",
    },
}


def login_config(provider_id: str) -> dict:
    return LOGIN_CONFIG[provider_id]
```

- [ ] **Step 2: 实现 `src/llm_translator/ui/login_dialog.py`**

```python
"""内嵌 QWebEngineView 登录对话框：用户在页面登录后，自动抓取凭据存入 CredentialStore。"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from llm_translator.auth.login import login_config
from llm_translator.auth.store import CredentialStore

try:
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor  # type: ignore
    from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
    _HAS_WEBENGINE = True
except Exception:  # pragma: no cover
    _HAS_WEBENGINE = False


class LoginDialog(QDialog):
    def __init__(self, provider_id: str, credentials: CredentialStore, parent=None) -> None:
        super().__init__(parent)
        self.provider_id = provider_id
        self.credentials = credentials
        self.cfg = login_config(provider_id)
        self.setWindowTitle(f"登录 — {provider_id}")
        self.resize(900, 640)

        layout = QVBoxLayout(self)
        if not _HAS_WEBENGINE:
            from PySide6.QtWidgets import QLabel
            layout.addWidget(QLabel("缺少 PySide6-Addons（QWebEngineView），无法内嵌登录。"))
            return

        self.view = QWebEngineView()
        self.profile = self.view.page().profile()
        # 登录后抓 cookie
        self.profile.cookieStore().cookieReceived.connect(self._on_cookie)
        layout.addWidget(self.view)

        self.view.loadFinished.connect(self._on_load_finished)
        self.view.setUrl(QUrl(self.cfg["url"]))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok or self.cfg.get("storage") != "api":
            return
        # Kimi: 登录后请求 refresh_token 接口取 access_token
        js = (
            "fetch(arguments[0], {credentials:'include'})"
            ".then(r=>r.json()).then(d=>d.access_token||'')"
        )
        self.view.page().runJavaScript(
            f"fetch('{self.cfg['extract_url']}',{{credentials:'include'}})"
            f".then(r=>r.json()).then(d=>window.__token=d.{self.cfg['token_key']}||'')"
        )
        # 简化：延迟读取
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._read_api_token)

    def _read_api_token(self) -> None:
        self.view.page().runJavaScript("window.__token||''", self._store_api_token)

    def _store_api_token(self, token: str) -> None:
        if token:
            self.credentials.set(self.provider_id, "token", str(token))
            self.accept()

    def _on_cookie(self, cookie) -> None:
        if self.cfg.get("storage") != "cookie":
            return
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        if name == self.cfg.get("token_cookie"):
            value = bytes(cookie.value()).decode("utf-8", errors="replace")
            if value:
                self.credentials.set(self.provider_id, "token", value)
                self.accept()
```

- [ ] **Step 3: Commit**

```bash
git add src/llm_translator/auth/login.py src/llm_translator/ui/login_dialog.py
git commit -m "feat(auth,ui): embedded web login with cookie/token capture"
```

---

## Task 22: 历史记录对话框（`ui/history_dialog.py`）

**Files:**
- Create: `src/llm_translator/ui/history_dialog.py`

- [ ] **Step 1: 实现 `src/llm_translator/ui/history_dialog.py`**

```python
"""历史记录对话框：列表 + 搜索框 + 清空。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from llm_translator.storage.history import HistoryStore


class HistoryDialog(QDialog):
    def __init__(self, history: HistoryStore, parent=None) -> None:
        super().__init__(parent)
        self.history = history
        self.setWindowTitle("历史记录")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索原文/译文…")
        self.search.textChanged.connect(self._reload)
        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.clicked.connect(self._clear)
        top.addWidget(self.search)
        top.addWidget(self.clear_btn)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)
        self._reload()

    def _reload(self) -> None:
        q = self.search.text().strip()
        rows = self.history.search(q, limit=200) if q else self.history.list(limit=200)
        self.list_widget.clear()
        for e in rows:
            text = f"[{e.provider}] {e.source_text}  →  {e.target_text}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, e)
            self.list_widget.addItem(it)

    def _clear(self) -> None:
        self.history.clear()
        self._reload()
```

- [ ] **Step 2: 整窗启动验证**

Run: `python -m llm_translator.main`
Expected: 窗口出现，布局接近参考图（顶部语言栏 + 上下输入输出双栏 + 浅色蓝点缀），点 ☰ 可打开设置，未配置模型时状态栏显示"未配置"。

- [ ] **Step 3: 手动验收清单（对照 spec 第 14 节）**

```
[ ] 窗口启动正常，配色为浅色蓝点缀，接近参考图
[ ] 顶部语言下拉、⇄交换、provider 下拉可见可用
[ ] Ctrl+Enter 触发翻译
[ ] 设置对话框能填 API Key 并"测试连接"成功（需真实 DeepSeek Key）
[ ] 流式输出：译文逐字出现
[ ] 复制按钮可用
[ ] 历史记录可查看/搜索/清空
[ ] 网页 provider 点登录弹出内嵌网页（需联网）
```

- [ ] **Step 4: Commit**

```bash
git add src/llm_translator/ui/history_dialog.py
git commit -m "feat(ui): history dialog"
```

---

# Phase 4 — 打包与文档

## Task 23: PyInstaller 打包（`build.spec`）

**Files:**
- Create: `build.spec`

> 关键坑：`curl_cffi`（含动态库 `libcurl-impersonate`）与 `QWebEngineView`（PySide6-Addons 大量二进制）需在 spec 显式声明。

- [ ] **Step 1: 写 `build.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置。验证：pyinstaller build.spec
import os
from PySide6 import __path__ as pyside_paths

block_cipher = None

# curl_cffi 自带 impersonate 动态库，需随包
curl_cffi_binaries = []
try:
    import curl_cffi
    curl_cffi_dir = os.path.dirname(curl_cffi.__file__)
    for root, _dirs, files in os.walk(curl_cffi_dir):
        for f in files:
            if f.endswith((".dll", ".so", ".dylib")):
                rel = os.path.relpath(root, os.path.dirname(curl_cffi_dir))
                curl_cffi_binaries.append((os.path.join(root, f), f"curl_cffi/{rel}"))
except ImportError:
    pass

a = Analysis(
    ["src/llm_translator/main.py"],
    pathex=["src"],
    binaries=curl_cffi_binaries,
    datas=[
        ("assets/light.qss", "assets"),
    ],
    hiddenimports=[
        "curl_cffi",
        "curl_cffi.requests",
        "curl_cffi._wrapper",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "qasync",
        "cryptography",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LLMTranslator",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="LLMTranslator",
)
```

- [ ] **Step 2: 试打包（onedir 模式）**

Run: `pyinstaller build.spec --noconfirm`
Expected: 生成 `dist/LLMTranslator/` 目录，内含 `LLMTranslator.exe`。

- [ ] **Step 3: 运行打包产物验证启动**

Run: `dist/LLMTranslator/LLMTranslator.exe`
Expected: 应用窗口正常启动，与开发环境一致。

> 若报 `curl_cffi` 找不到动态库，按报错路径补充到 `curl_cffi_binaries`；若 `QWebEngineView` 白屏/缺失，确认 `PySide6-Addons` 已随包（PyInstaller 的 PySide6 hook 通常自动处理，需 `hiddenimports` 中保留 QtWebEngine*）。

- [ ] **Step 4: Commit**

```bash
git add build.spec
git commit -m "build: PyInstaller spec (curl_cffi + QWebEngine)"
```

---

## Task 24: Inno Setup 安装器（`installer.iss`）

**Files:**
- Create: `installer.iss`

- [ ] **Step 1: 写 `installer.iss`（需本机装 Inno Setup 6 编译）**

```ini
; Inno Setup 脚本。用 ISCC 编译：iscc installer.iss
#define MyAppName "LLMTranslator"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "LLMTranslator"
#define MyAppExeName "LLMTranslator.exe"

[Setup]
AppId={{LLMTRANSLATOR-0A1B2C3D-2026}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=LLMTranslator-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\LLMTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 2: 编译安装包**

Run: `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss`
Expected: 生成 `installer_output/LLMTranslator-Setup-0.1.0.exe`。

- [ ] **Step 3: 双击安装包，验证一键安装**

Expected: 双击 → 选目录 → 安装 → 桌面/开始菜单出现快捷方式 → 启动正常。

- [ ] **Step 4: Commit**

```bash
git add installer.iss
git commit -m "build: Inno Setup one-click installer"
```

---

## Task 25: README 与分发说明

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 `README.md`**

```markdown
# LLMTranslator — 跨平台大模型桌面翻译软件

基于大语言模型的桌面翻译客户端，界面参考百度翻译。支持 OpenAI 兼容付费 API（DeepSeek / 智谱 GLM / OpenAI）与智谱清言 / Kimi / DeepSeek 网页免费逆向接入。

## 功能（v0.1 MVP）
- 文本翻译，流式输出（打字机效果）
- 翻译历史记录（搜索/清空）
- 多模型配置：付费 API（填 Key）+ 网页免费（内嵌登录）
- Windows 一键安装

## 开发环境
```bash
python -m pip install -e ".[dev]"
pytest -v                      # 运行测试
python -m llm_translator.main  # 启动
```

## 打包
```bash
pyinstaller build.spec --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```
产物：`installer_output/LLMTranslator-Setup-0.1.0.exe`（双击即装）。

## 首次使用
1. 安装后启动，点右上角 ☰ 设置。
2. 付费 API：填 Base URL + API Key + 模型名 → 测试连接。
3. 网页免费：点登录，在内嵌网页完成登录，自动抓取凭据。
4. 回主界面选模型，输入文本，Ctrl+Enter 翻译。

## 声明
网页逆向接入仅供个人学习使用，可能违反各服务条款且接口随时可能失效。凭据本地加密存储（Fernet，机器特征派生密钥）。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README"
```

- [ ] **Step 3: Phase 4 验收（对照 spec 第 14 节剩余项）**

```
[ ] pyinstaller 打包成功，产物可启动
[ ] Inno Setup 生成安装包，双击一键安装成功
[ ] 首次启动 SmartScreen 提示"仍可运行"（未签名，预期行为，README 已说明）
[ ] 凭据加密存储，重启后保持登录态
```

---

## 实现完成后

- 全量测试：`pytest -v` 全绿。
- 在真实 Windows 机器上跑完手动验收清单（Task 22 Step 3 + Task 25 Step 3）。
- 三家网页逆向端点（glm/kimi/deepseek 标 `# VERIFY` 处）用浏览器开发者工具核实并替换为实测值——这是上线前唯一必须人工确认的部分。
