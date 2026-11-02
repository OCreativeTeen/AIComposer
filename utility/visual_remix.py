# -*- coding: utf-8 -*-
"""t187u: 审阅文案 — 视觉：Remix 时把这一场的起始图（clip_image）一起交给本机 Strata（Qwen，支持看图），
让 visual 不和画面冲突。看图失败 / 没有图时由调用方退回纯文字 Remix。
t199u: 同时带上这一场的讲话（<1> <2> …）和人物，让视觉里的动作按对话的顺序和内容发展。
"""
import base64
import io
import os

VISUAL_IMAGE_REMIX_SYSTEM = """你是视频分镜编辑。用户给你一张起始画面（这一场视频的第一帧）和这一场的「视觉」描述。
把视觉描述改写成和这张图不冲突的版本：
- 以图为准：图里有几个人、谁站谁坐、在什么位置、穿什么、手里拿什么，视频一开始就是这样。描述里和图矛盾的部分要改掉或删掉
  （例如图里他已经坐在桌边，就不要写他进门、在玄关换鞋；图里她已经端着碗，就不要再写她从灶台盛汤）。
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
  说到手机时低头看手机；说「我陪你」时把手搭到对方手上）。说话的人和听的人都要有反应。
- 必须和起始图一致（人数、位置、衣着、道具从图里的状态接着发生）；最多一个大的位置变化，其余是表情、手势和小动作。
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
