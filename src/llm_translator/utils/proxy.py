"""QWebEngine 登录页的代理策略。

现象：系统配了 HTTP 代理（典型 Clash/V2Ray 的 127.0.0.1:7890），但代理进程未
运行/未监听 → Chromium 继承系统代理后所有请求 net::ERR_PROXY_CONNECTION_FAILED，
表现为登录页"无法联网"，尽管系统浏览器（不走该死代理）一切正常。

策略：登录页均为国内站点、本应直连。仅当系统配了 HTTP 代理但 TCP 探测连不上时，
给 Chromium 传 --no-proxy-server 强制直连；代理可达或未配代理时不干预，避免影响
确实需要走代理的用户。
"""
from __future__ import annotations

import socket
from typing import Callable, Optional, Tuple

HttpProxy = Optional[Tuple[str, int]]


def decide_force_direct(proxy: HttpProxy, reachable: Callable[[str, int], bool]) -> bool:
    """纯决策：系统配了 HTTP 代理但不可达 → 应强制直连。

    抽出为纯函数以便单测（reachable 由调用方注入，避免真实网络）。
    """
    if not proxy:
        return False
    host, port = proxy
    try:
        return not reachable(host, port)
    except Exception:
        return True


def _tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def system_http_proxy() -> HttpProxy:
    """返回系统配置的 HTTP 代理 (host, port)，没有则 None。"""
    try:
        from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
        for p in QNetworkProxyFactory.systemProxyForQuery():
            if p.type() == QNetworkProxy.HttpProxy and p.hostName():
                return (p.hostName(), p.port())
    except Exception:
        pass
    return None


def force_direct_for_dead_proxy() -> bool:
    """系统配了连不上的 HTTP 代理时返回 True。"""
    return decide_force_direct(system_http_proxy(), _tcp_reachable)


def apply_to_chromium_flags() -> None:
    """必要时把 --no-proxy-server 写入 QTWEBENGINE_CHROMIUM_FLAGS。

    必须在 QtWebEngine 子进程启动前（首次创建 QWebEngineView 前）调用——标志在
    子进程启动时读取，运行期无法变更。
    """
    import os
    if not force_direct_for_dead_proxy():
        return
    cur = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--no-proxy-server" not in cur:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (cur + " --no-proxy-server").strip()
