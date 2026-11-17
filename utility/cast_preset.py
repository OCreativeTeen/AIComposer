"""t447u: 「人物设置」——按场景生成方式 + 分析报告，让 Strata 预设人物名单；再按一次换一组关系。

名单格式和人物栏一样（t280 新写法）：``H <讲员形象> | woman/mature/chinese/林芳（妻子） | …``。
  * 播客：讲员（主持）+ 1 位嘉宾（人物），两人围着故事谈、不演故事。
  * 故事对话 / 故事表演：讲员 + 2 到 3 个人物。（t262: 主持人节目已并入故事表演，旧存值读作故事表演。）
  * t266: 短故事已并入故事对话（步数 1–6 = 固定场景数），人物名单规则和故事对话一样；旧存值读作故事对话。
用过的名单记在这一条的 ``cast_history``（新的在前），再按一次时告诉 Strata 换一组不同的关系。
场景生成前用 ``validate_cast_for_mode`` 检查人数。
"""

from __future__ import annotations

import re

CAST_HISTORY_KEY = "cast_history"
CAST_HISTORY_MAX = 8

# mode → (要不要讲员, 人物最少, 人物最多, 给 Strata 的说明)
MODE_RULES = {
    "podcast": (True, 1, 1, "Podcast (播客). The 讲员 is the host. Choose exactly ONE guest (嘉宾, the one 人物 in the list) who "
                            "DISCUSSES this material with the host: someone who lived it, a person close to it, or a fitting "
                            "expert. The host and the guest only talk about the story; they do not play its people."),
    "story_speak": (True, 2, 3, "Story dialogue (故事对话). The story people (人物) carry the story by talking to each other. "
                                "Choose 2 or 3 story people."),
    "story_act": (True, 2, 3, "Story performance (故事表演). The story people (人物) act the story without words. "
                              "Choose 2 or 3 story people."),
}

from utility import narration_modes as _narration_modes  # noqa: E402  # t258: 名字来自共用表

MODE_NAMES = dict(_narration_modes.MODES)

_GENDERS = ("woman", "man")
_AGES = ("kids", "youth", "teenager", "mature", "senior")
_ETHNICITIES = ("chinese", "english")
_PERSON_RE = re.compile(
    r"^(woman|man)/(kids|youth|teenager|mature|senior)/(chinese|english)/(.+)$", re.I
)
from utility import actor_format  # noqa: E402  # t280: actor 新写法（H / 不写 人物N：）

_LABEL_RE = actor_format.LABEL_RE


def _label_body(seg) -> tuple:
    """一段 → (label, body)：label 是 "讲员"（H / 讲员： / 主持人：）、"人物"（旧的 人物N：）或 ""（新写法的人物）。"""
    role, body = actor_format.split_label(seg)
    if role == "host":
        return "讲员", body
    return ("人物" if actor_format.LABEL_RE.match(str(seg or "").strip()) else ""), body


def mode_for_label(label: str) -> str:
    """场景生成下拉的 label（新旧名都认）→ podcast / story_speak / story_act；别的返回 ""。旧的主持人节目读作 story_act，旧的短故事 / Step Story 读作 story_speak。"""
    import config_channel

    key = config_channel.series_style_key(label)
    if key:
        return key
    if config_channel.is_step_story_label(label):
        return "story_speak"  # 别的频道（FlyLink）的固定步数 Step Story；t266: 短故事 = 故事对话
    return ""


def _segments(cast_text: str) -> list:
    raw = str(cast_text or "").replace("；", "|").replace(";", "|").replace("\n", "|")
    return [p.strip() for p in raw.split("|") if p.strip()]


