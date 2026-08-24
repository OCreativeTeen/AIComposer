"""CLI bot is always the 听筒 (human / Hermes operate; bot syncs and runs one command)."""

from __future__ import annotations

MODE_LISTEN = "listen"
VALID_MODES = (MODE_LISTEN,)

_current = MODE_LISTEN


def normalize_mode(raw: str) -> str:
    key = (raw or "").strip().lower().lstrip("-")
    if key in ("listen", "manual", "hand", "remote", "sync", "hermes", "cli", "passive", ""):
        return MODE_LISTEN
    if key in ("telegram", "tg", "auto", "agent"):
        raise ValueError("自主 bot 已移除。请用 python -m cli bot 或 cli\\run_bot.bat")
    raise ValueError(f"unknown bot mode: {raw!r}（只有听筒：listen / hermes）")


def set_mode(mode: str) -> str:
    global _current
    _current = normalize_mode(mode)
    return _current


def get_mode() -> str:
    return _current


def parse_bot_argv(argv: list[str]) -> str:
    """Parse ``bot`` extra args. Only listen / hermes remain."""
    args = list(argv or [])
    if not args:
        return set_mode(MODE_LISTEN)
    if args[0] in ("--mode", "-m") and len(args) >= 2:
        return set_mode(args[1])
    if args[0].startswith("--mode="):
        return set_mode(args[0].split("=", 1)[1])
    return set_mode(args[0])
