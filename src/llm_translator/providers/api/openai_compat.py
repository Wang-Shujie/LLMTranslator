"""OpenAI 兼容协议 Provider（通吃 DeepSeek / 智谱 GLM / OpenAI / 兼容聚合平台）。"""
from __future__ import annotations

from typing import AsyncGenerator

import httpx

from llm_translator.auth.store import CredentialStore
from llm_translator.core.prompt import build_messages
from llm_translator.providers.base import AuthError, BaseProvider
from llm_translator.utils.proxy import force_direct_for_dead_proxy
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


def preset_for(provider_id: str) -> dict:
    """返回 provider_id 对应的预设（base_url/model/label）。

    provider 初始化与设置面板预填默认值共用此映射，避免两处分别硬编码。
    未知 id 回落到 deepseek 预设。
    """
    return PRESETS[_PRESET_BY_ID.get(provider_id, "deepseek")]


class OpenAICompatProvider(BaseProvider):
    kind = "api"

    def __init__(self, provider_id: str, credentials: CredentialStore) -> None:
        super().__init__(provider_id, credentials)
        preset = preset_for(provider_id)
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
        # 系统配了连不上的代理（如 Clash 残留 127.0.0.1:7890）时直连，否则尊重系统代理
        trust_env = not force_direct_for_dead_proxy()
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), trust_env=trust_env) as client:
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
