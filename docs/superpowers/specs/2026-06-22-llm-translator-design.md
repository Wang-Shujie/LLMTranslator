# 多系统通用桌面级大模型翻译软件 — 设计文档

- **日期**：2026-06-22
- **状态**：待用户评审
- **作者**：与用户共同头脑风暴产出

---

## 1. 概述（Overview）

从零开发一个跨平台桌面翻译软件，使用大语言模型（LLM）作为翻译引擎。界面参考百度翻译客户端的布局风格。支持多种模型接入：付费 API（OpenAI 兼容协议）和免费网页版逆向接入。

### 1.1 核心需求

1. **一键安装**：Windows 上双击安装包即用，无需配置环境；同时提供免安装绿色版。
2. **方便配置**：图形化配置界面，统一管理付费 API（填 Key）和免费网页模型（内嵌登录抓 Cookie）。
3. **图形化界面**：参考百度翻译客户端，浅色主题、上下堆叠的输入/输出双栏、顶部语言切换栏。

### 1.2 目标用户

仅本人及少量朋友使用。**非公开商业分发**——因此不做代码签名、自动更新、官网分发等。

### 1.3 MVP 功能范围

| 功能 | MVP | 后续版本 |
|---|---|---|
| 文本翻译（输入即译） | ✅ | — |
| 流式输出（打字机效果） | ✅ | — |
| 翻译历史记录 | ✅ | — |
| 付费 API（OpenAI/DeepSeek/GLM，OpenAI 兼容） | ✅ | — |
| 免费网页逆向（智谱清言/Kimi/DeepSeek 网页版） | ✅ | — |
| Claude API | — | ✅ |
| 术语表 / 提示词模板 | — | ✅ |
| 多模型对比翻译 | — | ✅ |
| 全局快捷键 / 常驻置顶小窗 | — | ✅ |
| 划词翻译、文档翻译、截图 OCR、TTS 朗读 | — | ✅（或暂不做） |

> 参考图底部栏（AI 同传/文档翻译/截图翻译/划译）属于 MVP 之外功能，本版本不做。

---

## 2. 非目标（Non-Goals，YAGNI）

明确**不在**本版本范围内，避免范围蔓延：

- 代码签名 / macOS 公证 / 自动更新 / 官网分发
- 划词翻译、文档翻译、截图 OCR（需全局钩子/OCR，复杂度高）
- 多账号、云同步、团队协作
- 移动端

---

## 3. 技术栈决策

**选定方案：Python + PySide6（Qt）+ PyInstaller。**

| 候选 | 界面打磨 | 逆向生态 | 打包 | 结论 |
|---|---|---|---|---|
| Electron (Node) | ★★★★★ | ★★★★ | ★★★★ | 备选 |
| Tauri (Rust) | ★★★★ | ★★（迭代慢） | ★★★★★ | 不选（逆向迭代差） |
| **Python + PySide6** | ★★★ | ★★★★★（`curl_cffi`） | ★★★ | **选定** |

**选定理由**：本项目的核心痛点是网页逆向（必须频繁迭代、绕过 Cloudflare），Python 的 `curl_cffi` 在 TLS 指纹伪装上几乎无敌，且国内 LLM 逆向社区代码绝大多数是 Python，遇到问题最好查。界面虽不如 Web 灵活，但 PySide6 + QSS 足以还原参考图的标准表单式布局。用户接受"界面尽量接近示例即可"。

**最终依赖清单**：

```
PySide6              # GUI 框架
qasync               # asyncio 与 Qt 事件循环共存
httpx                # HTTP 客户端（普通请求）
curl_cffi            # HTTP 客户端（TLS 指纹伪装，绕 WAF）
QWebEngineView       # 内嵌网页登录（PySide6-Essentials 之外需 PySide6-Addons）
cryptography         # 凭据加密（Fernet）
platformdirs         # 跨平台用户数据目录
sqlite3              # 历史存储（Python 内置）
pytest               # 测试
pytest-asyncio       # 异步测试
PyInstaller          # 打包
Inno Setup           # Windows 安装器（外部工具）
```

