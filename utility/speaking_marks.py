"""Shared parser for speaking marks: <N> dialogue and <Ns> self-talk.

Lifecycle:
  - ``<N>`` is actor N speaking to someone (interactive dialogue).
  - ``<Ns>`` is the same actor N in self-talk / inner monologue (not a new person,
    and not a phantom speaker named ``s``). The letter must be lowercase ``s``.
  - Chinese parentheticals such as ``（自言自语）`` are ordinary spoken/written
    text, never control syntax and never a self-talk mark.
  - ``<0.5>``-style decimal marks are pauses, never speaker ids.

Self-talk may only occupy a contiguous block at the start or the end of a
scene's speaking (never the middle, never both ends) — generation prompts
still require that. A new project keeps the scene unsplit so image
generation or cover extraction runs once. After that image write succeeds,
a valid leading/trailing monologue scene is split into two consecutive
scenes (same authored fields except speaking). Interior / both-ends
layouts are left unchanged (no error). Already-split scenes and pure
monologue or dialogue do not split again.
"""
from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass

# Pause / beat: must contain a decimal point so it is not a speaker id.
PAUSE_MARK_RE = re.compile(r"[<＜]\s*\d+\.\d+\s*[>＞]")

# Matches <N> and <Ns> / ＜12s＞. Only lowercase s is the self-talk flag.
SPEAKER_TOKEN_RE = re.compile(r"[<＜]\s*(\d+)\s*(s)?\s*[>＞]")

# Number-only view of a speaker token (includes <Ns>). Used to find actor ids.
SPEAKER_ID_RE = re.compile(r"[<＜]\s*(\d+)\s*s?\s*[>＞]")

SCENE_MONOLOGUE_RULE = """
*** 自言自语 / self-talk
    ** 对白用 ``<N>``：N 是这一场 actor 里的第 N 个人。
    ** 自言自语 / 内心独白只用 ``<Ns>``：还是同一个人 N，小写字母 s 只表示自言自语，不是新角色，也不要发明人物 s。
    ** 自言自语只能出现在该场 speaking 的第一句（可连续几句）或最后一句（可连续几句），不能夹在中间，也不能同一场两端都有。
    ** 例：``<1s> 我怎麼又這樣。<2> 你今天怎麼這麼累？<1> 我也不知道。`` 或 ``<2> 先坐下。<1s> 原來我不是壞掉了。``
*** SELF-TALK / INNER MONOLOGUE
    ** Interactive lines use ``<N>``. Self-talk by that same person uses ``<Ns>`` (lowercase s is a flag, not a speaker).
    ** In one scene, self-talk may only be the first utterance(s) or the last utterance(s), never the middle and never both ends.
"""


@dataclass
class SpeechTurn:
    speaker: int
    text: str
    monologue: bool = False


def strip_monologue_tag(body: str) -> tuple:
    """Kept for existing callers (TTS cleanup).

    Self-talk is only ``<Ns>``, stripped by ``strip_speaker_marks`` / the
    speaking parser. Chinese parentheticals are left untouched as ordinary text.
    Always returns ``(False, stripped_text)``.
    """
    return False, str(body or "").strip()


def speaking_has_monologue(text: str) -> bool:
    """True when speaking uses a ``<Ns>`` mark (lowercase s only)."""
    if not text:
        return False
    return any(m.group(2) for m in SPEAKER_TOKEN_RE.finditer(str(text)))


