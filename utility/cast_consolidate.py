"""t278: 「动态生成人物」——每一场（每一页）自己找人，全部场景生成完再归拢成一份最终人物名单。

1. 每一场的 actor 是模型只看这一场（这一页的图 / 这一场的文字）找出来的人，前面场景的人物不带到后面。
   每个人都要 ``gender/age band/ethnicity/name``（项目的词表：man|woman；kids|teenager|youth|mature|senior；
   chinese|english）。缺了的不在这里自己补，只记一行日志，留给归拢时补。
2. 全部场景生成完：一次 Strata 文字调用（每场的序号、caption / visual / 台词摘要、这一场找到的人），
   Strata 把同一个人的几种写法并成一个、改错的性别 / 年龄段 / 民族、挑出必要的人（t279: 最多 10 个人物，
   讲员只在播客要），再给每一场「原来那一项 → 最终的谁」。
3. 按这个对应改写每一场的 actor（最终人物的 id + 这一场自己的括号说明），同一场两项并成一个人、
   或去掉不是人的项时，台词里的 <N> / <Ns> 跟着改号（s 自言自语标记不动，句子先后不动）。
4. 人物栏 = 最终名单，不带任何括号。
5. Strata 失败：重试 1 次，再不行用本地合并（只合并名字完全一样的人），日志写清楚。

本模块不碰界面和项目文件；``ask(system, user) -> str`` 可传假的（测试）。
环境变量 ``AICOMPOSER_CAST_CONSOLIDATE=local``：不调 Strata，直接本地合并（测试 / 离线）。
"""
from __future__ import annotations

import json
import os
import re

from utility.actor_edit_fields import ACTOR_AGES, ACTOR_GENDERS, ACTOR_RACES, _AGE_ALIASES, _GENDER_ALIASES

ENV_MODE = "AICOMPOSER_CAST_CONSOLIDATE"
MAX_PEOPLE = 10  # t279: 最终人物最多 10 个（= project_manager.CAST_MAX_PEOPLE）；每一场还是最多 4 个人
NOTE_MAX = 40  # 一场的括号说明最多这么长；更长的多半是模型的推理文字，不留

GENDERS = tuple(ACTOR_GENDERS)
AGES = tuple(ACTOR_AGES)
ETHNICITIES = tuple(ACTOR_RACES)

_GENDER_WORDS = {g: g for g in GENDERS}
_GENDER_WORDS.update(_GENDER_ALIASES)
_GENDER_WORDS.update({"男": "man", "男性": "man", "女": "woman", "女性": "woman"})
_AGE_WORDS = {a: a for a in AGES}
_AGE_WORDS.update(_AGE_ALIASES)
_ETH_WORDS = {e: e for e in ETHNICITIES}
_ETH_WORDS.update({"western": "english"})

from utility import actor_format  # noqa: E402  # t280: actor 新写法

_LABEL_RE = actor_format.LABEL_RE
_NOTE_RE = re.compile(r"\s*[（(【\[]([^（()）【】\[\]]*)[）)】\]]\s*$")
_PROSE_RE = re.compile(r"[。？！?!：:；;，,\n]")
_SPEAKER_RE = re.compile(r"[<＜]\s*(\d+)\s*(s)?\s*[>＞]")

FIELD_NAMES = {"gender": "性别", "age": "年龄段", "eth": "民族"}


# ----------------------------------------------------------------- 解析一场的人
def _segments(text) -> list:
    raw = str(text or "").replace("；", "|").replace(";", "|").replace("\n", "|")
    return [p.strip() for p in raw.split("|") if p.strip()]