---

## 4. 架构设计

### 4.1 核心思想：适配器模式（Adapter Pattern）

这是应对"网页逆向随时失效"的关键设计。所有模型（无论付费 API 还是网页逆向）都实现**同一个接口**，互相隔离：一家失效不影响其他家，修一家 = 改一个文件。

### 4.2 分层架构

```
┌─────────────────────────────────────┐
│  UI 层 (PySide6)                     │  主窗口、设置对话框、语言栏、流式渲染
├─────────────────────────────────────┤
│  核心编排层 (core)                    │  Translator：拼 prompt → 调 provider → 流式回传
├──────────────┬──────────────────────┤
│ Providers 适配层                     │
│ ├─ api/      │ OpenAI/DeepSeek/GLM  │  付费 API（OpenAI 兼容协议，一套通吃）
│ ├─ anthropic │ Claude（后续）        │
│ └─ web/      │ GLM/Kimi/DeepSeek网页 │  免费逆向（各自独立，curl_cffi）
├──────────────┴──────────────────────┤
│  Auth 凭据层                          │  API Key + Web Cookie/Token 的存储/校验/刷新
├─────────────────────────────────────┤
│  Storage 层                          │  历史(SQLite)、设置(JSON)、凭据(加密)
└─────────────────────────────────────┘
```

### 4.3 项目目录结构

```
llm-translator/
├── src/llm_translator/
│   ├── main.py                 # 入口，QApplication
│   ├── ui/                     # PySide6 视图
│   │   ├── main_window.py      # 主窗口
│   │   ├── settings_dialog.py  # 设置对话框
│   │   ├── widgets/            # 语言栏、文本面板、状态栏等
│   │   └── login_dialog.py     # 内嵌网页登录
│   ├── core/                   # 业务逻辑
│   │   ├── translator.py       # 翻译编排
│   │   ├── prompt.py           # 翻译 prompt 构建
│   │   └── language.py         # 语言码与名称映射
│   ├── providers/              # 适配层（关键）
│   │   ├── base.py             # BaseProvider 抽象接口
│   │   ├── registry.py         # provider id → 适配器 + 默认配置
│   │   ├── api/
│   │   │   └── openai_compat.py# OpenAI 兼容（通吃 DeepSeek/GLM/OpenAI）
│   │   ├── anthropic.py        # Claude（后续）
│   │   └── web/
│   │       ├── glm.py          # 智谱清言逆向
│   │       ├── kimi.py         # Kimi 逆向
│   │       └── deepseek.py     # DeepSeek 网页逆向
│   ├── auth/                   # 凭据/Cookie 管理
│   │   ├── store.py            # 加密存取
│   │   └── login.py            # 网页登录抓 Cookie
│   ├── storage/                # 持久化
│   │   ├── history.py          # SQLite 历史
│   │   └── settings.py         # JSON 设置
│   └── utils/
├── assets/
│   ├── light.qss               # 浅色主题样式表
│   └── icons/                  # 图标
├── tests/
├── build.spec                  # PyInstaller 配置
├── installer.iss               # Inno Setup 安装器脚本
├── pyproject.toml
└── README.md
```

### 4.4 异步与流式桥接

PySide6 的事件循环与 asyncio 通过 **`qasync`** 共存。Provider 在 asyncio 里产出 token，通过 **Qt 信号** 投递到主线程渲染，避免 UI 卡顿。

---

## 5. 模型接入层（Providers）

### 5.1 统一接口（`providers/base.py`）

```python
class BaseProvider(ABC):
    name: str
    kind: str                      # "api" | "web"

    @abstractmethod
    async def login(self) -> None:
        """API: 校验 Key；Web: 校验/刷新 Cookie。失败抛 AuthError。"""

    @abstractmethod
    async def translate(self, text: str, src: str, tgt: str) -> AsyncGenerator[str, None]:
        """异步生成器：逐个 yield token，驱动 UI 打字机效果。用法见第 7 节 `async for token in provider.translate(...)`。"""

    @abstractmethod
    def health(self) -> bool:
        """当前登录态/连接是否有效。"""
```

