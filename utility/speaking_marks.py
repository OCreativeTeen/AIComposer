"""Shared parser for speaking marks: <N> dialogue and <Ns> self-talk.

Lifecycle:
  - ``<N>`` is actor N speaking to someone (interactive dialogue).
  - ``<Ns>`` is the same actor N in self-talk / inner monologue (not a new person,
    and not a phantom speaker named ``s``).
  - Legacy ``<N>（自言自语）`` / ``<N>（自言自語）`` (half- or full-width parens)
    means the same as ``<Ns>``. New generated text should use ``<Ns>``.
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

# Matches <N>, <Ns>, ＜12s＞, and optional legacy monologue parenthesis after <N>.
SPEAKER_TOKEN_RE = re.compile(
    r"[<＜]\s*(\d+)\s*([sS])?\s*[>＞]"
    r"(?:\s*[（(]\s*自言自[语語]\s*[）)])?"
)

# Number-only view of a speaker token (includes <Ns>). Used to find actor ids.
SPEAKER_ID_RE = re.compile(r"[<＜]\s*(\d+)\s*[sS]?\s*[>＞]")

LEGACY_MONOLOGUE_PREFIX_RE = re.compile(r"^[（(]\s*自言自[语語]\s*[）)]\s*")
LEGACY_MONOLOGUE_ANY_RE = re.compile(r"[（(]\s*自言自[语語]\s*[）)]")

SCENE_MONOLOGUE_RULE = """
*** 自言自语 / self-talk（这一条优先于上面任何把独白写成「（自言自语）」或允许两端都独白的写法）
    ** 对白仍用 ``<N>``：N 是这一场 actor 里的第 N 个人。
    ** 自言自语 / 内心独白用 ``<Ns>``：还是同一个人 N，字母 s 只表示自言自语，不是新角色，也不要发明人物 s。
    ** 新生成的文本请写 ``<Ns>``，不要再写 ``（自言自语）`` / ``（自言自語）``。旧稿里的 ``<N>（自言自语）`` 或 ``<N>（自言自語）`` 含义相同。
    ** 自言自语只能出现在该场 speaking 的第一句（可连续几句）或最后一句（可连续几句），不能夹在中间，也不能同一场两端都有。
    ** 例：``<1s> 我怎麼又這樣。<2> 你今天怎麼這麼累？<1> 我也不知道。`` 或 ``<2> 先坐下。<1s> 原來我不是壞掉了。``
*** SELF-TALK / INNER MONOLOGUE
    ** Interactive lines use ``<N>``. Self-talk by that same person uses ``<Ns>`` (the letter s is a flag, not a speaker).
    ** Newly written text must use ``<Ns>``, not Chinese parenthetical labels.
    ** In one scene, self-talk may only be the first utterance(s) or the last utterance(s), never the middle and never both ends.
"""


@dataclass
class SpeechTurn:
    speaker: int
    text: str
    monologue: bool = False


def strip_monologue_tag(body: str) -> tuple:
    """Return (is_monologue, spoken_text). Tag must lead the chunk (legacy form)."""
    raw = str(body or "")
    m = LEGACY_MONOLOGUE_PREFIX_RE.match(raw.lstrip())
    if not m:
        return False, raw.strip()
    rest = raw.lstrip()[m.end():]
    return True, rest.strip()


def speaking_has_monologue(text: str) -> bool:
    """True when speaking uses ``<Ns>`` or legacy ``<N>（自言自语/語）``."""
    if not text:
        return False
    raw = str(text)
    for m in SPEAKER_TOKEN_RE.finditer(raw):
        if m.group(2) or ("自言自" in m.group(0)):
            return True
    if LEGACY_MONOLOGUE_ANY_RE.search(raw):
        return True
    return False


def strip_speaker_marks(text: str, *, pauses: bool = True) -> str:
    """Remove speaker / monologue marks (and optionally pause marks) so TTS does not read them."""
    out = str(text or "")
    if pauses:
        out = PAUSE_MARK_RE.sub(" ", out)
    out = SPEAKER_TOKEN_RE.sub(" ", out)
    out = LEGACY_MONOLOGUE_ANY_RE.sub(" ", out)
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

    Text before the first mark is speaker 1 (not monologue, unless it starts
    with a legacy monologue parenthesis). Pause marks stay inside the spoken
    text. Empty chunks are dropped.
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
        mono = bool(m.group(2)) or ("自言自" in m.group(0))
        pos = m.end()
    _append_turn(turns, who, raw[pos:], mono)
    return turns


def _append_turn(turns: list, who: int, chunk: str, token_mono: bool) -> None:
    tagged, cleaned = strip_monologue_tag(chunk)
    if not cleaned:
        return
    turns.append(SpeechTurn(int(who), cleaned, bool(token_mono or tagged)))


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


MONOLOGUE_SPLIT_KEY = "monologue_split"
MONOLOGUE_SPLIT_DONE = "done"


def scene_monologue_split_done(scene) -> bool:
    return isinstance(scene, dict) and scene.get(MONOLOGUE_SPLIT_KEY) == MONOLOGUE_SPLIT_DONE


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
