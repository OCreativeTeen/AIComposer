# -*- coding: utf-8 -*-
"""t436u: 建项目时整理场景（也给预览窗口的「整理场景」按钮用）。

生成场景时只按完整的故事片段分场，不管讲话多长。建项目时逐场整理：
1. 每一场都请 Strata 按这一场的讲话和人物改写视觉（有参考图就看图：``remix_scene_full``，
   没有图：``remix_visual_text``），让画面跟着讲话的节奏发展。原文留在 visual_before_remix / actor_before_remix。
2. 讲话超过 115 个字（汉字 1 个算 1，英文词 / 数字 1 个算 2，标点不算）的场按句子拆成连续的几场（每场 ≤115 字；
   音视频来源按文字稿时间，每场也不超过 25 秒）。人物、集号、参考图都沿用原场，caption 一样。
3. 同一场拆出来的几段一起交给 Strata 再改写，视觉连贯：原来的大动作拆成一串连贯的小动作。
4. 视频来源：拆出来的每一段取自己时间段中间的一帧，放在参考图的第一张（原来的图留在后面）。
5. 每一场写分镜 ``shot``：没拆的 "1-1"；拆成 3 段是 "1-3"、"2-3"、"3-3"。

Strata 出错或用户取消：抛 PrepFailed / PrepCancelled，调用方照原来的场景建项目。输入的场景不会被改动。
"""
from __future__ import annotations

import copy
import os
import re
import time

SHOT_FIELD = "shot"
MAX_UNITS = 115
MAX_SECONDS = 25.0

_SPEAKER_RE = re.compile(r"[<＜](\d+)(s?)[>＞]")
_PAUSE_RE = re.compile(r"[<＜]\s*\d*\.\d+\s*[>＞]")
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_WORD_RE = re.compile(r"[A-Za-z0-9\u00c0-\u024f]+(?:['’][A-Za-z]+)*")
_SENTENCE_RE = re.compile(
    r".+?(?:[。！？!?；;…]+[”’」』）)\]》\"']*|\.(?=\s|$)[”’\"']*|$)", re.S
)


class PrepCancelled(Exception):
    """用户取消了整理。"""


class PrepFailed(Exception):
    """Strata 出错，整理没做完。"""


def speaking_units(text: str) -> int:
    """讲话字数：汉字 1 个 = 1；英文词、数字串 1 个 = 2；标点、<N> 说话人标记、<0.5> 停顿都不算。"""
    body = _PAUSE_RE.sub(" ", str(text or ""))
    body = _SPEAKER_RE.sub(" ", body)
    cjk = len(_CJK_RE.findall(body))
    words = len(_WORD_RE.findall(_CJK_RE.sub(" ", body)))
    return cjk + 2 * words


def shot_label(j: int, m: int) -> str:
    return f"{int(j)}-{int(m)}"


def parse_shot(value):
    """"2-3" → (2, 3)；写得不对返回 None。"""
    m = re.fullmatch(r"\s*(\d+)\s*[-/]\s*(\d+)\s*", str(value or ""))
    if not m:
        return None
    j, n = int(m.group(1)), int(m.group(2))
    return (j, n) if 1 <= j <= n else None


# ---------------------------------------------------------------- 拆讲话（没有文字稿时间）
def speaking_pieces(speaking: str, max_units: int = MAX_UNITS) -> list:
    """讲话 → 一句一句 [{"mark": "1" / "1s", "text", "units", "last"}]。
    第一个标记前面的字算第 1 个人。超过上限的一句在分句标点处切开（last=False 表示后面还是同一句）。"""
    from utility.media_transcript import _split_long_sentence

    text = str(speaking or "")
    runs = []
    pos, mark = 0, "1"
    for m in _SPEAKER_RE.finditer(text):
        if text[pos:m.start()].strip():
            runs.append((mark, text[pos:m.start()]))
        mark = m.group(1) + m.group(2)
        pos = m.end()
    if text[pos:].strip():
        runs.append((mark, text[pos:]))
    out = []
    for mark, body in runs:
        for sent in _SENTENCE_RE.findall(body.strip()):
            sent = sent.strip()
            if not sent:
                continue
            if speaking_units(sent) > max_units:
                parts = _split_long_sentence(sent, max_units)
            else:
                parts = [sent]
            for k, part in enumerate(parts):
                out.append({"mark": mark, "text": part.strip(), "units": speaking_units(part),
                            "last": k == len(parts) - 1})
    return out


