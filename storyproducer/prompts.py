"""Headless prompt builders — no SCENE window / clipboard bridge."""

from __future__ import annotations

import string
from typing import Any


def format_template(template: str, **kwargs: Any) -> str:
    names: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(template or ""):
        if not field_name:
            continue
        names.add(field_name.split("!")[0].split(":")[0].strip())
    safe = {k: kwargs.get(k, "") for k in names}
    return (template or "").format(**safe)


def lm_choices(channel_id: str) -> list[tuple[str, str]]:
    import config

    cfg = config.get_channel_config(channel_id) or {}
    out: list[tuple[str, str]] = []
    for item in cfg.get("scenes_prompt_choices") or []:
        if not item or len(item) < 2:
            continue
        lbl, tpl = str(item[0] or "").strip(), item[1]
        if (tpl or "").strip():
            out.append((lbl, str(tpl)))
    return out


def visual_style_choices() -> list[str]:
    import config

    return [str(x).strip() for x in (config.VISUAL_STYLE_OPTIONS or []) if str(x).strip()]


def narrator_choices() -> list[str]:
    import config

    opts = config.narrator_person_options() if hasattr(config, "narrator_person_options") else []
    if opts:
        return [str(x).strip() for x in opts if str(x).strip()]
    return [str(x).strip() for x in (config.CHARACTER_PERSON_OPTIONS or []) if str(x).strip()]


def match_choice(value: str, labels: list[str]) -> str:
    """Number (1-based) or exact / substring label match. Empty if no match."""
    raw = (value or "").strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if not raw or not labels:
        return ""
    if raw.isdigit():
        i = int(raw)
        if 1 <= i <= len(labels):
            return labels[i - 1]
        return ""
    low = raw.lower()
    for lab in labels:
        if lab.lower() == low:
            return lab
    hits = [lab for lab in labels if low in lab.lower()]
    return hits[0] if len(hits) == 1 else ""


def _topic_fields(video_detail: dict) -> tuple[str, str, str]:
    import project_manager

    vd = video_detail if isinstance(video_detail, dict) else {}
    cat = (vd.get("topic_category") or "").strip()
    sub = (vd.get("topic_subtype") or "").strip()
    prof = vd.get(getattr(project_manager, "PROJECT_PROFILE_KEY", "project_profile"))
    if isinstance(prof, dict):
        if not cat:
            cat = (prof.get("topic_category") or "").strip()
        if not sub:
            sub = (prof.get("topic_subtype") or "").strip()
    topic = f"{cat}-{sub}" if cat or sub else ""
    return cat, sub, topic


def _tags_text(video_detail: dict) -> str:
    vd = video_detail if isinstance(video_detail, dict) else {}
    tags_raw = vd.get("tags", "")
    if isinstance(tags_raw, list):
        return ", ".join(str(x) for x in tags_raw if str(x).strip())
    return str(tags_raw or "").strip()


def _story_title(video_detail: dict) -> str:
    import project_manager

    vd = video_detail if isinstance(video_detail, dict) else {}
    prof = vd.get(getattr(project_manager, "PROJECT_PROFILE_KEY", "project_profile"))
    if isinstance(prof, dict):
        t = (prof.get("video_title") or "").strip()
        if t:
            return t
    return (vd.get("title") or vd.get("video_title") or "").strip()


def build_gemini_prompt(
    video_detail: dict,
    *,
    channel_id: str,
    lm_label: str,
    visual_style: str = "",
    instruction: str = "",
    language: str = "tw",
) -> str:
    """Assemble the LM template used by scnge (``{content}`` = analyzed_content)."""
    import config

    rows = lm_choices(channel_id)
    template = ""
    sections = 1
    for i, (lbl, tpl) in enumerate(rows):
        if lbl == lm_label:
            template = tpl
            sections = i + 1
            break
    if not template:
        return ""
    vd = video_detail if isinstance(video_detail, dict) else {}
    _cat, _sub, topic = _topic_fields(vd)
    lang = config.llm_language_label(language) if hasattr(config, "llm_language_label") else language
    body = format_template(
        template,
        topic=topic,
        tags=_tags_text(vd),
        language=lang,
        story_title=_story_title(vd),
        content=(vd.get("analyzed_content") or "").strip(),
        link=(vd.get("url") or "").strip(),
        instruction=(instruction or "").strip(),
        sections=sections,
        visual_style=(visual_style or "").strip(),
    )
    vs = (visual_style or "").strip()
    if vs and vs.lower() not in body.lower():
        body = body.rstrip() + f"\n\nVisual_Style: {vs}\n"
    return body.strip()


def build_notebooklm_clipbody(
    video_detail: dict,
    *,
    mode: str,
    variant: str = "",
    visual_style: str = "",
    main_character: str = "",
    host_narrator: str = "",
    scene_index: int = -1,
) -> str:
    """Same clip body as SCENE ``nbp`` / ``scene_choice``, without Tk."""
    import config_prompt
    import project_manager

    scenes = video_detail.get("scene_content") if isinstance(video_detail, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scene_content 需要有效 JSON 数组")
    if scene_index >= 0:
        if scene_index >= len(scenes):
            raise ValueError(f"场景 {scene_index + 1} 超出范围（共 {len(scenes)}）")
        scenes = [scenes[scene_index]]
    vs = (visual_style or "").strip() or getattr(project_manager, "LAST_VISUAL_STYLE", "") or ""
    return config_prompt.build_notebooklm_gen_instruction_clipbody(
        mode=mode,
        variant=variant,
        video_detail=video_detail if isinstance(video_detail, dict) else {},
        scene_content=scenes,
        visual_style=vs,
        main_character=(main_character or "").strip(),
        host_narrator=(host_narrator or "").strip(),
    )


def build_grok_video_prompts(
    video_detail: dict,
    n: int,
    *,
    video_nb_index: int,
    visual_style: str = "",
    host_narrator: str = "",
) -> list[tuple[str, str]]:
    import config_prompt
    import project_manager

    idx = int(video_nb_index)
    base, var, short = config_prompt.grok_scene_video_nb_export(idx)
    tag = f"[{idx}] {short}"
    scenes = video_detail.get("scene_content") if isinstance(video_detail, dict) else None
    if not isinstance(scenes, list) or len(scenes) < n:
        raise RuntimeError(
            f"scene_content 需要至少 {n} 场，当前 "
            f"{len(scenes) if isinstance(scenes, list) else 0}。"
        )
    vs = (visual_style or "").strip() or getattr(project_manager, "LAST_VISUAL_STYLE", "") or ""
    out: list[tuple[str, str]] = []
    for i in range(n):
        actor = ""
        if isinstance(scenes[i], dict):
            actor = (scenes[i].get("actor") or "").strip()
        text = config_prompt.build_notebooklm_gen_instruction_clipbody(
            mode=base,
            variant=var,
            video_detail=video_detail if isinstance(video_detail, dict) else {},
            scene_content=[scenes[i]],
            visual_style=vs,
            main_character=actor,
            host_narrator=(host_narrator or "").strip(),
        ).strip()
        if len(text) < 12:
            raise RuntimeError(f"场景 {i + 1} video 提示词为空或太短（{base}/{var}）。")
        out.append((f"场景{i + 1} {tag}", text))
    return out
