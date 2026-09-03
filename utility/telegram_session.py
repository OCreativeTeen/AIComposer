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
        "expected": 0,
        "generate_clicked": 0,
        "generate_started_at": "",
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
    try:
        expected = int(data.get("expected") or 0)
    except (TypeError, ValueError):
        expected = 0
    try:
        generate_clicked = int(data.get("generate_clicked") or 0)
    except (TypeError, ValueError):
        generate_clicked = 0
    return {
        "files": files,
        "selected": selected,
        "selected_path": selected_path,
        "pending_pick": pending,
        "telegram_sent_at": str(data.get("telegram_sent_at") or ""),
        "picked_at": str(data.get("picked_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
        "expected": max(0, expected),
        "generate_clicked": max(0, generate_clicked),
        "generate_started_at": str(data.get("generate_started_at") or ""),
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
    expected: int | None = None,
    generate_clicked: int | None = None,
    generate_started_at: str | None = None,
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
    exp = int(expected) if expected is not None else int(prev.get("expected") or 0)
    clicked = (
        int(generate_clicked)
        if generate_clicked is not None
        else int(prev.get("generate_clicked") or 0)
    )
    started = (
        generate_started_at
        if generate_started_at is not None
        else str(prev.get("generate_started_at") or "")
    )
    payload = {
        "files": files,
        "selected": sel,
        "selected_path": selected_path,
        "pending_pick": bool(pending_pick) and bool(files) and sel < 1,
        "telegram_sent_at": ts,
        "picked_at": pk,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expected": max(0, exp),
        "generate_clicked": max(0, clicked),
        "generate_started_at": started,
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


def mark_notebooklm_generate_started(times: int) -> dict:
    """nbi 已点 Generate ×N，尚未拷图。清掉上一轮封面路径。"""
    n = max(1, int(times or 3))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_whole_story_image_record(
        [],
        selected=0,
        pending_pick=False,
        telegram_sent_at="",
        picked_at="",
        expected=n,
        generate_clicked=n,
        generate_started_at=stamp,
    )
    return load_whole_story_image_record()


def save_whole_story_images(paths: list[str]) -> list[str]:
    """记住本轮 itc 下载到 Windows Downloads 的封面路径（whole_story_images.json）。"""
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
    """True when the owner should reply 1/2/3 for a whole-story cover."""
    rec = load_whole_story_image_record()
    files = list(rec.get("files") or [])
    if not files:
        return False
    if int(rec.get("selected") or 0) >= 1:
        return False
    return bool(rec.get("pending_pick"))


def dismiss_whole_story_pick_pending() -> None:
    """Stop treating stray digits as cover picks (e.g. during scnlm/scnvs)."""
    rec = load_whole_story_image_record()
    if not rec.get("pending_pick"):
        return
    files = list(rec.get("files") or [])
    _write_whole_story_image_record(
        files,
        selected=int(rec.get("selected") or 0),
        pending_pick=False,
    )


def _scene_choice_pick_path() -> str:
    return getattr(config, "SCENE_CHOICE_PICK_JSON", "") or ""


def load_scene_choice_pick() -> dict:
    """Hermes 等待 scnlm/scnvs 时：kind / max_n / pending_pick / picked。"""
    empty = {
        "kind": "",
        "max_n": 0,
        "pending_pick": False,
        "picked": 0,
        "updated_at": "",
    }
    path = _scene_choice_pick_path()
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    out = dict(empty)
    out["kind"] = str(data.get("kind") or "").strip().lower()
    try:
        out["max_n"] = max(0, int(data.get("max_n") or 0))
    except (TypeError, ValueError):
        out["max_n"] = 0
    out["pending_pick"] = bool(data.get("pending_pick"))
    try:
        out["picked"] = max(0, int(data.get("picked") or 0))
    except (TypeError, ValueError):
        out["picked"] = 0
    out["updated_at"] = str(data.get("updated_at") or "").strip()
    return out


def _write_scene_choice_pick(payload: dict) -> dict:
    path = _scene_choice_pick_path()
    if not path:
        return payload
    payload = dict(payload or {})
    payload["updated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass
    return payload


def start_scene_choice_pick(kind: str, max_n: int) -> dict:
    """开始等待 Telegram 序号（``kind`` = ``lm`` | ``vs``）。"""
    k = (kind or "").strip().lower()
    payload = {
        "kind": k,
        "max_n": max(0, int(max_n)),
        "pending_pick": bool(k and max_n > 0),
        "picked": 0,
    }
    _write_scene_choice_pick(payload)
    return load_scene_choice_pick()


def clear_scene_choice_pick() -> None:
    _write_scene_choice_pick(
        {"kind": "", "max_n": 0, "pending_pick": False, "picked": 0}
    )


def scene_choice_pick_pending() -> bool:
    rec = load_scene_choice_pick()
    return bool(rec.get("pending_pick")) and int(rec.get("max_n") or 0) > 0


def record_scene_choice_pick(index: int) -> dict:
    """听筒 / client 收到序号后写入 JSON。"""
    rec = load_scene_choice_pick()
    if not rec.get("pending_pick"):
        return rec
    max_n = int(rec.get("max_n") or 0)
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return rec
    if not (1 <= idx <= max_n):
        return rec
    rec["picked"] = idx
    rec["pending_pick"] = False
    _write_scene_choice_pick(rec)
    return load_scene_choice_pick()


def take_scene_choice_pick(kind: str) -> int:
    """若 ``kind`` 匹配且已选，返回序号并清空记录；否则 0。"""
    want = (kind or "").strip().lower()
    rec = load_scene_choice_pick()
    if rec.get("kind") != want:
        return 0
    if rec.get("pending_pick"):
        return 0
    idx = int(rec.get("picked") or 0)
    clear_scene_choice_pick()
    return idx if idx >= 1 else 0


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
    try:
        from cli.video_choice_queue import save_grok_clips_to_active_video_detail

        save_grok_clips_to_active_video_detail(files)
    except Exception:
        pass
    return files


def scene_count_from_prompt_text(prompt: str) -> int:
    """从 LM 长提示里解析 ``has N scene(s)``（仅 ``scnge`` 前、尚无 scene_content 时用）。"""
    text = (prompt or "").strip()
    if not text:
        return 0
    low = text.lower().replace("–", "-").replace("—", "-")
    for pat in (
        r"has\s+(\d+)\s+scenes?\b",
        r"the\s+whole\s+(?:\(one\)\s+)?story\s+has\s+(\d+)\s+scenes?",
        r"has\s+(\d+)\s+scene\s*\(\s*\d+\s+json",
        r"output\s*\(\s*(\d+)\s+scenes?\s*\)",
        r"(\d+)\s+scenes?\s*\(\s*\d+\s+json",
        r"the\s+story\s+has\s+(\d+)\s+scenes?",
    ):
        m = re.search(pat, low)
        if m:
            try:
                return max(1, int(m.group(1)))
            except (TypeError, ValueError):
                continue
    return 0


def grok_tab_count_for_prompt_choice(label: str) -> int:
    """Map LM 提示选项 → 场景数 / Grok Imagine 标签数。

    ``N Step Story`` → N（2–6）；其它（Short / Mini / Long / Talk …）→ 1。
    ``scnlm`` 选完即可用，不必等长 prompt 刷新或解析剪贴板。
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


def scene_count_from_lm_label(label: str) -> int:
    """``grok_tab_count_for_prompt_choice`` 的别名。"""
    return grok_tab_count_for_prompt_choice(label)


def story_scene_count(*, prompt_text: str = "", lm_label: str = "") -> int:
    """当前故事场景数。

  1. 已 scnsave：读当前 ``video_detail.scene_content`` 数组长度（唯一真源）
  2. 尚无 scene_content（``scnge`` 前）：``scnlm`` 选的 LM 标签 → ``grok_tab_count_for_prompt_choice``
  3. 再不行：从 LM 长 prompt 解析 ``has N scenes``
    """
    try:
        from cli.video_choice_queue import active_video_detail_scene_count

        n = int(active_video_detail_scene_count() or 0)
    except Exception:
        n = 0
    if n >= 1:
        return n
    label = (lm_label or "").strip()
    if not label:
        label = _active_scene_lm_label()
    if label:
        mapped = grok_tab_count_for_prompt_choice(label)
        if mapped >= 1:
            return mapped
    return scene_count_from_prompt_text(prompt_text)


def _active_scene_lm_label() -> str:
    """读 SCENE bridge 当前「选LM提示」文案（第一行）。"""
    try:
        from cli.bridge import send_bridge_command
        from cli.screens import SCREEN_STORY_SCENE

        ok, got = send_bridge_command(
            screen=SCREEN_STORY_SCENE,
            op="get",
            field="lm",
            timeout_s=4.0,
        )
        if ok:
            return (got or "").split("\n", 1)[0].strip()
    except Exception:
        pass
    return ""


def _grok_scene_video_nb_path() -> str:
    return getattr(config, "GROK_SCENE_VIDEO_NB_JSON", "") or ""


def _video_nb_index_from(data: dict) -> int:
    import config_prompt

    raw = data.get("video_nb_index")
    try:
        i = int(raw)
    except (TypeError, ValueError):
        return config_prompt.GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    n = len(config_prompt.GROK_SCENE_VIDEO_NB_VARIANTS) or 8
    if i < 1 or i > n:
        return config_prompt.GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    return i


def load_grok_scene_video_nb_index() -> int:
    """Grok scene video NotebookLM variant index 1…8 (see ``GROK_SCENE_VIDEO_NB_VARIANTS``)."""
    import config_prompt

    path = _grok_scene_video_nb_path()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return _video_nb_index_from(data)
        except (OSError, json.JSONDecodeError):
            pass
    return config_prompt.GROK_SCENE_VIDEO_NB_DEFAULT_INDEX


def save_grok_scene_video_nb_index(index: int) -> dict:
    """Remember Grok video prompt variant for ``grv`` / ``nbv``."""
    import config_prompt

    i = int(index)
    n = len(config_prompt.GROK_SCENE_VIDEO_NB_VARIANTS) or 8
    if i < 1 or i > n:
        raise ValueError(f"video_nb_index must be 1…{n}, got {index!r}")
    payload = {
        "video_nb_index": i,
        "video_nb_label": config_prompt.grok_scene_video_nb_choice_label(i),
        "video_nb_updated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    path = _grok_scene_video_nb_path()
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
    """跨次运行 Chrome 账号记录：本轮已用 + Grok Imagine 上次成功 profile。"""
    empty = {"used": [], "by_kind": {}, "grok_last": {"profile": "", "index": 0}}
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
    grok_last = data.get("grok_last")
    if not isinstance(grok_last, dict):
        grok_last = {}
    try:
        grok_index = int(grok_last.get("index") or 0)
    except (TypeError, ValueError):
        grok_index = 0
    return {
        "used": [str(x).strip() for x in used if str(x).strip()],
        "by_kind": {
            str(k): [str(x).strip() for x in (v or []) if str(x).strip()]
            for k, v in by_kind.items()
            if isinstance(v, list)
        },
        "grok_last": {
            "profile": str(grok_last.get("profile") or "").strip(),
            "index": max(0, grok_index),
            "launched_at": str(grok_last.get("launched_at") or ""),
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
    grok_last = data.get("grok_last") if isinstance(data.get("grok_last"), dict) else {}
    payload = {
        "used": used,
        "by_kind": by_kind,
        "grok_last": grok_last,
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


def _grok_imagine_profile_ring() -> list[int]:
    return list(config.list_grok_imagine_profile_indices() or [1])


def load_grok_imagine_last_profile() -> dict:
    """上次成功 ``grv`` 的 Chrome profile（存在 ``chrome_profiles_used.json``）。"""
    data = load_chrome_profiles_used()
    grok = data.get("grok_last") if isinstance(data.get("grok_last"), dict) else {}
    try:
        index = int(grok.get("index") or 0)
    except (TypeError, ValueError):
        index = 0
    return {
        "profile": str(grok.get("profile") or "").strip(),
        "index": max(0, index),
        "launched_at": str(grok.get("launched_at") or ""),
    }


def save_grok_imagine_last_profile(*, profile: str = "", index: int = 0) -> dict:
    """记下本次成功 grv 的 profile，供下一条故事切到轮换环里的下一个。"""
    profiles = list(config.list_gemini_chrome_profiles() or [])
    label = (profile or "").strip()
    idx = int(index or 0)
    if idx < 1 and label:
        idx = _index_for_notebooklm_label(label, profiles)
    if idx < 1:
        idx = _grok_imagine_profile_ring()[0]
    if not label and 1 <= idx <= len(profiles):
        label = str(profiles[idx - 1].get("label") or "").strip()
    data = load_chrome_profiles_used()
    payload = {
        "used": list(data.get("used") or []),
        "by_kind": dict(data.get("by_kind") or {}),
        "grok_last": {
            "profile": label,
            "index": idx,
            "launched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
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


def next_grok_imagine_profile_index(*, override: int | None = None) -> tuple[int, str]:
    """本次 grv 该用的号：显式 override，否则在上次成功号的下一个（仅 GROK 轮换环）。"""
    ring = _grok_imagine_profile_ring()
    profiles = list(config.list_gemini_chrome_profiles() or [])
    n = len(profiles) or 1
    if override is not None:
        i = max(1, min(int(override), n))
    else:
        rec = load_grok_imagine_last_profile()
        last_i = int(rec.get("index") or 0)
        if last_i not in ring:
            i = ring[0]
        else:
            i = ring[(ring.index(last_i) + 1) % len(ring)]
    label = (
        str(profiles[i - 1].get("label") or "").strip()
        if 1 <= i <= len(profiles)
        else ""
    )
    return i, label


def _notebooklm_last_profile_path() -> str:
    return getattr(config, "NOTEBOOKLM_LAST_PROFILE_JSON", "") or ""


def load_notebooklm_last_profile() -> dict:
    """上次成功 ``nbi`` 的 Chrome profile（跨进程、跨次启动）。"""
    empty = {"profile": "", "index": 0, "launched_at": ""}
    path = _notebooklm_last_profile_path()
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    try:
        index = int(data.get("index") or 0)
    except (TypeError, ValueError):
        index = 0
    return {
        "profile": str(data.get("profile") or "").strip(),
        "index": max(0, index),
        "launched_at": str(data.get("launched_at") or ""),
    }


def _notebooklm_profile_ring() -> list[dict]:
    return list(config.list_gemini_chrome_profiles() or [])


def _index_for_notebooklm_label(label: str, profiles: list[dict] | None = None) -> int:
    want = (label or "").strip().lower()
    if not want:
        return 0
    rows = profiles if profiles is not None else _notebooklm_profile_ring()
    for i, item in enumerate(rows, 1):
        name = (item.get("label") or "").strip().lower()
        if name == want or (want and want in name) or (name and name in want):
            return i
    return 0


def save_notebooklm_last_profile(*, profile: str = "", index: int = 0) -> dict:
    """记下本次成功 nbi 用的 profile name，供下次切到下一个号。"""
    profiles = _notebooklm_profile_ring()
    label = (profile or "").strip()
    idx = int(index or 0)
    if idx < 1 and label:
        idx = _index_for_notebooklm_label(label, profiles)
    if idx < 1:
        idx = 1
    if not label and 1 <= idx <= len(profiles):
        label = str(profiles[idx - 1].get("label") or "").strip()
    payload = {
        "profile": label,
        "index": idx,
        "launched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = _notebooklm_last_profile_path()
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


def next_notebooklm_profile_index(*, override: int | None = None) -> tuple[int, str]:
    """本次 nbi 该用的号：显式 override，否则「上次成功号的下一个」（没有记录则从 1 起）。"""
    profiles = _notebooklm_profile_ring()
    n = len(profiles) or 1
    if override is not None:
        i = max(1, min(int(override), n))
        label = str(profiles[i - 1].get("label") or "").strip() if profiles else ""
        return i, label
    rec = load_notebooklm_last_profile()
    last_i = int(rec.get("index") or 0)
    last_name = str(rec.get("profile") or "").strip()
    if last_i < 1 and last_name:
        last_i = _index_for_notebooklm_label(last_name, profiles)
    if last_i < 1:
        nxt = 1
    else:
        nxt = (last_i % n) + 1
    label = str(profiles[nxt - 1].get("label") or "").strip() if profiles else ""
    return nxt, label


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
        if scene_choice_pick_pending():
            digit = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if digit.isdigit() and " " not in raw and len(digit) <= 2:
                record_scene_choice_pick(int(digit))
                return True, f"已记录 SCENE 选项 #{int(digit)}，Hermes 将继续。"
        if whole_story_pick_pending():
            digit = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if digit.isdigit() and " " not in raw and len(digit) <= 2:
                try:
                    record_whole_story_pick(int(digit))
                except ValueError as exc:
                    return False, str(exc)
                return True, f"已记录封面 #{int(digit)}，Hermes 将继续。"
        cmd, _ = split_command(raw)
        if cmd in ("sync", "where", "here"):
            return True, self.announce_sync()
        return dispatch(raw)


def welcome_text(mode: str | None = None) -> str:
    del mode
    return (
        "Telegram 听筒已就绪（人 / Hermes 当操作员）。\n"
        "长命令（nbi / scnge / grv …）后台执行：立刻回 ⏳，完成后再发 ok/error [任务号]。\n"
        "发 busy 可看当前队列。\n"
        "若电脑上还没有 STORY/SCENE，我会用队列启动：\n"
        "python -m cli.pick_video_choice next --with-detail --json\n"
        "这是队列会话，随后可用 pick / pick 1 / pick 2 选故事（已完成的也能重做）。\n"
        "若已是 GUI_pm 手工会话：不自动 next，pick 已关掉，我只跟着窗口同步。\n"
        "你进到 STORY/SCENE 时我会主动告诉你能发哪些短 CLI。发 sync 可再同步一次。"
    )

