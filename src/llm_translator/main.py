"""应用入口。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from llm_translator.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LLMTranslator")

    # 加载主题样式
    qss = Path(__file__).resolve().parent.parent.parent / "assets" / "light.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))

    # 安装 qasync loop
    from llm_translator.ui.async_bridge import install_asyncio_loop
    import qasync  # type: ignore
    loop = qasync.QEventLoop(app)
    import asyncio
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
