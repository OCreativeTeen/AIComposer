"""t426u: 档位提示词的校验（返回 "" = 通过，否则是原因）。"""
from __future__ import annotations

import re

_CJK = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]")
# 无讲话档里不许出现的讲话 / 声音 / 上字类词（声音字段那一句固定文字除外）
_SPEECH = re.compile(
    r"\b(speak\w*|speech\w*|spoken|voice\w*|dialog\w*|narrat\w*|sing|sings|singing|singer\w*|song\w*|lip|lips|"
    r"lip-?sync\w*|talk\w*|say|says|saying|said|whisper\w*|mouth\w*|lyric\w*|subtitle\w*|caption\w*|monologue\w*|"
    r"verbatim|transcript\w*)\b", re.I)
FIELDS = ("subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:",
          "non_diegetic_music:")


# t429u: 没勾人物时，模板以外不许出现的「新角色」词：人物 / 亲属称呼 / 动物 / 生物（声音字段那句固定文字除外）
_BEINGS = re.compile(
    r"\b(wife|husband|brother|sister|mother|father|mom|dad|son|daughter|child|children|kid|kids|baby|boy|girl|"
    r"man|men|woman|women|lady|gentleman|friend|lover|grandma|grandpa|grandmother|grandfather|uncle|aunt|cousin|"
    r"neighbou?r|stranger|crowd|villager\w*|merchant\w*|soldier\w*|priest\w*|king|queen|protagonist|hero|"
    r"he|she|him|her|his|hers|"
    r"animal\w*|pet|pets|cat|cats|kitten\w*|dog|dogs|pupp\w*|bird|birds|horse\w*|sheep|goat\w*|cow\w*|"
    r"rabbit\w*|mouse|mice|fish|fishes|creature\w*|monster\w*|mascot\w*|dragon\w*|insect\w*|butterfl\w*)\b",
    re.I)
# 原文（中文）里本来就写了的，译文里可以有
_BEING_ZH = {"cat": "猫", "cats": "猫", "kitten": "猫", "dog": "狗", "dogs": "狗", "bird": "鸟", "birds": "鸟",
             "horse": "马", "fish": "鱼", "sheep": "羊", "goat": "羊", "cow": "牛", "rabbit": "兔",
             "butterfly": "蝶", "animal": "动物", "animals": "动物"}


def being_word(text: str, original: str = "") -> str:
    """t429u: 译文 / 提示词里新出现的人物或动物词（原文里写了对应的中文就不算）。"""
    for m in _BEINGS.finditer(text or ""):
        w = m.group(0).lower()
        zh = _BEING_ZH.get(w)
        if zh and zh in (original or ""):
            continue
        return m.group(0)
    return ""


_ANIMALS = re.compile(
    r"\b(animal\w*|pet|pets|cat|cats|kitten\w*|dog|dogs|pupp\w*|bird|birds|horse\w*|sheep|goat\w*|cow\w*|"
    r"rabbit\w*|mouse|mice|fish|fishes|creature\w*|monster\w*|mascot\w*|dragon\w*|insect\w*|butterfl\w*)\b", re.I)


def animal_word(text: str, original: str = "") -> str:
    """t429u: 只查动物 / 生物（场景描述里写人是正常的）。"""
    for m in _ANIMALS.finditer(text or ""):
        zh = _BEING_ZH.get(m.group(0).lower())
        if zh and zh in (original or ""):
            continue
        return m.group(0)
    return ""


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text or ""))


def speech_word(text: str) -> str:
    m = _SPEECH.search(text or "")
    return m.group(0) if m else ""


def field(prompt: str, name: str) -> str:
    """字段内容（到下一个字段为止）。"""
    text = prompt or ""
    i = text.find(name)
    if i < 0:
        return ""
    start = i + len(name)
    ends = [text.find(f, start) for f in FIELDS]
    ends = [e for e in ends if e >= 0]
    return text[start:min(ends) if ends else len(text)].strip()


def required_prefixes(ctx) -> list:
    import config_prompt as cp
    from prompt_profiles.select import M0_FAITHFUL

    out = [cp.ART_STYLE_LOCK_PREFIX, cp.VIDEO_ONE_SHOT_PREFIX, cp.VIDEO_PROPS_LOCK_PREFIX]
    if ctx.profile == M0_FAITHFUL:
        out.append(cp.VIDEO_FAITHFUL_PREFIX)
    if not ctx.use_actor:
        out.append(cp.VIDEO_NO_NEW_PEOPLE_PREFIX)
    if ctx.text in cp.IMAGE_TEXT_KEEP_CHOICES:
        out.append(cp.VIDEO_IMAGE_KEYWORDS_PREFIX)
    return out


def validate_h3(prompt: str, ctx, *, allow_raw=(), fyi_text: str = "", visual_text: str = "") -> str:
    """allow_raw = 没译成英文、原样放进画面描述的几段（只有它们里面可以有中文 / 别的字）。
    fyi_text = 放进去的 FYI（必须只在 detailed_description 里）。"""
    from prompt_profiles import blocks

    text = prompt or ""
    if not text.startswith(FIELDS[0]):
        return "第一行不是 subject_definitions:"
    for f in FIELDS:
        if text.count(f) != 1:
            return f"字段 {f} 应恰好一个"
    if field(text, "overall_soundscape:") != blocks.SOUNDSCAPE:
        return "声音字段不是固定的环境声"
    if field(text, "non_diegetic_music:") != blocks.MUSIC:
        return "音乐字段不是固定的无音乐"
    for p in required_prefixes(ctx):
        if text.count(p) != 1:
            return f"锁定句「{p}」应恰好一句"
    body = text.replace(blocks.SOUNDSCAPE, " ")
    for seg in allow_raw:
        if seg:
            body = body.replace(seg, " ")
    if has_cjk(body):
        return "有中文（只允许没译成英文的那几段）"
    w = speech_word(body)
    if w:
        return f"有讲话 / 声音类的词（{w}）"
    if not ctx.use_actor:  # t429u: 没勾人物：锁定句以外不许出现人物 / 动物词
        from prompt_profiles import blocks as _b

        content = body.replace(visual_text, " ") if visual_text else body
        for fixed in (_b.no_new_people(), _b.one_base_shot(), _b.art_style_lock(ctx.style), _b.objects_lock(),
                      _b.faithful(), _b.STORY_THROUGH_SCENE):
            content = content.replace(fixed, " ")
        w = being_word(content, " ".join(allow_raw))
        if w:
            return f"没勾人物却有人物 / 动物词（{w}）"
    if fyi_text:
        if fyi_text not in field(text, "detailed_description:"):
            return "FYI 不在画面描述里"
        for f in FIELDS:
            if f != "detailed_description:" and fyi_text in field(text, f):
                return f"FYI 出现在 {f}"
    return ""
