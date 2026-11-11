"""t370u: 生场视频时动态分节（不再在建项目 / 出图后按 <Ns> 拆场）。

一场的 speaking 按 ``<Ns>``（自言自语那几句单独一节）和手工 ``<s>``（加在某个 ``<n>`` 前面）分成几节。
生成时一节一节来：

1. 第 1 节：把这一场克隆一份插在它前面，克隆只留第 1 节的讲话（场景音频 / 时间轴也只留这一段），
   用这一场现在的起始图生成、导入到克隆上。原场景去掉这一节的讲话。
2. 克隆视频的最后一帧临时取出来，按「尾帧增强」选项（t376u：不增强 / MOSS / Qwen / Grok Image，t395u 默认 Qwen）
   「提高分辨率」（保持原画风 + 项目画风）增强，写进原场景的 zero_image_last，作为下一节的起始图。
   增强失败（ComfyUI 不通、Grok 出错等）就用原末帧（打印警告）。
3. 原场景剩下的讲话如果还能分，就重复 1–2；最后一节不再克隆，直接用新的 zero_image_last 生成原场景的视频。

这里只放纯逻辑（可离线测）；读写媒体、ffmpeg、ComfyUI 由调用方注入。
"""
from __future__ import annotations

import copy
import os

from utility.speaking_marks import (
    format_segment_turns,
    speaking_segment_turns,
)

SEGMENT_OF_KEY = "video_segment_of"  # 克隆出来的那一节记下原场景 id
# 拆节时原场景上要能退回的字段
_SNAPSHOT_KEYS = ("speaking", "speaking_timing", "clip_audio", "clip")
_MISSING = object()


def _weight(text: str) -> int:
    return max(1, len("".join(str(text or "").split()))) + 1


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


def _spoken(text: str) -> str:
    """t380u: 只比讲话内容：加 <s> / 句中补一个同样的说话人标记不算改了文字。"""
    from utility.speaking_marks import SEGMENT_MARK_RE, strip_speaker_marks
    return "".join(strip_speaker_marks(SEGMENT_MARK_RE.sub(" ", str(text or ""))).split())


def _clamp_speaker(n) -> int:
    try:
        return min(3, max(1, int(n)))
    except (TypeError, ValueError):
        return 1


def turn_spans_from_timing(scene: dict, turns: list):
    """speaking_timing → 每句 (开始, 结束) 秒。对不上（文字改过 / 条数不同）返回 None。

    sections 可能一句一条，也可能把挨着的同一个人合成一条（wf_speaking 的做法）；
    合成的那条按字数分给里面的每一句。
    """
    tm = scene.get("speaking_timing") if isinstance(scene, dict) else None
    if not isinstance(tm, dict) or not turns:
        return None
    if _spoken(tm.get("text")) != _spoken(scene.get("speaking")):
        return None
    secs = []
    for x in tm.get("sections") or []:
        if not isinstance(x, dict):
            return None
        try:
            a, b = float(x.get("start")), float(x.get("end"))
        except (TypeError, ValueError):
            return None
        secs.append((a, b))
    if not secs:
        return None
    if len(secs) == len(turns):
        return [(a, max(a, b)) for a, b in secs]
    groups: list = []
    for i, t in enumerate(turns):
        sp = _clamp_speaker(t.speaker)
        if groups and groups[-1][0] == sp:
            groups[-1][1].append(i)
        else:
            groups.append((sp, [i]))
    if len(groups) != len(secs):
        return None
    spans = [None] * len(turns)
    for (_sp, idxs), (a, b) in zip(groups, secs):
        total = sum(_weight(turns[i].text) for i in idxs) or 1
        cur = a
        for k, i in enumerate(idxs):
            end = b if k == len(idxs) - 1 else cur + (b - a) * _weight(turns[i].text) / total
            spans[i] = (cur, max(cur, end))
            cur = end
    return spans


