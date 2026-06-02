"""
Reusable Project Configuration Manager Module

This module provides classes for managing project configurations and 
providing a GUI for project selection. Can be used across multiple applications.
"""

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import os
import re
import json
import glob
import copy
import base64
from datetime import datetime
import config
import config_prompt
import config_channel
import utility.llm_api as llm_api
from utility.llm_api import LLMApi
from utility.file_util import safe_copy_overwrite, safe_remove, safe_clipboard_json_copy
from utility.tags_text import merge_tag_pick, parse_tags_list
from gui.downloader import MediaGUIManager

def _story_value_nonempty(sv) -> bool:
    if sv is None:
        return False
    if isinstance(sv, str):
        return bool(sv.strip())
    if isinstance(sv, list):
        return len(sv) > 0
    if isinstance(sv, dict):
        return len(sv) > 0
    return True


def story_text_from_config(cfg: dict) -> str:
    """从 ``PROJECT_CONFIG`` 或绑定的频道列表行外层 ``story`` 读取 remix / YouTube 用文本。"""
    if not isinstance(cfg, dict):
        return ""
    st = (cfg.get("story") or "").strip()
    if st:
        return st

    row = load_video_detail_row_for_config(cfg)
    if isinstance(row, dict):
        st = (row.get("story") or row.get("summary") or "").strip()
        if st:
            return st
    return ""


def project_topic_list_json_path(cfg: dict) -> str:
    """由 ``project_profile`` 的 ``channel`` + ``topic_category`` 解析目标主题分表 list JSON 路径。"""
    if not isinstance(cfg, dict):
        return ""
    ch = (cfg.get("channel") or "").strip()
    tc = (cfg.get("topic_category") or "").strip()
    if not ch or not tc:
        return ""
    return topic_category_list_json_path(ch, tc)


def find_list_row_index_by_pid(list_path: str, wanted_pid: str) -> int:
    """在指定 list JSON 中按 ``list_json_row_workflow_pid`` 查找行下标。"""
    wanted_pid = (wanted_pid or "").strip()
    if not wanted_pid or not list_path or not os.path.isfile(list_path):
        return -1
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError):
        return -1
    if not isinstance(arr, list):
        return -1
    for idx, item in enumerate(arr):
        if not isinstance(item, dict):
            continue
        if list_json_row_workflow_pid(item) == wanted_pid:
            return idx
    return -1


def load_video_detail_row_for_config(cfg: dict) -> dict | None:
    """在目标主题分表（``channel`` + ``topic_category``）中按 ``pid`` == 行 ``id`` 定位 video detail。"""
    if not isinstance(cfg, dict):
        return None
    lp = project_topic_list_json_path(cfg)
    file_pid = (cfg.get("pid") or "").strip()
    if not lp or not file_pid or not os.path.isfile(lp):
        return None
    try:
        with open(lp, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(arr, list):
        return None
    for item in arr:
        if not isinstance(item, dict):
            continue
        if list_json_row_workflow_pid(item) == file_pid:
            return item
    return None


def find_project_topic_list_row(cfg: dict) -> tuple[str, int, dict | None]:
    """返回 ``(list_path, index, row)``；未找到时 ``index`` 为 ``-1``、``row`` 为 ``None``。"""
    if not isinstance(cfg, dict):
        return "", -1, None
    lp = project_topic_list_json_path(cfg)
    file_pid = (cfg.get("pid") or "").strip()
    if not lp or not file_pid:
        return lp, -1, None
    ix = find_list_row_index_by_pid(lp, file_pid)
    if ix < 0 or not os.path.isfile(lp):
        return lp, -1, None
    try:
        with open(lp, "r", encoding="utf-8") as f:
            arr = json.load(f)
        if isinstance(arr, list) and 0 <= ix < len(arr):
            row = arr[ix]
            return lp, ix, row if isinstance(row, dict) else None
    except (OSError, json.JSONDecodeError):
        pass
    return lp, -1, None


def _jsonish_preview_fragment(val, max_len: int = 200) -> str:
    """将字符串 / dict / list 压成单行预览（截断）。"""
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.strip()
    elif isinstance(val, (dict, list)):
        try:
            s = json.dumps(val, ensure_ascii=False)
        except TypeError:
            s = str(val)
    else:
        s = str(val)
    return s[:max_len] + ("…" if len(s) > max_len else "")


def _raw_story_preview_text(story_result) -> str:
    """RAW 区预览：优先 analyzed_content，其次 scene_content，再次 content。"""
    if isinstance(story_result, dict):
        if _story_value_nonempty(story_result.get("analyzed_content")):
            return _jsonish_preview_fragment(story_result.get("analyzed_content"))
        if _story_value_nonempty(story_result.get("scene_content")):
            return _jsonish_preview_fragment(story_result.get("scene_content"))
        if _story_value_nonempty(story_result.get("story")):
            return _jsonish_preview_fragment(story_result.get("story"))
    return ""


def caption_from_scene_content_item(item: dict) -> str:
    """场景 dict 上的标题/字幕行：优先 ``caption``，兼容旧 ``title``。"""
    if not isinstance(item, dict):
        return ""
    for kk in ("caption", "title", "Title"):
        t = item.get(kk)
        if t is not None and str(t).strip():
            return str(t).strip()
    return ""


def normalize_scene_content_item_for_workflow(item: dict) -> None:
    if not isinstance(item, dict):
        return
    cap = item.get("caption")
    if cap is None or not str(cap).strip():
        cap = item.pop("title", "") or item.pop("Title", "")
    else:
        item.pop("title", None)
        item.pop("Title", None)
    if cap is not None and str(cap).strip():
        item["caption"] = str(cap).strip()

    story = item.pop("story", None)
    if not story:
        story = item.get("visual", None)
    if story:
        item["visual"] = story

    message = item.pop("message", None)
    if not message:
        message = item.get("voiceover", None)
    if message:
        item["voiceover"] = message



def title_from_scene_content(scene_content, ui_language_key: str = "") -> str:
    """从 ``scene_content``（list 或旧双语 dict）取首场景 ``caption``。"""
    scenes = config.scene_content_as_list(scene_content, ui_language_key)
    if not scenes:
        return ""
    first = scenes[0]
    if isinstance(first, dict):
        return caption_from_scene_content_item(first)
    return ""


def _raw_content_valid_for_create(ac) -> bool:
    """``analyzed_content`` 为非空纯文本。"""
    return bool(config.analyzed_content_text(ac).strip())


def build_soul(channel, topic_category, topic_subtype):
    channel_path = config.get_channel_path(config_channel.get_channel_id(channel)) if channel else None
    topic_choices, topic_categories, tag_features_map = config.load_topics(channel)

    topic_category = (topic_category or '').strip()
    topic_subtype = (topic_subtype or '').strip()

    for topic in topic_choices:
        if not isinstance(topic, dict):
            continue
        cat = topic.get('topic_category') or topic.get('category') or ''
        if cat.strip() != topic_category:
            continue
        # 先加载 category 级 soul
        cat_soul_spec = topic.get('soul') or ''
        category_soul = _load_soul_content(channel_path, cat_soul_spec) if cat_soul_spec else ''
        # 若有 subtype，再找并加载 subtype 级 soul
        subtype_soul = ''
        if topic_subtype:
            for st in topic.get('topic_subtypes') or []:
                if not isinstance(st, dict):
                    continue
                if (st.get('topic_subtype') or '').strip() == topic_subtype:
                    sub_spec = st.get('soul') or ''
                    subtype_soul = _load_soul_content(channel_path, sub_spec) if sub_spec else ''
                    break
        
        if subtype_soul:
            return subtype_soul, topic_choices, topic_categories, tag_features_map
        else:
            return category_soul, topic_choices, topic_categories, tag_features_map
        #parts = [p for p in (category_soul, subtype_soul) if p]
        #return '\n---\n'.join(parts) if parts else ''
    return '', topic_choices, topic_categories, tag_features_map  # 未找到匹配的 topic_category



PROJECT_CONFIG = None

# 欢迎屏选择的旁白 narrator，供 YT → RAW 启动新项目 等路径复用（与 config_prompt.NARRATOR 一致）
LAST_NARRATOR = config.CHARACTER_PERSON_OPTIONS[0]

# 欢迎屏选择的画面风格（英文，与 config.VISUAL_STYLE_OPTIONS 一致）
LAST_VISUAL_STYLE = config.VISUAL_STYLE_OPTIONS[0]

LAST_HOST_DISPLAY = config_prompt.HARRATOR_DISPLAY_OPTIONS[0]
LAST_YT_LANGUAGE = "tw"

# 频道「热门/视频列表」JSON 里每项的完整工作流配置（替代或并存 *.config）
PROJECT_PROFILE_KEY = "project_profile"

# 落盘写入 project_profile 的键（不含 RAW / 分类 / tags / soul 等）
PROJECT_PROFILE_STORAGE_KEYS = frozenset({
    "channel",
    "channel_prompt",
    "language",
    "narrator",
    "visual_style",
    "host_display",
    "pid",
    "video_width",
    "video_height",
    "scene_min_length",
    "watermark",
    "headmark",
    "video_title",
    "topic_category",
    "topic_subtype",
})

# 列表行外层字段（不落进 project_profile，由 sync_channel_list_item_from_full_config 写入/同步）
LIST_ITEM_TOP_PROJECT_KEYS = (
    "story",
    "analyzed_content",
    "scene_content",
    "topic_category",
    "topic_subtype",
    "tags",
)

_LIST_REF_PREFIX = "chanlist:"


def iter_channel_list_json_files():
    """扫描各频道 program/*/list/*.json。"""
    for cid in list(config_channel.CHANNEL_CONFIG.keys()):
        list_dir = config.channel_list_json_dir_abs(config.get_channel_path(cid))
        if not os.path.isdir(list_dir):
            continue
        for fp in sorted(glob.glob(os.path.join(list_dir, "*.json"))):
            yield fp


def encode_list_item_ref(list_path: str, index: int) -> str:
    """Treeview tag：指向列表文件中某一行的项目配置。"""
    raw = json.dumps([os.path.normpath(list_path), int(index)], ensure_ascii=False)
    return _LIST_REF_PREFIX + base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_list_item_ref(tag: str):
    """返回 (list_path, index) 或 (None, None)。"""
    if not isinstance(tag, str) or not tag.startswith(_LIST_REF_PREFIX):
        return None, None
    try:
        raw = base64.urlsafe_b64decode(tag[len(_LIST_REF_PREFIX) :].encode("ascii")).decode("utf-8")
        path, idx = json.loads(raw)
        return os.path.normpath(path), int(idx)
    except Exception:
        return None, None


def export_profile_for_storage(cfg: dict) -> dict:
    """写入 list / 文件前去掉仅内存用的 ``_`` 元数据，并保证可 JSON 序列化。"""
    out = {}
    for k, v in (cfg or {}).items():
        if str(k).startswith("_"):
            continue
        try:
            json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


def migrate_legacy_project_channel_prompt(cfg: dict) -> dict:
    """将旧 ``prompts`` + ``channel_template`` 合并为 ``channel_prompt``。"""
    if not isinstance(cfg, dict):
        return {}
    cp = dict(cfg.get("channel_prompt") or {})
    leg_p = cfg.get("prompts")
    if isinstance(leg_p, dict):
        cp.update(leg_p)
    leg_t = cfg.get("channel_template")
    if isinstance(leg_t, dict):
        cp.update(leg_t)
    if cp:
        cfg["channel_prompt"] = cp
    cfg.pop("prompts", None)
    cfg.pop("channel_template", None)
    cfg.pop("content", None)
    return cp


def profile_for_list_storage(cfg: dict) -> dict:
    """列表项内 ``project_profile`` 仅存白名单字段（含 topic_category / topic_subtype；不含 RAW / soul）。"""
    base = export_profile_for_storage(cfg or {})
    migrate_legacy_project_channel_prompt(base)
    out = {}
    for k in PROJECT_PROFILE_STORAGE_KEYS:
        if k not in base:
            continue
        v = base[k]
        try:
            json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        out[k] = copy.deepcopy(v)
    return out


def resolve_soul_for_config(cfg: dict) -> str:
    """不读缓存的 soul：由 channel + topic 动态 ``build_soul``。"""
    if not isinstance(cfg, dict):
        return ""
    ch = (cfg.get("channel") or "").strip()
    tc = (cfg.get("topic_category") or "").strip()
    ts = (cfg.get("topic_subtype") or "").strip()
    if not (ch and tc and ts):
        return ""
    soul, _, _, _ = build_soul(ch, tc, ts)
    return soul if isinstance(soul, str) else ""


def hydrate_config_soul_runtime(cfg: dict) -> None:
    """运行时在 cfg 填入 soul，兼容仍读 cfg['soul'] 的路径；不写回列表 JSON。"""
    if not isinstance(cfg, dict):
        return
    s = resolve_soul_for_config(cfg)
    if s:
        cfg["soul"] = s
    else:
        cfg.pop("soul", None)


def sync_channel_list_item_from_full_config(item: dict, full_cfg_clean: dict) -> None:
    """将 ``export_profile_for_storage`` 后的完整配置写入一行列表：不改变外层 ``title``（保留原视频列表标题）；同步 RAW/分类/tags + 窄 ``project_profile``（含 ``video_title``）。"""
    if not isinstance(item, dict):
        return
    item[PROJECT_PROFILE_KEY] = profile_for_list_storage(full_cfg_clean)
    item.pop("project_id", None)
    item.pop("project_pid", None)
    item.pop("pid", None)
    item.pop("video_title", None)
    fc = full_cfg_clean or {}
    for k in LIST_ITEM_TOP_PROJECT_KEYS:
        if k in fc:
            item[k] = copy.deepcopy(fc[k])
    file_pid = str((full_cfg_clean or {}).get("pid") or "").strip()
    if file_pid:
        item["id"] = file_pid
    sync_list_item_id_and_profile_pid(item)


def list_json_row_id(item: dict) -> str:
    """列表行主键：外层 ``id``（YouTube 视频 id 或项目 pid）。"""
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "").strip()


