# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置。验证：pyinstaller build.spec
import os
from PySide6 import __path__ as pyside_paths

block_cipher = None

# curl_cffi 自带 impersonate 动态库，需随包
curl_cffi_binaries = []
try:
    import curl_cffi
    curl_cffi_dir = os.path.dirname(curl_cffi.__file__)
    for root, _dirs, files in os.walk(curl_cffi_dir):
        for f in files:
            if f.endswith((".dll", ".so", ".dylib")):
                rel = os.path.relpath(root, os.path.dirname(curl_cffi_dir))
                curl_cffi_binaries.append((os.path.join(root, f), f"curl_cffi/{rel}"))
except ImportError:
    pass

a = Analysis(
    ["src/llm_translator/main.py"],
    pathex=["src"],
    binaries=curl_cffi_binaries,
    datas=[
        ("assets/light.qss", "assets"),
        # DeepSeek 网页 PoW 的 WASM（随包；wasmtime/numpy 为可选依赖，需另装 [web]）
        ("src/llm_translator/providers/web/wasm", "llm_translator/providers/web/wasm"),
    ],
    hiddenimports=[
        "curl_cffi",
        "curl_cffi.requests",
        "curl_cffi._wrapper",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "qasync",
        "cryptography",
        # 可选依赖：仅当安装了 [web] 时才用得上。PyInstaller 打包 DeepSeek 网页需带上。
        "wasmtime",
        "numpy",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LLMTranslator",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="LLMTranslator",
)
