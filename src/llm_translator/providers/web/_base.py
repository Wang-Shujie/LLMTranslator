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
