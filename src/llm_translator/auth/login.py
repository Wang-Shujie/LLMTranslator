"""网页登录配置：每个 provider 的登录页 URL + 抓取凭据的 JS。

抓取分两段 JS（在已登录的页面上下文里执行）：
- setup_js：页面加载后跑一次，用于发起异步请求（如 Kimi 用 refresh_token 换 access_token）。
- poll_js：定时轮询，返回 token 字符串；非空即视为登录成功，存凭据并关闭弹窗。
  为 None 表示尚不能自动抓取（靠 LoginDialog 的诊断日志定位真实键名后再补）。

凭据位置以公开逆向项目为准：
- DeepSeek：localStorage 的 userToken.value（xtekky/deepseek4free 核实）
- Kimi：cookie refresh_token → POST /api/auth/refresh_token → access_token（LLM-Red-Team/kimi-free-api）
- 智谱清言：公开资料未确认确切键名，暂只做诊断日志，待真机登录日志确认后补 poll_js。
"""
from __future__ import annotations

LOGIN_CONFIG: dict[str, dict] = {
    "deepseek-web": {
        "url": "https://chat.deepseek.com/sign_in",
        "setup_js": None,
        "poll_js": "(function(){try{var t=JSON.parse(localStorage.getItem('userToken'));return (t&&t.value)||''}catch(e){return ''}})()",
    },
    "kimi-web": {
        "url": "https://kimi.moonshot.cn/login",
        "setup_js": (
            "fetch('https://kimi.moonshot.cn/api/auth/refresh_token',{credentials:'include'})"
            ".then(function(r){return r.json()})"
            ".then(function(d){window.__kimi_token=d.access_token||''})"
            ".catch(function(){window.__kimi_token=''})"
        ),
        "poll_js": "window.__kimi_token||''",
    },
    "glm-web": {
        "url": "https://chatglm.cn/login",
        # 键名未确认：暂不自动抓取，靠 LoginDialog 诊断日志（localStorage/cookie）定位真实 token。
        "setup_js": None,
        "poll_js": None,
    },
}


def login_config(provider_id: str) -> dict:
    return LOGIN_CONFIG[provider_id]
