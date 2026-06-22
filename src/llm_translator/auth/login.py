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
