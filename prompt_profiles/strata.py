"""t426u: 档位自己的 Strata：只把几段中文资料（场景描述 / 讲话当故事内容 / FYI）译成英文画面方向，
提示词其余部分由模板生成（锁定句、声音字段不经 Strata，不会被改）。不通过校验就用没精简的档位提示词。"""
from __future__ import annotations

import json
import re
import time

from prompt_profiles.h3 import build_h3
from prompt_profiles.select import M0_FAITHFUL
from prompt_profiles.validate import has_cjk, speech_word, validate_h3

_SYS_BASE = """You turn short notes about ONE video clip into English visual directions for an image-to-video model.
The clip is one continuous shot that animates the start picture. Nobody in it uses their voice; only quiet ambient sound of the place is heard.
You get a JSON object whose values are notes (often Chinese). Return ONLY a JSON object with the same keys, each value one or two plain English sentences that describe what is SEEN: movement, gesture, expression, light, camera feel.
Rules:
- English only. No Chinese characters, no quotation marks, no names in brackets.
- Describe only visible things. Never mention words, voices, sound, music, text, letters, subtitles or captions.
- If a note is a line someone would say, describe instead the visible feeling behind it.
- Keep everything inside the place shown in the start picture.
- Do not start with "Throughout the clip"; that is added for you."""

_SYS_M0 = _SYS_BASE + """
- Profile: faithful animation. The only note is a direction for how the picture moves. Add no people, animals, places, eras or story beyond what the note says."""

_SYS_M1 = _SYS_BASE + """
- Profile: silent scene. "visual" is the scene description, "story" is the moment to act out with movement and expression, "fyi" is an extra direction for the motion."""

_SYS_NO_PEOPLE = """
- Keep every subject to what the start picture already shows. "visual" describes only what the picture already shows and adds no animal, pet or creature. In "story" and "fyi" write no person, family member, animal, pet or creature, no pronoun such as he or she, and no region, country, era or period.
- "story" (when given) becomes the mood or event of the moment, shown only through the camera, the light, the environment moving softly (light, shadow, air, cloth, leaves, smoke, water) and the picture's keywords, for example "warm lamplight slowly fills the quiet room while the shadows by the door grow long"."""


def system_prompt(ctx) -> str:
    base = _SYS_M0 if ctx.profile == M0_FAITHFUL else _SYS_M1
    if ctx.profile != M0_FAITHFUL and not ctx.use_actor:  # t429u: 没勾人物：故事不「演」，只成气氛
        base = base.replace('"story" is the moment to act out with movement and expression',
                            '"story" is the moment whose mood the scene shows')
    return base + (_SYS_NO_PEOPLE if not ctx.use_actor else "")


def _check_slots(ctx, en: dict) -> str:
    import config_prompt as cp

    want = ctx.slots()
    from prompt_profiles.validate import animal_word, being_word

    for key in want:
        val = (en.get(key) or "").strip()
        if not val:
            return f"Strata 没给「{key}」"
        if has_cjk(val):
            return f"「{key}」还有中文"
        w = speech_word(val)
        if w:
            return f"「{key}」有讲话 / 声音类的词（{w}）"
        if len(val) > 600:
            return f"「{key}」太长"
        if not ctx.use_actor:
            w = added_people_or_place(want[key], val)
            if w:
                return f"「{key}」加了人 / 地域时代（{w}）"
            # t429u: 妻子 / 弟弟 / 猫狗 这类新角色。场景描述写的是图里本来就有的东西：只查动物（原文写了的可以）
            w = being_word(val, want[key]) if key != "visual" else animal_word(val, want[key])
            if w:
                return f"「{key}」写了图里没有的人物 / 动物（{w}）"
    return ""


# 「两人」译成 two people 很正常，所以泛指的 people / person / figure 不算加人
_GENERIC_PEOPLE = {"people", "person", "persons", "figure", "figures"}


def added_people_or_place(original: str, english: str) -> str:
    """t426u: 没勾人物时，译文多了人（crowd / protagonist ……）或地域 / 时代的词就返回那个词。
    原文本来就写了地域 / 时代（中文词）时不查地域 / 时代。"""
    import config_prompt as cp

    low = " " + (english or "").lower() + " "
    for w in cp._PEOPLE_WORDS:
        if w.isascii() and w not in _GENERIC_PEOPLE and re.search(r"\b" + re.escape(w) + r"\b", low):
            return w
    orig = original or ""
    place_words = tuple(cp._PLACE_ERA_WORDS) + tuple(cp._setting_words())
    if any((not w.isascii()) and w in orig for w in place_words):
        return ""
    for w in place_words:
        if w and w.isascii() and re.search(r"\b" + re.escape(w.lower()) + r"\b", low):
            return w
    return ""


def _default_call(system: str, user: str, timeout_s: float) -> str:
    from utility import llm_api
    from utility.prompt_polish import _strata_client

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": system},
                                                {"role": "user", "content": user}])
    req["max_tokens"] = 1024
    resp = _strata_client(timeout_s).chat.completions.create(**req)
    return resp.choices[0].message.content if resp and resp.choices else ""


def refine_h3(ctx, call=None, timeout_s: float | None = None) -> tuple:
    """(最终提示词, 说明)。call(system, user, timeout_s) -> 文字（测试用假的）。
    没有要译的资料 → 直接用模板；Strata 失败 / 不通过 → 用没精简的档位提示词（原文放在画面描述里）。"""
    if timeout_s is None:
        from utility.prompt_polish import POLISH_TIMEOUT_S as timeout_s  # noqa: N811
    plain = build_h3(ctx)
    slots = ctx.slots()
    if not slots:
        return plain.prompt, "档位提示词，没有要翻译的资料"
    started = time.monotonic()
    try:
        text = (call or _default_call)(system_prompt(ctx), json.dumps(slots, ensure_ascii=False), timeout_s)
        m = re.search(r"\{.*\}", text or "", re.S)
        en = json.loads(m.group(0)) if m else {}
        if not isinstance(en, dict):
            en = {}
        en = {k: " ".join(str(v or "").split()).strip().rstrip(".") for k, v in en.items() if k in slots}
    except Exception as exc:  # noqa: BLE001
        why = f"Strata 翻译失败（{type(exc).__name__}: {str(exc)[:120]}），用没精简的档位提示词"
        print(f"[档位 Strata] {why}")
        return plain.prompt, why
    secs = time.monotonic() - started
    bad = _check_slots(ctx, en)
    if not bad:
        built = build_h3(ctx, en)
        bad = validate_h3(built.prompt, ctx, allow_raw=built.allow_raw, fyi_text=built.fyi_text,
                          visual_text=built.visual_text)
    if bad:
        why = f"{bad}，用没精简的档位提示词（{secs:.1f} 秒）"
        print(f"[档位 Strata] {why}")
        return plain.prompt, why
    why = f"Strata 已把 {'/'.join(slots)} 译成英文画面方向（{secs:.1f} 秒）"
    print(f"[档位 Strata] {why}")
    return built.prompt, why