def strip_notes(body) -> tuple:
    """``woman/kids/chinese/英莲（抱着）（哭）`` → (``woman/kids/chinese/英莲``, ["抱着", "哭"])。末尾的括号全去掉。"""
    base = str(body or "").strip()
    notes = []
    while True:
        m = _NOTE_RE.search(base)
        if not m:
            break
        if m.group(1).strip() and m.group(1).strip() not in notes:
            notes.insert(0, m.group(1).strip())
        base = base[: m.start()].rstrip()
    # 没收尾的括号（模型的长说明被截断）：从括号起都算说明
    m = re.search(r"[（(【\[]", base)
    if m and not re.search(r"[）)】\]]", base[m.start():]):
        rest = base[m.start() + 1:].strip()
        if rest:
            notes.insert(0, rest)
        base = base[: m.start()].rstrip()
    return base.strip(), notes


def clean_body(body) -> str:
    """人物栏用：只留 id（性别/年龄段/民族/名字），括号说明一个不留。"""
    return strip_notes(body)[0]


def clean_cast_text(cast_text) -> str:
    """名单文字里每个人的括号都去掉；t280: 写成新写法（讲员 = ``H …``，人物不带标签）。"""
    out = []
    for seg in _segments(cast_text):
        role, body = actor_format.split_label(seg)
        body = clean_body(body)
        if body:
            out.append(actor_format.entry(role, body))
    return " | ".join(out)


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).lower()


def parse_person(body) -> dict:
    """一项人物文字 → {gender, age, eth, name, note, missing, garbage}。不猜缺了的字段。"""
    base, notes = strip_notes(body)
    parts = [p.strip() for p in base.replace("／", "/").split("/") if p.strip()]
    gender = age = eth = ""
    rest = []
    for p in parts:
        low = p.lower()
        if not rest and not gender and low in _GENDER_WORDS:
            gender = _GENDER_WORDS[low]
            continue
        if not rest and not age and low in _AGE_WORDS:
            age = _AGE_WORDS[low]
            continue
        if not rest and not eth and low in _ETH_WORDS:
            eth = _ETH_WORDS[low]
            continue
        rest.append(p)
    name = "/".join(rest).strip()
    garbage = bool((name and (len(name) > 24 or _PROSE_RE.search(name))) or not (name or gender or age or eth))
    note = "，".join(notes)
    if len(note) > NOTE_MAX:
        note = ""
    missing = [k for k, v in (("gender", gender), ("age", age), ("eth", eth)) if not v]
    if not name:
        missing.append("name")
    return {"gender": gender, "age": age, "eth": eth, "name": name, "note": note,
            "missing": missing, "garbage": garbage}


def full_id(p: dict) -> str:
    return f"{p['gender']}/{p['age']}/{p['eth']}/{p['name']}"


def speakers_in(scene: dict) -> set:
    nums = set()
    for key in ("speaking", "voiceover"):
        for m in _SPEAKER_RE.finditer(str(scene.get(key) or "")):
            nums.add(int(m.group(1)))
    return nums


def scene_entries(k: int, scene: dict) -> list:
    """第 k 场 actor 的每一项（按原来的先后；<N> 的 N = 不算「不出现」的第几项）。"""
    out = []
    speakers = speakers_in(scene)
    pos = 0
    for seg in _segments(scene.get("actor")):
        role, body = actor_format.split_label(seg)
        if not body or body.startswith("不出现") or body == "背景":
            out.append({"kind": "absent", "raw": seg})
            continue
        pos += 1
        p = parse_person(body)
        p.update({"kind": "garbage" if p["garbage"] else "person", "raw": seg, "pos": pos, "ref": f"s{k}p{pos}",
                  "role": role, "speaks": pos in speakers,
                  "scene": k})
        out.append(p)
    return out


def scene_problems(people: list) -> list:
    """每一场找到的人有哪些问题（缺字段 / 不是人物的文字），用来写日志。不自己补。"""
    notes = []
    for ents in people:
        for e in ents:
            if e["kind"] == "garbage":
                notes.append(f"第 {e['scene']} 场：actor 里这一项不是人物（像是说明文字），不算：{e['raw'][:40]}")
            elif e["kind"] == "person" and e["missing"]:
                miss = "、".join(FIELD_NAMES.get(x, "名字") for x in e["missing"])
                notes.append(f"第 {e['scene']} 场：{e['name'] or e['raw'][:20]} 缺{miss}（不自己补，留给最后归拢人物）")
    return notes


