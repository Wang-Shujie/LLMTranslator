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
