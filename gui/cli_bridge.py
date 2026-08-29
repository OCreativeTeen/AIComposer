"""GUI-side CLI bridge: bind live widgets and apply file requests on the Tk thread.

Threading contract (important):

* The **poller thread** only touches plain Python state and files. It must never
  call a Tk method — Tkinter is not thread-safe and doing so freezes the GUI.
* The **pump** runs on the Tk thread via ``after()``. It is the only place that
  invokes widget handlers.

The poller answers cheap questions (``bound`` / ``ping``) by itself so a busy Tk
main loop can never make ``scn`` / readiness checks hang.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from typing import Any

import config

Handler = dict[str, Any]

_PUMP_INTERVAL_MS = 20
_POLL_INTERVAL_S = 0.02
_HEARTBEAT_INTERVAL_S = 0.5

_LOCK = threading.RLock()
# Tk-thread owned; read by the poller only through _BOUND_STATE snapshots.
_BOUND: dict[str, dict[str, Any]] = {}
# Plain-Python mirror of _BOUND that the poller may read safely.
_BOUND_STATE: dict[str, bool] = {}

_ROOT_WIDGET = None
_INBOX: queue.Queue = queue.Queue()
_SEEN_IDS: deque[str] = deque(maxlen=256)
_SEEN_SET: set[str] = set()

_POLLER_STARTED = False
_PUMP_ARMED = False
_LAST_PUMP_TS = 0.0

_CLICK_LABELS = {
    "scene": "场景",
    "save": "保存",
    "publish": "审阅发布",
    "analyze": "分析",
    "poem": "诗歌",
    "script": "脚本",
    "style": "风格",
    "cover": "封面提示",
    "project": "打开项目",
}

# Handlers that open a big editor. Running them inline would block the pump, so
# they are scheduled on the next Tk tick and acked immediately.
_DEFERRED_CLICKS = {(config.SCREEN_STORY_ROOT, "scene")}


def _iter_widgets(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        yield from _iter_widgets(child)


def _invoke_named_button(root, label: str) -> bool:
    """Find a Tk/ttk Button by visible text and invoke it (Tk thread only)."""
    if root is None or not label:
        return False
    for child in _iter_widgets(root):
        try:
            text = str(child.cget("text")).strip()
        except Exception:
            continue
        if text != label:
            continue
        invoke = getattr(child, "invoke", None)
        if not callable(invoke):
            continue
        try:
            invoke()
            return True
        except Exception:
            continue
    return False


def match_choice(want: str, choices: list[str]) -> str:
    want = (want or "").strip()
    if not want:
        return ""
    if want.isdigit():
        idx = int(want)
        if 1 <= idx <= len(choices):
            return choices[idx - 1]
        return ""
    for item in choices:
        if item == want:
            return item
    low = want.lower()
    for item in choices:
        if item.lower() == low:
            return item
    hits = [item for item in choices if low in item.lower()]
    if not hits:
        return ""
    starts = [item for item in hits if item.lower().startswith(low)]
    if len(starts) == 1:
        return starts[0]
    return hits[0]


def is_screen_bound(name: str) -> bool:
    """True when the screen is registered *and* finished building its handlers."""
    with _LOCK:
        return bool(_BOUND_STATE.get((name or "").strip()))


def register_bridge_root(widget) -> None:
    """Remember the app root so the pump survives dialogs opening and closing."""
    global _ROOT_WIDGET
    _ROOT_WIDGET = widget
    _start_poller()
    _arm_pump()


def bind_screen(
    name: str,
    widget,
    handlers: dict[str, Handler],
    *,
    ready: bool = True,
) -> None:
    """Register a screen. ``ready=False`` marks a placeholder that is still building."""
    with _LOCK:
        _BOUND[name] = {"widget": widget, "handlers": handlers or {}, "ready": ready}
        _BOUND_STATE[name] = bool(ready)
    config.set_active_screen(name)
    _start_poller()
    _arm_pump()


def unbind_screen(name: str) -> None:
    with _LOCK:
        _BOUND.pop(name, None)
        _BOUND_STATE.pop(name, None)
        has_scene = config.SCREEN_STORY_SCENE in _BOUND
        has_root = config.SCREEN_STORY_ROOT in _BOUND
    if has_scene:
        config.set_active_screen(config.SCREEN_STORY_SCENE)
    elif has_root:
        config.set_active_screen(config.SCREEN_STORY_ROOT)
    else:
        config.set_active_screen(config.SCREEN_NONE)
    _arm_pump()


# --------------------------------------------------------------------------- #
# file plumbing
# --------------------------------------------------------------------------- #


def _read_request() -> dict | None:
    path = config.CLI_BRIDGE_REQUEST_JSON
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _clear_request(req_id: str) -> None:
    """Delete the request file only if it still holds *this* request.

    The CLI may already have written the next request after giving up on this
    one; deleting that would strand the new command.
    """
    current = _read_request()
    if not current or str(current.get("id") or "") != req_id:
        return
    try:
        os.remove(config.CLI_BRIDGE_REQUEST_JSON)
    except OSError:
        pass


def _write_reply(payload: dict) -> None:
    path = config.CLI_BRIDGE_REPLY_JSON
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def _finish_request(req_id: str, ok: bool, message: str) -> None:
    _write_reply({"id": req_id, "ok": ok, "message": message})
    _clear_request(req_id)


def _write_heartbeat() -> None:
    """Let the CLI process tell 'GUI not running' apart from 'Tk main loop busy'."""
    with _LOCK:
        ready = sorted(k for k, v in _BOUND_STATE.items() if v)
        building = sorted(k for k, v in _BOUND_STATE.items() if not v)
    age = time.monotonic() - _LAST_PUMP_TS if _LAST_PUMP_TS else -1.0
    payload = {
        "ts": time.time(),
        "pump_age_s": round(age, 2),
        "pump_alive": bool(_PUMP_ARMED and 0 <= age < 3.0),
        "ready": ready,
        "building": building,
        "inbox": _INBOX.qsize(),
    }
    try:
        path = config.CLI_BRIDGE_HEARTBEAT_JSON
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# poller thread — files + plain state only, never Tk
# --------------------------------------------------------------------------- #


def _discard_stale_files() -> None:
    """Drop leftovers from a previous session so we never replay an old command."""
    for path in (config.CLI_BRIDGE_REQUEST_JSON, config.CLI_BRIDGE_REPLY_JSON):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


def _start_poller() -> None:
    global _POLLER_STARTED
    with _LOCK:
        if _POLLER_STARTED:
            return
        _POLLER_STARTED = True
    _discard_stale_files()
    threading.Thread(target=_poll_loop, daemon=True, name="cli-bridge-poll").start()


def _poll_loop() -> None:
    last_beat = 0.0
    while True:
        try:
            _poll_once()
            now = time.monotonic()
            if now - last_beat >= _HEARTBEAT_INTERVAL_S:
                _write_heartbeat()
                last_beat = now
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL_S)


def _mark_seen(req_id: str) -> bool:
    """Return True the first time we see this id."""
    with _LOCK:
        if req_id in _SEEN_SET:
            return False
        if len(_SEEN_IDS) == _SEEN_IDS.maxlen:
            _SEEN_SET.discard(_SEEN_IDS[0])
        _SEEN_IDS.append(req_id)
        _SEEN_SET.add(req_id)
        return True


def _is_expired(req: dict) -> bool:
    expires_at = req.get("expires_at")
    if not expires_at:
        return False
    try:
        return time.time() > float(expires_at)
    except (TypeError, ValueError):
        return False


def _poll_once() -> None:
    req = _read_request()
    if not req:
        return
    req_id = str(req.get("id") or "")
    if not req_id:
        return

    if _is_expired(req):
        # The caller already gave up; running it now would surprise the user.
        _mark_seen(req_id)
        _clear_request(req_id)
        return

    op = (req.get("op") or "").strip()
    screen = (req.get("screen") or "").strip()

    # Cheap, Tk-free answers: never let a busy main loop stall readiness checks.
    if op == "bound":
        if not _mark_seen(req_id):
            return
        ok = is_screen_bound(screen)
        with _LOCK:
            building = screen in _BOUND_STATE and not _BOUND_STATE.get(screen)
        if ok:
            msg = "bound"
        elif building:
            msg = f"screen {screen} is still building"
        else:
            msg = f"screen {screen} is not bound"
        _finish_request(req_id, ok, msg)
        return

    if op == "ping":
        if not _mark_seen(req_id):
            return
        age = time.monotonic() - _LAST_PUMP_TS if _LAST_PUMP_TS else -1.0
        alive = bool(_PUMP_ARMED and 0 <= age < 3.0)
        _finish_request(req_id, alive, f"pump_age={age:.2f}s inbox={_INBOX.qsize()}")
        return

    if not _mark_seen(req_id):
        return

    with _LOCK:
        known = screen in _BOUND_STATE
        ready = bool(_BOUND_STATE.get(screen))
    if not known:
        _finish_request(req_id, False, f"screen {screen} is not bound in GUI")
        return
    if not ready:
        _finish_request(
            req_id, False, f"screen {screen} 仍在加载，请 2 秒后重试"
        )
        return

    _INBOX.put(req)


# --------------------------------------------------------------------------- #
# pump — Tk thread only
# --------------------------------------------------------------------------- #


def _pump_widget():
    widget = _ROOT_WIDGET
    if widget is not None:
        try:
            if widget.winfo_exists():
                return widget
        except Exception:
            pass
    with _LOCK:
        entries = list(_BOUND.values())
    for entry in entries:
        candidate = entry.get("widget")
        if candidate is None:
            continue
        try:
            if candidate.winfo_exists():
                return candidate
        except Exception:
            continue
    return None


def _arm_pump() -> None:
    """Schedule the Tk-side pump. Safe to call repeatedly."""
    global _PUMP_ARMED
    with _LOCK:
        if _PUMP_ARMED:
            return
        _PUMP_ARMED = True
    widget = _pump_widget()
    if widget is None:
        with _LOCK:
            _PUMP_ARMED = False
        return
    try:
        widget.after(_PUMP_INTERVAL_MS, _pump)
    except Exception:
        with _LOCK:
            _PUMP_ARMED = False


def _pump() -> None:
    global _PUMP_ARMED, _LAST_PUMP_TS
    _LAST_PUMP_TS = time.monotonic()

    # Drain a few requests per tick so a long UI build cannot starve the queue.
    for _ in range(4):
        try:
            req = _INBOX.get_nowait()
        except queue.Empty:
            break

        req_id = str(req.get("id") or "")
        expires_at = req.get("expires_at")
        expired = False
        try:
            expired = bool(expires_at) and time.time() > float(expires_at)
        except (TypeError, ValueError):
            expired = False
        if expired:
            _finish_request(req_id, False, "request expired before GUI could run it")
        else:
            try:
                ok, message = _apply(req)
            except Exception as exc:
                ok, message = False, str(exc)
            _finish_request(req_id, ok, message)

    widget = _pump_widget()
    if widget is None:
        with _LOCK:
            _PUMP_ARMED = False
        return
    try:
        widget.after(_PUMP_INTERVAL_MS, _pump)
    except Exception:
        with _LOCK:
            _PUMP_ARMED = False


def _apply(req: dict) -> tuple[bool, str]:
    screen = (req.get("screen") or config.get_active_screen() or "").strip()
    op = (req.get("op") or "").strip()
    field = (req.get("field") or "").strip()
    value = req.get("value")
    value = "" if value is None else str(value)

    with _LOCK:
        bound = _BOUND.get(screen)
    if not bound:
        return False, f"screen {screen} is not bound in GUI"

    widget = bound.get("widget")
    try:
        if widget is None or not widget.winfo_exists():
            return False, f"screen {screen} widget is gone"
    except Exception:
        return False, f"screen {screen} widget is gone"

    handlers = bound.get("handlers") or {}
    spec = handlers.get(field)
    if not spec:
        if op == "click":
            label = _CLICK_LABELS.get(field, field)
            if _invoke_named_button(widget, label):
                return True, f"clicked {field}"
        return False, f"unknown field {field} on {screen}"

    try:
        if op == "click":
            fn = spec.get("click")
            if not callable(fn):
                return False, f"{field} is not clickable"
            if (screen, field) in _DEFERRED_CLICKS:
                try:
                    widget.after(1, fn)
                except Exception as exc:
                    return False, f"could not schedule {field}: {exc}"
                return True, f"clicked {field}"
            fn()
            return True, f"clicked {field}"
        if op == "choices":
            fn = spec.get("choices")
            choices = fn() if callable(fn) else (spec.get("choices") or [])
            return True, "\n".join(str(x) for x in choices)
        if op == "get":
            fn = spec.get("get")
            if not callable(fn):
                return False, f"{field} has no getter"
            current = fn()
            extra = ""
            ch_fn = spec.get("choices")
            if callable(ch_fn):
                choices = ch_fn()
                if choices:
                    extra = "\nchoices: " + " | ".join(str(x) for x in choices)
            return True, f"{current}{extra}"
        if op == "set":
            fn = spec.get("set")
            if not callable(fn):
                return False, f"{field} has no setter"
            return fn(value)
        if op == "persist":
            fn = spec.get("persist")
            if not callable(fn):
                return False, f"{field} has no persist"
            result = fn()
            if isinstance(result, tuple) and len(result) >= 2:
                return bool(result[0]), str(result[1])
            return True, f"persisted {field}"
    except Exception as exc:
        return False, f"{field} failed: {exc}"
    return False, f"unknown op {op}"
