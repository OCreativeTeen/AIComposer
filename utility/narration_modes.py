"""t258 / t262 / t263: 叙事方式（短故事 / 播客 / 故事对话 / 故事表演）——预览窗口（场景生成、节目生成）和魔法工作流「生场视频」窗口共用的唯一一张表。

这里只放：选项的存值和中文名、旧存值（旧标签 / 旧 key / 旧叙事风格）怎么认、每种方式「说话」和「表演」的规则文字。
三个地方（场景生成、节目生成、视频生成）都从这里取同一份规则文字，所以同一个方式三边一字不差。
t262: 主持人节目已并入故事表演（两者几乎重合），不再是单独的方式；旧存值一律当故事表演读。
t263: 没有「不知道」的情况。人物栏（场景生成、节目生成）和场景 actor（视频生成）里有没有讲员、讲员有没有肖像，
都是真实数据，所以每一处都选定 HOST_PORTRAIT / HOST_VOICEOVER / HOST_NONE 中的一种，规则文字只写这一种：
  * 故事表演：有讲员 → 每一场都由讲员讲解（有肖像出镜，没有肖像只是画外音）；没有讲员 → 整个节目没人说话。
  * 播客：讲员（主持）+ 嘉宾（人物）讨论这个故事，不演故事；与故事对话不同。
  * 短故事 / 故事对话：共用同一份说话 / 表演规则（人物互相对话）；故事对话里如果有讲员，只多一句讲员的说明。
文字里不能出现花括号（预览的提示词会被 format）。本文件不 import 任何别的本项目模块（config ↔ utility 不能循环）。
"""

from __future__ import annotations

import re

# 顺序 = 预览窗口下拉的顺序（短故事在最前，因为它是新项目的默认）。
MODES = (
    ("step_story", "短故事"),
    ("podcast", "播客"),
    ("story_speak", "故事对话"),
    ("story_act", "故事表演"),
)
MODE_KEYS = tuple(k for k, _l in MODES)
MODE_LABELS = tuple(l for _k, l in MODES)
LABEL_OF = dict(MODES)

# 没存过 / 认不出时用哪一个（和以前一致，不改已有项目的行为）。
DEFAULT_MODE = "podcast"

# 叙事方式对应提示词里的叙事形式（narrative）。
NARRATIVE = {
    "step_story": "story",
    "podcast": "narration",
    "story_speak": "story",
    "story_act": "story",
    "tech": "tech",
    "exec": "exec",
}

# 旧的「生场视频」叙事风格存值（video_prompt.narrative）→ 方式（迁移用）。tech / exec 以前并进主持人节目，现在读作故事表演。
LEGACY_NARRATIVE_TO_MODE = {"narration": "podcast", "story": "story_speak", "tech": "story_act", "exec": "story_act"}

# 旧文字 → key（旧 Series · X 标签、Story Only / Story Speak / Story Act、Step Story / Short Story / N Step Story；
# 主持人节目 / Counselor / 技术方案汇报 / 高管简报 → 故事表演）
_LEGACY_TEXT_TO_MODE = {
    "tech": "story_act", "exec": "story_act", "技术方案汇报": "story_act", "高管简报": "story_act",
    "主持人节目": "story_act", "主持人節目": "story_act", "counselor": "story_act",
    "短故事": "step_story", "step story": "step_story", "short story": "step_story",
}

# 讲员的情况（由真实数据决定，没有「不知道」）：
HOST_PORTRAIT = "portrait"      # 有讲员，而且有肖像
HOST_VOICEOVER = "voiceover"    # 有讲员，没有肖像 → 只是画外音，不出镜、不对口型
HOST_NONE = "none"              # 没有讲员
HOST_CASES = (HOST_PORTRAIT, HOST_VOICEOVER, HOST_NONE)

SELF_TALK_RULE = (
    "自言自语 (self-talk) marked <Ns> is that same 人物 talking to themselves (s is only a flag, never a new speaker "
    "and never a narrator): their own voice with the mouth closed and no lip-sync, only at the start or the end of a "
    "scene; the tag itself is never read aloud."
)