def cast_counts(cast_text: str) -> tuple:
    """名单 → (有没有讲员, 人物个数)。「不出现」的不算。"""
    host = False
    people = 0
    for seg in _segments(cast_text):
        label, body = _label_body(seg)
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
    故事对话（步数 0 或 1–6 都一样）/ 故事表演至少 2 个人物（讲员可有可无）。"""
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
        "woman/mature/chinese/林芳（妻子）",
        "man/mature/chinese/陈强（丈夫）",
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
        label, s = _label_body(s)
        if label == "讲员":
            continue
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
        parts.append(actor_format.entry("host", narrator))
    for body in people or []:
        parts.append(actor_format.entry("person", body))
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

    t266: 方式有三种：播客 / 故事对话 / 故事表演（短故事已并入故事对话，旧的短故事 / Step Story 读作故事对话）；
    旧的主持人节目 / Counselor / tech / exec 都读作故事表演。谁说话、人物怎么演由 utility/narration_modes 的规则原文给，
    所以三种方式的叙事形式都是 story（字段用法一样，说话规则按方式）。
    主窗口不是这四种时，用这一条存的故事风格（没有就播客）。"""
    import config_channel
    import config_prompt

    label = config_channel.canonical_prompt_label(mode_label or "")
    key = config_channel.series_style_key(label)
    if not key and config_channel.is_step_story_label(label):
        key = "story_speak"  # FlyLink 的固定步数 Step Story（t266: 短故事 = 故事对话）
        shown = config_prompt.story_style_label(key)
    else:
        key = key or config_prompt.normalize_story_style(story_style) or config_prompt.DEFAULT_STORY_STYLE
        shown = label if config_channel.series_style_key(label) else config_prompt.story_style_label(key)
    return shown, key, "story"

# ---------------------------------------------------------------------------
# t272: 「动态生成人物」——场景生成时按出场顺序现加人物，自动进人物栏（t279: 最多 10 个人物，讲员不算；每一场还是最多 4 个人）
# ---------------------------------------------------------------------------
DYNAMIC_CAST_KEY = "dynamic_cast"
DYNAMIC_CAST_LABEL = "动态生成人物"
DYNAMIC_CAST_MAX_PEOPLE = 10  # t279: 人物栏最多 10 个人物（讲员另算）= project_manager.CAST_MAX_PEOPLE
_TAIL_RE = re.compile(r"\s*[（(][^（()）]*[）)]\s*$")


