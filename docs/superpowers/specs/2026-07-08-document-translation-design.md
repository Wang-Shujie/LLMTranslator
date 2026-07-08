# 文档翻译 — 设计文档

- **日期**：2026-07-08
- **状态**：待用户评审
- **范围**：LLMTranslator v0.1.0 之后第 4 个增量功能（4 个后续功能中的最后一个）

---

## 1. 概述（Overview）

从菜单"文档翻译…"打开对话框 → 选 `.docx` 或 `.txt` 文件 → 逐段翻译（并发）→ 输出同格式译文文件（同目录 + `_目标语言` 后缀），保留段落结构/样式。

### 1.1 范围内（v1）
- 支持格式：**Word(.docx) + 纯文本(.txt)**（PDF 不在 v1）。
- 输出：同格式译文，替换原文，保留段落结构/样式；docx 段内 run 级格式为已知边界（见 §4）。
- 逐段并发翻译（并发上限可配）；进度条 + 取消。
- 预留"整篇翻译"接口（方案 B），v1 不实现。

### 1.2 非目标（YAGNI）
- PDF 输入/输出（暂不做；PDF 版面保留输出是研究级难题）。
- 双语对照输出（v1 只输出纯译文；以后加不难）。
- docx 段内 run 级格式（段中加粗/斜体）的完美保留——逐段翻译固有取舍。
- docx 页眉/页脚翻译（v1 仅正文 + 表格）。
- 文档翻译的全局热键（菜单对话框流程，不需要）。

---

## 2. 技术方案决策

**选定方案：逐段翻译（并发），方案 ①。**

| 候选 | 结论 |
|---|---|
| **① 逐段翻译（并发）** | **选定**。段落边界/结构精确保留；失败可定位到段。docx 段内 run 格式丢失（已知边界）。|
| ② 整篇一次性翻译 | 否决（拆分易错、段落边界易乱）。**但保留为接口（B），见 §3。** |

- docx 处理：`python-docx`（逐段抽取 + 写回）。
- txt 处理：标准库（空行分块 + 写回）。
- 翻译：复用现有默认 provider；逐段 `"".join([tok async for tok in provider.translate(seg, src, tgt)])` 取完整译文，`asyncio.gather` + `Semaphore` 并发。

---

## 3. 架构与服务接口（含预留 B）

纯新增：

```
src/llm_translator/
  core/
    doc_translate.py    # DocumentTranslator（编排）+ TranslationGranularity 策略接口
                        #   + DocxHandler / TxtHandler（格式专用 抽取/写回）
  ui/
    document_dialog.py  # DocumentDialog：选文件、语言、输出、进度、取消
    main_window.py      # 菜单"文档翻译…" → 打开对话框
  storage/settings.py   # doc_concurrency、doc_output_dir
```

**翻译粒度策略（预留 B 的扩展点）**：
```python
class TranslationGranularity(ABC):
    @abstractmethod
    async def translate(self, segments, provider, src, tgt) -> list[str]:
        """segments → 译文列表，1:1 对应。"""

class PerParagraphGranularity(TranslationGranularity):   # v1，方案①
    async def translate(self, segments, provider, src, tgt):
        sem = asyncio.Semaphore(8)
        async def one(seg):
            async with sem:
                return "".join([t async for t in provider.translate(seg, src, tgt)])
        return await asyncio.gather(*[one(s) for s in segments])

class WholeDocumentGranularity(TranslationGranularity):  # 预留，方案②（B），v1 不实现
    async def translate(self, segments, provider, src, tgt):
        raise NotImplementedError("整篇翻译：后续版本实现")
```
> `DocumentTranslator` 持一个 granularity，v1 注入 `PerParagraphGranularity`。以后做整篇，实现 `WholeDocumentGranularity` 即可，调用方不变。即"保留 B 接口"。

---

## 4. 格式处理器

```python
class DocxHandler:
    def extract(self, path) -> list[Segment]      # 正文段落 + 表格单元格段落（python-docx）
    def replace(self, path, translations, out)    # 按段写回译文，保留段落结构/样式
class TxtHandler:
    def extract(self, path) -> list[Segment]      # 按空行分块
    def replace(self, path, translations, out)
```

**docx 已知边界**：段内 run 级格式（段中加粗/斜体）丢失——译文按整段写回；段落级样式（标题/列表/对齐）保留。表头/页眉页脚 v1 不译（仅正文 + 表格）。

---

## 5. 翻译流程（worker 线程）

