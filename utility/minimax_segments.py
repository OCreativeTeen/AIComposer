"""t201u: MiniMax 带场景音频（作为说话 / 作为唱歌）时，音频 > 12.25 秒（12 秒档 294 帧）就分段生成再接起来。

每段 ≤ 12.25 秒、≥ 4 秒，切点尽量平均、并挪到附近的静音（ffmpeg silencedetect）里，不切断字；切点对齐到 1/24 秒。
第 1 段用场景起始图，第 k 段用第 k-1 段（裁好后）的最后一帧当起始图；所有段在同一台机器上依次跑。
每段视频裁到正好是这段音频的长度，统一重编码接起来，再换上原始完整的场景音频 → 一个 mp4，交给原来的导入流程。
"""
import math
import os
import re
import subprocess
import threading

FPS = 24
SEG_MAX = 294 / 24  # t166u: 12 秒档的实际长度 12.25 秒
SEG_MIN = 4.0
SNAP_WINDOW = 2.5  # 理想切点前后多少秒内找静音

_tls = threading.local()  # DualRunner 在工人线程里放 should_stop


class SegmentStopped(RuntimeError):
    """按了停止：当前段做完就停，不导入半场。"""


def set_should_stop(fn) -> None:
    _tls.should_stop = fn


def should_stop() -> bool:
    fn = getattr(_tls, "should_stop", None)
    try:
        return bool(fn and fn())
    except Exception:  # noqa: BLE001
        return False


def _run(args) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def probe_seconds(path: str) -> float:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, timeout=60)
        return float((out.stdout or "").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def probe_frames(path: str) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "default=noprint_wrappers=1:nokey=1", path],
                         capture_output=True, text=True, timeout=300)
    return int((out.stdout or "0").strip() or 0)


def detect_silences(audio_path: str, noise_db: int = -35, min_len: float = 0.2) -> list:
    """[(开始, 结束)] 静音区间。"""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", audio_path, "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", p.stderr)]
    return [(max(0.0, s), e) for s, e in zip(starts, ends)]


def _q(t: float) -> float:
    return round(t * FPS) / FPS


def plan_segments(duration: float, silences=None) -> list:
    """把 duration 秒分成 N=ceil(dur/SEG_MAX) 段（不够就加段）：[(开始, 结束, 是否落在静音里)]，切点在 1/24 秒格上。"""
    dur = float(duration)
    if dur <= SEG_MAX:
        return [(0.0, dur, False)]
    mids = sorted((s + e) / 2.0 for s, e in (silences or []) if 0 < (s + e) / 2.0 < dur)
    n = math.ceil(dur / SEG_MAX)
    while True:
        cuts, prev, ok = [], 0.0, True
        for i in range(1, n):
            ideal = prev + (dur - prev) / (n - i + 1)
            left = n - i  # 这一刀之后还剩几段
            lo = max(prev + SEG_MIN, dur - left * SEG_MAX)
            hi = min(prev + SEG_MAX, dur - left * SEG_MIN)
            if lo > hi:
                ok = False
                break
            near = [m for m in mids if lo <= m <= hi and abs(m - ideal) <= SNAP_WINDOW]
            if near:
                c, sil = min(near, key=lambda m: abs(m - ideal)), True
            else:
                c, sil = min(max(ideal, lo), hi), False
            c = _q(c)
            if c > hi + 1e-9:
                c -= 1.0 / FPS
            if c < lo - 1e-9:
                c += 1.0 / FPS
            cuts.append((c, sil))
            prev = c
        if ok and dur - prev <= SEG_MAX + 1e-6:
            break
        n += 1
    edges = [0.0] + [c for c, _ in cuts] + [dur]
    sil = [False] + [s for _, s in cuts]
    return [(edges[i], edges[i + 1], sil[i]) for i in range(len(edges) - 1)]


def cut_audio(src: str, start: float, end: float, out: str) -> str:
    _run(["-ss", f"{start:.4f}", "-i", src, "-t", f"{end - start:.4f}", "-ac", "2", "-ar", "48000", out])
    return out


