"""内嵌 QWebEngineView 登录对话框：用户在页面登录后，自动抓取凭据存入 CredentialStore。"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from llm_translator.auth.login import login_config
from llm_translator.auth.store import CredentialStore

try:
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor  # type: ignore
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

        layout = QVBoxLayout(self)
        if not _HAS_WEBENGINE:
            from PySide6.QtWidgets import QLabel
            layout.addWidget(QLabel("缺少 PySide6-Addons（QWebEngineView），无法内嵌登录。"))
            return

        self.view = QWebEngineView()
        self.profile = self.view.page().profile()
        # 登录后抓 cookie
        self.profile.cookieStore().cookieReceived.connect(self._on_cookie)
        layout.addWidget(self.view)

        self.view.loadFinished.connect(self._on_load_finished)
        self.view.setUrl(QUrl(self.cfg["url"]))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok or self.cfg.get("storage") != "api":
            return
        # Kimi: 登录后请求 refresh_token 接口取 access_token
        self.view.page().runJavaScript(
            f"fetch('{self.cfg['extract_url']}',{{credentials:'include'}})"
            f".then(r=>r.json()).then(d=>window.__token=d.{self.cfg['token_key']}||'')"
        )
        # 简化：延迟读取
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._read_api_token)

    def _read_api_token(self) -> None:
        self.view.page().runJavaScript("window.__token||''", self._store_api_token)

    def _store_api_token(self, token: str) -> None:
        if token:
            self.credentials.set(self.provider_id, "token", str(token))
            self.accept()

    def _on_cookie(self, cookie) -> None:
        if self.cfg.get("storage") != "cookie":
            return
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        if name == self.cfg.get("token_cookie"):
            value = bytes(cookie.value()).decode("utf-8", errors="replace")
            if value:
                self.credentials.set(self.provider_id, "token", value)
                self.accept()
