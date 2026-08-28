"""Cross-process CLI → GUI bridge (request / reply JSON files)."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

import config

# Only one request file exists, so concurrent callers inside this process must
# serialize or they clobber each other's request.
_SEND_LOCK = threading.Lock()


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


def gui_heartbeat() -> dict | None:
    """Latest GUI bridge heartbeat, or None when the GUI is not running."""
    data = _read_json(getattr(config, "CLI_BRIDGE_HEARTBEAT_JSON", "")) or None
    if not data:
        return None
    try:
        if time.time() - float(data.get("ts") or 0) > 8.0:
            return None
    except (TypeError, ValueError):
        return None
    return data


def _timeout_hint(screen: str) -> str:
    beat = gui_heartbeat()
    if beat is None:
        return (
            "GUI bridge 无响应：GUI 进程没在跑（或刚崩过）。\n"
            "请先启动 GUI，再重发命令。"
        )
    if not beat.get("pump_alive"):
        return (
            "GUI bridge 无响应：GUI 还活着，但 Tk 主线程被卡住"
            f"（pump 已 {beat.get('pump_age_s')} 秒没跑）。\n"
            "多半是某个窗口正在做同步的长任务。等它做完，或重启 GUI。"
        )
    ready = ", ".join(beat.get("ready") or []) or "（无）"
    building = ", ".join(beat.get("building") or [])
    extra = f"；正在加载：{building}" if building else ""
    return (
        f"GUI bridge 超时（screen={screen}）。GUI 正常，但该屏没应答。\n"
        f"已就绪的屏：{ready}{extra}"
    )


def bridge_screen_bound(screen: str, *, timeout_s: float = 1.5) -> bool:
    """Ask the GUI process whether ``screen`` is registered and finished building.

    Answered by the GUI poller thread, so this stays fast even when Tk is busy.
    """
    ok, _msg = send_bridge_command(
        screen=screen,
        op="bound",
        field="",
        timeout_s=timeout_s,
    )
    return ok


def bridge_pump_alive(*, timeout_s: float = 1.5) -> tuple[bool, str]:
    """True when the GUI Tk main loop is actually processing bridge work."""
    return send_bridge_command(
        screen=config.SCREEN_NONE,
        op="ping",
        field="",
        timeout_s=timeout_s,
    )


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
        "expires_at": time.time() + timeout_s,
    }
    reply_path = config.CLI_BRIDGE_REPLY_JSON

    with _SEND_LOCK:
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
            time.sleep(0.02)

        # Stop the GUI from running a command whose caller already gave up.
        try:
            stale = _read_json(config.CLI_BRIDGE_REQUEST_JSON)
            if stale and stale.get("id") == req_id:
                os.remove(config.CLI_BRIDGE_REQUEST_JSON)
        except OSError:
            pass

    return False, _timeout_hint(screen)
