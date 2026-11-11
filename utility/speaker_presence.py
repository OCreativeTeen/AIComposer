# -*- coding: utf-8 -*-
"""t392u: MiniMax 参考图工作流：先看场景图（起始画面）里已经有哪些说话人，只给不在图里的人发肖像。

肖像会被模型当成镜头直接放出来（说到某人那句就切到他的肖像），所以场景图里已经有的人一律不发肖像；
全都在 → 一张肖像也不发（提示词里也没有肖像段 / Speaker map 里的肖像编号）。
用本机 Strata（和 prompt_polish.describe_speakers 同一个看图接口）。结果按（图路径 + 修改时间 + 说话人）缓存，
全集再跑同一张图不再问。判断失败 / 超时 → 不发肖像（只发场景图），控制台打出原因。
"""
import json
import os
import re
import threading
import time

PRESENCE_TIMEOUT_S = 45.0
SCENE_CACHE_FIELD = "speaker_presence"
_CACHE = {}
_LOCK = threading.Lock()

_SYS = """You check which people of one video scene can be seen in the scene picture (Picture 1).
You get a list of people (id, name, a short description of their look and where they sit or stand), then Picture 1, and for some people a portrait that only helps you recognise them.
A person is present when that person can be seen anywhere in Picture 1: whole or partly, from the side or from behind, small or in the background. A person is missing only when no one in Picture 1 can be that person.
Return only JSON, for example: {"present": ["S1"], "missing": ["S2"]}"""


def cache_key(image_path: str, speakers: list) -> str:
    try:
        mt = os.path.getmtime(image_path)
    except OSError:
        mt = 0.0
    who = "|".join(f"{n}:{name}" for n, name, *_r in speakers)
    return f"{os.path.normcase(os.path.abspath(str(image_path or '')))}|{mt:.3f}|{who}"


def _strata_ask(content, timeout_s: float) -> str:
    """一次 Strata 看图请求，返回原始文字（失败抛异常）。"""
    from utility import llm_api
    from utility.prompt_polish import _clean, _strata_client

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": _SYS},
                                                {"role": "user", "content": content}])
    req["max_tokens"] = 256
    resp = _strata_client(timeout_s).chat.completions.create(**req)
    return _clean(resp.choices[0].message.content if resp and resp.choices else "")


def _content(image_path: str, speakers: list, with_portraits: bool) -> list:
    from utility.prompt_polish import _image_data_url

    lines = ["People:"]
    for n, name, desc, *_r in speakers:
        lines.append(f"- S{n}: {name}" + (f", {desc}" if desc else ""))
    content = [{"type": "text", "text": "\n".join(lines)},
               {"type": "text", "text": "Picture 1 (the scene):"},
               {"type": "image_url", "image_url": {"url": _image_data_url(image_path, 768)}}]
    if with_portraits:
        for n, name, _desc, *rest in speakers:
            portrait = rest[0] if rest else ""
            if portrait and os.path.isfile(portrait):
                content += [{"type": "text", "text": f"Portrait of S{n} {name} (only to recognise this person):"},
                            {"type": "image_url", "image_url": {"url": _image_data_url(portrait, 384)}}]
    return content


def parse_answer(raw: str, ids: set) -> set:
    """JSON → 在场的说话人编号集合。读不出来抛 ValueError。没提到的人算不在（给肖像）。"""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise ValueError(f"没有 JSON：{(raw or '')[:80]}")
    data = json.loads(m.group(0))
    if not isinstance(data, dict) or not isinstance(data.get("present", []), list):
        raise ValueError(f"JSON 格式不对：{(raw or '')[:80]}")
    present = set()
    for x in data.get("present") or []:
        mm = re.match(r"^\s*S?(\d+)\s*$", str(x))
        if mm and int(mm.group(1)) in ids:
            present.add(int(mm.group(1)))
    return present


def detect_present_speakers(image_path: str, speakers: list, *, scene=None, ask=None,
                            timeout_s: float = PRESENCE_TIMEOUT_S) -> tuple:
    """speakers = [(序号, 名字, 外貌/位置描述, 肖像路径或 "")]。
    返回 (在场序号集合, 说明)；判断不出来返回 (None, 原因)。ask(content, timeout_s) -> 文字，测试里换成假的。"""
    if not speakers:
        return set(), "没有说话人"
    if not image_path or not os.path.isfile(image_path):
        return None, "没有场景图"
    key = cache_key(image_path, speakers)
    with _LOCK:
        if key in _CACHE:
            return set(_CACHE[key]), "缓存"
    if isinstance(scene, dict):
        rec = scene.get(SCENE_CACHE_FIELD)
        if isinstance(rec, dict) and rec.get("key") == key and isinstance(rec.get("present"), list):
            present = {int(x) for x in rec["present"]}
            with _LOCK:
                _CACHE[key] = present
            return set(present), "缓存（场景里记过）"
    ask = ask or _strata_ask
    ids = {int(n) for n, *_r in speakers}
    started = time.monotonic()
    try:
        try:
            raw = ask(_content(image_path, speakers, True), timeout_s)
        except Exception as exc:  # noqa: BLE001  带肖像的请求被拒：只看场景图再问一次
            if type(exc).__name__ not in ("BadRequestError",):
                raise
            print(f"[人物在场] 带肖像请求被拒（{str(exc)[:80]}），只看场景图再问")
            raw = ask(_content(image_path, speakers, False), timeout_s)
        present = parse_answer(raw, ids)
    except Exception as exc:  # noqa: BLE001
        return None, f"Strata 没判断出来（{type(exc).__name__}: {str(exc)[:100]}）"
    with _LOCK:
        _CACHE[key] = set(present)
    if isinstance(scene, dict):
        scene[SCENE_CACHE_FIELD] = {"key": key, "present": sorted(present), "at": round(time.time(), 1)}
    return present, f"Strata 看图 {time.monotonic() - started:.1f} 秒"


def portraits_for_missing(scene, image_path: str, refs: list, speakers: list, *, detect=None, log=print) -> list:
    """refs = [(序号, 名字, 肖像路径)]（要发的肖像候选）。返回只给场景图里没有的人的那几张（顺序不变）。
    判断失败 → 不发肖像（[]）：肖像会被切成镜头，比认错脸更糟。"""
    refs = list(refs or [])
    if not refs:
        return []
    people = list(speakers or []) or [(n, name, "", path) for n, name, path in refs]
    present, why = (detect or detect_present_speakers)(image_path, people, scene=scene)
    if present is None:
        log(f"[人物在场] {why}；这一场不发肖像（只发场景图）")
        return []
    names = {int(n): name for n, name, *_r in people}
    kept = [r for r in refs if int(r[0]) not in present]
    _in = "、".join(names.get(n, f"S{n}") for n in sorted(present)) or "无"
    _out = "、".join(name for n, name in sorted(names.items()) if n not in present) or "无"
    _sent = "、".join(f"{name}（<Picture {k}>）" for k, (_n, name, _p) in enumerate(kept, 2)) or "不发肖像"
    log(f"[人物在场] 场景图里有：{_in}；不在：{_out}；发肖像：{_sent}（{why}）")
    return kept
