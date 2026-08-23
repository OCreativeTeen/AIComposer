#!/usr/bin/env python3
"""视频列表「选择队列」：GUI 导出选中行 → ``program/video_choice_queue.json`` → CLI 逐条取用。

用法示例::

    python -m aiagent.pick_video_choice list
    python -m aiagent.pick_video_choice next --json
    python -m aiagent.pick_video_choice next --with-detail --json
    python -m aiagent.pick_video_choice done <choice_id>
    python -m aiagent.pick_video_choice skip <choice_id>
"""

from __future__ import annotations

import os
import sys

# 保证从 aiagent/ 直接运行脚本时仍能 import 项目根模块（config 等）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import project_manager

VIDEO_CHOICE_QUEUE_JSON = config.VIDEO_CHOICE_QUEUE_JSON
QUEUE_VERSION = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_program_dir() -> None:
    os.makedirs(config.BASE_PROGRAM_PATH, exist_ok=True)


def load_queue() -> dict:
    """读取队列；文件不存在时返回空队列。"""
    path = VIDEO_CHOICE_QUEUE_JSON
    if not os.path.isfile(path):
        return {"version": QUEUE_VERSION, "cursor": 0, "items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"version": QUEUE_VERSION, "cursor": 0, "items": []}
    if not isinstance(data, dict):
        data = {"version": QUEUE_VERSION, "cursor": 0, "items": []}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    if not isinstance(data.get("cursor"), int) or data["cursor"] < 0:
        data["cursor"] = 0
    data["version"] = QUEUE_VERSION
    return data


def save_queue(data: dict) -> str:
    """写回队列 JSON，返回绝对路径。"""
    if not isinstance(data, dict):
        raise ValueError("queue data 必须是 dict")
    _ensure_program_dir()
    items = data.get("items")
    if not isinstance(items, list):
        items = []
        data["items"] = items
    data["version"] = QUEUE_VERSION
    if "cursor" not in data or not isinstance(data.get("cursor"), int) or data["cursor"] < 0:
        data["cursor"] = 0
    path = VIDEO_CHOICE_QUEUE_JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return os.path.abspath(path)


def _row_lookup_keys(video_detail: dict) -> list[str]:
    if not isinstance(video_detail, dict):
        return []
    keys: list[str] = []
    for k in ("url", "id"):
        v = (video_detail.get(k) or "").strip()
        if v and v not in keys:
            keys.append(v)
    pid = project_manager.list_json_row_workflow_pid(video_detail)
    if pid and pid not in keys:
        keys.append(pid)
    return keys


def _queue_item_dedupe_key(item: dict) -> str:
    list_path = os.path.normcase(os.path.normpath((item.get("list_json_path") or "").strip()))
    row_key = (item.get("row_key") or item.get("url") or item.get("row_id") or "").strip()
    return f"{list_path}\0{row_key}"


def build_queue_item_from_video_detail(
    video_detail: dict,
    *,
    channel_id: str = "",
    channel_path: str = "",
    list_json_path: str = "",
    title: str = "",
    yt_language: str = "",
    visual_style: str = "",
    narrator: str = "",
) -> dict:
    """由列表行构造可写入队列的条目（不含 choice_id / status）。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    ch_path = (channel_path or "").strip()
    ch_id = (channel_id or "").strip()
    if not ch_id and ch_path:
        ch_id = config.get_channel_id(os.path.basename(ch_path))
    list_path = (list_json_path or "").strip()
    if not list_path and ch_path:
        list_path = config.yt_text_download_list_json_path(ch_id) if ch_id else ""

    row_keys = _row_lookup_keys(vd)
    row_key = row_keys[0] if row_keys else ""

    tags = vd.get("tags", "")
    if isinstance(tags, list):
        tags_text = " | ".join(str(t) for t in tags if t is not None)
    else:
        tags_text = str(tags) if tags else ""

    sc = vd.get("scene_content")
    has_scene = False
    if isinstance(sc, list) and sc:
        has_scene = True
    elif isinstance(sc, str) and sc.strip():
        has_scene = True

    return {
        "channel_id": ch_id,
        "channel_path": ch_path,
        "list_json_path": list_path,
        "row_key": row_key,
        "row_id": (vd.get("id") or "").strip(),
        "url": (vd.get("url") or "").strip(),
        "title": (title or vd.get("title") or vd.get("video_title") or "").strip(),
        "topic_category": (vd.get("topic_category") or "").strip(),
        "topic_subtype": (vd.get("topic_subtype") or "").strip(),
        "tags": tags_text,
        "workflow_pid": project_manager.list_json_row_workflow_pid(vd),
        "language": (vd.get("language") or "").strip(),
        "yt_language": (yt_language or "").strip(),
        "visual_style": (visual_style or "").strip(),
        "narrator": (narrator or "").strip(),
        "has_analyzed_content": bool((vd.get("analyzed_content") or "").strip()),
        "has_scene_content": has_scene,
    }


def export_video_details_to_queue(
    video_details: list[dict],
    *,
    channel_id: str = "",
    channel_path: str = "",
    list_json_path: str = "",
    title_fn=None,
    yt_language: str = "",
    visual_style: str = "",
    narrator: str = "",
) -> tuple[int, int, str]:
    """用当前选中项**整表覆盖**队列（清空旧列表，cursor 归零）。返回 (写入数, 跳过数, 文件路径)。"""
    items: list[dict] = []
    skipped = 0
    now = _utc_now_iso()
    seen: set[str] = set()

    for vd in video_details or []:
        if not isinstance(vd, dict):
            skipped += 1
            continue
        title = ""
        if callable(title_fn):
            try:
                title = (title_fn(vd) or "").strip()
            except Exception:
                title = ""
        base = build_queue_item_from_video_detail(
            vd,
            channel_id=channel_id,
            channel_path=channel_path,
            list_json_path=list_json_path,
            title=title,
            yt_language=yt_language,
            visual_style=visual_style,
            narrator=narrator,
        )
        if not base.get("row_key") and not base.get("workflow_pid"):
            skipped += 1
            continue
        dedupe = _queue_item_dedupe_key(base)
        if dedupe in seen:
            skipped += 1
            continue
        seen.add(dedupe)
        items.append({
            **base,
            "choice_id": uuid.uuid4().hex[:12],
            "exported_at": now,
        })

    data = {
        "version": QUEUE_VERSION,
        "cursor": 0,
        "exported_at": now,
        "items": items,
    }
    path = save_queue(data)
    return len(items), skipped, path


def list_queue_items(*, remaining_only: bool = False) -> list[dict]:
    data = load_queue()
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    if remaining_only:
        cursor = int(data.get("cursor") or 0)
        items = items[cursor:]
    return items


def _find_item_by_choice_id(data: dict, choice_id: str) -> dict | None:
    cid = (choice_id or "").strip()
    if not cid:
        return None
    for it in data.get("items") or []:
        if isinstance(it, dict) and (it.get("choice_id") or "").strip() == cid:
            return it
    return None


def pick_next_item(*, advance: bool = True) -> dict | None:
    """按 ``cursor`` 取下一条；默认取用后 cursor +1（无 pending / in_progress 状态）。"""
    data = load_queue()
    items = data.get("items") or []
    cursor = int(data.get("cursor") or 0)
    if cursor >= len(items):
        return None
    item = items[cursor]
    if not isinstance(item, dict):
        return None
    if advance:
        data["cursor"] = cursor + 1
        save_queue(data)
    return copy.deepcopy(item)


def advance_queue_cursor(steps: int = 1) -> int:
    """手动前移 cursor（``done`` / ``skip`` 兼容用）。返回新 cursor。"""
    data = load_queue()
    items = data.get("items") or []
    cursor = int(data.get("cursor") or 0)
    cursor = min(cursor + max(1, steps), len(items))
    data["cursor"] = cursor
    save_queue(data)
    return cursor


def reset_queue_cursor() -> None:
    data = load_queue()
    data["cursor"] = 0
    save_queue(data)


def _match_row_in_list(arr: list, item: dict) -> dict | None:
    row_key = (item.get("row_key") or "").strip()
    row_id = (item.get("row_id") or "").strip()
    url = (item.get("url") or "").strip()
    pid = (item.get("workflow_pid") or "").strip()
    for row in arr:
        if not isinstance(row, dict):
            continue
        if row_key and (
            (row.get("url") or "").strip() == row_key
            or (row.get("id") or "").strip() == row_key
        ):
            return row
        if url and (row.get("url") or "").strip() == url:
            return row
        if row_id and (row.get("id") or "").strip() == row_id:
            return row
        if pid and project_manager.list_json_row_workflow_pid(row) == pid:
            return row
    return None


def resolve_video_detail_from_queue_item(item: dict) -> dict | None:
    """从 ``list_json_path`` 读盘，按 row_key / pid 定位完整 video detail 行。"""
    if not isinstance(item, dict):
        return None
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path or not os.path.isfile(list_path):
        return None
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(arr, list):
        return None
    return _match_row_in_list(arr, item)


def resolve_queue_item_by_id(choice_id: str) -> dict | None:
    data = load_queue()
    it = _find_item_by_choice_id(data, choice_id)
    if not it:
        return None
    row = resolve_video_detail_from_queue_item(it)
    return {
        "queue_item": copy.deepcopy(it),
        "video_detail": copy.deepcopy(row) if row else None,
    }


def apply_queue_item_yt_prefs(item: dict) -> dict:
    """将队列条目中的 YT 欢迎屏选项写入内存 LAST_*（并尽量写回 prefs 文件）。"""
    if not isinstance(item, dict):
        return {}
    prefs = config.load_yt_tools_prefs()
    lang = (item.get("yt_language") or prefs.get("language") or project_manager.LAST_YT_LANGUAGE or "tw").strip()
    if lang not in config.LANGUAGES:
        lang = project_manager.LAST_YT_LANGUAGE if project_manager.LAST_YT_LANGUAGE in config.LANGUAGES else "tw"

    vs = (item.get("visual_style") or prefs.get("visual_style") or project_manager.LAST_VISUAL_STYLE or "").strip()
    if vs not in config.VISUAL_STYLE_OPTIONS:
        vs = project_manager.LAST_VISUAL_STYLE

    narr_opts = config.narrator_person_options()
    nar = (item.get("narrator") or prefs.get("narrator") or project_manager.LAST_NARRATOR or "").strip()
    if nar and narr_opts and nar not in narr_opts:
        nar = project_manager.LAST_NARRATOR or (narr_opts[0] if narr_opts else "")

    project_manager.LAST_YT_LANGUAGE = lang
    project_manager.LAST_VISUAL_STYLE = vs
    project_manager.LAST_NARRATOR = nar

    ch = (item.get("channel_id") or prefs.get("channel") or "").strip()
    if ch:
        config.save_yt_tools_prefs({
            "channel": ch,
            "language": lang,
            "narrator": nar,
            "visual_style": vs,
            "reserved": (prefs.get("reserved") or "").strip(),
        })
    return {"channel": ch, "language": lang, "narrator": nar, "visual_style": vs}


def launch_queue_item_gui(item: dict) -> int:
    """跳过欢迎屏 / 列表选择 / 操作菜单，直达该条目的「打开摘要编辑」。"""
    if not isinstance(item, dict):
        print("无效的 queue item", file=sys.stderr)
        return 1

    import tkinter as tk

    try:
        import tkinterdnd2 as TkinterDnD

        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()

    root.title("AIComposer — YT 工具")
    try:
        root.geometry("1x1+-3000+-3000")
        root.resizable(False, False)
    except tk.TclError:
        pass

    prefs = apply_queue_item_yt_prefs(item)
    ch = (item.get("channel_id") or prefs.get("channel") or "").strip()
    if not ch:
        ch_path = (item.get("channel_path") or "").strip()
        if ch_path:
            ch = config.get_channel_id(os.path.basename(ch_path))
    if not ch:
        print("队列条目缺少 channel_id", file=sys.stderr)
        return 1

    lang = prefs.get("language") or "tw"
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path:
        list_path = config.yt_text_download_list_json_path(ch)

    row_keys = [
        k
        for k in (
            item.get("row_key"),
            item.get("row_id"),
            item.get("url"),
            item.get("workflow_pid"),
        )
        if (k or "").strip()
    ]
    auto_key = row_keys[0] if row_keys else ""

    from gui.downloader import MediaGUIManager

    _yt_log = tk.Text(root)

    def _yt_log_fn(w, m):
        try:
            w.insert(tk.END, m + "\n")
        except Exception:
            pass

    yt_gui = MediaGUIManager(root, ch, "temp", {}, _yt_log_fn, _yt_log, language=lang)

    def _poll_standalone_exit():
        try:
            if not root.winfo_exists():
                return
            has_dialog = any(isinstance(w, tk.Toplevel) for w in root.winfo_children())
            if not has_dialog:
                root.quit()
                return
        except tk.TclError:
            return
        root.after(350, _poll_standalone_exit)

    def _run():
        try:
            yt_gui.open_hot_videos_from_list_json(
                list_path,
                auto_open_summary_row_keys=row_keys,
            )
        finally:
            root.after(350, _poll_standalone_exit)

    root.after(0, _run)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass
    return 0


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 program/video_choice_queue.json 逐条取用 GUI 导出的视频选择。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出队列条目")
    p_list.add_argument(
        "--remaining",
        action="store_true",
        help="仅列出尚未取用的条目（cursor 之后）",
    )
    p_list.add_argument("--json", action="store_true", help="JSON 输出")

    p_next = sub.add_parser("next", help="取下一条（按 cursor 顺序）")
    p_next.add_argument("--json", action="store_true")
    p_next.add_argument(
        "--with-detail",
        action="store_true",
        help="附带从 list JSON 解析的完整 video_detail",
    )
    p_next.add_argument(
        "--no-advance",
        action="store_true",
        help="只预览当前条，不前移 cursor",
    )
    p_next.add_argument(
        "--no-gui",
        action="store_true",
        help="不启动 GUI（仅输出 JSON / 文本，供 agent 使用）",
    )

    p_done = sub.add_parser("done", help="前移 cursor（兼容旧工作流）")
    p_done.add_argument("choice_id", nargs="?", default="")
    p_done.add_argument("--json", action="store_true")

    p_skip = sub.add_parser("skip", help="前移 cursor（跳过当前条）")
    p_skip.add_argument("choice_id", nargs="?", default="")
    p_skip.add_argument("--json", action="store_true")

    p_resolve = sub.add_parser("resolve", help="按 choice_id 解析完整 video detail")
    p_resolve.add_argument("choice_id")
    p_resolve.add_argument("--json", action="store_true")

    sub.add_parser("path", help="打印队列文件绝对路径")
    sub.add_parser("reset-cursor", help="将 cursor 重置为 0")

    p_status = sub.add_parser("status", help="队列统计")
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "path":
        print(os.path.abspath(VIDEO_CHOICE_QUEUE_JSON))
        return 0

    if args.command == "list":
        items = list_queue_items(remaining_only=args.remaining)
        if args.json:
            _print_json(items)
        else:
            for it in items:
                print(
                    f"{it.get('choice_id', '?'):12}  "
                    f"{(it.get('title') or it.get('row_key') or '')[:80]}"
                )
        return 0

    if args.command == "next":
        item = pick_next_item(advance=not args.no_advance)
        if not item:
            if args.json:
                _print_json(None)
            else:
                print("（队列已取完）", file=sys.stderr)
            return 1
        if args.with_detail:
            detail = resolve_video_detail_from_queue_item(item)
            payload = {"queue_item": item, "video_detail": detail}
        else:
            payload = item
        if args.json:
            _print_json(payload)
        if args.no_gui:
            if not args.json:
                print(f"choice_id: {item.get('choice_id')}")
                print(f"title: {item.get('title')}")
                print(f"list: {item.get('list_json_path')}")
                print(f"row_key: {item.get('row_key')}")
            return 0
        return launch_queue_item_gui(item)

    if args.command == "done":
        cursor = advance_queue_cursor()
        if args.json:
            _print_json({"cursor": cursor, "remaining": len(list_queue_items(remaining_only=True))})
        else:
            print(f"cursor → {cursor}")
        return 0

    if args.command == "skip":
        cursor = advance_queue_cursor()
        if args.json:
            _print_json({"cursor": cursor, "remaining": len(list_queue_items(remaining_only=True))})
        else:
            print(f"已跳过，cursor → {cursor}")
        return 0

    if args.command == "resolve":
        payload = resolve_queue_item_by_id(args.choice_id)
        if not payload:
            print(f"未找到 choice_id: {args.choice_id}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(payload)
        else:
            qi = payload["queue_item"]
            print(f"title: {qi.get('title')}")
            print(f"has video_detail: {payload.get('video_detail') is not None}")
        return 0

    if args.command == "reset-cursor":
        reset_queue_cursor()
        print("cursor 已重置为 0")
        return 0

    if args.command == "status":
        data = load_queue()
        total = len(data.get("items") or [])
        cursor = int(data.get("cursor") or 0)
        remaining = max(0, total - cursor)
        payload = {
            "path": os.path.abspath(VIDEO_CHOICE_QUEUE_JSON),
            "total": total,
            "cursor": cursor,
            "remaining": remaining,
            "exported_at": data.get("exported_at"),
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"队列: {payload['path']}")
            print(f"合计: {total}  已取用: {cursor}  剩余: {remaining}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
