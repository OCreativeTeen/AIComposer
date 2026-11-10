"""从场景图提取人物肖像，并按粘贴肖像的同一路径关联到 actor；由人在人物窗里看一眼确认。

t316u：用 Grok Image（和「修改图片 / 补全人物」相同的图生图路径）按人物描述提取头部/肩部肖像。
t319u：来源只用这一场自己的 clip_image。新项目播种时 clip_image 是封面的拷贝，
这种还没从封面提取出来的图（与冻结的封面原图 / 项目封面内容相同）一律不用，
也不退到 clip_image_last、zero 图或封面。人物身份 = 性别/年龄/国别/名字，括号不算。
t329u：去掉 Strata 审核。每一位人物（一位一位来）在人物窗（双击人物那个窗口）里给人看：
确认 = 留下并记为已确认（后面的场景不再问）；删除肖像 = 不要这张；取消 / Esc = 停止这次自动提取。
已有肖像：先给人看，不调 Grok；删掉了才用这一场的图重新提取一次。绝不在没有人按删除时覆盖肖像。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile

# review(actor, portrait_path, kind) 的返回值（kind = "existing" / "new"）
REVIEW_OK = "ok"  # 确认 / 关窗：留下
REVIEW_DELETED = "deleted"  # 删除肖像
REVIEW_STOP = "stop"  # 取消 / Esc：停止这次自动提取
REVIEW_IGNORED = "ignored"  # t343u 手动重新提取：忽略新图，原来的肖像（有的话）保持不变

STATUS_OK = "ok"  # 新提取的肖像，人确认了
STATUS_CONFIRMED = "confirmed"  # 已有肖像，人确认了（没调 Grok）
STATUS_DELETED = "deleted"  # 新提取的被人删了：这一场跳过这一位
STATUS_FAILED = "failed"  # Grok 没给图 / 保存失败
STATUS_SKIPPED = "skipped"  # 以前已确认：不再问
STATUS_EXISTING = "existing"  # 已有肖像（手动模式只做没有肖像的人）
STATUS_STOPPED = "stopped"  # 人按了取消 / Esc
STATUS_REPLACED = "replaced"  # t343u 手动重新提取：新图换上，原来的改名 .bakN 备份
STATUS_IGNORED = "ignored"  # t343u 手动重新提取：忽略新图，原来的保持
STATUS_NOT_SPEAKING = "not_speaking"  # t357u 这一场 actor 里有、但讲话里没有他的台词：不从这一场的图提取

STATUS_LABEL = {
    STATUS_OK: "成功（已确认）",
    STATUS_CONFIRMED: "已有肖像，已确认",
    STATUS_DELETED: "已删除，这一场跳过",
    STATUS_FAILED: "提取失败",
    STATUS_SKIPPED: "已确认过，跳过",
    STATUS_EXISTING: "已有肖像跳过",
    STATUS_STOPPED: "已停止",
    STATUS_REPLACED: "已换成新提取的肖像（原来的已备份 .bak）",
    STATUS_IGNORED: "已忽略新提取的，原来的肖像不变",
    STATUS_NOT_SPEAKING: "这一场没有讲话，跳过（在有他讲话的那一场提取）",
}

DEFAULT_IMAGE_SLOT = "clip_image"

EXTRACT_PROMPT_INTRO = (
    "Extract a head-and-shoulders character portrait of ONLY the person described below "
    "from Image 1 (the scene picture), and only if that person is clearly present. "
    "Draw it in exactly the same art style as Image 1."
)


def status_label(status: str) -> str:
    return STATUS_LABEL.get(str(status or ""), STATUS_LABEL[STATUS_FAILED])


def format_actor_result_line(row: dict) -> str:
    who = ((row.get("label") or "") + " " + (row.get("name") or row.get("body") or "")).strip()
    line = f"{who}：{status_label(row.get('status'))}"
    dest = row.get("dest") or ""
    if row.get("status") in (STATUS_OK, STATUS_REPLACED) and dest:
        line += f"（{os.path.basename(dest)}）"
    return line


_PAREN_TAIL = re.compile(r"[（(]([^）)]*)[）)]\s*$")


def actor_identity(body: str) -> str:
    """性别/年龄/国别/名字；去掉末尾括号（同 project_manager.split_actor_motion）。"""
    text = (body or "").strip()
    found = _PAREN_TAIL.search(text)
    return text[: found.start()].strip() if found else text


def _file_digest(path: str) -> tuple:
    try:
        with open(path, "rb") as fh:
            return os.path.getsize(path), hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None, None


def _same_content(a: str, b: str) -> bool:
    if not (a and b and os.path.isfile(a) and os.path.isfile(b)):
        return False
    if os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)):
        return True
    size_a, hash_a = _file_digest(a)
    size_b, hash_b = _file_digest(b)
    return size_a is not None and size_a == size_b and hash_a == hash_b


def clip_image_is_cover_copy(scene, covers=()) -> bool:
    """clip_image 还是播种时的封面拷贝：与冻结的封面原图或任一项目封面内容相同。"""
    if not isinstance(scene, dict):
        return False
    clip = scene.get(DEFAULT_IMAGE_SLOT) or ""
    if not (isinstance(clip, str) and clip and os.path.isfile(clip)):
        return False
    frozen = scene.get("zero_image_last") or ""
    if scene.get("cover_origin") == "cover" and isinstance(frozen, str) and _same_content(clip, frozen):
        return True
    return any(isinstance(c, str) and _same_content(clip, c) for c in (covers or ()))


def scene_clip_image_source(scene, covers=()) -> str:
    """这一场自己的 clip_image；没有、或还是封面拷贝 → ""。不退到其它图或封面。"""
    if not isinstance(scene, dict):
        return ""
    path = scene.get(DEFAULT_IMAGE_SLOT) or ""
    if not (isinstance(path, str) and path and os.path.isfile(path)):
        return ""
    if clip_image_is_cover_copy(scene, covers):
        return ""
    return os.path.abspath(path)


def actor_ref_from_entry(entry) -> dict | None:
    if not isinstance(entry, dict):
        return None
    import project_manager

    body, motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
    body = (body or "").strip()
    if not body or project_manager.actor_is_absent(body):
        return None
    role = "host" if entry.get("role") == "host" else "person"
    bits = [p.strip() for p in body.split("/") if p.strip()]
    gender = bits[0].lower() if bits and bits[0].lower() in ("man", "woman") else ""
    age = bits[1] if len(bits) > 1 else ""
    nationality = bits[2] if len(bits) > 2 else ""
    name = bits[3] if len(bits) > 3 else (bits[-1] if bits else body)
    label = "讲员" if role == "host" else (entry.get("label") or "人物")
    return {
        "role": role,
        "body": body,
        "label": label,
        "note": (motion or "").strip(),
        "gender": gender,
        "age": age,
        "nationality": nationality,
        "name": name,
        "key": f"{role}:{body}",
    }


def actors_from_scene(scene) -> list:
    """这一场 actor 栏里的人（含讲员），按顺序。每行带 ``slot``：在 actor 栏的第几位（从 1 起），
    就是讲话里 ``<N>`` / ``<Ns>`` 的 N。"""
    if not isinstance(scene, dict):
        return []
    preset = scene.get("actor_refs")
    if isinstance(preset, list):
        out = []
        for pos, item in enumerate(preset, 1):
            if isinstance(item, dict) and item.get("body"):
                row = dict(item)
                row.setdefault("slot", pos)
                raw = str(row["body"])
                row["body"] = actor_identity(raw)
                if not row.get("note") and row["body"] != raw.strip():
                    row["note"] = raw.strip()[len(row["body"]):].strip("（）() ")
                row.setdefault("role", "person")
                row.setdefault("label", "人物")
                row.setdefault("name", row["body"].split("/")[-1])
                row["key"] = f"{row['role']}:{row['body']}"
                out.append(row)
        return out
    import project_manager

    text = project_manager.actor_text_for_generation(scene.get("actor") or "")
    rows = []
    for pos, entry in enumerate(project_manager.active_actor_entries(text), 1):
        ref = actor_ref_from_entry(entry)
        if ref:
            ref["slot"] = pos
            rows.append(ref)
    return rows


def speaking_actor_slots(scene, n_actors: int = 0) -> set:
    """t357u: 这一场讲话里有台词的人（actor 栏第几位）。

    用 ``speaking_marks.parse_speaking_turns``：``<N>`` / ``<Ns>``（自言自语还是第 N 个人）；
    没有任何标记的讲话、或第一个标记之前的话，按 app 一贯的规矩算第 1 个人（同 ``_speaker_slots``）。
    讲话空 → 空集合。编号超出人数时和 ``config_prompt.h3_speaker_map`` 一样，按出现的编号顺序对到第 1、2… 位。
    """
    from utility.speaking_marks import parse_speaking_turns, scene_speaking_source

    text = scene_speaking_source(scene, allow_story_content=True) if isinstance(scene, dict) else ""
    labels = sorted({int(t.speaker) for t in parse_speaking_turns(text) if str(t.text or "").strip()})
    n = int(n_actors or 0)
    if n and labels and any(not (1 <= k <= n) for k in labels) and len(labels) <= n:
        return set(range(1, len(labels) + 1))
    return set(labels)


def split_actors_by_speaking(scene) -> tuple:
    """t357u: (要提取的, 不提取的)，都是去重后的项目人物（不含讲员）。

    要提取 = 在这一场 actor 栏里（人物1/人物2…）**并且**讲话里有他的台词。同一个人在 actor 栏出现两次时，
    任何一次有台词都算。没有 slot 的行（老数据）不作限制，照旧提取。
    """
    actors = actors_from_scene(scene)
    slots = speaking_actor_slots(scene, len(actors))
    speaking_keys = set()
    for a in actors:
        slot = a.get("slot")
        if slot is None or int(slot) in slots:
            speaking_keys.add(confirm_key(dict(a, body=actor_identity(a.get("body") or ""))))
    rows = _dedupe_actors(actors)
    return ([r for r in rows if r["key"] in speaking_keys], [r for r in rows if r["key"] not in speaking_keys])


def actor_description_text(actor: dict) -> str:
    """Gender / age / nationality / name / parenthesis appearance — used in both prompts."""
    actor = actor or {}
    lines = [
        f"Portrait id: {actor.get('body') or ''}",
        f"Gender: {actor.get('gender') or ''}",
        f"Age: {actor.get('age') or ''}",
        f"Nationality/ethnicity: {actor.get('nationality') or ''}",
        f"Name: {actor.get('name') or ''}",
        f"Appearance description: {actor.get('note') or '(none)'}",
    ]
    return "\n".join(lines)


def build_portrait_extract_prompt(actor: dict, style: str = "") -> str:
    """Prompt for Grok Image: extract head/shoulders only if the person is clearly in the scene.

    t373u: 第一条 = 项目画风锁定（``style`` = 项目画面风格，例「三维卡通 (Pixar-Art-Cartoon)」）。
    以前这里一个字没提画风，还写了 "real face" / "plain, neutral background"，三维卡通的人被画成了真人照片。"""
    from config_prompt import image_art_style_lock_rule

    return "\n".join([
        image_art_style_lock_rule(style, "Image 1"),
        "",
        EXTRACT_PROMPT_INTRO,
        "",
        actor_description_text(actor),
        "",
        "Rules:",
        "- Extract only if this exact person is clearly present in Image 1.",
        "- Do not invent a face, do not substitute another person, and do not guess from the text alone.",
        "- Show the head and shoulders. Keep the same face, hair, age, gender presentation, and clothing as in the "
        "scene, drawn the way Image 1 draws them (same art style, same character design).",
        "- Use a plain, simple background in the same art style. No extra people, scenery, props, or text.",
        "- If the person is not clearly in the picture, do not produce a portrait.",
    ])


def generate_portrait_with_grok(image_path: str, actor: dict, prompt: str, *, account: str = "") -> str:
    """Grok Image edit: scene image + extract prompt → temporary PNG path (or "")."""
    from utility import chrome_account
    from utility import grok_cdp

    if not image_path or not os.path.isfile(image_path):
        return ""
    with chrome_account.use(account):
        img = grok_cdp.make_image(prompt, [image_path])
    if img is None or not hasattr(img, "save"):
        return ""
    handle, dest = tempfile.mkstemp(prefix="actor_portrait_", suffix=".png")
    os.close(handle)
    try:
        img.save(dest, "PNG")
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    return dest


def _default_portrait_path(role, name, avatar_dir="", style=None):
    from utility.content_pdf import actor_portrait_path

    return actor_portrait_path(role, name, avatar_dir, style)


def _default_portrait_dest(role, name, avatar_dir="", style=None):
    from utility.content_pdf import actor_portrait_dest

    return actor_portrait_dest(role, name, avatar_dir, style)


def _has_portrait(actor, avatar_dir, style, portrait_path, portrait_dest) -> str:
    found = ""
    try:
        found = portrait_path(actor.get("role") or "person", actor.get("body") or "", avatar_dir, style) or ""
    except Exception:
        found = ""
    if found and os.path.isfile(found):
        return os.path.abspath(found)
    try:
        dest = portrait_dest(actor.get("role") or "person", actor.get("body") or "", avatar_dir, style) or ""
    except Exception:
        dest = ""
    if dest and os.path.isfile(dest):
        return os.path.abspath(dest)
    return ""


def _as_image_path(raw) -> str:
    if isinstance(raw, str) and raw and os.path.isfile(raw):
        return os.path.abspath(raw)
    if raw is not None and hasattr(raw, "save"):
        handle, dest = tempfile.mkstemp(prefix="actor_portrait_", suffix=".png")
        os.close(handle)
        raw.save(dest, "PNG")
        return dest
    return ""


def _discard_temp(path: str, *protected: str) -> None:
    if not path or not os.path.isfile(path):
        return
    name = os.path.basename(path)
    if not name.startswith("actor_portrait_"):
        return
    skip = {os.path.normcase(os.path.abspath(p)) for p in protected if p}
    if os.path.normcase(os.path.abspath(path)) in skip:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _save_independent(src: str, dest: str) -> str:
    if not dest:
        raise ValueError("没有肖像保存路径")
    if os.path.isfile(dest):
        raise FileExistsError(dest)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    try:
        from PIL import Image

        im = Image.open(src)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.save(dest, "PNG")
    except Exception:
        shutil.copy2(src, dest)
    return os.path.abspath(dest)


def confirm_key(actor: dict) -> str:
    """已确认表里的键：角色 + 身份（性别/年龄/国别/名字，括号不算）。"""
    actor = actor or {}
    return f"{actor.get('role') or 'person'}:{actor_identity(actor.get('body') or '')}"


def remove_portrait_files(actor, avatar_dir="", style="", portrait_path=None, portrait_dest=None, limit: int = 8) -> list:
    """删掉这一位关联的肖像（人物窗看到的那张、粘贴写的那张）：改名成 <名>.bakN.<扩展名>，可找回。

    一层一层删，直到同一查找再也找不到（最多 ``limit`` 张）。返回改过名的原路径。"""
    portrait_path = portrait_path or _default_portrait_path
    portrait_dest = portrait_dest or _default_portrait_dest
    removed = []
    for _ in range(max(1, int(limit))):
        found = _has_portrait(actor, avatar_dir, style, portrait_path, portrait_dest)
        if not found or found in removed:
            break
        backup_portrait_file(found)
        removed.append(found)
    return removed


def backup_portrait_file(path: str) -> str:
    """同人物窗粘贴前的备份：<名>.bakN.<扩展名>。返回备份路径（没有文件就返回 ""）。"""
    if not path or not os.path.isfile(path):
        return ""
    folder, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    n = 1
    while True:
        bak = os.path.join(folder, f"{stem}.bak{n}{ext}")
        if not os.path.exists(bak):
            os.replace(path, bak)
            return bak
        n += 1


# 只审项目人物：讲员的肖像在共用的讲员头像库（固定名单），不在这里提取、也不在这里删。
REVIEW_ROLES = ("person",)


def _dedupe_actors(actors, roles=REVIEW_ROLES) -> list:
    out, seen = [], set()
    for actor in actors or []:
        if not isinstance(actor, dict) or not actor.get("body"):
            continue
        if roles and (actor.get("role") or "person") not in roles:
            continue
        row = dict(actor)
        row["body"] = actor_identity(row.get("body") or "")
        key = confirm_key(row)
        if not row["body"] or key in seen:
            continue
        seen.add(key)
        row["key"] = key
        out.append(row)
    return out


def all_actors_confirmed(scenes, confirmed) -> bool:
    """这些场景里**有讲话**的每一位人物都确认过了（t357u：不讲话的人不在这一场提取，也不等他）。没有人物也算。"""
    confirmed = confirmed if confirmed is not None else set()
    for scene in scenes or []:
        for actor in split_actors_by_speaking(scene)[0]:
            if actor["key"] not in confirmed:
                return False
    return True


def review_portraits_for_scene(
    scene,
    avatar_dir: str = "",
    *,
    covers=(),
    style: str = "",
    generate=None,
    review=None,
    remove=None,
    confirmed=None,
    existing: str = "review",
    stop_on_failure: bool = True,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> dict:
    """这一场的人物一位一位来（只用这一场自己的 clip_image，不用封面）。

    - 已确认过（``confirmed`` 里有）：跳过。
    - 已有肖像：``existing="review"`` 时不调 Grok，先 ``review(actor, path, "existing")``；
      确认 → 记为已确认；删除 → 删掉后用这一场的图调一次 Grok，再给人看；取消 → 停止。
      ``existing="skip"``：已有肖像的人不动。
    ``existing="replace"``（t343u 手动「提取人物肖像」）：见 ``_reextract_one``——每一位都调 Grok 重新提取。
    - 没有肖像：调一次 Grok；拿到图就按粘贴的路径关联，再 ``review(actor, path, "new")``：
      确认 → 留下并记为已确认；删除 → 删掉，这一场跳过这一位；取消 → 留下（不记确认）并停止。
    - Grok 失败 / 没给图：不开窗；``stop_on_failure`` 时这一场剩下的人也跳过（下一场再试）。

    ``review`` 返回 REVIEW_OK / REVIEW_DELETED / REVIEW_STOP（None 当作 OK）。
    返回 {"source", "results", "reason", "stopped", "grok_calls"}。
    """
    portrait_path = portrait_path or _default_portrait_path
    portrait_dest = portrait_dest or _default_portrait_dest
    generate = generate or (lambda img, act, pr: generate_portrait_with_grok(img, act, pr, account=account))
    review = review or (lambda actor, path, kind: REVIEW_OK)
    confirmed = confirmed if confirmed is not None else set()

    def _remove(actor):
        if remove is not None:
            remove(actor)
        if _has_portrait(actor, avatar_dir, style, portrait_path, portrait_dest):
            remove_portrait_files(actor, avatar_dir, style, portrait_path, portrait_dest)

    # t357u: 只提取 actor 栏里有、并且这一场讲话里有他台词的人；其余的人记一行「这一场没有讲话，跳过」
    actors, silent = split_actors_by_speaking(scene)
    out = {"source": "", "results": [], "reason": "", "stopped": False, "grok_calls": 0}
    silent_rows = [dict(a, status=STATUS_NOT_SPEAKING, dest="") for a in silent]
    if not actors:
        out["reason"] = "no_speaking_actors" if silent else "no_actors"
        out["results"] = silent_rows
        return out
    todo = [a for a in actors if a["key"] not in confirmed]
    if not todo:
        out["reason"] = "all_confirmed"
        out["results"] = [dict(a, status=STATUS_SKIPPED, dest="") for a in actors] + silent_rows
        return out
    image = scene_clip_image_source(scene, covers)
    if not image:
        out["reason"] = "no_scene_clip_image"
        return out
    out["source"] = image
    results = out["results"]
    for row in actors:
        if row["key"] in confirmed:
            results.append(dict(row, status=STATUS_SKIPPED, dest=""))
            continue
        if existing == "replace":
            out["grok_calls"] += 1
            res = _reextract_one(row, image, avatar_dir, style, generate, review, remove, portrait_path, portrait_dest)
            if res.get("status") in (STATUS_OK, STATUS_REPLACED):
                confirmed.add(row["key"])
            results.append(res)
            if res.get("status") == STATUS_STOPPED:
                out["stopped"] = True
                break
            continue
        found = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if found:
            if existing == "skip":
                results.append(dict(row, status=STATUS_EXISTING, dest=found))
                continue
            answer = review(row, found, "existing") or REVIEW_OK
            if answer == REVIEW_STOP:
                results.append(dict(row, status=STATUS_STOPPED, dest=found))
                out["stopped"] = True
                break
            if answer != REVIEW_DELETED:
                confirmed.add(row["key"])
                results.append(dict(row, status=STATUS_CONFIRMED, dest=found))
                continue
            _remove(row)
            if _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest):
                results.append(dict(row, status=STATUS_FAILED, dest="", reason="没删掉"))
                continue
        # 调 Grok 之前再查一次：刚刚有人粘贴了就不调、不覆盖。
        again = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if again:
            results.append(dict(row, status=STATUS_EXISTING, dest=again))
            continue
        try:
            dest = portrait_dest(row.get("role") or "person", row.get("body") or "", avatar_dir, style) or ""
        except Exception:
            dest = ""
        out["grok_calls"] += 1
        raw_path = ""
        try:
            raw_path = _as_image_path(generate(image, row, build_portrait_extract_prompt(row, style)))
        except Exception:
            raw_path = ""
        if not raw_path or not dest:
            _discard_temp(raw_path, image, dest)
            results.append(dict(row, status=STATUS_FAILED, dest=""))
            if stop_on_failure:
                break
            continue
        if _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest):  # Grok 期间有人粘贴了：不覆盖
            _discard_temp(raw_path, image, dest)
            results.append(dict(row, status=STATUS_EXISTING, dest=_has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)))
            continue
        try:
            saved = _save_independent(raw_path, dest)
        except Exception:
            _discard_temp(raw_path, image, dest)
            results.append(dict(row, status=STATUS_FAILED, dest=""))
            if stop_on_failure:
                break
            continue
        _discard_temp(raw_path, image, saved)
        answer = review(row, saved, "new") or REVIEW_OK
        if answer == REVIEW_DELETED:
            _remove(row)
            results.append(dict(row, status=STATUS_DELETED, dest=""))
            continue
        if answer == REVIEW_STOP:
            results.append(dict(row, status=STATUS_STOPPED, dest=saved))
            out["stopped"] = True
            break
        confirmed.add(row["key"])
        results.append(dict(row, status=STATUS_OK, dest=saved))
    results.extend(silent_rows)  # t357u: 不讲话的人放在最后，每人一行跳过原因
    return out


def _restore_backups(backups) -> None:
    """把 .bakN 改回原名（原名已被别人占了就留着备份，不覆盖）。"""
    for orig, bak in reversed(backups or []):
        if bak and os.path.isfile(bak) and not os.path.exists(orig):
            try:
                os.replace(bak, orig)
            except OSError:
                pass


def _reextract_one(row, image, avatar_dir, style, generate, review, remove, portrait_path, portrait_dest) -> dict:
    """t343u 手动「提取人物肖像」：不管有没有肖像，都用这一场的 clip_image 调一次 Grok。

    - Grok 失败：原来的肖像一点不动。
    - 拿到图：原来显示的那张先改名 .bakN（同删除肖像），新图存到粘贴路径，``review(actor, path, "replace")``：
      确认 → 新图留下（旧的留在 .bakN）；忽略 → 删掉新图、把旧的改回原名（原来没有就什么都不留）；
      删除肖像 → 新图也改名 .bakN，这一位没有肖像（两张都在备份里）；停止 → 同忽略，并停止后面的人。
    """
    try:
        dest = portrait_dest(row.get("role") or "person", row.get("body") or "", avatar_dir, style) or ""
    except Exception:
        dest = ""
    raw_path = ""
    try:
        raw_path = _as_image_path(generate(image, row, build_portrait_extract_prompt(row, style)))
    except Exception:
        raw_path = ""
    if not raw_path or not dest:
        _discard_temp(raw_path, image, dest)
        return dict(row, status=STATUS_FAILED, dest="")
    backups = []
    try:
        # 只备份显示的那张，以及占着粘贴路径的那张（下层共用的故事肖像不动）
        found = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if found:
            backups.append((found, backup_portrait_file(found)))
        if os.path.isfile(dest):
            backups.append((os.path.abspath(dest), backup_portrait_file(dest)))
        saved = _save_independent(raw_path, dest)
        shown = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if os.path.normcase(shown) != os.path.normcase(os.path.abspath(saved)):
            os.remove(saved)
            raise RuntimeError(f"新肖像存了但显示的不是它：{shown}")
    except Exception:
        _discard_temp(raw_path, image, dest)
        _restore_backups(backups)
        return dict(row, status=STATUS_FAILED, dest="")
    _discard_temp(raw_path, image, saved)
    answer = review(row, saved, "replace") or REVIEW_OK
    if answer in (REVIEW_IGNORED, REVIEW_STOP):
        try:
            if os.path.isfile(saved):
                os.remove(saved)
        except OSError:
            pass
        _restore_backups(backups)
        kept = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        return dict(row, status=STATUS_STOPPED if answer == REVIEW_STOP else STATUS_IGNORED, dest=kept)
    if answer == REVIEW_DELETED:
        if remove is not None:
            remove(row)
        if _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest):
            remove_portrait_files(row, avatar_dir, style, portrait_path, portrait_dest)
        return dict(row, status=STATUS_DELETED, dest="")
    return dict(row, status=STATUS_REPLACED if backups else STATUS_OK, dest=saved)


def scan_scenes_for_portraits(
    scenes,
    avatar_dir: str = "",
    *,
    covers=(),
    style: str = "",
    generate=None,
    review=None,
    remove=None,
    confirmed=None,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> dict:
    """按场景顺序逐场 review_portraits_for_scene；人按了停止、或所有人物都确认了就停。"""
    scenes = [s for s in (scenes or []) if isinstance(s, dict)]
    confirmed = confirmed if confirmed is not None else set()
    reports, calls, stopped = [], 0, False
    for scene in scenes:
        if all_actors_confirmed(scenes, confirmed):
            break
        out = review_portraits_for_scene(
            scene, avatar_dir, covers=covers, style=style, generate=generate, review=review, remove=remove,
            confirmed=confirmed, account=account, portrait_path=portrait_path, portrait_dest=portrait_dest,
        )
        reports.extend(out["results"])
        calls += out["grok_calls"]
        if out["stopped"]:
            stopped = True
            break
    return {"results": reports, "grok_calls": calls, "stopped": stopped, "confirmed": confirmed}