UI 与编排层只依赖此接口，**不感知**背后是 API 还是网页逆向。

### 5.2 付费 API（`providers/api/openai_compat.py`）

关键简化：**OpenAI 兼容协议是事实标准**。DeepSeek、智谱 GLM、OpenAI、硅基流动、OpenRouter 均走 `/v1/chat/completions`。

- 只写**一个** `OpenAICompatProvider` 类，由 `base_url` + `api_key` + `model` 参数化。
- 内置预设：DeepSeek API / 智谱 GLM API / OpenAI；另支持"自定义"填任意兼容地址。
- 流式：`stream: true` → SSE，逐行解析 `data:` chunk → yield `delta.content`；遇 `[DONE]` 终止。

### 5.3 免费网页逆向（`providers/web/`）

每家接口各异，**各自一个文件**，完全隔离：

| 文件 | 目标 | 要点 |
|---|---|---|
| `glm.py` | chatglm.cn（智谱清言） | 抓登录后 token，调内部 chat 接口，SSE 流式 |
| `kimi.py` | kimi.moonshot.cn | 用 access_token 调内部接口，SSE 流式 |
| `deepseek.py` | chat.deepseek.com | user token + device id，SSE 流式 |

- 全部使用 **`curl_cffi`**（TLS 指纹伪装，绕 Cloudflare/WAF），`httpx` 兜底。
- 登录态/Cookie 刷新逻辑放在 `auth/`（见第 6 节）。
- **隔离原则**：某家失效 → 抛 `ProviderUnavailable` → UI 提示"X 不可用，请重新登录或换其他模型"，其他家照常工作。修复 = 仅改对应单文件。

> **风险声明**：网页逆向通常违反各家服务条款，且接口随时变更、可能失效。仅供个人/学习用途，不公开商业分发。

### 5.4 Provider 注册表（`providers/registry.py`）

集中登记"provider id → 适配器类 + 默认配置"，设置界面左侧列表从此生成。**新增一家模型 = 加一条登记 +（若网页类）一个适配器文件**，其余代码不动。

```python
registry = {
    "deepseek-api":  (OpenAICompatProvider, {"preset": "deepseek"}),
    "glm-api":       (OpenAICompatProvider, {"preset": "glm"}),
    "openai":        (OpenAICompatProvider, {"preset": "openai"}),
    "glm-web":       (GlmWebProvider,       {}),
    "kimi-web":      (KimiWebProvider,      {}),
    "deepseek-web":  (DeepSeekWebProvider,  {}),
}
```

---

## 6. Auth 凭据层（`auth/`）

解决网页逆向的登录态问题，并安全存储所有凭据。

- **加密存储**：所有 API Key 与 Web Cookie/Token 用 `cryptography`（Fernet）加密后存本地 `secrets.enc`，密钥由机器特征派生——防止"复制配置文件即可读到明文凭据"。
- **网页登录流程**：设置界面点「登录」→ 弹出 `QWebEngineView` 加载官网登录页 → 用户正常登录（账号/扫码）→ 拦截响应中的 Cookie/Token → 加密存储。下次启动自动加载，过期则提示重新登录。
- **健康检查**：`health()` 在翻译前（或定期）校验登录态；失效则 UI 红点 + "请重新登录"。

---

## 7. 翻译流程（`core/translator.py`）

```
用户输入文本 + Ctrl+Enter（或点「翻译」按钮）
 → Translator.translate(text, src, tgt)
   → prompt.build(text, src, tgt)          # 构造翻译 prompt
   → registry.get(current_provider)        # 取当前选中 provider
   → await provider.login()                # 若需要
   → async for token in provider.translate(text, src, tgt):
       signal.token_received.emit(token)   # Qt 信号推主线程逐字渲染
   → history.add(...)                      # 完成后存历史
```