def estimated_turn_spans(turns: list, seconds: float):
    """没有可用时间轴：按字数把整段音频分给每一句。"""
    try:
        seconds = float(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds <= 0 or not turns:
        return None
    total = sum(_weight(t.text) for t in turns) or 1
    cur, out = 0.0, []
    for k, t in enumerate(turns):
        end = seconds if k == len(turns) - 1 else cur + seconds * _weight(t.text) / total
        out.append((cur, end))
        cur = end
    return out


def plan_first_segment(scene: dict):
    """这一场能分节就返回计划：第 1 节、剩下的讲话、句数等。只有一节返回 None。"""
    if not isinstance(scene, dict):
        return None
    groups = speaking_segment_turns(scene.get("speaking") or "")
    if len(groups) < 2:
        return None
    turns = [t for g in groups for t in g]
    n_first = len(groups[0])
    return {
        "first": format_segment_turns(groups[0]),
        "rest": format_segment_turns(turns[n_first:]),
        "n_first": n_first,
        "turns": turns,
        "count": len(groups),
    }


def segment_cut_seconds(scene: dict, plan: dict, audio_seconds=None) -> tuple:
    """第 1 节和后面的分界（秒）。返回 (秒, 来源 'timing' / 'estimate', 每句时间)；算不出返回 (None, '', None)。"""
    turns, n = plan["turns"], plan["n_first"]
    spans = turn_spans_from_timing(scene, turns)
    source = "timing"
    if spans is None:
        spans = estimated_turn_spans(turns, audio_seconds)
        source = "estimate"
    if not spans:
        return None, "", None
    a, b = spans[n - 1][1], spans[n][0]
    cut = (a + b) / 2.0 if b >= a else b
    return round(cut, 3), source, spans


def _timing_for(turns: list, spans: list, offset: float, text: str, duration=None, per_turn: bool = True) -> dict:
    sections = []
    for t, (a, b) in zip(turns, spans):
        a, b = max(0.0, a - offset), max(0.0, b - offset)
        sp = _clamp_speaker(t.speaker)
        if not per_turn and sections and sections[-1]["speaker"] == sp:
            sections[-1]["end"] = round(b, 2)
            sections[-1]["text"] = (sections[-1]["text"] + t.text).strip()
            continue
        sections.append({"speaker": sp, "start": round(a, 2), "end": round(b, 2), "text": t.text})
    rec = {"text": (text or "").strip(), "sections": sections}
    if duration and duration > 0:
        rec["duration"] = round(float(duration), 3)
    return rec


def new_scene_id(scenes) -> int:
    ids = []
    for s in scenes or []:
        if isinstance(s, dict):
            try:
                ids.append(int(s.get("id") or 0))
            except (TypeError, ValueError):
                pass
    nid = ((max(ids) if ids else 0) // 100 + 1) * 100
    return max(nid, 10000)


def split_first_segment(scenes: list, scene: dict, *, next_id=None, clone_images=None,
                        cut_audio=None, audio_seconds=None, store_media=None):
    """把第 1 节拆成一场新场景，插在 ``scene`` 前面。返回 token（给 undo / 接末帧用）；不能分返回 None。

    - ``clone_images(src, dst)``：给克隆独立拷贝图槽（默认 scene_image_slots.clone_image_slots）。
    - ``cut_audio(path, start, length) -> 新文件``、``audio_seconds(path)``、``store_media(scene, key, ext, path)``：
      有场景音频（clip_audio）时按分界切成两段，各写回自己的场景。
    原场景还是同一个 dict（批量里拿着它的引用不变），只是讲话少了第 1 节。
    """
    if not isinstance(scenes, list) or not isinstance(scene, dict):
        return None
    try:
        idx = next(i for i, s in enumerate(scenes) if s is scene)
    except StopIteration:
        return None
    plan = plan_first_segment(scene)
    if not plan:
        return None
    if clone_images is None:
        from utility.scene_image_slots import clone_image_slots as clone_images

    snapshot = {k: (copy.deepcopy(scene[k]) if k in scene else _MISSING) for k in _SNAPSHOT_KEYS}

    audio = scene.get("clip_audio") or ""
    has_audio = bool(isinstance(audio, str) and audio and os.path.isfile(audio))
    total = None
    if has_audio and callable(audio_seconds):
        try:
            total = float(audio_seconds(audio) or 0) or None
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 分节：场景音频长度没读出来：{exc}")
            total = None
    cut, source, spans = segment_cut_seconds(scene, plan, total)
    per_turn = False
    tm = scene.get("speaking_timing")
    if isinstance(tm, dict) and len(tm.get("sections") or []) == len(plan["turns"]):
        per_turn = True

    clone = copy.deepcopy(scene)
    clone["id"] = int(next_id) if next_id is not None else new_scene_id(scenes)
    for key in ("clip", "clip_audio", "speaking_timing", "video_speech_speed", "video_prompt_log"):
        clone.pop(key, None)
    try:
        clone_images(scene, clone)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 分节：没有独立拷贝场景图，这一场不分节：{exc}")
        return None

    n = plan["n_first"]
    head_turns, rest_turns = plan["turns"][:n], plan["turns"][n:]
    audio_cut = False
    if has_audio and cut and total and 0 < cut < total and callable(cut_audio) and callable(store_media):
        try:
            head = cut_audio(audio, 0.0, cut)
            tail = cut_audio(audio, cut, total - cut)
            if not (head and os.path.isfile(head) and tail and os.path.isfile(tail)):
                raise RuntimeError("切出来的音频不在")
            store_media(clone, "clip_audio", ".wav", head)
            store_media(scene, "clip_audio", ".wav", tail)
            audio_cut = True
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 分节：场景音频没切成，两边都不带场景音频：{exc}")
            clone.pop("clip_audio", None)
    elif has_audio:
        print("⚠️ 分节：场景音频没法按节切开，克隆这一节不带场景音频")

    clone["speaking"] = plan["first"]
    if spans:
        clone["speaking_timing"] = _timing_for(head_turns, spans[:n], 0.0, plan["first"],
                                               cut if audio_cut else None, per_turn)
    clone[SEGMENT_OF_KEY] = scene.get("id")

    scene["speaking"] = plan["rest"]
    if spans:
        scene["speaking_timing"] = _timing_for(rest_turns, spans[n:], cut or 0.0, plan["rest"],
                                               (total - cut) if audio_cut else None, per_turn)
    else:
        scene.pop("speaking_timing", None)
    if has_audio and not audio_cut:
        scene.pop("clip_audio", None)  # 整场音频对不上剩下的讲话；拆节失败退回时从 snapshot 还原
    scene.pop("clip", None)  # 整场的旧预览片不对了；调用方重做静态预览
    scenes.insert(idx, clone)
    return {
        "clone": clone, "scene": scene, "snapshot": snapshot, "cut": cut, "cut_source": source,
        "audio_cut": audio_cut, "segments": plan["count"],
    }


def undo_first_segment(scenes: list, token: dict) -> bool:
    """生成 / 导入失败：去掉克隆，原场景的讲话、音频、时间轴、预览片退回拆节前。"""
    if not isinstance(token, dict):
        return False
    clone, scene = token.get("clone"), token.get("scene")
    if isinstance(scenes, list):
        for i, s in enumerate(scenes):
            if s is clone:
                del scenes[i]
                break
    if isinstance(scene, dict):
        for key, val in (token.get("snapshot") or {}).items():
            if val is _MISSING:
                scene.pop(key, None)
            else:
                scene[key] = val
    return True


def enhance_last_frame(frame_path: str, *, style: str = "", upscale=None) -> tuple:
    """末帧 → 下一节的起始图。``upscale(path, target, style) -> PIL`` （MOSS 提高分辨率）。

    返回 (图路径, 是否增强了, 说明)。增强失败（ComfyUI 不通等）返回原末帧和原因，调用方照常往下做。
    """
    if not frame_path or not os.path.isfile(frame_path):
        raise FileNotFoundError(f"末帧不在：{frame_path}")
    if not callable(upscale):
        return frame_path, False, "没有提高分辨率的后端"
    try:
        import tempfile

        from utility.image_upscale import finish_upscale, upscale_target_for_image

        target = upscale_target_for_image(frame_path)
        if not target:
            raise ValueError("读不出末帧尺寸")
        img = upscale(frame_path, target, style)
        if img is None or not hasattr(img, "save"):
            raise RuntimeError("提高分辨率没有返回图")
        img = finish_upscale(img, target, frame_path)  # t377u: 对齐尺寸 + 颜色统计对齐原末帧
        fd, out = tempfile.mkstemp(suffix=".png", prefix="seg_lastframe_up_")
        os.close(fd)
        img.convert("RGB").save(out)
        return out, True, f"{target[0]}x{target[1]}"
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 分节：末帧提高分辨率失败，用原末帧接下一节：{exc}")
        return frame_path, False, str(exc)


# ---- t376u: 尾帧增强选项 ----
LAST_FRAME_ENHANCE_OPTIONS = (("none", "不增强"), ("moss", "MOSS"), ("qn", "Qwen"), ("grok", "Grok Image"))
LAST_FRAME_ENHANCE_DEFAULT = "qn"  # t395u: 默认 Qwen（记过选项的项目照旧）
_ENHANCE_ALIASES = {"": LAST_FRAME_ENHANCE_DEFAULT, "off": "none", "raw": "none", "no": "none",
                    "qwen": "qn", "grok_image": "grok", "grokimage": "grok"}


def normalize_last_frame_enhance(value) -> str:
    """记下的选项 → none / moss / qn / grok；不认得的（含没记过）= 默认 Qwen（t395u）。"""
    v = str(value or "").strip().lower().replace(" ", "")
    v = _ENHANCE_ALIASES.get(v, v)
    return v if v in dict(LAST_FRAME_ENHANCE_OPTIONS) else LAST_FRAME_ENHANCE_DEFAULT


def last_frame_enhance_label(value) -> str:
    return dict(LAST_FRAME_ENHANCE_OPTIONS)[normalize_last_frame_enhance(value)]


def last_frame_upscaler(mode, *, status=None, account: str = ""):
    """选项 → ``upscale(path, target, style) -> PIL``（给 enhance_last_frame）；「不增强」返回 None。"""
    m = normalize_last_frame_enhance(mode)
    if m == "none":
        return None
    if m == "qn":
        return lambda p, t, s: qn_upscale(p, t, s, status=status)
    if m == "grok":
        return lambda p, t, s: grok_upscale(p, t, s, account=account, status=status)
    return lambda p, t, s: moss_upscale(p, t, s, status=status)


def enhance_segment_last_frame(frame_path: str, *, mode=LAST_FRAME_ENHANCE_DEFAULT, style: str = "",
                               status=None, account: str = "") -> tuple:
    """t376u: 按选项增强末帧。返回 (图路径, 是否增强了, 说明)；不增强 / 失败都返回原末帧。"""
    m = normalize_last_frame_enhance(mode)
    if m == "none":
        if not frame_path or not os.path.isfile(frame_path):
            raise FileNotFoundError(f"末帧不在：{frame_path}")
        return frame_path, False, "选了不增强"
    return enhance_last_frame(frame_path, style=style,
                              upscale=last_frame_upscaler(m, status=status, account=account))


def qn_upscale(frame_path: str, target, style: str = "", *, server=None, timeout_s: float = 600.0, status=None):
    """t376u: Qwen(QN) ComfyUI 图片编辑 · 提高分辨率（同 MOSS 的提示词口吻换成 Picture 1 + 项目画风）。"""
    import config_prompt
    from utility.image_upscale import comfy_upscale_canvas, upscale_init_denoise
    from utility.sd_image_processor import generate_image_qwen_edit

    pos, neg = config_prompt.build_comfy_upscale_prompt(target, backend="qn", style=style)
    canvas = comfy_upscale_canvas(target)
    return generate_image_qwen_edit(pos, [frame_path], server=server, negative=neg, adapt=False,
                                    width=canvas[0], height=canvas[1], timeout_s=timeout_s,
                                    status=status, init_denoise=upscale_init_denoise("qn"))  # t377u


def grok_upscale(frame_path: str, target, style: str = "", *, account: str = "", status=None):
    """t376u: Grok Image · 提高分辨率（同「图片修改 · 提高分辨率」的 Grok 提示词）。t377u: 第一行 = FAITHFUL RESTORE。"""
    import config_prompt
    from utility import chrome_account, grok_cdp

    prompt = config_prompt.style_lock_first(config_prompt.build_upscale_prompt(target, style))
    with chrome_account.use(account or ""):
        return grok_cdp.make_image(prompt, [frame_path], status)


def moss_upscale(frame_path: str, target, style: str = "", *, server=None, timeout_s: float = 600.0, status=None):
    """MOSS ComfyUI · 提高分辨率（同「图片修改 · 提高分辨率」的提示词 + 项目画风）。"""
    import config_prompt
    from utility.image_upscale import comfy_upscale_canvas, upscale_init_denoise
    from utility.sd_image_processor import generate_image_moss_edit

    pos, neg = config_prompt.build_comfy_upscale_prompt(target, backend="moss", style=style)
    canvas = comfy_upscale_canvas(target)
    return generate_image_moss_edit(pos, [frame_path], server=server, negative=neg, adapt=False,
                                    width=canvas[0], height=canvas[1], timeout_s=timeout_s,
                                    status=status, init_denoise=upscale_init_denoise("moss"))  # t377u
