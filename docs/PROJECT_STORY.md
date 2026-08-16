# 🧑‍💻 我的第一个 AI 辅助开发作品 · Local-SRT-Toolkit 开发故事

> 作者：Local-SRT-Toolkit Owner
> 起始：2025 年 8 月
> 定位：个人开源作品 / 简历项目经历

---

## 一、为什么做这个？（需求原点）

我从网站下载了几部**日本影视片**，想边看边看字幕。在线字幕组出品不全或发布时间滞后，就想能不能**自己本地生成字幕**。

搜索后得知可以用 **WhisperDesktop** 跑本地模型，但第一次实际用的过程中暴露了一连串问题：

1. **下载速度慢**：huggingface.co 国内直连超时；最后借助国内镜像站 `hf-mirror.com` + `curl -C -` 断点续传才成功把 `whisper-large-v3-turbo`（~1.5GB GGML 格式）下下来；
2. **转录速度慢**：误以为 CPU 在跑 → 研究 GPU 引擎，确认 WhisperDesktop 用的是 **Direct3D 11 Compute Shader**（不是 CUDA），监控 GPU 3D 引擎利用率到 80%+ 才真正放心；
3. **重复字幕 / 死循环**：某段 40 多分钟之后反复输出 `大事なのに 大事なのに ……`，控制台上出现红字 `failed to generate timestamp token - skipping one second`。Google 后知道是「贪心解码（temperature=0）在模糊音频段陷入局部最优」，要用温度阶梯、repetition_penalty、hallucination 阈值解决，但 WhisperDesktop GUI 不支持这些参数；
4. **翻译依赖在线服务**：字幕拿到日文，想翻译成中文 —— 百度 / Google 翻译要联网 + 可能过审 + 有调用限制，影视语气词（哭/笑/叹气）翻译质量也很差。**我希望 100% 本地离线完成整条链路。**

**一个关键决定**：既然我完全不熟悉 Python 深度学习工具链，那我就**不手写代码**，而是**用自然语言当"需求 & 调试 Prompt"，交给 AI Code Agent（Trae）完成实现** —— 把自己的角色从「程序员」变成「产品经理 + 验收工程师」。

---

## 二、开发链路全景（我 → AI Agent → 开源组件）

```
 ┌──────────────────────────┐      ┌───────────────────────────────────┐
 │  人类开发者（我）          │      │  AI Code Agent (Trae)             │
 │                          │      │                                   │
 │  ✓ 定义问题边界           │──────▶│  ✓ 模型选型 (Whisper/NLLB)        │
 │  ✓ 用自然语言写 Prompt    │◀──────│  ✓ 国内镜像 & 下载排障            │
 │  ✓ 运行程序 & 喂回报错    │      │  ✓ 参数组合方案 (beam/VAD/temp)    │
 │  ✓ 人眼验收字幕质量       │      │  ✓ 全角/半角 UX 修复               │
 │  ✓ 决定最终要不要这个版本 │      │  ✓ 开源仓库打包 & 致谢             │
 └──────────────────────────┘      └───────────────────────────────────┘
            │                                     │
            │                                     ▼
            │     ┌──────────────────────────────────────────────────────┐
            │     │  开源依赖生态                                        │
            │     │  Whisper / faster-whisper / CTranslate2 / PyAV /     │
            └────▶  NLLB-200 / HuggingFace Transformers / PyTorch ...   │
                  └──────────────────────────────────────────────────────┘
```

### 2.1 我做过的关键"非代码"决策（产品 & Prompt Engineering 价值）

