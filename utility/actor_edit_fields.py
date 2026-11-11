"""t400u: 人物预览窗里性别/年龄/民族/名字/括号描述的拆分与拼回（不依赖 Tk）。"""
from __future__ import annotations

import re

# 只收已知英文别名；「男女」「29-31歲」「東亞」这类不在清单里的值原样保留。
_GENDER_ALIASES = {
    "girl": "woman",
    "female": "woman",
    "boy": "man",
    "male": "man",
}

# 与 project_manager._ACTOR_AGE 一致；这里自备一份，避免测试桩改掉全局表。
_AGE_ALIASES = {
    "kids": "kids",
    "kid": "kids",
    "child": "kids",
    "children": "kids",
    "teenager": "teenager",
    "teen": "teenager",
    "youth": "youth",
    "young": "youth",
    "mature": "mature",
    "middle": "mature",
    "middle-aged": "mature",
    "adult": "mature",
    "senior": "senior",
    "elder": "senior",
    "old": "senior",
}

ACTOR_GENDERS = ("man", "woman")
ACTOR_AGES = ("kids", "teenager", "youth", "mature", "senior")
ACTOR_RACES = ("chinese", "english")


def split_actor_edit_body(body: str) -> tuple[str, str]:
    """拆出末尾括号，规则与 project_manager.split_actor_motion 相同。"""
    body = (body or "").strip()
    found = re.search(r"[（(]([^）)]*)[）)]\s*$", body)
    if not found:
        return body, ""
    return body[: found.start()].strip(), found.group(1).strip()


def actor_paren_is_motion(text: str) -> bool:
    """进出方式（含「画面/畫面」）不是形象描述。与 config_prompt.actor_scene_note 一致。"""
    t = (text or "").strip()
    return bool(t) and ("画面" in t or "畫面" in t)


def clean_actor_note(note: str) -> str:
    """描述里去掉括号，压成一行。"""
    t = re.sub(r"[（）()]", " ", note or "")
    t = " ".join(t.split()).strip(" ，,。")
    return t


def parse_actor_edit_fields(body: str) -> dict:
    """把人物字符串拆成 gender/age/race/name/note。

    不在下拉清单里的值原样保留，不改成 woman/mature/chinese。
    末尾括号：进出方式不算描述，形象描述放进 note。
    已知英文别名（female、teen、adult 等）收到标准值。
    """
    raw = (body or "").strip()
    base, paren = split_actor_edit_body(raw)
    note = "" if actor_paren_is_motion(paren) else paren
    bits = [x.strip() for x in base.split("/") if x.strip()]
    gender = bits[0] if bits else ""
    low = gender.lower()
    if low in ACTOR_GENDERS:
        gender = low
    else:
        gender = _GENDER_ALIASES.get(low, gender)

    age = bits[1] if len(bits) > 1 else ""
    if age:
        mapped = _AGE_ALIASES.get(age.lower(), "")
        age = mapped if mapped else age

    race = bits[2] if len(bits) > 2 else ""
    if race and race.lower() in ACTOR_RACES:
        race = race.lower()

    name = "/".join(bits[3:]) if len(bits) > 3 else ""
    return {
        "gender": gender,
        "age": age,
        "race": race,
        "name": name,
        "note": note,
    }


def format_actor_edit_fields(
    gender: str = "",
    age: str = "",
    race: str = "",
    name: str = "",
    note: str = "",
) -> str:
    """拼回 性别/年龄/民族[/名字][（描述）]。空段不加。"""
    parts = []
    for token in (gender, age, race):
        t = (token or "").strip().replace("/", "")
        if t:
            parts.append(t)
    nm = (name or "").strip().replace("/", "")
    body = "/".join(parts)
    if nm:
        body = f"{body}/{nm}" if body else nm
    cleaned = clean_actor_note(note)
    if cleaned and body:
        return f"{body}（{cleaned}）"
    return body


def actor_edit_combo_values(preset, current: str) -> tuple:
    """当前值不在清单里时加到最前面，让下拉能显示、也能改。"""
    values = tuple(preset or ())
    cur = (current or "").strip()
    if cur and cur not in values:
        return (cur,) + values
    return values