def strip_speaker_marks(text: str, *, pauses: bool = True) -> str:
    """Remove speaker marks (and optionally pause marks) so TTS does not read them."""
    out = str(text or "")
    if pauses:
        out = PAUSE_MARK_RE.sub(" ", out)
    out = SPEAKER_TOKEN_RE.sub(" ", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def speaker_ids_in_text(text: str) -> list:
    """Actor ids referenced by ``<N>`` / ``<Ns>``, in first-seen order. Never yields ``s``."""
    used: list = []
    for m in SPEAKER_ID_RE.finditer(str(text or "")):
        n = int(m.group(1))
        if n not in used:
            used.append(n)
    return used


def parse_speaking_turns(text: str) -> list:
    """Split speaking into ``SpeechTurn`` values.

    Text before the first mark is speaker 1 (not self-talk). Pause marks stay
    inside the spoken text. Empty chunks are dropped. Only ``<Ns>`` sets
    ``monologue=True``.
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    turns: list[SpeechTurn] = []
    pos, who, mono = 0, 1, False
    for m in SPEAKER_TOKEN_RE.finditer(raw):
        chunk = raw[pos:m.start()]
        _append_turn(turns, who, chunk, mono)
        who = int(m.group(1))
        mono = bool(m.group(2))
        pos = m.end()
    _append_turn(turns, who, raw[pos:], mono)
    return turns


def _append_turn(turns: list, who: int, chunk: str, token_mono: bool) -> None:
    cleaned = str(chunk or "").strip()
    if not cleaned:
        return
    turns.append(SpeechTurn(int(who), cleaned, bool(token_mono)))


def format_speaking_turns(turns) -> str:
    """Rebuild speaking with canonical ``<N>`` / ``<Ns>`` marks."""
    parts = []
    for t in turns or []:
        text = str(getattr(t, "text", "") or "").strip()
        if not text:
            continue
        speaker = int(getattr(t, "speaker", 1) or 1)
        mark = f"<{speaker}s>" if getattr(t, "monologue", False) else f"<{speaker}>"
        parts.append(f"{mark} {text}")
    return " ".join(parts).strip()


def split_speaking_turns(text: str) -> list:
    """Compatibility helper: ``[(speaker, spoken_text), ...]`` with marks stripped."""
    return [(t.speaker, t.text) for t in parse_speaking_turns(text) if t.text]


def classify_monologue_layout(turns) -> str:
    """``none`` / ``all`` / ``prefix`` / ``suffix`` / ``invalid``."""
    flags = [bool(getattr(t, "monologue", False)) for t in (turns or []) if str(getattr(t, "text", "") or "").strip()]
    if not flags:
        return "none"
    if not any(flags):
        return "none"
    if all(flags):
        return "all"
    i = 0
    while i < len(flags) and flags[i]:
        i += 1
    j = len(flags) - 1
    while j >= 0 and flags[j]:
        j -= 1
    if i > 0 and not any(flags[i:]):
        return "prefix"
    if j < len(flags) - 1 and not any(flags[: j + 1]):
        return "suffix"
    return "invalid"


def split_speaking_pair(speaking: str):
    """If speaking should become two scenes, return (first, second, kind).

    kind is ``prefix`` (monologue first) or ``suffix`` (monologue second).
    Pure monologue, no monologue, or an unsplitable layout (interior,
    both ends, blank side) returns None so the caller keeps the original
    speaking string unchanged.
    """
    turns = parse_speaking_turns(speaking)
    kind = classify_monologue_layout(turns)
    if kind in ("none", "all", "invalid"):
        return None
    if kind == "prefix":
        i = 0
        while i < len(turns) and turns[i].monologue:
            i += 1
        mono, dialogue = turns[:i], turns[i:]
        first, second = format_speaking_turns(mono), format_speaking_turns(dialogue)
    else:
        j = len(turns) - 1
        while j >= 0 and turns[j].monologue:
            j -= 1
        dialogue, mono = turns[: j + 1], turns[j + 1 :]
        first, second = format_speaking_turns(dialogue), format_speaking_turns(mono)
    if not (first or "").strip() or not (second or "").strip():
        return None
    return first, second, kind


def speaking_turns_nonempty(speaking: str) -> list:
    """Parser turns that actually have spoken text (not punctuation-based sentences)."""
    return [t for t in parse_speaking_turns(speaking or "") if str(getattr(t, "text", "") or "").strip()]


def speaking_is_single_inner_monologue(speaking: str) -> bool:
    """Exactly one ``<Ns>`` self-talk turn — not several sentences inside it."""
    turns = speaking_turns_nonempty(speaking)
    return len(turns) == 1 and bool(getattr(turns[0], "monologue", False))


def speaking_is_all_inner_monologue(speaking: str) -> bool:
    turns = speaking_turns_nonempty(speaking)
    return bool(turns) and all(bool(getattr(t, "monologue", False)) for t in turns)


def speaking_has_interactive_dialogue(speaking: str) -> bool:
    return any(not bool(getattr(t, "monologue", False)) for t in speaking_turns_nonempty(speaking))


def scene_speaking_source(scene, *, allow_story_content: bool = False) -> str:
    """Speaking text used for video speaker-mark semantics.

    Always prefer the scene's own ``speaking`` field. Empty speaking means no
    speech for Story Speak (do not narrate visual or unmarked story_content).
    Fall back to ``story_content`` only when ``allow_story_content`` is true
    (Story Act box storage) AND that field itself contains speaker marks.
    """
    if not isinstance(scene, dict):
        return ""
    text = str(scene.get("speaking") or "").strip()
    if text:
        return text
    if not allow_story_content:
        return ""
    sc = str(scene.get("story_content") or "").strip()
    if sc and (SPEAKER_TOKEN_RE.search(sc) or speaking_has_monologue(sc)):
        return sc
    return ""


def scenes_speaking_is_single_inner_monologue(scenes) -> bool:
    """True when every scene that has speaking is a single inner-monologue turn.

    Mixed dialogue + self-talk, or more than one parser turn, returns False so
    the per-turn no-lip-sync fallback stays in effect.
    """
    found = False
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        text = scene_speaking_source(scene)
        if not text.strip():
            continue
        if not speaking_is_single_inner_monologue(text):
            return False
        found = True
    return found


MONOLOGUE_SPLIT_KEY = "monologue_split"
MONOLOGUE_SPLIT_DONE = "done"


def scene_monologue_split_done(scene) -> bool:
    return isinstance(scene, dict) and scene.get(MONOLOGUE_SPLIT_KEY) == MONOLOGUE_SPLIT_DONE


COVER_STEP_KEY = "cover_step"


def scene_cover_step(scene) -> int | None:
    """Original cover-panel / extract-step number (1-based), or None if missing."""
    if not isinstance(scene, dict):
        return None
    raw = scene.get(COVER_STEP_KEY)
    try:
        step = int(raw)
    except (TypeError, ValueError):
        return None
    return step if step >= 1 else None


def _norm_speaking(text: str) -> str:
    return format_speaking_turns(parse_speaking_turns(text or ""))


def authored_fields_match(left, right) -> bool:
    if not (isinstance(left, dict) and isinstance(right, dict)):
        return False
    for key in ("caption", "visual", "actor"):
        if (left.get(key) or "").strip() != (right.get(key) or "").strip():
            return False
    return True


def look_like_split_pair(first, second) -> bool:
    """True when two consecutive scenes unambiguously reconstruct one split."""
    if not (scene_monologue_split_done(first) and scene_monologue_split_done(second)):
        return False
    combo = ((_norm_speaking(first.get("speaking")) + " " + _norm_speaking(second.get("speaking"))).strip())
    pair = split_speaking_pair(combo)
    if not pair:
        pair = split_speaking_pair(((first.get("speaking") or "") + " " + (second.get("speaking") or "")).strip())
    if not pair:
        return False
    left, right, _kind = pair
    return _norm_speaking(first.get("speaking")) == _norm_speaking(left) and _norm_speaking(
        second.get("speaking")
    ) == _norm_speaking(right)


def _cover_groups(scenes):
    items = [s for s in (scenes or []) if isinstance(s, dict)]
    groups = []
    i = 0
    while i < len(items):
        nxt = items[i + 1] if i + 1 < len(items) else None
        if nxt is not None and look_like_split_pair(items[i], nxt):
            groups.append([items[i], nxt])
            i += 2
        else:
            groups.append([items[i]])
            i += 1
    return groups


def ensure_cover_steps(scenes) -> bool:
    """Persist original cover-step numbers. Returns True if any scene changed.

    Safe recovery for older projects: consecutive ``monologue_split=done``
    scenes whose speaking reconstructs a prefix/suffix pair share one step.
    Already-stamped values are kept. Does not invent a mapping when a lone
    marked scene cannot be paired.
    """
    if not isinstance(scenes, list):
        return False
    groups = _cover_groups(scenes)
    changed = False
    next_step = 1
    used = [scene_cover_step(s) for g in groups for s in g]
    stamped = [v for v in used if v]
    if stamped and all(scene_cover_step(s) for g in groups for s in g):
        return False
    for group in groups:
        existing = [scene_cover_step(s) for s in group]
        have = [v for v in existing if v]
        if have and len(set(have)) == 1:
            step = have[0]
        elif have:
            # Conflicting stamps inside an unambiguous pair: do not invent.
            continue
        else:
            while next_step in have or next_step in [scene_cover_step(s) for g in groups for s in g if scene_cover_step(s)]:
                next_step += 1
            step = next_step
            next_step += 1
        for scene in group:
            if scene_cover_step(scene) != step:
                scene[COVER_STEP_KEY] = step
                changed = True
    return changed


def unique_cover_step_count(scenes) -> int:
    ensure_cover_steps(scenes)
    seen = []
    for scene in scenes or []:
        step = scene_cover_step(scene)
        if step and step not in seen:
            seen.append(step)
    return len(seen)


def cover_step_sequence(scenes) -> list:
    ensure_cover_steps(scenes)
    return [scene_cover_step(s) for s in (scenes or []) if isinstance(s, dict)]


def should_share_cover_extract(primary, other) -> bool:
    if primary is other or not (isinstance(primary, dict) and isinstance(other, dict)):
        return False
    step_a, step_b = scene_cover_step(primary), scene_cover_step(other)
    if not step_a or step_a != step_b:
        return False
    if authored_fields_match(primary, other):
        return True
    return look_like_split_pair(primary, other) or look_like_split_pair(other, primary)


def iter_cover_extract_targets(scenes):
    """Yield ``(scene, step)`` once per original cover panel when siblings match.

    Later halves that only differ in speaking (same cover step, same authored
    caption/visual/actor or an unambiguous split pair) are skipped so batch
    extract does not spend a second image request on the same panel.
    """
    ensure_cover_steps(scenes)
    emitted = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        step = scene_cover_step(scene)
        if not step:
            continue
        prev = next((item for item in emitted if item[1] == step), None)
        if prev is not None and should_share_cover_extract(prev[0], scene):
            continue
        emitted.append((scene, step))
        yield scene, step


def sync_cover_step_partners(scenes, scene) -> list:
    """Copy settled authored stills/text to other scenes that share this cover step."""
    if not isinstance(scenes, list) or not isinstance(scene, dict):
        return []
    from utility.scene_image_slots import clone_image_slots

    updated = []
    for other in scenes:
        if not should_share_cover_extract(scene, other):
            continue
        for key in ("caption", "visual", "actor", "visual_before_remix", "actor_before_remix"):
            if key in scene:
                other[key] = scene[key]
        try:
            clone_image_slots(scene, other)
        except Exception as exc:
            print(f"⚠️ 同一步封面图没有同步到拆开的另一场：{exc}")
            continue
        updated.append(other)
    return updated


def index_after_monologue_insert(scenes, scene, current_index) -> int:
    try:
        current = int(current_index or 0)
    except (TypeError, ValueError):
        current = 0
    try:
        idx = next(i for i, item in enumerate(scenes or []) if item is scene)
    except StopIteration:
        return current
    if current > idx:
        return current + 1
    return current


def apply_monologue_split_after_image(scenes, scene, *, next_id=None):
    """After image write (and remix, when that runs) settle: maybe insert a sibling.

    ``scene`` stays the same object (batch jobs / callbacks keep their reference)
    and becomes the first half. A new dict is inserted immediately after it.
    Image slots on the sibling are independent file copies, including a new
    file for frozen ``zero_image_last``. Clip video/audio and speaking_timing
    are not copied onto the sibling (they belong to the unsplit speech).
    Returns the sibling, or None if no split happened. Failure to copy images
    leaves ``scenes`` and ``scene`` unchanged.
    """
    if not isinstance(scenes, list) or not isinstance(scene, dict):
        return None
    try:
        idx = next(i for i, item in enumerate(scenes) if item is scene)
    except StopIteration:
        return None
    if scene_monologue_split_done(scene):
        return None
    pair = split_speaking_pair(scene.get("speaking") or "")
    if not pair:
        return None
    from utility.scene_image_slots import COVER_SEED_SLOTS, clone_image_slots

    ensure_cover_steps(scenes)

    if not any(
        isinstance(scene.get(slot), str) and scene.get(slot) and os.path.isfile(scene[slot])
        for slot in COVER_SEED_SLOTS
    ):
        return None
    first_s, second_s, _kind = pair
    sibling = copy.deepcopy(scene)
    if next_id is None:
        ids = [int(s.get("id") or 0) for s in scenes if isinstance(s, dict)]
        base = max(ids) if ids else 0
        next_id = (int(base) // 100 + 1) * 100
        if next_id < 10000:
            next_id = 10000
    sibling["id"] = next_id
    if scene_cover_step(scene):
        sibling[COVER_STEP_KEY] = scene_cover_step(scene)
    sibling["speaking"] = second_s
    sibling.pop("speaking_timing", None)
    sibling.pop("clip", None)
    sibling.pop("clip_audio", None)
    try:
        clone_image_slots(scene, sibling)
    except Exception as exc:
        print(f"⚠️ 自言自语分场：没有独立拷贝场景图，保持一场：{exc}")
        return None
    # Drop unsplit speech A/V only after a valid split (clone succeeded).
    # Halves must not inherit or later receive the full-speech clip/audio.
    sibling[MONOLOGUE_SPLIT_KEY] = MONOLOGUE_SPLIT_DONE
    scene["speaking"] = first_s
    scene.pop("speaking_timing", None)
    scene.pop("clip", None)
    scene.pop("clip_audio", None)
    scene[MONOLOGUE_SPLIT_KEY] = MONOLOGUE_SPLIT_DONE
    scenes.insert(idx + 1, sibling)
    return sibling


def expand_scenes_for_new_project(scenes):
    """Speaking-only helper: deep-copy a list and split valid monologue scenes.

    Not used at project creation (images must run once on the unsplit scene).
    Kept for tests and any caller that only has scene dicts, no image files.
    Invalid layouts are copied verbatim.
    """
    if not isinstance(scenes, list):
        return scenes
    planned = []
    for item in scenes:
        if not isinstance(item, dict):
            planned.append(("keep", item, None))
            continue
        pair = split_speaking_pair(item.get("speaking") or "")
        planned.append(("split" if pair else "keep", item, pair))
    out = []
    for action, item, pair in planned:
        if action == "keep":
            out.append(copy.deepcopy(item) if isinstance(item, dict) else item)
            continue
        first_s, second_s, _kind = pair
        first = copy.deepcopy(item)
        second = copy.deepcopy(item)
        for sc, speaking in ((first, first_s), (second, second_s)):
            sc["speaking"] = speaking
            sc.pop("id", None)
            sc.pop("speaking_timing", None)
        out.extend([first, second])
    return out
