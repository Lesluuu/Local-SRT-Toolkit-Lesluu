# -*- coding: utf-8 -*-
"""
本地 SRT 字幕翻译器 - 日文/英文/韩文 → 中文
启动方式: 双击 启动字幕翻译.bat

翻译符合场景的策略:
  - 不是逐条孤立翻译, 而是把 6~8 条时间相近的字幕凑成一整段,
    整段送入翻译模型 (句子之间用换行分隔). 模型看到整段上下文,
    人称/时态/语气保持一致, 场景不割裂.
  - 模型返回整段中文后, 再按【原 SRT 条数 + 中文换行符或标点】
    拆回对应每一条字幕.

模型: Facebook NLLB-200 distilled-600M (单模型覆盖 ja/en/ko→中文, 免费, 本地离线)
     通过 hf-mirror.com 国内镜像下载, 约 3GB (后续全部本地运行).
"""
import os
import sys
import re
import json
import uuid
import time
import inspect
import traceback
import contextlib
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

# --- Windows DLL 路径注册 (torch / cublas 等) ---
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
                if str(_d) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

# 强制用 hf-mirror.com 作为 HuggingFace 下载源 + 超时/重试 (参考经验 1252594)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")   # 单分片 5 分钟超时
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0") # 避免 hf_transfer 缺失报错

# ============================================================
# 字幕数据结构
# ============================================================
class SrtEntry:
    __slots__ = ("idx", "start", "end", "text")
    def __init__(self, idx, start, end, text):
        self.idx = idx      # 原始序号 int
        self.start = start  # float 秒
        self.end = end      # float 秒
        self.text = text    # str, 一行或多行(\n分隔)已合并为单行(多空格压缩)

# ============================================================
# SRT 解析 & 写出
# ============================================================
def _parse_ts(s):
    """SRT时间码 HH:MM:SS,mmm → float 秒"""
    s = s.strip().replace(".", ",")
    if not s:
        return 0.0
    try:
        hms, mmm = s.split(",", 1)
        h, m, s = hms.split(":")
        return int(h)*3600 + int(m)*60 + int(s) + int(mmm)/1000.0
    except Exception:
        return 0.0

def _fmt_ts(sec):
    """float秒 → HH:MM:SS,mmm"""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    if s >= 60:
        m += s // 60
        s = s % 60
    if m >= 60:
        h += m // 60
        m = m % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

_WS = re.compile(r"\s+")
def read_srt(path):
    """读取 SRT → list[SrtEntry]. 自动处理 UTF-8/UTF-8-SIG/GB18030/Shift-JIS/EUC-KR"""
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "shift-jis", "euc-kr"):
        try:
            with open(path, "r", encoding=enc) as f:
                text = f.read()
                break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError(f"无法识别字幕文件编码: {path}")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    entries = []
    n = 0
    for b in blocks:
        lines = [ln for ln in b.split("\n") if ln.strip() != ""]
        if len(lines) < 2:
            continue
        cur = 0
        idx = n + 1
        m1 = re.fullmatch(r"\s*\d+\s*", lines[cur])
        if m1:
            try:
                idx = int(lines[cur].strip())
            except Exception:
                pass
            cur += 1
        start, end = 0.0, 0.0
        if cur < len(lines) and "-->" in lines[cur]:
            ts = lines[cur].split("-->", 1)
            start = _parse_ts(ts[0])
            end = _parse_ts(ts[1])
            cur += 1
        body = " ".join(lines[cur:]).strip()
        body = _WS.sub(" ", body)
        if not body:
            continue
        n += 1
        entries.append(SrtEntry(idx, start, end, body))
    return entries

def write_srt(entries, path):
    """写出标准 SRT (UTF-8 BOM), 按 start 排序"""
    entries = sorted(entries, key=lambda e: e.start)
    lines = []
    for i, e in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(e.start)} --> {_fmt_ts(e.end)}")
        lines.append(e.text.strip())
        lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines).rstrip() + "\n")

