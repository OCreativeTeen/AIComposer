"""从场景图提取人物肖像，并按粘贴肖像的同一路径关联到 actor。

t316u：用 Grok Image（和「修改图片 / 补全人物」相同的图生图路径）按人物描述
提取头部/肩部肖像；再用 Strata 看图审核。只有审核通过才关联。不改场景图。
已有肖像的人物跳过，绝不覆盖。
"""
from __future__ import annotations

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


def scene_portrait_source(scene, slot: str = DEFAULT_IMAGE_SLOT) -> str:
    """Current/primary scene still used for extraction: chosen slot, default clip_image."""
    if not isinstance(scene, dict):
        return ""
    keys = []
    chosen = str(slot or DEFAULT_IMAGE_SLOT).strip() or DEFAULT_IMAGE_SLOT
    keys.append(chosen)
    for extra in (DEFAULT_IMAGE_SLOT, "clip_image_last"):
        if extra not in keys:
            keys.append(extra)
    for key in keys:
        path = scene.get(key) or ""
        if isinstance(path, str) and path and os.path.isfile(path):
            return os.path.abspath(path)
    return ""


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
                row.setdefault("role", "person")
                row.setdefault("label", "人物")
                row.setdefault("name", row["body"].split("/")[-1])
                row.setdefault("key", f"{row['role']}:{row['body']}")
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
    for actor in actors or []:
        if not isinstance(actor, dict) or not actor.get("body"):
            continue
        row = dict(actor)
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
        try:
            saved = _save_independent(raw_path, dest)
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


def scan_scenes_for_portraits(
    scenes,
    avatar_dir: str = "",
    *,
    style: str = "",
    slot: str = DEFAULT_IMAGE_SLOT,
    generate=None,
    verify=None,
    account: str = "",
    portrait_path=None,
    portrait_dest=None,
) -> dict:
    """Walk scenes in order; Grok+Strata for missing portraits; stop when every known actor has one."""
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
    grok_calls = 0
    strata_calls = 0

    def counted_generate(image, actor, prompt, _gen=generate):
        nonlocal grok_calls
        grok_calls += 1
        fn = _gen or (lambda img, act, pr: generate_portrait_with_grok(img, act, pr, account=account))
        return fn(image, actor, prompt)

    def counted_verify(portrait, actor, scene_image, _ver=verify):
        nonlocal strata_calls
        strata_calls += 1
        fn = _ver or verify_portrait_with_strata
        return fn(portrait, actor, scene_image)

    for scene in scenes:
        if not any(not _has_portrait(a, avatar_dir, style, portrait_path, portrait_dest) for a in known):
            break
        missing_here = [
            actor for actor in actors_from_scene(scene)
            if not _has_portrait(actor, avatar_dir, style, portrait_path, portrait_dest)
        ]
        if not missing_here:
            continue
        image = scene_portrait_source(scene, slot)
        if not image:
            continue
        batch = extract_actor_portraits(
            image, missing_here, avatar_dir, style=style,
            generate=counted_generate, verify=counted_verify, account=account,
            portrait_path=portrait_path, portrait_dest=portrait_dest,
        )
        reports.extend(batch)
        if not any(not _has_portrait(a, avatar_dir, style, portrait_path, portrait_dest) for a in known):
            break
    return {
        "results": reports,
        "grok_calls": grok_calls,
        "strata_calls": strata_calls,
        "actors": known,
    }
