# 截图 OCR 翻译 — 设计文档

- **日期**：2026-07-08
- **状态**：待用户评审
- **范围**：LLMTranslator v0.1.0 之后第 3 个增量功能（4 个后续功能中的第 3 个）

---

## 1. 概述（Overview）

全局热键 `Ctrl+Shift+O` → 自定义截图覆盖层（百度网盘式）：暗化背景 + 拖框选区 + 工具条（源/目标语言、对照、直接翻译、翻译）。点"翻译"后，RapidOCR（ONNX，离线）识别选区内文字+坐标，再用现有翻译 provider 翻译，按模式呈现：

| 直接翻译 | 对照 | 结果模式 |
|---|---|---|
| OFF | OFF | **原地覆盖**：译文按原文位置叠在截图上，盖住原文 |
| OFF | ON | **对照**：选区上方弹一个**同尺寸**译文画布，与原图上下对比 |
| ON | — | **直接翻译**：面板显示 OCR 原文 + 译文 |

对照按钮仅在"直接翻译"关闭时可启用。

### 1.1 范围内（v1）
- 全局热键截图、自定义覆盖层、拖框选区、工具条（语言/对照/直接翻译/翻译）。
- RapidOCR 离线识别（文字 + bbox 坐标）；现有 provider 在线翻译。
- 三种结果模式（原地覆盖 / 对照 / 直接翻译）。
- 菜单开关，状态持久化。仅主屏。

### 1.2 非目标（YAGNI）
- 多显示器/多屏截图（v1 仅主屏）。
- 选区内文字的精细排版还原（字号/颜色完全匹配原图）——best-effort 适配 bbox。
- OCR 热键/语言的自定义设置 UI（v1 用默认值，设置项后期加）。
- 纯视觉大模型出坐标（方案 X，已否决）。

---

## 2. 技术方案决策

### 2.1 OCR + 位置来源：RapidOCR（ONNX）
| 候选 | 结论 |
|---|---|
| X. 纯视觉大模型出 text+bbox+translation | 否决。坐标精度取决于模型（Qwen2-VL/GLM-4.6V 较好，其余粗糙），复杂版面错位；达不到"对齐百度网盘"的就地覆盖质量。|
| **Y. RapidOCR（ONNX）取文字+坐标 + 现有 provider 翻译** | **选定**。坐标可靠、CJK 好；翻译仍走在线 provider（与全 app 一致）。|

代价：引入 `onnxruntime`（~50–80MB 原生）+ RapidOCR 模型（~10–30MB），打包体积明显增大（见 §10）。

### 2.2 截图捕获：Qt `QScreen.grabWindow`
热键瞬间先拍**冻结帧**（避免覆盖层被拍入），覆盖层以冻结帧为背景；选区从冻结帧裁剪。零新依赖（Qt 自带）。

### 2.3 翻译粒度
- **原地覆盖 / 对照**：逐块翻译（`asyncio.gather` 并发，每块取完整译文）→ 保留位置映射。
- **直接翻译**：整段一次性翻译（流式灌面板）→ 不需位置。

---

## 3. 架构与模块划分（纯新增）

```
src/llm_translator/
  core/
    ocr.py              # OcrBlock(text, bbox) + OcrEngine（RapidOCR 封装）→ list[OcrBlock]
    screen_capture.py   # grab_screen() → QPixmap（主屏冻结快照）
  ui/
    capture_overlay.py  # CaptureOverlay：全屏暗化 + 拖框选区 + 工具条
    ocr_result.py       # paint_translated_blocks + 三种结果窗口
    main_window.py      # OCR 热键 → 启动截图；接结果 → 按模式显示；菜单开关
  storage/settings.py   # ocr_hotkey、ocr_enabled
```

复用底座：worker 线程 + `asyncio.run` + Qt 信号回主线程；翻译 provider/registry；`keyboard` 热键（与划词共用）。

---

## 4. OCR 引擎（`core/ocr.py`）

```python
@dataclass
class OcrBlock:
    text: str
    bbox: tuple[int, int, int, int]   # x, y, w, h（选区内坐标）

class OcrEngine:
    def recognize(self, image: QPixmap) -> list[OcrBlock]:
        """RapidOCR 识别 → 文字块 + 坐标框。同步阻塞，跑 worker 线程。"""
```
RapidOCR 输出 4 点多边形 → 转 `(x,y,w,h)`。`recognize` 同步阻塞 → worker 线程调用。

---

## 5. 截图覆盖层（`ui/capture_overlay.py`）

`CaptureOverlay(QWidget)`，全屏无边框置顶：
- 背景：冻结快照为底图，整体半透明暗化，**仅选区清晰**。
- 拖框选区：鼠标按下→拖动→松开；蓝色边框 + 四角拖拽点；可重拖改。
- **工具条**（选区下方，白底圆角）：`自动检测▼  ⇌  目标语言▼  ☑对照  ☐直接翻译  [翻译]  ✕`
  - 对照按钮仅在"直接翻译"关闭时可启用。
  - 模式判定：直接翻译 ON → 直接翻译面板；OFF+对照 OFF → 原地覆盖；OFF+对照 ON → 对照。