# ============================================================
# 语言识别 (基于字幕内容的启发式, 足够区分 ja/en/ko/zh)
# ============================================================
_RE_HIRAGANA = re.compile(r"[\u3040-\u309F]")
_RE_KATAKANA  = re.compile(r"[\u30A0-\u30FF]")
_RE_HANGUL    = re.compile(r"[\uAC00-\uD7AF]")
_RE_CJK       = re.compile(r"[\u4E00-\u9FFF]")
_RE_ASCII     = re.compile(r"[A-Za-z]")

def detect_lang_from_entries(entries):
    """返回 'ja' | 'en' | 'ko' | 'zh' | 'auto'"""
    if not entries:
        return "auto"
    sample = " ".join(e.text for e in entries[:60])
    n_hi = len(_RE_HIRAGANA.findall(sample))
    n_ka = len(_RE_KATAKANA.findall(sample))
    n_ko = len(_RE_HANGUL.findall(sample))
    n_cn = len(_RE_CJK.findall(sample))
    n_en = len(_RE_ASCII.findall(sample))
    total_char = max(1, len([c for c in sample if not c.isspace()]))
    if (n_hi + n_ka) / total_char > 0.08:
        return "ja"
    if n_ko / total_char > 0.15:
        return "ko"
    if n_en / total_char > 0.4:
        return "en"
    if n_cn / total_char > 0.25 and (n_hi + n_ka + n_ko) == 0:
        return "zh"
    return "auto"

# ============================================================
# NLLB 常量 + 中文标点后处理
# ============================================================
NLLB_HF_ID = "facebook/nllb-200-distilled-600M"
NLLB_LANG_CODE = {
    "ja": "jpn_Jpan",
    "en": "eng_Latn",
    "ko": "kor_Hang",
    "zh": "zho_Hans",
}
MODEL_HF_IDS = {
    "ja": NLLB_HF_ID,
    "en": NLLB_HF_ID,
    "ko": NLLB_HF_ID,
}

def _zh_normalize(text):
    """中文字幕输出规范化: 半角标点→全角, 删除开头多余标点, 压缩重复标点, 删除中文句内空格"""
    text = text.strip()
    if not text:
        return ""
    repl = [(",", "，"), (".", "。"), ("!", "！"), ("?", "？"),
            (":", "："), (";", "；"), ("(", "（"), (")", "）")]
    out = []
    for ch in text:
        for a, b in repl:
            if ch == a:
                ch = b
                break
        out.append(ch)
    s = "".join(out)
    s = re.sub(r"。{2,}", "。", s)
    s = re.sub(r"，{2,}", "，", s)
    # 删除句首的标点 / 多余空格 (NLLB 有时会输出 ",真的吗?" 这种)
    s = s.lstrip("，。！？：；,.!?;: 　\t")
    # 删除中文句子内部多余空格
    s = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", s)
    return s.strip()

# ============================================================
# 工具: torch.inference_mode 兼容 + tokenizer 参数探测
# ============================================================
def torch_inference_mode():
    try:
        import torch
        return torch.inference_mode()
    except Exception:
        return contextlib.nullcontext()

def _tok_has_kwarg(tok, name):
    try:
        sig = inspect.signature(tok.__call__)
        return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()) \
            or name in sig.parameters
    except Exception:
        return False

def _resolve_lang_token_id(tok, lang_code):
    """三档兼容: lang_code_to_id → convert_tokens_to_ids → encode 首 id"""
    cand = None
    if hasattr(tok, "lang_code_to_id") and isinstance(getattr(tok, "lang_code_to_id"), dict):
        cand = tok.lang_code_to_id.get(lang_code)
    unk = getattr(tok, "unk_token_id", None)
    if cand is None or (unk is not None and cand == unk):
        try:
            x = tok.convert_tokens_to_ids(lang_code)
            if isinstance(x, int) and (unk is None or x != unk):
                cand = x
        except Exception:
            pass
    if cand is None or (unk is not None and cand == unk):
        try:
            ids = tok.encode(lang_code, add_special_tokens=False)
            if ids:
                cand = ids[0]
        except Exception:
            pass
    if cand is None:
        raise RuntimeError(f"NLLB tokenizer 无法获取 {lang_code} 的 token id (transformers API 变动)")
    return cand

