"""publish schedule dialog + published-media filing (moved verbatim from gui/downloader.py)."""
import os
import json
import re
import config
from datetime import datetime, timedelta
from utility.file_util import show_auto_close_popup
try:
    from tkcalendar import Calendar as TkCalendar
except ImportError:
    TkCalendar = None
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
from utility.file_util import _move_file_to_dest_with_fallback
from utility.time_util import _format_publish_display_date
from gui.dl.youtube_dl import _video_youtube_id
from gui.dl.gen_video_files import _find_gen_video_mp4_for_row


def _gen_video_publish_mp4_if_ready(video: dict) -> str:
    """gen_video 下任一候选 stem 的 ``.mp4`` 存在即有成片（频道行 / 项目行不区别对待）。"""
    return _find_gen_video_mp4_for_row(video)


def _apply_publish_create_date(
    video_detail: dict,
    *,
    publish_at,
    published_iso: str = "",
) -> None:
    """记录本工具上传到 YouTube 的日期（``create_date``，YYYYMMDD）；不改 ``upload_date``。"""
    if not isinstance(video_detail, dict):
        return
    iso = (published_iso or "").strip()
    if iso:
        try:
            _dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            video_detail["create_date"] = _dt.astimezone().strftime("%Y%m%d")
            return
        except Exception:
            pass
    if publish_at is not None:
        local_tz = datetime.now().astimezone().tzinfo
        pa = (
            publish_at
            if getattr(publish_at, "tzinfo", None)
            else publish_at.replace(tzinfo=local_tz)
        )
        video_detail["create_date"] = pa.astimezone().strftime("%Y%m%d")
    else:
        video_detail["create_date"] = datetime.now().strftime("%Y%m%d")


_INPUT_PUBLISH_TXT_RE = re.compile(r"^__\d+__.+\.txt$", re.IGNORECASE)


def _scan_input_media_publish_map():
    """扫描 config.INPUT_MEDIA_PATH，返回 {youtube_id: {txt_path, mp4_path}}。"""
    out = {}
    base = getattr(config, "INPUT_MEDIA_PATH", None)
    if not base or not os.path.isdir(base):
        return out
    try:
        for name in os.listdir(base):
            if not _INPUT_PUBLISH_TXT_RE.match(name):
                continue
            txt_path = os.path.join(base, name)
            if not os.path.isfile(txt_path):
                continue
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            yid = (data.get("id") or "").strip()
            if not yid:
                continue
            stem = os.path.splitext(name)[0]
            mp4_path = os.path.join(base, stem + ".mp4")
            out[yid] = {"txt_path": txt_path, "mp4_path": mp4_path}
    except Exception:
        pass
    return out


def _folder_english_prefix(folder_name: str) -> str:
    """如 Identity__人格防御... → 'Identity'。"""
    if not folder_name:
        return ""
    return folder_name.split("__", 1)[0] if "__" in folder_name else folder_name


def _parse_input_media_category_short_code(basename_no_ext: str) -> str:
    """从 __102__Identi__Slug_ 形式解析中间简码（如 Identi）。"""
    if not basename_no_ext.startswith("__"):
        return ""
    parts = basename_no_ext.split("__")
    if len(parts) >= 4 and parts[1].isdigit():
        return (parts[2] or "").strip()
    return ""


def _find_category_subfolder(parent_dir: str, short_code: str, topic_category: str):
    """在 parent_dir 下找与 video_detail['topic_category'] 或文件名简码前缀匹配的子文件夹。"""
    try:
        names = os.listdir(parent_dir)
    except OSError:
        return None
    dirs = [n for n in names if os.path.isdir(os.path.join(parent_dir, n))]
    tc = (topic_category or "").strip()
    if tc:
        for n in dirs:
            en = _folder_english_prefix(n)
            if en == tc or n.startswith(tc + "__"):
                return n
    sc = (short_code or "").strip()
    if not sc:
        return None
    best = None
    best_len = -1
    for n in dirs:
        en = _folder_english_prefix(n)
        if en.startswith(sc) and len(en) > best_len:
            best = n
            best_len = len(en)
    return best


def _is_already_in_category_folder(current_dir: str, short_code: str, topic_category: str) -> bool:
    """已在名称匹配的子文件夹内（如 Identity__xxx）则不再移动。"""
    base = os.path.basename(current_dir.rstrip("/\\"))
    if not base:
        return False
    en = _folder_english_prefix(base)
    tc = (topic_category or "").strip()
    if tc and en == tc:
        return True
    sc = (short_code or "").strip()
    if sc and en.startswith(sc):
        return True
    return False