def trim_video(src: str, seconds: float, out: str) -> str:
    """裁到正好 round(seconds*24) 帧（24fps 重编码，去掉音轨，最后统一换原声）。"""
    frames = max(1, int(round(seconds * FPS)))
    _run(["-i", src, "-an", "-vf", f"fps={FPS},format=yuv420p", "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "medium", "-crf", "16", out])
    return out


def last_frame(src: str, out_png: str) -> str:
    _run(["-sseof", "-0.5", "-i", src, "-update", "1", "-q:v", "1", out_png])
    if not os.path.isfile(out_png):
        raise RuntimeError(f"最后一帧没取出来：{src}")
    return out_png


def concat_with_audio(parts: list, audio_src: str, seconds: float, out: str) -> str:
    lst = out + ".txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '" + os.path.abspath(p).replace("\\", "/").replace("'", "'\\''") + "'\n")
    _run(["-f", "concat", "-safe", "0", "-i", lst, "-i", audio_src, "-map", "0:v:0", "-map", "1:a:0",
          "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", str(FPS), "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-t", f"{seconds:.4f}", "-movflags", "+faststart", out])
    return out


_PIC2 = re.compile(r"[^.\n。]*Picture 2[^.\n。]*[.。]?\s*")


_SPK_MAP = re.compile(r"\(S(\d+)\) is ([^,;(]+)")
_WHEN = re.compile(r"from (\d+(?:\.\d+)?) s to (\d+(?:\.\d+)?) s")
_SWITCH = re.compile(r"^Then the lip movement switches to [^,]*?(?: (from \d+(?:\.\d+)? s to \d+(?:\.\d+)? s))?, (?:and )?")


def _speaker_names(text: str) -> dict:
    return {int(n): nm.strip() for n, nm in _SPK_MAP.findall(text or "")}


def segment_dialogue(text: str, start: float, end: float, timeline) -> tuple:
    """t150u: 这一段只留时间上落在 [start, end] 里的台词句（时间改成这一段里的秒数），返回 (提示词, 这一段说话人序号顺序)。
    timeline = [(开始, 结束, 说话人序号)]，一句台词一条；对不上就原样返回 (text, None)。"""
    from utility.prompt_polish import _dialogue_span

    tl = [tuple(x) for x in (timeline or []) if isinstance(x, (list, tuple)) and len(x) >= 3]
    span = _dialogue_span(text) if (tl and "<d>" in text) else None
    if not span:
        return text, None
    body = text[span[0]:span[1]]
    turns = [t.strip() for t in re.findall(r".*?</d>", body, flags=re.S)]
    if len(turns) != len(tl):
        return text, None
    keep, order = [], []
    for t, (a, b, n) in zip(turns, tl):
        a, b, n = float(a), float(b), int(n)
        ov = min(b, end) - max(a, start)
        if ov < 0.25 and not (a >= start and b <= end):
            continue
        ra, rb = max(a, start) - start, min(b, end) - start
        t = _WHEN.sub(f"from {ra:.1f} s to {rb:.1f} s", t, count=1)
        if not keep:  # 这一段的第一句：不是「换到某人」，直接说这个人
            m = _SWITCH.match(t)
            if m:
                t = ((m.group(1) + ", ") if m.group(1) else "") + t[m.end():]
                t = t[0].upper() + t[1:]
        keep.append(t)
        if not order or order[-1] != n:
            order.append(n)
    new = " ".join(keep) if keep else "Nobody speaks in this segment; everyone keeps their lips closed."
    return text[:span[0]] + new + text[span[1]:], order


def segment_prompt(prompt: str, k: int, m: int, start: float, end: float, keep_last: bool, timeline=None) -> str:
    text = prompt or ""
    if not keep_last:  # 结束图只给最后一段，前面几段去掉「Picture 2 …」那句
        text = _PIC2.sub("", text).rstrip()
    names = _speaker_names(text)
    text, order = segment_dialogue(text, start, end, timeline)  # t150u
    note = (f"Segment {k} of {m}: this shot covers seconds {start:.1f}-{end:.1f} of the scene dialogue; "
            "lip-sync only the words in the given audio.")
    if order is not None and names:
        who = lambda n: f"{names.get(n, f'Speaker {n}')} (S{n})"  # noqa: E731
        silent = [who(n) for n in sorted(names) if n not in order]
        if not order:
            note += " Nobody speaks in this segment; everyone keeps their lips closed."
        else:
            note += (" In this segment " + (f"only {who(order[0])} speaks" if len(order) == 1
                                            else ", then ".join(who(n) for n in order) + " speak in this order"))
            note += ("; " + " and ".join(silent) + (" keeps" if len(silent) == 1 else " keep")
                     + " their lips closed the whole segment." if silent else ".")
    if k > 1:
        note += (" Continues directly from the previous shot: same people, same place, same clothing, same light, "
                 "same camera direction; Picture 1 is the last frame of the previous shot.")
    return text + "\n\n" + note


def run_segmented(*, gen_one, image_path, prompt, audio_path, audio_seconds, dest_dir, base_name,
                  last_image_path=None, status=None, retry_same=1, is_unreachable=None, timeline=None) -> str:
    """gen_one(image, prompt, seconds, audio, last_image, out_path, status) → mp4。返回接好的 mp4。
    每段失败在同一台重试 retry_same 次；连不上直接抛出（交给双机换另一台整场重来）；
    按了停止：当前段做完就抛 SegmentStopped，不接、不导入。"""
    say = status if callable(status) else (lambda m: print("🎬 " + str(m)))
    sil = detect_silences(audio_path)
    plan = plan_segments(audio_seconds, sil)
    m = len(plan)
    say(f"场景音频 {audio_seconds:.2f} 秒 > {SEG_MAX:.2f} 秒，分 {m} 段："
        + "，".join(f"{a:.2f}–{b:.2f}" + ("" if s or i == 0 else "（附近没静音）") for i, (a, b, s) in enumerate(plan)))
    seg_dir = os.path.join(dest_dir, base_name + "_segments")
    os.makedirs(seg_dir, exist_ok=True)
    start_img, trimmed = image_path, []
    for k, (a, b, _s) in enumerate(plan, 1):
        if should_stop():
            raise SegmentStopped(f"已停止（做完 {k - 1}/{m} 段），这一场不导入")
        tag = f"第{k}/{m}段"
        seg_audio = cut_audio(audio_path, a, b, os.path.join(seg_dir, f"seg{k}of{m}_audio.wav"))
        # t150u: 没有结束图时（参考图工作流）不删「Picture 2」句：那是第 1 个肖像 / Speaker map，不是结束图
        p = segment_prompt(prompt, k, m, a, b, keep_last=(k == m or not last_image_path), timeline=timeline)
        raw = os.path.join(seg_dir, f"seg{k}of{m}_raw.mp4")
        for attempt in range(retry_same + 1):
            try:
                say(f"{tag}（{b - a:.2f} 秒）生成中…" + ("（重试）" if attempt else ""))
                got = gen_one(start_img, p, b - a, seg_audio, last_image_path if k == m else None, raw,
                              lambda msg, _t=tag: say(f"{_t}：{msg}"))
                if not (got and os.path.isfile(got)):
                    raise RuntimeError("没有拿到视频文件")
                raw = got
                break
            except SegmentStopped:
                raise
            except Exception as exc:  # noqa: BLE001
                if (callable(is_unreachable) and is_unreachable(exc)) or attempt >= retry_same:
                    raise RuntimeError(f"{tag} 失败：{exc}") from exc
                say(f"⚠️ {tag} 失败（{exc}），同一台再试一次")
        cut = trim_video(raw, b - a, os.path.join(seg_dir, f"seg{k}of{m}_trim.mp4"))
        trimmed.append(cut)
        if k < m:
            start_img = last_frame(cut, os.path.join(seg_dir, f"seg{k}of{m}_lastframe.png"))
    out = os.path.join(dest_dir, base_name + f"_joined{m}.mp4")
    say(f"{m} 段接起来 + 换原始场景音频 → {os.path.basename(out)}")
    return concat_with_audio(trimmed, audio_path, audio_seconds, out)