# ============================================================
# 翻译器: 懒加载 NLLB-200 单模型 + 整段(7条/组)上下文翻译
# ============================================================
class Translator:
    def __init__(self, cache_dir=None, device=None):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent / "mt_models"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        self._nllb = None  # (tok, mdl, dev)

    def _decide_device(self):
        if self.device is not None:
            return self.device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
        return "cpu"

    def _ensure_nllb(self):
        if self._nllb is not None:
            return self._nllb
        dev = self._decide_device()
        print(f"   🧠 加载翻译模型 [{NLLB_HF_ID}]  设备={dev} (首次自动下载约3GB)...", flush=True)
        t0 = time.time()
        try:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            tok = AutoTokenizer.from_pretrained(NLLB_HF_ID, cache_dir=str(self.cache_dir))
            mdl = AutoModelForSeq2SeqLM.from_pretrained(NLLB_HF_ID, cache_dir=str(self.cache_dir))
            if dev != "cpu":
                try:
                    mdl = mdl.half()
                except Exception:
                    pass
            mdl = mdl.to(dev)
            self._nllb = (tok, mdl, dev)
            print(f"     ✅ 加载完成, 用时 {time.time()-t0:.1f}s", flush=True)
            return self._nllb
        except Exception as e:
            tb = traceback.format_exc()
            print(f"     ❌ 加载失败: {e}\n{tb[:800]}", flush=True)
            raise

    def _translate_text(self, src_lang, text, max_length=512):
        """单段文本 → 中文(内部会按 token 长度自动 chunk)"""
        if src_lang not in MODEL_HF_IDS:
            raise RuntimeError(f"暂不支持源语言: {src_lang}")
        tok, mdl, dev = self._ensure_nllb()
        src_code = NLLB_LANG_CODE[src_lang]
        tgt_code = NLLB_LANG_CODE["zh"]
        tgt_bos_id = _resolve_lang_token_id(tok, tgt_code)
        # 传 src_lang 关键字 (兼容新老 transformers)
        if _tok_has_kwarg(tok, "src_lang"):
            encoded = tok(text, return_tensors="pt", truncation=True,
                          max_length=1024, src_lang=src_code)
        else:
            try:
                tok.src_lang = src_code
            except Exception:
                pass
            encoded = tok(text, return_tensors="pt", truncation=True, max_length=1024)
        encoded = {k: v.to(dev) for k, v in encoded.items()}
        with torch_inference_mode():
            gen = mdl.generate(
                **encoded,
                forced_bos_token_id=tgt_bos_id,
                max_length=max_length,
                num_beams=3,
                early_stopping=True,
                no_repeat_ngram_size=3,
            )
        return tok.batch_decode(gen, skip_special_tokens=True)[0].strip()

    def translate_paragraph(self, src_lang, paragraph):
        """多条字幕拼成的换行段落 → 翻译后中文段落"""
        max_tokens = 400
        sents = [s.strip() for s in paragraph.split("\n") if s.strip()]
        out_chunks = []
        buf, buf_len = [], 0
        def _flush(buf):
            if not buf:
                return
            txt = "\n".join(buf)
            zh = self._translate_text(src_lang, txt, max_length=max_tokens)
            out_chunks.append(zh.strip())
        for s in sents:
            est = len(s) + 1
            if buf and (buf_len + est > max_tokens or len(buf) >= 8):
                _flush(buf)
                buf, buf_len = [], 0
            buf.append(s)
            buf_len += est
        _flush(buf)
        return _zh_normalize("\n".join(out_chunks).strip())

    def translate_chunk(self, src_lang, entries_chunk):
        """
        逐条翻译 (1 条原文 → 1 条译文 1:1 对应), 绝对不出现按字符乱切导致的日文碎片.
        返回 [中文句列表], 长度 == len(entries_chunk)
        """
        N = len(entries_chunk)
        if N == 0:
            return []
        out = []
        print(f"       📝 本组 {N} 条字幕逐条翻译中 (每条几秒) [", end="", flush=True)
        for idx, e in enumerate(entries_chunk, start=1):
            src = e.text.strip()
            if not src:
                out.append("")
                print("·", end="", flush=True)
                continue
            try:
                zh = self._translate_text(src_lang, src, max_length=256)
                zh = _zh_normalize(zh)
                if not zh:
                    zh = src
            except Exception:
                zh = src
            out.append(zh)
            # 每 2 条打一个点, 用户知道没卡死
            if idx % 2 == 0:
                print("·", end="", flush=True)
        print("] ✅", flush=True)
        return out

