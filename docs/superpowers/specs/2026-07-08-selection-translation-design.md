# 划词翻译 — 设计文档

- **日期**：2026-07-08
- **状态**：待用户评审
- **范围**：LLMTranslator v0.1.0 之后第 2 个增量功能（4 个后续功能中的第 2 个）

---

## 1. 概述（Overview）

在任意程序中选中文字 → 按全局热键 `Ctrl+Shift+T` → 在光标附近弹出流式译文明信片，可复制或"展开到主窗口"。取词用"模拟 Ctrl+C 读剪贴板"（覆盖几乎所有支持复制的程序）。触发后**强制恢复用户原剪贴板**（硬要求）。可在主菜单开关。

### 1.1 范围内（v1）
- 全局热键触发（默认 `Ctrl+Shift+T`，存于设置）。
- 模拟 Ctrl+C 取词；Qt `QClipboard` 保存/恢复原剪贴板（文本 + 图片）。
- 贴光标的无边框置顶弹窗：流式译文 + 复制 + "展开到主窗口"。
- 主菜单可勾选开关；状态持久化。
- 弹窗翻译**不写入历史**（临时查询）。

### 1.2 非目标（Non-Goals，YAGNI）
- 鼠标松开自动弹窗 / 选中后浮图标（真·划词）——跨程序选区检测复杂、易误触，不做。
- 划词翻译的设置 UI（热键自定义、开关的设置面板）——v1 用菜单开关 + 默认热键；设置项后期加。
- 非文本/非图片剪贴板格式（如资源管理器复制的文件）的完美恢复——边界，见 §5。

---

## 2. 技术方案决策

**选定方案：`keyboard` 库（全局热键 + 模拟 Ctrl+C）+ Qt `QClipboard`（剪贴板保存/恢复）。**

| 候选 | 结论 |
|---|---|
| ① `keyboard` + Qt QClipboard | **选定**。一个新依赖（`keyboard`）；剪贴板交给 Qt 能保存/恢复文本和图片；代码最少。|
| ② Windows 原生 `RegisterHotKey` + `SendInput` | 否决。代码量大、pywin32 更重、复杂。|
| ③ `pynput` + Qt 剪贴板 | 否决。API 比 `keyboard` 啰嗦，无明显收益。|

> 原方案曾考虑 `pyperclip`，但 `pyperclip` 只能处理文本，无法恢复图片剪贴板。为完整满足"剪贴板恢复"要求，改用 Qt 内置 `QClipboard`（零新依赖，文本+图片都能保存/恢复）。故唯一新依赖是 `keyboard`。

**默认热键 `Ctrl+Shift+T` 的选择理由**：`Ctrl+D` 等高频快捷键被全局热键占用会与浏览器（收藏）/Excel（填充）等双触发或冲突；`Ctrl+Shift+T` 在多数程序无占用，安全。

---

## 3. 架构与模块划分

纯新增 + 给 `Translator` 加一个参数：

```
src/llm_translator/
  core/
    selection.py        # SelectionController(QObject)：注册全局热键（keyboard），
                        #   取词流程含剪贴板保存/恢复（Qt QClipboard），发 captured 信号
    translator.py       # translate() 增加 save_history 参数（弹窗用 False）
  ui/
    selection_popup.py  # SelectionPopup(QWidget)：无边框置顶、贴光标、流式译文 + 复制 + 展开
    main_window.py      # 持有 SelectionController；接弹窗 + expand_to_main；菜单开关
  storage/
    settings.py         # 加 selection_hotkey、selection_enabled
```

**复用底座**：翻译流水线（`Translator`）、worker 线程 + `asyncio.run` + Qt 信号回主线程的后台模式。

---

## 4. 取词 + 剪贴板恢复流程（核心正确性点）

全程 Qt 主线程 + 非阻塞等待（不卡 UI）：

```
[keyboard 线程] 按下 Ctrl+Shift+T
  → self.triggered.emit()                       # Qt 信号跨到主线程
[Qt 主线程] on_triggered():
  1. clip = QGuiApplication.clipboard()
  2. saved_text = clip.text()
     saved_pixmap = clip.pixmap()（若剪贴板是图片）            # 保存原剪贴板
  3. keyboard.send("ctrl+c")                                  # 模拟复制
  4. QTimer.singleShot(120ms, _finish_capture)                # 非阻塞等目标程序写入剪贴板
[Qt 主线程] _finish_capture():
  5. captured = clip.text()                                   # 取词
  6. 还原剪贴板（强制，无论取词成败）：                          # ★ 用户硬要求
        若 saved_pixmap 非空 → clip.setPixmap(saved_pixmap)
        否则                  → clip.setText(saved_text)
  7. if captured 且 captured != saved_text：
        取光标坐标 → 发 captured(captured_text, cursor_pos) 信号
```

**满足"必须恢复"的要点**：
- Qt `QClipboard`（非 pyperclip）→ 保存/恢复**文本和图片**两种主流内容。
- 第 2 步先存原剪贴板，第 6 步取完词立刻还原；第 6 步在取词成败两条路径上都执行。
- 第 4 步 `QTimer.singleShot(120ms)` 非阻塞等待，不冻结主界面。
- 全程 Qt 主线程（热键信号投递过来），避免跨线程碰剪贴板。

**已知边界**：极少见的剪贴板 MIME（如资源管理器"复制的文件"）无法完美还原；文本和图片两种日常场景完全覆盖。

---

## 5. 弹窗组件（`ui/selection_popup.py`）