**Prompt 构建约束**（`core/prompt.py`）：只输出译文、不加解释、保留换行与格式：

```
You are a professional translator. Translate the following text from {src} to {tgt}.
Output ONLY the translation. Do not add any explanation or notes.
Preserve original formatting and line breaks.

Text:
{text}
```

---

## 8. 界面设计（`ui/`）

### 8.1 主窗口布局（对照参考图，适配 LLM 文本翻译）

垂直单栏布局：

```
┌──────────────────────────────────────────────────────┐
│ 顶部栏 (TopBar, ~40px)                                │
│ [中文(简体) ▼]  [⇄交换]  [英语 ▼]    [DeepSeek API ▼]  [☰]│
├──────────────────────────────────────────────────────┤
│ 源文本输入区（上半）                                   │
│  ┌──────────────────────────────────────┐  [✕清空]   │
│  │ （白色圆角输入框，边框 #e0e0e0）       │            │
│  └──────────────────────────────────────┘            │
│   字数: 0                              [翻译 ➤ Ctrl+Enter]│
├───────── 流式输出时显示加载动画 ──────────────────────┤
│ 译文输出区（下半，只读）                               │
│  ┌──────────────────────────────────────┐ [📋复制]   │
│  │ （译文逐字出现，打字机效果）           │ [🔊朗读]   │
│  └──────────────────────────────────────┘            │
├──────────────────────────────────────────────────────┤
│ 状态栏: ● DeepSeek API 已连接 | 耗时 1.2s | 287 字     │
└──────────────────────────────────────────────────────┘
```

- 词典参考图的音标/释义标签页是单词查询特有，LLM 文本翻译改成**纯译文输出 + 复制/朗读工具栏**。
- 参考图底部栏（AI 同传等）属于后续功能，本版本留空。

### 8.2 配色（`assets/light.qss`，对齐参考图）

| 用途 | 色值 |
|---|---|
| 主背景 | `#ffffff` |
| 面板/顶栏/底栏 | `#f8f8f8` |
| 主文字 | `#000000` |
| 次文字 | `#666666` |
| 强调蓝（按钮/激活态/链接） | `#1890ff` |
| 边框 | `#e0e0e0` |
| 圆角 | `8px` |

### 8.3 设置对话框（需求 #2「方便配置」的核心）

```
┌─ 设置 ───────────────────────────────────┐
│ 左侧 Provider 列表          右侧详情面板   │
│ ┌──────────────┐ ┌──────────────────────┐│
│ │ ▸ DeepSeek API│ │ Base URL: __________ ││
│ │   智谱 GLM API│ │ API Key:  __________ ││
│ │   OpenAI      │ │ 模型名:   __________ ││
│ │ ── 网页免费 ──│ │ [测试连接]  ●已连接  ││
│ │   智谱清言    │ │                      ││
│ │   Kimi        │ │ （网页类显示：）     ││
│ │   DeepSeek网页│ │ 状态: ●未登录        ││
│ └──────────────┘ │ [登录] (弹网页登录)  ││
│                  └──────────────────────┘│
│ 通用：默认模型 [▼]  默认语言对 [▼]  字号  │
└──────────────────────────────────────────┘
```

- **付费 API**：填 Base URL + API Key + 模型名 → 「测试连接」校验。
- **网页免费**：点「登录」→ 弹 `QWebEngineView` 正常登录 → 自动抓 Cookie。
- 每个 provider 独立启用/禁用开关。
- 菜单 [☰]：历史记录 / 设置 / 关于。

---

## 9. 数据存储（`storage/`）

| 数据 | 方式 | 位置 |
|---|---|---|
| 历史记录 | SQLite（`translations(id, timestamp, src, tgt, source_text, target_text, provider)`，可分页/搜索/清空） | `%APPDATA%/LLMTranslator/history.db` |
| 设置 | JSON（语言对、默认 provider、字号、各 provider 启用状态） | `settings.json` |
| 凭据 | 加密（Fernet） | `secrets.enc` |

