"""Cross-process CLI → GUI bridge (request / reply JSON files)."""

from __future__ import annotations

import json
import os
import time
import uuid

import config


def _read_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def send_bridge_command(
    *,
    screen: str,
    op: str,
    field: str,
    value: str = "",
    timeout_s: float = 8.0,
) -> tuple[bool, str]:
    """Ask the running GUI to get/set/click a bound screen field."""
    req_id = uuid.uuid4().hex[:12]
    request = {
        "id": req_id,
        "screen": screen,
        "op": op,
        "field": field,
        "value": value or "",
    }
    reply_path = config.CLI_BRIDGE_REPLY_JSON
    try:
        if os.path.isfile(reply_path):
            os.remove(reply_path)
    except OSError:
        pass
    try:
        _write_json(config.CLI_BRIDGE_REQUEST_JSON, request)
    except OSError as exc:
        return False, f"bridge write failed: {exc}"

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        reply = _read_json(reply_path)
        if reply and reply.get("id") == req_id:
            ok = bool(reply.get("ok"))
            return ok, str(reply.get("message") or ("ok" if ok else "failed"))
        time.sleep(0.1)
    return False, (
        "GUI bridge timeout — is the target window open "
        f"(screen={screen})?"
    )
