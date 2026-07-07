"""网页登录配置：每个 provider 的登录页 URL + 抓取凭据的方式。

两种抓取：
- JS（setup_js/poll_js）：在已登录页面上下文里读 localStorage（DeepSeek/Kimi）。
- cookie（token_cookie）：登录态在 cookie 里时，等该 cookie 到达即抓（智谱清言）。

凭据位置以公开逆向项目 + 真机日志为准：
- DeepSeek：localStorage 的 userToken.value（xtekky/deepseek4free）
- Kimi：www.kimi.com，localStorage 的 access_token（真机日志确认）
- 智谱清言：cookie chatglm_refresh_token（xiaoY233/GLM-Free-API + 真机日志确认）
"""
from __future__ import annotations

LOGIN_CONFIG: dict[str, dict] = {
    "deepseek-web": {
        "url": "https://chat.deepseek.com/sign_in",
        "setup_js": None,
        "poll_js": "(function(){try{var t=JSON.parse(localStorage.getItem('userToken'));return (t&&t.value)||''}catch(e){return ''}})()",
        "token_cookie": None,
    },
    "kimi-web": {
        "url": "https://www.kimi.com/",
        # Kimi 登录后 access_token 直接存于 localStorage（真机日志确认），轮询读取即可
        "setup_js": None,
        "poll_js": "localStorage.getItem('access_token') || ''",
        "token_cookie": None,
    },
    "glm-web": {
        "url": "https://chatglm.cn/",
        # 智谱清言登录态在 cookie：抓 chatglm_refresh_token（比 chatglm_token 更持久）
        "setup_js": None,
        "poll_js": None,
        "token_cookie": "chatglm_refresh_token",
    },
}


def login_config(provider_id: str) -> dict:
    return LOGIN_CONFIG[provider_id]

