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


def _items_voicebox(service, wav: str, length: float) -> tuple[list[dict], str]:
    """Voicebox：有分段时间用分段，没有就整小段一行。返回 (片段, 错误说明)。"""
    raw = service.transcribe(wav, with_timestamps=True)
    data = None
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        text = str(raw or "").strip()
        if text:
            return [{"start": 0.0, "end": float(length), "text": text}], ""
        return [], str(getattr(service, "_last_transcribe_error", "") or "").strip()
    segments = data.get("segments")
    if isinstance(segments, list) and segments:
        return [dict(s) for s in segments if isinstance(s, dict)], ""
    text = str(data.get("text") or "").strip()
    if text:
        return [{"start": 0.0, "end": float(length), "text": text}], ""
    return [], str(getattr(service, "_last_transcribe_error", "") or "").strip()


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
    再把结果贴回来；它的返回值就是这次的回答。每一次调用都先试自动(Strata)，
    只有这一次失败才打开手动窗口，下一次调用仍然先试自动。``mode`` 只用来统计手动次数。
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
    print(f"{what}：自动调用没成功，转到手动模式。")
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


def _punctuate_with_times(items: list[dict], language: str, ask,
                          stats: Optional[dict] = None) -> list[tuple[float, str]]:
    """一批片段交给 LLM：补标点、一句一行、每行开头写开始秒数。出问题就退回原始片段。

    ``ask(系统提示词, 用户提示词, 说明)`` 返回 LLM 的回答（自动或手动），拿不到返回 ``None``；
    ``ask`` 是 ``None`` 表示没有 LLM 可用。
    ``stats["punct_batches"]`` 记一共处理了几批，``stats["punct_fallback"]`` 记几批退回了原始片段。
    """
    if not items:
        return []
    raw = _raw_lines(items)
    if stats is not None:
        stats["punct_batches"] = stats.get("punct_batches", 0) + 1

    def fallback() -> list[tuple[float, str]]:
        if stats is not None:
            stats["punct_fallback"] = stats.get("punct_fallback", 0) + 1
        return raw

    if ask is None:
        return fallback()
    user = "\n".join(f"[{it['start']:.1f}-{it['end']:.1f}] {it['text']}" for it in items)
    system = config_prompt.TRANSCRIPT_TIMESTAMP_SYSTEM_PROMPT.format(language=_language_label(language))
    answer = ask(system, user, "补标点")
    if answer is None:
        print("带时间的标点处理失败，这一批用原始片段。")
        return fallback()
    text = _strip_fence(answer)
    lines: list[tuple[float, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _LINE_RE.match(line)
        if not match:
            print("带时间的标点处理：有一行没有时间戳，这一批用原始片段。")
            return fallback()
        lines.append((float(match.group(1)), match.group(2)))
    if not lines:
        return fallback()
    lo = min(float(it["start"]) for it in items) - 1.0
    hi = max(float(it["end"]) for it in items) + 2.0
    last = lo
    for stamp, _sentence in lines:
        if stamp < last - 0.05 or stamp > hi:
            print("带时间的标点处理：时间对不上，这一批用原始片段。")
            return fallback()
        last = max(last, stamp)
    before = len(_strip("".join(str(it["text"]) for it in items)))
    after = len(_strip("".join(sentence for _t, sentence in lines)))
    if before and not (0.85 <= after / before <= 1.15):
        print("带时间的标点处理：字数对不上，这一批用原始片段。")
        return fallback()
    return lines


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
    else:
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
            if transcriber is not None:
                items = _items_whisper(transcriber, wav, language, length)
            else:
                items, err = _items_voicebox(service, wav, length)
                if err:
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
