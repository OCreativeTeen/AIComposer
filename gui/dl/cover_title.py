"""cover image save + title dialog (moved verbatim from gui/downloader.py)."""
import os
import time
import threading
import copy
import config
from utility.ffmpeg_processor import FfmpegProcessor, resolve_watermark_for_channel
from utility.file_util import safe_copy_overwrite, safe_remove, make_safe_file_name, show_auto_close_popup
import project_manager
import tkinter as tk
import tkinter.ttk as ttk
from gui.dl.youtube_dl import _normalize_channel_list_item_for_storage, _youtube_row_display_title, _youtube_row_source_title
from gui.dl.list_store import _persist_channel_videos
from gui.dl.gen_video_files import _gen_video_cover_webp_dest_filename, _title_from_cover_image_path
from gui.dl.summary_window import _refresh_summary_window_title


def _apply_project_video_title(video_detail: dict, title: str) -> None:
    """有 ``project_profile`` 时，用成片名更新 ``video_title``。"""
    if not isinstance(video_detail, dict):
        return
    vt = (title or "").strip()
    if not vt:
        return
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if not isinstance(prof, dict) or not prof:
        return
    merged = copy.deepcopy(prof)
    merged["video_title"] = vt
    video_detail[project_manager.PROJECT_PROFILE_KEY] = (
        project_manager.profile_for_list_storage(merged)
    )


def _scene_captions_for_cover_title(video_detail: dict) -> list[str]:
    sc = video_detail.get("scene_content") if isinstance(video_detail, dict) else None
    if not isinstance(sc, list):
        return []
    out: list[str] = []
    for item in sc:
        if not isinstance(item, dict):
            continue
        cap = project_manager.caption_from_scene_content_item(item)
        if cap:
            out.append(cap)
    return out


def _cover_save_story_title(video_detail: dict) -> str:
    """当前故事名：成片名优先，否则列表行原标题。"""
    return (
        _youtube_row_display_title(video_detail)
        or _youtube_row_source_title(video_detail)
    ).strip()


def _cover_title_preset_options(
    video_detail: dict,
    *,
    image_path: str = "",
) -> list[tuple[str, str]]:
    """``(下拉显示, 填入成片名)``；故事原名始终第一项。"""
    options: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, value: str) -> None:
        v = (value or "").strip()
        if not v or v in seen:
            return
        seen.add(v)
        shown = v if len(v) <= 56 else v[:56] + "…"
        options.append((f"{label}：{shown}", v))

    add("故事原名", _cover_save_story_title(video_detail))
    img = _title_from_cover_image_path(image_path)
    if img:
        add("图片文件名", img)
    for i, cap in enumerate(_scene_captions_for_cover_title(video_detail), 1):
        add(f"场景 {i}", cap)
    if not options:
        add("故事原名", "")
    return options


def _apply_video_title_before_cover_save(
    video_detail: dict,
    *,
    video_title: str,
    channel_path: str = "",
) -> None:
    """保存封面前：仅更新 ``project_profile.video_title``（不改场景 caption / 原视频标题）。"""
    if not isinstance(video_detail, dict):
        return
    vt = (video_title or "").strip()
    if not vt:
        return
    _apply_project_video_title(video_detail, vt)
    _normalize_channel_list_item_for_storage(video_detail, channel_path or "")


