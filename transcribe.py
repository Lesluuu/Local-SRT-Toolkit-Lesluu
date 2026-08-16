"""
本地视频批量字幕转录 - faster-whisper + CUDA
启动方式: 双击 start_transcribe.bat
"""
import os
import sys
import uuid
import time
import shutil
import traceback
from pathlib import Path

# --- 国内 HuggingFace 镜像 (必须在 import transformers/huggingface_hub 之前设置) ---
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

# --- 兼容旧版 fwenv 和新版 venv 两种虚拟环境 ---
_SCRIPT_DIR = Path(__file__).resolve().parent
for _env_name in ("venv", "fwenv", ".venv"):
    _env_path = _SCRIPT_DIR / _env_name
    if (_env_path / "Lib" / "site-packages").exists():
        sys.path.insert(0, str(_env_path / "Lib" / "site-packages"))
        _bin = _env_path / "Scripts"
        if _bin.exists():
            os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")
        break

# --- Windows DLL 路径注册 (CUDA / cuBLAS / cuDNN / NVRTC) ---
# 这一步必须在 import faster_whisper / ctranslate2 之前执行,
# 否则会报 RuntimeError: Library cublas64_12.dll is not found
try:
    _env_base = None
    for _env_name in ("venv", "fwenv", ".venv"):
        _candidate = _SCRIPT_DIR / _env_name
        if (_candidate / "Lib" / "site-packages").exists():
            _env_base = _candidate
            break
    _DLL_DIRS = []
    if _env_base:
        _DLL_DIRS = [
            _env_base / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
            _env_base / "Lib" / "site-packages" / "nvidia" / "cuda_runtime" / "bin",
            _env_base / "Lib" / "site-packages" / "nvidia" / "cuda_nvrtc" / "bin",
            _env_base / "Lib" / "site-packages" / "ctranslate2",
        ]
    for _d in _DLL_DIRS:
        if _d.exists():
            try:
                os.add_dll_directory(str(_d))
            except Exception:
                # 旧版 Python 可能没这个 API, 退回到 PATH 追加
                if str(_d) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mpeg", ".mpg", ".m2ts"}

# ============================================================
# 🎯 高精度转录：Whisper initial_prompt 引导 + 参数表
#    Whisper 是"条件语言模型": initial_prompt 会把概率分布偏向
#    指定的场景/词汇, 对日文语气词(哭/笑/叹气)识别提升非常显著.
# ============================================================
def build_initial_prompt(lang):
    """根据目标语言构造场景+语气词密集的 initial_prompt (224 token 以内, Whisper 限制)"""
    if lang == "ja" or not lang or lang == "auto":
        # 日文影视: 日常对话 + 大量语气词 + 拟声词 + 敬体形/简体混用
        return (
            "この動画は日本語の映画やドラマ、アニメの字幕作成です。"
            "日常会話、敬語、タメ口、スラング、感情表現を正確に書き起こしてください。"
            "特に、「ははは」「ふふっ」「クスクス」(笑い)、「すすり泣く」「えーん」「ひぃひぃ」(泣き声)、"
            "「はぁ…」「ふぅ…」「ふーん」(ため息・吐息)、「んー」「あー」「うーんと」「えっとー」(言い淀み)、"
            "「あははっ」「きゃあ」「うわぁ」「やったー」「うそーん」「えー！？」(感嘆)、"
            "「ざわざわ…」「シーン…」「ドキドキ」(場面音) といった"
            "泣く・笑う・ため息・感嘆詞を絶対に省略せず、すべて忠実に文字起こししてください。"
            "人名・地名・専門用語も正確に。敬体形、命令形、終助詞「よ、ね、わ、さ、なあ、かしら」を残す。"
        )
    if lang == "zh":
        return (
            "这是中文影视剧/综艺的字幕转录。请准确还原所有对话，包括口语、语气词和情感表达。"
            "笑声：哈哈哈、嘿嘿、呵呵、噗；哭声：呜呜、嘤嘤、抽泣；叹气：唉、哎、嗨；"
            "犹豫：嗯、呃、那个、就是说、这个嘛；感叹：哇、天哪、我的天、哎呀。"
            "以上语气词、哭泣、笑声、叹气全部保留，不要省略。书面语口语混用，方言与俚语尽量还原。"
        )
    if lang == "en":
        return (
            "This is an English movie/TV show transcript. Please write highly accurate dialogue, "
            "preserve all emotion: laughter (haha, hehe, ha, chuckles), crying (sob, sniffle, wail, boohoo), "
            "sighs (sigh, ugh, whew, phew), hesitations (uh, um, er, well, like, y'know), "
            "exclamations (wow, whoa, oh my god, jeez). Do NOT omit any of them."
        )
    if lang == "ko":
        return (
            "한국 영화/드라마 자막 생성입니다. 일상 대화, 반말, 존댓말, 슬랭, 감정 표현을 정확히 전사하세요. "
            "웃음: 하하하, 히히, 크크; 울음: 흑흑, 엉엉, 훌쩍; 한숨: 아이구, 휴, 에이; "
            "망설임: 어, 음, 그게, 저기; 감탄: 대박, 헐, 어머나. 이 모든 감정어와 울고 웃는 소리를 절대 빠뜨리지 마세요."
        )
    return None