路径用 `platformdirs` 处理跨平台（Windows `%APPDATA%`，macOS `~/Library/Application Support`，Linux `~/.local/share`）。

---

## 10. 错误处理

| 场景 | 处理 |
|---|---|
| 单家 Provider 失效 | 抛 `ProviderUnavailable`，UI 提示并隔离，不影响其他家 |
| 网络超时/断连 | 友好提示 + 自动重试一次 |
| 流式中断 | 保留已显示的部分译文，提示"连接中断，已显示部分结果" |
| 登录失效（401/403） | 捕获并提示"请重新登录" |
| Provider 未配置/未登录 | 「翻译」按钮禁用并提示原因 |

---

## 11. 打包（需求 #1 一键安装）

- **PyInstaller**（`build.spec`）：
  - 主推 `--onedir`（启动快、调试方便）绿色版 + `--onefile` 单 exe 两种产物。
  - **已知难点**：`curl_cffi`（动态库 + ctypes）与 `QWebEngineView`（PySide6-Addons，大量二进制资源）是 PyInstaller 打包的高频坑，在 spec 里显式声明 `hiddenimports` / `binaries` / `datas`。
- **Windows 安装器**：用 **Inno Setup**（`installer.iss`）把绿色目录封装成 exe 安装包，含桌面快捷方式与开始菜单项，双击即装。同步提供免安装绿色版（zip）。
- **不做**代码签名（自用，方案 A 已定；未签名首次启动需在 SmartScreen 点"仍要运行"）。

---

## 12. 测试策略

| 层级 | 方法 |
|---|---|
| 单元测试（pytest） | `core/prompt.py`、`core/language.py`、`storage/history.py`、`storage/settings.py` |
| OpenAI 兼容流式解析 | 注入 mock SSE 响应，验证 `delta.content` 逐 token yield、`[DONE]` 终止 |
| Provider 契约测试 | 每个 provider 注入 fake HTTP 层，验证 `login()` / `translate()` / `health()` 行为符合 `BaseProvider` 契约 |
| 网页逆向适配器 | **录像 fixture**：录一次真实响应存为文件，回放测试解析逻辑；真实连通性靠手动验证 |
| 集成测试 | `Translator` 端到端（mock provider）验证流式信号投递、历史写入 |
| UI | 对照参考图的手动验收清单（布局、配色、交互） |

---

## 13. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 网页接口随时变更/失效 | 高（核心功能） | 适配器隔离 + 单文件修复；多 provider 冗余；录像 fixture 保护解析逻辑 |
| 网页逆向违反 ToS | 中 | 仅供个人/学习，不公开分发（方案 A 已定） |
| PyInstaller 打包 curl_cffi/QWebEngine 失败 | 中 | spec 显式声明依赖，预留调试时间，优先验证最小可打包骨架 |
| 未签名被 SmartScreen 拦截 | 低 | 用户手动"仍要运行"；README 说明 |
| 凭据安全 | 中 | Fernet 加密 + 机器特征派生密钥 |

---

## 14. 验收标准（MVP）

1. 在 Windows 双击安装包可一键安装并启动，无需额外配置环境。
2. 启动后界面布局/配色接近参考图（顶部语言栏 + 上下输入输出双栏 + 浅色蓝点缀）。
3. 在设置界面填入 OpenAI 兼容 API Key（如 DeepSeek），点「测试连接」显示已连接，可成功翻译并流式输出。
4. 在设置界面登录智谱清言/Kimi/DeepSeek 网页版之一，可成功翻译并流式输出。
5. 译文可复制；翻译历史可查看/搜索/清空。
6. 单家 provider 失效时，UI 提示且其他 provider 仍可用。
7. 凭据在本地加密存储，重启后保持登录态。

---

## 15. 后续版本（不在本 spec 实现范围）

- Claude API 适配器（`providers/anthropic.py`）
- 术语表 / 提示词模板
- 多模型对比翻译（并排译文）
- 全局快捷键 / 常驻置顶小窗
- 划词翻译、文档翻译、截图 OCR、TTS 朗读