def _ask_video_title_before_cover_save_dialog(
    parent,
    video_detail: dict,
    *,
    image_path: str = "",
) -> dict | None:
    """保存封面前让用户确认成片名；默认保持故事原名。取消则放弃本次粘贴/拖放。"""
    if not isinstance(video_detail, dict):
        return None
    has_project_profile = project_manager.list_json_row_has_project_profile(
        video_detail
    )
    source_title = _youtube_row_source_title(video_detail)
    story_title = _cover_save_story_title(video_detail)
    presets = _cover_title_preset_options(video_detail, image_path=image_path)
    label_to_value = {lab: val for lab, val in presets}
    result_holder: dict | None = None
    dlg = tk.Toplevel(parent)
    dlg.title("保存封面前 — 确认视频标题")
    dlg.geometry("720x280")
    dlg.minsize(520, 240)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"720x280+{(sw - 720) // 2}+{(sh - 280) // 2}")

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    hint = (
        "默认保持故事原名。可用下拉改用图片文件名或某个场景的 caption，"
        "也可以在下方输入框里自己改。"
        "不会修改原视频标题（YouTube 下载名），也不会改各场景 caption。"
    )
    if has_project_profile:
        hint += " 若选用其它名字，会更新 project_profile.video_title。"
    ttk.Label(frm, text=hint, wraplength=680, justify=tk.LEFT).pack(
        anchor=tk.W, pady=(0, 10)
    )

    if source_title:
        src_row = ttk.Frame(frm)
        src_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(src_row, text="原视频标题（只读）:", width=18).pack(side=tk.LEFT)
        ttk.Label(
            src_row,
            text=source_title,
            wraplength=560,
            foreground="#555",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    pick_box = ttk.LabelFrame(frm, text="选用名称", padding=8)
    pick_box.pack(fill=tk.X, pady=(0, 8))
    combo_var = tk.StringVar(value=presets[0][0])
    combo = ttk.Combobox(
        pick_box,
        textvariable=combo_var,
        values=[lab for lab, _ in presets],
        state="readonly",
        width=86,
    )
    combo.pack(fill=tk.X)

    title_box = ttk.LabelFrame(frm, text="成片名（可手改）", padding=8)
    title_box.pack(fill=tk.X, pady=(0, 10))
    title_var = tk.StringVar(value=story_title)
    title_entry = ttk.Entry(title_box, textvariable=title_var, width=90)
    title_entry.pack(fill=tk.X)
    title_entry.focus_set()
    title_entry.selection_range(0, tk.END)

    def on_preset_selected(_event=None) -> None:
        lab = (combo_var.get() or "").strip()
        val = label_to_value.get(lab, "")
        title_var.set(val)
        title_entry.selection_range(0, tk.END)

    combo.bind("<<ComboboxSelected>>", on_preset_selected)

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X)

    def on_confirm():
        nonlocal result_holder
        vt = (title_var.get() or "").strip()
        skip = (not vt) or (vt == story_title)
        result_holder = {"video_title": vt, "skip_title_update": skip}
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row, text="确认并继续", command=on_confirm).pack(side=tk.RIGHT)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.wait_window()
    return result_holder


def save_cover_image_as_gen_video_webp(
    image_path: str,
    video_detail: dict,
    *,
    channel: str = "",
    pid: str = "yt_img",
    lang: str = "zh",
    cleanup_source: bool = False,
) -> tuple[bool, str, str]:
    """加水印并写入 ``gen_video/<源图文件名>.webp``（保留如 ``Infographic_2.webp``；同步；不弹窗）。

    Returns ``(ok, dest_abs, error_msg)``.
    """
    if not isinstance(video_detail, dict):
        return False, "", "invalid video_detail"
    src = (image_path or "").strip()
    if not src or not os.path.isfile(src):
        return False, "", f"封面源文件不存在: {src or image_path}"

    wm_path, wm_opts = resolve_watermark_for_channel(channel or "")
    if not wm_path:
        return (
            False,
            "",
            r"未找到水印 PNG（请放在 program/<频道>/ 下，或配置频道 watermark.path）。",
        )

    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    dest_name = _gen_video_cover_webp_dest_filename(
        video_detail, source_image_path=src
    )
    wm_webp = ""
    webp_tmp = ""
    out_ok = ""
    err_msg = ""
    try:
        os.makedirs(gen_dir, exist_ok=True)
        ff = FfmpegProcessor(pid or "yt_img", lang or "zh")
        wm_webp = ff.apply_watermark_to_flat_image(src, wm_path, wm_opts or {})
        if not wm_webp or not os.path.isfile(wm_webp):
            return False, "", "图片叠加水印失败。"
        webp_tmp = ff.image_to_webp(wm_webp)
        if not webp_tmp or not os.path.isfile(webp_tmp):
            return False, "", "图片转 WebP 失败。"
        dest_abs = os.path.join(gen_dir, dest_name)
        safe_copy_overwrite(webp_tmp, dest_abs)
        out_ok = os.path.abspath(dest_abs)
    except Exception as ex:
        err_msg = str(ex)
    finally:
        if cleanup_source and src and os.path.isfile(src):
            try:
                safe_remove(src)
            except Exception:
                pass
        for tmp in (wm_webp, webp_tmp):
            if tmp and tmp != out_ok and os.path.isfile(tmp):
                try:
                    safe_remove(tmp)
                except Exception:
                    pass
    if out_ok:
        if isinstance(video_detail, dict):
            project_manager.append_cover_image(video_detail, out_ok)
        return True, out_ok, ""
    return False, "", err_msg or "保存封面失败"


def save_pil_image_to_cover_array(
    pil_image,
    video_detail: dict,
    *,
    channel: str = "",
    pid: str = "yt_img",
    lang: str = "zh",
    filename_hint: str = "",
) -> tuple[bool, str, str]:
    """将 PIL Image 保存为临时文件，加水印并追加到 cover_image 数组。

    Returns ``(ok, dest_abs, error_msg)``.
    """
    import tempfile

    if not isinstance(video_detail, dict):
        return False, "", "invalid video_detail"
    if pil_image is None or not hasattr(pil_image, "save"):
        return False, "", "invalid PIL image"

    hint = (filename_hint or "").strip()
    if not hint:
        hint = f"workflow_image_{int(time.time())}"
    hint = make_safe_file_name(hint)
    if not hint.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        hint = hint + ".png"

    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(hint)[1] or ".png")
    os.close(fd)
    try:
        pil_image.save(tmp_path)
    except Exception as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False, "", f"保存临时图片失败: {exc}"

    ok, dest, err = save_cover_image_as_gen_video_webp(
        tmp_path,
        video_detail,
        channel=channel,
        pid=pid,
        lang=lang,
        cleanup_source=True,
    )
    return ok, dest, err