# ---- 短故事 / 故事对话：共用同一份规则（人物互相对话）。短故事没有讲员；故事对话有讲员时只多一句讲员的说明。----
_DIALOGUE_LABEL = "短故事 / 故事对话"
_DIALOGUE_SPEAKING = (
    _DIALOGUE_LABEL + " · SPEAKING: the 人物 (the story's characters) carry the story by talking to each other, said "
    "aloud in the scene like a film or TV drama; every line is spoken only by its labeled 人物, one voice at a time. "
    + SELF_TALK_RULE
)
_DIALOGUE_PERFORMANCE = (
    _DIALOGUE_LABEL + " · PERFORMANCE: the 人物 act while they speak: movement, faces, and reactions fit and strengthen "
    "the words; lip-sync only the person whose interactive line it is, the others listen or react."
)
_DIALOGUE_HOST = {
    HOST_PORTRAIT: (
        "Cast here: the 讲员 has a portrait (肖像). The 讲员 is only a short narrator on screen (introduction, "
        "transition, closing) and never takes over a story scene.",
        "The 讲员 is on camera only when narrating and does not act the story out.",
    ),
    HOST_VOICEOVER: (
        "Cast here: the 讲员 has no portrait (肖像). The 讲员 is only a short voice-over narrator (introduction, "
        "transition, closing): never shown on screen, no lip-sync, and never takes over a story scene.",
        "The 讲员 is never shown.",
    ),
    HOST_NONE: (
        "Cast here: there is no 讲员. Nobody narrates: no narrator, no host, no voice-over.",
        "Nobody is shown as a narrator or host.",
    ),
}

# ---- 播客：讲员（主持）+ 嘉宾（人物）讨论这个故事。不演故事，也不是故事对话。----
_PODCAST_SPEAKING = (
    "播客 · SPEAKING: a discussion between the 讲员 (the host) and the 嘉宾 (the guest: the 人物 in the cast). They talk "
    "ABOUT the story as a third party, back and forth (question, reply, a short example, a follow-up), each line only "
    "by its labeled speaker, one voice at a time. The host opens, asks, leads and sums up; the guest answers, tells "
    "what they know and adds. Neither is a character of the story and neither speaks as one: the people of the story "
    "never speak. At most three people speak in one scene."
)
_PODCAST_PERFORMANCE = (
    "播客 · PERFORMANCE: nobody performs the story. The speakers are shown talking about it, with the gestures, "
    "expressions and reactions of a real conversation (listening, nodding, leaning in). What they discuss may be "
    "illustrated by the place and the objects in the picture, but no one re-enacts it and no story character appears."
)
_PODCAST_CASES = {
    HOST_PORTRAIT: (
        "Cast here: the 讲员 has a portrait (肖像). The host and the guest are both on screen, each talking on camera, "
        "lip-synced only on their own lines.",
        "The 讲员 and the 嘉宾 are both in the picture.",
    ),
    HOST_VOICEOVER: (
        "Cast here: the 讲员 has no portrait (肖像). The host is a voice only: heard as voice-over, never shown on "
        "screen, no lip-sync. The guest is on screen, talking on camera, lip-synced only on their own lines.",
        "Only the 嘉宾 is in the picture; the 讲员 is not shown.",
    ),
    HOST_NONE: (
        "Cast here: there is no 讲员. The first 人物 is the host and the other 人物 are the guests, all on screen, "
        "lip-synced only on their own lines.",
        "The 人物 are in the picture: the first is the host, the others are guests.",
    ),
}