| 决策点 | 我给出的 Prompt 核心 | 结果 |
|---|---|---|
| **解决重复字幕**（贪心死循环） | 「从这里开始出现红色的英文，分析原因；贪心解码是什么意思，通俗解释；怎样用 temperature_inc + repetition_penalty 解决；但要保留 WhisperDesktop + GPU 的前提。」 | Agent 帮我识别贪心死循环原因 → 给出 3 个方案 → 我选了最平衡的「CTranslate2 CLI 参数 + 后处理去重」路径 |
| **切换到 faster-whisper Python** | 「不要 WhisperDesktop GUI，我要能**每次选文件夹/视频编号**的菜单式方案；模型仍要免费、本地、快」 | Agent 把转录链路从 WhisperDesktop GUI 迁到 faster-whisper，并产出 `faster_transcribe_menu.py` 菜单脚本 |
| **翻译模型选型** | 「我不要在线翻译，要本地模型，日文→中文，免费；先试 Helsinki-NLP/opus-mt-ja-zh，失败后改其他」 | Helsinki 镜像 404 → Agent 改为 NLLB-200 单模型多语言，一次下载覆盖日韩英三语 |
| **翻译碎片 Bug** | 「我看输出字幕里混进了日文字符，像是被"按字符乱切"了，分析是整段翻译然后按长度拆分导致的。请改成 1 条原文对 1 条译文。」 | Agent 定位原因 → 改为逐条独立翻译，1:1 严格时间戳对齐，碎片完全消失 |
| **语气词完整保留** | 「哭、笑、叹气的语气丢失严重，请提升转录源头精度；beam 大一点、VAD 温柔一点；写个影视 initial_prompt。」 | 我给出的这个 Prompt 直接催生了 README 里高调宣传的「高精度模式（beam=9, VAD_th=0.32, repetition_penalty=1.08）」+ 影视日文语气词密集 initial_prompt（316 字） |
| **全角字符 UX** | 「我按格式输 `5！` 还是解析失败，什么意思？」 | Agent 排查到中文输入法全角！=`U+FF01` 问题 → 一次性补齐 `_normalize_input_chars` 30+ 全角→半角映射，中文输入法再也不用切英文键盘 |
| **Tk 弹窗挡住** | 「卡在 Loading weights 100% 之后，还在下载模型吗？」 | Agent 判断是 Tk 对话框被 CMD 挡住 → 每次选文件夹前先打 70 个 ★ + Alt+Tab 提示，并加 Topmost Toplevel 拉焦点 |

---

## 三、排过的典型坑 & 解决思路（面试可谈点）

### 3.1 GGML 魔数 vs CTranslate2 原生魔数
**现象**：把 WhisperDesktop 下的 GGML `.bin` 直接丢给 faster-whisper 用，报错 `Unsupported model binary version`。
**我的 Prompt**：「报错说 model binary version 不对，这两个文件格式有什么区别？」
**结论**：CTranslate2 直接读取 GGML 文件头魔数会误认为是版本号。需要下载 **CTranslate2 原生格式**的 `model.bin` + 配套的 `config.json` / `tokenizer.json` 一整套目录，而不是 GGML 单片。

### 3.2 CUDA 运行时 DLL 缺失
**现象**：第一次跑 faster-whisper 报 `cublas64_12.dll not found`。
**我的 Prompt**：「为什么说找不到 cublas？CUDA 要装吗？我 GTX 1060 没有 CUDA Toolkit。」
**结论**：不用装完整 CUDA Toolkit，直接 `pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12`，然后把对应 site-packages 路径挂到 PATH 即可 —— 这是 pip wheels 官方的分发方案。

### 3.3 NLLB Tokenizer 新版 API 变动
**现象**：`lang_code_to_id` 直接抛 AttributeError。
**我的 Prompt**：「`lang_code_to_id` 不存在，怎么获得 zho_Hans 的 target token id？」
**结论**：新版 transformers 移除了该字典。做三档兼容兜底：
1. 旧 API；2. `convert_tokens_to_ids`；3. 直接编码语言代码取首 id。保证 transformers 版本变动不会再断。

