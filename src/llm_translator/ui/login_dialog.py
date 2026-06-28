"""内嵌 QWebEngineView 登录对话框：用户在页面登录后，抓取凭据存入 CredentialStore。

抓取策略见 auth/login.py（setup_js/poll_js）：定时轮询 poll_js，命中非空即存凭据并
关闭弹窗。另提供"我已完成登录"按钮兜底（SPA 登录可能不触发 loadFinished），并写
诊断日志（cookie / localStorage 键名），便于定位键名未确认的 provider。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from llm_translator.auth.login import login_config
from llm_translator.auth.store import CredentialStore

# Chromium 会继承系统代理；若系统配了连不上的 HTTP 代理（Clash 等关闭后残留），
# 登录页会 ERR_PROXY_CONNECTION_FAILED。国内登录页本应直连，这里在 QtWebEngine
# 初始化前按需强制直连。必须在首次创建 QWebEngineView（子进程启动）前生效。
from llm_translator.utils.proxy import apply_to_chromium_flags
apply_to_chromium_flags()

try:
    from PySide6.QtWebEngineCore import QWebEngineProfile  # type: ignore
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
        self._cookies: dict[str, str] = {}

        layout = QVBoxLayout(self)
        if not _HAS_WEBENGINE:
            layout.addWidget(QLabel("缺少 PySide6-Addons（QWebEngineView），无法内嵌登录。"))
            return

        self.view = QWebEngineView()
        self.profile = self.view.page().profile()
        # cookieAdded：Qt6 信号名（Qt5 的 cookieReceived 已移除）。累计所有 cookie 供诊断。
        self.profile.cookieStore().cookieAdded.connect(self._on_cookie)
        layout.addWidget(self.view)

        hint = QLabel("登录成功后会自动抓取凭据并关闭；若未自动关闭，登录后点下方按钮。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.done_btn = QPushButton("我已完成登录，抓取凭据")
        self.done_btn.clicked.connect(self._manual_capture)
        layout.addWidget(self.done_btn)

        self.view.loadFinished.connect(self._on_load_finished)
        self.view.setUrl(QUrl(self.cfg["url"]))

        # 轮询 poll_js：登录态出现即抓取并关闭
        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self._poll_capture)

    # ---- 生命周期 ----
    def _on_load_finished(self, ok: bool) -> None:
        self._log(f"loadFinished ok={ok} url={self.view.url().toString()}")
        if not ok:
            return
        setup = self.cfg.get("setup_js")
        if setup:
            self.view.page().runJavaScript(setup)
        self._dump_storage_keys()
        self._poll.start()
        self._poll_capture()  # 立即试一次

    def _on_cookie(self, cookie) -> None:
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        value = bytes(cookie.value()).decode("utf-8", errors="replace")
        if name and name not in self._cookies:
            self._cookies[name] = value
            self._log(f"cookie: {name}={value[:30]}")

    # ---- 抓取 ----
    def _poll_capture(self) -> None:
        js = self.cfg.get("poll_js")
        if js:
            self.view.page().runJavaScript(js, self._on_token)

    def _manual_capture(self) -> None:
        self._log("manual capture")
        setup = self.cfg.get("setup_js")
        if setup:
            self.view.page().runJavaScript(setup)
        self._dump_storage_keys()
        self._poll_capture()

    def _on_token(self, token) -> None:
        if token is None:
            token = ""
        token = str(token).strip()
        self._log(f"poll result: {token[:24]!r}")
        if token:
            self.credentials.set(self.provider_id, "token", token)
            self._poll.stop()
            self.accept()

    # ---- 诊断 ----
    def _dump_storage_keys(self) -> None:
        # 记录 localStorage 键名（智谱清言等键名未确认时，据此定位真实 token）
        self.view.page().runJavaScript(
            "Object.keys(localStorage).join(',')",
            lambda ks: self._log(f"localStorage keys: {ks}"),
        )

    def _log(self, msg: str) -> None:
        line = f"[{self.provider_id}] {msg}"
        print(line, flush=True)
        try:
            from llm_translator.storage import paths
            with open(paths.data_dir() / "login_capture.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._poll.stop()
        self._log(f"cookies observed: {list(self._cookies)}")
        super().closeEvent(event)
