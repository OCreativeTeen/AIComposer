"""t447u: 「人物设置」——按场景生成方式 + 分析报告，让 Strata 预设人物名单；再按一次换一组关系。

名单格式和人物栏一样：``讲员：<讲员形象> | 人物1：woman/mature/chinese/林芳（妻子） | 人物2：…``。
  * 播客：讲员（主持）+ 1 位嘉宾（人物），两人围着故事谈、不演故事。
  * 故事对话 / 故事表演：讲员 + 2 到 3 个人物。（t262: 主持人节目已并入故事表演，旧存值读作故事表演。）
  * 短故事：2 个人物，没有讲员。
用过的名单记在这一条的 ``cast_history``（新的在前），再按一次时告诉 Strata 换一组不同的关系。
场景生成前用 ``validate_cast_for_mode`` 检查人数。
"""

from __future__ import annotations

import re

CAST_HISTORY_KEY = "cast_history"
CAST_HISTORY_MAX = 8

# mode → (要不要讲员, 人物最少, 人物最多, 给 Strata 的说明)
MODE_RULES = {
    "podcast": (True, 1, 1, "Podcast (播客). The 讲员 is the host. Choose exactly ONE guest (嘉宾, written as 人物1) who "
                            "DISCUSSES this material with the host: someone who lived it, a person close to it, or a fitting "
                            "expert. The host and the guest only talk about the story; they do not play its people."),
    "story_speak": (True, 2, 3, "Story dialogue (故事对话). The story people (人物) carry the story by talking to each other. "
                                "Choose 2 or 3 story people."),
    "story_act": (True, 2, 3, "Story performance (故事表演). The story people (人物) act the story without words. "
                              "Choose 2 or 3 story people."),
    "step_story": (False, 2, 2, "Short story (短故事). Exactly 2 story people (人物) who talk to each other. No narrator."),
}

from utility import narration_modes as _narration_modes  # noqa: E402  # t258: 名字来自共用表

MODE_NAMES = dict(_narration_modes.MODES)

_GENDERS = ("woman", "man")
_AGES = ("kids", "youth", "teenager", "mature", "senior")
_ETHNICITIES = ("chinese", "english")
_PERSON_RE = re.compile(
    r"^(woman|man)/(kids|youth|teenager|mature|senior)/(chinese|english)/(.+)$", re.I
)
_LABEL_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:\d+[.、)]\s*)?(讲员|講員|人物\s*\d*)\s*[：:]\s*")


def mode_for_label(label: str) -> str:
    """场景生成下拉的 label（新旧名都认）→ podcast / story_speak / story_act / step_story；别的返回 ""。旧的主持人节目读作 story_act。"""
    import config_channel

    key = config_channel.series_style_key(label)
    if key:
        return key
    if config_channel.is_step_story_label(label):
        return "step_story"
    return ""


def _segments(cast_text: str) -> list:
    raw = str(cast_text or "").replace("；", "|").replace(";", "|").replace("\n", "|")
    return [p.strip() for p in raw.split("|") if p.strip()]


def cast_counts(cast_text: str) -> tuple:
    """名单 → (有没有讲员, 人物个数)。「不出现」的不算。"""
    host = False
    people = 0
    for seg in _segments(cast_text):
        m = _LABEL_RE.match(seg)
        label = (m.group(1) if m else "").replace(" ", "")
        body = seg[m.end():].strip() if m else seg
        if not body or body.startswith("不出现"):
            continue
        if label in ("讲员", "講員"):
            host = True
        else:
            people += 1
    return host, people


CAST_BUTTON = "「人物设置」"


