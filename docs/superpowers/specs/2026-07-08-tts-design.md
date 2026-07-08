# TTS 朗读 — 设计文档

- **日期**：2026-07-08
- **状态**：待用户评审
- **范围**：LLMTranslator v0.1.0 之后第一个增量功能（4 个后续功能中的第 1 个）

---

## 1. 概述（Overview）

为 LLMTranslator 增加文本朗读（Text-to-Speech）：主界面的原文与译文各加一个 🔊 按钮，点击即朗读对应文本，播放中可停止。第一版**仅支持在线** TTS（`edge-tts` / 微软语音），但抽象出 `TtsEngine` 接口，为后续接入离线语音引擎预留扩展点。

### 1.1 范围内（v1）
- 原文 🔊 按钮、译文 🔊 按钮（主界面各一）。
- 按文本语言自动选择 edge-tts 音色（多语言）。
- 播放 / 停止（按钮图标 🔊 ⇄ ⏹ 切换）；两个按钮互斥（点一个会先停另一个）。
- 失败友好提示（不崩溃）。

### 1.2 非目标（Non-Goals，YAGNI）
- 离线语音引擎（仅预留接口，不实现）。
- 音色手选、语速/音调调节。
- 历史记录条目的朗读。
- 源语言为 `auto` 时的语言自动检测（用默认音色兜底，见 §5）。
- TTS 设置项（v1 不加；接口与设置均已预留）。

---

## 2. 技术栈决策

**选定方案：edge-tts（在线）→ 临时 mp3 → QMediaPlayer（下载后播放）。**

| 候选 | 结论 |
|---|---|
| ① edge-tts → 临时 mp3 → QMediaPlayer | **选定**。简单、稳、可停止、复用 PySide6 自带多媒体（无新重型依赖）。短文本 ~1s 出声可接受。|
| ② edge-tts 流式 → QBuffer → QMediaPlayer 边下边播 | 否决。分块喂送 + 缓冲协调复杂易错，短文本过度工程。|
| ③ edge-tts → simpleaudio/playsound | 否决。多引原生音频库、停止控制差、打包多坑。|

**依赖**：`edge-tts`（带 `aiohttp` 等，约 +10~20MB）。播放用 `PySide6.QtMultimedia.QMediaPlayer`（PySide6 自带）。

**为什么 edge-tts**：免费、音色自然、支持几十种语言和多种音色——翻译场景下多语言音色质量是 TTS 有没有用的关键。Windows 自带的离线 SAPI 语音读外语基本没法听，故留作后续离线引擎选项。

---

## 3. 架构与模块划分

纯新增，不改已有代码：

```
src/llm_translator/
  core/tts.py        # TtsEngine 接口 + EdgeTtsEngine + LANG_VOICE 映射（纯 async，不依赖 Qt）
  ui/tts_player.py   # TtsPlayer(QObject)：持有 QMediaPlayer + worker 线程，负责播放/停止/状态
  ui/main_window.py  # 仅加 2 个 🔊 按钮，接到 TtsPlayer
```

**复用底座**：
- 翻译流水线（`Translator`）不涉及——TTS 独立于翻译。
- worker 线程 + `asyncio.run` + Qt 信号回主线程的模式（与现有翻译后台一致），因为 edge-tts 是 async、qasync 跑不了。

---

## 4. 引擎接口（`core/tts.py`）—— 离线扩展点

```python
class TtsError(Exception):
    """TTS 合成失败。"""

class TtsEngine(ABC):
    """语音合成引擎接口。

    v1 仅有在线实现 EdgeTtsEngine。后续离线引擎（如 OfflineSapiEngine，基于
    pyttsx3 / Windows SAPI）实现同一接口即可接入，调用方（TtsPlayer）无需改动。
    """

    @abstractmethod
    async def synthesize(self, text: str, lang: str) -> bytes:
        """合成语音，返回完整 mp3 字节。

        text: 要朗读的文本。
        lang: 语言码（zh/en/ja/...）。引擎据此选音色。
        失败抛 TtsError。
        """


# 语言码 → edge-tts 音色（默认自然女声）
LANG_VOICE: dict[str, str] = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "ru": "ru-RU-DariyaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "th": "th-TH-PremwadeeNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "ar": "ar-SA-ZariyahNeural",
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # lang 未命中或 "auto" 时兜底


class EdgeTtsEngine(TtsEngine):
    """在线 TTS 引擎（edge-tts / 微软语音）。"""

    async def synthesize(self, text: str, lang: str) -> bytes:
        import edge_tts  # 延迟导入，便于打包收集 + 缺失时清晰报错
        voice = LANG_VOICE.get(lang, DEFAULT_VOICE)
        try:
            comm = edge_tts.Communicate(text, voice)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            if not buf:
                raise TtsError("edge-tts 返回空音频")
            return bytes(buf)
        except TtsError:
            raise
        except Exception as e:  # 网络/解析等
            raise TtsError(f"edge-tts 合成失败：{e}") from e
```

