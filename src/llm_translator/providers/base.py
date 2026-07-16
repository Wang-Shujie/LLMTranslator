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
    async def translate(self, text: str, src: str, tgt: str, context: str = "") -> AsyncGenerator[str, None]:
        """异步生成器：逐个 yield token。用法 `async for tok in provider.translate(...)`。"""

    @abstractmethod
    def health(self) -> bool:
        """当前登录态/连接是否有效（不发起重请求，仅检查已存凭据状态）。"""
