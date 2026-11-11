# -*- coding: utf-8 -*-
"""t187u: 审阅文案 — 视觉：Remix 时把这一场的起始图（clip_image）一起交给本机 Strata（Qwen，支持看图），
让 visual 不和画面冲突。看图失败 / 没有图时由调用方退回纯文字 Remix。
t199u: 同时带上这一场的讲话（<1> <2> …）和人物，让视觉里的动作按对话的顺序和内容发展。
t223u: 看图调整（双击 Remix + 新建项目逐场出图后）先人物后视觉：actor 位置优先于 visual。
"""
import base64
import io
import os

VISUAL_IMAGE_REMIX_SYSTEM = """你是视频分镜编辑。用户给你一张起始画面（这一场视频的第一帧）和这一场的「视觉」描述。
把视觉描述改写成和这张图不冲突的版本：
- 以图为准（人数、姿势、道具、环境）：图里有几个人、谁站谁坐、穿什么、手里拿什么，视频一开始就是这样。描述里和图矛盾的部分要改掉或删掉
  （例如图里他已经坐在桌边，就不要写他进门、在玄关换鞋；图里她已经端着碗，就不要再写她从灶台盛汤）。
  若用户已给定锁定的人物括号（左/右/坐位），则人物位置以该括号为准，不得因图把左右换反（t223u actor-is-truth）。
- 动作从图里的状态接着往下发生；整场大约 10 秒，最多一个大的位置变化，其余是表情和小动作。不要加新的人。
- 保留场景的地点、时间、气氛和情绪重点，以及人物的名字（名字原样照抄）。
- 简短：2 到 4 句。用和原文相同的语言和字体（原文是繁体就用繁体，简体就用简体）。
- 只输出改写后的视觉描述，不要解释，不要标题。图和描述对不上时也一样：直接按图写，不要说明哪里不符，不要用 ** 或列表。
You are a storyboard editor. Rewrite the scene's visual description so it matches the start picture (the first frame):
people, positions, poses, clothing and props as shown; drop or change actions that contradict it; continue from that state;
about 10 seconds, at most one big change of position; no new people; keep names, place, time and mood; 2-4 sentences,
same language and script as the original. Output only the rewritten description."""

# t199u: 有讲话时追加的规则（图片版和纯文字版都用）
VISUAL_DIALOGUE_RULES = """
另外，用户还会给你这一场的「讲话」（<1> 是人物1 说的，<2> 是人物2 说的，以此类推）和人物名单。视觉要和讲话一拍一拍地同步：
- 按讲话的顺序写，每一句（或每一段）对应一拍：<2> 说到某件事时，人物2 在做什么、人物1 怎么反应；接着 <1> 回答时，人物1 做什么……
  句子的先后就是动作的先后。用人物的名字，不要写 <1> <2> 这种标记。
- 至少有一处具体、可信的动作 / 手势 / 视线 / 道具或环境变化，直接对应某一句话的内容（例如说到「打勾」时用手指在空中或纸上打勾；
  说「我陪你」时把手搭到对方手上）。说话的人和听的人都要有反应。
- 必须和起始图一致（人数、位置、衣着、道具从图里的状态接着发生；图里空着的手不凭空拿出东西，不写图里没有的物品）；最多一个大的位置变化，其余是表情、手势和小动作。
- 不能写和讲话内容相矛盾的动作或情绪；不要加新的人；不要把台词写进视觉（不加引号、不复述原句）；人物看着彼此或手上的东西，不看镜头。
- 简洁：讲话有好几拍时可以写到 5 个短句，每句只写一拍。
The user also gives the scene's dialogue (<1> = person 1, <2> = person 2 ...) and the cast. Follow the dialogue beat by beat, in
order: while <2> says X, person 2 does ... and person 1 reacts; then as <1> answers, person 1 ... Include at least one concrete,
physically plausible action, gesture, gaze or change in the place tied to a specific line's content (e.g. a ticking gesture on
"tick it off"). Stay consistent with the start picture; at most one big change of position; nothing that contradicts what is said;
no new people; no quoted lines; nobody looks at the camera; up to 5 short sentences, one beat each."""

VISUAL_TEXT_REMIX_SYSTEM = """你是视频分镜编辑。用户给你这一场的「视觉」描述（这一场视频里发生的动作和画面）。
把它改写得清楚、简短、可以拍：整场大约 10 秒，最多一个大的位置变化，其余是表情和小动作；不要加新的人；
保留地点、时间、气氛、情绪重点和人物的名字（原样照抄）；2 到 4 句；用和原文相同的语言和字体；只输出改写后的视觉描述。"""


