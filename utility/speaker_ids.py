"""t174u: 场景生成后，人物编号按整个故事统一。

提示词要求：同一个人整篇故事用同一个 人物N / <N>，actor 按编号从小到大列出这一场的人。
程序里 <N> = 这一场 actor 里的第 N 个人（配音、形象图、MiniMax 说话人都按这个对），
所以这里只做两件事，不删任何内容：
1) actor 按 人物N 从小到大重排（<N> 不变，只是顺序对上）；
2) 这一场缺了前面的编号（例如只有 人物2）时，把这一场的 <N> 和 人物N 改成 1..k，
   不然配音会找不到人。改过的场景和前后描述不一致的人都写进 notes 提醒。
"""
from __future__ import annotations

import re

_LABEL_RE = re.compile(r"^\s*人物\s*(\d+)\s*[:：]\s*")
_MARK_RE = re.compile(r"([<＜])\s*(\d+)\s*([>＞])")
_HOST_WORDS = ("讲员", "講員", "主持人")


def _segments(actor: str) -> list:
    raw = str(actor or "").replace("；", "|").replace(";", "|")
    return [p.strip() for p in raw.split("|") if p.strip()]


def _base(body: str) -> str:
    return re.split(r"[（(]", body, 1)[0].strip().lower()


def align_story_speakers(scenes: list) -> tuple:
    """返回 (scenes, notes)。scenes 原地修改并返回。"""
    notes: list = []
    seen_desc: dict = {}
    for si, sc in enumerate(scenes or [], 1):
        if not isinstance(sc, dict):
            continue
        segs = _segments(sc.get("actor"))
        if not segs:
            continue
        labeled = []
        for seg in segs:
            if any(w in seg for w in _HOST_WORDS):
                labeled = None
                break
            m = _LABEL_RE.match(seg)
            if not m:
                labeled = None
                break
            labeled.append((int(m.group(1)), seg[m.end():].strip()))
        if not labeled:
            continue
        nums = [k for k, _b in labeled]
        if len(set(nums)) != len(nums):
            notes.append(f"第{si}场：actor 里 人物编号重复 {nums}，没有改")
            continue
        for k, body in labeled:
            b = _base(body)
            if k in seen_desc and seen_desc[k] != b:
                notes.append(f"第{si}场：人物{k} 的描述和前面不一样（{seen_desc[k]} → {b}）")
            seen_desc.setdefault(k, b)
        speaking = str(sc.get("speaking") or "")
        used = {int(m.group(2)) for m in _MARK_RE.finditer(speaking)}
        missing = sorted(used - set(nums))
        if missing:
            notes.append(f"第{si}场：speaking 用了 actor 里没有的 <{'>/<'.join(map(str, missing))}>")
        ordered = sorted(labeled)
        pos = {k: i for i, (k, _b) in enumerate(ordered, 1)}
        if all(pos[k] == k for k in pos):
            if labeled != ordered:
                sc["actor"] = " | ".join(f"人物{k}：{b}" for k, b in ordered)
            continue
        # 缺了前面的编号：这一场改成 1..k
        sc["actor"] = " | ".join(f"人物{pos[k]}：{b}" for k, b in ordered)
        sc["speaking"] = _MARK_RE.sub(
            lambda m: f"{m.group(1)}{pos.get(int(m.group(2)), int(m.group(2)))}{m.group(3)}", speaking
        )
        change = "，".join(f"人物{k}→{pos[k]}" for k in pos if pos[k] != k)
        notes.append(f"第{si}场：这一场没有前面编号的人，按本场顺序改成 {change}（配音按本场第几人对应）")
    return scenes, notes