# ---- 故事表演：人物只演不说。有讲员 → 每一场都由讲员讲解；没有讲员 → 整个节目没人说话。----
_ACT_SPEAKING_COMMON = (
    "故事表演 · SPEAKING: the 人物 (the story's main characters, one or several) do not speak on camera: no dialogue, "
    "no lines, no mouth speaking motion, no lip-sync. Sound effects only, never music."
)
# (情况说明, 说话, 表演)
_ACT_CASES = {
    HOST_PORTRAIT: (
        "the 讲员 has a portrait (肖像)",
        "the 讲员 explains every scene: in each scene the 讲员 is shown on screen and speaks to the audience, "
        "explaining what the scene shows and what it means in the story, lip-synced on the 讲员's own lines only. "
        "The 讲员 never takes the 人物's place in the story, and the 人物 never answer.",
        "the 讲员 stands in every scene and explains it while the 人物 keep performing; the 讲员 does not act the "
        "story out and does not join the story.",
    ),
    HOST_VOICEOVER: (
        "the 讲员 has no portrait (肖像)",
        "the 讲员 explains every scene as a background voice-over: the same explanation heard from behind the "
        "picture, never shown on screen, no lip-sync. Nobody on screen speaks.",
        "no 讲员 is on screen; the picture shows only the 人物 performing, silently.",
    ),
    HOST_NONE: (
        "there is no 讲员",
        "nobody speaks at all, in any scene: no narrator, no host, no voice-over. The 人物's performance and the "
        "sound effects carry the story.",
        "only the 人物 perform; there is no 讲员 anywhere.",
    ),
}
_ACT_PERFORMANCE_COMMON = (
    "故事表演 · PERFORMANCE: told like a silent film. The 人物 (the story's main characters, one or several) act the "
    "story out through action, behavior, facial expression, and gesture, exactly as ``story_content`` gives it (or as "
    "``visual`` and the actor's parentheses give it when a scene has no ``story_content``), so the picture itself "
    "tells it. They are actors, never guests, and never sit in a studio discussion. Sound effects only, never music."
)


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _act_speaking(host) -> str:
    case = _ACT_CASES[host]
    return _ACT_SPEAKING_COMMON + " Cast here: " + case[0] + ". " + _cap(case[1])


def _act_performance(host) -> str:
    case = _ACT_CASES[host]
    return _ACT_PERFORMANCE_COMMON + " Cast here: " + case[0] + ". " + _cap(case[2])


def _dialogue_speaking(host) -> str:
    return _DIALOGUE_SPEAKING + " " + _DIALOGUE_HOST[host][0]


def _dialogue_performance(host) -> str:
    return _DIALOGUE_PERFORMANCE + " " + _DIALOGUE_HOST[host][1]


def _podcast_speaking(host) -> str:
    return _PODCAST_SPEAKING + " " + _PODCAST_CASES[host][0]


def _podcast_performance(host) -> str:
    return _PODCAST_PERFORMANCE + " " + _PODCAST_CASES[host][1]


# 每个方式一行说明（给界面蓝字 / 备注用）。
_NOTES = {
    "step_story": "短故事：两个人物互相对话（和故事对话同一份说话 / 表演规则），没有讲员；固定场景数。",
    "podcast": "播客：讲员（主持）和嘉宾讨论这个故事，不演故事；和故事对话不同。",
    "story_speak": "故事对话：人物互相对话来讲故事；有讲员时讲员只做简短旁白。",
    "story_act": ("故事表演：人物只演不说、只有音效；有讲员 → 每一场都由讲员讲解"
                  "（有肖像出镜，没有肖像是画外音）；没有讲员 → 没人说话。"),
}


def normalize(value) -> str:
    """存值 / 标签（中文名；旧写法 "Series . Podcast"、Story Only、Step Story、tech / exec、Counselor、主持人节目 …）→ key；认不出返回空。

    旧的 tech / exec（技术方案汇报 / 高管简报）和 Counselor / 主持人节目 一律 → story_act（故事表演）。"""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower().replace("·", ".")
    if not text:
        return ""
    for key, label in MODES:
        if text in (key, label.lower()):
            return key
    if text in _LEGACY_TEXT_TO_MODE:
        return _LEGACY_TEXT_TO_MODE[text]
    if re.fullmatch(r"[1-9] ?step story", text):
        return "step_story"
    if "podcast" in text:
        return "podcast"
    if "counselor" in text or "主持人节目" in text or "主持人節目" in text:
        return "story_act"
    if "story act" in text or "story_act" in text:
        return "story_act"
    if "story only" in text or "story_only" in text or "story speak" in text or "story_speak" in text:
        return "story_speak"
    return ""


def label(value) -> str:
    key = normalize(value) or DEFAULT_MODE
    return LABEL_OF[key]


