"""GUI-side CLI bridge: bind live widgets and apply file requests on the Tk thread."""

from __future__ import annotations

import json
import os
from typing import Any

import config

Handler = dict[str, Any]
_BOUND: dict[str, dict[str, Any]] = {}
_ROOT_WIDGET = None
_ROOT_POLLING = False
_PENDING_ON_TK = False
_LAST_REQ_ID = ""

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


def _iter_widgets(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        yield from _iter_widgets(child)


def _invoke_named_button(root, label: str) -> bool:
    """Find a Tk/ttk Button by visible text and invoke it on the next Tk tick."""
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
            root.after(0, invoke)
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
    if len(hits) == 1:
        return hits[0]
    return hits[0]


def is_screen_bound(name: str) -> bool:
    """True if this screen has a live widget registered for CLI bridge."""
    entry = _BOUND.get((name or "").strip())
    if not entry:
        return False
    widget = entry.get("widget")
    if widget is None:
        return False
    try:
        return bool(widget.winfo_exists())
    except Exception:
        return False


def register_bridge_root(widget) -> None:
    """Keep polling on the app root so SCENE ``wait_window`` cannot kill the bridge."""
    global _ROOT_WIDGET
    _ROOT_WIDGET = widget
    _ensure_root_poller()


def bind_screen(name: str, widget, handlers: dict[str, Handler]) -> None:
    _BOUND[name] = {"widget": widget, "handlers": handlers or {}}
    config.set_active_screen(name)
    _ensure_root_poller()
    try:
        widget.after(0, _maybe_dispatch_request)
    except Exception:
        pass


def unbind_screen(name: str) -> None:
    _BOUND.pop(name, None)
    if config.SCREEN_STORY_SCENE in _BOUND:
        config.set_active_screen(config.SCREEN_STORY_SCENE)
    elif config.SCREEN_STORY_ROOT in _BOUND:
        config.set_active_screen(config.SCREEN_STORY_ROOT)
    else:
        config.set_active_screen(config.SCREEN_NONE)
    _ensure_root_poller()


def _ensure_root_poller() -> None:
    global _ROOT_POLLING
    widget = _ROOT_WIDGET
    if widget is None or _ROOT_POLLING:
        return
    try:
        if not widget.winfo_exists():
            return
    except Exception:
        return
    _ROOT_POLLING = True
    widget.after(80, _root_poll_once)


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


def _clear_request() -> None:
    path = config.CLI_BRIDGE_REQUEST_JSON
    try:
        if os.path.isfile(path):
            os.remove(path)
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


def _apply(req: dict) -> tuple[bool, str]:
    screen = (req.get("screen") or config.get_active_screen() or "").strip()
    op = (req.get("op") or "").strip()
    field = (req.get("field") or "").strip()
    value = req.get("value")
    if value is None:
        value = ""
    else:
        value = str(value)

    bound = _BOUND.get(screen)
    if not bound:
        return False, f"screen {screen} is not bound in GUI"
    handlers = bound.get("handlers") or {}
    spec = handlers.get(field)
    if not spec:
        if op == "click":
            label = _CLICK_LABELS.get(field, field)
            if _invoke_named_button(bound.get("widget"), label):
                return True, f"clicked {field}"
        return False, f"unknown field {field} on {screen}"

    try:
        if op == "click":
            fn = spec.get("click")
            if not callable(fn):
                return False, f"{field} is not clickable"
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
    except Exception as exc:
        return False, f"{field} failed: {exc}"
    return False, f"unknown op {op}"


def _finish_request(req_id: str, ok: bool, message: str) -> None:
    global _LAST_REQ_ID
    _LAST_REQ_ID = req_id
    _write_reply({"id": req_id, "ok": ok, "message": message})
    _clear_request()


def _maybe_dispatch_request() -> None:
    global _PENDING_ON_TK
    if _PENDING_ON_TK:
        return
    req = _read_request()
    if not req:
        return
    req_id = str(req.get("id") or "")
    if not req_id or req_id == _LAST_REQ_ID:
        return

    screen = (req.get("screen") or "").strip()
    bound = _BOUND.get(screen)
    if not bound:
        _finish_request(req_id, False, f"screen {screen} is not bound in GUI")
        return

    target = bound.get("widget")
    if target is None:
        _finish_request(req_id, False, f"screen {screen} has no widget")
        return
    try:
        if not target.winfo_exists():
            _finish_request(req_id, False, f"screen {screen} widget is gone")
            return
    except Exception:
        _finish_request(req_id, False, f"screen {screen} widget is gone")
        return

    _PENDING_ON_TK = True

    def _run_on_tk(r=req, rid=req_id):
        global _PENDING_ON_TK
        try:
            if rid == _LAST_REQ_ID:
                return
            ok, message = _apply(r)
            _finish_request(rid, ok, message)
        except Exception as exc:
            _finish_request(rid, False, str(exc))
        finally:
            _PENDING_ON_TK = False

    try:
        target.after(0, _run_on_tk)
    except Exception as exc:
        _PENDING_ON_TK = False
        try:
            ok, message = _apply(req)
            _finish_request(req_id, ok, message)
        except Exception as inner:
            _finish_request(req_id, False, f"{exc}; {inner}")


def _root_poll_once() -> None:
    global _ROOT_POLLING
    widget = _ROOT_WIDGET
    if widget is None:
        _ROOT_POLLING = False
        return
    try:
        if not widget.winfo_exists():
            _ROOT_POLLING = False
            return
    except Exception:
        _ROOT_POLLING = False
        return

    _maybe_dispatch_request()

    try:
        widget.after(100, _root_poll_once)
    except Exception:
        _ROOT_POLLING = False