# ============================================================
# 断点续翻进度文件
# ============================================================
def progress_path(srt_src_path, output_dir, src_root):
    try:
        rel = Path(srt_src_path).resolve().relative_to(Path(src_root).resolve())
    except Exception:
        rel = Path(Path(srt_src_path).name)
    base = str(rel).replace(os.sep, "__").replace(":", "__")
    return Path(output_dir) / f".progress_{base}.json"

def load_progress(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_progress(p, obj):
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        tmp = str(p) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        print(f"   ⚠️  保存进度失败: {e}", flush=True)

# ============================================================
# 翻译单个 SRT
# ============================================================
def translate_one_srt(src_path, out_path, translator, src_lang_override,
                      chunk_size=7, force=False):
    """返回 (success:bool, translated_count:int, msg:str)"""
    try:
        t0 = time.time()
        entries = read_srt(src_path)
        if not entries:
            return False, 0, "SRT 文件为空"
        detected = detect_lang_from_entries(entries)
        src_lang = src_lang_override if src_lang_override not in (None, "", "auto") else detected
        if src_lang == "zh":
            return True, 0, f"已判定为中文字幕,跳过翻译 (detect={detected})"
        if src_lang not in MODEL_HF_IDS:
            return False, 0, (
                f"无法处理的字幕语言: 检测={detected}, 覆盖值={src_lang_override or 'auto'}. "
                f"当前支持 ja/en/ko → 中文"
            )
        out_parent = Path(out_path).parent
        try:
            grand = Path(src_path).resolve().parent.parent
            prog_path = progress_path(src_path, out_parent, grand)
        except Exception:
            prog_path = out_parent / f".progress_{Path(src_path).stem}.json"
        prog = load_progress(prog_path)
        done_chunks = set(prog.get("done_chunks", []))
        if Path(out_path).exists() and not force and not prog:
            return True, len(entries), "已存在成品,跳过 (force 可覆盖)"
        sorted_idx = sorted(range(len(entries)), key=lambda i: entries[i].start)
        chunks = [sorted_idx[i:i + chunk_size] for i in range(0, len(sorted_idx), chunk_size)]
        done_new = 0
        for ci, chunk_indices in enumerate(chunks):
            if ci in done_chunks and not force:
                done_new += len(chunk_indices)
                continue
            chunk_entries = [entries[i] for i in chunk_indices]
            try:
                zh_lines = translator.translate_chunk(src_lang, chunk_entries)
                if len(zh_lines) != len(chunk_entries):
                    if len(zh_lines) < len(chunk_entries):
                        zh_lines = zh_lines + [""] * (len(chunk_entries) - len(zh_lines))
                    else:
                        zh_lines = zh_lines[:len(chunk_entries) - 1] + \
                                   ["".join(zh_lines[len(chunk_entries) - 1:])]
            except Exception as e:
                tb = traceback.format_exc()
                print(f"   ❌ chunk#{ci} 翻译失败: {e}\n{tb[:600]}", flush=True)
                zh_lines = [e.text for e in chunk_entries]
            for k, i in enumerate(chunk_indices):
                zh = zh_lines[k].strip() if k < len(zh_lines) else ""
                if not zh:
                    zh = chunk_entries[k].text
                entries[i] = SrtEntry(entries[i].idx, entries[i].start, entries[i].end, zh)
            done_chunks.add(ci)
            done_new += len(chunk_indices)
            save_progress(prog_path, {
                "done_chunks": sorted(int(x) for x in done_chunks),
                "total_chunks": len(chunks),
                "total_entries": len(entries),
            })
        tmp = str(out_path) + ".tmp." + uuid.uuid4().hex[:8] + ".srt"
        write_srt(entries, tmp)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, out_path)
        try:
            if Path(prog_path).exists():
                os.remove(prog_path)
        except Exception:
            pass
        elapsed = time.time() - t0
        return True, done_new, f"成功: 共 {len(entries)} 条, 耗时 {elapsed:.0f}s ({src_lang}→zh)"
    except Exception as e:
        tb = traceback.format_exc()
        return False, 0, f"失败: {type(e).__name__}: {e}\n{tb}"