def accept_summary_cover_image(
    image_path: str,
    summary_window: tk.Toplevel,
    ctx: dict,
    *,
    interactive: bool = True,
    async_ui: bool = True,
    refresh_ui: bool = True,
    cleanup_source: bool = False,
    title_override: str | None = None,
) -> tuple[bool, str]:
    """接受一张图片作为当前 STORY 的 gen_video 封面。

  * ``interactive=True``（拖放）：弹窗确认成片名；默认保持故事原名。
  * ``interactive=False``（``itc N`` / Telegram）：不弹窗、不改故事名。
    """
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return False, "STORY 上下文无效（mgr / video_detail）"
    if not image_path or not os.path.isfile(image_path):
        return False, "封面图片路径无效"

    def _apply_cover_title_and_refresh_ui(video_title: str) -> None:
        vt = (video_title or "").strip()
        if not vt:
            return
        ch_path = getattr(mgr, "channel_path", "") or ""
        _apply_video_title_before_cover_save(
            vd,
            video_title=vt,
            channel_path=ch_path,
        )
        if not _persist_channel_videos(mgr):
            return
        if not refresh_ui:
            return
        rfn_title = ctx.get("refresh_title_fields") if isinstance(ctx, dict) else None
        if callable(rfn_title):
            try:
                rfn_title()
            except Exception:
                _refresh_summary_window_title(summary_window, vd)
        else:
            _refresh_summary_window_title(summary_window, vd)
        refresh_tree = ctx.get("refresh_channel_tree") if isinstance(ctx, dict) else None
        if callable(refresh_tree):
            try:
                refresh_tree()
            except Exception:
                pass

    if interactive:
        par = summary_window if summary_window.winfo_exists() else (
            getattr(mgr, "root", None) or summary_window.winfo_toplevel()
        )
        title_choice = _ask_video_title_before_cover_save_dialog(
            par, vd, image_path=image_path
        )
        if title_choice is None:
            if cleanup_source and image_path and os.path.isfile(image_path):
                try:
                    safe_remove(image_path)
                except Exception:
                    pass
            return False, "已取消保存封面"
        if not title_choice.get("skip_title_update"):
            _apply_cover_title_and_refresh_ui(title_choice.get("video_title", ""))
    elif title_override is not None:
        _apply_cover_title_and_refresh_ui(title_override)

    channel = getattr(mgr, "channel", "") or ""
    pid = getattr(mgr, "pid", "") or "yt_img"
    lang = getattr(mgr, "language", "") or "zh"

    def _finish_ui(out_ok: str, err_msg: str) -> tuple[bool, str]:
        if out_ok:
            vd["cover_image"] = out_ok
            _persist_channel_videos(mgr)
        if refresh_ui:
            rfn_feat = ctx.get("refresh_feature_media_row") if isinstance(ctx, dict) else None
            if callable(rfn_feat):
                try:
                    rfn_feat()
                except Exception:
                    pass
        if out_ok:
            if interactive:
                par = summary_window if summary_window.winfo_exists() else (
                    getattr(mgr, "root", None) or summary_window.winfo_toplevel()
                )
                show_auto_close_popup(
                    par,
                    "封面已保存",
                    f"已加水印并保存为 WebP：\n{out_ok}",
                )
                return True, f"封面已保存: {out_ok}"
            return True, f"封面已保存: {out_ok}"
        if interactive:
            par = summary_window if summary_window.winfo_exists() else (
                getattr(mgr, "root", None) or summary_window.winfo_toplevel()
            )
            show_auto_close_popup(par, "保存失败", err_msg or "保存封面失败", kind="error")
        return False, err_msg or "保存封面失败"

    if not async_ui:
        ok, dest, err = save_cover_image_as_gen_video_webp(
            image_path,
            vd,
            channel=channel,
            pid=pid,
            lang=lang,
            cleanup_source=cleanup_source,
        )
        return _finish_ui(dest if ok else "", err)

    def _worker():
        ok, out_ok, err_msg = save_cover_image_as_gen_video_webp(
            image_path,
            vd,
            channel=channel,
            pid=pid,
            lang=lang,
            cleanup_source=cleanup_source,
        )
        root = getattr(mgr, "root", None) or summary_window.winfo_toplevel()

        def _done_ui():
            _finish_ui(out_ok if ok else "", err_msg)

        root.after(0, _done_ui)

    threading.Thread(target=_worker, daemon=True).start()
    return True, "封面保存中…"
