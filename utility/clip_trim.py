"""Scene clip trim helpers (no GUI / queue imports — avoids circular imports)."""

from __future__ import annotations

LEGACY_DEFAULT_CLIP_END = 10.0


def clip_end_means_full_length(value, *, legacy_end: float = LEGACY_DEFAULT_CLIP_END) -> bool:
    """``clip_end`` unset or legacy 10s placeholder → use entire mp4 in review/concat."""
    if value in (None, ""):
        return True
    try:
        return abs(float(value) - float(legacy_end)) < 0.05
    except (TypeError, ValueError):
        return True