def _image_data_url(path: str, side: int = 768) -> str:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _user_text(visual: str, names=(), language_label: str = "", speaking: str = "") -> str:
    names = [str(n) for n in (names or ()) if n]
    note = ""
    if names:
        note += "这一场的人物：" + "、".join(names) + "。\n"
        if (speaking or "").strip():
            note += "说话人对应：" + "，".join(f"<{i}> = 人物{i} {n}" for i, n in enumerate(names, 1)) + "。\n"
    if language_label:
        note += f"输出语言：{language_label}。\n"
    if (speaking or "").strip():
        note += "讲话（按顺序）：\n" + speaking.strip() + "\n\n"
    return note + "视觉描述原文：\n" + (visual or "").strip()


def _chat(messages) -> str:
    from utility import llm_api

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    resp = api._chat_completions(llm_api.STRATA, messages)
    return (resp.choices[0].message.content or "").strip() if resp and resp.choices else ""


def remix_visual_with_image(visual: str, image_path: str, *, names=(), language_label: str = "",
                            speaking: str = "") -> str:
    """返回改写后的 visual；图不在、Strata 不能看图或返回空时抛异常（调用方退回纯文字 / 保留原文）。

    t199u: ``speaking`` = 这一场的讲话（<1> <2> …），``names`` 按 <N> 的顺序；讲话为空时和以前一样。
    """
    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError("没有起始图")
    system = VISUAL_IMAGE_REMIX_SYSTEM + (VISUAL_DIALOGUE_RULES if (speaking or "").strip() else "")
    user = [
        {"type": "text", "text": _user_text(visual, names, language_label, speaking)},
        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
    ]
    out = _chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    if not out:
        raise RuntimeError("Strata 看图改写返回空")
    return out


def remix_visual_text(visual: str, *, names=(), language_label: str = "", speaking: str = "") -> str:
    """t199u: 没有图 / 看图失败时的纯文字改写，同样按讲话同步（对话框的退路用）。"""
    system = VISUAL_TEXT_REMIX_SYSTEM + (VISUAL_DIALOGUE_RULES if (speaking or "").strip() else "")
    out = _chat([{"role": "system", "content": system},
                 {"role": "user", "content": _user_text(visual, names, language_label, speaking)}])
    if not out:
        raise RuntimeError("Strata 纯文字改写返回空")
    return out


# t158u / t223u: scene adjust = actors FIRST (count/seats), then visual (story plot + image enrich).
# Shared by Remix (double-click 视觉) and new-project cover/scene-image analysis.

ACTORS_FROM_IMAGE_SYSTEM = """你是视频分镜编辑。用户给你一张起始画面、人物名单（可含已有括号）、可选的讲话。
只输出 JSON（不要别的文字、不要 ```）：{"actors": {"1": "人物1 在这一场的样子", "2": "..."}, "new_actors": {}}
规则（t223u 人物优先）：
- 先定人物：actors 键是人物序号（与说话人 <N> 对应）；非空描述的人数应等于讲话里出现过的不同 <N>（再加上要补的缺失说话人）。
- 已有的 actor 括号（衣着、左/右/座位）是谁是谁的唯一准则。用括号里的衣着与座位去图里对人；不得把左右换反，不得用视觉原文里的左右去改座位。
- 若还没有括号：从图写衣服颜色款式、明显特征、表情、位置（左/右/前/后，坐或站）。
- 有括号时：保留其中的座位与衣着，只用图丰富表情/姿势/道具（不改左右）。
- 每个值一个短句（15–40字）；不写名字，不用 / | 和括号；图里没有就写空字符串；语言字体跟用户要求一致。
You are a storyboard editor. Output actors JSON only. Existing actor parenthesis (clothing, left/right/seat) is GROUND TRUTH —
match people in the image by that; never swap seats. Enrich expression/pose from the image. No names, no / | or brackets."""

VISUAL_AFTER_ACTORS_RULES = """
用户已先定好人物括号（衣着与左/右/座位）——这是人物位置的唯一准则（t223u）。
改写视觉时：
- 尽量保留原视觉的故事情节与拍子顺序；只用图里看得到的道具/表情/环境细节丰富，不要换故事。
- 人物左/右/坐在…必须跟已定好的人物括号一致；不得因图把两人左右换反，也不得用旧视觉里冲突的座位。
- 有讲话时仍按讲话一拍一拍写动作；说话人脸和嘴可见，不写捂嘴/低头/走进画面。
- 只输出改写后的视觉描述（不要 JSON、不要解释）。
Actors are already locked (clothing + left/right/seat). Keep the story plot; enrich from the image; never swap seats
against the locked actor notes. Output only the rewritten visual description."""