def host_case(has_host, has_portrait=False) -> str:
    """人物栏 / 场景 actor 里有没有讲员、讲员有没有肖像 → 三种情况之一。没有「不知道」：
    没有讲员 = none；有讲员有肖像 = portrait；有讲员没有肖像 = voiceover（画外音）。"""
    if not has_host:
        return HOST_NONE
    return HOST_PORTRAIT if has_portrait else HOST_VOICEOVER


def _host(value) -> str:
    return value if value in HOST_CASES else HOST_NONE


def speaking_rule(value, host=HOST_NONE) -> str:
    """这个方式「谁说话」的规则原文（场景生成、节目生成、视频生成三处都用这一份）。
    host = 讲员的情况（HOST_*）；没给 = 没有讲员。短故事没有讲员，永远按没有讲员写。"""
    key = normalize(value)
    if not key:
        return ""
    host = _host(host)
    if key == "step_story":
        return _dialogue_speaking(HOST_NONE)
    if key == "story_speak":
        return _dialogue_speaking(host)
    if key == "podcast":
        return _podcast_speaking(host)
    return _act_speaking(host)


def performance_rule(value, host=HOST_NONE) -> str:
    """这个方式「人物怎么演、画面怎么表现」的规则原文（三处都用这一份）。"""
    key = normalize(value)
    if not key:
        return ""
    host = _host(host)
    if key == "step_story":
        return _dialogue_performance(HOST_NONE)
    if key == "story_speak":
        return _dialogue_performance(host)
    if key == "podcast":
        return _podcast_performance(host)
    return _act_performance(host)


def note(value) -> str:
    key = normalize(value) or DEFAULT_MODE
    return _NOTES[key]


def scene_data_rule(value, host=HOST_NONE) -> str:
    """只在场景生成里用：讲员写进场景数据（actor / speaking / visual）的方式。没有讲员就没有这一条。"""
    key = normalize(value)
    host = _host(host)
    if not key or key == "step_story" or host == HOST_NONE:
        return ""
    shown = ("The 讲员 has a 肖像, so ``visual`` shows the 讲员 on screen." if host == HOST_PORTRAIT else
             "The 讲员 has no 肖像, so ``visual`` never shows the 讲员, and the video step plays the 讲员's lines as a voice-over.")
    where = "in every scene" if key == "story_act" else "in every scene where the 讲员 speaks"
    return ("Scene data: the 讲员 is listed first in ``actor`` (position 1) " + where
            + ", and the 讲员's lines are marked ``<1>``. " + shown)


def rules_block(value, host=HOST_NONE) -> str:
    """放进提示词的整段规则（标题 + 说话 + 表演 + 场景数据）。说话 / 表演两条全部来自 speaking_rule / performance_rule。"""
    key = normalize(value)
    if not key:
        return ""
    data = scene_data_rule(key, host)
    return (
        "*** NARRATION MODE RULES (the same rules the video window and the program window use for this mode)\n"
        "    ** " + speaking_rule(key, host) + "\n"
        "    ** " + performance_rule(key, host) + "\n"
        + ("    ** " + data + "\n" if data else "")
    )


RULES_BLOCK_HEAD = "*** NARRATION MODE RULES"


def with_rules_block(prompt: str, value, host=HOST_NONE) -> str:
    """把 rules_block 放进一份场景模板：放在「场景跟着来源」（SCENES FOLLOW THE SOURCE）之前；
    没有这一段就放在 EPISODES 之前；再没有就放在 INPUT 之前。已经有规则段就原样返回。
    放在 EPISODES 和 INPUT 之前，所以「共 N 集」的替换不会碰到它。"""
    block = rules_block(value, host)
    if not block or RULES_BLOCK_HEAD in prompt:
        return prompt
    for marker in ("\n*** SCENES FOLLOW THE SOURCE NAMED FOR THIS RUN", "\n*** EPISODES:",
                   "\n--------------------------------------------------\nINPUT\n"):
        if marker in prompt:
            return prompt.replace(marker, "\n" + block.rstrip("\n") + "\n" + marker, 1)
    return prompt


def new_project_default(selected_label, fallback: str = "") -> str:
    """预览窗口选的场景生成方式（下拉的名字）→ 新项目默认的叙事方式 key。认不出时用 fallback。"""
    return normalize(selected_label) or normalize(fallback)