def _move_published_input_media_files(mp4_path: str, video_detail: dict) -> str:
    """发布后把同 stem 的 mp4/png/txt 移入同级分类子文件夹；返回给 UI 的说明。"""
    mp4_path = os.path.abspath(mp4_path)
    parent = os.path.dirname(mp4_path)
    stem, _ = os.path.splitext(os.path.basename(mp4_path))
    short_code = _parse_input_media_category_short_code(stem)
    topic_category = (video_detail.get("topic_category") or "").strip()

    if not short_code and not topic_category:
        return ""

    if _is_already_in_category_folder(parent, short_code, topic_category):
        return "成品已在分类文件夹内，未移动。"

    sub = _find_category_subfolder(parent, short_code, topic_category)
    if not sub:
        hint = short_code or topic_category
        return f"未找到与「{hint}」对应的分类子文件夹，文件未移动。"

    dest_dir = os.path.join(parent, sub)
    if not os.path.isdir(dest_dir):
        return "分类文件夹不存在，未移动。"

    moved = []
    for ext in (".mp4", ".png", ".txt"):
        src = os.path.join(parent, stem + ext)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest_dir, os.path.basename(src))
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
            continue
        try:
            _move_file_to_dest_with_fallback(src, dst)
            moved.append(ext)
        except OSError as e:
            return f"归档失败（{ext}）：{e}"

    if not moved:
        return "未找到可移动的同名 .mp4/.png/.txt，未移动。"
    return f"已将成品移入文件夹：{sub}"


def _publish_cell_display(video: dict, input_map: dict):
    """返回 (列文本, 状态 published|ready|txt|na, 用于发布的 mp4 绝对路径)。

    可发布：优先 gen_video 下任一条目候选 stem 的 ``.mp4``（参见 ``_find_gen_video_mp4_for_row``）；其次 input 目录 __*__.txt + 同名 mp4。
    已上传：``publish`` 有值即显示为已发布。
    """
    pub = (video.get("publish") or "").strip()
    if pub:
        return _format_publish_display_date(pub) + " ✓", "published", ""

    mp4_gv = _gen_video_publish_mp4_if_ready(video)
    if mp4_gv:
        return "ready", "ready", mp4_gv

    yid = _video_youtube_id(video)
    if yid and yid in input_map:
        entry = input_map[yid] or {}
        txt_path = (entry.get("txt_path") or "").strip()
        mp4_path = os.path.abspath(entry.get("mp4_path") or "") if entry.get("mp4_path") else ""
        if txt_path and os.path.isfile(txt_path):
            if mp4_path and os.path.isfile(mp4_path):
                return "ready", "ready", mp4_path
            return "TXT", "txt", ""

    return "N/A", "na", ""


def _resolve_review_publish_mp4_path(video_detail: dict, input_map: dict) -> str:
    """本条用于「审阅并发布」的成品 mp4：gen_video → input 联名；不限于列表「ready」状态（已上传也可再找文件重投）。"""
    if not isinstance(video_detail, dict):
        return ""
    _, _, mp4 = _publish_cell_display(video_detail, input_map)
    p = (mp4 or "").strip()
    if p and os.path.isfile(p):
        return os.path.abspath(p)
    gv = _gen_video_publish_mp4_if_ready(video_detail)
    if gv and os.path.isfile(gv):
        return gv
    yid = _video_youtube_id(video_detail)
    if yid and yid in input_map:
        cand = (input_map.get(yid) or {}).get("mp4_path") or ""
        cand = cand.strip()
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    return ""