def build_transcribe_options(lang, precision):
    """
    根据精度模式返回 transcribe() 参数 dict:
      precision = 'high'   → 极限精度(慢点, 但语气词/拟声词绝不丢, VAD 温柔不切叹气)
      precision = 'normal' → 平衡速度和精度(默认)
    """
    high = (precision == "high")
    # --- VAD 参数：high 模式下更"温柔"，防止把叹气、抽泣、呼吸声切掉 ---
    if high:
        vad_params = dict(
            threshold=0.32,              # Silero VAD 默认 0.5 → 降为 0.32 保轻声/叹气
            min_speech_duration_ms=120,  # 默认 250 → 120ms  短短 "はぁ" 不丢
            min_silence_duration_ms=300, # 默认 500 → 300ms  短停顿不切
            max_speech_duration_s=60,    # 默认 30s → 60s  长台词不截断
        )
    else:
        vad_params = dict(
            threshold=0.40,
            min_speech_duration_ms=180,
            min_silence_duration_ms=500,
            max_speech_duration_s=45,
        )
    return dict(
        language=lang if lang and lang != "auto" else None,
        beam_size=(9 if high else 6),            # beam 大=更多候选项=更准
        patience=(1.4 if high else 1.1),         # beam patience 高=更深搜索
        temperature=(0.0, 0.15, 0.3, 0.45, 0.6), # 比原来更密的温度阶梯, 贪心失败时快速降级
        repetition_penalty=(1.08 if high else 1.2), # high 模式不重罚重复 → "はははは"笑声保留
        no_speech_threshold=(0.5 if high else 0.6),
        compression_ratio_threshold=(2.2 if high else 2.4), # 更早判定幻觉
        log_prob_threshold=(-1.1 if high else -1.0),
        vad_filter=True,
        vad_parameters=vad_params,
        word_timestamps=False,                     # False → 快; 真要逐词对齐再开
        condition_on_previous_text=True,          # 利用上文保持语义一致(关键!)
        initial_prompt=build_initial_prompt(lang),# ★ 场景引导: 语气词密集区
        suppress_tokens=[],                       # ★ 不抑制任何 token: 哭/笑/叹能出标点和拟声
        suppress_blank=False,                     # 不丢短暂静音后的软语音起点
        without_timestamps=False,
        hallucination_silence_threshold=2.0,      # 静音>2s 判定幻觉=丢,防"大事なのに"死循环
    )

