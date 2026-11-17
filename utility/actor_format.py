"""t280: 场景 ``actor``（和人物栏名单）的文字写法。

新写法（写出去只用这一种）：每个人一段，段和段之间用 `` | ``；位置就是第几个人（第 1 段 = 讲话里的 <1>）。
  * 人物：``gender/age band/ethnicity/name（这一场的说明）``，前面不写「人物N：」「人物：」。
  * 讲员：``H gender/age band/ethnicity/name（…）``（大写 H + 空格）。讲员说话也用它在 actor 里的位置 <N>，没有单独的标记。
  * 不出现的人：``不出现``。

旧写法（``人物N：``、``人物：``、``讲员：``、``講員：``、``主持人：``，还有叠起来的 ``人物2：讲员：``）读的时候照样认。
这个模块不依赖别的项目模块（工具模块和界面都能用）。
"""
from __future__ import annotations

import re

HOST_TAG = "H"
HOST_WORDS = ("讲员", "講員", "主持人")
ABSENT = "不出现"
# 一段开头的标签：旧的 人物N： / 人物： / 讲员： / 講員： / 主持人：，或新的 "H "；前面可以有列表符号 / 序号
LABEL_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:\d+[.、)]\s*)?(?:(讲员|講員|主持人|人物\s*\d*)\s*[：:]\s*|(H)\s+)")
SEP_RE = re.compile(r"\s*[|；;]\s*")


def segments(text) -> list:
    """actor 文字 → 每个人一段（去掉空段）。分隔符是 | ；; 和换行，括号里面的不算（括号说明里可以有分号）。"""
    out, buf, depth = [], [], 0
    for ch in str(text or ""):
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch in "|\n" or (ch in "；;" and depth == 0):
            out.append("".join(buf))
            buf = []
            if ch == "\n":
                depth = 0
            continue
        buf.append(ch)
    out.append("".join(buf))
    return [p.strip() for p in out if p.strip()]


def split_label(seg) -> tuple:
    """一段 → (role, body)。role 是 "host"（讲员）或 "person"。叠起来的标签都去掉。"""
    text = str(seg or "").strip()
    role = "person"
    while True:
        m = LABEL_RE.match(text)
        if not m:
            break
        word = (m.group(1) or "").replace(" ", "")
        if m.group(2) or word in HOST_WORDS:
            role = "host"
        text = text[m.end():].strip()
    return role, text


def entry(role: str, body: str) -> str:
    """写一段（新写法）。讲员 = ``H body``；人物 = ``body``。"""
    body = str(body or "").strip()
    if role == "host":
        return f"{HOST_TAG} {body}" if body else HOST_TAG
    return body


def join(parts) -> str:
    return " | ".join(p for p in (str(x or "").strip() for x in parts or []) if p)


def migrate(text) -> str:
    """旧写法 → 新写法，只改标签：顺序、括号、不出现的人都不动（存的时候用）。已经是新写法就原样返回。"""
    if is_new_format(text):
        return text if isinstance(text, str) else str(text or "")
    out = []
    for seg in segments(text):
        role, body = split_label(seg)
        out.append(entry(role, body))
    return join(out)


def ref_who(row, *, pos=None, zh: bool = False) -> str:
    """t281: 提示词 / 参考图名单里怎么称呼一个人（新写法，不写 人物N「名字」）：
    讲员 = ``H 形象``；人物 = ``性别/年龄段/族裔/名字``。给了位置（这一场 actor 里的第几个人，讲员也算一个；
    也可以放在 row["pos"]）就加上，分清哪张图是谁。"""
    row = row if isinstance(row, dict) else {}
    name = str(row.get("name") or row.get("body") or "").strip()
    host = row.get("role") == "host"
    who = entry("host" if host else "person", name) or ("H" if host else "")
    p = pos if pos is not None else row.get("pos")
    try:
        p = int(p or 0)
    except (TypeError, ValueError):
        p = 0
    if p > 0:
        who += f"（actor 第{p}位）" if zh else f" (actor position {p})"
    return who


def is_new_format(text) -> bool:
    """这段 actor 文字是不是已经全是新写法（没有 人物N： / 讲员： 这类旧标签）。"""
    for seg in segments(text):
        m = LABEL_RE.match(seg)
        if m and not m.group(2):
            return False
    return True
