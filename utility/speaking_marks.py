"""Shared parser for speaking marks: <N> dialogue and <Ns> self-talk.

Lifecycle:
  - ``<N>`` is actor N speaking to someone (interactive dialogue).
  - ``<Ns>`` is the same actor N in self-talk / inner monologue (not a new person,
    and not a phantom speaker named ``s``). The letter must be lowercase ``s``.
  - Chinese parentheticals such as ``（自言自语）`` are ordinary spoken/written
    text, never control syntax and never a self-talk mark.
  - ``<0.5>``-style decimal marks are pauses, never speaker ids.

Self-talk is generation-time only: a scene is never split into two scenes
because of ``<Ns>`` (t373u removed the old split-after-image path completely). At video time, ``<Ns>`` runs and manual
``<s>`` marks become segments generated one by one (utility/video_segments.py).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

# Pause / beat: must contain a decimal point so it is not a speaker id.
PAUSE_MARK_RE = re.compile(r"[<＜]\s*\d+\.\d+\s*[>＞]")

# Matches <N> and <Ns> / ＜12s＞. Only lowercase s is the self-talk flag.
SPEAKER_TOKEN_RE = re.compile(r"[<＜]\s*(\d+)\s*(s)?\s*[>＞]")

# Number-only view of a speaker token (includes <Ns>). Used to find actor ids.
SPEAKER_ID_RE = re.compile(r"[<＜]\s*(\d+)\s*s?\s*[>＞]")

# t370u: 手工分节符 ``<s>``（没有数字）。加在某个 ``<n>`` 前面 = 从这一句起是新的一节；
# 生场视频时按节一节一节生成。它不是说话人，不读出来，也不进视频提示词。
SEGMENT_MARK_RE = re.compile(r"[<＜]\s*[sS]\s*[>＞]")

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
    # t370u: a manual ``<s>`` segment mark sits right before this turn.
    cut_before: bool = False


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
    out = SEGMENT_MARK_RE.sub(" ", out)  # t370u: <s> is a boundary, never spoken
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
    pos, who, mono, cut = 0, 1, False, False
    for m in SPEAKER_TOKEN_RE.finditer(raw):
        chunk = raw[pos:m.start()]
        cut = _append_chunk(turns, who, chunk, mono, cut)
        who = int(m.group(1))
        mono = bool(m.group(2))
        pos = m.end()
    _append_chunk(turns, who, raw[pos:], mono, cut)
    if turns:
        turns[0].cut_before = False  # a mark before the first line splits nothing
    return turns


def _append_chunk(turns: list, who: int, chunk: str, mono: bool, cut: bool) -> bool:
    """t370u: one speaker chunk; ``<s>`` inside it starts a new segment (same speaker).

    Returns whether a trailing ``<s>`` (no text after it) cuts before the next turn.
    """
    pending = bool(cut)
    for k, piece in enumerate(SEGMENT_MARK_RE.split(str(chunk or ""))):
        if k > 0:
            pending = True
        cleaned = piece.strip()
        if cleaned:
            turns.append(SpeechTurn(int(who), cleaned, bool(mono), pending))
            pending = False
    return pending


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
        if parts and getattr(t, "cut_before", False):
            mark = "<s> " + mark  # t370u: keep the manual segment mark
        parts.append(f"{mark} {text}")
    return " ".join(parts).strip()


def speaking_has_segment_marks(text: str) -> bool:
    """t370u: speaking contains a manual ``<s>`` segment mark."""
    return bool(SEGMENT_MARK_RE.search(str(text or "")))


def speaking_segment_turns(text: str) -> list:
    """t370u: speaking → segments (节), each a list of ``SpeechTurn``.

    A new segment starts at every manual ``<s>`` mark and wherever self-talk
    (``<Ns>``) starts or stops, so a run of ``<Ns>`` lines is its own segment.
    One segment (or none) means the scene is generated in one go.
    """
    groups: list = []
    for turn in parse_speaking_turns(text):
        if groups and not turn.cut_before and bool(turn.monologue) == bool(groups[-1][-1].monologue):
            groups[-1].append(turn)
        else:
            groups.append([turn])
    return groups


def format_segment_turns(turns) -> str:
    """t370u: canonical speaking for a slice of turns; the first turn's ``<s>`` is dropped."""
    out = [copy.copy(t) for t in (turns or [])]
    if out:
        out[0].cut_before = False
    return format_speaking_turns(out)


