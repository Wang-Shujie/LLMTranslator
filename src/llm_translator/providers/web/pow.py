"""DeepSeek 网页 PoW（工作量证明）求解。

复用 xtekky/deepseek4free 逆向的 WASM（Custom sha3）。wasmtime + numpy 为可选依赖
（pyproject 的 [web] extra），缺失时抛清晰错误。WASM 文件随包打包。
来源：https://github.com/xtekky/deepseek4free
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_WASM_PATH = Path(__file__).parent / "wasm" / "sha3_wasm_bg.7b9ca65ddd.wasm"


def _require_deps() -> tuple[Any, Any]:
    try:
        import wasmtime  # type: ignore
        import numpy  # type: ignore
        return wasmtime, numpy
    except ImportError as e:  # pragma: no cover - 仅缺可选依赖时
        raise RuntimeError(
            "DeepSeek 网页翻译需要可选依赖 wasmtime 与 numpy，"
            '请安装：pip install "llm-translator[web]"'
        ) from e


class _DeepSeekHash:
    """加载并调用 PoW WASM（wasm_solve）。实例缓存复用（编译 WASM 较贵）。"""

    def __init__(self) -> None:
        wasmtime, numpy = _require_deps()
        self._np = numpy
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, _WASM_PATH.read_bytes())
        self._store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        linker.define_wasi()
        self._inst = linker.instantiate(self._store, module)
        self._mem = self._inst.exports(self._store)["memory"]

    def _write(self, text: str) -> tuple[int, int]:
        encoded = text.encode("utf-8")
        length = len(encoded)
        ptr = self._inst.exports(self._store)["__wbindgen_export_0"](self._store, length, 1)
        mv = self._mem.data_ptr(self._store)
        for i, b in enumerate(encoded):
            mv[ptr + i] = b
        return ptr, length

    def calculate(self, algorithm: str, challenge: str, salt: str,
                  difficulty: int, expire_at: int):
        prefix = f"{salt}_{expire_at}_"
        exp = self._inst.exports(self._store)
        retptr = exp["__wbindgen_add_to_stack_pointer"](self._store, -16)
        try:
            cp, cl = self._write(challenge)
            pp, pl = self._write(prefix)
            exp["wasm_solve"](self._store, retptr, cp, cl, pp, pl, float(difficulty))
            mv = self._mem.data_ptr(self._store)
            status = int.from_bytes(bytes(mv[retptr:retptr + 4]), "little", signed=True)
            if status == 0:
                return None
            value = self._np.frombuffer(bytes(mv[retptr + 8:retptr + 16]), dtype=self._np.float64)[0]
            return int(value)
        finally:
            exp["__wbindgen_add_to_stack_pointer"](self._store, 16)


@lru_cache(maxsize=1)
def _hasher() -> _DeepSeekHash:
    return _DeepSeekHash()


def solve_challenge(config: dict) -> str:
    """解 PoW 挑战，返回 x-ds-pow-response 头所需的 base64 串。"""
    answer = _hasher().calculate(
        config["algorithm"], config["challenge"], config["salt"],
        config["difficulty"], config["expire_at"],
    )
    result = {
        "algorithm": config["algorithm"],
        "challenge": config["challenge"],
        "salt": config["salt"],
        "answer": answer,
        "signature": config["signature"],
        "target_path": config["target_path"],
    }
    return base64.b64encode(json.dumps(result).encode()).decode()
