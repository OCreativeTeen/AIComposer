"""t426u: MiniMax 无讲话档（M0 忠实动画 / M1 无讲话场景）的 H3 提示词：Pixaroma Act 结构，只写正面描述。

字段：subject_definitions / summary / retention_analysis / detailed_description / overall_soundscape /
non_diegetic_music。没有讲话、字幕、旁白的任何字眼；声音字段明确只有安静的环境声；FYI 只进画面描述。"""
from __future__ import annotations

from dataclasses import dataclass, field

from prompt_profiles import blocks
from prompt_profiles.select import M0_FAITHFUL

PIC = blocks.PIC


@dataclass
class H3Build:
    prompt: str
    allow_raw: list = field(default_factory=list)  # 原样（没翻译）放进去的几段，校验时允许有中文
    fyi_text: str = ""  # 放进去的 FYI 句子（校验它只在画面描述里）
    visual_text: str = ""  # t429u: 场景描述那句（写的是图里本来就有的东西，不查人物词）


def _sentence(text: str) -> str:
    t = " ".join(str(text or "").split()).strip()
    if t and t[-1] not in ".!?。！？":
        t += "."
    return t


def _count_word(n: int) -> str:
    return {1: "one person", 2: "two people", 3: "three people", 4: "four people"}.get(n, f"{n} people")


def _cast_phrase(cast: list) -> str:
    items = [("an " if c[:1].lower() in "aeiou" else "a ") + c for c in cast if c]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_h3(ctx, en: dict | None = None) -> H3Build:
    """en = Strata 译好的英文画面方向 {visual, story, fyi}；没有（没勾 Strata / 失败）就把原文放进画面描述。"""
    en = dict(en or {})
    raw = []

    def slot(key: str) -> str:
        val = (en.get(key) or "").strip()
        if val:
            return val
        orig = (getattr(ctx, key, "") or "").strip()
        if orig:
            raw.append(orig)
        return orig

    style = blocks.style_en(ctx.style)
    m0 = ctx.profile == M0_FAITHFUL
    n = len(ctx.cast) if ctx.use_actor else 0

    # subject_definitions
    if n:
        subj1 = (f"- <Subject 1> is the {_count_word(n)} already in {PIC} ({_cast_phrase(ctx.cast)}), each with the same "
                 "look, clothes and place as in the picture.")
    else:  # t429u: 不提动物 / 人物这类词，只说图里已经画了的东西
        subj1 = (f"- <Subject 1> is exactly what {PIC} already shows, each with the same look and place as in the "
                 "picture, and nothing more.")
    defs = "\n".join([
        f"- {PIC} is the start image and first frame of the video, showing the base scene in {style}.",
        subj1,
        f"- <Subject 2> is the surroundings of {PIC}: the same place, background and light.",
    ])

    # summary
    if m0:
        summary = (f"One continuous shot in {style} that gently brings {PIC} to life: <Subject 1> and <Subject 2> keep "
                   "the content, look and keywords of the picture while small natural movement runs through the scene.")
    elif ctx.use_actor:
        summary = (f"One continuous shot in {style} inside the base scene of {PIC}: the moment is shown through "
                   "movement, gesture and expression of <Subject 1> within <Subject 2>.")
    else:  # t429u: 没勾人物：靠镜头、光线、环境和关键词讲
        summary = (f"One continuous shot in {style} inside the base scene of {PIC}: the moment is carried by the "
                   "camera, the light, the gently moving environment and the keywords of <Subject 2>, with <Subject 1> "
                   "staying as it is in the picture.")
    if ctx.place:
        summary += f" The setting is {ctx.place}."

    retention = (f"{PIC} is the first frame. <Subject 1> and <Subject 2> keep their look, identity, size and place from "
                 "the first frame to the last; the art style, colours and light of the picture stay the same.")

    # detailed_description
    locked = [blocks.camera(ctx.camera), blocks.art_style_lock(ctx.style), blocks.one_base_shot(),
              blocks.objects_lock()]
    if m0:
        locked.append(blocks.faithful())
    if not ctx.use_actor:
        locked.append(blocks.no_new_people())
    locked += [blocks.caption(ctx.text), blocks.light(ctx.visual, ctx.start_image)]
    lines = ["[Shot 1] " + " ".join(x for x in locked if x)]

    if m0:  # t429u: 不写呼吸 / 姿势（图里没人时会被画出一个人来）
        lines.append(f"Throughout the clip what is in {PIC} comes gently alive in place: light and shadow drift slowly "
                     "across <Subject 2>, and cloth, leaves, smoke or water move softly where they already are.")
    else:
        vis = slot("visual")
        if vis:
            lines.append(_sentence(f"Throughout the clip, {vis}"))
        if ctx.use_actor:
            story = slot("story")
            if story:
                lines.append(_sentence(f"Throughout the clip <Subject 1> acts out this moment through movement, "
                                       f"gesture and expression only: {story}"))
        else:  # t429u: 没勾人物：讲话当故事内容只译成气氛 / 事件；没译成英文就不放原文（原文里的妻子、弟弟会被画出来）
            story = (en.get("story") or "").strip()
            if story or ctx.story.strip():
                lines.append(blocks.STORY_THROUGH_SCENE)
            if story:
                lines.append(_sentence(f"Throughout the clip, {story}"))
        if not vis and not story and ctx.use_actor:
            lines.append("Throughout the clip <Subject 1> moves calmly and naturally within <Subject 2>, with small "
                         "gestures and expressions.")
        elif not vis and not story and not ctx.story.strip():
            lines.append(f"Throughout the clip what is in {PIC} comes gently alive in place: light and shadow drift "
                         "slowly across <Subject 2>, and cloth, leaves, smoke or water move softly where they already are.")
        if ctx.stage_line:
            lines.append(_sentence(ctx.stage_line))
    fyi_text = ""
    fyi = slot("fyi")
    if fyi:
        fyi_text = _sentence(f"Throughout the clip, {fyi}")
        lines.append(fyi_text)

    prompt = "\n".join([
        "subject_definitions:", defs, "",
        "summary:", summary, "",
        "retention_analysis:", retention, "",
        "detailed_description:", "\n".join(lines), "",
        "overall_soundscape:", blocks.SOUNDSCAPE, "",
        "non_diegetic_music:", blocks.MUSIC,
    ])
    return H3Build(prompt=prompt, allow_raw=raw, fyi_text=fyi_text,
                   visual_text=_sentence(f"Throughout the clip, {vis}") if (not m0 and vis) else "")


def build_h3_prompt(ctx, en: dict | None = None) -> str:
    return build_h3(ctx, en).prompt