`SelectionPopup(QWidget)`：
- 窗口 flags：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`（无边框、置顶、不占任务栏）。
- 定位：贴光标；超出屏幕边缘自动翻到对侧（不挡、不出屏）。
- 内容：流式译文（QLabel 自动换行）+ 底部 `📋复制`、`↗展开到主窗口` 两按钮。
- 关闭：点弹窗外（失去激活）/ 按 `Esc`。
- 流式：复用 worker 线程 + token 信号，token 追加到译文 Label。
- **复用一个实例**：每次触发先 `reset()`（清空旧文、停旧翻译）→ 重新定位 → 重新翻译，避免叠弹窗。
- 信号 `expand_to_main(source_text, target_text)`：点"展开"时发出，主窗口接收。

---

## 6. 热键控制器（`core/selection.py`）

`SelectionController(QObject)`：
- `enable()`：按 `settings.selection_hotkey` 注册 `keyboard.add_hotkey(hotkey, self._on_hotkey)`。
- `disable()`：`keyboard.remove_hotkey(hotkey)`。
- `_on_hotkey()`（keyboard 线程）：只 `self.triggered.emit()`。
- 主线程槽执行 §4 取词/恢复流程 → 发 `captured(text, pos)`。
- 启动时按 `settings.selection_enabled` 决定是否 `enable()`。
- 退出时 `disable()` 清理。

---

## 7. 主窗口接线 + 开关（`ui/main_window.py`）

- `__init__`：构造 `SelectionController`，连 `captured(text, pos)` → `_show_selection_popup`。
- `_show_selection_popup(text, pos)`：取/复用 `SelectionPopup`，定位 `pos`，用 `settings.default_provider` + 当前 src/tgt 起 worker 线程翻译（`save_history=False`），流式灌进弹窗。
- 连弹窗 `expand_to_main(src, tgt)` → 填 `src_edit`/`tgt_edit` + 显示并激活主窗口。
- **菜单开关**：☰ 菜单加 checkable 项 `☑ 划词翻译 (Ctrl+Shift+T)`。勾选 → `controller.enable()` + `settings.selection_enabled=True`；取消 → `disable()` + `False`。状态持久化，启动据此注册。

---

## 8. `Translator.translate()` 改动（最小、向后兼容）

```python
async def translate(self, text, src, tgt, save_history: bool = True):
    ...
    if save_history:
        self.history.add(Entry(...))
```

主界面现有调用保持默认 `True`；划词弹窗传 `False`。

---

## 9. Settings 新增

```python
selection_hotkey: str = "ctrl+shift+t"
selection_enabled: bool = True
```

v1 用默认值；自定义热键/设置面板的 UI 后期再加。

---

## 10. 错误处理

| 场景 | 处理 |
|---|---|
| 选中为空 / 目标程序不支持复制 | 不弹窗（或闪现"未取到选中文本"小提示） |
| 当前 provider 未配置 | 弹窗显示"请先在设置中配置模型" |
| 翻译失败（provider 报错） | 弹窗内显示错误文案 |
| 热键注册失败（被占用） | 启动提示一次，功能自动关闭，不崩 |
| 剪贴板恢复 | §4，取词成败都还原 |

---

## 11. 打包

- 新依赖：`keyboard`（小，纯 Python + Windows 钩子）。
- `build.spec` 加 `*collect_all("keyboard")`。
- README 注明：`keyboard` 为低级键盘钩子，**极少数杀毒可能误报**（自用项目可加白名单）。

---

## 12. 测试策略

| 层级 | 方法 |
|---|---|
| 单元（pytest） | 热键串解析；弹窗贴边翻转定位；剪贴板保存/恢复逻辑（mock QClipboard）；`translate(save_history=False)` 不写历史 |
| 手动验收 | 见下清单 |

**手动验收清单**：
```
[ ] 浏览器/Word/记事本/PDF 选中文字 → Ctrl+Shift+T → 光标处弹窗流式译文
[ ] 复制一段内容 → 触发划词 → Ctrl+V → 粘贴出【原复制内容】（剪贴板已恢复）★核心
[ ] 剪贴板原是图片 → 划词后图片仍在
[ ] 弹窗点复制可用；点"展开到主窗口"→ 主界面填入并前置
[ ] 点弹窗外 / Esc → 关闭
[ ] ☰ 菜单取消勾选"划词翻译" → Ctrl+Shift+T 不再触发；重启保持关闭
[ ] 未配置模型时弹窗提示
```

---

## 13. 文档

- README 功能区加"划词翻译（全局热键 Ctrl+Shift+T）"。
- 注明：默认热键、剪贴板自动恢复、`keyboard` 库的 AV 误报可能、可在主菜单开关。

---

## 14. 验收标准（MVP）

1. 任意程序选中文字 + `Ctrl+Shift+T` → 光标处弹流式译文明信片。
2. **触发划词后，用户原剪贴板（文本/图片）被完整恢复**（硬要求）。
3. 弹窗可复制、可"展开到主窗口"；点外/Esc 关闭。
4. 弹窗翻译不写入历史。
5. ☰ 菜单可开关划词翻译，状态持久化。
6. 未选中/不支持复制/未配置模型/翻译失败 → 友好处理，不崩溃。

---

## 15. 后续（不在本 spec 范围）

- 热键自定义 / 设置面板 UI。
- 鼠标松开自动弹窗 / 选中浮图标（真·划词）。
- 非文本/非图片剪贴板格式的恢复。
- 其余增量功能：TTS（已 spec）、截图 OCR、文档翻译。