# ============================================================
# GUI 选文件夹 / 菜单
# ============================================================
_PICK_REMINDER_PRINTED = False
def _remind_gui_popup(kind):
    """Tk 文件选择对话框经常被命令行挡住, 给用户大字提醒"""
    global _PICK_REMINDER_PRINTED
    sep = "★" * 70
    print()
    print(sep)
    print(f"  ⚠️   即将弹出【选择{kind}文件夹】的 GUI 对话框!")
    print("  ⚠️   如果没看到, 很可能被这个命令行窗口挡住了 → 按 Alt+Tab 切换窗口")
    print("  ⚠️   或点击任务栏上一闪一闪的 '文件资源管理器' / 'Python' 图标")
    print(sep)
    _PICK_REMINDER_PRINTED = True
    time.sleep(0.8)

def pick_folder(title):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        # 额外: 用一个短暂可见的 topmost Toplevel 把系统焦点拉到 Tk, 让 filedialog 更容易前置
        try:
            helper = tk.Toplevel(root)
            helper.attributes("-topmost", True)
            helper.withdraw()
        except Exception:
            pass
        folder = filedialog.askdirectory(title=title, parent=root)
        try:
            root.destroy()
        except Exception:
            pass
        return folder.strip() if folder else None
    except Exception:
        return None

def scan_srts(folder_src):
    """递归扫描 .srt, 返回 [(i, path, size, entries_count, detected_lang)]"""
    root = Path(folder_src).resolve()
    srts = sorted(p for p in root.rglob("*.srt") if p.is_file())
    out = []
    for i, p in enumerate(srts, start=1):
        sz = p.stat().st_size
        cnt, lang = None, "?"
        try:
            es = read_srt(p)
            cnt = len(es)
            lang = detect_lang_from_entries(es)
        except Exception:
            pass
        out.append((i, p, sz, cnt, lang))
    return out

def compute_output_path(src_path, src_root, out_root):
    try:
        rel = Path(src_path).resolve().relative_to(Path(src_root).resolve())
    except Exception:
        rel = Path(Path(src_path).name)
    return Path(out_root).resolve() / rel

def print_menu(items, src_dir, out_dir, src_lang):
    print("=" * 72)
    print(f"  源字幕文件夹 : {src_dir}")
    tag_same = "✅ 路径不同" if Path(src_dir).resolve() != Path(out_dir).resolve() else "❌ 和源相同(必改!)"
    print(f"  输出文件夹   : {out_dir}   {tag_same}")
    print(f"  源语言       : {src_lang or 'auto(自动识别)'}   [当前支持 ja/en/ko → 中文]")
    print(f"  共找到 {len(items)} 个 SRT 字幕文件:")
    print("-" * 72)
    for i, p, sz, cnt, lang in items:
        sz_tag = f"{sz/1024:.0f}KB" if sz < 1024 * 1024 else f"{sz/1024/1024:.1f}MB"
        cnt_tag = f"{cnt:>5}条" if cnt is not None else "读失败"
        print(f"  [{i:>3}]  {lang:>3s}  {cnt_tag}  {sz_tag:>7s}")
        print(f"         {p}")
    print("-" * 72)
    print("  选择方式:")
    print("    all     → 翻译所有 (已完成自动跳过, 加 ! 强制覆盖, 如 all!)")
    print("    1-5     → 翻译第 1~5 个")
    print("    1,3,5   → 翻译指定编号的几个")
    print("    3!      → 仅第 3 个, 覆盖重翻")
    print("    lang=ja → 把源语言改为 ja (或 en/ko/auto)")
    print("    dir=in  → 重新选输入文件夹; dir=out 重新选输出文件夹")
    print("    q       → 退出")
    print("=" * 72)

