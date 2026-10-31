"""t168u: 每个 STORY 的 AI 生成历史（名字 / 摘要 / 场景），放在 WORKING_DIR 下的临时文件里，只追加，不覆盖。

文件：<WORKING_DIR>/<pid 或 id>_gen_history.json（UTF-8）
{"titles": [{"run", "backend", "time", "title"}], "summaries": [{"run", "backend", "time", "text"}],
 "scene_sets": [{"run", "backend", "time", "scenes": [...]}]}
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time

_LOCK = threading.Lock()
KINDS = ("titles", "summaries", "scene_sets")


def story_key(video_detail) -> str:
    key = ""
    try:
        import project_manager

        key = project_manager.list_json_row_workflow_pid(video_detail) or ""
    except Exception:  # noqa: BLE001
        key = ""
    if not key and isinstance(video_detail, dict):
        key = str(video_detail.get("id") or video_detail.get("url") or video_detail.get("title") or "")
    key = re.sub(r"[^\w\-]+", "_", key.strip(), flags=re.U).strip("_")[:80]
    return key or "story"


def history_path(video_detail, working_dir: str | None = None) -> str:
    if not working_dir:
        import config

        working_dir = config.WORKING_DIR
    return os.path.join(working_dir, f"{story_key(video_detail)}_gen_history.json")


def display_backend(raw) -> str:
    """t169u: 存的原值（按钮名 / 模型 id）→ 显示名 Grok / Gemini / DeepSeek / Strata。"""
    r = str(raw or "").strip()
    low = r.lower()
    if not low or low == "?":
        return "未知"
    if low == "llm":
        # t168 早期记录：摘要走 LLMApi() 默认路径 = 本机 Strata，失败才转手动窗口，所以不能百分之百确定
        return "Strata（默认，未确认）"
    if low == "manual" or low == "手动":
        return "手动窗口"
    for key, name in (("deepseek", "DeepSeek"), ("gemini", "Gemini"), ("grok", "Grok"),
                      ("strata", "Strata"), ("qwen", "Strata")):
        if key in low:
            return name
    return r


def _empty() -> dict:
    return {k: [] for k in KINDS}


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    for k in KINDS:
        if not isinstance(data.get(k), list):
            data[k] = []
    return data


def _write_atomic(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gen_history_", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _next_run(items: list) -> int:
    runs = [int(x.get("run") or 0) for x in items if isinstance(x, dict) and str(x.get("run") or "").isdigit()]
    return (max(runs) if runs else 0) + 1


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def append(path: str, kind: str, backend: str, payload) -> int:
    """追加一次生成。titles: payload 是名字列表（同一个 run）；summaries: 文字；scene_sets: 场景列表。返回 run 号。"""
    if kind not in KINDS:
        raise ValueError(kind)
    with _LOCK:
        data = load(path)
        items = data[kind]
        run = _next_run(items)
        t = _now()
        backend = (backend or "").strip() or "?"
        if kind == "titles":
            for name in payload or []:
                name = str(name or "").strip()
                if name:
                    items.append({"run": run, "backend": backend, "time": t, "title": name})
        elif kind == "summaries":
            text = str(payload or "").strip()
            if not text:
                return 0
            items.append({"run": run, "backend": backend, "time": t, "text": text})
        else:
            scenes = [s for s in (payload or []) if isinstance(s, dict)]
            if not scenes:
                return 0
            items.append({"run": run, "backend": backend, "time": t, "scenes": scenes})
        _write_atomic(path, data)
        return run


def record(video_detail, kind: str, backend: str, payload) -> int:
    """出错只打日志，不影响生成本身。"""
    try:
        path = history_path(video_detail)
        run = append(path, kind, backend, payload)
        if run:
            print(f"🗂 生成历史已追加 {kind} 第 {run} 次（{backend}）→ {path}")
        return run
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 生成历史没有写入：{exc}")
        return 0