def validate_cast_for_mode(mode: str, cast_text) -> tuple:
    """场景生成前检查人物栏。返回 (ok, 说明)。t263: 场景生成必须先有人物（没有人物不生成）：
    人物栏是空的 → 请先按「人物设置」生成讲员和人物；播客要有讲员（主持）加至少 1 位嘉宾（人物）；
    故事对话 / 故事表演 / 短故事至少 2 个人物（讲员可有可无，短故事没有讲员）。"""
    host, people = cast_counts(cast_text or "")
    name = MODE_NAMES.get(mode, mode)
    if mode not in MODE_RULES:
        return True, ""
    if not host and people == 0:
        return False, (f"{name}需要人物：人物栏现在是空的。请先按{CAST_BUTTON}生成"
                       + ("讲员和人物" if MODE_RULES[mode][0] else "人物")
                       + "（也可以在人物栏里手动添加），再生成场景。")
    if mode == "podcast":
        if not host:
            return False, (f"{name}需要讲员（主持人）和至少 1 位嘉宾（人物）：人物栏里没有讲员。"
                           f"请先在人物栏里选一个讲员，再按{CAST_BUTTON}生成嘉宾。")
        if people < 1:
            return False, f"{name}需要至少 1 位嘉宾（人物），现在有 0 位。请先按{CAST_BUTTON}生成，或在人物栏里添加。"
    elif people < 2:
        return False, f"{name}至少要 2 个人物（讲员不算），现在有 {people} 个。请先按{CAST_BUTTON}或在人物栏里添加。"
    return True, ""


def cast_history(video_detail) -> list:
    vd = video_detail if isinstance(video_detail, dict) else {}
    hist = vd.get(CAST_HISTORY_KEY)
    if not isinstance(hist, list):
        return []
    return [str(h).strip() for h in hist if str(h or "").strip()][:CAST_HISTORY_MAX]


def remember_cast(video_detail, people: list) -> list:
    """把这次的人物（不含讲员）记进 cast_history，新的在前。返回新的 history。"""
    sig = " | ".join(str(p).strip() for p in people or [] if str(p).strip())
    if not isinstance(video_detail, dict) or not sig:
        return cast_history(video_detail)
    hist = [h for h in cast_history(video_detail) if h != sig]
    hist.insert(0, sig)
    video_detail[CAST_HISTORY_KEY] = hist[:CAST_HISTORY_MAX]
    return video_detail[CAST_HISTORY_KEY]


def build_cast_prompt(mode: str, analysis: str, *, history=None, current: str = "") -> tuple:
    """返回 (system, user)。"""
    need_host, lo, hi, desc = MODE_RULES[mode]
    count = f"exactly {lo}" if lo == hi else f"{lo} to {hi}"
    system = "\n".join([
        "You cast the people for a short video program. Read the material and decide who should appear.",
        "*** MODE: " + desc,
        f"*** Return {count} story people (人物). " + (
            "Do NOT list the 讲员 (host/narrator); it is set separately." if need_host else "There is no 讲员."),
        "*** Output ONLY lines in this exact format, nothing else:",
        "人物1：woman/mature/chinese/林芳（妻子）",
        "人物2：man/mature/chinese/陈强（丈夫）",
        "    * gender: woman or man. age band: kids, youth, teenager, mature, or senior. ethnicity: chinese or english.",
        "    * Then a name that fits the person and the material (Chinese name for chinese, English name for english).",
        "    * In the full-width parentheses: this person's role or relationship to the others, 2 to 6 characters "
        "(妻子, 丈夫, 女儿, 父亲, 同事, 嘉宾·心理咨询师 …).",
        "    * The relationships must fit the material: who these people are to each other in this story.",
        "    * Age band and gender must match the role (a daughter in primary school is woman/kids, a grandfather is man/senior).",
    ])
    hist = [h for h in (history or []) if str(h).strip()]
    user_parts = []
    if hist:
        user_parts.append(
            "These casts were already used. Choose a DIFFERENT set of relationships this time "
            "(different roles, not only different names):\n" + "\n".join(f"- {h}" for h in hist)
        )
    if (current or "").strip():
        user_parts.append("Current cast (replace it): " + current.strip())
    user_parts.append("Material (analysis report):\n" + (analysis or "").strip()[:12000])
    return system, "\n\n".join(user_parts)