# Kept for reference / older call sites; remix_scene_full no longer uses one-shot visual+actors JSON.
SCENE_ACTORS_RULES = """
(deprecated t223u — use ACTORS_FROM_IMAGE_SYSTEM then VISUAL_AFTER_ACTORS_RULES)
"""


MISSING_SPEAKERS_RULES = """
- 讲话里有些 <N> 在人物名单里没有（见「缺的说话人」）：这些人也在这一场、也要说话。从讲话里的称呼和图判断他/她的名字
  （讲话里别人怎么叫就用什么名字，看不出就写「人物N」）、性别、年龄段、族裔，写进 JSON 的 "new_actors"，
  并且在 visual 里写到这个人（在画面哪里、说话时的动作表情），actors 里也给他/她这一场的样子。
  "new_actors": {"2": {"name": "小雅", "gender": "woman", "age": "youth", "ethnicity": "chinese", "look": "这一场的样子短句"}}
  gender 只能 man / woman；age 只能 kids / teenager / youth / mature / senior；ethnicity 用 chinese / english 等英文小写。"""


def speaking_numbers(speaking: str) -> list:
    """讲话里出现过的说话人序号 <N>（从小到大）。"""
    import re

    return sorted({int(x) for x in re.findall(r"<\s*(\d+)\s*>", speaking or "")})


