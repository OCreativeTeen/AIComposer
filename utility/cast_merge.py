"""t280: 人物栏「人物合并」：把几个人并成一个，改写每一场的 actor 和讲话里的 <N>（纯函数，不碰界面和文件）。

* 合并后的人放在第一个选中的人的位置（人物栏里）；每一场里，被并的人中第一个出现的位置留下，写成新的 id，
  这一场原来的括号说明保留（第一个没有说明就用后面那个的）。
* 同一场里有两个被并的人：只留一个，另一个去掉；讲话里两个人的 <N> 都改成留下的那个号，后面的人往前补位
  （和 t278 归拢一样用 project_manager.remap_speaker_marks，连着的同一个人合成一段）。
* 讲员（H）不参加合并。没有被并的人的场景一个字不动。
"""
from __future__ import annotations

import re

from utility import actor_format

_TAIL_RE = re.compile(r"\s*[（(][^（()）]*[）)]\s*$")
_ABSENT = ("", "不出现", "背景")


def default_key(row: dict) -> tuple:
    """同一个人：讲员按角色；人物按 性别/年龄段/族裔/名字（去掉括号，大小写不分）。"""
    if (row or {}).get("role") == "host":
        return ("host", "")
    from utility.cast_consolidate import clean_body

    return ("person", clean_body(str((row or {}).get("body") or "")).strip().lower())


def _items(actor) -> list:
    out, pos = [], 0
    for seg in actor_format.segments(actor):
        role, body = actor_format.split_label(seg)
        m = _TAIL_RE.search(body)
        base = body[: m.start()].strip() if m else body.strip()
        tail = m.group(0).strip() if m else ""
        absent = base in _ABSENT
        if not absent:
            pos += 1
        out.append({"role": role, "base": base, "tail": tail, "absent": absent, "pos": 0 if absent else pos})
    return out


def _write(items: list) -> str:
    return actor_format.join(actor_format.entry(it["role"], it["base"] + it["tail"]) for it in items)


def merge_scene(scene: dict, keys, new_body: str, key=default_key) -> bool:
    """一场：keys 里的人并成 new_body。改了返回 True（没有这些人就一个字不动）。"""
    if not isinstance(scene, dict):
        return False
    keys = set(keys or ())
    items = _items(scene.get("actor"))
    hits = [it for it in items if not it["absent"] and it["role"] != "host"
            and key({"role": "person", "body": it["base"]}) in keys]
    if not hits:
        return False
    keep = hits[0]
    keep["base"] = str(new_body or "").strip()
    if not keep["tail"]:
        keep["tail"] = next((h["tail"] for h in hits[1:] if h["tail"]), "")
    drop = {id(h) for h in hits[1:]}
    kept, posmap, newpos = [], {}, 0
    for it in items:
        if id(it) in drop:
            continue
        if not it["absent"]:
            newpos += 1
            posmap[it["pos"]] = newpos
        kept.append(it)
    for h in hits[1:]:
        posmap[h["pos"]] = posmap[keep["pos"]]
    scene["actor"] = _write(kept)
    if any(a != b for a, b in posmap.items()):
        import project_manager

        for field in ("speaking", "voiceover"):
            text = str(scene.get(field) or "")
            if text.strip():
                new = project_manager.remap_speaker_marks(text, posmap)
                if new != text:
                    scene[field] = new
                    if field == "speaking":
                        scene.pop("speaking_timing", None)  # 时间轴对不上了，重新算
    return True


def merge_people_in_scenes(scenes, keys, new_body: str, key=default_key) -> int:
    """每一场都并。返回改了几场。"""
    return sum(1 for sc in (scenes or []) if merge_scene(sc, keys, new_body, key=key))


def merge_cast_rows(rows: list, indexes, new_body: str) -> list:
    """人物栏的行：indexes 里的人并成一个，放在第一个选中的人（indexes[0]）的位置；讲员不并。"""
    rows = list(rows or [])
    idx = [i for i in (indexes or []) if 0 <= i < len(rows) and (rows[i] or {}).get("role") != "host"]
    if not idx:
        return [dict(r) for r in rows]
    first, others = idx[0], set(idx[1:])
    out = []
    for i, r in enumerate(rows):
        if i in others:
            continue
        out.append(dict(r, role="person", body=str(new_body or "").strip()) if i == first else dict(r))
    return out


def remove_cast_rows(rows: list, indexes) -> list:
    """人物栏的行：去掉 indexes 里的人（讲员也可以删）。"""
    drop = set(indexes or [])
    return [dict(r) for i, r in enumerate(rows or []) if i not in drop]


def _same_stem(a: str, b: str) -> bool:
    import os

    na = os.path.splitext(os.path.normcase(os.path.abspath(a)))[0]
    nb = os.path.splitext(os.path.normcase(os.path.abspath(b)))[0]
    return na == nb


def merge_portrait_files(paths, dest: str) -> dict:
    """t281: 合并时的肖像。``paths`` = 被并的人现在的肖像（第一个选中的在前；没有的写 ""），``dest`` = 合并后这一位的肖像。

    留第一个选中的人的；他没有就用后面第一个有的 → 复制成 dest（dest 原来有别的图先 .bakN）。
    其他人的肖像（包括被用掉的那张原图，只要它不是 dest）都改名 .bakN 备份，一张都不删。
    返回 {"kept": 用的哪张, "dest": 写好的路径, "backups": [备份]}。"""
    import os

    from utility.portrait_candidates import apply_portrait_choice, backup_existing

    have = [p for p in (paths or []) if p and os.path.isfile(p)]
    out = {"kept": "", "dest": "", "backups": []}
    if not have or not dest:
        return out
    keep = have[0]
    out["kept"] = keep
    out["dest"] = keep if _same_stem(keep, dest) else apply_portrait_choice(keep, dest)
    for p in have:
        if os.path.isfile(p) and not _same_stem(p, out["dest"]):
            out["backups"] += backup_existing(p)
    return out


def merge_voice_settings(project_config, bodies, new_body: str) -> dict:
    """t281: 合并时的声音（项目的 actor_voices 表）：留第一个选中的人选过的声音，他没选过就用后面第一个选过的，
    记到合并后的人名下。原来几个人的记录留着不删。返回 {"voice": ..., "changed": bool}。"""
    import config_prompt

    out = {"voice": "", "changed": False}
    if not isinstance(project_config, dict):
        return out
    table = project_config.get("actor_voices")
    if not isinstance(table, dict):
        return out
    keys = [config_prompt.actor_voice_storage_key(b or "", "person") for b in (bodies or [])]
    voice = next((str(table.get(k) or "").strip() for k in keys if k and str(table.get(k) or "").strip()), "")
    new_key = config_prompt.actor_voice_storage_key(new_body or "", "person")
    out["voice"] = voice
    if voice and new_key and table.get(new_key) != voice:
        table[new_key] = voice
        out["changed"] = True
    return out


def split_id(body: str) -> dict:
    """``woman/mature/chinese/名字（…）`` → {gender, age, eth, name}（合并窗口预填用；girl/boy 读成 woman/man）。"""
    from utility.cast_consolidate import parse_person

    p = parse_person(body or "")
    return {"gender": p.get("gender") or "", "age": p.get("age") or "", "eth": p.get("eth") or "",
            "name": p.get("name") or ""}
