# LLMTranslator — 跨平台大模型桌面翻译软件

基于大语言模型的桌面翻译客户端，界面参考百度翻译。支持 OpenAI 兼容付费 API（DeepSeek / 智谱 GLM / OpenAI）与智谱清言 / Kimi / DeepSeek 网页免费逆向接入。

## 功能
- 文本翻译，流式输出（打字机效果）
- 翻译历史记录（搜索/清空）
- 多模型配置：付费 API（填 Key）+ 网页免费（内嵌登录）
- TTS 朗读：原文/译文各一个 🔊 按钮，点击朗读（在线）
- 划词翻译：任意程序选中文字 → Ctrl+Shift+T → 光标处弹译文明信片（可复制/展开到主窗口）
- 截图 OCR：Ctrl+Shift+O 截图选区 → RapidOCR 识别 → 翻译（原地覆盖 / 对照 / 直接翻译三种模式）
- 文档翻译：菜单 → 文档翻译… → 选 .docx/.txt → 逐段翻译保留段落结构 → 输出同格式译文
- Windows 一键安装

## 开发环境
```bash
python -m pip install -e ".[dev]"
pytest -v                      # 运行测试
python -m llm_translator.main  # 启动
```

## 打包
```bash
pyinstaller build.spec --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```
产物：`installer_output/LLMTranslator-Setup-0.2.0.exe`（双击即装）。

## 首次使用
1. 安装后启动，点右上角 ☰ 设置。
2. 付费 API：填 Base URL + API Key + 模型名 → 测试连接。
3. 网页免费：点登录，在内嵌网页完成登录，自动抓取凭据。
4. 回主界面选模型，输入文本，Ctrl+Enter 翻译。

## TTS 朗读（在线）
TTS 朗读当前仅支持在线（使用 `edge-tts` / 微软语音），需要联网。代码已预留 `TtsEngine` 接口，后续版本将加入离线语音引擎（如 Windows 系统 SAPI）。

## 划词翻译
全局热键 `Ctrl+Shift+T`（可在主菜单 ☰ 开关）。取词通过模拟 `Ctrl+C` 读取选中文字，**触发后会自动恢复你原有的剪贴板内容**（文本/图片）。依赖 `keyboard` 库（低级键盘钩子，极少数杀毒可能误报，自用项目可加白名单）。

## 截图 OCR
全局热键 `Ctrl+Shift+O`（可在主菜单 ☰ 开关）。使用 `RapidOCR`（ONNX 离线引擎）识别截图中的文字 + 坐标，再用翻译模型译。三种结果模式：原地覆盖（译文贴在原文位置）、对照（上方同尺寸译文画布 + 下方原图）、直接翻译（面板显示原文 + 译文）。依赖 `onnxruntime` + `rapidocr-onnxruntime`（~80-120MB，首次 OCR 有模型加载耗时 ~1-2s）。

## 文档翻译
菜单 → 文档翻译… → 选择 `.docx` 或 `.txt` 文件 → 逐段并发翻译 → 输出同格式译文（同目录 + `_目标语言` 后缀）。docx 保留段落结构/样式（段内 run 级格式为已知边界）。预留 `WholeDocumentGranularity` 整篇翻译接口（方案 B），后续实现。

## 声明
网页逆向接入仅供个人学习使用，可能违反各服务条款且接口随时可能失效。凭据本地加密存储（Fernet，机器特征派生密钥）。