**离线预留**：未来加 `OfflineSapiEngine(TtsEngine)`，其 `synthesize` 用 `pyttsx3` 写入 wav 字节返回；`TtsPlayer` 构造时传入不同实现即可，调用方代码不变。

---

## 5. 播放控制器（`ui/tts_player.py`）

`TtsPlayer(QObject)` 把"合成"与"播放"串起来，主界面只跟它打交道。

**对外接口**：
- `play(text: str, lang: str) -> None`：**总是开始一次新播放**——内部 `_gen` 自增，作废任何在途合成/播放（自然实现"切到新内容时停旧的"）。是否要先停由调用方（按钮 handler，§6）决定。
- `stop() -> None`：停播放器、作废当前合成任务、清临时文件、回 idle。
- 信号 `state_changed(str)`：`"idle" | "loading" | "playing"`，驱动按钮图标。
- 信号 `error(str)`：失败文案，主界面显示在状态栏。

**内部流程**：
```
play(text, lang)
  → gen = ++self._gen; state_changed("loading")
  → threading.Thread(worker):
        data = asyncio.run(engine.synthesize(text, lang))
        _synthesized.emit(gen, data)        # Qt 信号，跨线程回主线程
  → _play_bytes(gen, data) [主线程 Slot]:
        if gen != self._gen: return         # 过期，丢弃
        写临时 .mp3
        QMediaPlayer.setSource + play()
        state_changed("playing")
  → QMediaPlayer.EndOfMedia → state_changed("idle") + 清临时文件
```

**两个正确性要点**：
1. **跨线程安全**：`edge_tts` 在 worker 线程 `asyncio.run` 跑；mp3 字节经 Qt 信号 `_synthesized` 投回主线程后才操作 `QMediaPlayer`（QMediaPlayer 只能在 Qt 线程用）。
2. **作废过期合成（代际计数）**：`_gen` 自增。`stop()` 与新 `play()` 都令 `_gen` 前进；旧合成回来时 `gen != self._gen` 即丢弃，避免"停了又突然响"。

**停止的细节**：Python `threading.Thread` 无法干净 kill；正在跑的 edge-tts 合成会在后台自然结束（结果被代际计数丢弃）。`stop()` 立即停播放器 + 标记作废，体感即时。

---

## 6. 主界面接线（`ui/main_window.py`，改动约 30~40 行）

- 原文输入区 `✕清空` 旁加 `🔊` 按钮 → `on_speak_source()` →
  `tts_player.play(self.src_edit.toPlainText(), self.src_combo.currentData())`。
- 译文输出区 `📋复制` 旁加 `🔊` 按钮 → `on_speak_target()` →
  `tts_player.play(self.tgt_edit.toPlainText(), self.tgt_combo.currentData())`。
- `__init__` 内构造一个共享 `TtsPlayer(EdgeTtsEngine())`。
- 两个按钮都听 `tts_player.state_changed`，并用一个 `_active_speak_btn` 记录当前在播的是哪个：播放中那个按钮图标 `🔊 → ⏹`，另一个保持 `🔊`；播完/停止还原。
- **按钮 handler 的 toggle/switch 逻辑**（明确，避免"再点当前按钮是重启还是关闭"的歧义）：
  ```python
  def on_speak_source(self):
      if self._active_speak_btn is self.src_speak_btn:   # 当前正在播原文 → 关闭（toggle off）
          self.tts_player.stop()
      else:                                               # 否则切到原文（会自然停掉译文）
          self.tts_player.play(self.src_edit.toPlainText(), self.src_combo.currentData())
  ```
  译文按钮同理。即：**点当前在播的按钮 = 停止；点另一个 = 切换**。`play()` 内部的 `_gen` 机制保证切换时旧合成被作废。

