# 🎬 Local-SRT-Toolkit · 本地高精度字幕工具箱

> **100% 本地离线运行 · 无需任何 API Key · 不付费 · 不上传视频/字幕**
>
> 一个面向**影视/动漫/个人视频创作者**的端到端字幕解决方案：
> **高精度本地语音转录**（保留 哭/笑/叹气/犹豫 等全部语气词）
> + **日文/英文/韩文 → 中文 批量字幕翻译**（场景感知，1:1 时间戳对齐）
>
> 本项目是我的 **第一个 AI 辅助开发（AI Prompt Engineering + AI Code Agent）开源作品**，整个开发流程由 AI 代码助手（Trae）引导完成，包括从模型选型、下载排障、参数调优、Debug 闭环、用户体验打磨的全链路。详见 [`docs/PROJECT_STORY.md`](docs/PROJECT_STORY.md)。

---

## ✨ 核心特性

### 🎙️ ① 高精度本地语音转录（[transcribe.py](transcribe.py)）

- **引擎**：[faster-whisper](https://github.com/guillaumekln/faster-whisper)（基于 [OpenAI Whisper large-v3-turbo](https://github.com/openai/whisper) + [CTranslate2](https://github.com/OpenNMT/CTranslate2) 量化推理，CTranslate2 原生模型）
- **🆕 语气词增强**：通过**场景专用 initial_prompt** + 降 VAD 阈值 + 减轻重复惩罚，完整还原：
  - 笑声 `ははは / ふふっ / クスクス`
  - 哭声 `えーん / ひぃひぃ / すすり泣く`
  - 叹气吐息 `はぁ… / ふぅ… / ふーん`
  - 犹豫停顿 `んー / えっとー / あー`
  - 感叹 `きゃあ / うわぁ / えー！？`
  - 场景音 `ざわざわ… / シーン… / ドキドキ`
- **两档精度模式**：
  - `high`：beam=9, VAD_th=0.32, repetition_penalty=1.08（语气词完整保留，略慢）
  - `normal`：beam=6, VAD_th=0.40（速度精度平衡）
- **自动防"大事なのに"死循环**：temperature 阶梯 + hallucination_silence_threshold=2s 判定幻觉丢弃
- **零配置 GUI 菜单**：Tk 文件夹选择 + 多格式选择（`all` / `1-5` / `1,3,5` / `5!` 强制覆盖）
- **全角字符兼容**：中文输入法下直接输 `5！` / `mode：high` / `１，３` 都能识别，不用切英文键盘

### 🈯 ② 多语言 → 中文 SRT 批量翻译（[translate.py](translate.py)）

- **引擎**：[Facebook NLLB-200 distilled-600M](https://github.com/facebookresearch/fairseq/tree/nllb)（单模型覆盖 200 种语言，**日文/英文/韩文 → 中文**均经过测试）
- **1:1 严格时间戳对齐**：逐条独立翻译，杜绝整段拼接后乱切导致的"源语言字符碎片混入译文"问题
- **中文后处理规范化**：半角→全角标点、去句首多余标点、压缩重复标点、去句内空格
- **输出路径强制独立**：必须选择**不同文件夹**（GUI 校验），绝不覆盖/修改源 SRT
- **断点续翻**：每个 SRT 独立进度文件，中途关掉下次继续，不丢进度；`all!` / `3!` 强制重翻
- **自动源语言检测**：假名比例→日语 / Hangul 比例→韩语 / ASCII 比例→英语
- **逐条进度打点**：翻译过程每 2 条打一个 `·`，不会"假卡死"

### 🧠 模型 & 依赖来源（全部免费 & 开源 & 可离线）

| 模块 | 首次运行自动从国内镜像 `hf-mirror.com` 下载 | 大小 |
|---|---|---|
| 转录：Whisper large-v3-turbo CTranslate2 (int8_float32) | `E:\AI\fw_model\`（可自定义模型路径） | ~1.6 GB |
| 翻译：Facebook NLLB-200 distilled-600M (PyTorch) | `./mt_models/`（相对项目目录） | ~3.1 GB |

下载后永久本地缓存，之后断网也能跑。

---

## 🚀 快速开始（Windows）

### 0. 环境要求

- **Python** 3.10 / 3.11 / 3.12 （安装时勾选 `Add Python to PATH`）
- **推荐 GPU**：NVIDIA GTX 1060 6GB 以上（支持 CUDA 会自动启用，速度比 CPU 快 5~10 倍；没有 GPU 就跑 CPU 模式）
- 硬盘空闲：**转录模型 ~2GB + 翻译模型 ~3GB + 视频 = 至少 10GB**

### 1. 安装依赖（首次一次性）

```bat
REM （可选）推荐建虚拟环境，避免污染全局 Python
py -3 -m venv .venv
.venv\Scripts\activate.bat

REM 安装依赖（使用清华源加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 开始使用

| 双击哪个 .bat | 做什么 |
|---|---|
| **[`start_transcribe.bat`](start_transcribe.bat)** | 🎬 把视频文件转录成 日文/英文 SRT 字幕 |
| **[`start_translate.bat`](start_translate.bat)** | 🈯 把上一步产生的 SRT 翻译成 中文 SRT |

典型工作流：
```
①  start_transcribe.bat → 选视频文件夹 → 产出【日文 SRT】
②  start_translate.bat  → 【源文件夹】选日文 SRT 所在目录
                         → 【输出文件夹】选另一个独立目录
                         → 输入 all → 批量产出【中文 SRT】
```

脚本内置菜单所有交互都有中文提示，格式参考菜单头部。**推荐精度默认 `high`**，如果觉得太慢可以在菜单里输入 `mode=normal` 切换。

---

## ⚙️ 菜单命令速查（两个脚本通用）

| 输入示例 | 含义 |
|---|---|
| `all` | 处理全部（有结果的跳过） |
| `all!` | 全部强制覆盖重跑 |
| `1-5` | 处理第 1 到第 5 个 |
| `1,3,5` | 处理指定编号的 3 个 |
| `5!` | 只处理第 5 个，强制覆盖 |
| `mode=high` / `mode=normal` | 切换转录精度（仅转录脚本） |
| `lang=ja` / `lang=en` / `lang=ko` / `lang=auto` | 切换源语言（两脚本通用） |
| `dir=in` / `dir=out` | 重新选源/输出文件夹（仅翻译脚本） |
| `q` | 退出 |

> 💡 **Tk 文件夹选择对话框被命令行挡住了？** 看到一大排 ★ 提示后按 **Alt+Tab** 切到弹窗即可。

---

## 🙏 致谢（Credits & Acknowledgments）

本项目是**组装与增强**性质的工具包，核心能力完全建立在以下开源作者 / 团队 / 机构的慷慨贡献之上，在此郑重感谢：

### 一、语音转录链路

| 项目 | 作者 / 机构 | 许可证 | 贡献 |
|---|---|---|---|
| [Whisper large-v3-turbo](https://github.com/openai/whisper) | **OpenAI** (Authors: Alec Radford, Jong Wook Kim, Tao Xu, et al.) | MIT | 大规模多语言 ASR 预训练模型；没有它一切都是无源之水 |
| [faster-whisper](https://github.com/guillaumekln/faster-whisper) | **Guillaume Klein (Symanto Research)** | MIT | 把 Whisper 移植到 CTranslate2，推理速度提升 4×，显存减半；Windows 本地能用的核心原因 |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | **OpenNMT 社区 (Guillaume Klein, Max Copperman, et al.)** | MIT | 高效量化 & 推理引擎，支持 int8 / float16 / CPU / CUDA |
| [PyAV](https://github.com/PyAV-Org/PyAV) | **PyAV Org (Mike Boers, Mark Reid, et al.)** | BSD 3-Clause | 直接解码视频音轨给 Whisper，不用先抽 WAV |
| [Silero VAD](https://github.com/snakers4/silero-vad) | **Silero Team** | MIT | 语音活动检测；我们通过阈值调整让它不要误切叹气/抽泣 |

### 二、字幕翻译链路

| 项目 | 作者 / 机构 | 许可证 | 贡献 |
|---|---|---|---|
| [NLLB-200 distilled-600M](https://github.com/facebookresearch/fairseq/tree/nllb) | **Meta AI (Facebook Research) · NLLB Team** (Marta R. Costa-jussà, James Cross, Onur Çelebi, et al.) | MIT | No Language Left Behind - 200 种语言单模型翻译方案；日韩英→中文的本地翻译核心 |
| [SentencePiece](https://github.com/google/sentencepiece) | **Google (Taku Kudo, John Richardson)** | Apache 2.0 | NLLB 使用的 BPE / Unigram 分词 |
| [Hugging Face Transformers](https://github.com/huggingface/transformers) | **Hugging Face Inc. + 1500+ Community Contributors** | Apache 2.0 | NLLB Tokenizer + Seq2Seq 推理框架，加载/缓存/生成流水线 |
| [PyTorch](https://github.com/pytorch/pytorch) | **PyTorch Foundation (Meta, NVIDIA, Google, Microsoft, Amazon, et al.)** | BSD 3-Clause | 翻译模型的 GPU/CPU 张量后端 |
| [hf-mirror.com](https://hf-mirror.com) | 国内社区镜像站 | — | 让国内网络能顺利下载 Hugging Face 模型，不用挂代理 |

### 三、开发方式

- **本项目的开发由 AI 代码助手（Trae，基于大语言模型）全程辅助完成**。
- 人类开发者（我）的工作集中在：**明确需求边界** → **用自然语言 Prompt 引导选型 / 参数调优 / Debug 方向** → **人工验收运行结果** → **人工做最终质量判断**。详细过程参见 [`docs/PROJECT_STORY.md`](docs/PROJECT_STORY.md)。

---

## 📜 License

本项目代码在 [MIT License](LICENSE) 下开源。
*使用的第三方模型各自有独立许可证：*
- Whisper 系列模型：MIT License
- NLLB-200 模型权重：MIT License (Meta)
- CTranslate2 & faster-whisper 代码：MIT License
- Hugging Face Transformers & Tokenizers：Apache License 2.0

请在分发 / 二次创作 / 商业使用时完整保留各组件的版权声明与 License 文本。

---

## 🗂️ 项目文件总览

```
Local-SRT-Toolkit/
├── LICENSE              MIT 开源许可证
├── README.md            你正在看的这个文件 ←
├── requirements.txt     pip 依赖列表
├── .gitignore           严格忽略大模型缓存/字幕产出物 (防止误传 GitHub)
│
├── transcribe.py        🎬 高精度本地语音转录 ( faster-whisper + 语气词增强 )
├── start_transcribe.bat 双击启动转录
│
├── translate.py         🈯 多语言 SRT → 中文翻译 ( NLLB-200 )
├── start_translate.bat  双击启动翻译
│
└── docs/
    └── PROJECT_STORY.md 🧑‍💻 我的第一个 AI 辅助开发作品完整开发故事
```

---

## 🐛 常见问题（FAQ）

**Q1：第一次启动显示「正在下载模型」很慢？**
A：正常。首次会从 `hf-mirror.com` 下载合计约 4.7GB 的模型文件，国内镜像速度通常 2–20 MB/s。下载完永久保存在本地，之后离线可用。可挂在后台睡觉。

**Q2：文件夹选择弹窗没出现？**
A：被命令行窗口挡住了。看到 ★ 大字提示后按 **Alt+Tab** 切窗口即可。

**Q3：翻译出来的中文还是怪怪的？**
A：先看源头——**日文 SRT 本身有没有语气词**。如果转录缺字翻译一定不准。请把转录精度设回 `mode=high`，用 `all!` 强制重转字幕源，再跑翻译。

**Q4：我只有 6GB 显存跑得动吗？**
A：完全可以，这就是作者本人的显卡配置（GTX 1060 6GB）。转录走 `int8_float32` compute_type，翻译走 `fp16`（自动回退 CPU）都能跑。

**Q5：字幕产出物能传 GitHub 吗？**
A：**强烈建议不要！** 视频 / 产生的 SRT 可能受版权保护。`.gitignore` 里已经严格排除了所有 *.srt / *.bin / *.safetensors，只要不改这个配置就不会误传。