def _join(left: str, right: str, sentence_end: bool) -> str:
    if not left:
        return right
    if sentence_end:
        return left + " " + right
    if _CJK_RE.search(left[-1:]) or _CJK_RE.search(right[:1]) or left[-1:] in "，、；：":
        return left + right
    return left + " " + right


def _pieces_text(pieces: list) -> str:
    parts: list = []
    previous = None
    prev_last = True
    for p in pieces:
        if p["mark"] != previous:
            parts.append(f"<{p['mark']}> {p['text']}")
            previous = p["mark"]
        else:
            parts[-1] = _join(parts[-1], p["text"], prev_last)
        prev_last = p["last"]
    return " ".join(parts).strip()


def split_speaking_text(speaking: str, max_units: int = MAX_UNITS) -> list:
    """讲话超过上限 → 按句拆成最少的几段，每段 ≤ 上限、尽量一样长，每段开头写说话人 <N>。没超返回 [原文]。"""
    from utility.media_transcript import _balanced_groups

    if speaking_units(speaking) <= max_units:
        return [speaking]
    pieces = speaking_pieces(speaking, max_units)
    units = [p["units"] for p in pieces]
    if len(pieces) < 2:
        return [speaking]
    k = max(2, -(-sum(units) // max_units))
    while k < len(pieces):
        groups = _balanced_groups(units, k)
        if all(sum(units[a:b]) <= max_units for a, b in groups):
            break
        k += 1
    else:
        groups = [(i, i + 1) for i in range(len(pieces))]
    return [_pieces_text(pieces[a:b]) for a, b in groups]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def split_scene_by_text(scene: dict, max_units: int = MAX_UNITS) -> list:
    """没有文字稿时间时拆一场：按讲话拆成几段（深拷贝原场，只改 speaking）。
    原场有 start 和 end 就按字数比例分时间；只有 start 的只留给第一段。没超返回 [scene]。"""
    texts = split_speaking_text(scene.get("speaking") or "", max_units)
    if len(texts) < 2:
        return [scene]
    st, en = _num(scene.get("start")), _num(scene.get("end"))
    total = sum(speaking_units(t) for t in texts) or 1
    done = 0
    parts = []
    for j, text in enumerate(texts):
        part = copy.deepcopy(scene)
        part["speaking"] = text
        part.pop("speaking_timing", None)
        if st is not None and en is not None and en > st:
            a = st + (en - st) * done / total
            done += speaking_units(text)
            b = en if j == len(texts) - 1 else st + (en - st) * done / total
            part["start"], part["end"] = round(a, 2), round(b, 2)
        else:  # 时间不全：start 只留给第一段，end 只留给最后一段
            if j > 0:
                part.pop("start", None)
            if j < len(texts) - 1:
                part.pop("end", None)
        parts.append(part)
    return parts


def split_scenes(scenes: list, transcript_text: str = "", *, max_units: int = MAX_UNITS,
                 max_seconds: float = MAX_SECONDS) -> tuple:
    """讲话太长的场拆开。返回 (新的场景列表, [(原场下标, [拆出来的几场])])。
    有带时间的文字稿（音视频来源）先按文字稿时间拆（≤115 字、≤25 秒），对不上的场再按讲话文字拆。"""
    out = list(scenes or [])
    groups: list = []
    timed_ids = set()
    if (transcript_text or "").strip():
        from utility.media_transcript import split_long_transcript_scenes

        g: list = []
        out, _added = split_long_transcript_scenes(out, transcript_text, max_units=max_units,
                                                    max_seconds=max_seconds, groups_out=g)
        for idx, parts in g:
            groups.append((idx, parts))
            timed_ids.update(id(p) for p in parts)
    # 文字稿拆过的场之外，讲话还超的按文字拆
    final: list = []
    orig_pos = {}
    pos = 0
    by_part = {id(p): idx for idx, parts in groups for p in parts}
    for s in out:
        if id(s) in by_part:
            final.append(s)
            continue
        # 没被文字稿拆的场：它在原列表里的位置
        while pos < len(scenes or []) and scenes[pos] is not s:
            pos += 1
        orig = pos if pos < len(scenes or []) else None
        if isinstance(s, dict) and speaking_units(s.get("speaking") or "") > max_units:
            parts = split_scene_by_text(s, max_units)
            if len(parts) > 1:
                groups.append((orig, parts))
                final.extend(parts)
                continue
        final.append(s)
    groups.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return final, groups


# ---------------------------------------------------------------- Strata
def scene_names(actor_text: str) -> list:
    """actor → 说话人名字（按 <N> 的顺序），和双击 Remix 用的一样。"""
    try:
        import config_prompt

        return [config_prompt._speaker_identity(r)[0] for r in config_prompt._scene_speakers({"actor": actor_text or ""})]
    except Exception:  # noqa: BLE001
        return []


def _first_image(scene) -> str:
    from utility.material_image_matcher import first_ref_image

    return first_ref_image(scene)


def _split_visual_ok(old: str, new: str) -> bool:
    n = (new or "").strip()
    if not n or "**" in n:
        return False
    return len(n) <= max(400, int(len((old or "").strip()) * 2.5))


class _Strata:
    """真的 Strata 调用（测试里换成假的）。"""

    @staticmethod
    def remix_full(visual, image, *, actor_text, language_label, speaking):
        from utility.visual_remix import remix_scene_full

        return remix_scene_full(visual, image, actor_text=actor_text, language_label=language_label, speaking=speaking)

    @staticmethod
    def remix_text(visual, *, names, language_label, speaking):
        from utility.visual_remix import remix_visual_text

        return remix_visual_text(visual, names=names, language_label=language_label, speaking=speaking)

    @staticmethod
    def remix_group(visual, parts, *, names, language_label, image_path):
        from utility.visual_remix import remix_split_group

        return remix_split_group(visual, parts, names=names, language_label=language_label, image_path=image_path)


def remix_scene(scene: dict, *, strata=_Strata, language_label: str = "", convert=None, log=print, label="") -> bool:
    """一场按讲话 + 人物（+ 参考图）改写视觉，写回 scene。返回是否改了。Strata 出错抛异常。"""
    from utility.visual_remix import accept_auto_remix

    conv = convert or (lambda t: t)
    visual = str(scene.get("visual") or "")
    if not visual.strip():
        log(f"整理场景：{label} 没有视觉文字，跳过")
        return False
    actor = str(scene.get("actor") or "")
    speaking = str(scene.get("speaking") or "")
    image = _first_image(scene)
    new_actor = None
    if image:
        res = strata.remix_full(visual, image, actor_text=actor, language_label=language_label, speaking=speaking)
        new_visual = conv(res.get("visual") or "")
        new_actor = conv(res.get("actor") or "") or None
    else:
        new_visual = conv(strata.remix_text(visual, names=scene_names(actor), language_label=language_label,
                                            speaking=speaking) or "")
    why = accept_auto_remix(visual, new_visual)
    if why:
        log(f"整理场景：{label} {why}，保留原来的视觉")
        return False
    scene.setdefault("visual_before_remix", visual)
    scene["visual"] = new_visual
    if new_actor and new_actor != actor:
        scene.setdefault("actor_before_remix", actor)
        scene["actor"] = new_actor
    return True


def remix_group(parts: list, parent_visual: str, *, strata=_Strata, language_label: str = "", convert=None,
                log=print, label="") -> bool:
    """同一场拆出来的几段一起改写视觉（连贯）。Strata 出错抛异常；结果不合用保留原场的视觉。"""
    conv = convert or (lambda t: t)
    if not (parent_visual or "").strip():
        return False
    first = parts[0]
    vis = strata.remix_group(parent_visual, [p.get("speaking") or "" for p in parts],
                             names=scene_names(first.get("actor") or ""), language_label=language_label,
                             image_path=_first_image(first))
    vis = [conv(v or "") for v in (vis or [])]
    if len(vis) != len(parts) or not all(_split_visual_ok(parent_visual, v) for v in vis):
        log(f"整理场景：{label} 分镜视觉不合用，几段都保留原场的视觉")
        return False
    for p, v in zip(parts, vis):
        p.setdefault("visual_before_remix", parent_visual)
        p["visual"] = v
    return True


def attach_part_frames(parts: list, video_path: str, *, picker=None, out_dir: str = "", log=print) -> int:
    """视频来源：拆出来的每一段取自己时间段中间的一帧，放在 ref_images 第一张（原来的图留在后面）。返回加了几张。"""
    from utility import material_image_matcher as mim

    if not video_path or not os.path.isfile(video_path):
        return 0
    out_dir = out_dir or os.path.join(mim.working_dir_for(video_path), f"shots_{time.strftime('%Y%m%d_%H%M%S')}")
    found = (picker or mim.extract_scene_frames)(video_path, parts, out_dir, log=log) or {}
    added = 0
    for idx, imgs in found.items():
        if not (0 <= int(idx) < len(parts)) or not imgs:
            continue
        part = parts[int(idx)]
        have = [r for r in (part.get(mim.REF_FIELD) or []) if isinstance(r, (dict, str))]
        new = []
        for img in imgs:
            if not img.get("path"):
                continue
            rec = mim.ref_entry(img)
            rec["source"] = "shot_frame"  # t442u: 复制进项目时编号排在原图后面（project_ref_images.SHOT_FRAME_SOURCE）
            if img.get("time") is not None:
                rec["time"] = img["time"]
            new.append(rec)
        keys = {os.path.normcase(os.path.abspath(r["path"])) for r in new}
        rest = [r for r in have
                if os.path.normcase(os.path.abspath(str(r.get("path") if isinstance(r, dict) else r))) not in keys]
        part[mim.REF_FIELD] = new + rest
        added += len(new)
    return added


def _set_shots(final: list, groups: list) -> None:
    split_ids = {}
    for _idx, parts in groups:
        for j, p in enumerate(parts, 1):
            split_ids[id(p)] = shot_label(j, len(parts))
    for s in final:
        if not isinstance(s, dict):
            continue
        if id(s) in split_ids:
            s[SHOT_FIELD] = split_ids[id(s)]
        elif not str(s.get(SHOT_FIELD) or "").strip():  # t440u: 已有的 shot 不改
            s[SHOT_FIELD] = shot_label(1, 1)


def prepare_scenes(scenes: list, *, transcript_text: str = "", source_kind: str = "", source_path: str = "",
                   language_label: str = "", convert=None, strata=_Strata, frame_picker=None,
                   max_units: int = MAX_UNITS, max_seconds: float = MAX_SECONDS,
                   progress=None, cancel=None, log=print) -> tuple:
    """整理场景，返回 (新的场景列表, 报告)。不改输入。Strata 出错抛 PrepFailed，取消抛 PrepCancelled。"""
    work = copy.deepcopy([s for s in (scenes or []) if isinstance(s, dict)])
    report = {"remixed": 0, "kept": 0, "split": 0, "added": 0, "group_remixed": 0, "frames": 0}

    def _check():
        if cancel and cancel():
            raise PrepCancelled("取消了")

    def _say(msg):
        if progress:
            progress(msg)

    n = len(work)
    for i, sc in enumerate(work, 1):
        _check()
        _say(f"改写视觉 {i}/{n}")
        try:
            ok = remix_scene(sc, strata=strata, language_label=language_label, convert=convert, log=log,
                             label=f"第{i}场")
        except (PrepCancelled, PrepFailed):
            raise
        except Exception as exc:  # noqa: BLE001
            raise PrepFailed(f"第{i}场 Strata 改写视觉失败：{exc}") from exc
        report["remixed" if ok else "kept"] += 1
    _check()
    _say("按讲话长度拆分")
    final, groups = split_scenes(work, transcript_text, max_units=max_units, max_seconds=max_seconds)
    report["split"] = len(groups)
    report["added"] = len(final) - len(work)
    for g, (idx, parts) in enumerate(groups, 1):
        _check()
        _say(f"分镜视觉连贯 {g}/{len(groups)}")
        parent = work[idx] if idx is not None and 0 <= idx < len(work) else parts[0]
        label = f"第{(idx or 0) + 1}场"
        try:
            if remix_group(parts, str(parent.get("visual") or ""), strata=strata, language_label=language_label,
                           convert=convert, log=log, label=label):
                report["group_remixed"] += 1
        except (PrepCancelled, PrepFailed):
            raise
        except Exception as exc:  # noqa: BLE001
            raise PrepFailed(f"{label} Strata 分镜改写失败：{exc}") from exc
        if str(source_kind or "").strip().lower() == "video":
            try:
                report["frames"] += attach_part_frames(parts, source_path, picker=frame_picker, log=log)
            except Exception as exc:  # noqa: BLE001
                log(f"⚠️ 整理场景：{label} 拆开的几段没取到画面：{exc}")
    _set_shots(final, groups)
    try:  # 拆开以后人物编号再对一次（只重排 / 补位，不删内容）
        from utility.speaker_ids import align_story_speakers

        final, _notes = align_story_speakers(final)
    except Exception as exc:  # noqa: BLE001
        log(f"⚠️ 整理场景：人物编号检查没做：{exc}")
    return final, report


def report_text(report: dict, before: int, after: int) -> str:
    return (f"改写视觉 {report.get('remixed', 0)} 场（保留原文 {report.get('kept', 0)} 场）；"
            f"拆开 {report.get('split', 0)} 场 → 共 {after} 场（原来 {before} 场）；"
            f"分镜视觉连贯 {report.get('group_remixed', 0)} 组" +
            (f"；分镜取画面 {report['frames']} 张" if report.get("frames") else ""))
