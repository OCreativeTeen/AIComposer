"""Telegram CLI 听筒：同步当前 GUI 窗口，执行刚听到的那一条命令。"""

from __future__ import annotations

from collections.abc import Callable

import json
import os
import re
from datetime import datetime, timezone

import config
from cli.commands import dispatch, short_cli, split_command
from cli.mode import get_mode
from cli.screens import current_screen_info

Notify = Callable[[str], None]


def _whole_story_images_path() -> str:
    return getattr(config, "WHOLE_STORY_IMAGES_JSON", "") or ""


def load_whole_story_image_record() -> dict:
    """NotebookLM 封面图记录：files / selected / selected_path / pending_pick。"""
    empty = {
        "files": [],
        "selected": 0,
        "selected_path": "",
        "pending_pick": False,
        "telegram_sent_at": "",
        "picked_at": "",
        "updated_at": "",
    }
    path = _whole_story_images_path()
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    files_raw = data.get("files")
    files: list[str] = []
    if isinstance(files_raw, list):
        for item in files_raw:
            p = (item or "").strip() if isinstance(item, str) else ""
            if p and os.path.isfile(p) and p not in files:
                files.append(p)
    try:
        selected = int(data.get("selected") or 0)
    except (TypeError, ValueError):
        selected = 0
    selected_path = str(data.get("selected_path") or "").strip()
    if selected_path and not os.path.isfile(selected_path):
        selected_path = ""
    if not selected_path and 1 <= selected <= len(files):
        selected_path = files[selected - 1]
    pending = bool(data.get("pending_pick")) and bool(files)
    if selected >= 1 and not pending:
        pending = False
    if selected < 0 or selected > len(files):
        selected = 0
        selected_path = ""
    return {
        "files": files,
        "selected": selected,
        "selected_path": selected_path,
        "pending_pick": pending,
        "telegram_sent_at": str(data.get("telegram_sent_at") or ""),
        "picked_at": str(data.get("picked_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
    }


def load_whole_story_images() -> list[str]:
    """NotebookLM 整篇故事 infographic 下载路径（Windows Downloads）。"""
    return list(load_whole_story_image_record().get("files") or [])


def _write_whole_story_image_record(
    files: list[str],
    *,
    selected: int = 0,
    pending_pick: bool = False,
    telegram_sent_at: str | None = None,
    picked_at: str | None = None,
) -> list[str]:
    prev = load_whole_story_image_record()
    sel = max(0, int(selected or 0))
    selected_path = ""
    if 1 <= sel <= len(files):
        selected_path = files[sel - 1]
    ts = (
        telegram_sent_at
        if telegram_sent_at is not None
        else str(prev.get("telegram_sent_at") or "")
    )
    pk = picked_at if picked_at is not None else str(prev.get("picked_at") or "")
    path = _whole_story_images_path()
    payload = {
        "files": files,
        "selected": sel,
        "selected_path": selected_path,
        "pending_pick": bool(pending_pick) and bool(files) and sel < 1,
        "telegram_sent_at": ts,
        "picked_at": pk,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if sel >= 1:
        payload["pending_pick"] = False
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return files


def save_whole_story_images(paths: list[str]) -> list[str]:
    """记住本轮 nbi 下载的封面路径（whole_story_images.json）。"""
    files: list[str] = []
    for item in paths or []:
        p = os.path.normpath(os.path.abspath((item or "").strip()))
        if p and os.path.isfile(p) and p not in files:
            files.append(p)
    return _write_whole_story_image_record(
        files,
        selected=0,
        pending_pick=bool(files),
        telegram_sent_at="",
        picked_at="",
    )


def mark_whole_story_telegram_sent() -> dict:
    """itc 已把封面图发到 Telegram，等待用户选 1/2/3。"""
    rec = load_whole_story_image_record()
    files = list(rec.get("files") or [])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_whole_story_image_record(
        files,
        selected=int(rec.get("selected") or 0),
        pending_pick=True,
        telegram_sent_at=stamp,
        picked_at=str(rec.get("picked_at") or ""),
    )
    return load_whole_story_image_record()


def record_whole_story_pick(index: int) -> dict:
    """记下用户选中的封面序号（1-based），不贴进 Grok。"""
    rec = load_whole_story_image_record()
    files = list(rec.get("files") or [])
    idx = int(index)
    if idx < 1 or idx > len(files):
        raise ValueError(f"没有第 {idx} 张封面（共 {len(files)} 张）")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_whole_story_image_record(
        files,
        selected=idx,
        pending_pick=False,
        picked_at=stamp,
    )
    out = load_whole_story_image_record()
    return {"index": idx, "path": out.get("selected_path") or files[idx - 1]}


def select_whole_story_image(index: int) -> dict:
    """兼容旧名；委托 ``record_whole_story_pick``。"""
    return record_whole_story_pick(index)


def selected_whole_story_image_path() -> str:
    rec = load_whole_story_image_record()
    p = str(rec.get("selected_path") or "").strip()
    if p and os.path.isfile(p):
        return p
    idx = int(rec.get("selected") or 0)
    files = list(rec.get("files") or [])
    if 1 <= idx <= len(files):
        return files[idx - 1]
    return ""


def whole_story_pick_pending() -> bool:
    rec = load_whole_story_image_record()
    return bool(rec.get("pending_pick")) and bool(rec.get("files"))


def load_grok_scene_videos() -> list[dict]:
    """Grok 各场景 video clip 下载路径，已按 scene 1…N 排序。

    每项 ``{"scene": int, "path": str}``。缺文件的项会被丢掉。
    """
    path = getattr(config, "GROK_SCENE_VIDEOS_JSON", "") or ""
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        return []
    out: list[dict] = []
    for item in files:
        if isinstance(item, str):
            p = os.path.normpath(os.path.abspath(item.strip()))
            if p and os.path.isfile(p):
                out.append({"scene": len(out) + 1, "path": p})
            continue
        if not isinstance(item, dict):
            continue
        p = os.path.normpath(os.path.abspath((item.get("path") or "").strip()))
        if not p or not os.path.isfile(p):
            continue
        try:
            scene = int(item.get("scene") or 0)
        except (TypeError, ValueError):
            scene = 0
        out.append({"scene": scene, "path": p})
    numbered = [x for x in out if x["scene"] > 0]
    if numbered:
        numbered.sort(key=lambda x: x["scene"])
        return numbered
    for i, item in enumerate(out, 1):
        item["scene"] = i
    return out


def save_grok_scene_videos(items: list[dict] | list[str]) -> list[dict]:
    """按场景顺序记住本轮 Grok video clip（Windows Downloads）。"""
    files: list[dict] = []
    for i, item in enumerate(items or [], 1):
        if isinstance(item, str):
            p = os.path.normpath(os.path.abspath((item or "").strip()))
            scene = i
        elif isinstance(item, dict):
            p = os.path.normpath(os.path.abspath((item.get("path") or "").strip()))
            try:
                scene = int(item.get("scene") or i)
            except (TypeError, ValueError):
                scene = i
        else:
            continue
        if not p or not os.path.isfile(p):
            continue
        files.append({"scene": scene, "path": p})
    files.sort(key=lambda x: x["scene"])
    path = getattr(config, "GROK_SCENE_VIDEOS_JSON", "") or ""
    if path:
        payload = {
            "files": files,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return files


def grok_tab_count_for_prompt_choice(label: str) -> int:
    """Map LM 提示选项 → 场景数 / Grok Imagine 标签数。

    N Step Story → N（2–6）；其它（Short / Mini / Long…）→ 1。
    """
    raw = (label or "").strip()
    if not raw:
        return 0
    low = raw.lower().replace("–", "-").replace("—", "-")
    for n, patterns in (
        (6, (r"(^|[^\d])6\s*[-_]?\s*step\b", "六步", "6步")),
        (5, (r"(^|[^\d])5\s*[-_]?\s*step\b", "五步", "5步")),
        (4, (r"(^|[^\d])4\s*[-_]?\s*step\b", "四步", "4步")),
        (3, (r"(^|[^\d])3\s*[-_]?\s*step\b", "三步", "3步")),
        (
            2,
            (
                r"(^|[^\d])2\s*[-_]?\s*step\b",
                "两步",
                "二步",
                "2步",
            ),
        ),
    ):
        pat, *zh = patterns
        if re.search(pat, low) or any(z in raw for z in zh):
            return n
    return 1


def scene_count_from_prompt_text(prompt: str) -> int:
    """从 LM 长提示里解析 ``has N scene(s)``。"""
    text = (prompt or "").strip()
    if not text:
        return 0
    low = text.lower().replace("–", "-").replace("—", "-")
    for pat in (
        r"has\s+(\d+)\s+scenes?\b",
        r"the\s+whole\s+(?:\(one\)\s+)?story\s+has\s+(\d+)\s+scenes?",
        r"output\s*\(\s*(\d+)\s+scenes?\s*\)",
        r"(\d+)\s+scenes?\s*\(\s*\d+\s+json",
    ):
        m = re.search(pat, low)
        if m:
            try:
                return max(1, int(m.group(1)))
            except (TypeError, ValueError):
                continue
    return 0


def story_scene_count(*, prompt_text: str = "") -> int:
    """当前故事应有几场：优先 ``story_scene_prompt_choice``，否则从 prompt 解析。"""
    rec = load_story_scene_prompt_choice()
    try:
        n = int(rec.get("scenes") or rec.get("tabs") or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 1:
        return n
    label = (rec.get("label") or "").strip()
    if label:
        mapped = grok_tab_count_for_prompt_choice(label)
        if mapped >= 1:
            return mapped
    return scene_count_from_prompt_text(prompt_text)


def load_story_scene_prompt_choice() -> dict:
    """Last LM prompt picked on the 分镜窗 (``story_scene_prompt_choice``)."""
    path = getattr(config, "STORY_SCENE_PROMPT_CHOICE_JSON", "") or ""
    empty = {"label": "", "tabs": 0, "scenes": 0}
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    label = str(data.get("label") or "").strip()
    tabs = data.get("tabs")
    try:
        tabs_i = int(tabs)
    except (TypeError, ValueError):
        tabs_i = grok_tab_count_for_prompt_choice(label)
    if not label:
        return dict(empty)
    if tabs_i < 1:
        tabs_i = grok_tab_count_for_prompt_choice(label) or 1
    return {"label": label, "tabs": tabs_i, "scenes": tabs_i}


def save_story_scene_prompt_choice(label: str) -> dict:
    """Remember 分镜窗 LM 提示选择，供 ``grok_image`` / ``scene_choice`` 决定场景数。"""
    text = (label or "").strip()
    tabs = grok_tab_count_for_prompt_choice(text)
    payload = {
        "label": text,
        "tabs": tabs,
        "scenes": tabs,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = getattr(config, "STORY_SCENE_PROMPT_CHOICE_JSON", "") or ""
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return payload


def _chrome_profiles_used_path() -> str:
    return getattr(config, "CHROME_PROFILES_USED_JSON", "") or ""


def load_chrome_profiles_used() -> dict:
    """本轮（跨多条故事）已用过的 Chrome 账号，用来建议换号避开额度。"""
    empty = {"used": [], "by_kind": {}}
    path = _chrome_profiles_used_path()
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    used = data.get("used")
    if not isinstance(used, list):
        used = []
    by_kind = data.get("by_kind")
    if not isinstance(by_kind, dict):
        by_kind = {}
    return {
        "used": [str(x).strip() for x in used if str(x).strip()],
        "by_kind": {
            str(k): [str(x).strip() for x in (v or []) if str(x).strip()]
            for k, v in by_kind.items()
            if isinstance(v, list)
        },
        "updated_at": data.get("updated_at") or "",
    }


def record_chrome_profile_used(kind: str, label: str) -> dict:
    """记下本轮选过的 Gemini / NotebookLM / Grok 账号。"""
    text = (label or "").strip()
    key = (kind or "").strip().lower() or "other"
    data = load_chrome_profiles_used()
    used = list(data.get("used") or [])
    if text and text not in used:
        used.append(text)
    by_kind = dict(data.get("by_kind") or {})
    bucket = list(by_kind.get(key) or [])
    if text and text not in bucket:
        bucket.append(text)
    by_kind[key] = bucket
    payload = {
        "used": used,
        "by_kind": by_kind,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = _chrome_profiles_used_path()
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return payload


def chrome_profile_choice_labels(kind: str = "") -> tuple[list[str], int | None]:
    """列出 Chrome 账号，标注本轮已用过的；返回 (显示文案, 建议的 1-based 序号)。"""
    profiles = config.list_gemini_chrome_profiles()
    data = load_chrome_profiles_used()
    used = set(data.get("used") or [])
    kind_used = set((data.get("by_kind") or {}).get((kind or "").strip().lower()) or [])
    labels: list[str] = []
    suggest: int | None = None
    for i, item in enumerate(profiles, 1):
        label = (item.get("label") or "").strip()
        notes: list[str] = []
        if label in used:
            if label in kind_used and kind:
                notes.append(f"本轮 {kind} 已用过")
            else:
                notes.append("本轮已用过")
        elif suggest is None:
            suggest = i
            notes.append("建议：还没用过，可避开额度")
        extra = f"  ← {'；'.join(notes)}" if notes else ""
        labels.append(f"{label}{extra}")
    if suggest is None and profiles:
        labels[0] = labels[0] + "  ← 建议（本轮账号都用过了，可再选或换号）"
        suggest = 1
    return labels, suggest


class TelegramCliSession:
    """听筒：跟着 GUI 窗口同步，执行刚听到的那一条 CLI。"""

    def __init__(self, mode: str | None = None) -> None:
        self.last_announced_screen = ""
        self.mode = mode or get_mode()

    def busy_with_flow(self) -> bool:
        return False

    def announce_sync(self) -> str:
        from cli.gui_session import format_listen_sync

        info = current_screen_info()
        self.last_announced_screen = (info.get("screen") or "none").strip() or "none"
        return format_listen_sync(info)

    def handle(self, text: str, notify: Notify | None = None) -> tuple[bool, str]:
        del notify
        raw = (text or "").strip()
        if not raw:
            return False, "empty command"
        if whole_story_pick_pending():
            digit = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if digit.isdigit() and " " not in raw and len(digit) <= 2:
                return dispatch(f"{short_cli('whole_story_pick')} {digit}")
        cmd, _ = split_command(raw)
        if cmd in ("sync", "where", "here"):
            return True, self.announce_sync()
        return dispatch(raw)


def welcome_text(mode: str | None = None) -> str:
    del mode
    return (
        "Telegram 听筒已就绪（人 / Hermes 当操作员）。\n"
        "若电脑上还没有 STORY/SCENE，我会用队列启动：\n"
        "python -m aiagent.pick_video_choice next --with-detail --json\n"
        "这是队列会话，随后可用 pick / pick 1 / pick 2 选故事（已完成的也能重做）。\n"
        "若已是 GUI_pm 手工会话：不自动 next，pick 已关掉，我只跟着窗口同步。\n"
        "你进到 STORY/SCENE 时我会主动告诉你能发哪些短 CLI。发 sync 可再同步一次。"
    )

