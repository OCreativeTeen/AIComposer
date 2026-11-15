"""把一段音频或视频转成「每句前面带时间戳」的文字文件。

做法：
1. 把声音切成固定长度的小段（``config.TRANSCRIBE_CHUNK_SECONDS``，默认 600 秒），一段一段转录。
   转录用哪一种由 ``config.TRANSCRIBE_ENGINE`` 决定：本机 Whisper 或 Voicebox。
2. 本机 Whisper 每个片段自带开始和结束时间。Voicebox 的接口只给整段文字，
   服务端有分段时间就用，没有就只知道这一小段从几秒到几秒。
3. 原文没有标点，也没有按句分开。把若干小段（连同时间）交给 LLM：补标点、一句一行，
   每行开头写这一句开始的秒数（精确到 0.1 秒）。
   LLM 没有按格式回答、时间乱了、或者字数对不上时，这一批退回原始片段：一个片段一行，
   用它自己的开始时间。
4. 所有小段都处理完、拼成完整的带时间的句子之后，再单独调用一次 LLM，根据整段对话的上下文
   判断每一句是谁说的（最多 4 个人）。对话里换人很频繁，所以这一步单独做，能看到整体上下文。
   文字太长时按 ``config.TRANSCRIBE_SPEAKER_MAX_CHARS`` 分窗口，后一个窗口会带上前面已经判断好的几句。
5. 输出 ``[hh:mm:ss.s] <说话人> 一句话`` 的文本文件，每句一行。说话人标记 ``<1>`` ``<2>`` …
   只写在换人的那一句前面；整个文件第一句一定写 ``<1>``。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Optional

import config
import config_prompt

_LINE_RE = re.compile(r"^\s*\[\s*(\d+(?:\.\d+)?)\s*\]\s*(.+?)\s*$")
_SPEAKER_LINE_RE = re.compile(r"^\s*(\d+)\s*[:：=\-]\s*<?\s*(\d+)\s*>?\s*$")
MAX_SPEAKERS = 4


def transcript_path_for_media(media_path: str) -> str:
    """媒体的文字稿路径：同一个文件夹、同样的文件名，扩展名换成 ``.txt``。"""
    return os.path.splitext(os.path.abspath(media_path))[0] + ".txt"


def find_transcript_for_media(media_path: str) -> str:
    """媒体旁边已经有文字稿就返回它的路径，没有返回空字符串。"""
    if not media_path:
        return ""
    path = transcript_path_for_media(media_path)
    return path if os.path.isfile(path) else ""


def ask_copy_choice(parent, media_name: str, transcript_name: str) -> str:
    """媒体和文字稿都有时，问用户拷哪一个。返回 ``"media"``、``"transcript"``，取消返回空字符串。"""
    return ask_choice(
        parent,
        "拷贝",
        "这里既有媒体，也有它的文字稿。\n"
        f"媒体：{media_name}\n文字稿：{transcript_name}\n\n要拷贝哪一个到剪贴板？",
        [("transcript", "拷贝文字稿"), ("media", "拷贝媒体")],
    )


def ask_choice(parent, title: str, text: str, options: list[tuple[str, str]]) -> str:
    """弹一个模态小窗口：一段说明加几个按钮，最右边固定是「取消」。

    ``options`` 是 ``[(返回值, 按钮文字), ...]``。点了某个按钮返回它的返回值；
    取消或关掉窗口返回空字符串。
    """
    import tkinter as tk
    from tkinter import ttk

    result = {"value": ""}
    top = tk.Toplevel(parent)
    top.title(title)
    top.transient(parent)
    top.resizable(False, False)
    box = ttk.Frame(top, padding=16)
    box.pack(fill=tk.BOTH, expand=True)
    ttk.Label(box, text=text, justify=tk.LEFT).pack(anchor=tk.W)
    row = ttk.Frame(box)
    row.pack(fill=tk.X, pady=(12, 0))

    def pick(value: str) -> None:
        result["value"] = value
        top.destroy()

    for index, (value, label) in enumerate(options):
        ttk.Button(row, text=label, command=lambda v=value: pick(v)).pack(
            side=tk.LEFT, padx=(0 if index == 0 else 8, 0)
        )
    ttk.Button(row, text="取消", command=lambda: pick("")).pack(side=tk.RIGHT)
    top.protocol("WM_DELETE_WINDOW", lambda: pick(""))
    top.update_idletasks()
    try:
        px = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_reqwidth()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - top.winfo_reqheight()) // 3
        top.geometry(f"+{max(0, px)}+{max(0, py)}")
    except tk.TclError:
        pass
    try:
        top.grab_set()
        parent.wait_window(top)
    except tk.TclError:
        pass
    try:
        parent.grab_set()
    except tk.TclError:
        pass
    return result["value"]


def format_timestamp(seconds: float) -> str:
    """秒数写成 ``hh:mm:ss.s``，保留一位小数。"""
    tenths = int(round(max(0.0, float(seconds)) * 10))
    hours, rest = divmod(tenths, 36000)
    minutes, rest = divmod(rest, 600)
    whole, tenth = divmod(rest, 10)
    return f"{hours:02d}:{minutes:02d}:{whole:02d}.{tenth}"


def _probe_seconds(path: str) -> float:
    from utility.ffmpeg_audio_processor import ffprobe_path

    try:
        out = subprocess.run(
            [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return max(0.0, float((out.stdout or "").strip() or 0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _cut_chunk(source: str, start: float, length: float, dest: str) -> bool:
    """从音频或视频里切出一小段声音，写成单声道 16k 的 wav（语音识别够用）。"""
    from utility.ffmpeg_audio_processor import ffmpeg_path

    try:
        subprocess.run(
            [
                ffmpeg_path, "-y",
                "-ss", f"{start:.3f}",
                "-t", f"{length:.3f}",
                "-i", source,
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                dest,
            ],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return os.path.isfile(dest) and os.path.getsize(dest) > 100


def _language_label(language: str) -> str:
    lang = (language or "").strip() or "zh"
    if lang in ("zh-CN", "tw", "zh-TW", "zh-tw"):
        lang = "zh"
    return config.LANGUAGES.get(lang, lang)


def _items_whisper(transcriber, wav: str, language: str, length: float) -> list[dict]:
    """本机 Whisper：每个片段有开始、结束（相对这一小段）和文字。"""
    segments = transcriber.transcribe_with_whisper(
        wav, language or "zh", False, False, False, 0.2, max(1.0, float(length))
    )
    items = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("caption") or seg.get("text") or "").strip()
        try:
            start = float(seg.get("start") or 0.0)
            end = float(seg.get("end") or start)
        except (TypeError, ValueError):
            continue
        if text:
            items.append({"start": start, "end": max(end, start), "text": text})
    return items


VOICEBOX_PIECE_MAX = 15.0   # Voicebox 只回整段文字：按停顿切成不超过这么多秒的小块，每块一行，时间就是这块的起止


def _speech_regions(wav: str, length: float) -> list[tuple[float, float]]:
    """用 ffmpeg silencedetect 找出有声音的区间（相对这个 wav 的秒数）。"""
    from utility.ffmpeg_audio_processor import ffmpeg_path

    try:
        out = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-nostats", "-i", wav,
             "-af", "silencedetect=noise=-35dB:d=0.35", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        log = out.stderr or ""
    except (OSError, subprocess.SubprocessError):
        return [(0.0, float(length))]
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    in_silence = False
    for kind, value in re.findall(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)", log):
        t = min(max(0.0, float(value)), float(length))
        if kind == "start":
            if t - cursor > 0.15:
                regions.append((cursor, t))
            in_silence = True
        else:
            cursor = t
            in_silence = False
    if not in_silence and float(length) - cursor > 0.15:
        regions.append((cursor, float(length)))  # 一直有声到最后
    return regions


def _voicebox_pieces(wav: str, length: float, max_len: float = VOICEBOX_PIECE_MAX) -> list[tuple[float, float]]:
    """把有声区间合成不超过 max_len 秒的小块；只在停顿处切，一个区间本身太长才硬切。"""
    pieces: list[tuple[float, float]] = []
    for s0, e0 in _speech_regions(wav, length):
        while e0 - s0 > max_len:
            pieces.append((s0, s0 + max_len))
            s0 += max_len
        if pieces and e0 - pieces[-1][0] <= max_len and (s0 - pieces[-1][1] < 1.2 or e0 - s0 < 0.5):
            pieces[-1] = (pieces[-1][0], e0)   # 停顿很短（或这块太短），并到上一块
        else:
            pieces.append((s0, e0))
    # 不到 0.5 秒又并不进去的小块（多半是咳嗽、杂音），不送去识别
    return [pc for pc in pieces if pc[1] - pc[0] >= 0.5]


VOICEBOX_FAIL_LIMIT = 3          # 同一个 5xx 错误连续这么多次，这次转录就不再用 Voicebox
VOICEBOX_DOWN = "VOICEBOX_DOWN:"  # _items_voicebox 返回的错误说明以它开头 = Voicebox 不能用了


def _voicebox_text(service, wav: str, language: str) -> tuple[str, list[dict], str]:
    """调 Voicebox 一次。返回 (整段文字, 服务端分段, 错误说明)。"""
    raw = service.transcribe(wav, with_timestamps=True, language=(language or None))
    if not raw:
        return "", [], str(getattr(service, "_last_transcribe_error", "") or "").strip() or "Voicebox 没有返回"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return str(raw).strip(), [], ""
    if not isinstance(data, dict):
        return str(data).strip(), [], ""
    segs = data.get("segments")
    segs = [dict(x) for x in segs if isinstance(x, dict)] if isinstance(segs, list) else []
    return str(data.get("text") or "").strip(), segs, ""


def _items_voicebox(service, wav: str, length: float, language: str = "") -> tuple[list[dict], str]:
    """Voicebox → 和本机 Whisper 一样的片段 ``[{"start", "end", "text"}]``（秒，相对这一小段）。

    Voicebox 的 /transcribe 只回 ``{"text", "duration"}``，没有分段时间（也没有开时间戳的参数）。
    所以先按停顿把这一小段切成 ≤15 秒的小块，一块调一次，这块的起止时间就是这几句的时间
    （起点是这块第一个有声的地方，精确到 ffmpeg 停顿检测）。服务端将来若带了分段，就直接用分段。
    """
    lang = (language or "").strip()
    if lang in ("zh-CN", "tw", "zh-TW", "zh-tw"):
        lang = "zh"
    pieces = _voicebox_pieces(wav, length)
    if not pieces:
        return [], ""
    items: list[dict] = []
    last_err = ""
    folder = os.path.dirname(wav)
    stem = os.path.splitext(os.path.basename(wav))[0]
    for n, (p0, p1) in enumerate(pieces):
        piece = os.path.join(folder, f"{stem}_vb{n:03d}.wav")
        lo = max(0.0, p0 - 0.1)
        if not _cut_chunk(wav, lo, (p1 + 0.15) - lo, piece):
            last_err = "切小块失败"
            continue
        try:
            text, segs, err = _voicebox_text(service, piece, lang)
        finally:
            try:
                os.remove(piece)
            except OSError:
                pass
        if err:
            last_err = err
            if err.startswith("HTTP 5"):
                state = getattr(service, "_vb_fail", None) or {"err": "", "count": 0}
                state = {"err": err, "count": state["count"] + 1 if state["err"] == err else 1}
                service._vb_fail = state
                if state["count"] >= VOICEBOX_FAIL_LIMIT:
                    return items, VOICEBOX_DOWN + err
            continue
        service._vb_fail = None
        if segs:
            for seg in segs:
                try:
                    st = lo + float(seg.get("start") or 0.0)
                    en = lo + float(seg.get("end") or seg.get("start") or 0.0)
                except (TypeError, ValueError):
                    continue
                t = str(seg.get("text") or "").strip()
                if t:
                    items.append({"start": st, "end": max(en, st), "text": t})
        elif text:
            items.append({"start": round(p0, 2), "end": round(p1, 2), "text": text})
    return items, ("" if items else last_err)


def _items_whisper_pieces(transcriber, wav: str, language: str, length: float) -> list[dict]:
    """本机 Whisper（CPU 兜底时用）：和 Voicebox 一样先按停顿切成 ≤15 秒的小块，一块一块转，
    每块的片段加上这块的起点，开始时间更准。"""
    items: list[dict] = []
    folder = os.path.dirname(wav)
    stem = os.path.splitext(os.path.basename(wav))[0]
    for n, (p0, p1) in enumerate(_voicebox_pieces(wav, length)):
        piece = os.path.join(folder, f"{stem}_wp{n:03d}.wav")
        lo = max(0.0, p0 - 0.1)
        if not _cut_chunk(wav, lo, (p1 + 0.15) - lo, piece):
            continue
        try:
            for it in _items_whisper(transcriber, piece, language, (p1 + 0.15) - lo):
                st = max(p0, lo + float(it["start"]))
                items.append({"start": st, "end": max(st, lo + float(it["end"])), "text": it["text"]})
        finally:
            for f in (piece, os.path.splitext(piece)[0] + ".srt.json"):
                try:
                    os.remove(f)
                except OSError:
                    pass
    return items


def _is_cuda_error(message: str) -> bool:
    low = (message or "").lower()
    return "cuda" in low or "out of memory" in low or "cublas" in low or "cudnn" in low


def _strip(text: str) -> str:
    """去掉标点和空白，只比较字本身。"""
    return re.sub(r"[\W_]+", "", text or "")


def _raw_lines(items: list[dict]) -> list[tuple[float, str]]:
    return [(float(it["start"]), str(it["text"]).strip()) for it in items if str(it["text"]).strip()]


def _apply_speakers(lines: list[tuple[float, Optional[int], str]], state: dict
                    ) -> list[tuple[float, Optional[int], str]]:
    """整理说话人：只在换人的那一句留下标记；第一句一定有标记；人数不超过 4；更新 state。"""
    current = state.get("current")
    top = int(state.get("max") or 0)
    out = []
    for stamp, tag, sentence in lines:
        if tag is not None and not (1 <= tag <= MAX_SPEAKERS):
            tag = None
        if tag is not None and tag > top + 1:
            tag = top + 1  # 编号必须按第一次出现的顺序
        if current is None:
            tag = tag or 1
            shown = tag
        else:
            shown = tag if (tag is not None and tag != current) else None
        if tag is not None:
            current = tag
            top = max(top, tag)
        out.append((stamp, shown, sentence))
    state["current"] = current
    state["max"] = top
    return out


def _strip_fence(answer) -> str:
    text = (answer or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("text"):
            text = text[4:].strip()
    return text


def _ask_llm(llm, system: str, user: str, check_cancel: Optional[Callable[[], None]] = None,
             what: str = "LLM", manual: Optional[Callable[[str, str, str], Optional[str]]] = None,
             mode: Optional[dict] = None) -> Optional[str]:
    """调用 LLM。自动调用失败（报错或返回空，比如 Gemini 忙返回 503）就转到手动模式。

    手动模式：``manual(system, user, what)`` 会打开 LLM 手动窗口，让人把提示词拿去处理，
    再把结果贴回来；它的返回值就是这次的回答。传入的 ``llm`` 会先自动调用（补标点用的是 Strata），
    只有这一次失败才打开手动窗口。``llm`` 为空时不调用任何模型，直接打开手动窗口。
    ``mode`` 只用来统计手动次数。
    自动调用失败后自动重试的次数由 ``config.TRANSCRIBE_LLM_RETRIES`` 决定，默认 1，就是不重试。
    手动也没拿到回答就返回 ``None``。
    """
    import time

    use_auto = llm is not None
    if use_auto:
        attempts = max(1, int(getattr(config, "TRANSCRIBE_LLM_RETRIES", 1) or 1))
        for attempt in range(1, attempts + 1):
            if check_cancel is not None:
                check_cancel()
            try:
                answer = llm.generate_text(system, user)
            except Exception as exc:  # noqa: BLE001
                answer = None
                print(f"{what}：调用出错（第 {attempt}/{attempts} 次）：{type(exc).__name__}: {exc}")
            if answer and str(answer).strip():
                return str(answer)
            if attempt < attempts:
                wait = 6 * attempt
                print(f"{what}：没有拿到回答，{wait} 秒后重试（第 {attempt}/{attempts} 次失败）…")
                for _ in range(wait):
                    if check_cancel is not None:
                        check_cancel()
                    time.sleep(1)
    if manual is None:
        return None
    if mode is not None:
        mode["manual"] = True
        mode["manual_count"] = mode.get("manual_count", 0) + 1
    if use_auto:
        print(f"{what}：自动调用没成功，转到手动模式。")
    else:
        print(f"{what}：这一步不自动调用模型，直接打开手动窗口。")
    if check_cancel is not None:
        check_cancel()
    try:
        result = manual(system, user, what)
    except InterruptedError:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"{what}：手动模式出错：{type(exc).__name__}: {exc}")
        return None
    return str(result) if result and str(result).strip() else None


class ManualBridge:
    """让后台线程里的转录，能请主线程打开「LLM 手动窗口」。

    Tk 窗口只能在主线程里开。后台线程调用 ``call``：把提示词交出去，等着。
    主线程的界面循环隔一会儿调用一次 ``serve``：有人在等，就打开手动窗口，结果交回给后台线程。
    """

    def __init__(self, cancelled: Optional[Callable[[], bool]] = None):
        import threading

        self._lock = threading.Lock()
        self._request: Optional[dict] = None
        self._threading = threading
        self._cancelled = cancelled or (lambda: False)

    def call(self, system: str, user: str, what: str) -> Optional[str]:
        """后台线程用：等主线程把手动窗口的结果送回来。"""
        return self._wait({"system": system, "user": user, "what": what})

    def call_file(self, system: str, user: str, what: str, *, images=None,
                  cli_kind: str = "video", file_dest_dir: str = "", extra: Optional[dict] = None) -> Optional[str]:
        """后台线程用：结果是一个文件（如 CLI自动 生成的 mp4）。返回文件路径，拿不到返回 None。

        主线程开的是带图的手动窗口（``LLMApi.show_manual_window(cli_kind=..., file_dest_dir=...)``）；
        手动时也可以在窗口里点「选视频文件…」交回一个文件。
        """
        result = self._wait({"system": system, "user": user, "what": what, "images": list(images or []),
                             "cli_kind": cli_kind, "file_dest_dir": file_dest_dir, "want_file": True,
                             "extra": dict(extra or {})})
        return str(result) if result else None

    def _wait(self, fields: dict):
        request = dict(fields)
        request.update({"event": self._threading.Event(), "result": None, "taken": False})
        with self._lock:
            self._request = request
        while not request["event"].wait(0.3):
            if self._cancelled():
                with self._lock:
                    if self._request is request and not request["taken"]:
                        self._request = None
                        raise InterruptedError("已取消")
        return request["result"]

    def pending(self) -> bool:
        with self._lock:
            return self._request is not None and not self._request["taken"]

    def serve(self, before: Optional[Callable[[str], None]] = None,
              after: Optional[Callable[[], None]] = None) -> bool:
        """主线程用：有人在等就打开手动窗口。处理了一次返回 True。

        ``before(说明)`` 在窗口打开前调用（比如放开进度窗口的独占），``after()`` 在窗口关掉后调用。
        """
        with self._lock:
            request = self._request
            if request is None or request["taken"]:
                return False
            request["taken"] = True
        result = None
        try:
            if before is not None:
                before(request["what"])
            from utility import llm_api

            api = llm_api.LLMApi(llm_api.MANUAL)
            if request.get("want_file"):
                resp = api.show_manual_window(
                    request["system"], request["user"], images=request.get("images"),
                    cli_kind=request.get("cli_kind"), file_dest_dir=request.get("file_dest_dir"),
                    extra=request.get("extra"),
                )
                result = str(resp) if isinstance(resp, llm_api.FileResult) else None
            else:
                result = api.generate_text(request["system"], request["user"])
        except Exception as exc:  # noqa: BLE001
            print(f"手动窗口出错：{type(exc).__name__}: {exc}")
            result = None
        finally:
            try:
                if after is not None:
                    after()
            finally:
                request["result"] = result
                with self._lock:
                    if self._request is request:
                        self._request = None
                request["event"].set()
        return True


# 一次交给 Strata 的补标点长度：两分钟。10 分钟整段送进去时，答不完或开头多了一句说明，
# 整段都会被退回，文字稿里就只剩没有标点的识别原文。
# 字数上限只挡住特别密的一段，正常语速两分钟不会先被字数切开。
_PUNCT_MAX_CHARS = 1500
_PUNCT_MAX_SECONDS = 120.0
_PUNCT_CLOCK_RE = re.compile(
    r"^\s*\[\s*(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)\s*\]\s*(.+?)\s*$"
)
_SENTENCE_END_RE = re.compile(r"[。！？!?；;]")


def _parse_punct_line(line: str):
    """补标点的一行。``[秒]`` 或 ``[hh:mm:ss.s]`` 都可以。对不上返回 None。"""
    clock = _PUNCT_CLOCK_RE.match(line)
    if clock:
        hours, minutes, seconds, text = clock.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds), text
    match = _LINE_RE.match(line)
    if match:
        return float(match.group(1)), match.group(2)
    return None


def _text_needs_sentence_breaks(text: str) -> bool:
    """一段比较长、却几乎没有句号问号，就是还没补上标点。"""
    bare = _strip(text)
    if len(bare) < 40:
        return False
    return len(_SENTENCE_END_RE.findall(text or "")) < max(1, len(bare) // 80)


def _punct_slices(items: list[dict]) -> list[list[dict]]:
    """按两分钟切开，避免一次把 10 分钟都交给 Strata。"""
    if not items:
        return []
    slices: list[list[dict]] = []
    start = 0
    chars = 0
    origin = float(items[0].get("start") or 0)
    for index, item in enumerate(items):
        size = len(str(item.get("text") or "")) + 16
        span = float(item.get("end") or item.get("start") or 0) - origin
        if index > start and (chars + size > _PUNCT_MAX_CHARS or span > _PUNCT_MAX_SECONDS):
            slices.append(items[start:index])
            start = index
            chars = 0
            origin = float(item.get("start") or 0)
        chars += size
    if start < len(items):
        slices.append(items[start:])
    return slices


def _punctuate_with_times(items: list[dict], language: str, ask,
                          stats: Optional[dict] = None) -> list[tuple[float, str]]:
    """一批片段交给 LLM：补标点、一句一行、每行开头写开始秒数。出问题就退回原始片段。

    10 分钟的识别结果会先切成两分钟一段再交给 Strata。某一小段没补上标点，
    只退回这一小段，不把整段 10 分钟都退回。
    ``ask`` 是 ``None`` 表示没有 LLM 可用。
    ``stats["punct_batches"]`` 记一共处理了几批，``stats["punct_fallback"]`` 记几批退回了原始片段。
    """
    if not items:
        return []
    slices = _punct_slices(items)
    if len(slices) > 1:
        out: list[tuple[float, str]] = []
        for piece in slices:
            out.extend(_punctuate_one(piece, language, ask, stats))
        return out
    return _punctuate_one(items, language, ask, stats)


def _punctuate_one(items: list[dict], language: str, ask,
                   stats: Optional[dict] = None, *, retry: bool = True) -> list[tuple[float, str]]:
    raw = _raw_lines(items)

    def fallback() -> list[tuple[float, str]]:
        if stats is not None:
            stats["punct_fallback"] = stats.get("punct_fallback", 0) + 1
        return raw

    status, lines = _punctuate_call(items, language, ask, stats)
    if status == "down":
        print("带时间的标点处理失败，这一小段用原始片段。")
        return fallback()
    source = "".join(str(it.get("text") or "") for it in items)
    bare = status == "ok" and _text_needs_sentence_breaks(source) and _text_needs_sentence_breaks(
        "".join(sentence for _stamp, sentence in lines)
    )
    if status != "ok" or bare:
        if retry and status != "down" and len(items) >= 2:
            print("带时间的标点处理：这一小段没补上，拆成两段再交给 Strata。")
            mid = len(items) // 2
            return (
                _punctuate_one(items[:mid], language, ask, stats, retry=False)
                + _punctuate_one(items[mid:], language, ask, stats, retry=False)
            )
        if bare:
            print("带时间的标点处理：没有加上标点，这一小段用原始片段。")
        return fallback()
    return lines


def _punctuate_call(items: list[dict], language: str, ask,
                    stats: Optional[dict] = None) -> tuple[str, list[tuple[float, str]]]:
    """返回 ``("ok", 句子)``、``("bad", [])`` 或 ``("down", [])``。``down`` 是 Strata 没有回答。"""
    if stats is not None:
        stats["punct_batches"] = stats.get("punct_batches", 0) + 1
    if ask is None:
        return "down", []
    user = "\n".join(f"[{it['start']:.1f}-{it['end']:.1f}] {it['text']}" for it in items)
    system = config_prompt.TRANSCRIPT_TIMESTAMP_SYSTEM_PROMPT.format(language=_language_label(language))
    answer = ask(system, user, "补标点")
    if answer is None:
        return "down", []
    lines: list[tuple[float, str]] = []
    started = False
    for line in _strip_fence(answer).splitlines():
        if not line.strip():
            continue
        parsed = _parse_punct_line(line)
        if parsed is None:
            if not started:
                continue
            print("带时间的标点处理：有一行没有时间戳。")
            return "bad", []
        started = True
        lines.append(parsed)
    if not lines:
        return "bad", []
    lo = min(float(it["start"]) for it in items) - 1.0
    hi = max(float(it["end"]) for it in items) + 2.0
    last = lo
    for stamp, _sentence in lines:
        if stamp < last - 0.05 or stamp > hi:
            print("带时间的标点处理：时间对不上。")
            return "bad", []
        last = max(last, stamp)
    before = len(_strip("".join(str(it["text"]) for it in items)))
    after = len(_strip("".join(sentence for _t, sentence in lines)))
    if before and not (0.85 <= after / before <= 1.15):
        print("带时间的标点处理：字数对不上。")
        return "bad", []
    return "ok", lines


def _speaker_windows(lines: list[tuple[float, str]], max_chars: int) -> list[tuple[int, int]]:
    """把全部句子按字数分成若干窗口（含头不含尾的下标）。够短就只有一个窗口。"""
    windows: list[tuple[int, int]] = []
    start = 0
    total = 0
    for index, (_stamp, sentence) in enumerate(lines):
        size = len(sentence) + 16
        if index > start and total + size > max_chars:
            windows.append((start, index))
            start = index
            total = 0
        total += size
    if start < len(lines):
        windows.append((start, len(lines)))
    return windows


def _label_speakers(lines: list[tuple[float, str]], language: str, ask,
                    check_cancel: Optional[Callable[[], None]] = None,
                    stats: Optional[dict] = None
                    ) -> list[tuple[float, Optional[int], str]]:
    """全部句子都带好时间之后，单独调用 LLM，按整段对话的上下文判断每一句是谁说的。

    LLM 对每个句子编号回答说话人编号（``12: 2``）。回答缺的句子沿用上一句的人。
    整个调用失败时，所有句子算同一个人（<1>）。返回 ``(秒, 只在换人处才有的说话人, 句子)``。
    """
    state = {"current": None, "max": 0}
    if not lines:
        return []
    speakers: list[int] = [0] * len(lines)  # 0 表示 LLM 没回答
    if ask is not None:
        max_chars = max(2000, int(getattr(config, "TRANSCRIBE_SPEAKER_MAX_CHARS", 40000) or 40000))
        for lo, hi in _speaker_windows(lines, max_chars):
            if check_cancel is not None:
                check_cancel()
            context_lines = []
            known = [s for s in speakers[max(0, lo - 12):lo] if s]
            for j in range(max(0, lo - 12), lo):
                if speakers[j]:
                    context_lines.append(f"{j + 1}: <{speakers[j]}> {lines[j][1]}")
            top = max([s for s in speakers[:lo] if s] or [0])
            if lo == 0 or not known:
                context = "This is the beginning of the recording. Speaker numbers start at 1."
            else:
                context = (f"This is a continuation. The lines before the first line below are already labelled "
                           f"(shown first, for context only; do not answer for them). Speakers seen so far: 1 to {top}.")
            system = config_prompt.TRANSCRIPT_SPEAKER_SYSTEM_PROMPT.format(
                language=_language_label(language), context=context
            )
            body = []
            if context_lines:
                body.append("=== Already labelled (context only) ===")
                body.extend(context_lines)
                body.append("=== Label these lines ===")
            for j in range(lo, hi):
                body.append(f"{j + 1}: [{format_timestamp(lines[j][0])}] {lines[j][1]}")
            if stats is not None:
                stats["speaker_windows"] = stats.get("speaker_windows", 0) + 1
            answer = ask(system, "\n".join(body), "说话人判断")
            if answer is None:
                print("说话人判断失败，这一部分当作同一个人。")
                if stats is not None:
                    stats["speaker_failed"] = stats.get("speaker_failed", 0) + 1
                continue
            for line in _strip_fence(answer).splitlines():
                match = _SPEAKER_LINE_RE.match(line)
                if not match:
                    continue
                number = int(match.group(1)) - 1
                who = int(match.group(2))
                if lo <= number < hi and 1 <= who <= MAX_SPEAKERS:
                    speakers[number] = who
            answered = sum(1 for s in speakers[lo:hi] if s)
            if answered < (hi - lo) * 0.5:
                print(f"说话人判断：只回答了 {answered}/{hi - lo} 句，其余沿用上一句的人。")
                if stats is not None:
                    stats["speaker_failed"] = stats.get("speaker_failed", 0) + 1
    labelled = []
    current = 0
    for (stamp, sentence), who in zip(lines, speakers):
        if who:
            current = who
        labelled.append((stamp, current or None, sentence))
    return _apply_speakers(labelled, state)


def transcribe_media_with_timestamps(
    path: str,
    *,
    engine: str,
    pid: str,
    language: str = "",
    out_dir: Optional[str] = None,
    chunk_seconds: Optional[float] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    notes: Optional[list] = None,
    manual_llm: Optional[Callable[[str, str, str], Optional[str]]] = None,
) -> str:
    """把音频或视频转成每句带时间戳的文字，写成 txt，返回 txt 的路径。

    出错抛 ``RuntimeError``，用户取消抛 ``InterruptedError``。
    ``progress(已完成的小段数, 小段总数, 说明)`` 会在转录过程中被调用。
    补标点、判断说话人都要调用 LLM。自动调用(Strata)某一次失败，这一次就转到手动模式：
    调用 ``manual_llm(系统提示词, 用户提示词, 说明)`` 打开 LLM 手动窗口，让人处理后把结果贴回来，
    下一次调用仍然先试自动。不给 ``manual_llm`` 就不转手动，失败的那一步用没处理的结果。
    文字稿虽然写出来了，但 LLM 那几步（补标点、判断说话人）没成功时，会往 ``notes`` 里加说明文字，
    调用方应当告诉用户。
    """
    if engine not in ("whisper", "voicebox"):
        raise RuntimeError(f"不认识的转录方式：{engine!r}")
    if not path or not os.path.isfile(path):
        raise RuntimeError("找不到要转录的文件。")
    total_seconds = _probe_seconds(path)
    if total_seconds <= 0.2:
        raise RuntimeError("读不出这个文件有多长。")
    size = float(chunk_seconds or getattr(config, "TRANSCRIBE_CHUNK_SECONDS", 600) or 600)
    size = max(5.0, size)
    count = max(1, int(-(-total_seconds // size)))

    def report(done: int, message: str) -> None:
        if progress is not None:
            try:
                progress(done, count, message)
            except Exception:  # noqa: BLE001
                pass

    def check_cancel() -> None:
        if cancelled is not None and cancelled():
            raise InterruptedError("已取消")

    report(0, "正在准备转录…")
    transcriber = None
    service = None
    if engine == "whisper":
        from utility import audio_transcriber

        transcriber = audio_transcriber.AudioTranscriber(pid, model_size="small", device="cuda")
    else:  # voicebox
        from utility.voicebox_speech_service import VoiceboxService

        service = VoiceboxService(pid)

    llm = None
    try:
        from utility import llm_api

        llm = llm_api.LLMApi(llm_api.MODEL_SIMPLE)      # 补标点：简单，用 Strata
        # 这里失败时由 ManualBridge 转手动（主线程），LLMApi 自己不再开手动窗口，免得开两次。
        llm.manual_fallback = False
    except Exception as exc:  # noqa: BLE001
        print(f"LLM 没有准备好，转录结果不补标点、不按句分行：{exc}")

    mode: dict = {}
    ask = None
    if llm is not None or manual_llm is not None:
        def ask(system: str, user: str, what: str) -> Optional[str]:
            return _ask_llm(llm, system, user, check_cancel, what, manual_llm, mode)

    # 判断说话人：不再调 DeepSeek，直接走手动窗口（ManualBridge，主线程打开）。
    ask_hard = None
    if manual_llm is not None:
        def ask_hard(system: str, user: str, what: str) -> Optional[str]:
            return _ask_llm(None, system, user, check_cancel, what, manual_llm, mode)

    batch_size = max(1, int(getattr(config, "TRANSCRIBE_LLM_BATCH_CHUNKS", 1) or 1))
    work_dir = tempfile.mkdtemp(prefix="transcribe_")
    result_lines: list[tuple[float, str]] = []
    stats: dict = {}
    pending: list[dict] = []
    last_error = ""
    got_any = False

    def flush() -> None:
        nonlocal pending
        if pending:
            result_lines.extend(_punctuate_with_times(pending, language, ask, stats))
            pending = []

    try:
        for index in range(count):
            check_cancel()
            start = index * size
            length = min(size, total_seconds - start)
            if length < 0.3:
                report(index + 1, "")
                continue
            report(index, f"转录第 {index + 1} / {count} 段（{format_timestamp(start)}）")
            wav = os.path.join(work_dir, f"chunk_{index:04d}.wav")
            if not _cut_chunk(path, start, length, wav):
                last_error = "有一段声音没有切出来。"
                continue
            items = []
            if transcriber is not None:
                if getattr(transcriber, "cpu_pieces", False):
                    items = _items_whisper_pieces(transcriber, wav, language, length)
                else:
                    items = _items_whisper(transcriber, wav, language, length)
                werr = str(getattr(transcriber, "last_error", "") or "")
                if not items and _is_cuda_error(werr):
                    # 本机显卡显存不够（或别的 CUDA 错误）：这一段和后面所有段都改用 Voicebox。
                    print(f"⚠️ 本机 Whisper 出 CUDA 错误（{werr[:160]}），"
                          f"从第 {index + 1} 段起改用 Voicebox 转录。")
                    if notes is not None:
                        notes.append("本机 Whisper 显存不够，这次转录中途改用了 Voicebox。")
                    try:
                        engine_x = getattr(transcriber, "_whisperx_engine", None)
                        transcriber._whisperx_engine = None
                        del engine_x
                        import gc
                        import torch

                        gc.collect()
                        torch.cuda.empty_cache()
                    except Exception:  # noqa: BLE001
                        pass
                    transcriber = None
                    for leftover in (os.path.splitext(wav)[0] + ".srt.json",):
                        try:
                            os.remove(leftover)
                        except OSError:
                            pass
                    from utility.voicebox_speech_service import VoiceboxService

                    service = VoiceboxService(pid)
                elif werr:
                    last_error = werr
            if transcriber is None:
                items, err = _items_voicebox(service, wav, length, language)
                if err.startswith(VOICEBOX_DOWN):
                    reason = err[len(VOICEBOX_DOWN):]
                    print(f"⚠️ Voicebox 连续 {VOICEBOX_FAIL_LIMIT} 次同样出错（{reason[:160]}），"
                          f"从第 {index + 1} 段起改用本机 Whisper（CPU，int8）转录，会慢一些。")
                    if notes is not None:
                        notes.append(f"Voicebox 服务端出错（{reason[:120]}），这次转录改用了本机 CPU Whisper。")
                    from utility import audio_transcriber

                    transcriber = audio_transcriber.AudioTranscriber(pid, model_size="small", device="cpu")
                    transcriber.cpu_pieces = True
                    items = _items_whisper_pieces(transcriber, wav, language, length)
                    werr = str(getattr(transcriber, "last_error", "") or "")
                    if werr:
                        last_error = werr
                elif err:
                    last_error = err
            for item in items:
                item["start"] = start + float(item["start"])
                item["end"] = start + float(item["end"])
                pending.append(item)
            if items:
                got_any = True
            if (index + 1) % batch_size == 0:
                check_cancel()
                report(index + 1, "补标点、按句标时间…")
                flush()
            else:
                report(index + 1, "")
        check_cancel()
        report(count, "补标点、按句标时间…")
        flush()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if not got_any or not result_lines:
        raise RuntimeError("没有转出文字。" + (f" {last_error[:240]}" if last_error else ""))

    # 所有句子和时间都弄好、拼在一起之后，最后单独做一次说话人判断（看得到整段对话的上下文）。
    check_cancel()
    report(count, "判断每一句是谁在说话…")
    labelled_lines = _label_speakers(result_lines, language, ask_hard, check_cancel, stats)
    if notes is not None:
        if ask is None:
            notes.append("LLM 没有准备好：文字稿没有补标点，也没有判断说话人。")
        else:
            if stats.get("punct_fallback"):
                notes.append(
                    f"补标点、分句：{stats.get('punct_batches', 0)} 批里有 {stats['punct_fallback']} 批没成功"
                    "（模型忙、手动窗口里取消了，或返回的格式不对），那几批用的是语音识别的原始分段，没有标点。"
                )
            if stats.get("speaker_failed"):
                notes.append(
                    "判断说话人没有成功（模型忙、手动窗口里取消了，或返回的格式不对）：文字稿里没有人物切换，"
                    "或者只有一部分有。"
                )
        if notes:
            notes.append("等模型不忙的时候，重新转录一次就好。")

    folder = out_dir or tempfile.gettempdir()
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    dest = os.path.join(folder, f"{stem}.txt")  # 和媒体同名，只是扩展名是 .txt
    with open(dest, "w", encoding="utf-8") as f:
        for stamp, speaker, sentence in labelled_lines:
            tag = f"<{speaker}> " if speaker else ""
            f.write(f"[{format_timestamp(stamp)}] {tag}{sentence}\n")
    return dest


def transcribe_with_progress_dialog(parent, media_path: str, *, pid: str = "", language: str = "",
                                    out_dir: Optional[str] = None) -> tuple[str, str]:
    """弹一个带进度条和「取消」的小窗口，在后台转录。返回 ``(文字稿路径, 错误说明)``。

    成功时错误说明是空字符串；用户取消时路径为空、错误说明是 ``"cancelled"``。
    用哪种转录方式由 ``config.TRANSCRIBE_ENGINE`` 决定。
    """
    import threading
    import tkinter as tk
    from tkinter import ttk

    engine = str(getattr(config, "TRANSCRIBE_ENGINE", "whisper") or "").strip().lower()
    if engine not in ("whisper", "voicebox"):
        return "", f"config.py 里的 TRANSCRIBE_ENGINE 写的是 {engine!r}，只能是 \"whisper\" 或 \"voicebox\"。"

    state = {"done": False, "cancel": False, "error": "", "path": "", "message": "正在准备转录…", "ratio": 0.0}
    notes: list[str] = []
    top = tk.Toplevel(parent)
    top.title("转录中")
    top.transient(parent)
    top.resizable(False, False)
    box = ttk.Frame(top, padding=14)
    box.pack(fill=tk.BOTH, expand=True)
    label = ttk.Label(box, text=state["message"], width=44, justify=tk.LEFT)
    label.pack(anchor=tk.W)
    bar = ttk.Progressbar(box, length=320, mode="determinate", maximum=1, value=0)
    bar.pack(fill=tk.X, pady=(8, 8))

    def cancel() -> None:
        state["cancel"] = True
        label.config(text="正在取消…")

    ttk.Button(box, text="取消", command=cancel).pack(anchor=tk.E)
    top.protocol("WM_DELETE_WINDOW", cancel)
    top.update_idletasks()
    try:
        px = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_reqwidth()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - top.winfo_reqheight()) // 3
        top.geometry(f"+{max(0, px)}+{max(0, py)}")
    except tk.TclError:
        pass
    try:
        top.grab_set()
    except tk.TclError:
        pass

    def on_progress(done: int, total: int, message: str) -> None:
        if message:
            state["message"] = message
        state["ratio"] = (done / total) if total else 0.0

    bridge = ManualBridge(lambda: state["cancel"])

    def work() -> None:
        try:
            state["path"] = transcribe_media_with_timestamps(
                media_path, engine=engine, pid=pid, language=language, out_dir=out_dir,
                progress=on_progress, cancelled=lambda: state["cancel"], notes=notes,
                manual_llm=bridge.call,
            )
        except InterruptedError:
            state["error"] = "cancelled"
        except Exception as exc:  # noqa: BLE001
            state["error"] = str(exc) or type(exc).__name__
        state["done"] = True

    def before_manual(what: str) -> None:
        state["message"] = f"自动调用没成功（{what}），请在手动窗口里处理…"
        try:
            label.config(text=state["message"])
            top.grab_release()
        except tk.TclError:
            pass

    def after_manual() -> None:
        try:
            top.grab_set()
        except tk.TclError:
            pass

    threading.Thread(target=work, daemon=True).start()
    try:
        while not state["done"]:
            try:
                if bridge.pending():
                    bridge.serve(before_manual, after_manual)
                label.config(text=state["message"])
                bar.config(value=float(state["ratio"]))
                top.update()
            except tk.TclError:
                state["cancel"] = True
                break
            import time
            time.sleep(0.05)
    finally:
        try:
            top.grab_release()
            top.destroy()
        except tk.TclError:
            pass
        try:
            parent.grab_set()
        except tk.TclError:
            pass
    if not state["done"]:
        return "", "cancelled"
    if not state["error"] and notes:
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                "转录：有一部分没做好",
                "文字稿已经写出来了，但是：\n\n" + "\n".join(notes),
                parent=parent,
            )
        except tk.TclError:
            pass
    return (state["path"], "") if not state["error"] else ("", state["error"])


_TIMED_LINE_RE = re.compile(
    r"^\s*\[(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)\]\s*(?:[<＜](\d+)[>＞]\s*)?(.*\S)\s*$"
)


def parse_timed_transcript(text: str) -> list[dict]:
    """读文字稿。每一行 ``[hh:mm:ss.s]``，换人时才有 ``<N>``。

    返回的每一句都带上当时是谁在说（没写标记的沿用上一句）。
    """
    rows: list[dict] = []
    current = 0
    for line in (text or "").splitlines():
        match = _TIMED_LINE_RE.match(line)
        if not match:
            continue
        hours, minutes, seconds, who, sentence = match.groups()
        stamp = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if who:
            current = int(who)
        elif not current:
            current = 1
        sentence = (sentence or "").strip()
        if sentence:
            rows.append({"start": stamp, "speaker": current, "text": sentence})
    return rows


def read_timed_transcript_text(media_path: str = "", video_detail: dict | None = None) -> str:
    """找这份媒体的文字稿。概览用旁边的同名 txt；这条自己的媒体再用记下的 transcript。"""
    candidates: list[str] = []
    media = (media_path or "").strip()
    if media:
        candidates.append(os.path.splitext(media)[0] + ".txt")
    if isinstance(video_detail, dict):
        stored = str(video_detail.get("transcript") or "").strip()
        story_media = str(video_detail.get("media") or "").strip()
        same = False
        if media and story_media:
            try:
                same = os.path.normcase(os.path.abspath(media)) == os.path.normcase(os.path.abspath(story_media))
            except OSError:
                same = False
        if stored and (not media or same):
            candidates.append(stored)
        if story_media and (not media or same):
            candidates.append(os.path.splitext(story_media)[0] + ".txt")
    seen: set[str] = set()
    for path in candidates:
        key = os.path.normcase(os.path.abspath(path)) if path else ""
        if not key or key in seen or not os.path.isfile(path):
            continue
        seen.add(key)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if parse_timed_transcript(text):
            return text
    return ""


def _scene_bounds(scenes: list) -> list[tuple[dict, float, float]] | None:
    """每一场的起止秒。缺 start 就没法按文字稿切，返回 None。缺 end 用下一场的 start。"""
    bounds = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        try:
            start = float(scene.get("start"))
        except (TypeError, ValueError):
            return None
        try:
            end = float(scene.get("end"))
        except (TypeError, ValueError):
            end = None
        bounds.append([scene, start, end])
    if not bounds:
        return None
    for index, item in enumerate(bounds):
        if item[2] is None:
            if index + 1 < len(bounds):
                item[2] = bounds[index + 1][1]
            else:
                item[2] = item[1]
    return [(scene, start, float(end)) for scene, start, end in bounds]


_SENTENCE_END = "。！？!?.;；…"
_TRAILING_CLOSERS = "\"'”’」』）)]》"
_SOFT_END = "，,、"


def _as_sentence(text: str) -> str:
    """文字稿一行就是一句。抄进 speaking 时，句尾没有收句标点就补上，断句才不会被拼没。

    行里原有的逗号、问号、句号保持不动。已经收住的句子不再加第二个句号。
    """
    body = (text or "").strip()
    if not body:
        return body
    trimmed = body.rstrip(_TRAILING_CLOSERS)
    closers = body[len(trimmed):]
    stem = trimmed.rstrip()
    if stem and stem[-1] in _SOFT_END:
        stem = stem[:-1].rstrip()
    if not stem:
        return body
    if stem[-1] in _SENTENCE_END:
        return body
    mark = "。" if any("\u4e00" <= ch <= "\u9fff" for ch in stem) else "."
    return stem + mark + closers


def _sentence_in_scene(stamp: float, start: float, end: float, is_last: bool) -> bool:
    """一句归到「开始时间落在这一场里」的场。边界上的那句归下一场。"""
    if stamp < start - 0.05:
        return False
    if is_last:
        return stamp <= end + 0.05
    return stamp < end - 0.05


def apply_verbatim_speaking(scenes: list, transcript_text: str) -> tuple[int, int]:
    """用文字稿原句替换每一场的 speaking。模型写的讲话丢掉。

    只保留谁在说：一场开头写当时的 ``<N>``，换人再写。字和行里已有的标点保持原样。
    每一行是一句；句尾没有句号时补上，拼进同一场时断句还在。
    返回 (写回的场数, 没有落到任何一场的句数)。对不上时间就不改。
    """
    rows = parse_timed_transcript(transcript_text)
    bounds = _scene_bounds(scenes) if rows else None
    if not rows or not bounds:
        return 0, 0
    used = [False] * len(rows)
    replaced = 0
    last = len(bounds) - 1
    for index, (scene, start, end) in enumerate(bounds):
        picked = []
        for row_i, row in enumerate(rows):
            if _sentence_in_scene(row["start"], start, end, index == last):
                picked.append(row)
                used[row_i] = True
        if not picked:
            continue
        parts: list[str] = []
        previous = None
        for row in picked:
            speaker = int(row["speaker"] or 1)
            sentence = _as_sentence(row["text"])
            if speaker != previous:
                parts.append(f"<{speaker}> {sentence}")
                previous = speaker
            else:
                parts.append(sentence)
        scene["speaking"] = " ".join(parts).strip()
        scene.pop("speaking_timing", None)
        replaced += 1
    missed = sum(1 for flag in used if not flag)
    return replaced, missed


# ---- t434u: 一场讲话最多 115 个字（约 25 秒），超了按句拆成连续的几场 ----
SCENE_SPEAKING_MAX_UNITS = 115  # 汉字 1 个算 1；英文词 / 数字串 1 个算 2；标点不算
SCENE_SPEAKING_MAX_SECONDS = 25.0  # 第二道检查：按文字稿时间，一场不超过 25 秒（单独一句超了没法再拆）
_UNIT_MARK_RE = re.compile(r"[<＜]\d+s?[>＞]")
_UNIT_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_UNIT_WORD_RE = re.compile(r"[A-Za-z0-9\u00c0-\u024f]+(?:['’][A-Za-z]+)*")
_CLAUSE_RE = re.compile(r"[^，,、；;：:。！？!?…]+[，,、；;：:。！？!?…]*[\"'”’」』）)\]》]*")


def speaking_units(text: str) -> int:
    """t434u: 讲话字数（汉字 1 个 = 1；英文词、数字串 1 个 = 2；标点和 <N> 标记不算）。"""
    body = _UNIT_MARK_RE.sub(" ", str(text or ""))
    cjk = len(_UNIT_CJK_RE.findall(body))
    words = len(_UNIT_WORD_RE.findall(_UNIT_CJK_RE.sub(" ", body)))
    return cjk + 2 * words


def _balanced_groups(units: list, k: int) -> list:
    """把 units 按顺序分成 k 组，最大的一组尽量小。返回每组的 (起, 止) 下标。"""
    n = len(units)
    pre = [0]
    for u in units:
        pre.append(pre[-1] + u)
    inf = float("inf")
    best = [[inf] * (n + 1) for _ in range(k + 1)]
    cut = [[0] * (n + 1) for _ in range(k + 1)]
    best[0][0] = 0
    for g in range(1, k + 1):
        for j in range(g, n + 1):
            for i in range(g - 1, j):
                v = max(best[g - 1][i], pre[j] - pre[i])
                if v < best[g][j]:
                    best[g][j], cut[g][j] = v, i
    out, j = [], n
    for g in range(k, 0, -1):
        i = cut[g][j]
        out.append((i, j))
        j = i
    return out[::-1]


def _hard_chunks(text: str, max_units: int) -> list:
    """一个分句本身就超过上限（没有标点）：按字 / 词硬切成大致一样长的几段。"""
    tokens = re.findall(r"[A-Za-z0-9\u00c0-\u024f]+(?:['’][A-Za-z]+)*\s*|\S\s*|\s+", text)
    units = [speaking_units(t) for t in tokens]
    k = max(1, -(-sum(units) // max_units))
    return ["".join(tokens[a:b]) for a, b in _balanced_groups(units, k)]


def _split_long_sentence(text: str, max_units: int) -> list:
    """一句超过上限：在分句标点（，、；：。！？）后面切，每段不超过上限，尽量一样长。"""
    clauses = [c for c in _CLAUSE_RE.findall(text) if c.strip()] or [text]
    pieces: list = []
    for clause in clauses:
        if speaking_units(clause) > max_units:
            pieces.extend(_hard_chunks(clause, max_units))
        else:
            pieces.append(clause)
    units = [speaking_units(p) for p in pieces]
    k = max(1, -(-sum(units) // max_units))
    while True:
        groups = _balanced_groups(units, k)
        if all(sum(units[a:b]) <= max_units for a, b in groups):
            return ["".join(pieces[a:b]).strip() for a, b in groups]
        k += 1


def _join_speech(left: str, right: str) -> str:
    if not left:
        return right
    if _UNIT_CJK_RE.search(left[-1:]) or left[-1:] in "，、；：。！？…」』）》" or _UNIT_CJK_RE.search(right[:1]):
        return left + right
    return left + " " + right


def _scene_pieces(picked: list, scene_end: float, max_units: int) -> list:
    """这一场的句子 → 片段 [{start, end, speaker, text, units, row, last}]。超长的句子拆成几段（时间按字数分）。"""
    out = []
    for i, row in enumerate(picked):
        s = float(row["start"])
        e = float(picked[i + 1]["start"]) if i + 1 < len(picked) else max(float(scene_end), s)
        text = row["text"]
        parts = [text] if speaking_units(text) <= max_units else _split_long_sentence(text, max_units)
        total = sum(speaking_units(p) for p in parts) or 1
        done = 0
        for j, part in enumerate(parts):
            u = speaking_units(part)
            a = s + (e - s) * done / total
            done += u
            b = s + (e - s) * done / total
            out.append({"start": a, "end": b, "speaker": int(row["speaker"] or 1), "text": part,
                        "units": u, "row": i, "last": j == len(parts) - 1})
    return out


def _plan_scene_split(pieces: list, start: float, end: float, max_units: int, max_seconds: float) -> list:
    """最少分几场：每场不超过 max_units 字；时间第二道检查（一场超过 max_seconds 秒且不止一段时再多分）。"""
    n = len(pieces)
    units = [p["units"] for p in pieces]

    def span(a, b):
        s = start if a == 0 else pieces[a]["start"]
        e = end if b == n else pieces[b]["start"]
        return e - s

    def ok(groups):
        return all(sum(units[a:b]) <= max_units and (b - a == 1 or span(a, b) <= max_seconds + 0.05)
                   for a, b in groups)

    if ok([(0, n)]):
        return [(0, n)]
    k = max(2, -(-sum(units) // max_units))
    while k < n:
        groups = _balanced_groups(units, k)
        if ok(groups):
            return groups
        k += 1
    return [(i, i + 1) for i in range(n)]


def _speaking_text(pieces: list) -> str:
    """片段拼回讲话：一场开头写 <N>，换人再写；整句之间空一格，同一句拆开的段直接接上。"""
    parts: list = []
    previous = None
    prev_last = True
    for p in pieces:
        text = _as_sentence(p["text"]) if p["last"] else p["text"].strip()
        if p["speaker"] != previous:
            parts.append(f"<{p['speaker']}> {text}")
            previous = p["speaker"]
        elif prev_last:
            parts[-1] = parts[-1] + " " + text
        else:
            parts[-1] = _join_speech(parts[-1], text)
        prev_last = p["last"]
    return " ".join(parts).strip()


def split_long_transcript_scenes(scenes: list, transcript_text: str, *,
                                 max_units: int = SCENE_SPEAKING_MAX_UNITS,
                                 max_seconds: float = SCENE_SPEAKING_MAX_SECONDS,
                                 groups_out: list | None = None) -> tuple[list, int]:
    """t434u: 按文字稿写回讲话以后、人物对位以前：讲话超过 max_units 字（或超过 max_seconds 秒）的场，
    按句子拆成连续的几场（尽量一样长；单独一句超了就在分句标点处切）。拆出来的场沿用原场的故事、画面、
    人物等全部字段，只改 start / end / speaking。返回 (新的场景列表, 多出来的场数)。对不上时间就原样返回。
    t436u: groups_out 给了就把每个拆开的场记成 (原场在 scenes 里的下标, [拆出来的几场])。"""
    rows = parse_timed_transcript(transcript_text)
    bounds = _scene_bounds(scenes) if rows else None
    if not rows or not bounds:
        return scenes, 0
    import copy as _copy

    out: list = []
    added = 0
    last = len(bounds) - 1
    by_id = {id(scene): (start, end, index) for index, (scene, start, end) in enumerate(bounds)}
    for scene_pos, scene in enumerate(scenes or []):
        info = by_id.get(id(scene)) if isinstance(scene, dict) else None
        if info is None:
            out.append(scene)
            continue
        start, end, index = info
        picked = [row for row in rows if _sentence_in_scene(row["start"], start, end, index == last)]
        if not picked:
            out.append(scene)
            continue
        pieces = _scene_pieces(picked, end, max_units)
        groups = _plan_scene_split(pieces, start, end, max_units, max_seconds)
        if len(groups) == 1:
            out.append(scene)
            continue
        n = len(pieces)
        made = []
        for a, b in groups:
            part = _copy.deepcopy(scene)
            part["start"] = round(start if a == 0 else pieces[a]["start"], 2)
            part["end"] = round(end if b == n else pieces[b]["start"], 2)
            part["speaking"] = _speaking_text(pieces[a:b])
            part.pop("speaking_timing", None)
            out.append(part)
            made.append(part)
        if groups_out is not None:
            groups_out.append((scene_pos, made))
        added += len(groups) - 1
    return out, added