def sec_to_hms(sec):
    if sec is None or sec < 0:
        return "??:??:??"
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def format_srt_time(seconds_float):
    """秒(float) → SRT 时间码 HH:MM:SS,mmm"""
    h = int(seconds_float // 3600)
    m = int((seconds_float % 3600) // 60)
    s = int(seconds_float % 60)
    ms = int(round((seconds_float - int(seconds_float)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(segments, srt_path):
    """把 faster-whisper segments 写成 SRT 文本文件"""
    lines = []
    for idx, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        start_s = format_srt_time(seg.start)
        end_s = format_srt_time(seg.end)
        lines.append(str(idx))
        lines.append(f"{start_s} --> {end_s}")
        lines.append(text)
        lines.append("")
    with open(srt_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    return len([l for l in lines if l and l[0].isdigit() and ":" not in l])  # 行数

def try_get_duration(video_path):
    """探测视频总时长,失败返回 None"""
    try:
        import av
        with av.open(str(video_path)) as container:
            return float(container.duration / av.time_base) if container.duration else None
    except Exception:
        return None

def pick_folder_gui():
    """用 tkinter 弹文件夹选择框,失败返回 None"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        # 置顶
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="请选择存放视频的文件夹")
        root.destroy()
        if folder:
            return folder.strip()
        return None
    except Exception:
        return None

def scan_videos(folder_path):
    """扫描文件夹(递归子目录)下所有视频,返回 [(idx, path, duration, has_srt)]"""
    folder = Path(folder_path).resolve()
    results = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in VIDEO_EXTS:
            continue
        srt_path = p.with_suffix(p.suffix + ".srt")
        # 兼容 xxx.mp4 -> xxx.srt
        srt_path2 = p.with_suffix(".srt")
        has_srt = srt_path.exists() or srt_path2.exists()
        results.append((p, has_srt))
    # 按路径排序,给编号
    out = []
    for i, (p, hs) in enumerate(results, start=1):
        dur = try_get_duration(p)
        out.append((i, p, dur, hs))
    return out

def print_menu(videos, lang, precision):
    print("=" * 70)
    prec_tag = "🎯 高精度(慢,保留哭/笑/叹气)" if precision == "high" else "🚀 标准(平衡速度精度)"
    print(f"  目标语言: [{lang}]   精度模式: [{prec_tag}]   (改精度: mode=high / mode=normal)")
    print(f"  共找到 {len(videos)} 个视频文件:")
    print("-" * 70)
    for idx, p, dur, has_srt in videos:
        tag = "✅ 已有字幕" if has_srt else "❌ 无字幕"
        print(f"  [{idx:>3}]  {sec_to_hms(dur)}  {tag}")
        print(f"         {p}")
    print("-" * 70)
    print("  选择方式:")
    print("    all     → 转录所有无字幕的 (已有字幕的跳过)")
    print("    all!    → 转录所有视频,已有的强制覆盖重写")
    print("    1-5     → 转录第 1 到第 5 个(编号范围)")
    print("    1,3,5   → 转录指定编号的几个(逗号分隔)")
    print("    3!      → 只转第 3 个,即使已有字幕也覆盖")
    print("    mode=high   → 高精度: 完整保留哭/笑/叹气,beam=9 (推荐,稍慢)")
    print("    mode=normal → 标准精度: 速度优先 (速度≈high的1.3倍)")
    print("    q       → 退出")
    print("=" * 70)

def _normalize_input_chars(s):
    """中文输入法常见全角字符 → ASCII 半角 (用户输入 5！/1，3/1－5/lang：ja 全都能识别)"""
    if not s:
        return s
    # 全角 ! " # $ % & ' ( ) * + , - . / : ; < = > ? @ 对应 U+FF01..U+FF40 中可映射的
    trans = str.maketrans({
        "！": "!",  "？": "?",  "．": ".",  "，": ",",  "、": ",",
        "：": ":",  "；": ";",  "（": "(",  "）": ")",  "【": "[",
        "】": "]",  "「": "\"", "」": "\"", "｛": "{",  "｝": "}",
        "－": "-",  "—": "-",   "–": "-",   "～": "~",   "〜": "~",
        "／": "/",  "＼": "\\", "＝": "=",   "＋": "+",   "＊": "*",
        "％": "%",  "＃": "#",   "＠": "@",   "＆": "&",   "＄": "$",
        "　": " ",   # 全角空格
    })
    s = s.translate(trans)
    # 全角数字 ０-９ → 0-9
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:
            out.append(chr(code - 0xFF10 + ord("0")))
        else:
            out.append(ch)
    return "".join(out)


def parse_selection(raw, videos, force=False):
    """解析用户输入,返回 [(path, force_overwrite), ...]"""
    raw = _normalize_input_chars(raw).strip().lower()
    if not raw:
        return []
    # 末尾 ! 表示强制覆盖 (支持用户写成 5! / all！ 等等)
    if raw.endswith("!"):
        force = True
        raw = raw[:-1].strip()
    if raw == "all":
        result = []
        for idx, p, dur, has_srt in videos:
            if force or (not has_srt):
                result.append((p, force))
        return result
    # 1-5
    if "-" in raw and "," not in raw:
        try:
            a, b = raw.split("-", 1)
            a, b = int(a), int(b)
            a, b = sorted([a, b])
            out = []
            for idx, p, dur, has_srt in videos:
                if a <= idx <= b:
                    if force or (not has_srt):
                        out.append((p, force))
            return out
        except Exception:
            pass
    # 1,3,5
    if "," in raw:
        out = []
        try:
            ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except Exception:
            return []
        for idx, p, dur, has_srt in videos:
            if idx in ids:
                if force or (not has_srt):
                    out.append((p, force))
        return out
    # 单个数字
    try:
        n = int(raw)
        out = []
        for idx, p, dur, has_srt in videos:
            if idx == n:
                if force or (not has_srt):
                    out.append((p, force))
        return out
    except Exception:
        return []

def transcribe_one(video_path, model, lang, srt_path_out, precision):
    """转录单个视频,返回 (success, segment_count, info_str)"""
    import gc
    try:
        t0 = time.time()
        opts = build_transcribe_options(lang, precision)
        print(f"       ⚙️   精度=[{precision}]  beam={opts['beam_size']}  "
              f"VAD_th={opts['vad_parameters']['threshold']}  prompt_len={len(opts['initial_prompt'] or '')}文字", flush=True)
        segments_iter, info = model.transcribe(str(video_path), **opts)
        # 收集 segments
        segments = list(segments_iter)
        # 去重: high 模式对重复罚轻, 严格比较 (整句同才合并, 允许 ははは 单句出现)
        dedup = []
        last_text = None
        for s in segments:
            t = s.text.strip()
            if t and t != last_text:
                dedup.append(s)
                last_text = t
        if not dedup:
            # 可能没有语音,写空 SRT 方便用户知道
            with open(srt_path_out, "w", encoding="utf-8-sig") as f:
                f.write("")
            return True, 0, f"无语音内容 (用时 {time.time()-t0:.1f}s)"
        # 临时文件→原子替换,防止中途挂了留半拉子
        tmp_path = srt_path_out + ".tmp." + uuid.uuid4().hex[:8] + ".srt"
        count = write_srt(dedup, tmp_path)
        os.replace(tmp_path, srt_path_out)
        elapsed = time.time() - t0
        info_str = f"{count} 条字幕, 用时 {elapsed:.1f}s"
        if video_path.stat().st_size and info.duration:
            speed_x = info.duration / elapsed if elapsed > 0 else 0
            info_str += f" (≈{speed_x:.1f}×实时)"
        gc.collect()
        return True, count, info_str
    except Exception as e:
        tb = traceback.format_exc()
        return False, 0, f"失败: {e}\n{tb}"

def load_model(model_path):
    """加载模型,返回 (model, info_str). model_path 可以是本地目录或 HuggingFace repo ID."""
    from faster_whisper import WhisperModel
    t0 = time.time()
    # 有 NVIDIA GPU 时优先 CUDA, 依次降级 compute_type; 没 GPU 直接 CPU
    import torch
    has_cuda = torch.cuda.is_available()
    if has_cuda:
        for ct in ["int8_float32", "int8", "float32"]:
            try:
                model = WhisperModel(
                    str(model_path),
                    device="cuda",
                    compute_type=ct,
                    device_index=0,
                    num_workers=1,
                )
                return model, f"✅ 模型加载成功 (CUDA compute_type={ct}, 用时 {time.time()-t0:.1f}s)"
            except Exception as e:
                msg = str(e).lower()
                if ("cuda" in msg or "memory" in msg or "kernel" in msg
                        or "compute type" in msg or "float16" in msg):
                    print(f"  ⚠️  compute_type={ct} 失败,尝试降级...  ({e})")
                    continue
                raise
    # CUDA 全失败或没 GPU, 回退 CPU 兜底
    if has_cuda:
        print(f"  ⚠️  CUDA 全失败,回退 CPU (会很慢,但能用)...")
    else:
        print(f"  ℹ️  未检测到 NVIDIA GPU, 使用 CPU 模式 (速度较慢)...")
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", num_workers=1)
    return model, f"✅ 模型加载成功 (CPU compute_type=int8, 用时 {time.time()-t0:.1f}s)"

def srt_for_video(video_path):
    """返回该视频对应的 SRT 输出路径(优先 xxx.srt,其次 xxx.mp4.srt)"""
    video_path = Path(video_path)
    # 两种候选:前者是 xxx.mp4 -> xxx.srt
    cand1 = video_path.with_suffix(".srt")
    # 如果 cand1 不存在且有 xxx.mp4.srt,沿用那个
    cand2 = video_path.with_suffix(video_path.suffix + ".srt")
    if cand2.exists() and not cand1.exists():
        return cand2
    return cand1

def main():
    print("=" * 70)
    print("  🎬  本地视频批量字幕转录 (faster-whisper + NVIDIA CUDA)  ")
    print("     模型: whisper-large-v3-turbo (CTranslate2 原生格式)")
    print("     显卡: GTX 1060 6GB  →  CUDA int8_float32 (INT8量化+FP32计算)")
    print("     防重复: temperature 阶梯 + repetition_penalty 1.2 + VAD静音过滤")
    print("=" * 70)
    base_dir = Path(__file__).resolve().parent
    # faster-whisper 需要目录格式: fw_model/ 下有:
    #   model.bin (CTranslate2 原生 large-v3-turbo)
    #   config.json + preprocessor_config.json
    #   tokenizer.json + vocabulary.json
    FW_MODEL_HF_ID = "Systran/faster-whisper-large-v3-turbo"
    model_path = base_dir / "fw_model"
    use_hf_download = False
    if not model_path.exists() or not (model_path / "model.bin").exists():
        print(f"📦 本地模型目录 fw_model/ 不存在或缺少 model.bin")
        print(f"   将从 HuggingFace 镜像自动下载 CTranslate2 格式模型 (~1.6GB)...")
        print(f"   模型: {FW_MODEL_HF_ID}")
        print(f"   首次下载需要较长时间, 之后永久本地缓存, 断网也能用.")
        use_hf_download = True
        model_path = FW_MODEL_HF_ID  # WhisperModel 接受 HF repo ID 会自动下载

    # --- 步骤1: 让用户确认语言 ---
    print()
    lang_default = "ja"
    lang = input(f"🎙️  请输入目标语言代码 (默认 {lang_default}=日语,回车用默认):\n    常用: ja=日语 zh=中文 en=英语 ko=韩语 auto=自动识别\n> ").strip().lower()
    if not lang:
        lang = lang_default
    precision_default = "high"
    precision_in = input(f"🎯  请输入精度模式 (默认 {precision_default}=高精度,回车用默认):\n    high=高精度(慢/完整保留哭笑声叹气,推荐)  normal=标准(平衡速度精度)\n> ").strip().lower()
    precision = precision_in if precision_in in ("high", "normal") else precision_default
    print(f"  → 语言=[{lang}]  精度=[{precision}]")

    # --- 步骤2: 选视频文件夹 ---
    print()
    print("📂 即将弹出文件夹选择框... 如果没看到 → 按 Alt+Tab 切窗口")
    folder = pick_folder_gui()
    if not folder:
        print("  ⚠️  没选文件夹,请手动输入完整路径")
        folder = input("> ").strip()
    if not folder or not Path(folder).exists():
        print("❌ 无效路径,退出")
        input("按回车退出...")
        return
    folder = str(Path(folder).resolve())
    print(f"  → 扫描文件夹: {folder}")

    # --- 步骤3: 扫描视频列表 ---
    print()
    print("🔍 正在扫描视频 (探测时长,请稍候)...")
    videos = scan_videos(folder)
    if not videos:
        print("❌ 没找到任何视频文件 (支持: mp4/mkv/avi/mov/wmv/flv/webm/m4v/ts/mpeg/mpg)")
        input("按回车退出...")
        return

    # --- 步骤4: 主循环 ---
    while True:
        # 刷新 SRT 状态(因为上一轮可能生成了新的)
        refreshed = []
        for idx, p, dur, _ in videos:
            new_has_srt = (p.with_suffix(".srt").exists() or p.with_suffix(p.suffix + ".srt").exists())
            refreshed.append((idx, p, dur, new_has_srt))
        videos = refreshed

        print_menu(videos, lang, precision)
        raw_original = input("请输入你的选择 > ").strip()
        raw = _normalize_input_chars(raw_original)   # 全角→半角, 让 5！/mode：high 都能识别
        if raw.lower() in ("q", "quit", "exit", ""):
            print("👋 再见")
            time.sleep(1)
            return
        # 精度模式切换
        import re as _re
        m_md = _re.match(r"^\s*mode\s*[=:]\s*(high|normal)\s*$", raw, _re.I)
        if m_md:
            precision = m_md.group(1).lower()
            print(f"  ✅ 精度模式已切为: {precision}")
            continue
        m_lg = _re.match(r"^\s*lang\s*[=:]\s*(ja|zh|en|ko|auto)\s*$", raw, _re.I)
        if m_lg:
            lang = m_lg.group(1).lower()
            print(f"  ✅ 目标语言已切为: {lang}")
            continue
        selected = parse_selection(raw, videos)
        if not selected:
            print("❌ 解析失败,请按上面的格式输入 (q 退出, mode=high/normal 切精度, lang=xx 切语言)")
            continue

        # --- 步骤5: 加载模型(懒加载,只在第一次选择时加载) ---
        if not hasattr(main, "_model"):
            print()
            print("🧠 正在加载模型到 GPU (第一次需要 10~30 秒,请稍候)...")
            try:
                model, info_s = load_model(model_path)
                print(f"  {info_s}")
                main._model = model
            except Exception as e:
                print(f"❌ 模型加载失败: {e}")
                traceback.print_exc()
                input("按回车退出...")
                return
        else:
            print()
            print("🧠 模型已在 GPU,开始转录")

        # --- 步骤6: 逐个转录 ---
        total = len(selected)
        success_cnt = 0
        fail_cnt = 0
        skip_cnt = 0
        for i, (vp, force_ow) in enumerate(selected, start=1):
            srt_path = srt_for_video(vp)
            if srt_path.exists() and not force_ow:
                print(f"\n  [{i}/{total}] ⏭️  跳过(已有字幕): {vp.name}")
                skip_cnt += 1
                continue
            dur_tag = sec_to_hms(try_get_duration(vp))
            ow_tag = " [覆盖重写]" if force_ow else ""
            print(f"\n  [{i}/{total}] ▶️  开始{ow_tag}: {vp.name}  ({dur_tag})")
            ok, count, info = transcribe_one(vp, main._model, lang, str(srt_path), precision)
            if ok:
                print(f"  [{i}/{total}] ✅ 完成 {info}  → {srt_path.name}")
                success_cnt += 1
            else:
                print(f"  [{i}/{total}] ❌ 失败 {vp.name}: {info}")
                fail_cnt += 1

        print()
        print("=" * 60)
        print(f"  📊 本轮结果: 成功 {success_cnt}  /  失败 {fail_cnt}  /  跳过 {skip_cnt}")
        print("=" * 60)
        print()
        ans = input("回车继续选择其它视频,输入 q 退出 > ").strip().lower()
        if ans in ("q", "quit", "exit"):
            print("👋 再见")
            time.sleep(1)
            return

if __name__ == "__main__":
    main()
