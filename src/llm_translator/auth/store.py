"""加密凭据存储（Fernet，密钥由机器特征派生）。

凭据整体存为一个加密的 JSON 字典：{provider_id: {key: value}}。

安全边界：本模块防御"随意的本地文件窥探"（casual local file snooping），
而非拥有本机的攻击者——后者既能读取本文件，也能重新派生密钥。
密钥由 MAC 地址 + 主机名经 PBKDF2 派生，固定盐。
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