- `Esc` / `✕` 取消关闭。
- 点"翻译" → 发 `capture_selected(crop_image, mode, src, tgt)` → 自身关闭。

---

## 6. 三种结果视图（`ui/ocr_result.py`）

共享 `paint_translated_blocks(painter, blocks_and_translations, bg_mode)`：每块 `bbox` 填底色 → 画译文（字号适配框宽高，超出截断/换行）。

| 模式 | 视图 | 渲染 |
|---|---|---|
| 原地覆盖 | `OverlayResultWindow`（无边框置顶，定位到截图原位置） | 在 `crop_image` 上按 bbox 填底盖原文 + 画译文 |
| 对照 | 上下两个同尺寸窗体：上方译文画布（白底按 bbox 画译文），下方原图 | 上：白底画布镜像版面画译文；下：原图；上下对比 |
| 直接翻译 | `OcrDirectPanel`（小对话框） | 上：OCR 原文（可复制）；下：流式译文（可复制），不需 bbox |

三者均支持 `Esc`/点外关闭、复制译文。

---

## 7. 主窗口接线 + 开关（`ui/main_window.py`）

- OCR 热键（默认 `ctrl+shift+o`，可配）→ `_start_ocr_capture()`：`grab_screen()` 拍冻结帧 → 显示 `CaptureOverlay`。
- 接 `capture_selected` → worker 线程跑 OCR + 翻译（按 mode 决定逐块/整段）→ 构造对应结果视图显示。
- 菜单加"截图 OCR"checkable 开关，状态写 `settings.ocr_enabled`，启动据此注册热键。

---

## 8. Settings 新增

```python
ocr_hotkey: str = "ctrl+shift+o"
ocr_enabled: bool = True
```
v1 用默认值；自定义 UI 后期加。

---

## 9. 错误处理

| 场景 | 处理 |
|---|---|
| 选区无文字 / OCR 空结果 | 提示"未识别到文字"，不渲染 |
| OCR 引擎初始化失败（模型缺失/onnxruntime 出错） | 提示"OCR 引擎初始化失败" |
| 某块翻译失败 | 该块留空/保原文，其余正常；末尾汇总"X 块失败" |
| 未配置 provider | 提示"请先配置翻译模型" |
| 多显示器 | 仅主屏（v1 边界，README 注明） |

---

## 10. 打包（最重的功能）

- 新依赖：`rapidocr`（ONNX）+ `onnxruntime`（原生）。
- `onnxruntime` ≈ 50–80MB 原生库；RapidOCR 模型 ≈ 10–30MB → 打包体积 **+~80–120MB**。
- `build.spec`：`*collect_all("rapidocr")`（含模型数据）+ `*collect_all("onnxruntime")`（原生 dll）。
- README 注明体积影响 + 首次 OCR 模型加载耗时（~1–2s）。

---

## 11. 测试策略

| 层级 | 方法 |
|---|---|
| 单元 | bbox 4 点→(x,y,w,h) 转换；三种模式判定逻辑；`paint_translated_blocks` 几何（mock painter）；OCR 文本拼接 |
| 集成（fixture） | RapidOCR 对一张固定测试图识别（需模型，本地可跑）|
| 手动验收 | 见下清单 |

**手动验收清单**：
```
[ ] Ctrl+Shift+O → 暗化覆盖层，能拖框选区，工具条出现
[ ] 工具条对照/直接翻译互斥逻辑正确（直接翻译开时对照禁用）
[ ] 原地覆盖：译文按原位置盖原文，版面大致对齐
[ ] 对照：上方同尺寸译文画布 + 下方原图，上下对比
[ ] 直接翻译：面板显示 OCR 原文 + 流式译文
[ ] 各模式 Esc/点外关闭、译文可复制
[ ] 无文字提示；未配置模型提示
[ ] 菜单开关"截图 OCR"，状态持久化
```

---

## 12. 文档

README 加"截图 OCR（Ctrl+Shift+O）"：三种模式、依赖 onnxruntime/rapidocr 的体积与首次加载耗时、可菜单开关。

---

## 13. 验收标准（MVP）

1. 热键 → 自定义覆盖层拖框选区 + 工具条。
2. 三种结果模式（原地覆盖/对照/直接翻译）按 toggle 逻辑正确呈现。
3. 译文位置/版面合理（RapidOCR 坐标）。
4. OCR/翻译失败、无文字、未配置模型 → 友好提示，不崩溃。
5. 菜单可开关、持久化。
6. 打包含 onnxruntime + rapidocr 模型，体积增大已记录。

---

## 14. 后续（不在本 spec 范围）

- 多显示器/多屏截图。
- 选区内文字精细排版还原（字号/颜色完全匹配）。
- 设置 UI（热键/语言自定义）。
- 其余增量功能：TTS（已 spec）、划词翻译（已 spec）、文档翻译。