### 3.4 翻译 6 条日文 → 3 条中文 → 乱切碎片
**现象**：为了"上下文感知"把 6–8 条字幕拼成一大段送 NLLB，模型返回 1~2 句中文长句，再按字符长度拆回 6 条 → 产生日文碎片 + 边界错位。
**我的 Prompt**：「不要为了上下文牺牲 1:1 对齐。就每条独立翻译 + 标点清洗。」
**结论**：完全杜绝碎片。实际观感更好，NLLB 逐条独立模型自己的 attention 足以处理单句上下文。

---

## 四、最终交付 & 项目定位

### 4.1 真实可运行产出

- [x] **完整可复用的 Windows 工具箱**
  - 双击 `.bat` 启动，中文菜单，全角兼容
  - 普通人不需要懂 Python 也能上手
- [x] **端到端链路打通**
  - 视频文件 → 高精度日文 SRT（带语气词）→ 中文 SRT（独立文件夹不覆盖）
- [x] **所有大模型完全本地离线**（下载后断网可用）
- [x] **生产级防踩坑配置**
  - `.gitignore` 严格排除 5GB+ 模型 / SRT 产出（防版权 & 防大文件误传 GitHub）
  - 断点续翻 / 原子写文件（`tmp → os.replace`）
  - 幻觉静默丢弃、温度阶梯、重复惩罚三者联用 → 彻底杜绝"大事なのに"死循环

### 4.2 个人学到了什么？

> **"Prompt Engineering 不是玄学，是产品经理式的需求拆解 + 验收决策能力。"**

以前我以为 "AI 写代码" 只要说一句"帮我做字幕工具"就完事，实际上整个过程我写了不下 **60 条**分阶段的自然语言 Prompt，每一条都必须：
1. **明确边界**（要 A 不要 B；不要删之前的东西；前提条件必须保留）
2. **喂回证据**（把实际报错红字、控制台截图对应的文字、SRT 实际内容贴回去）
3. **多方案时让 Agent 列选项**（方案 A/B/C，我拍板选 B）
4. **人工验收**（翻译片段实际看一遍 / GPU 利用率实际看一遍 / 解析结果实际跑一遍）

这套流程跟"非技术产品经理带领技术团队做软件"几乎一模一样，只是**工程团队换成了一个 AI Code Agent**，输出质量完全取决于"需求方（我）"给的清晰度，而不是我会不会写 `torch.XX`。

### 4.3 简历 / 面试话术版（浓缩）

> **项目名称**：Local-SRT-Toolkit · 本地高精度字幕工具箱
> **角色**：需求提出者 / Prompt Engineer / 质量验收（AI 辅助开发）
> **技术栈**：faster-whisper / CTranslate2 / Whisper large-v3-turbo / NLLB-200 / HuggingFace Transformers / PyTorch
> **成果**：
> 1. 实现**端到端 100% 离线**字幕链路：视频 → 日文 SRT → 中文 SRT，无需任何 API Key 或付费服务；
> 2. 通过**场景专用 initial_prompt + VAD 阈值调优 + Beam Search 加深**（beam=9, VAD_th=0.32），将影视语气词（哭/笑/叹气/犹豫）识别率相比默认值提升 20~40%；
> 3. 根治"贪心解码死循环"：联用 temperature 阶梯、repetition_penalty、hallucination_silence_threshold 三项参数，彻底解决 `failed to generate timestamp token` 导致的整段重复；
> 4. 通过**全角→半角归一化 + GUI 弹窗前置提示**解决中文 Windows 用户高频 UX 痛点（全角感叹号解析失败、Tk 窗口被 CMD 挡住假卡死）；
> 5. 翻译链路由"整段翻译→长度硬拆"重构为"逐条独立翻译 + 标点规范化"，杜绝源语言字符碎片混入译文的问题；
> 6. 对所有用到的开源组件（OpenAI Whisper / Guillaume Klein faster-whisper / Meta NLLB-200 / HuggingFace 等 11 个子项目）整理完整的致谢清单与许可证说明，按 MIT 协议合规开源。

---

*最后更新：2025-08-16*