def _normalize_input_chars(s):
    """中文输入法常见全角字符 → ASCII 半角 (让 5！ / 1，3 / 1－5 / lang：ja 都能识别)"""
    if not s:
        return s
    trans = str.maketrans({
        "！": "!",  "？": "?",  "．": ".",  "，": ",",  "、": ",",
        "：": ":",  "；": ";",  "（": "(",  "）": ")",  "【": "[",
        "】": "]",  "「": "\"", "」": "\"", "｛": "{",  "｝": "}",
        "－": "-",  "—": "-",   "–": "-",   "～": "~",   "〜": "~",
        "／": "/",  "＼": "\\", "＝": "=",   "＋": "+",   "＊": "*",
        "％": "%",  "＃": "#",   "＠": "@",   "＆": "&",   "＄": "$",
        "　": " ",
    })
    s = s.translate(trans)
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:
            out.append(chr(code - 0xFF10 + ord("0")))
        else:
            out.append(ch)
    return "".join(out)

def parse_selection(raw, items, force=False):
    raw = _normalize_input_chars(raw).strip()
    if not raw:
        return None
    if raw.lower().endswith("!"):
        force = True
        raw = raw[:-1].strip()
    if raw.lower() == "all":
        return [(it[1], force) for it in items]
    if "-" in raw and "," not in raw:
        try:
            a, b = sorted(int(x.strip()) for x in raw.split("-", 1))
        except Exception:
            return None
        return [(it[1], force) for it in items if a <= it[0] <= b]
    if "," in raw:
        try:
            ids = set(int(x.strip()) for x in raw.split(",") if x.strip())
        except Exception:
            return None
        return [(it[1], force) for it in items if it[0] in ids]
    try:
        n = int(raw)
    except Exception:
        return None
    return [(it[1], force) for it in items if it[0] == n]