> 不重构 main_window，只新增按钮 + handler + 图标切换逻辑。`TtsPlayer` 独立成文件，避免主窗口继续膨胀。

---

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| 空文本 | `play()` 直接 return，不报错、不切状态 |
| edge-tts 网络/超时/空音频 | 抛 `TtsError` → `error` 信号 → 状态栏"朗读失败：…"，按钮还原 idle |
| QMediaPlayer 播放异常 | 同样走 `error` 信号 |
| 无网络（在线限制） | edge-tts 必然失败 → 友好提示（不崩溃）；见 §10 文档说明 |

---

## 8. 打包

- `pyproject.toml`：依赖加 `edge-tts`。
- `build.spec`：
  - `*collect_all("edge_tts")`（`edge_tts` 在 `EdgeTtsEngine` 内延迟 `import`，PyInstaller 静态看不见，必须整体收集）。
  - hiddenimports 加 `PySide6.QtMultimedia`（确保 QMediaPlayer 进包）。
  - Windows 上 mp3 播放走系统 Media Foundation，无需额外 Qt 音频插件。
- TTS 上线后的发布包需重新构建一次（开发期不影响；当前按用户要求不 push）。

---

## 9. 测试策略

| 层级 | 方法 |
|---|---|
| 单元（pytest） | `LANG_VOICE` 映射查表（纯函数）；`EdgeTtsEngine` 选 voice 的逻辑（`LANG_VOICE.get(lang, DEFAULT)`，不联网） |
| 手动验收 | 原文🔊/译文🔊出声、⏹停止、互斥、播完还原、断网友好提示、空文本无操作 |

> `EdgeTtsEngine.synthesize` 与 `TtsPlayer` 涉及网络/Qt 多媒体，按既有原则（在线/UI 类主要靠手动验收）不做联网单元测试，与 web provider 一致。

**手动验收清单**：
```
[ ] 点原文 🔊 → 听到原文朗读（按 src 语言音色）
[ ] 点译文 🔊 → 听到译文朗读（按 tgt 语言音色）
[ ] 播放中按钮变 ⏹，再点停止；播完自动还原 🔊
[ ] 朗读原文时点译文 🔊 → 先停原文再播译文（互斥）
[ ] 拔网后点 🔊 → 状态栏提示"朗读失败"，不崩溃
[ ] 清空文本后点 🔊 → 无反应（不报错）
```

---

## 10. 文档（用户要求"写清当前仅在线"）

- `README.md` 功能区加一项："TTS 朗读（原文/译文，在线）"。
- 在 README 加说明段：
  > **TTS 朗读当前仅支持在线**（使用 `edge-tts` / 微软语音），需要联网。代码已预留 `TtsEngine` 接口，后续版本将加入离线语音引擎（如 Windows 系统 SAPI）。
- `core/tts.py` 的 `TtsEngine` 抽象类文档字符串中标注"离线实现入口"，便于后续维护者识别扩展点。

---

## 11. 验收标准（MVP）

1. 主界面原文区与译文区各有一个 🔊 按钮。
2. 点原文 🔊 按源语言音色朗读原文；点译文 🔊 按目标语言音色朗读译文。
3. 播放中按钮变 ⏹，可停止；播放结束自动还原 🔊。
4. 两个 🔊 互斥（点任一会先停另一个）。
5. 断网/合成失败 → 状态栏友好提示，不崩溃。
6. 空文本 → 按钮无操作。
7. `TtsEngine` 接口存在，`EdgeTtsEngine` 为其在线实现（离线扩展点已预留）。
8. README 写明"当前仅在线 + 已预留离线接口"。

---

## 12. 后续（不在本 spec 范围）

- 离线 TTS 引擎（`OfflineSapiEngine`，pyttsx3 / Windows SAPI）。
- 音色手选 / 语速音调（设置项）。
- 历史记录朗读。
- `src_lang="auto"` 时的语言检测（用于精确选音色）。
- 其余 3 个增量功能：划词翻译、截图 OCR、文档翻译（各自独立 spec）。
