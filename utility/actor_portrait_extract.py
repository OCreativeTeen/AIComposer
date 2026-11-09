"""从场景图提取人物肖像，并按粘贴肖像的同一路径关联到 actor。

t316u：用 Grok Image（和「修改图片 / 补全人物」相同的图生图路径）按人物描述
提取头部/肩部肖像；再用 Strata 看图审核。只有审核通过才关联。不改场景图。
已有肖像的人物跳过，绝不覆盖。

t319u：来源只用这一场自己的 clip_image。新项目播种时 clip_image 是封面的拷贝，
这种还没从封面提取出来的图（与冻结的封面原图 / 项目封面内容相同）一律不用，
也不退到 clip_image_last、zero 图或封面。人物身份 = 性别/年龄/国别/名字，括号不算。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile

STATUS_OK = "ok"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

STATUS_LABEL = {
    STATUS_OK: "成功",
    STATUS_REJECTED: "未通过审核",
    STATUS_FAILED: "提取失败",
    STATUS_SKIPPED: "已有肖像跳过",
}

DEFAULT_IMAGE_SLOT = "clip_image"
MIN_VERIFY_CONFIDENCE = 0.7

EXTRACT_PROMPT_INTRO = (
    "Extract a head-and-shoulders portrait of ONLY the person described below "
    "from Image 1 (the scene picture), and only if that person is clearly present."
)

VERIFY_SYSTEM = """You review a candidate character portrait against a written description and the original scene picture.
Return JSON only (no markdown, no extra text):
{"match":true,"reason":"short reason","confidence":0.86}

Set match=true ONLY if every point below is true:
- The portrait shows exactly one real-looking person (not empty, not several people, not a collage).
- Gender, age band, and nationality/ethnicity all match the description.
- Appearance notes (the text in parentheses: clothing, hair, face, distinctive features) are consistent when they describe how the person looks.
- The same person plausibly appears in the source scene image (face, hair and clothing correspond). If the scene has no such person, match MUST be false.
- The portrait was extracted from the scene, not invented to fit the text alone.