# ============================================================
# main
# ============================================================
def main():
    print("=" * 72)
    print("  🈯  本地 SRT 字幕翻译器 (日文/英文/韩文 → 中文)")
    print(f"     模型:  {NLLB_HF_ID}  (免费, 首次自动下载, 之后本地离线)")
    print("     特色:  上下文整段翻译(6-8条/组), 保证场景语气连贯")
    print("     断点:  每个文件进度独立保存, 中途退出接着翻")
    print("     安全:  输出文件夹必须 ≠ 源文件夹, 永远不覆盖原字幕")
    print("=" * 72)
    base = Path(__file__).resolve().parent

    # 1) 选输入/输出文件夹 (保证两者不同)
    src_dir = None
    out_dir = None
    src_lang = "auto"
    while True:
        if not src_dir:
            print("\n📂 请选择【源 SRT 字幕所在文件夹】(会递归子目录)...")
            _remind_gui_popup("源 SRT 字幕")
            src_dir = pick_folder("选择存放 SRT 字幕的源文件夹")
            if not src_dir:
                print("⚠️  未选择, 手动输入完整路径:")
                x = input("> ").strip().strip('"')
                if x and Path(x).exists():
                    src_dir = x
            if not src_dir or not Path(src_dir).exists():
                print("❌ 无效输入目录, 重试或 q 退出")
                y = input("按回车重选, 输入 q 退出 > ").strip().lower()
                if y in ("q", "quit"):
                    return
                continue
        if not out_dir:
            print("\n📂 请选择【翻译后 SRT 输出文件夹】(必须与源文件夹不同)...")
            _remind_gui_popup("翻译后字幕输出")
            out_dir = pick_folder("选择翻译后字幕的输出文件夹")
            if not out_dir:
                print("⚠️  未选择, 手动输入完整路径:")
                x = input("> ").strip().strip('"')
                if x:
                    Path(x).mkdir(parents=True, exist_ok=True)
                    out_dir = x
            if not out_dir:
                print("❌ 无效输出目录, 重试")
                continue
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            if Path(src_dir).resolve() == Path(out_dir).resolve():
                print("❌ 输出文件夹与源文件夹相同! 为了不覆盖原字幕请换另一个")
                out_dir = None
                continue
        print(f"\n🔎 扫描 {src_dir} 下的 SRT 文件...", end=" ", flush=True)
        items = scan_srts(src_dir)
        print(f"找到 {len(items)} 个", flush=True)
        if not items:
            print(f"\n❌ 在 {src_dir} 下没找到任何 .srt 文件")
            y = input("按回车换输入文件夹, q 退出 > ").strip().lower()
            if y in ("q", "quit"):
                return
            src_dir = None
            continue
        break

    translator = Translator(cache_dir=str(base / "mt_models"))

    while True:
        items = scan_srts(src_dir)
        print_menu(items, src_dir, out_dir, src_lang)
        raw_original = input("请输入你的选择 > ").strip()
        raw = _normalize_input_chars(raw_original)   # 全角→半角: 5！/ lang：ja / dir：in 全都能识别
        if not raw:
            continue
        low = raw.lower()
        if low in ("q", "quit", "exit"):
            print("👋 再见")
            return
        m = re.match(r"^\s*lang\s*[=:]\s*(ja|en|ko|auto|zh)\s*$", raw, re.I)
        if m:
            src_lang = m.group(1).lower()
            print(f"✅ 源语言改为: {src_lang}")
            continue
        m = re.match(r"^\s*dir\s*[=:]\s*(in|out|src|dst)\s*$", raw, re.I)
        if m:
            k = m.group(1).lower()
            if k in ("in", "src"):
                src_dir = None
                while not src_dir:
                    print("\n📂 选择新的【源 SRT 文件夹】...")
                    _remind_gui_popup("源 SRT")
                    nd = pick_folder("选择存放 SRT 的源文件夹")
                    if nd:
                        src_dir = nd
                    else:
                        x = input("手动输入完整路径 > ").strip().strip('"')
                        if x and Path(x).exists():
                            src_dir = x
            else:
                out_dir = None
            while not out_dir or Path(src_dir).resolve() == Path(out_dir).resolve():
                print("\n📂 选择新的【输出文件夹】...")
                _remind_gui_popup("翻译后字幕输出")
                nd = pick_folder("选择翻译后输出文件夹")
                if nd:
                    out_dir = nd
                else:
                    x = input("手动输入完整路径 > ").strip().strip('"')
                    if x:
                        Path(x).mkdir(parents=True, exist_ok=True)
                        out_dir = x
                if out_dir and Path(src_dir).resolve() == Path(out_dir).resolve():
                    print("❌ 不能和源文件夹相同!")
                    out_dir = None
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            continue
        sel = parse_selection(raw, items)
        if not sel:
            print("❌ 解析失败, 请按菜单格式输入 (q 退出)")
            continue
        total = len(sel)
        ok_cnt = fail_cnt = skip_cnt = 0
        for i, (sp, force_ow) in enumerate(sel, start=1):
            sp = Path(sp).resolve()
            op = compute_output_path(sp, src_dir, out_dir)
            tag_ow = " [覆盖]" if force_ow else ""
            print(f"\n  [{i}/{total}] ▶️  {tag_ow} {sp.name}")
            print(f"       → {op}")
            try:
                ok, n, msg = translate_one_srt(
                    str(sp), str(op), translator,
                    src_lang_override=(src_lang if src_lang != "auto" else None),
                    chunk_size=7, force=force_ow,
                )
            except Exception as e:
                ok, n, msg = False, 0, f"异常: {type(e).__name__}: {e}"
            if ok:
                if "跳过" in msg:
                    print(f"  [{i}/{total}] ⏭️  {msg}")
                    skip_cnt += 1
                else:
                    print(f"  [{i}/{total}] ✅ 翻译完成 ({n}条) - {msg}")
                    ok_cnt += 1
            else:
                print(f"  [{i}/{total}] ❌ {msg}")
                fail_cnt += 1
        print()
        print("=" * 60)
        print(f"  📊 本轮结果: 成功 {ok_cnt}  /  失败 {fail_cnt}  /  跳过 {skip_cnt}")
        print("=" * 60)
        x = input("回车继续, q 退出 > ").strip().lower()
        if x in ("q", "quit", "exit"):
            print("👋 再见")
            return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 中断退出")