def parse_cast_reply(text: str, mode: str) -> list:
    """Strata 回的文字 → 人物 body 列表（``woman/mature/chinese/林芳（妻子）``），最多按 mode 的上限截断。"""
    _need_host, _lo, hi, _desc = MODE_RULES[mode]
    out = []
    for line in str(text or "").replace("|", "\n").splitlines():
        s = line.strip().strip("`").strip()
        if not s:
            continue
        m = _LABEL_RE.match(s)
        if m:
            if m.group(1) in ("讲员", "講員"):
                continue
            s = s[m.end():].strip()
        s = s.replace("／", "/").replace(" / ", "/")
        s = s.replace("(", "（").replace(")", "）")
        pm = _PERSON_RE.match(s)
        if not pm:
            continue
        g, a, e, rest = pm.group(1).lower(), pm.group(2).lower(), pm.group(3).lower(), pm.group(4).strip()
        if not rest:
            continue
        body = f"{g}/{a}/{e}/{rest}"
        if body not in out:
            out.append(body)
        if len(out) >= hi:
            break
    return out


def compose_cast_text(mode: str, narrator: str, people: list) -> str:
    need_host = MODE_RULES[mode][0]
    parts = []
    if need_host and (narrator or "").strip():
        parts.append(f"讲员：{narrator.strip()}")
    for i, body in enumerate(people or [], 1):
        parts.append(f"人物{i}：{body}")
    return " | ".join(parts)


def _default_generate(system: str, user: str) -> str:
    from utility import llm_api

    return llm_api.LLMApi(llm_api.STRATA).generate_text(system, user)


def preset_cast(mode: str, analysis: str, *, narrator: str = "", history=None, current: str = "",
                generate=None, tries: int = 2) -> tuple:
    """问 Strata 要一组人物。返回 (名单文字, 人物列表)；拿不到够数的人物抛 ValueError。

    ``generate(system, user) -> str`` 可以传 mock（测试用）；默认用本机 Strata。"""
    if mode not in MODE_RULES:
        raise ValueError("这个场景生成方式不用设置人物")
    lo = MODE_RULES[mode][1]
    gen = generate or _default_generate
    system, user = build_cast_prompt(mode, analysis, history=history, current=current)
    last = ""
    for _ in range(max(1, int(tries))):
        last = gen(system, user) or ""
        people = parse_cast_reply(last, mode)
        if len(people) >= lo and (people or lo == 0):
            return compose_cast_text(mode, narrator, people), people
    if lo == 0:
        return compose_cast_text(mode, narrator, []), []
    raise ValueError("Strata 没给出合格的人物名单：" + (last.strip()[:200] or "（空）"))


def program_mode_narrative(mode_label: str, story_style=None) -> tuple:
    """t448u: 节目生成跟主窗口选的场景生成方式走 → (显示名, 故事风格 key, 叙事方式)。

    t262: 方式有四种：短故事 / 播客 / 故事对话 / 故事表演，短故事是自己的一种（key = step_story），不再当故事对话；
    旧的主持人节目 / Counselor / tech / exec 都读作故事表演。谁说话、人物怎么演由 utility/narration_modes 的规则原文给，
    所以四种方式的叙事形式都是 story（字段用法一样，说话规则按方式）。
    主窗口不是这四种时，用这一条存的故事风格（没有就播客）。"""
    import config_channel
    import config_prompt

    label = config_channel.canonical_prompt_label(mode_label or "")
    key = config_channel.series_style_key(label)
    if not key and config_channel.is_step_story_label(label):
        key = "step_story"
        shown = config_channel.STEP_STORY_LABEL
    else:
        key = key or config_prompt.normalize_story_style(story_style) or config_prompt.DEFAULT_STORY_STYLE
        shown = label if config_channel.series_style_key(label) else config_prompt.story_style_label(key)
    return shown, key, "story"


