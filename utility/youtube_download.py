"""YouTube 单视频下载工具：最高 / 最低分辨率、可选字幕（srt/vtt + 纯文本）、可选拆出音频（mp3/wav）。

输出到 ``<AI_MEDIA_ROOT>/Download``。复用：
- ``gui.dl.youtube_dl``：``_normalize_youtube_watch_url``（单视频 URL）、``MediaDownloader._detect_js_runtime``（Node/Deno，
  yt-dlp 解 YouTube 签名需要）、最高画质的 format_sort 写法（``_youtube_best_video_ydl_opts``）。
- ``utility.ffmpeg_audio_processor.FfmpegAudioProcessor.extract_audio_from_video``：拆音频。
Cookies：``.env`` 的 YOUTUBE_COOKIES_FILE；没设就用 Windows「下载」文件夹里最新的 *cookies*.txt。只打印路径，不打印内容。

API::

    from utility.youtube_download import download_youtube
    result = download_youtube(url, resolution="lowest", transcript=True, split_audio="mp3")

界面：``open_youtube_download_dialog(parent)``；也可 ``python -m utility.youtube_download``。
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import threading
from typing import Callable, Optional

import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
import config

Status = Optional[Callable[[str], None]]

SUB_LANGS = ["zh-Hans", "zh-Hant", "zh", "zh-CN", "zh-TW", "en", "en-US", "en-GB"]


def download_dir() -> str:
    root = getattr(config, "AI_MEDIA_ROOT", "") or "D:/AI_MEDIA"
    path = os.path.normpath(os.path.join(root, "Download"))
    os.makedirs(path, exist_ok=True)
    return path


def find_cookies_file() -> str:
    """YOUTUBE_COOKIES_FILE（.env）→ 下载文件夹里最新的 *cookies*.txt → 空。"""
    env = (os.environ.get("YOUTUBE_COOKIES_FILE") or "").strip().strip('"')
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env) and os.path.getsize(env) > 0:
            return env
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    cands = [p for p in glob.glob(os.path.join(dl, "*cookies*.txt")) if os.path.getsize(p) > 0]
    return max(cands, key=os.path.getmtime) if cands else ""


def _say(status: Status, msg: str) -> None:
    print(f"[youtube_download] {msg}")
    if status:
        try:
            status(msg)
        except Exception:  # noqa: BLE001
            pass


def _js_runtime():
    try:
        from gui.dl.youtube_dl import MediaDownloader

        return MediaDownloader._detect_js_runtime(None)  # 不用 self
    except Exception:  # noqa: BLE001
        return (None, None)


def _normalize(url: str) -> str:
    try:
        from gui.dl.youtube_dl import _normalize_youtube_watch_url

        return _normalize_youtube_watch_url(url)
    except Exception:  # noqa: BLE001
        return (url or "").strip()


def _format_opts(resolution: str) -> dict:
    if resolution == "telegram":
        # t99u: <=720p mp4 (h264+m4a preferred) so the file stays under the Telegram bot 50MB limit
        return {
            "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]/worst",
            "format_sort": ["res:720", "+size", "vcodec:h264", "acodec:m4a"],
            "merge_output_format": "mp4",
        }
    if resolution == "lowest":
        return {
            "format": "worstvideo*+worstaudio/worst",
            "format_sort": ["+res", "+fps", "+size", "+br"],
            "merge_output_format": "mp4",
        }
    try:
        from gui.dl.youtube_dl import _youtube_best_video_ydl_opts

        return _youtube_best_video_ydl_opts()
    except Exception:  # noqa: BLE001
        return {"format": "bestvideo*+bestaudio/best", "merge_output_format": "mp4"}


def subtitle_to_text(path: str) -> str:
    """srt / vtt → 纯文本（去时间轴、标签、连续重复行）。返回 .txt 路径。"""
    out_lines: list = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if (not line or line == "WEBVTT" or line.isdigit() or "-->" in line
                    or re.match(r"^(Kind|Language|NOTE|STYLE)\b", line)):
                continue
            line = re.sub(r"<[^>]+>", "", line).strip()
            if line and (not out_lines or out_lines[-1] != line):
                out_lines.append(line)
    txt = os.path.splitext(path)[0] + ".txt"
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines) + "\n")
    return txt


def split_audio(video_path: str, fmt: str = "mp3") -> str:
    """复用 FfmpegAudioProcessor 拆音频，放到视频旁边，同名。"""
    from utility.ffmpeg_audio_processor import FfmpegAudioProcessor

    fmt = "wav" if fmt == "wav" else "mp3"
    tmp = FfmpegAudioProcessor("yt_download").extract_audio_from_video(video_path, output_format=fmt)
    if not tmp or not os.path.isfile(tmp):
        raise RuntimeError("拆音频失败（视频没有音轨，或 ffmpeg 出错）")
    dest = os.path.splitext(video_path)[0] + "." + fmt
    shutil.move(tmp, dest)
    return dest


def _fmt_srt_time(sec: float) -> str:
    ms = int(round(max(0.0, float(sec)) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s_, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s_:02d},{ms:03d}"


def _check_transcribe_service() -> str:
    """看本机转录服务能不能用。返回转录方式（"voicebox"/"whisper"）；不能用时抛出清楚的错误。"""
    engine = str(getattr(config, "TRANSCRIBE_ENGINE", "voicebox") or "voicebox").strip().lower()
    if engine != "voicebox":
        return engine
    import requests

    base = str(getattr(config, "VOICEBOX_BASE_URL", "") or "").rstrip("/")
    try:
        requests.get(base + "/health", timeout=8)
    except requests.RequestException as exc:
        raise RuntimeError(f"本机转录服务 Voicebox 连不上（config.VOICEBOX_BASE_URL），请先启动它：{type(exc).__name__}")
    return engine


def transcribe_local(media_path: str, *, language: str = "", status: Status = None) -> tuple[str, str]:
    """用项目已有的转录代码（utility.media_transcript 的切段 + Voicebox/Whisper）把媒体转成 .srt 和 .txt。

    按 config.TRANSCRIBE_CHUNK_SECONDS 切段（_cut_chunk），每段转录（_items_voicebox / _items_whisper），
    加上这一段的起始秒数后合并。不调用 LLM 补标点。返回 (srt 路径, txt 路径)。"""
    import tempfile

    from utility import media_transcript as mt

    engine = _check_transcribe_service()
    total = mt._probe_seconds(media_path)
    if total <= 0.2:
        raise RuntimeError("读不出音频长度，无法转录")
    size = max(5.0, float(getattr(config, "TRANSCRIBE_CHUNK_SECONDS", 600) or 600))
    count = max(1, int(-(-total // size)))
    lang = (language or "").split("-")[0].strip()
    service = transcriber = None
    if engine == "whisper":
        from utility import audio_transcriber

        transcriber = audio_transcriber.AudioTranscriber("yt_download", model_size="small", device="cuda")
    else:
        from utility.voicebox_speech_service import VoiceboxService

        service = VoiceboxService("yt_download")
    items: list[dict] = []
    work = tempfile.mkdtemp(prefix="yt_transcribe_")
    try:
        for i in range(count):
            start = i * size
            length = min(size, total - start)
            if length < 0.3:
                continue
            _say(status, f"本地转录（{engine}）第 {i + 1} / {count} 段（{mt.format_timestamp(start)}，每段 {int(size)} 秒）…")
            wav = os.path.join(work, f"chunk_{i:04d}.wav")
            if not mt._cut_chunk(media_path, start, length, wav):
                _say(status, f"第 {i + 1} 段切不出来，跳过")
                continue
            if transcriber is not None:
                got = mt._items_whisper(transcriber, wav, lang or "en", length)
                err = str(getattr(transcriber, "last_error", "") or "")
            else:
                got, err = mt._items_voicebox(service, wav, length, lang)
            try:
                os.remove(wav)
            except OSError:
                pass
            if err and str(err).startswith(mt.VOICEBOX_DOWN):
                raise RuntimeError("Voicebox 转录服务出错，停止：" + str(err)[len(mt.VOICEBOX_DOWN):][:200])
            if not got and err:
                _say(status, f"第 {i + 1} 段没转出文字：{str(err)[:120]}")
            for it in got:
                items.append({"start": start + float(it["start"]), "end": start + float(it["end"]),
                              "text": str(it["text"]).strip()})
            _say(status, f"第 {i + 1} / {count} 段完成（累计 {len(items)} 句）")
    finally:
        try:
            os.rmdir(work)
        except OSError:
            pass
    if not items:
        raise RuntimeError("本地转录没有得到任何文字")
    items.sort(key=lambda x: x["start"])
    base = os.path.splitext(media_path)[0] + ".local"
    srt, txt = base + ".srt", base + ".txt"
    with open(srt, "w", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            f.write(f"{n}\n{_fmt_srt_time(it['start'])} --> {_fmt_srt_time(max(it['end'], it['start'] + 0.3))}\n{it['text']}\n\n")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(it["text"] for it in items) + "\n")
    return srt, txt


def download_youtube(url: str, *, resolution: str = "highest", transcript: bool = False,
                     split_audio_fmt: str = "", out_dir: str = "", use_cookies: bool = True,
                     status: Status = None, audio_only: bool = False, audio_fmt: str = "mp3",
                     force_local: bool = False, local_fallback: bool = True) -> dict:
    """下载一个 YouTube 视频。resolution: "highest" / "lowest"；split_audio_fmt: "" / "mp3" / "wav"。
    返回 {"video", "subtitles": [...], "texts": [...], "audio", "title", "cookies_used"}。"""
    import yt_dlp

    url = _normalize(url)
    if not url:
        raise ValueError("没有 URL")
    out_dir = out_dir or download_dir()
    os.makedirs(out_dir, exist_ok=True)
    progress = {"last": -1}

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = int(d.get("downloaded_bytes", 0) * 100 / total) if total else -1
            if pct != progress["last"] and (pct < 0 or pct % 5 == 0):
                progress["last"] = pct
                _say(status, f"下载中 {pct}%" if pct >= 0 else "下载中 …")
        elif d.get("status") == "finished":
            _say(status, "下载完成，合并 / 处理中 …")

    opts = {
        "outtmpl": os.path.join(out_dir, "%(title).80B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "windowsfilenames": True,
    }
    if audio_only:
        audio_fmt = audio_fmt if audio_fmt in ("mp3", "wav") else "mp3"
        opts["format"] = "bestaudio/best"
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": audio_fmt}
        if audio_fmt == "mp3":
            pp["preferredquality"] = "0"
        opts["postprocessors"] = [pp]
    else:
        opts.update(_format_opts(resolution))
    if transcript and not force_local:
        opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": SUB_LANGS,
            "subtitlesformat": "srt/vtt/best",
            "postprocessors": list(opts.get("postprocessors") or []) + [
                {"key": "FFmpegSubtitlesConvertor", "format": "srt"}
            ],
        })
        if not audio_only:
            opts["keepvideo"] = True
    name, rpath = _js_runtime()
    if name:
        opts["js_runtimes"] = {name: ({"path": rpath} if rpath else {})}
        opts["remote_components"] = ["ejs:github"]
    cookies = find_cookies_file() if use_cookies else ""

    # 和 MediaDownloader._get_ydl_opts_base 一样按 player_client 轮流试（某些客户端会给 403）
    clients = (["mweb"], ["web"], ["android"], ["tv_embedded"], ["ios"]) if name else (["android"], ["mweb"], ["web"])

    def run(with_cookies: bool, client):
        o = dict(opts)
        o["extractor_args"] = {"youtube": {"player_client": list(client)}}
        if with_cookies and cookies:
            o["cookiefile"] = cookies
        with yt_dlp.YoutubeDL(o) as ydl:
            return ydl.extract_info(url, download=True), ydl

    _say(status, f"开始下载（{'最低' if resolution == 'lowest' else '最高'}分辨率）：{url}")
    cookies_used = False
    attempts = [(False, c) for c in clients] + ([(True, c) for c in clients] if cookies else [])
    errors = []
    info = ydl = None
    for with_cookies, client in attempts:  # 公开视频先不用 cookies
        try:
            if with_cookies and not cookies_used:
                _say(status, f"不带 cookies 都失败，改用 cookies 文件 {os.path.basename(cookies)} 重试 …")
            cookies_used = with_cookies
            _say(status, f"尝试 player_client={client[0]}" + ("（带 cookies）" if with_cookies else ""))
            info, ydl = run(with_cookies, client)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{client[0]}{'+cookies' if with_cookies else ''}: {str(exc).splitlines()[0][:100]}")
            for part in glob.glob(os.path.join(out_dir, "*.part")):
                try:
                    os.remove(part)
                except OSError:
                    pass
    if info is None:
        hint = "" if cookies else "（没有找到 cookies 文件；可在 .env 设 YOUTUBE_COOKIES_FILE 或放一个 *cookies*.txt 到「下载」文件夹）"
        raise RuntimeError("下载失败" + hint + "：\n" + "\n".join(errors))
    video = ""
    for item in (info.get("requested_downloads") or []):
        video = item.get("filepath") or video
    if not video:
        video = ydl.prepare_filename(info)
    base = os.path.splitext(video)[0]
    if audio_only:
        cand = base + "." + audio_fmt
        if os.path.isfile(cand):
            video = cand
    subs = sorted(p for p in glob.glob(glob.escape(base) + ".*") if p.lower().endswith((".srt", ".vtt")))
    texts = [subtitle_to_text(p) for p in subs if p.lower().endswith(".srt")] or \
            [subtitle_to_text(p) for p in subs[:1]]
    local_error = ""
    if transcript and (force_local or (not subs and local_fallback)):
        if not subs:
            _say(status, "强制本地转录 …" if force_local else "YouTube 没有字幕，改用本地转录 …")
        try:
            srt, txt = transcribe_local(video, language=str(info.get("language") or ""), status=status)
            subs = subs + [srt]
            texts = texts + [txt]
        except Exception as exc:  # noqa: BLE001
            local_error = str(exc)
            _say(status, f"本地转录失败：{exc}")
    elif transcript and not subs:
        _say(status, "这个视频没有可下载的字幕 / 自动字幕")
    audio = video if audio_only else ""
    if split_audio_fmt and not audio_only:
        _say(status, f"拆音频（{split_audio_fmt}）…")
        audio = split_audio(video, split_audio_fmt)
    h = info.get("height")
    _say(status, f"完成：{os.path.basename(video)}" + (f"（{h}p）" if h and not audio_only else ""))
    return {"local_error": local_error, "audio_only": audio_only, "video": video, "subtitles": subs, "texts": texts, "audio": audio,
            "title": info.get("title") or "", "height": h, "cookies_used": cookies_used}


def open_youtube_download_dialog(parent=None):
    """小窗口：URL、分辨率、字幕、拆音频、状态、打开文件夹。"""
    import tkinter as tk
    from tkinter import messagebox, ttk

    win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    win.title("YouTube 下载")
    win.resizable(False, False)
    frm = ttk.Frame(win, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frm, text="视频网址").grid(row=0, column=0, sticky="w")
    url_var = tk.StringVar()
    ent = ttk.Entry(frm, textvariable=url_var, width=60)
    ent.grid(row=0, column=1, columnspan=3, sticky="we", pady=2)
    try:
        clip = win.clipboard_get().strip()
        if "youtu" in clip:
            url_var.set(clip)
    except Exception:  # noqa: BLE001
        pass
    kind_var = tk.StringVar(value="video")
    ttk.Label(frm, text="下载内容").grid(row=7, column=0, sticky="w")
    ttk.Radiobutton(frm, text="视频", value="video", variable=kind_var).grid(row=7, column=1, sticky="w")
    ttk.Radiobutton(frm, text="仅音频（用右边的 mp3/wav）", value="audio", variable=kind_var).grid(row=7, column=2, columnspan=2, sticky="w")
    force_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text="强制本地转录（即使 YouTube 有字幕；没字幕时自动本地转录）", variable=force_var).grid(row=8, column=1, columnspan=3, sticky="w")
    res_var = tk.StringVar(value="highest")
    ttk.Label(frm, text="分辨率").grid(row=1, column=0, sticky="w")
    ttk.Radiobutton(frm, text="最高", value="highest", variable=res_var).grid(row=1, column=1, sticky="w")
    ttk.Radiobutton(frm, text="最低", value="lowest", variable=res_var).grid(row=1, column=2, sticky="w")
    sub_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="下载字幕（srt/vtt + 纯文本）", variable=sub_var).grid(row=2, column=1, columnspan=2, sticky="w")
    aud_var = tk.BooleanVar(value=False)
    fmt_var = tk.StringVar(value="mp3")
    ttk.Checkbutton(frm, text="拆出音频", variable=aud_var).grid(row=3, column=1, sticky="w")
    ttk.Combobox(frm, textvariable=fmt_var, values=["mp3", "wav"], width=5, state="readonly").grid(row=3, column=2, sticky="w")
    status_var = tk.StringVar(value=f"保存到 {download_dir()}")
    ttk.Label(frm, textvariable=status_var, wraplength=460, foreground="#555").grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 4))
    bar = ttk.Progressbar(frm, mode="indeterminate", length=460)
    bar.grid(row=5, column=0, columnspan=4, sticky="we")

    def ui_status(msg):
        win.after(0, lambda: status_var.set(msg))

    def go():
        url = url_var.get().strip()
        if not url:
            messagebox.showwarning("YouTube 下载", "先填视频网址", parent=win)
            return
        btn.config(state="disabled")
        bar.start(12)

        def work():
            try:
                ao = kind_var.get() == "audio"
                r = download_youtube(url, resolution=res_var.get(), transcript=sub_var.get(),
                                     split_audio_fmt=fmt_var.get() if aud_var.get() else "", status=ui_status,
                                     audio_only=ao, audio_fmt=fmt_var.get(), force_local=force_var.get())
                msg = f"完成：{os.path.basename(r['video'])}"
                if r.get("local_error"):
                    msg += f"；本地转录失败：{r['local_error']}"
                if r["subtitles"]:
                    msg += f"；字幕 {len(r['subtitles'])} 个"
                elif sub_var.get():
                    msg += "；没有字幕"
                if r["audio"] and not r.get("audio_only"):
                    msg += f"；音频 {os.path.basename(r['audio'])}"
                ui_status(msg)
            except Exception as exc:  # noqa: BLE001
                ui_status(f"失败：{exc}")
            finally:
                win.after(0, lambda: (bar.stop(), btn.config(state="normal")))

        threading.Thread(target=work, daemon=True).start()

    btns = ttk.Frame(frm)
    btns.grid(row=9, column=0, columnspan=4, sticky="e", pady=(8, 0))
    btn = ttk.Button(btns, text="下载", command=go)
    btn.pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="打开文件夹", command=lambda: os.startfile(download_dir())).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=4)
    ent.focus_set()
    if parent is None:
        win.mainloop()
    return win


if __name__ == "__main__":
    open_youtube_download_dialog()
