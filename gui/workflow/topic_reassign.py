"""t203u: 魔法工作流顶栏「确认分类」：分类 / 子类 / 标签改动只在确认后生效。

- 分类变了：把项目在 list_by_topic 里的那一行从旧分类列表搬到新分类列表（整行保留，改 topic 字段，先备份）；
  子类（t212u）和标签都让 Strata 根据 analyzed_content 在新分类里选（子类不合法就用第一个）；标签让 Strata 根据 analyzed_content + topics.json 里这个子类的 tags 建议来选，
  没合适的可以提新标签，新标签加进 topics.json 同一分类 / 子类的 tags（先备份）。
- 只有子类 / 标签变了：在当前列表里原地改这一行。
这里只有纯函数（不碰 tkinter），方便无界面测试。
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import time

TOPICS_FILE = "topics.json"


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def backup_file(path: str, backup_dir: str = "") -> str:
    """复制一份 <name>.bak_<时间>；backup_dir 为空时放在原文件旁边。"""
    if not path or not os.path.isfile(path):
        return ""
    d = backup_dir or os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f"{os.path.basename(path)}.bak_{_ts()}")
    k = 1
    while os.path.exists(dst):  # 同一秒里第二次备份不覆盖
        k += 1
        dst = os.path.join(d, f"{os.path.basename(path)}.bak_{_ts()}_{k}")
    shutil.copy2(path, dst)
    return dst


def tags_as_list(v) -> list:
    if isinstance(v, (list, tuple)):
        return [str(t).strip() for t in v if str(t).strip()]
    s = str(v or "").strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            got = ast.literal_eval(s)
            if isinstance(got, (list, tuple)):
                return [str(t).strip() for t in got if str(t).strip()]
        except Exception:  # noqa: BLE001
            pass
    return [t.strip() for t in re.split(r"[|,，、;；]", s) if t.strip()]


def _tags_like(old, tags: list):
    """按原来的存法写回：原来是 "['a', 'b']" 字符串就还写字符串，是列表就写列表。"""
    return str(list(tags)) if isinstance(old, str) else list(tags)


# ---------------------------------------------------------------- topics.json
def topic_entry(topics: list, category: str) -> dict:
    for it in topics or []:
        if isinstance(it, dict) and str(it.get("topic_category") or "").strip() == category:
            return it
    return {}


def subtype_entry(topics: list, category: str, subtype: str) -> dict:
    for s in topic_entry(topics, category).get("topic_subtypes") or []:
        if isinstance(s, dict) and str(s.get("topic_subtype") or "").strip() == subtype:
            return s
    return {}


def subtypes_of(topics: list, category: str) -> list:
    return [str(s.get("topic_subtype") or "").strip() for s in topic_entry(topics, category).get("topic_subtypes") or []
            if isinstance(s, dict) and str(s.get("topic_subtype") or "").strip()]


def suggested_tags(topics: list, category: str, subtype: str = "") -> list:
    """子类的 tags；没指定子类时合并这个分类所有子类的 tags（再加分类本身的 tags，如有）。"""
    if subtype:
        return tags_as_list(subtype_entry(topics, category, subtype).get("tags"))
    out = tags_as_list(topic_entry(topics, category).get("tags"))
    for s in topic_entry(topics, category).get("topic_subtypes") or []:
        for t in tags_as_list((s or {}).get("tags")):
            if t not in out:
                out.append(t)
    return out


def add_tags_to_topics(topics_path: str, category: str, subtype: str, new_tags: list) -> list:
    """把新标签加进 topics.json 这个分类 / 子类的 tags（先备份）。返回真正新加的标签。"""
    new_tags = [t for t in (str(x).strip() for x in new_tags or []) if t]
    if not new_tags:
        return []
    topics = _read_json(topics_path)
    ent = subtype_entry(topics, category, subtype) if subtype else topic_entry(topics, category)
    if not ent:
        return []
    have = tags_as_list(ent.get("tags"))
    added = [t for t in new_tags if t not in have]
    if not added:
        return []
    backup_file(topics_path)
    ent["tags"] = have + added
    _write_json(topics_path, topics)
    return added


# ---------------------------------------------------------------- Strata
def build_tag_prompt(analyzed: str, category: str, subtype: str, subtype_desc: str, suggestions: list,
                     category_desc: str = "") -> tuple:
    system = (
        "You choose YouTube topic tags for a psychology / story video. The ANALYSIS REPORT is the primary "
        "source: tags must name what the report is really about. Category, subtype, their descriptions and the "
        "suggested tags are reference only (prefer a suggested tag when it fits). Reply with JSON only: "
        '{"tags": [...], "new_tags": [...]}. "tags" = 3 to 6 tags from the suggestion list that really fit the '
        'content. Only when none of the suggestions fits a key point, put 1 to 3 short new tags (same language and '
        'style as the suggestions, 2 to 6 Chinese characters each) in "new_tags"; they are also used as tags. '
        "No explanation."
    )
    user = (
        f"ANALYSIS REPORT (分析报告, primary input):\n{(analyzed or '')[:6000]}\n\n"
        f"--- Reference ---\nCategory: {category}\nCategory description: {category_desc}\n"
        f"Subtype: {subtype}\nSubtype description: {subtype_desc}\n"
        f"Suggested tags: {json.dumps(suggestions, ensure_ascii=False)}"
    )
    return system, user


def parse_tag_reply(reply, suggestions: list) -> tuple:
    """返回 (tags, new_tags)。tags 里不在建议里的也算新标签。"""
    text = reply if isinstance(reply, str) else str((reply or {}).get("text") if isinstance(reply, dict) else reply or "")
    m = re.search(r"\{.*\}", text or "", re.S)
    data = {}
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            data = {}
    picked = tags_as_list(data.get("tags"))
    new = tags_as_list(data.get("new_tags"))
    for t in picked:
        if t not in suggestions and t not in new:
            new.append(t)
    tags = []
    for t in picked + new:
        if t not in tags:
            tags.append(t)
    return tags[:8], new[:3]


def strata_pick_tags(analyzed: str, topics: list, category: str, subtype: str, llm=None) -> tuple:
    """调用本机 Strata（utility.llm_api.LLMApi(STRATA).generate_text）。llm 可传 mock：有 generate_text(sys, user)。"""
    sugg = suggested_tags(topics, category, subtype)
    desc = str(subtype_entry(topics, category, subtype).get("description") or "")
    cdesc = str(topic_entry(topics, category).get("description") or "")
    system, user = build_tag_prompt(analyzed, category, subtype, desc, sugg, cdesc)
    if llm is None:
        from utility import llm_api
        llm = llm_api.LLMApi(llm_api.STRATA)
    reply = llm.generate_text(system, user)
    return parse_tag_reply(reply, sugg)


def build_subtype_tag_prompt(analyzed: str, category: str, category_desc: str, subtypes: list) -> tuple:
    """t212u: 分类变了：让 Strata 同时选子类（只能从新分类的子类里选）和标签。
    subtypes = [{"topic_subtype", "description", "tags"}]。"""
    system = (
        "You re-classify a psychology / story video into a new category. The ANALYSIS REPORT is the primary "
        "source. Pick the ONE subtype (from the given list only, copy its name exactly) that best fits the report, "
        "then choose tags. Reply with JSON only: "
        '{"subtype": "...", "tags": [...], "new_tags": [...]}. "tags" = 3 to 6 tags, preferably from the chosen '
        "subtype's tag list, that really fit the content. Only when none fits a key point, put 1 to 3 short new tags "
        '(same language and style, 2 to 6 Chinese characters each) in "new_tags"; they are also used as tags. '
        "No explanation."
    )
    lines = []
    for st in subtypes:
        lines.append(f"- {st.get('topic_subtype')}: {st.get('description') or ''} | tags: "
                     + json.dumps(tags_as_list(st.get("tags")), ensure_ascii=False))
    user = (
        f"ANALYSIS REPORT (分析报告, primary input):\n{(analyzed or '')[:6000]}\n\n"
        f"--- Reference ---\nCategory: {category}\nCategory description: {category_desc}\n"
        "Subtypes (pick one):\n" + "\n".join(lines)
    )
    return system, user


def parse_subtype_reply(reply, subs: list) -> str:
    """回复里的 subtype 必须在 subs 里（容忍空格 / 大小写 / 包含关系），否则返回空。"""
    text = reply if isinstance(reply, str) else str((reply or {}).get("text") if isinstance(reply, dict) else reply or "")
    m = re.search(r"\{.*\}", text or "", re.S)
    got = ""
    if m:
        try:
            got = str((json.loads(m.group(0)) or {}).get("subtype") or "").strip()
        except Exception:  # noqa: BLE001
            got = ""
    if not got:
        return ""
    norm = lambda x: re.sub(r"\s+", "", x).lower()
    for s_ in subs:
        if norm(s_) == norm(got):
            return s_
    for s_ in subs:
        if norm(s_) in norm(got) or norm(got) in norm(s_):
            return s_
    return ""


def strata_pick_subtype_tags(analyzed: str, topics: list, category: str, fallback_sub: str = "", llm=None) -> tuple:
    """t212u: 返回 (子类, tags, new_tags)。子类不合法 → fallback_sub（在列表里）或第一个子类，没子类就空。"""
    subs = subtypes_of(topics, category)
    ents = [subtype_entry(topics, category, x) for x in subs]
    cdesc = str(topic_entry(topics, category).get("description") or "")
    system, user = build_subtype_tag_prompt(analyzed, category, cdesc, ents)
    if llm is None:
        from utility import llm_api
        llm = llm_api.LLMApi(llm_api.STRATA)
    reply = llm.generate_text(system, user)
    sub = parse_subtype_reply(reply, subs) or (fallback_sub if fallback_sub in subs else (subs[0] if subs else ""))
    tags, new = parse_tag_reply(reply, suggested_tags(topics, category, sub))
    return sub, tags, new


# ---------------------------------------------------------------- list_by_topic
def _row_pid(item: dict) -> str:
    try:
        import project_manager
        return project_manager.list_json_row_workflow_pid(item)
    except Exception:  # noqa: BLE001
        prof = item.get("project_profile") if isinstance(item.get("project_profile"), dict) else {}
        return str(prof.get("pid") or item.get("pid") or "").strip()


def row_key(item: dict) -> str:
    """行的标识：有项目 pid 用 pid；还没建项目的行用 id / url。"""
    if not isinstance(item, dict):
        return ""
    pid = _row_pid(item)
    if pid:
        return pid
    if str(item.get("id") or "").strip():
        return "id:" + str(item.get("id")).strip()
    if str(item.get("url") or "").strip():
        return "url:" + str(item.get("url")).strip()
    return ""


def _is_row(it, key: str) -> bool:
    return isinstance(it, dict) and bool(key) and (row_key(it) == key or _row_pid(it) == key)


def _set_topic_fields(item: dict, category: str, subtype: str, tags: list) -> None:
    item["topic_category"] = category
    item["topic_subtype"] = subtype
    item["tags"] = _tags_like(item.get("tags"), tags)
    prof = item.get("project_profile")
    if isinstance(prof, dict):
        prof["topic_category"] = category
        prof["topic_subtype"] = subtype
        prof["tags"] = _tags_like(prof.get("tags"), tags) if "tags" in prof else list(tags)


def update_item_in_place(list_path: str, pid: str, category: str, subtype: str, tags: list,
                         backup_dir: str = "") -> bool:
    arr = _read_json(list_path)
    hit = [i for i, it in enumerate(arr) if _is_row(it, pid)]
    if not hit:
        return False
    backup_file(list_path, backup_dir)
    for i in hit:
        _set_topic_fields(arr[i], category, subtype, tags)
    _write_json(list_path, arr)
    return True


def move_item(old_path: str, new_path: str, pid: str, category: str, subtype: str, tags: list,
              backup_dir: str = "") -> str:
    """把 pid 这一行从 old_path 搬到 new_path（整行保留，改 topic 字段）。返回说明；出错抛 ValueError。"""
    if os.path.abspath(old_path) == os.path.abspath(new_path):
        raise ValueError("新旧分类是同一个列表")
    old = _read_json(old_path)
    rows = [it for it in old if _is_row(it, pid)]
    if not rows:
        raise ValueError(f"旧列表里找不到 pid {pid}: {old_path}")
    new = _read_json(new_path) if os.path.isfile(new_path) else []
    if not isinstance(new, list):
        raise ValueError(f"新列表格式不对: {new_path}")
    row = rows[0]
    _set_topic_fields(row, category, subtype, tags)
    backup_file(old_path, backup_dir)
    if os.path.isfile(new_path):
        backup_file(new_path, backup_dir)
    new = [it for it in new if not (_is_row(it, pid))]  # 不重复
    new.append(row)
    _write_json(new_path, new)  # 先写新表，再从旧表删
    _write_json(old_path, [it for it in old if not (_is_row(it, pid))])
    return f"已从 {os.path.basename(old_path)} 移到 {os.path.basename(new_path)}"

# ---------------------------------------------------------------- 确认分类（魔法工作流 / STORY 预览共用）
def apply_change(ch_path: str, list_path_fn, key: str, old: tuple, new: tuple, analyzed: str,
                 llm=None, backup_dir: str = "") -> dict:
    """old/new = (分类, 子类, 标签list)。list_path_fn(分类) → list_by_topic 文件路径。
    分类或子类变了 → Strata 按分析报告重新生成标签（新标签加进 topics.json）；只改了标签 → 用手填的。
    分类变了 → 搬行（moved=True，调用方要关窗口）；否则原地改。出错抛 ValueError。"""
    old_cat, old_sub, old_tags = old
    cat, sub, tags = new[0], new[1], list(new[2])
    topics_path = os.path.join(ch_path, TOPICS_FILE)
    try:
        topics = _read_json(topics_path)
    except Exception:  # noqa: BLE001
        topics = []
    subs = subtypes_of(topics, cat)
    if subs and sub not in subs:
        sub = subs[0]
    if not subs and cat != old_cat:
        sub = ""
    out = {"moved": False, "category": cat, "subtype": sub, "tags": tags, "added": [], "regen": False,
           "strata_error": "", "msg": ""}
    if cat != old_cat or sub != old_sub:
        out["regen"] = True
        try:
            if cat != old_cat:  # t212u: 分类变了 → Strata 同时选子类和标签
                sub, got, proposed = strata_pick_subtype_tags(analyzed or "", topics, cat, sub, llm=llm)
                out["subtype"] = sub
            else:
                got, proposed = strata_pick_tags(analyzed or "", topics, cat, sub, llm=llm)
            if proposed:
                out["added"] = add_tags_to_topics(topics_path, cat, sub, proposed)
            if got:
                out["tags"] = tags = got
        except Exception as e:  # noqa: BLE001
            out["strata_error"] = str(e)
    if cat != old_cat:
        out["msg"] = move_item(list_path_fn(old_cat), list_path_fn(cat), key, cat, sub, tags, backup_dir)
        out["moved"] = True
    else:
        ok = update_item_in_place(list_path_fn(cat), key, cat, sub, tags, backup_dir)
        out["msg"] = "列表里这一行已更新" if ok else "列表里没找到这一行"
        out["found"] = ok
    return out