def _parse_actor_notes_json(out: str, missing=()) -> tuple:
    """Parse actors / new_actors JSON from a Strata reply. Returns (notes, added)."""
    import json
    import re

    m = re.search(r"\{.*\}", out or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {}, {}
    notes = {}
    for k, v in (data.get("actors") or {}).items():
        try:
            n = int(str(k).strip())
        except ValueError:
            continue
        if str(v or "").strip():
            notes[n] = str(v).strip()
    added = {}
    for k, v in (data.get("new_actors") or {}).items():
        try:
            n = int(str(k).strip())
        except ValueError:
            continue
        if n in (missing or ()) and isinstance(v, dict):
            added[n] = {x: str(v.get(x) or "").strip() for x in ("name", "gender", "age", "ethnicity", "look")}
    return notes, added


def _existing_actor_paren_lines(actor_text: str, names) -> str:
    """Lines of existing actor parentheses (authoritative seats) for the actors-first pass."""
    import config_prompt

    rows = config_prompt._scene_speakers({"actor": actor_text or ""})
    lines = []
    for i, (r, nm) in enumerate(zip(rows, names), 1):
        note = config_prompt.actor_scene_note(r) or ""
        lines.append(f"{i} = {nm}" + (f"（已有括号/唯一座位准则：{note}）" if note else ""))
    return "\n".join(lines)


def _locked_actor_block(names, notes: dict) -> str:
    lines = ["已定好的人物括号（位置唯一准则，不得换左右）："]
    for i, nm in enumerate(names or (), 1):
        look = (notes or {}).get(i) or ""
        lines.append(f"- {i} = {nm}: {look or '（无）'}")
    return "\n".join(lines)


def correct_actors_from_image(image_path: str, *, names=(), actor_text: str = "", language_label: str = "",
                              speaking: str = "", missing=()) -> tuple:
    """t223u phase 1: fix/align actor scene notes from the image under actor-is-truth.
    Returns (notes, added)."""
    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError("没有起始图")
    names = [str(n) for n in (names or ()) if n]
    system = ACTORS_FROM_IMAGE_SYSTEM + (MISSING_SPEAKERS_RULES if missing else "")
    miss_note = ("\n缺的说话人（人物名单里没有，要补）："
                 + "，".join(f"<{n}>" for n in missing)) if missing else ""
    body = ""
    if language_label:
        body += f"输出语言：{language_label}。\n"
    if (speaking or "").strip():
        body += "讲话（按顺序）：\n" + speaking.strip() + "\n\n"
        body += "说话人对应：" + "，".join(
            f"<{i}> = 人物{i} {n}" for i, n in enumerate(names, 1)) + "。\n"
    body += "人物序号与已有括号：\n" + (_existing_actor_paren_lines(actor_text, names) or "（无）")
    body += miss_note
    user = [
        {"type": "text", "text": body},
        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
    ]
    out = _chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    if not out:
        raise RuntimeError("Strata 看图调人物返回空")
    return _parse_actor_notes_json(out, missing=missing)


def correct_visual_from_image(visual: str, image_path: str, *, names=(), notes=None, language_label: str = "",
                              speaking: str = "") -> str:
    """t223u phase 2: rewrite visual after actors are locked — keep story plot, enrich from image,
    never contradict locked actor seats."""
    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError("没有起始图")
    system = (VISUAL_IMAGE_REMIX_SYSTEM + (VISUAL_DIALOGUE_RULES if (speaking or "").strip() else "")
              + VISUAL_AFTER_ACTORS_RULES)
    text = _user_text(visual, names, language_label, speaking)
    text += "\n" + _locked_actor_block(names, notes or {})
    user = [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
    ]
    out = _chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    if not out:
        raise RuntimeError("Strata 看图改写视觉返回空")
    return out.strip()


def remix_scene_full(visual: str, image_path: str, *, actor_text: str = "", language_label: str = "",
                     speaking: str = "") -> dict:
    """t161u / t223u: shared by new-project cover analysis AND visual double-click Remix.
    Actors first (count = distinct speakers in 讲话; seats from actor-is-truth + image), then visual.
    Returns {"visual", "notes": {N: look}, "added": {...}, "actor": new actor text, "missing": [...]}."""
    import config_prompt
    import project_manager

    names = [config_prompt._speaker_identity(r)[0] for r in config_prompt._scene_speakers({"actor": actor_text})]
    missing = [n for n in speaking_numbers(speaking) if n > len(names)]
    visual2, notes, added = _remix_scene(visual, image_path, names=names, language_label=language_label,
                                         speaking=speaking, missing=missing, actor_text=actor_text)
    actor = project_manager.set_actor_scene_notes(actor_text or "", notes)
    actor = project_manager.add_missing_actors(actor, missing, added, notes)
    return {"visual": visual2, "notes": notes, "added": added, "actor": actor, "missing": missing}


def remix_scene_with_image(visual: str, image_path: str, *, names=(), language_label: str = "",
                           speaking: str = "", actor_text: str = "") -> tuple:
    """t158u / t223u: returns (visual, {speaker_index: look}). Actors-first then visual."""
    v, notes, _added = _remix_scene(visual, image_path, names=names, language_label=language_label,
                                    speaking=speaking, missing=(), actor_text=actor_text)
    return v, notes


def _remix_scene(visual: str, image_path: str, *, names=(), language_label: str = "",
                 speaking: str = "", missing=(), actor_text: str = "") -> tuple:
    """t223u: (1) correct actors from image under actor-is-truth, (2) then adjust visual.
    Returns (visual, {N: look}, {N: new_person})."""
    names = [str(n) for n in (names or ()) if n]
    notes, added = correct_actors_from_image(
        image_path, names=names, actor_text=actor_text, language_label=language_label,
        speaking=speaking, missing=missing)
    # If Strata returned no actor notes but we already had parentheses, keep those seats
    if not notes and actor_text:
        try:
            import config_prompt
            rows = config_prompt._scene_speakers({"actor": actor_text})
            for i, r in enumerate(rows, 1):
                n = config_prompt.actor_scene_note(r)
                if n:
                    notes[i] = n
        except Exception:
            pass
    visual2 = correct_visual_from_image(
        visual, image_path, names=names, notes=notes, language_label=language_label, speaking=speaking)
    return visual2, notes, added


def accept_auto_remix(old: str, new: str) -> str:
    """t198u: 自动调整视觉（不经过对话框）能不能直接写回：返回 '' = 可以，否则返回不用的原因。"""
    o, n = (old or "").strip(), (new or "").strip()
    if not n:
        return "结果是空的"
    if n == o:
        return "和原文一样"
    if len(n) < max(8, int(len(o) * 0.3)):
        return f"结果太短（{len(n)} 字，原文 {len(o)} 字）"
    if len(n) > max(400, int(len(o) * 2.5)):  # t199u: 模型在解释（图和描述对不上等），不是视觉描述
        return f"结果太长（{len(n)} 字，原文 {len(o)} 字），像是解释"
    if "**" in n or any(w in n for w in ("不符", "不匹配", "不相符", "對不上", "对不上", "以下根據", "以下根据", "重要提示")):
        return "结果像是在解释图和描述不符，不是视觉描述"
    return ""