def speaking_segments(text: str) -> list:
    """t370u: speaking text of each segment (no ``<s>`` inside a one-segment slice)."""
    return [format_segment_turns(g) for g in speaking_segment_turns(text)]


_SEGMENT_MARK_AT_END_RE = re.compile(r"[<＜]\s*[sS]\s*[>＞]\s*$")


def segment_mark_insert(text: str, pos: int) -> tuple:
    """t373u: 讲话框 Ctrl+S = 在光标处加手工分节符 ``<s>``（不再把场景拆成两场）。

    ``pos`` = 光标前的字数。可以加：返回 ``(新文本, 加完后的光标位置, "")``；不能加：``(None, None, 原因)``。
    规则：
    - 光标后面紧跟一个说话人标记 ``<n>`` / ``<ns>``（例 ``<2>``、``<12>``、``<1s>``）；中间只隔空格 / 换行也算。
    - 不能在最开头（光标前面没有讲话）也不能在最末尾（这个标记后面没有讲话）。
    - 这里已经有 ``<s>``（光标前紧挨着或光标后紧跟）就不再加。
    加的是 ``<s>``；光标正好贴着 ``<n>`` 时加 ``<s> ``（留一个空格）。
    """
    text = str(text or "")
    try:
        pos = max(0, min(int(pos), len(text)))
    except (TypeError, ValueError):
        return None, None, "读不出光标位置。"
    before, after = text[:pos], text[pos:]
    lead = len(after) - len(after.lstrip())
    if SEGMENT_MARK_RE.match(after, lead) or _SEGMENT_MARK_AT_END_RE.search(before):
        return None, None, "这里已经有分节符 <s>，不用再加。"
    mark = SPEAKER_TOKEN_RE.match(after, lead)
    if not mark:
        return None, None, ("分节符 <s> 只能加在某个说话人标记（例如 <1>、<2>、<1s>）的前面。\n"
                            "请把光标放在那个 <n> 的前面再按 Ctrl+S。")
    if not strip_speaker_marks(SEGMENT_MARK_RE.sub(" ", before)).strip():
        return None, None, "最开头不能加分节符 <s>：前面还没有讲话。"
    if not strip_speaker_marks(SEGMENT_MARK_RE.sub(" ", after[mark.end():])).strip():
        return None, None, "最末尾不能加分节符 <s>：这个说话人标记后面没有讲话。"
    piece = "<s>" if lead else "<s> "
    return before + piece + after, pos + len(piece), ""


def speaking_segment_count(text: str) -> int:
    return len(speaking_segment_turns(text))


def split_speaking_turns(text: str) -> list:
    """Compatibility helper: ``[(speaker, spoken_text), ...]`` with marks stripped."""
    return [(t.speaker, t.text) for t in parse_speaking_turns(text) if t.text]


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


def authored_fields_match(left, right) -> bool:
    if not (isinstance(left, dict) and isinstance(right, dict)):
        return False
    for key in ("caption", "visual", "actor"):
        if (left.get(key) or "").strip() != (right.get(key) or "").strip():
            return False
    return True


def ensure_cover_steps(scenes) -> bool:
    """Persist original cover-step numbers (one per scene, in order). Returns True if any scene changed.

    Already-stamped values are kept; unstamped scenes get the next unused step.
    """
    if not isinstance(scenes, list):
        return False
    items = [s for s in scenes if isinstance(s, dict)]
    used = {scene_cover_step(s) for s in items if scene_cover_step(s)}
    changed = False
    next_step = 1
    for scene in items:
        if scene_cover_step(scene):
            continue
        while next_step in used:
            next_step += 1
        scene[COVER_STEP_KEY] = next_step
        used.add(next_step)
        next_step += 1
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
    return authored_fields_match(primary, other)


def iter_cover_extract_targets(scenes):
    """Yield ``(scene, step)`` once per original cover panel when siblings match.

    Later scenes that only differ in speaking (same cover step and the same
    authored caption/visual/actor, e.g. t370u video-segment clones) are skipped
    so batch extract does not spend a second image request on the same panel.
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