If anything is uncertain, or the portrait looks hallucinated, match MUST be false.
confidence is how sure you are of this verdict, from 0 to 1.
"""


def status_label(status: str) -> str:
    return STATUS_LABEL.get(str(status or ""), STATUS_LABEL[STATUS_FAILED])


def format_actor_result_line(row: dict) -> str:
    who = ((row.get("label") or "") + " " + (row.get("name") or row.get("body") or "")).strip()
    line = f"{who}：{status_label(row.get('status'))}"
    dest = row.get("dest") or ""
    if row.get("status") == STATUS_OK and dest:
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
    if not isinstance(scene, dict):
        return []
    preset = scene.get("actor_refs")
    if isinstance(preset, list):
        out = []
        for item in preset:
            if isinstance(item, dict) and item.get("body"):
                row = dict(item)
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
    for entry in project_manager.active_actor_entries(text):
        ref = actor_ref_from_entry(entry)
        if ref:
            rows.append(ref)
    return rows


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


def build_portrait_extract_prompt(actor: dict) -> str:
    """Prompt for Grok Image: extract head/shoulders only if the person is clearly in the scene."""
    return "\n".join([
        EXTRACT_PROMPT_INTRO,
        "",
        actor_description_text(actor),
        "",
        "Rules:",
        "- Extract only if this exact person is clearly present in Image 1.",
        "- Do not invent a face, do not substitute another person, and do not guess from the text alone.",
        "- Show the head and shoulders. Keep the real face, hair, age, gender presentation, and clothing from the scene.",
        "- Use a plain, neutral background. No extra people, scenery, props, or text.",
        "- If the person is not clearly in the picture, do not produce a portrait.",
    ])


def parse_verify_json(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    blob = fence.group(1) if fence else raw
    match = re.search(r"\{.*\}", blob, re.S)
    try:
        data = json.loads(match.group(0) if match else blob)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if "match" not in data:
        return None
    flag = data.get("match")
    if isinstance(flag, str):
        flag = flag.strip().lower() in ("1", "true", "yes", "y")
    else:
        flag = bool(flag)
    try:
        conf = float(data.get("confidence")) if data.get("confidence") is not None else None
    except (TypeError, ValueError):
        conf = None
    return {
        "match": flag,
        "reason": str(data.get("reason") or "").strip(),
        "confidence": conf,
    }


def verdict_accepts(verdict) -> bool:
    if not isinstance(verdict, dict):
        return False
    try:
        conf = float(verdict.get("confidence"))
    except (TypeError, ValueError):
        return False
    return bool(verdict.get("match")) and conf >= MIN_VERIFY_CONFIDENCE


def verify_portrait_with_strata(portrait_path: str, actor: dict, scene_image: str = "") -> dict | None:
    """Strata vision review of a Grok-returned portrait (optionally with the source scene)."""
    from utility.visual_remix import _chat, _image_data_url

    if not portrait_path or not os.path.isfile(portrait_path):
        return None
    parts = [
        {"type": "text", "text": (
            "Decide whether this portrait is the described person.\n"
            + actor_description_text(actor)
            + "\nImage 1 = the candidate portrait."
            + (" Image 2 = the source scene picture.\n" if scene_image and os.path.isfile(scene_image) else "\n")
        )},
        {"type": "image_url", "image_url": {"url": _image_data_url(portrait_path)}},
    ]
    if scene_image and os.path.isfile(scene_image) and os.path.normcase(scene_image) != os.path.normcase(portrait_path):
        parts.append({"type": "image_url", "image_url": {"url": _image_data_url(scene_image)}})
    out = _chat([{"role": "system", "content": VERIFY_SYSTEM}, {"role": "user", "content": parts}])
    return parse_verify_json(out)


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


def extract_actor_portraits(
    image_path: str,
    actors: list,
    avatar_dir: str = "",
    *,
    style: str = "",
    generate=None,
    verify=None,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> list:
    """For each actor without a portrait: Grok extract, then Strata verify, then associate.

    ``generate(image_path, actor, prompt)`` returns a file path or PIL image.
    ``verify(portrait_path, actor, scene_image)`` returns a verdict dict or raw JSON string.
    """
    portrait_path = portrait_path or _default_portrait_path
    portrait_dest = portrait_dest or _default_portrait_dest
    generate = generate or (lambda img, act, pr: generate_portrait_with_grok(img, act, pr, account=account))
    verify = verify or verify_portrait_with_strata
    results = []
    seen_ids = set()
    for actor in actors or []:
        if not isinstance(actor, dict) or not actor.get("body"):
            continue
        row = dict(actor)
        row["body"] = actor_identity(row.get("body") or "")
        ident = (row.get("role") or "person", row["body"])
        if not row["body"] or ident in seen_ids:
            continue
        seen_ids.add(ident)
        # 每次调 Grok 之前都重新检查（前面的场景或用户粘贴可能刚刚有了肖像）。
        existing = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if existing:
            row["status"] = STATUS_SKIPPED
            row["dest"] = existing
            results.append(row)
            continue
        dest = ""
        try:
            dest = portrait_dest(row.get("role") or "person", row.get("body") or "", avatar_dir, style) or ""
        except Exception:
            dest = ""
        if dest and os.path.isfile(dest):
            row["status"] = STATUS_SKIPPED
            row["dest"] = os.path.abspath(dest)
            results.append(row)
            continue
        if not image_path or not os.path.isfile(image_path):
            row["status"] = STATUS_FAILED
            row["dest"] = ""
            results.append(row)
            continue
        prompt = build_portrait_extract_prompt(row)
        raw_path = ""
        try:
            raw_path = _as_image_path(generate(image_path, row, prompt))
        except Exception:
            raw_path = ""
        if not raw_path:
            row["status"] = STATUS_FAILED
            row["dest"] = ""
            results.append(row)
            continue
        try:
            verdict = verify(raw_path, row, image_path)
        except Exception:
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_FAILED
            row["dest"] = ""
            results.append(row)
            continue
        if isinstance(verdict, str):
            verdict = parse_verify_json(verdict)
        if not isinstance(verdict, dict) or "match" not in verdict:
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_FAILED
            row["dest"] = ""
            results.append(row)
            continue
        if not verdict_accepts(verdict):
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_REJECTED
            row["dest"] = ""
            row["reason"] = (verdict or {}).get("reason") or ""
            results.append(row)
            continue
        concurrent = _has_portrait(row, avatar_dir, style, portrait_path, portrait_dest)
        if concurrent:  # 审核期间有人粘贴了肖像：不覆盖
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_SKIPPED
            row["dest"] = concurrent
            results.append(row)
            continue
        try:
            saved = _save_independent(raw_path, dest)
        except FileExistsError:
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_SKIPPED
            row["dest"] = os.path.abspath(dest)
            results.append(row)
            continue
        except Exception:
            _discard_temp(raw_path, image_path, dest)
            row["status"] = STATUS_FAILED
            row["dest"] = ""
            results.append(row)
            continue
        _discard_temp(raw_path, image_path, saved)
        row["status"] = STATUS_OK
        row["dest"] = saved
        results.append(row)
    return results


def extract_portraits_for_scene(
    scene,
    avatar_dir: str = "",
    *,
    covers=(),
    style: str = "",
    generate=None,
    verify=None,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> dict:
    """这一场：只用它自己的 clip_image，为还没有肖像的人物提取。

    返回 {"source", "results", "reason"}；没有可用的 clip_image（含封面拷贝）时 results 为空。
    """
    portrait_path = portrait_path or _default_portrait_path
    portrait_dest = portrait_dest or _default_portrait_dest
    actors = actors_from_scene(scene)
    missing = [a for a in actors if not _has_portrait(a, avatar_dir, style, portrait_path, portrait_dest)]
    if not missing:
        return {"source": "", "results": [], "reason": "all_have_portraits" if actors else "no_actors"}
    image = scene_clip_image_source(scene, covers)
    if not image:
        return {"source": "", "results": [], "reason": "no_scene_clip_image"}
    rows = extract_actor_portraits(
        image, missing, avatar_dir, style=style,
        generate=generate, verify=verify, account=account,
        portrait_path=portrait_path, portrait_dest=portrait_dest,
    )
    return {"source": image, "results": rows, "reason": ""}


def scan_scenes_for_portraits(
    scenes,
    avatar_dir: str = "",
    *,
    covers=(),
    style: str = "",
    generate=None,
    verify=None,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> dict:
    """按场景顺序逐场调用 extract_portraits_for_scene；所有已知人物都有肖像就停。"""
    portrait_path = portrait_path or _default_portrait_path
    portrait_dest = portrait_dest or _default_portrait_dest
    scenes = [s for s in (scenes or []) if isinstance(s, dict)]
    known = []
    seen = set()
    for scene in scenes:
        for actor in actors_from_scene(scene):
            key = actor.get("key") or ""
            if key and key not in seen:
                seen.add(key)
                known.append(actor)
    reports = []
    calls = {"grok": 0, "strata": 0}
    gen_fn = generate or (lambda img, act, pr: generate_portrait_with_grok(img, act, pr, account=account))
    ver_fn = verify or verify_portrait_with_strata

    def counted_generate(image, actor, prompt):
        calls["grok"] += 1
        return gen_fn(image, actor, prompt)

    def counted_verify(portrait, actor, scene_image):
        calls["strata"] += 1
        return ver_fn(portrait, actor, scene_image)

    def all_done() -> bool:
        return not any(not _has_portrait(a, avatar_dir, style, portrait_path, portrait_dest) for a in known)

    for scene in scenes:
        if all_done():
            break
        out = extract_portraits_for_scene(
            scene, avatar_dir, covers=covers, style=style,
            generate=counted_generate, verify=counted_verify, account=account,
            portrait_path=portrait_path, portrait_dest=portrait_dest,
        )
        reports.extend(out["results"])
    return {
        "results": reports,
        "grok_calls": calls["grok"],
        "strata_calls": calls["strata"],
        "actors": known,
    }
