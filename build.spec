# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置。验证：pyinstaller build.spec
import os
from PySide6 import __path__ as pyside_paths
from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None

# wasmtime（DeepSeek 网页 PoW 用）的平台 native dll（win32-x86_64/_wasmtime.dll）由 ctypes
# 运行时加载，PyInstaller 静态分析看不见，必须整体收集包的 datas/binaries/submodules
_wasmtime_datas, _wasmtime_binaries, _wasmtime_hi = collect_all("wasmtime")

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
    binaries=[*curl_cffi_binaries, *_wasmtime_binaries],
    datas=[
        ("assets/light.qss", "assets"),
        # DeepSeek 网页 PoW 的 WASM（随包；wasmtime/numpy 为可选依赖，需另装 [web]）
        ("src/llm_translator/providers/web/wasm", "llm_translator/providers/web/wasm"),
        *_wasmtime_datas,
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
        "numpy",
        # 注册表用 importlib 懒加载 web providers，PyInstaller 静态分析看不见，
        # 必须显式收集整个 llm_translator 包（含 glm/kimi/deepseek/login_dialog 等）
        *collect_submodules("llm_translator"),
        *_wasmtime_hi,
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