def ask_publish_schedule_dialog(parent, mp4_path_hint=None, dialog_title="上传至 YouTube"):
    """
    与 GUI_wf.py _ask_upload_schedule 相同：立即上传或定时公开；tkcalendar 可选。
    返回 None 表示取消；("immediate", None) 或 ("scheduled", datetime)。
    """
    result = {"ok": False, "mode": "immediate", "dt": None}
    dlg = tk.Toplevel(parent)
    dlg.title(dialog_title)
    dlg.transient(parent)
    dlg.resizable(True, True)
    dlg.geometry("440x560")
    dlg.grab_set()

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    if mp4_path_hint:
        ttk.Label(frm, text=f"视频文件:\n{mp4_path_hint}", wraplength=410, justify=tk.LEFT).pack(anchor="w", pady=(0, 8))

    ttk.Label(
        frm,
        text=(
            "YouTube API 支持定时「公开」：上传时为私有，到点自动公开。\n"
            "「首映 Premiere」需在 YouTube Studio 里单独设置。"
        ),
        wraplength=410,
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(0, 10))

    mode_var = tk.StringVar(value="scheduled")
    ttk.Radiobutton(
        frm,
        text="立即上传（不公开列出，与原先一致）",
        variable=mode_var,
        value="immediate",
    ).pack(anchor="w")
    ttk.Radiobutton(
        frm,
        text="定时发布（指定日期与时刻后由 YouTube 自动公开）",
        variable=mode_var,
        value="scheduled",
    ).pack(anchor="w", pady=(0, 6))

    sched_frame = ttk.LabelFrame(frm, text="日期与时间（本机本地时区）", padding=8)
    sched_frame.pack(fill=tk.BOTH, expand=True, pady=6)

    now = datetime.now()
    local_tz = now.astimezone().tzinfo

    cal_widget = None
    y_var = tk.IntVar(value=now.year)
    m_var = tk.IntVar(value=now.month)
    d_var = tk.IntVar(value=now.day)
    h_var = tk.IntVar(value=min(now.hour + 1, 23))
    min_var = tk.IntVar(value=0)

    if TkCalendar is not None:
        cal_widget = TkCalendar(
            sched_frame,
            selectmode="day",
            date_pattern="yyyy-mm-dd",
            year=now.year,
            month=now.month,
            day=now.day,
        )
        cal_widget.pack(pady=4)
    else:
        rowd = ttk.Frame(sched_frame)
        rowd.pack(fill=tk.X, pady=2)
        ttk.Label(rowd, text="年").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=now.year, to=now.year + 3, textvariable=y_var, width=6).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(rowd, text="月").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=1, to=12, textvariable=m_var, width=4).pack(side=tk.LEFT, padx=4)
        ttk.Label(rowd, text="日").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=1, to=31, textvariable=d_var, width=4).pack(side=tk.LEFT, padx=4)

    rowt = ttk.Frame(sched_frame)
    rowt.pack(fill=tk.X, pady=4)
    ttk.Label(rowt, text="时 (0–23)").pack(side=tk.LEFT)
    tk.Spinbox(rowt, from_=0, to=23, textvariable=h_var, width=4).pack(side=tk.LEFT, padx=6)
    ttk.Label(rowt, text="分 (0–59)").pack(side=tk.LEFT)
    tk.Spinbox(rowt, from_=0, to=59, textvariable=min_var, width=4).pack(side=tk.LEFT, padx=6)

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X, pady=(12, 0))

    def on_ok():
        if mode_var.get() == "immediate":
            result["ok"] = True
            result["mode"] = "immediate"
            result["dt"] = None
            dlg.destroy()
            return
        if TkCalendar is not None and cal_widget is not None:
            dstr = cal_widget.get_date()
            try:
                y, mo, da = map(int, dstr.split("-"))
            except ValueError:
                show_auto_close_popup(dlg, "日期错误", "无法解析日历日期（需 yyyy-mm-dd）。", kind="error")
                return
        else:
            y, mo, da = y_var.get(), m_var.get(), d_var.get()
        try:
            dt = datetime(y, mo, da, h_var.get(), min_var.get(), 0, tzinfo=local_tz)
        except ValueError as e:
            show_auto_close_popup(dlg, "日期错误", str(e), kind="error")
            return
        min_future = datetime.now(local_tz) + timedelta(minutes=2)
        if dt <= min_future:
            messagebox.showwarning("时间", "请选择至少约 2 分钟后的时间。", parent=dlg)
            return
        result["ok"] = True
        result["mode"] = "scheduled"
        result["dt"] = dt
        dlg.destroy()

    def on_cancel():
        result["ok"] = False
        dlg.destroy()

    ttk.Button(btn_row, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT)
    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.update_idletasks()
    px = (dlg.winfo_screenwidth() - 440) // 2
    py = (dlg.winfo_screenheight() - 560) // 2
    dlg.geometry(f"440x560+{px}+{py}")
    dlg.wait_window()
    if not result["ok"]:
        return None
    return (result["mode"], result["dt"])