# ----------------------------------------------------------------- Strata 归拢
def _short(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def build_prompt(scenes: list, people: list, *, mode: str = "", cap: int = MAX_PEOPLE, setting: str = "") -> tuple:
    """t280: ``setting`` = Story 窗的 地域 / 时代 / 舞台（一两句英文），有就写进去：缺的民族、名字按这个背景判断。"""
    allow_host = mode == "podcast"
    host_rule = (
        "This mode needs exactly one 讲员 (host): give them in \"host\" as {\"gender\", \"age\", \"ethnicity\", \"name\"} "
        "and map their entries to \"H\"." if allow_host else
        "This mode has no 讲员: \"host\" is null and nothing maps to \"H\". An entry marked 讲员 that is really a story "
        "person maps to that person."
    )
    system = "\n".join([
        "You merge the people found in the scenes of ONE story into ONE final cast.",
        "Each scene below lists the people that were found in that scene on its own (scene by scene, without looking at "
        "the other scenes). So the same person may appear under different names or titles (门子 / 应天府门子, "
        "甄士隐 / 士隐), with a wrong gender, age band or ethnicity, with a field missing, or an entry may not be a "
        "person at all (a sentence, a note, a placeholder).",
        "*** Do this:",
        "  1. Decide who the real people of this story are. Merge entries that are the same person (alias, title vs. "
        "name, short vs. full name). Read each scene's caption, picture text and lines to judge; when a scene clearly "
        "shows that an entry is really someone else, map it to that person.",
        "  2. Give every final person a full id: gender = man or woman; age = kids, teenager, youth, mature or senior; "
        "ethnicity = chinese or english; then the name. Fix wrong or missing values from the story (a little daughter is "
        "woman/kids, a young servant boy is man/teenager, a grandmother is woman/senior).",
        "  3. The name is the person's name in this story. When the story gives no personal name, a descriptive name is "
        "fine (某某的女儿, 甘氏之女, 门子). Never a placeholder (人物1, 某人, A). No parentheses and no notes in the "
        "final cast.",
        *(["  3b. The story setting below (place, era, stage) was chosen by the user. Use it when an entry's ethnicity or "
           "age is missing or unclear, and keep names that fit it; never rename a person the scenes already name."]
          if (setting or "").strip() else []),
        f"  4. Keep only the people the program needs: at most {int(cap)} people. Prefer people who speak and who appear "
        "in many scenes. " + host_rule,
        "  5. For EVERY scene, map EVERY entry ref (like s3p2) to a final key (P1, P2, …" + (", H" if allow_host else "")
        + "), or to \"\" when the entry is not a real person or is a minor person left out of the final cast.",
        "*** Output ONLY this JSON, nothing else:",
        '{"cast": [{"key": "P1", "gender": "man", "age": "mature", "ethnicity": "chinese", "name": "贾雨村"}], '
        '"host": null, "scenes": [{"scene": 1, "map": {"s1p1": "P1", "s1p2": ""}}]}',
    ])
    rows = []
    for k, (sc, ents) in enumerate(zip(scenes, people), 1):
        rows.append(f"scene {k}: caption={_short(sc.get('caption'), 60)} | visual={_short(sc.get('visual'), 220)} "
                    f"| lines={_short(sc.get('speaking'), 240)}")
        listed = [e for e in ents if e["kind"] in ("person", "garbage")]
        if not listed:
            rows.append("  (nobody)")
        for e in listed:
            if e["kind"] == "garbage":
                what = "NOT A PERSON? " + _short(e["raw"], 80)
            else:
                what = "/".join(x for x in (e["gender"], e["age"], e["eth"], e["name"]) if x)
                if e["missing"]:
                    what += "  [missing: " + ", ".join(x if x != "eth" else "ethnicity" for x in e["missing"]) + "]"
                if e["note"]:
                    what += f"  (in this scene: {e['note']})"
            tag = " [讲员]" if e["role"] == "host" else ""
            rows.append(f"  {e['ref']}{tag} = {what}" + ("  [speaks]" if e["speaks"] else ""))
    user = "Scenes, in order:\n" + "\n".join(rows)
    if (setting or "").strip():
        user = "Story setting (chosen by the user): " + setting.strip() + "\n\n" + user
    return system, user


def _json_object(raw) -> dict:
    text = re.sub(r"<think>.*?</think>", "", str(raw or ""), flags=re.S | re.I).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    for cand in ([fence.group(1)] if fence else []) + [text]:
        a, b = cand.find("{"), cand.rfind("}")
        if a < 0 or b <= a:
            continue
        try:
            data = json.loads(cand[a:b + 1])
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("回答里没有 JSON 对象：" + (_short(text, 120) or "（空）"))


def _person_from_reply(item) -> str:
    if not isinstance(item, dict):
        raise ValueError(f"人物不是对象：{item!r}")
    g = _GENDER_WORDS.get(str(item.get("gender") or "").strip().lower(), "")
    a = _AGE_WORDS.get(str(item.get("age") or item.get("age_band") or "").strip().lower(), "")
    e = _ETH_WORDS.get(str(item.get("ethnicity") or item.get("eth") or "").strip().lower(), "")
    name = clean_body(str(item.get("name") or "")).strip().replace("/", "")
    if not (g and a and e and name) or len(name) > 24 or _PROSE_RE.search(name):
        raise ValueError(f"最终人物缺字段或不合规：{json.dumps(item, ensure_ascii=False)[:120]}")
    return f"{g}/{a}/{e}/{name}"


def _name_of(body: str) -> str:
    return _norm_name(body.split("/", 3)[-1]) if body.count("/") >= 3 else ""


def parse_reply(raw, people: list, *, cap: int = MAX_PEOPLE, allow_host: bool = False) -> dict:
    """Strata 的回答 → {"cast": [id…], "host": id 或 "", "map": {ref: 序号 / "H" / None}, "dropped": [...]}。
    不合规（没有 JSON、人物缺字段 / 词不在词表里）抛 ValueError（调用方重试 / 退回本地合并）。"""
    data = _json_object(raw)
    items = data.get("cast")
    if not isinstance(items, list):
        raise ValueError("回答里没有 cast 列表")
    bodies, keymap, dropped = [], {}, []
    for i, item in enumerate(items, 1):
        body = _person_from_reply(item)
        key = str(item.get("key") or f"P{i}").strip()
        same = next((j for j, b in enumerate(bodies) if b == body or _name_of(b) == _name_of(body)), None)
        if same is not None:
            keymap[key] = same
            continue
        if len(bodies) >= int(cap):
            keymap[key] = None
            dropped.append(body)
            continue
        keymap[key] = len(bodies)
        bodies.append(body)
    host = ""
    if allow_host and isinstance(data.get("host"), dict) and data.get("host"):
        host = _person_from_reply(data["host"])
    ref_map = {}
    for item in data.get("scenes") or []:
        if not isinstance(item, dict):
            continue
        for ref, key in (item.get("map") or {}).items():
            key = str(key or "").strip()
            if key == "H":
                ref_map[str(ref)] = "H" if host else None
            else:
                ref_map[str(ref)] = keymap.get(key)
    names = {_name_of(b): j for j, b in enumerate(bodies)}
    persons = [e for ents in people for e in ents if e["kind"] == "person"]
    for e in persons:  # Strata 漏了的项：名字完全一样就对上，否则不进最终人物
        if e["ref"] not in ref_map:
            if host and e["role"] == "host" and _norm_name(e["name"]) == _name_of(host):
                ref_map[e["ref"]] = "H"
            else:
                ref_map[e["ref"]] = names.get(_norm_name(e["name"]))
    if persons and not bodies and not host:
        raise ValueError("回答里的最终人物是空的")
    return {"cast": bodies, "host": host, "map": ref_map, "dropped": dropped}


def local_merge(people: list, *, cap: int = MAX_PEOPLE, allow_host: bool = False, log=print) -> dict:
    """Strata 不行时的本地合并：只把名字完全一样的人并成一个（不认别名）。样子取这个名字最常见的完整写法；
    一个完整写法都没有的人不进人物栏（不自己补），日志写出来。人物按说话的场数、出场的场数挑前 cap 个，按第一次出场排。"""
    groups = {}
    order = 0
    for ents in people:
        for e in ents:
            if e["kind"] != "person" or not e["name"]:
                continue
            role = "H" if (allow_host and e["role"] == "host") else "P"
            g = groups.setdefault((role, _norm_name(e["name"])), {"first": order, "ids": [], "scenes": set(),
                                                                    "speaks": set(), "refs": [], "name": e["name"]})
            order += 1
            if not [x for x in e["missing"] if x != "name"]:
                g["ids"].append(full_id(e))
            g["scenes"].add(e["scene"])
            if e["speaks"]:
                g["speaks"].add(e["scene"])
            g["refs"].append(e["ref"])
    chosen = {}
    for key, g in groups.items():
        if not g["ids"]:
            log(f"⚠️ 动态人物（本地合并）：{g['name']} 每一场都缺性别 / 年龄段 / 民族，本地补不了，没放进人物栏（请手动补）")
            continue
        counts = {}
        for i in g["ids"]:
            counts[i] = counts.get(i, 0) + 1
        best = max(counts.values())
        chosen[key] = next(i for i in g["ids"] if counts[i] == best)
    host = ""
    host_refs = []
    for key in sorted((k for k in chosen if k[0] == "H"), key=lambda k: groups[k]["first"]):
        host, host_refs = chosen[key], groups[key]["refs"]
        break
    ranked = sorted((k for k in chosen if k[0] == "P"),
                    key=lambda k: (-len(groups[k]["speaks"]), -len(groups[k]["scenes"]), groups[k]["first"]))
    keep = sorted(ranked[: int(cap)], key=lambda k: groups[k]["first"])
    for k in ranked[int(cap):]:
        log(f"动态人物（本地合并）：人物已满 {cap} 个，{chosen[k]} 不进人物栏")
    bodies = [chosen[k] for k in keep]
    ref_map = {}
    for idx, k in enumerate(keep):
        for ref in groups[k]["refs"]:
            ref_map[ref] = idx
    for ref in host_refs:
        ref_map[ref] = "H"
    return {"cast": bodies, "host": host, "map": ref_map, "dropped": [chosen[k] for k in ranked[int(cap):]]}


# ----------------------------------------------------------------- 改写每一场
def remap_speakers(text: str, posmap: dict) -> str:
    """<N> / <Ns> 按 posmap 改号；s（自言自语）留着，句子先后不动；不在 posmap 里的号不动。"""
    def sub(m):
        n = int(m.group(1))
        if n not in posmap:
            return m.group(0)
        return f"<{posmap[n]}{'s' if m.group(2) else ''}>"
    return _SPEAKER_RE.sub(sub, str(text or ""))


def apply_result(scenes: list, people: list, result: dict, *, log=print) -> None:
    bodies, host, ref_map = result["cast"], result.get("host") or "", result["map"]
    for k, (sc, ents) in enumerate(zip(scenes, people), 1):
        if not ents:
            continue
        rows, posmap, seen = [], {}, {}
        newpos = 0
        for e in ents:
            if e["kind"] == "absent":
                continue
            target = ref_map.get(e["ref"]) if e["kind"] == "person" else None
            if target is None or (target == "H" and not host):
                if e["speaks"]:
                    newpos += 1
                    posmap[e["pos"]] = newpos
                    rows.append(actor_format.entry(e["role"], actor_format.split_label(e["raw"])[1]))
                    log(f"⚠️ 动态人物：第 {k} 场 {e['name'] or e['raw'][:20]} 有台词但不在最终人物里，留在这一场（没进人物栏）")
                elif e["kind"] == "person":
                    log(f"动态人物：第 {k} 场 {e['name'] or e['raw'][:20]} 不在最终人物里，从这一场拿掉（没有台词）")
                continue
            if target in seen:
                posmap[e["pos"]] = seen[target]
                if e["note"] and not rows[seen[target] - 1][2]:
                    rows[seen[target] - 1][2] = e["note"]
                continue
            newpos += 1
            seen[target] = newpos
            posmap[e["pos"]] = newpos
            if target == "H":
                rows.append(["host", host, e["note"]])
            else:
                rows.append(["person", bodies[int(target)], e["note"]])
        parts = []
        for r in rows:
            if isinstance(r, list):
                parts.append(actor_format.entry(r[0], r[1] + (f"（{r[2]}）" if r[2] else "")))
            else:
                parts.append(r)
        parts += [actor_format.migrate(e["raw"]) for e in ents if e["kind"] == "absent"]
        sc["actor"] = " | ".join(parts)
        if any(o != n for o, n in posmap.items()):
            for key in ("speaking", "voiceover"):
                if sc.get(key):
                    sc[key] = remap_speakers(sc[key], posmap)


def cast_text(result: dict) -> str:
    parts = []
    if result.get("host"):
        parts.append(actor_format.entry("host", clean_body(result["host"])))
    for body in result.get("cast") or []:
        parts.append(actor_format.entry("person", clean_body(body)))
    return " | ".join(parts)


def strata_ask(system: str, user: str) -> str:
    """一次 Strata 文字调用（不开手动窗口）。``AICOMPOSER_CAST_CONSOLIDATE=local`` 时不调。"""
    if (os.environ.get(ENV_MODE) or "").strip().lower() == "local":
        raise RuntimeError(f"{ENV_MODE}=local：不调 Strata")
    from utility import llm_api
    from utility.prompt_polish import _clean, _strata_client

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": system}, {"role": "user", "content": user}])
    resp = _strata_client(llm_api.STRATA_SCENE_TIMEOUT_S).chat.completions.create(**req)
    return _clean(resp.choices[0].message.content if resp and resp.choices else "")


def consolidate(scenes: list, *, mode: str = "", ask=None, cap: int = MAX_PEOPLE, retries: int = 1, log=print,
                setting: str = "") -> dict:
    """全部场景生成完以后跑一次。改写 scenes（actor / 台词号），返回
    {"cast": 人物栏文字（无括号）, "source": "strata" / "local" / "none", "error": 最后一次失败原因, "result": ...}。"""
    allow_host = mode == "podcast"
    people = [scene_entries(k, sc) for k, sc in enumerate(scenes or [], 1)]
    for note in scene_problems(people):
        log(f"动态人物：{note}")
    persons = [e for ents in people for e in ents if e["kind"] == "person"]
    error = ""
    if not persons:
        result, source = {"cast": [], "host": "", "map": {}, "dropped": []}, "none"
    else:
        result, source = None, ""
        system, user = build_prompt(scenes, people, mode=mode, cap=cap, setting=setting)
        fn = ask or strata_ask
        for attempt in range(1 + max(0, int(retries))):
            try:
                result = parse_reply(fn(system, user), people, cap=cap, allow_host=allow_host)
                source = "strata"
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log(f"⚠️ 动态人物：Strata 归拢人物第 {attempt + 1} 次没成功：{error[:200]}")
        if result is None:
            log("⚠️ 动态人物：Strata 归拢人物失败（重试 1 次也没成），改用本地合并：只把名字完全一样的人并成一个，"
                "别名 / 称呼（如 门子 和 应天府门子）不会合并，缺的性别 / 年龄段 / 民族也补不了，请检查人物栏")
            result = local_merge(people, cap=cap, allow_host=allow_host, log=log)
            source = "local"
    apply_result(scenes, people, result, log=log)
    text = cast_text(result)
    who = {"strata": "Strata 归拢", "local": "本地合并", "none": "没有找到人物"}[source]
    log(f"动态人物：最终人物（{who}）：{text or '（没有人物）'}")
    return {"cast": text, "source": source, "error": error, "result": result}