def list_json_row_has_project_profile(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    pr = item.get(PROJECT_PROFILE_KEY)
    return isinstance(pr, dict) and bool(pr)


def sync_list_item_id_and_profile_pid(item: dict) -> None:
    """迁移旧 ``gen_video_stem`` / ``localproj:`` url；有项目绑定时保证 ``id`` 与 ``project_profile.pid`` 一致。"""
    if not isinstance(item, dict):
        return
    legacy_stem = (item.pop("gen_video_stem", None) or "").strip()
    url = (item.get("url") or "").strip()
    if url.lower().startswith("localproj:"):
        m = re.match(r"localproj:([^:]+):", url, flags=re.IGNORECASE)
        if m and not list_json_row_id(item):
            item["id"] = m.group(1).strip()
        restore = (item.get("cloned_from_url") or "").strip()
        if restore:
            item["url"] = restore
        else:
            item.pop("url", None)
    prof = item.get(PROJECT_PROFILE_KEY)
    if isinstance(prof, dict) and prof:
        pid = str(prof.get("pid") or "").strip()
        outer = list_json_row_id(item)
        if legacy_stem and not outer:
            item["id"] = legacy_stem
            outer = legacy_stem
        if pid and outer and pid != outer:
            item["id"] = pid
            prof["pid"] = pid
        elif pid and not outer:
            item["id"] = pid
        elif outer and not pid:
            prof["pid"] = outer
    elif legacy_stem and not list_json_row_id(item):
        item["id"] = legacy_stem


def list_json_row_workflow_pid(item: dict) -> str:
    """工作流 pid：有 ``project_profile`` 时与外层 ``id`` 一致（读 ``id``，兼容仅 profile 内 pid 的旧行）。"""
    if not isinstance(item, dict):
        return ""
    pr = item.get(PROJECT_PROFILE_KEY)
    if isinstance(pr, dict) and pr:
        iid = list_json_row_id(item)
        if iid:
            return iid
        return str(pr.get("pid") or "").strip()
    return ""


def project_config_from_list_item(item: dict, list_path: str = "", index: int = -1) -> dict:
    """从视频列表的一行构造与原先 ``*.config`` 等价的 PROJECT_CONFIG 字典。"""
    if not isinstance(item, dict):
        return {}
    prof = item.get(PROJECT_PROFILE_KEY)
    cfg = {}
    if isinstance(prof, dict) and prof:
        cfg = profile_for_list_storage(copy.deepcopy(prof))
    pid = list_json_row_workflow_pid(item)
    if pid:
        cfg["pid"] = pid
    for k in LIST_ITEM_TOP_PROJECT_KEYS:
        if k in item:
            cfg[k] = copy.deepcopy(item[k])
    vt = (cfg.get("video_title") or "").strip()
    if vt:
        cfg["video_title"] = vt
    for k in (
        "language",
        "channel",
        "video_width",
        "video_height",
        "visual_style",
        "narrator",
        "host_display",
        "watermark",
        "headmark",
        "scene_min_length",
    ):
        if k not in cfg and item.get(k) is not None:
            cfg[k] = copy.deepcopy(item[k])
    if list_path:
        pass  # 列表路径由 topic_category 动态解析，不落盘
    cfg.pop("channel_list_json", None)
    cfg.pop("_channel_list_json", None)
    cfg.pop("_channel_list_index", None)
    hydrate_config_soul_runtime(cfg)
    return cfg


def load_project_config_by_pid(wanted_pid: str):
    """按 pid 在各频道 ``list/*.json`` 中查找；优先匹配 ``list/<topic_category>.json`` 分表行。"""
    wanted_pid = (wanted_pid or "").strip()
    if not wanted_pid:
        return None
    best = None
    best_rank = -1
    for list_path in iter_channel_list_json_files():
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except Exception:
            continue
        if not isinstance(arr, list):
            continue
        for idx, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            cand = list_json_row_workflow_pid(item)
            if cand != wanted_pid:
                continue
            tc = (item.get("topic_category") or "").strip()
            prof = item.get(PROJECT_PROFILE_KEY)
            if not tc and isinstance(prof, dict):
                tc = (prof.get("topic_category") or "").strip()
            rank = 2 if tc and os.path.basename(list_path) == config.topic_category_list_file_basename(tc) else 0
            if rank > best_rank:
                best_rank = rank
                best = project_config_from_list_item(item, list_path, idx)
    return best


def _write_profile_to_list_at_index(list_path: str, index: int, full_exported_cfg: dict) -> bool:
    """``full_exported_cfg`` 须为 ``export_profile_for_storage`` 的结果；整行同步外层 + 窄 profile。"""
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except Exception:
        return False
    if not isinstance(arr, list) or index < 0 or index >= len(arr):
        return False
    if not isinstance(arr[index], dict):
        return False
    sync_channel_list_item_from_full_config(arr[index], full_exported_cfg or {})
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _try_save_profile_to_lists_by_pid(file_pid: str, full_exported_cfg: dict) -> bool:
    for list_path in iter_channel_list_json_files():
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except Exception:
            continue
        if not isinstance(arr, list):
            continue
        for idx, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            cand = list_json_row_workflow_pid(item)
            if cand == file_pid:
                if _write_profile_to_list_at_index(list_path, idx, full_exported_cfg):
                    return True
    return False


def topic_category_list_json_path(channel_field: str, topic_category: str) -> str:
    """与 ``config.topic_category_list_json_abspath`` / ``gui.downloader`` 主题列表路径完全一致。"""
    return config.topic_category_list_json_abspath(channel_field, topic_category)


def _prompt_topic_category_if_needed(parent) -> str:
    if parent is None:
        return ""
    try:
        import tkinter.simpledialog as simpledialog

        s = simpledialog.askstring(
            "主题分类 (topic_category)",
            "保存项目需要主题分类。\n请输入与当前频道 topics.json 中一致的 topic_category：",
            parent=parent,
        )
        return (s or "").strip()
    except Exception:
        return ""


def _upsert_profile_in_topic_list_file(list_path: str, file_pid: str, full_exported_cfg: dict) -> bool:
    """在指定 list JSON 内按 pid 更新或追加一行（整行同步）。"""
    arr = []
    if os.path.isfile(list_path):
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            arr = []
    if not isinstance(arr, list):
        arr = []
    found = False
    file_pid = (file_pid or "").strip()
    for item in arr:
        if not isinstance(item, dict):
            continue
        if list_json_row_workflow_pid(item) == file_pid:
            sync_channel_list_item_from_full_config(item, full_exported_cfg or {})
            found = True
            break
    if not found:
        new_item = {}
        sync_channel_list_item_from_full_config(new_item, full_exported_cfg or {})
        arr.append(new_item)
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


media_count = 0
pid = None

def refresh_scene_media(scene, media_type, media_postfix, replacement=None, make_replacement_copy=False):
    global media_count, pid, PROJECT_CONFIG
    scene_id = scene.get("id", int(datetime.now().timestamp() * 1000) + media_count)
    new_media_stem = media_type + "_" + str(scene_id) + "_" + str(int(datetime.now().timestamp()*100 + media_count%100))
    media_count = (media_count + 1) % 100

    old_media_path = scene.get(media_type, None)
    if pid is None and PROJECT_CONFIG:
        pid = PROJECT_CONFIG.get('pid')
    if not pid:
        raise ValueError("无法获取项目ID，请先选择项目")
    scene[media_type] = config.get_media_path(pid) + "/" + new_media_stem + media_postfix

    if replacement:
        safe_copy_overwrite(replacement, scene[media_type])
        if not make_replacement_copy:
            safe_remove(replacement)
    return old_media_path, scene[media_type]


def _load_soul_content(channel_path, soul_spec):
    """将 soul 规格（文件路径或内联文本）转为实际内容。"""
    if not soul_spec or not isinstance(soul_spec, str):
        return ''
    soul = soul_spec.strip()
    if channel_path and soul and (soul.endswith('.md') or ('.' in soul and '\n' not in soul and len(soul) < 200)):
        file_path = os.path.join(channel_path, soul)
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception:
                pass
    return ""


class ProjectConfigManager:
    """管理每个项目的配置文件 - 可重用的项目配置管理器"""
    
    def __init__(self, pid=None):
        self.pid = pid

        self.load_config(pid)


    def list_projects(self):
        """列出项目：扫描各频道 ``list/*.json``（热门 + topic 分表）；行内 pid 优先 ``project_profile.pid``。"""
        seen_pid = set()
        projects = []

        for list_path in iter_channel_list_json_files():
            try:
                mtime = os.path.getmtime(list_path)
                last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                last_modified = ""
            try:
                with open(list_path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
            except Exception as e:
                print(f"⚠️ 无法读取列表 {list_path}: {e}")
                continue
            if not isinstance(arr, list):
                continue
            for idx, item in enumerate(arr):
                if not isinstance(item, dict):
                    continue
                cfg = project_config_from_list_item(item, list_path, idx)
                tpid = (cfg.get("pid") or "").strip()
                if not tpid:
                    continue
                if tpid in seen_pid:
                    continue
                seen_pid.add(tpid)
                title = (cfg.get("video_title") or "").strip() or tpid
                language = cfg.get("language", "zh")
                channel = cfg.get("channel", "")
                video_size = f"{cfg.get('video_width', '1920')}x{cfg.get('video_height', '1080')}"
                ref = encode_list_item_ref(list_path, idx)
                projects.append(
                    {
                        "pid": tpid,
                        "title": title,
                        "language": language,
                        "channel": channel,
                        "video_size": video_size,
                        "last_modified": last_modified,
                        "config_file": ref,
                        "config_data": cfg,
                    }
                )

        projects.sort(key=lambda x: x["last_modified"], reverse=True)
        return projects
    

    def load_config(self, pid):
        global PROJECT_CONFIG
        if not pid:
            return PROJECT_CONFIG

        self.pid = pid
        merged = load_project_config_by_pid(pid)
        if merged is not None:
            PROJECT_CONFIG = merged
            print(f"🔍 load_config: 已从频道 list/ 加载，PID: {PROJECT_CONFIG.get('pid') if PROJECT_CONFIG else 'None'}")
        else:
            print(f"🔍 load_config: 未在任何 list/*.json 中找到 pid={pid}")
        return PROJECT_CONFIG
    
    @staticmethod
    def set_global_config(config_data):
        """设置全局 PROJECT_CONFIG"""
        global PROJECT_CONFIG
        PROJECT_CONFIG = config_data.copy() if config_data else None
        if PROJECT_CONFIG is not None:
            PROJECT_CONFIG.pop('debut_content', None)
            hydrate_config_soul_runtime(PROJECT_CONFIG)

    def load_project_config(self, config_file):
        """加载项目配置：仅支持 ``chanlist:`` 列表引用（某 ``list/*.json`` 的行）。"""
        lp, ix = decode_list_item_ref(config_file)
        if lp is not None and ix is not None:
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if isinstance(arr, list) and 0 <= ix < len(arr) and isinstance(arr[ix], dict):
                    return project_config_from_list_item(arr[ix], lp, ix)
            except Exception as e:
                print(f"❌ 从频道列表加载失败: {e}")
            return None
        return None
    
    def delete_project_config(self, config_file):
        """删除项目：仅支持 ``chanlist:`` 引用——清空该行的 ``project_profile``。"""
        lp, ix = decode_list_item_ref(config_file)
        if lp is not None and ix is not None:
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if not isinstance(arr, list) or ix < 0 or ix >= len(arr):
                    return False
                if isinstance(arr[ix], dict):
                    arr[ix].pop(PROJECT_PROFILE_KEY, None)
                    arr[ix].pop("project_id", None)
                    arr[ix].pop("project_pid", None)
                    arr[ix].pop("pid", None)
                with open(lp, "w", encoding="utf-8") as f:
                    json.dump(arr, f, ensure_ascii=False, indent=2)
                print(f"🗑️ 已从频道列表移除项目配置: {lp}[{ix}]")
                return True
            except Exception as e:
                print(f"❌ 删除列表项目配置失败: {e}")
                return False
        print("❌ 不支持删除：请从「选择项目」列表产生的引用删除")
        return False


def save_project_config(parent=None):
    """写回 ``project_profile`` 到 ``list/<topic_category>.json``（由 profile 内 channel + topic_category 定位）。

    不再使用 ``PROJECT_DATA_PATH/config/{pid}.config``。若无 ``topic_category``，在有 ``parent`` 时弹窗请求。
    """
    global PROJECT_CONFIG, pid
    if not PROJECT_CONFIG:
        print("❌ 项目配置未加载，无法保存项目配置")
        return False
    file_pid = PROJECT_CONFIG.get("pid") or pid
    if not file_pid:
        print("❌ 项目ID未设置，无法保存项目配置")
        return False
    to_store = export_profile_for_storage(copy.deepcopy(PROJECT_CONFIG))

    ch = (PROJECT_CONFIG.get("channel") or "").strip()
    if not ch:
        print("❌ 缺少 channel，无法定位 list/ 下的主题列表文件")
        return False

    tc = (PROJECT_CONFIG.get("topic_category") or "").strip()
    if not tc:
        tc = _prompt_topic_category_if_needed(parent)
        if not tc:
            print("❌ 缺少 topic_category，已取消保存（请在工作流中设置主题或在弹窗中输入）")
            return False
        PROJECT_CONFIG["topic_category"] = tc
        to_store = export_profile_for_storage(copy.deepcopy(PROJECT_CONFIG))

    tpath = topic_category_list_json_path(ch, tc)
    ix = find_list_row_index_by_pid(tpath, file_pid)
    if ix >= 0 and _write_profile_to_list_at_index(tpath, ix, to_store):
        pid = file_pid
        print(f"✅ 项目配置已写入主题列表: {tpath} (pid {file_pid})")
        return True
    if _upsert_profile_in_topic_list_file(tpath, file_pid, to_store):
        pid = file_pid
        print(f"✅ 项目配置已写入主题列表: {tpath}")
        return True
    print(f"❌ 无法写入主题列表文件: {tpath}")
    return False


class ProjectSelectionDialog:
    """项目选择对话框 - 可重用的项目选择界面"""
    
    def __init__(self, parent, config_manager, youtube_gui, create_only,
                 initial_channel=None, initial_language=None, initial_narrator=None, initial_visual_style=None, initial_host_display=None,
                 initial_analyzed_content=None, initial_scene_content=None, initial_category=None, initial_subtype=None, initial_tags=None):

        self.parent = parent
        self.config_manager = config_manager
        self.youtube_gui = youtube_gui
        self.selected_config = None
        self.llm_api_local = LLMApi(llm_api.GPT_MINI)
        # 与频道 topics.json / tags.json 对应；create_new_project 内「添加标签」等闭包依赖
        self.topics_data = []
        self.tag_features_map = {}

        available_channels = list(config_channel.CHANNEL_CONFIG.keys())
        default_channel = initial_channel or (available_channels[0] if available_channels else 'default')
        default_lang = initial_language or 'tw'

        _nar = initial_narrator or LAST_NARRATOR
        _vs = initial_visual_style or LAST_VISUAL_STYLE
        _hd = initial_host_display or LAST_HOST_DISPLAY
        
        self.default_project_config = {
            'languages': ['tw', 'zh', 'en'],
            'default_language': default_lang,
            'channels': available_channels,
            'default_channel': default_channel,
            'default_title': '新项目',
            'default_video_width': '1920',
            'default_video_height': '1080'
        }

        icat = (initial_category or '').strip() or None
        isub = (initial_subtype or '').strip() or None
        if initial_tags is not None:
            if isinstance(initial_tags, list):
                itags = [
                    str(t).strip()
                    for t in initial_tags
                    if t is not None and str(t).strip()
                ]
            else:
                itags = parse_tags_list(str(initial_tags)) or None
            if itags == []:
                itags = None
        else:
            itags = None

        # 首次「选择项目」等入口不传 analyzed/scene：须避免对 None 调 .get；字符串则解析为 dict（保留双语结构）
        ac_src = ""
        ac_src = ""
        if isinstance(initial_analyzed_content, str):
            ac_src = initial_analyzed_content.strip()
        elif initial_analyzed_content is not None:
            ac_src = config.normalize_analyzed_content_value(
                initial_analyzed_content, default_lang
            )
        sc_src = []
        if initial_scene_content is not None:
            if isinstance(initial_scene_content, list):
                sc_src = initial_scene_content
            elif isinstance(initial_scene_content, dict):
                sc_src = config.normalize_scene_content_value(
                    initial_scene_content, default_lang
                )
            elif isinstance(initial_scene_content, str) and initial_scene_content.strip():
                try:
                    parsed_sc = json.loads(
                        safe_clipboard_json_copy(initial_scene_content.strip())
                    )
                    sc_src = config.normalize_scene_content_value(
                        parsed_sc, default_lang
                    )
                except json.JSONDecodeError:
                    sc_src = []
        self.story_result = {
            'channel': default_channel,
            'language': default_lang,
            'narrator': _nar,
            'visual_style': _vs,
            'host_display': _hd,
            'channel_prompt': None,
            'topic_category': icat,
            'topic_subtype': isub,
            'tags': itags,
            'soul': None,
            'analyzed_content': ac_src,
            'scene_content': sc_src,
            'action': None,
        }

        #self.story_result['analyzed_content'] = initial_analyzed_content
        #self.story_result['scene_content'] = initial_scene_content

        if (
            initial_channel
            and self.story_result.get('topic_category')
            and self.story_result.get('topic_subtype')
        ):
            self.story_result['soul'], _, _, _ = build_soul(
                initial_channel,
                self.story_result['topic_category'],
                self.story_result['topic_subtype'],
            )

        if create_only:
            # 创建隐藏的父窗口（用于后续销毁），创建表单必须挂在可见的 parent 下否则会白屏
            self.dialog = tk.Toplevel(parent)
            self.dialog.withdraw()
            self._form_parent = parent  # 创建新项目窗口的父窗口须为可见
            self.create_new_project()
            if self.story_result.get('action') != 'new' and self.dialog.winfo_exists():
                self.dialog.destroy()
        else:
            self.create_dialog()



    def create_dialog(self):
        """项目列表：打开 / 删除 / 刷新；不提供「新建项目」（新建走 downloader 等单独入口）。"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择项目")
        self.dialog.geometry("1000x600")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (600 // 2)
        self.dialog.geometry(f"1000x600+{x}+{y}")

        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        title_label = ttk.Label(main_frame, text="选择要打开的项目", font=('TkDefaultFont', 14, 'bold'))
        title_label.pack(pady=(0, 20))

        list_frame = ttk.LabelFrame(main_frame, text="现有项目", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        columns = ('PID', '标题', '类型', '语言', '频道', '尺寸', '最后修改')
        self.project_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        self.project_tree.heading('PID', text='项目ID')
        self.project_tree.heading('标题', text='标题')
        self.project_tree.heading('类型', text='项目类型')
        self.project_tree.heading('语言', text='语言')
        self.project_tree.heading('频道', text='频道')
        self.project_tree.heading('尺寸', text='尺寸')
        self.project_tree.heading('最后修改', text='最后修改时间')
        self.project_tree.column('PID', width=120)
        self.project_tree.column('标题', width=150)
        self.project_tree.column('类型', width=80)
        self.project_tree.column('语言', width=60)
        self.project_tree.column('频道', width=100)
        self.project_tree.column('尺寸', width=80)
        self.project_tree.column('最后修改', width=130)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.project_tree.yview)
        self.project_tree.configure(yscrollcommand=scrollbar.set)
        self.project_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.project_tree.bind('<Double-1>', self.on_double_click)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        ttk.Button(left_buttons, text="刷新列表", command=self.refresh_projects).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_buttons, text="删除项目", command=self.delete_project).pack(side=tk.LEFT, padx=(0, 10))
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        ttk.Button(right_buttons, text="打开选中", command=self.open_selected).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(right_buttons, text="取消", command=self.cancel).pack(side=tk.LEFT)

        self.refresh_projects()
        if self.project_tree.get_children():
            self.project_tree.selection_set(self.project_tree.get_children()[0])

    def refresh_projects(self):
        """刷新项目列表"""
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)
        projects = self.config_manager.list_projects()
        for project in projects:
            self.project_tree.insert('', tk.END, values=(
                project['pid'],
                project['title'],
                project['language'],
                project['channel'],
                project['video_size'],
                project['last_modified']
            ), tags=(project['config_file'],))

    def on_double_click(self, event):
        """双击打开项目"""
        self.open_selected()

    def delete_project(self):
        """删除选中的项目"""
        selection = self.project_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要删除的项目")
            return
        item = selection[0]
        config_file = self.project_tree.item(item)['tags'][0]
        pid = self.project_tree.item(item)['values'][0]
        title = self.project_tree.item(item)['values'][1]
        if messagebox.askyesno("确认删除", f"确定要删除项目 '{pid} - {title}' 吗？\n\n这将删除项目配置文件，但不会删除项目数据。"):
            if self.config_manager.delete_project_config(config_file):
                self.refresh_projects()
                messagebox.showinfo("成功", "项目配置已删除")

    def create_new_project(self):
        """创建新项目"""
        # 创建新项目配置对话框；create_only 时父窗口须为可见的 parent，否则会白屏
        form_parent = getattr(self, '_form_parent', self.dialog)
        new_project_dialog = tk.Toplevel(form_parent)
        new_project_dialog.title("创建新项目")
        new_project_dialog.geometry("800x800")
        new_project_dialog.transient(form_parent)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 800) // 2
        y = (new_project_dialog.winfo_screenheight() - 800) // 2
        new_project_dialog.geometry(f"800x800+{x}+{y}")
        
        main_frame = ttk.Frame(new_project_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        row = 0

        # PID、标题、视频分辨率：同一行横向排列
        top_fields_row = ttk.Frame(main_frame)
        top_fields_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Label(top_fields_row, text="PID:").pack(side=tk.LEFT, padx=(0, 4))
        pid_entry = ttk.Entry(top_fields_row, width=18)
        pid_entry.pack(side=tk.LEFT, padx=(0, 16))
        auto_pid = f"p{datetime.now().strftime('%Y%m%d%H%M')}"
        pid_entry.insert(0, auto_pid)

        ttk.Label(top_fields_row, text="标题:").pack(side=tk.LEFT, padx=(0, 4))
        title_entry = ttk.Entry(top_fields_row, width=28)
        title_entry.pack(side=tk.LEFT, padx=(0, 16))

        title_manual_touch = [False]
        prog_title_sync = {"on": False}

        def _apply_title_programmatic(text: str):
            prog_title_sync["on"] = True
            title_entry.delete(0, tk.END)
            title_entry.insert(0, text)

            def _clear_prog_flag():
                prog_title_sync["on"] = False

            try:
                new_project_dialog.after(1, _clear_prog_flag)
            except tk.TclError:
                prog_title_sync["on"] = False

        def _on_title_keyrelease(_evt=None):
            if prog_title_sync["on"]:
                return
            title_manual_touch[0] = True

        title_entry.bind("<KeyRelease>", _on_title_keyrelease, add="+")

        def refresh_title_entry_from_scene():
            nt = title_from_scene_content(
                self.story_result.get("scene_content"),
                self.story_result.get("language") or "",
            )
            if not nt:
                return
            if title_manual_touch[0]:
                return
            _apply_title_programmatic(nt)

        _dt = title_from_scene_content(
            self.story_result.get("scene_content"), self.story_result.get("language") or ""
        )
        _apply_title_programmatic(_dt or self.default_project_config["default_title"])

        ttk.Label(top_fields_row, text="视频:").pack(side=tk.LEFT, padx=(0, 4))
        resolution_frame = ttk.Frame(top_fields_row)
        resolution_frame.pack(side=tk.LEFT, padx=(0, 0))
        resolution_var = tk.StringVar(value="1080x1920")
        ttk.Radiobutton(resolution_frame, text="1920x1080 (横向)", variable=resolution_var, value="1920x1080").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(resolution_frame, text="1080x1920 (纵向)", variable=resolution_var, value="1080x1920").pack(side=tk.LEFT)
        row += 1

        # 频道、语言只读；画面风格 / HOST / 旁白 与欢迎屏一致，此处用 Combobox 可改，创建时从控件写入 story_result
        welcome_info_row = ttk.Frame(main_frame)
        welcome_info_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        _np_styles = list(config.VISUAL_STYLE_OPTIONS)
        _vs_cur = self.story_result.get('visual_style')
        _hd_init = self.story_result.get('host_display')
        _nar_init = self.story_result.get('narrator')
        new_project_visual_style_var = tk.StringVar(value=_vs_cur)
        new_project_host_display_var = tk.StringVar(value=_hd_init)

        new_project_narrator_var = tk.StringVar(value=_nar_init)
        # SET new_project_narrator_var default value TO woman/qin-fast/chinese
        new_project_narrator_var.set("woman/qin-fast/chinese")

        ttk.Label(welcome_info_row, text="频道:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(welcome_info_row, text=str(self.story_result.get('channel', '')), foreground="gray").pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(welcome_info_row, text="语言:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(welcome_info_row, text=str(self.story_result.get('language', '')), foreground="gray").pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(welcome_info_row, text="画面风格:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_visual_style_var,
            values=_np_styles,
            state="readonly",
            width=14,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(welcome_info_row, text="HOST:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_host_display_var,
            values=list(config_prompt.HARRATOR_DISPLAY_OPTIONS),
            state="readonly",
            width=16,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(welcome_info_row, text="旁白:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_narrator_var,
            values=config.CHARACTER_PERSON_OPTIONS,
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT, padx=(0, 8))
        row += 1

        def sync_channel_prompt(*args):
            """频道变更时同步完整 ``channel_prompt`` 快照到项目配置。"""
            self.story_result["channel_prompt"] = config_channel.get_channel_prompt_snapshot(
                self.story_result["channel"]
            )
            self.story_result.pop("prompts", None)
            self.story_result.pop("channel_template", None)

        sync_channel_prompt()

        # 主题分类、主题子类型：同一行横向排列
        topic_row = ttk.Frame(main_frame)
        topic_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Label(topic_row, text="主题分类:").pack(side=tk.LEFT)
        topic_category_combo = ttk.Combobox(topic_row, values=[], state="readonly", width=32)
        topic_category_combo.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(topic_row, text="主题子类:").pack(side=tk.LEFT)
        topic_subtype_combo = ttk.Combobox(topic_row, values=[], state="readonly", width=32)
        topic_subtype_combo.pack(side=tk.LEFT, padx=(0, 20))
        row += 1

        # 主题标签显示（可编辑，支持 a,b, GENRE=Jazz 格式，单选变更会同步至此）
        ttk.Label(main_frame, text="主题标签:").grid(row=row, column=0, sticky='nw', padx=(0, 8), pady=5)
        _tags_initial = self.story_result.get('tags')
        _tags_str = ', '.join(_tags_initial) if isinstance(_tags_initial, list) else (str(_tags_initial) if _tags_initial else '')
        tags_var = tk.StringVar(value=_tags_str)
        tags_row = ttk.Frame(main_frame)
        tags_row.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='ew')
        tags_entry = ttk.Entry(tags_row, textvariable=tags_var, width=72)
        tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _on_tag_pick_pm(feature: str, option: str):
            merged = merge_tag_pick(parse_tags_list(tags_var.get() or ""), feature, option)
            tags_var.set(", ".join(merged))

        def _open_tag_menu_pm():
            from gui.tag_picker_menu import build_tag_cascade_menu, post_menu_below_widget
            m = build_tag_cascade_menu(new_project_dialog, self.tag_features_map, _on_tag_pick_pm)
            post_menu_below_widget(m, tags_add_btn_pm)

        tags_add_btn_pm = ttk.Button(tags_row, text="添加标签", command=_open_tag_menu_pm)
        tags_add_btn_pm.pack(side=tk.LEFT, padx=(8, 0))
        row += 1
        
        # 显示说明文本的标签（支持多行）
        topic_explanation_label = ttk.Label(main_frame, text="", foreground="gray", wraplength=700, justify='left')
        topic_explanation_label.grid(row=row, column=1, columnspan=2, padx=(10, 0), pady=5, sticky='nw')
        row += 1
        
        def _tags_analysis_part(tags):
            """从 tags 中提取分析得来的部分（不含 '=' 的项，含旧版纯文本标签）"""
            if not tags:
                return []
            lst = tags if isinstance(tags, list) else parse_tags_list(str(tags))
            lst = [t.strip() for t in lst if t and isinstance(t, str)]
            return [t for t in lst if "=" not in t]

        def _tags_manual_part(tags):
            """从 tags 中提取手动选择的 KEY=value 部分"""
            if not tags:
                return []
            lst = tags if isinstance(tags, list) else parse_tags_list(str(tags))
            lst = [t.strip() for t in lst if t and isinstance(t, str)]
            return [t for t in lst if "=" in t]

        def _on_tags_entry_change(*args):
            """用户手动编辑 tags 时同步到 story_result"""
            combined = parse_tags_list(tags_var.get() or "")
            self.story_result["tags"] = combined if combined else None

        tags_var.trace_add('write', _on_tags_entry_change)

        # 更新主题子类型选项的函数（根据选择的 category）
        def update_topic_subtype(*args):
            selected_category = topic_category_combo.get()
            self.story_result['topic_category'] = selected_category.strip() if selected_category else None
            self.story_result['topic_subtype'] = None
            # 保留全部标签：KEY=value 与旧版纯文本（切换分类时不再只保留含「=」项）
            tags_var.set(", ".join(self.story_result.get("tags") or []))
            self.story_result['soul'] = None
            topic_subtype_combo.set('')
            topic_subtype_combo['values'] = []
            topic_explanation_label.config(text="")
            
            if selected_category and self.topics_data:
                subtypes = []
                for topic in self.topics_data:
                    if topic.get('topic_category') == selected_category:
                        for subtype_item in topic.get('topic_subtypes', []):
                            if isinstance(subtype_item, dict):
                                subtype_name = subtype_item.get('topic_subtype', '')
                                if subtype_name and subtype_name not in subtypes:
                                    subtypes.append(subtype_name)
                topic_subtype_combo['values'] = sorted(subtypes)
        
        # 更新说明文本的函数（显示 soul 和 sample_topic），并更新 self.topic_category/subtype/soul
        def update_explanation(*args):
            selected_category = topic_category_combo.get()
            selected_subtype = topic_subtype_combo.get()
            self.story_result['topic_category'] = selected_category.strip() if selected_category else None
            self.story_result['topic_subtype'] = selected_subtype.strip() if selected_subtype else None
            self.story_result['soul'], choices, categories, features = build_soul(self.story_result['channel'], self.story_result['topic_category'], self.story_result['topic_subtype'])
            
            if selected_category and choices:
                for topic in choices:
                    if topic.get('topic_category') == selected_category:
                        sample = topic.get('sample_topic', '')
                        display_parts = []
                        if self.story_result['soul']:
                            first_line = (self.story_result['soul'].split('\n')[0] or self.story_result['soul']).strip()
                            display_soul = (first_line[:64] + '…') if len(first_line) > 64 else first_line
                            display_parts.append(f"灵魂: {display_soul}")
                        if sample:
                            display_parts.append(f"示例: {sample}")
                        if display_parts:
                            topic_explanation_label.config(text="\n".join(display_parts), foreground="gray")
                        else:
                            topic_explanation_label.config(text="")
                        break
                else:
                    topic_explanation_label.config(text="")
            else:
                topic_explanation_label.config(text="")
        
        # 绑定事件在下方内容区域统一设置（含 update_buttons_state）

        # 加载主题分类选项的函数（从 topics.json）；channel/language 已从首层传入，不再从 UI 同步
        def update_topic_choices(*args):
            self.topics_data.clear()
            self.tag_features_map.clear()
            topic_category_combo.set('')
            topic_category_combo['values'] = []
            topic_subtype_combo.set('')
            topic_subtype_combo['values'] = []
            topic_explanation_label.config(text="")

            if self.story_result['channel']:
                loaded_choices, loaded_categories, loaded_tag_map = config.load_topics(
                    self.story_result['channel']
                )
                self.topics_data.extend(loaded_choices)
                if isinstance(loaded_tag_map, dict):
                    self.tag_features_map.update(loaded_tag_map)
                topic_category_combo['values'] = sorted(loaded_categories)

            _tg = self.story_result.get('tags')
            if isinstance(_tg, list) and _tg:
                tags_var.set(', '.join(_tg))
            elif _tg:
                tags_var.set(str(_tg).strip())
            else:
                tags_var.set('')

            try:
                update_buttons_state()
            except NameError:
                pass  # 初次加载时 update_buttons_state 尚未定义

        # 频道/语言已从首层传入，无需绑定变更事件；初始化加载主题分类与模板
        update_topic_choices()
        sync_channel_prompt()

        # 内容编辑区域：RAW
        content_panels_frame = ttk.Frame(main_frame)
        content_panels_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        content_panels_frame.columnconfigure(0, weight=1)
        row += 1

        raw_label_frame = ttk.LabelFrame(content_panels_frame, text="RAW内容", padding=10)
        raw_label_frame.grid(row=0, column=0, padx=(5, 5), sticky='nsew')
        raw_preview = ttk.Label(raw_label_frame, text="RAW: (未生成)", foreground="gray", wraplength=200)
        raw_preview.pack(anchor='w', pady=(0, 10))
        edit_raw_btn = ttk.Button(raw_label_frame, text="RAW内容", command=lambda: None)
        edit_raw_btn.pack(pady=5)

        scene_story_frame = ttk.LabelFrame(content_panels_frame, text="Story / scene_content (JSON)", padding=10)
        scene_story_frame.grid(row=1, column=0, padx=(5, 5), pady=(8, 0), sticky='nsew')
        scene_preview = ttk.Label(
            scene_story_frame,
            text="Story: (未填写)",
            foreground="gray",
            wraplength=200,
        )
        scene_preview.pack(anchor='w', pady=(0, 10))
        edit_scene_story_btn = ttk.Button(scene_story_frame, text="编辑 Story", command=lambda: None)
        edit_scene_story_btn.pack(pady=5)


        def update_previews():
            """根据 story_result 更新 RAW / scene_content 单行预览"""
            preview = _raw_story_preview_text(self.story_result)
            if preview:
                raw_preview.config(text=f"RAW: {preview}", foreground="black")
            else:
                raw_preview.config(text="RAW: (未生成)", foreground="gray")

            sp = _jsonish_preview_fragment(self.story_result.get("scene_content"), max_len=260)
            if sp:
                scene_preview.config(text=f"Story: {sp}", foreground="black")
            else:
                scene_preview.config(text="Story: (未填写)", foreground="gray")

        # 根据 topic 启用/禁用 RAW 编辑按钮
        def update_buttons_state(*args):
            has_topic = bool(self.story_result['topic_category'] and self.story_result['topic_subtype'])
            st = 'normal' if has_topic else 'disabled'
            edit_raw_btn.config(state=st)
            edit_scene_story_btn.config(state=st)


        def apply_initial_topic_selection():
            """把 __init__/YT 写入的 topic_category、topic_subtype 同步到下拉框（须在 update_buttons_state 之后）。"""
            cat = (self.story_result.get('topic_category') or '').strip()
            if not cat:
                return
            cats = list(topic_category_combo['values'])
            if cat not in cats:
                return
            topic_category_combo.set(cat)
            update_topic_subtype()
            sub = (self.story_result.get('topic_subtype') or '').strip()
            if sub:
                subs = list(topic_subtype_combo['values'])
                if sub in subs:
                    topic_subtype_combo.set(sub)
            update_explanation()
            update_buttons_state()

        apply_initial_topic_selection()


        def on_topic_category_selected(e):
            update_topic_subtype()
            update_explanation()
            update_buttons_state()

        def on_topic_subtype_selected(e):
            update_explanation()
            update_buttons_state()

        topic_category_combo.bind('<<ComboboxSelected>>', on_topic_category_selected)
        topic_subtype_combo.bind('<<ComboboxSelected>>', on_topic_subtype_selected)


        def open_project_content_editor(initial_text=None):
            """编辑 analyzed_content；确认后写回 ``story_result['analyzed_content']``（纯文本）。"""
            if initial_text is None:
                initial_text = self.story_result.get('analyzed_content')
            if isinstance(initial_text, str) and initial_text.strip():
                _prefill = initial_text.strip()
            else:
                _prefill = config.analyzed_content_text(initial_text) or None
            raw_dialog = tk.Toplevel(new_project_dialog)
            raw_dialog.title("项目内容 输入")
            raw_dialog.geometry("700x400")
            raw_dialog.transient(new_project_dialog)
            raw_dialog.grab_set()
            raw_dialog.update_idletasks()
            x = (raw_dialog.winfo_screenwidth() - 700) // 2
            y = (raw_dialog.winfo_screenheight() - 400) // 2
            raw_dialog.geometry(f"700x400+{x}+{y}")
            frame = ttk.Frame(raw_dialog, padding=20)
            frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(
                frame,
                text="请输入 Raw Case-Story（纯文本，当前项目语言）：",
                font=('TkDefaultFont', 10, 'bold'),
                wraplength=640,
                justify=tk.LEFT,
            ).pack(anchor='w', pady=(0, 5))
            case_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=70, height=12)
            case_text.pack(fill=tk.BOTH, expand=True)

            if _prefill:
                case_text.insert(tk.END, _prefill)

            def paste_on_double_click(e):
                try:
                    s = safe_clipboard_json_copy(raw_dialog.clipboard_get())
                    if s:
                        case_text.delete(1.0, tk.END)
                        case_text.insert(tk.END, s)
                except tk.TclError:
                    pass
            case_text.bind('<Double-1>', paste_on_double_click)

            raw_input_holder = [None]

            def on_ok():
                # 必须在 destroy 前读取文本；否则 wait_window 返回后控件已销毁会触发 TclError
                try:
                    raw_input_holder[0] = case_text.get('1.0', tk.END).strip()
                except tk.TclError:
                    raw_input_holder[0] = ""
                raw_dialog.destroy()

            btn_f = ttk.Frame(frame)
            btn_f.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(btn_f, text="确认", command=on_ok).pack(side=tk.LEFT, padx=5)

            raw_dialog.wait_window()

            raw_input = (raw_input_holder[0] or "").strip()
            if not raw_input:
                return
            normalized = config.normalize_analyzed_content_text(raw_input)
            if not _raw_content_valid_for_create(normalized):
                messagebox.showwarning(
                    "内容无效",
                    "无法保存：analyzed_content 须为非空文本。",
                    parent=new_project_dialog,
                )
                return

            self.story_result["analyzed_content"] = normalized
            update_buttons_state()
            update_previews()


        def open_scene_story_editor(initial_text=None):
            """粘贴 / 编辑 ``scene_content`` JSON；确认后刷新预览并按需同步标题输入框。"""
            if initial_text is None:
                initial_text = self.story_result.get('scene_content')
            if isinstance(initial_text, list):
                _scf = json.dumps(initial_text, ensure_ascii=False, indent=2)
            elif isinstance(initial_text, dict):
                _scf = json.dumps(initial_text, ensure_ascii=False, indent=2)
            elif isinstance(initial_text, str) and initial_text.strip():
                _scf = initial_text.strip()
            else:
                _scf = None
            dlg = tk.Toplevel(new_project_dialog)
            dlg.title("Story / scene_content 输入")
            dlg.geometry("820x620")
            dlg.transient(new_project_dialog)
            dlg.grab_set()
            dlg.update_idletasks()
            x = (dlg.winfo_screenwidth() - 820) // 2
            y = (dlg.winfo_screenheight() - 620) // 2
            dlg.geometry(f"820x620+{x}+{y}")
            frame = ttk.Frame(dlg, padding=20)
            frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(
                frame,
                text="请输入 scene_content JSON（NotebookLM 输出为场景 array，语言由项目语种决定）：",
                font=('TkDefaultFont', 10, 'bold'),
            ).pack(anchor='w', pady=(0, 5))
            text_w = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=94, height=28)
            text_w.pack(fill=tk.BOTH, expand=True)
            if _scf:
                text_w.insert(tk.END, _scf)

            def paste_sc(e=None):
                try:
                    s = safe_clipboard_json_copy(dlg.clipboard_get())
                    if s:
                        text_w.delete(1.0, tk.END)
                        text_w.insert(tk.END, s)
                except tk.TclError:
                    pass

            text_w.bind('<Double-1>', paste_sc)

            holder = [None]

            def ok_sc():
                try:
                    holder[0] = text_w.get('1.0', tk.END).strip()
                except tk.TclError:
                    holder[0] = ""
                dlg.destroy()

            bf = ttk.Frame(frame)
            bf.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(bf, text="确认", command=ok_sc).pack(side=tk.LEFT, padx=5)

            dlg.wait_window()

            raw_txt = (holder[0] or "").strip()
            if not raw_txt:
                return
            try:
                parsed_sc = json.loads(safe_clipboard_json_copy(raw_txt))
            except json.JSONDecodeError:
                return
            parsed_sc = config.normalize_scene_content_value(
                parsed_sc,
                self.story_result.get("language") or "",
            )
            if not parsed_sc:
                return
            self.story_result['scene_content'] = parsed_sc
            update_buttons_state()
            update_previews()
            refresh_title_entry_from_scene()


        edit_raw_btn.config(command=open_project_content_editor)
        edit_scene_story_btn.config(command=open_scene_story_editor)

        update_previews()
        if self.story_result.get('analyzed_content'):
            new_project_dialog.after(300, lambda: open_project_content_editor(initial_text=self.story_result.get('analyzed_content')))

        # 初始状态：按钮禁用（topic 未选时）
        update_buttons_state()
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)

        def on_create():
            pid = pid_entry.get().strip()
            title = title_entry.get().strip()
            resolution = resolution_var.get()
            
            if not pid:
                messagebox.showerror("错误", "请输入项目ID")
                return
            if not title:
                messagebox.showerror("错误", "请输入标题")
                return
            
            ac = self.story_result.get('analyzed_content')
            sc = self.story_result.get('scene_content')
            if not ac or not sc:
                messagebox.showerror("错误", "请先生成故事(Story)内容，才能创建项目")
                return

            _sc_title = title_from_scene_content(sc, self.story_result.get("language") or "")
            if _sc_title:
                title = _sc_title

            # 解析分辨率
            if resolution == "1920x1080":
                video_width = "1920"
                video_height = "1080"
            elif resolution == "1080x1920":
                video_width = "1080"
                video_height = "1920"
            else:
                # 默认值
                video_width = self.default_project_config['default_video_width']
                video_height = self.default_project_config['default_video_height']

            # self.story_result
            self.story_result['pid'] = pid
            self.story_result['video_title'] = title
            self.story_result['video_width'] = video_width
            self.story_result['video_height'] = video_height
            self.story_result['visual_style'] = new_project_visual_style_var.get()
            self.story_result['host_display'] = new_project_host_display_var.get()
            self.story_result['narrator'] = new_project_narrator_var.get()

            global LAST_NARRATOR, LAST_HOST_DISPLAY, LAST_VISUAL_STYLE
            LAST_VISUAL_STYLE = self.story_result['visual_style']
            LAST_HOST_DISPLAY = self.story_result['host_display']
            LAST_NARRATOR = self.story_result['narrator']

            self.story_result['action'] = 'new'
            # 保存 channel_id（多个 config key 可对应同一 channel_id）
            ch_id = config_channel.get_channel_id(self.story_result['channel'])
            self.story_result['channel'] = ch_id
            _ch_cfg = config_channel.get_channel_config(ch_id)
            self.story_result['channel_prompt'] = config_channel.get_channel_prompt_snapshot(ch_id)
            self.story_result.pop('prompts', None)
            self.story_result.pop('channel_template', None)
            self.story_result['scene_min_length'] = _ch_cfg.get('scene_min_length', 9)
            self.story_result['watermark'] = dict(_ch_cfg.get('watermark') or {})
            self.story_result['headmark'] = dict(_ch_cfg.get('headmark') or {})
            self.selected_config = self.story_result

            new_project_dialog.destroy()
            self.dialog.destroy()
        
        def on_cancel():
            new_project_dialog.destroy()
        
        ttk.Button(button_frame, text="创建", command=on_create).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # 等待对话框关闭
        new_project_dialog.wait_window()
    

    def open_selected(self):
        """打开选中的项目"""
        selection = self.project_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要打开的项目")
            return
        
        item = selection[0]
        config_file = self.project_tree.item(item)['tags'][0]
        self.selected_config = self.config_manager.load_project_config(config_file)
        
        if self.selected_config:
            # 更新全局 PROJECT_CONFIG（selected_config 已由 load_project_config 读取，无需重复 load_config）
            ProjectConfigManager.set_global_config(self.selected_config)
            self.config_manager.pid = self.selected_config.get('pid')
            self.story_result['action'] = 'open'
            self.dialog.destroy()
        else:
            messagebox.showerror("错误", "无法加载项目配置")
    
    def cancel(self):
        """取消"""
        self.story_result['action'] = 'cancel'
        self.dialog.destroy()
    
    def show(self):
        """显示对话框并等待结果"""
        self.dialog.wait_window()
        return self.story_result.get('action', 'cancel'), self.selected_config


def launch_yt_media_tool(
    parent,
    *,
    channel: str,
    language: str,
    narrator: str,
    visual_style: str,
    host_display: str,
    yt_method: str,
    yt_method_args: tuple = (),
):
    """独立 YT 入口：不再创建额外的「YT 管理」占位窗。

    日志控件仅创建、不 pack。勿对 ``parent`` 使用 ``withdraw()``：在 Windows 下会导致后续
    ``Toplevel(parent)``（选频道等）无法显示。改为将根窗移到屏外极小几何以保持 mapped。

    当 ``parent`` 下没有任何 ``Toplevel`` 子窗口时，轮询 ``quit()`` 结束 ``mainloop``。
    """
    global LAST_NARRATOR, LAST_VISUAL_STYLE, LAST_HOST_DISPLAY
    LAST_NARRATOR = narrator
    LAST_VISUAL_STYLE = visual_style
    LAST_HOST_DISPLAY = host_display

    ch = (channel or "").strip()
    lang = (language or "tw").strip()
    if not ch:
        messagebox.showwarning("提示", "请先选择频道", parent=parent)
        return

    try:
        parent.geometry("1x1+-3000+-3000")
        parent.update_idletasks()
    except tk.TclError:
        pass

    # 仅占位供回调签名使用，不布局 → 不出现在屏幕上
    _yt_log = tk.Text(parent)
    _yt_log.configure(height=1, width=1)

    def _yt_log_fn(w, m):
        try:
            w.insert(tk.END, m + "\n")
        except Exception:
            pass

    yt_gui = MediaGUIManager(parent, ch, "temp", {}, _yt_log_fn, _yt_log, language=lang)

    def _poll_standalone_exit():
        try:
            if not parent.winfo_exists():
                return
            has_dialog = any(isinstance(w, tk.Toplevel) for w in parent.winfo_children())
            if not has_dialog:
                parent.quit()
                return
        except tk.TclError:
            return
        parent.after(350, _poll_standalone_exit)

    def _run_yt_job():
        try:
            getattr(yt_gui, yt_method)(*yt_method_args)
        finally:
            parent.after(350, _poll_standalone_exit)

    # 须在 GUI_pm mainloop 启动后执行；勿在欢迎屏回调里同步跑长任务（否则 after(0) 弹窗不显示）
    parent.after(0, _run_yt_job)


def show_initial_choice_dialog(parent):
    """``GUI_pm.py`` 独立入口：频道/语言、风格/预留、旁白/HOST；四个 YT 功能按钮。

    视频/字幕语言在欢迎屏选择（``config.LANGUAGES``），不再在「项目管理」内二次弹窗。

    魔法工作流 ``GUI_wf.py`` 启动时不再经此函数，直接进入「选择项目」列表。
    """
    result = {
        'choice': 'cancel',
        'channel': '',
        'language': '',
        'narrator': LAST_NARRATOR,
        'visual_style': LAST_VISUAL_STYLE,
        'host_display': LAST_HOST_DISPLAY
    }

    dialog = tk.Toplevel(parent)
    dialog.title("YT 工具")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)

    main_frame = ttk.Frame(dialog, padding=30)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 第 1 行：频道（YT_text_download.json）、语言；第 2 行：风格、预留；第 3 行：旁白、HOST
    _yt_ch = config.load_yt_text_download_channel_options()
    _yt_display_to_id = _yt_ch["display_to_id"]
    default_lang_key = LAST_YT_LANGUAGE if LAST_YT_LANGUAGE in config.LANGUAGES else 'tw'
    _lang_display_to_key = {
        f"{label} ({key})": key for key, label in config.LANGUAGES.items()
    }
    _lang_options = list(_lang_display_to_key.keys())
    _lang_default_display = f"{config.LANGUAGES[default_lang_key]} ({default_lang_key})"

    _styles = list(config.VISUAL_STYLE_OPTIONS)
    try:
        _style_default = _styles[_styles.index(LAST_VISUAL_STYLE)]
    except ValueError:
        _style_default = _styles[0]

    opts_grid = ttk.Frame(main_frame)
    opts_grid.pack(fill=tk.X, pady=(0, 15))
    _combo_w = 28
    _row_gap = (10, 0)

    channel_var = tk.StringVar(value=_yt_ch["default_display"])
    channel_combo = ttk.Combobox(
        opts_grid,
        textvariable=channel_var,
        values=_yt_ch["display_options"],
        state="readonly",
        width=_combo_w,
    )
    language_var = tk.StringVar(value=_lang_default_display)
    language_combo = ttk.Combobox(
        opts_grid,
        textvariable=language_var,
        values=_lang_options,
        state="readonly",
        width=_combo_w,
    )
    language_combo.set(_lang_default_display)
    visual_style_var = tk.StringVar(value=_style_default)
    visual_style_combo = ttk.Combobox(
        opts_grid,
        textvariable=visual_style_var,
        values=_styles,
        state="readonly",
        width=_combo_w,
    )
    narrator_var = tk.StringVar(value=LAST_NARRATOR)
    narrator_combo = ttk.Combobox(
        opts_grid,
        textvariable=narrator_var,
        values=config.CHARACTER_PERSON_OPTIONS,
        state="readonly",
        width=_combo_w,
    )

    _hd_cur = config_prompt.HARRATOR_DISPLAY_OPTIONS[0]
    _host_opts = list(config_prompt.HARRATOR_DISPLAY_OPTIONS)
    _host_default = _hd_cur if _hd_cur in _host_opts else _host_opts[0]
    host_display_var = tk.StringVar(value=_host_default)
    host_display_combo_welcome = ttk.Combobox(
        opts_grid,
        textvariable=host_display_var,
        values=_host_opts,
        state="readonly",
        width=_combo_w,
    )
    reserved_var = tk.StringVar(value="")
    reserved_combo = ttk.Combobox(
        opts_grid,
        textvariable=reserved_var,
        values=(),
        state="disabled",
        width=_combo_w,
    )

    # 每行 2 组 label+combo；两列 combo 等宽
    ttk.Label(opts_grid, text="频道").grid(row=0, column=0, sticky="w", padx=(0, 6))
    channel_combo.grid(row=0, column=1, sticky="ew", padx=(0, 16))
    ttk.Label(opts_grid, text="语言").grid(row=0, column=2, sticky="w", padx=(0, 6))
    language_combo.grid(row=0, column=3, sticky="ew")

    ttk.Label(opts_grid, text="风格").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=_row_gap)
    visual_style_combo.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=_row_gap)
    ttk.Label(opts_grid, text="预留").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=_row_gap)
    reserved_combo.grid(row=1, column=3, sticky="ew", pady=_row_gap)

    ttk.Label(opts_grid, text="旁白").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=_row_gap)
    narrator_combo.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=_row_gap)
    ttk.Label(opts_grid, text="HOST").grid(row=2, column=2, sticky="w", padx=(0, 6), pady=_row_gap)
    host_display_combo_welcome.grid(row=2, column=3, sticky="ew", pady=_row_gap)

    for col in (1, 3):
        opts_grid.columnconfigure(col, weight=1, uniform="yt_welcome_combo")

    def _sync_result_narrator():
        global LAST_NARRATOR
        result['narrator'] = narrator_var.get()
        LAST_NARRATOR = result['narrator']

    def _sync_result_visual_style():
        global LAST_VISUAL_STYLE
        result['visual_style'] = visual_style_var.get()
        LAST_VISUAL_STYLE = result['visual_style']

    def _sync_result_host_display():
        global LAST_HOST_DISPLAY
        result['host_display'] = host_display_var.get()
        LAST_HOST_DISPLAY = result['host_display']

    def _resolve_language_key():
        display = (language_var.get() or "").strip()
        return _lang_display_to_key.get(display, default_lang_key)

    def _sync_result_language():
        global LAST_YT_LANGUAGE
        key = _resolve_language_key()
        result['language'] = key
        LAST_YT_LANGUAGE = key

    def _sync_welcome_choices():
        _sync_result_narrator()
        _sync_result_visual_style()
        _sync_result_host_display()
        _sync_result_language()

    def on_cancel():
        result['choice'] = 'cancel'
        dialog.destroy()

    def _resolve_welcome_channel_id():
        disp = (channel_var.get() or "").strip()
        return _yt_display_to_id.get(disp, _yt_ch["default_channel"])

    def _run_yt_tool(yt_method: str, *method_args):
        ch = _resolve_welcome_channel_id()
        if not ch:
            messagebox.showwarning("提示", "请先选择频道", parent=dialog)
            return
        _sync_welcome_choices()
        result["channel"] = ch
        result["choice"] = "yt"
        dialog.destroy()
        launch_yt_media_tool(
            parent,
            channel=ch,
            language=_resolve_language_key(),
            narrator=narrator_var.get(),
            visual_style=visual_style_var.get(),
            host_display=host_display_var.get(),
            yt_method=yt_method,
            yt_method_args=method_args,
        )

    _btn_row_gap = (0, 10)
    tk.Button(
        opts_grid,
        text="频道列表项目管理",
        font=('TkDefaultFont', 14, 'bold'),
        command=lambda: _run_yt_tool("manage_hot_videos"),
    ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(15, 10))

    ttk.Button(
        opts_grid,
        text="媒体文字转译",
        command=lambda: _run_yt_tool("transcribe_media", True),
    ).grid(row=4, column=1, sticky="ew", padx=(0, 16), pady=_btn_row_gap)
    ttk.Button(
        opts_grid,
        text="Download YT文字",
        command=lambda: _run_yt_tool("download_youtube", True, True),
    ).grid(row=4, column=3, sticky="ew", pady=_btn_row_gap)

    ttk.Button(
        opts_grid,
        text="Download YT視頻",
        command=lambda: _run_yt_tool("download_youtube", False, False),
    ).grid(row=5, column=1, sticky="ew", padx=(0, 16))
    ttk.Button(
        opts_grid,
        text="取消",
        command=on_cancel,
    ).grid(row=5, column=3, sticky="ew")

    dialog.update_idletasks()
    w, h = 520, 520
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    dialog.wait_window()
    return (
        result['choice'],
        result['channel'] or _yt_ch["default_channel"],
        result['language'] or default_lang_key,
        result.get('narrator') or LAST_NARRATOR,
        result.get('visual_style') or LAST_VISUAL_STYLE,
        result.get('host_display') or config_prompt.HARRATOR_DISPLAY_OPTIONS[-1],
    )


def create_project_dialog(parent, youtube_gui=None):
    """``GUI_wf.py``：直接进入「选择项目」列表（无欢迎屏新建入口）。"""
    global PROJECT_CONFIG
    config_manager = ProjectConfigManager()
    available_channels = list(config_channel.CHANNEL_CONFIG.keys())
    default_channel = available_channels[0] if available_channels else "default"

    dialog = ProjectSelectionDialog(
        parent=parent,
        config_manager=config_manager,
        youtube_gui=youtube_gui,
        create_only=False,
        initial_channel=default_channel,
        initial_language="tw",
        initial_narrator=LAST_NARRATOR,
        initial_visual_style=LAST_VISUAL_STYLE,
        initial_host_display=LAST_HOST_DISPLAY,
    )
    result, selected_config = dialog.show()

    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()
    return result, selected_config


def create_project_with_initial_raw(parent, channel, language, narrator, visual_style, host_display,
                                    analyzed_content, scene_content, topic_category, topic_subtype, topic_tags):
    """用现有 RAW 材料直接启动创建新项目。``analyzed_content`` 为纯文本字符串。"""
    global PROJECT_CONFIG
    if analyzed_content is None and scene_content is None:
        return 'cancel', None

    config_manager = ProjectConfigManager()
    _nar = narrator if narrator is not None else LAST_NARRATOR
    _vs = visual_style if visual_style is not None else LAST_VISUAL_STYLE
    _hd = host_display if host_display is not None else config_prompt.HARRATOR_DISPLAY_OPTIONS[-1]

    dialog = ProjectSelectionDialog(
        parent=parent,
        config_manager=config_manager,
        youtube_gui=None,
        create_only=True,

        initial_channel=channel, 
        initial_language=language,
        
        initial_narrator=_nar,
        initial_visual_style=_vs,
        initial_host_display=_hd,

        initial_analyzed_content=analyzed_content,
        initial_scene_content=scene_content,
        initial_category = topic_category,
        initial_subtype = topic_subtype,
        initial_tags = topic_tags
    )

    result = dialog.story_result.get('action', 'cancel')
    selected_config = dialog.selected_config
    if dialog.dialog.winfo_exists():
        dialog.dialog.destroy()
    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()

    # 不写盘：Downloader 等对「先有列表行再给 video_detail.project_profile」的路径必须在本函数返回后，
    # 先更新内存中的该行再保存 JSON；若此处 save_project_config，磁盘上尚无 pid，
    # 会落到 upsert「仅 profile」空行追加，与同 pid 的原视频重复一行。

    return result, selected_config