def dynamic_cast_enabled(video_detail) -> bool:
    """这一条（行）有没有勾「动态生成人物」。存在 video_detail 和它的 project_profile 里。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    value = vd.get(DYNAMIC_CAST_KEY)
    if value is None:
        prof = vd.get("project_profile")
        if isinstance(prof, dict):
            value = prof.get(DYNAMIC_CAST_KEY)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _strip_tail(body: str) -> tuple:
    """``woman/mature/chinese/名(动作)`` → (去掉括号的 id, 括号原文含括号或空)。"""
    text = (body or "").strip()
    m = _TAIL_RE.search(text)
    if not m:
        return text, ""
    return text[: m.start()].strip(), m.group(0).strip()


def person_name(body: str) -> str:
    """人物 id 里的名字（gender/age/ethnicity/名字 的最后一段），小写；没有名字返回 ""。"""
    base = _strip_tail(body)[0].replace("／", "/")
    parts = [p.strip() for p in base.split("/") if p.strip()]
    return parts[-1].lower() if len(parts) >= 4 else ""


def split_cast(cast_text) -> tuple:
    """名单文字 → (讲员 body 或 "", [人物 body 按次序])；「不出现」的不要，人物 body 不带括号里的关系 / 动作。"""
    host, people = "", []
    for seg in _segments(cast_text):
        label, body = _label_body(seg)
        if not body or body.startswith("不出现"):
            continue
        if label in ("讲员", "講員"):
            host = host or _strip_tail(body)[0]
        else:
            people.append(_strip_tail(body)[0])
    return host, people


def join_cast(host: str, people) -> str:
    parts = []
    if (host or "").strip():
        parts.append(actor_format.entry("host", host))
    for body in people or []:
        parts.append(actor_format.entry("person", body))
    return " | ".join(parts)


def merge_scene_people(cast_text, scene_actor: str, *, mode: str = "", cap: int = DYNAMIC_CAST_MAX_PEOPLE,
                       allow_host: bool = False) -> tuple:
    """一场的 actor 里的人并进名单。返回 (新名单, 改好的 actor, 提醒列表)。

    * 名单里已有的人（按名字认）：actor 里写成名单里的 id（名字不变、性别 / 年龄段 / 民族跟名单一致），这一场的括号表现保留。
    * 名单里没有、名字有效的新人：名单没满（人物 < cap）就加到名单最后；满了就不加，只给提醒（这个人只留在这一场里）。
    * 讲员：名单没有讲员且 allow_host（播客）时才把这一场的讲员加进名单；别的方式不加。
    """
    host, people = split_cast(cast_text)
    names = {person_name(p): i for i, p in enumerate(people) if person_name(p)}
    notes = []
    out = []
    for seg in _segments(scene_actor):
        label, body = _label_body(seg)
        if not body or body.startswith("不出现") or body.strip() == "背景":
            out.append(actor_format.migrate(seg))
            continue
        base, tail = _strip_tail(body)
        if label in ("讲员", "講員"):
            if not host and allow_host and base:
                host = base
            out.append(actor_format.migrate(seg) if not host else f"H {host}{tail}")
            continue
        name = person_name(base)
        if name and name in names:
            canon = people[names[name]]
            out.append(f"{canon}{tail}")
            continue
        if not name:
            notes.append(f"人物没有名字，没加进人物栏：{base}")
            out.append(actor_format.migrate(seg))
            continue
        if len(people) >= max(0, int(cap)):
            notes.append(f"人物已满 {cap} 个，{base} 只留在这一场，没加进人物栏")
            out.append(actor_format.migrate(seg))
            continue
        base = base.replace("／", "/")
        people.append(base)
        names[name] = len(people) - 1
        notes.append(f"新人物：{base}")
        out.append(f"{base}{tail}")
    return join_cast(host, people), " | ".join(out), notes


FRESH_CAST_KEY = "_dynamic_cast_fresh"  # t276: 只在生成用的副本上：原来的人物栏（含讲员）这次完全不用


def fresh_cast_view(video_detail) -> dict:
    """t276: 勾了「动态生成人物」时场景生成用的副本：人物栏（含讲员）清空、讲员名去掉，打上 FRESH 标记。
    不改原来那一条；原来的人物一个也不发给模型，人物全部由模型从内容（PDF 页 / 文字）里找。"""
    vd = dict(video_detail) if isinstance(video_detail, dict) else {}
    vd["story_actors"] = ""
    vd.pop("narrator", None)
    prof = vd.get("project_profile")
    if isinstance(prof, dict):
        prof = dict(prof)
        prof["story_actors"] = ""
        prof.pop("narrator", None)
        vd["project_profile"] = prof
    vd[FRESH_CAST_KEY] = True
    return vd


def is_fresh_view(video_detail) -> bool:
    return bool(isinstance(video_detail, dict) and video_detail.get(FRESH_CAST_KEY))


FRESH_CAST_RULES = (
    # t278: 每一场自己找人（不带前面场景的人），每个人四段都要写全；全部生成完再归拢成一份名单。
    "    ** IGNORE ANY EARLIER CAST, AND FIND THE PEOPLE OF EACH SCENE ON ITS OWN: nobody is fixed in advance. For every "
    "scene, look only at that scene's own picture and words and list exactly the people it shows or who speak in it. "
    "Do not carry people over from other scenes or pages, and do not add someone only because they were in an earlier "
    "scene.",
    "    ** Every person in ``actor`` is written in full, every time: ``gender/age band/ethnicity/name``. gender is "
    "man or woman; age band is kids, teenager, youth, mature or senior; ethnicity is chinese or english; then the name. "
    "All four parts are required for every person in every scene: never leave one out, never write a number for the age. "
    "No label in front (never 人物N： or 人物：); a 讲员 is written ``H gender/age band/ethnicity/name``.",
    "    ** Name each person by their real name in this story, exactly as the material gives it. When the material gives "
    "no personal name, a descriptive name is fine (某某的女儿, 甘氏之女, 门子). Never use a placeholder (人物1, 某人, "
    "男子, the man, A) and never reuse a name from an earlier cast list, an example, or another story.",
    "    ** Gender and age band follow who the person is in this story: a little daughter is woman/kids, a young "
    "servant boy is man/teenager, an old grandmother is woman/senior.",
    "    ** One person per entry. After the id only an optional short note about this scene in full-width parentheses "
    "(（手持古籍）). No reasoning, no explanations and no sentences in ``actor``.",
)


def dynamic_cast_block(cast_text, mode: str = "", cap: int = DYNAMIC_CAST_MAX_PEOPLE, fresh: bool = False) -> str:
    """提示词里的「动态生成人物」段：名单可以不全 / 是空的，可以按出场加新人物，id 前后一致，人物最多 cap 个（讲员不算）。
    t276: ``fresh`` = 原来的人物栏完全不用：再加「人物全部从内容里找、用故事里的真名、不用占位名 / 以前的名字」。
    （名单里要是有人，只能是这次生成前面几页找出来的人。）"""
    host, people = split_cast(cast_text)
    left = max(0, int(cap) - len(people))
    lines = [
        "*** DYNAMIC CAST (the user allows new people; this overrides every other line, before or after it, that says the "
        "cast is fixed or complete, or that says not to add anyone or not to invent a 讲员)",
    ]
    if fresh:
        # t278: 不再有累计名单（每场自己找人），全部场景生成完统一归拢（utility.cast_consolidate）
        lines.extend(FRESH_CAST_RULES)
        lines += [
            "    ** At most four people in one scene's ``actor``, as the scene rules say. After all scenes are written, "
            f"the people of all scenes are merged into one cast of at most {int(cap)} people (人物)"
            + (" plus one 讲员" if mode == "podcast" else "")
            + "; the same person written a little differently in two scenes is fixed then, so just be exact in each scene.",
            "    ** A scene may have nobody in it (an empty ``actor`` and no <N> lines): that is allowed.",
        ]
        if mode == "podcast":
            lines.append("    ** This mode needs a 讲员 (host): in the scenes where the host appears, write them as "
                         "``H gender/age band/ethnicity/name``, all four parts.")
        else:
            lines.append("    ** Do not invent a 讲员 unless the mode rules above ask for one.")
        return "\n".join(lines)
    lines += [
        "    ** The cast list may be empty or too small for this mode. When a person who is in the picture or the words "
        "and is not in the list appears, introduce them yourself in ``actor`` as ``gender/age band/ethnicity/name`` "
        "(full look id: man or woman; kids, youth, teenager, mature or senior; chinese or english; a real name taken "
        "from the picture or the words). Do not use a nameless id.",
        "    ** Keep it consistent: a person already in the list is always written with exactly the same id "
        "(same name, gender, age band, ethnicity). A person you introduce keeps that same id every time they come back. "
        "Never rename a person and never write one person under two names.",
        f"    ** At most {int(cap)} people (人物) in the whole program; the 讲员 is not counted. "
        + (f"{len(people)} are already listed, so you may add at most {left} more."
           if people else f"None is listed yet, so you may add up to {int(cap)}.")
        + (" The list is full: add nobody; use only the listed people." if left == 0 else ""),
        "    ** Add a person only when they really take part (they speak, or the scene shows them acting). "
        "A scene may have nobody in it (an empty ``actor`` and no <N> lines): that is allowed.",
    ]
    if mode == "podcast" and not host:
        lines.append("    ** This mode needs a 讲员 (host) and the list has none: you may introduce one as "
                     "``H gender/age band/ethnicity/name``. Do it once; keep the same id afterwards.")
    else:
        lines.append("    ** Do not invent a 讲员 unless the mode rules above ask for one and the list has none.")
    return "\n".join(lines)