```
选文件 → DocumentDialog 调 doc_translate(path, src, tgt, out_path):
  handler = Handler.for_format(path)            # .docx / .txt
  segments = handler.extract(path)
  → 进度信号：已抽取 N 段
  translations = await granularity.translate(segments, provider, src, tgt)  # 逐段并发
  → 进度信号：每段完成更新
  handler.replace(path, translations, out_path)
  → 完成信号：out_path
```
输出命名：与原文件同目录，文件名加目标语言后缀（如 `report_en.docx`）。

---

## 6. 对话框 UI（`ui/document_dialog.py`）

- 选文件区：`[选择文件…]` → 文件对话框（过滤 `*.docx *.txt`）→ 显示文件名。
- 语言区：源语言下拉（`自动检测`/…）、⇌ 交换、目标语言下拉（默认读 settings）。
- 输出：显示解析后输出路径（默认同目录 + `_目标语言` 后缀）；可"更改…"另选目录。
- 操作：`[翻译]`、进度条 `已译 X / N 段`、`[取消]`、状态标签。
- 后台：worker 线程跑 §5 流程；进度/完成/错误经 Qt 信号回主线程。
- **取消**：置 cancel 标志 → 剩余段跳过 → 不写半成品；状态"已取消"。
- 完成：状态显示输出路径 + "打开所在文件夹"按钮。

---

## 7. 主窗口接线

- ☰ 菜单加 **`文档翻译…`**（普通动作，非 checkable）→ 打开 `DocumentDialog`。
- **不绑全局热键**（菜单对话框流程）。

---

## 8. Settings 新增

```python
doc_concurrency: int = 8        # 逐段翻译并发上限
doc_output_dir: str = ""        # 空 = 输出到原文件同目录；否则用此目录
```

v1 用默认值；设置 UI 后期加。

---

## 9. 错误处理

| 场景 | 处理 |
|---|---|
| 不支持的格式（如 PDF） | "v1 仅支持 .docx/.txt" |
| 文件读取失败（损坏/无权限） | "无法读取文件：…" |
| 空文档 / 无文字段 | "文档为空或无文字" |
| 某段翻译失败 | 该段保留原文，其余继续；末尾"X 段失败" |
| 未配置 provider | "请先配置翻译模型" |
| 取消 | "已取消"，不写半成品 |
| 输出写出失败 | "无法写出：…" |

---

## 10. 打包（4 个功能里最轻）

- 新依赖：仅 `python-docx`（纯 Python，几 MB）。txt 用标准库。
- `build.spec` 加 `*collect_submodules("docx")`（python-docx 模块名为 `docx`）。
- **无原生库**，体积几乎不增。

---

## 11. 测试策略

| 层级 | 方法 |
|---|---|
| 单元 | `TxtHandler` 空行分块 + 写回往返；`DocxHandler` 抽取（正文+表格）+ 写回保留结构（fixture docx）；`PerParagraphGranularity` 用 fake provider 验证 1:1 + 并发；`WholeDocumentGranularity` 抛 `NotImplementedError`（预留 B）|
| 集成 | 小 fixture docx + mock provider → 译文 docx，校验段数保留、文字替换 |
| 手动验收 | 见下清单 |

**手动验收清单**：
```
[ ] 菜单"文档翻译…" → 对话框 → 选 .docx → 翻译 → 同目录产出 report_目标语言.docx
[ ] 选 .txt → 产出同名 _目标语言.txt
[ ] docx 段落结构/样式（标题、列表、对齐）保留；段内加粗等 run 格式丢失（已知边界）
[ ] 进度条实时更新；点取消 → 中止、不写半成品、状态"已取消"
[ ] 表格内文字也被翻译；空文档/损坏文件友好提示
[ ] 未配置模型时提示
```

---

## 12. 文档

README 加"文档翻译（菜单 → 文档翻译…）"：支持 .docx/.txt（PDF 不在 v1）、docx 段内 run 格式边界、输出命名、**预留"整篇翻译"接口（B）后续实现**。

---

## 13. 验收标准（MVP）

1. docx/txt 进、同格式译文出（同目录 + `_目标语言` 后缀）。
2. 段落结构/样式保留（docx run 级格式为已知边界）。
3. 进度 + 取消正常（取消不写半成品）。
4. 逐段失败/空文档/未配置/损坏均有友好提示。
5. `TranslationGranularity` 接口在；`PerParagraph` 实现；`WholeDocument` 预留且文档注明。
6. 打包含 `python-docx`，体积几乎不增。

---

## 14. 后续（不在本 spec 范围）

- PDF 输入/输出。
- 双语对照输出。
- docx 段内 run 级格式保留 + 页眉页脚翻译。
- 整篇翻译策略（B）的实现。
