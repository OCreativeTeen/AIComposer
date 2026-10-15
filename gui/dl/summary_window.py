"""story summary window helpers + clip review scheduling (moved verbatim from gui/downloader.py)."""
import config
from utility.ffmpeg_processor import resolve_watermark_for_channel
from utility.file_util import show_auto_close_popup
from gui.summary_mp4_review_dialog import ask_summary_mp4_review_segments, run_trim_concat_watermark_worker
import tkinter as tk
import tkinter.messagebox as messagebox
from gui.dl.youtube_dl import _youtube_row_display_title
from gui.dl.list_store import _persist_channel_videos
from gui.dl.gen_video_files import _gen_video_watermark_dest_filename, _set_gen_video_clip_segments


def _refresh_summary_window_title(
    summary_window: tk.Toplevel,
    video_detail: dict,
) -> None:
    """刷新摘要窗标题栏。"""
    try:
        if not summary_window.winfo_exists():
            return
    except tk.TclError:
        return
    ctx = getattr(summary_window, "_summary_drop_ctx", None) or {}
    idx = ctx.get("summary_title_index", "")
    suf = ctx.get("summary_dnd_title_suffix", "")
    title_part = _youtube_row_display_title(video_detail) or "—"
    # 前缀 STORY | 给听筒识别；长 YouTube 标题只留一段，避免截掉前缀。
    if len(title_part) > 72:
        title_part = title_part[:72].rstrip() + "…"
    idx_part = f"{idx} - " if str(idx).strip() else ""
    summary_window.title(f"STORY | {idx_part}{title_part}{suf}")


def _fit_story_summary_window(summary_window) -> None:
    """把预览窗高度收到内容底部，场景 JSON 下面不再留空带。"""
    try:
        if not summary_window.winfo_exists():
            return
    except tk.TclError:
        return
    try:
        summary_window.update_idletasks()
        bottom = 0
        for child in summary_window.winfo_children():
            try:
                bottom = max(bottom, child.winfo_y() + child.winfo_reqheight())
            except tk.TclError:
                continue
        if bottom < 80:
            return
        sw = summary_window.winfo_screenwidth()
        sh = summary_window.winfo_screenheight()
        try:
            chrome = summary_window.winfo_rooty() - summary_window.winfo_y()
        except tk.TclError:
            chrome = 0
        if chrome < 8:
            chrome = 32
        width = 1100
        height = min(max(bottom + chrome + 6, 240), sh - 36)
        x = max(0, (sw - width) // 2)
        y = 12
        summary_window.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError:
        pass


def schedule_summary_gen_video_clip_review(
    summary_window: tk.Toplevel,
    *,
    mgr,
    vd: dict,
    ctx: dict,
    mp4_paths: list[str] | None = None,
    initial_segments: list[dict] | None = None,
) -> None:
    """非阻塞：下一 Tk tick 打开审阅窗（供 CLI ``vc`` bridge 调用）。"""

    def _open():
        if not summary_window.winfo_exists():
            return
        _run_summary_gen_video_clip_review(
            summary_window,
            mgr=mgr,
            vd=vd,
            ctx=ctx,
            mp4_paths=mp4_paths,
            initial_segments=initial_segments,
        )

    summary_window.after(0, _open)


def _run_summary_gen_video_clip_review(
    summary_window: tk.Toplevel,
    *,
    mgr,
    vd: dict,
    ctx: dict,
    mp4_paths: list[str] | None = None,
    initial_segments: list[dict] | None = None,
) -> None:
    """打开审阅窗 → 保存片段到 scene_content clip 字段 → 拼接加水印写入 gen_video['video']。"""
    wm_path, wm_opts = resolve_watermark_for_channel(getattr(mgr, "channel", "") or "")
    if not wm_path:
        messagebox.showwarning(
            "加水印失败",
            r"未找到水印 PNG（请放在 program/<频道>/ 下，或配置频道 watermark.path）。",
            parent=summary_window,
        )
        return

    pid = getattr(mgr, "pid", "") or "yt_wm"
    lang = getattr(mgr, "language", "") or "zh"
    try:
        if initial_segments:
            segments = ask_summary_mp4_review_segments(
                summary_window,
                initial_segments=initial_segments,
                pid=pid,
                lang=lang,
            )
        else:
            segments = ask_summary_mp4_review_segments(
                summary_window,
                mp4_paths=mp4_paths or [],
                pid=pid,
                lang=lang,
            )
    except ValueError as ex:
        messagebox.showwarning("审阅", str(ex), parent=summary_window)
        return
    if not segments:
        return

    _set_gen_video_clip_segments(vd, segments)
    _persist_channel_videos(mgr)

    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "")
    dest_name = _gen_video_watermark_dest_filename(vd)

    def _on_worker_done(out_ok: str, err_msg: str, n_saved: int):
        root = getattr(mgr, "root", None) or summary_window.winfo_toplevel()

        def _done_ui():
            par = summary_window if summary_window.winfo_exists() else root
            if out_ok:
                vd["video"] = out_ok
                _persist_channel_videos(mgr)
                rfn = ctx.get("refresh_channel_tree")
                if callable(rfn):
                    try:
                        rfn()
                    except Exception:
                        pass
                rfn_pub = ctx.get("refresh_publish_row")
                if callable(rfn_pub):
                    try:
                        rfn_pub()
                    except Exception:
                        pass
                rfn_feat = ctx.get("refresh_feature_media_row")
                if callable(rfn_feat):
                    try:
                        rfn_feat()
                    except Exception:
                        pass
                if n_saved > 1:
                    msg = f"已裁剪并拼接 {n_saved} 段、加水印保存：\n{out_ok}"
                else:
                    msg = f"已裁剪并加水印保存：\n{out_ok}"
                show_auto_close_popup(par, "已保存", msg)
            elif err_msg:
                show_auto_close_popup(par, "加水印失败", err_msg, kind="error")

        root.after(0, _done_ui)

    run_trim_concat_watermark_worker(
        segments=segments,
        pid=pid,
        lang=lang,
        wm_path=wm_path,
        wm_opts=wm_opts or {},
        gen_dir=gen_dir,
        dest_name=dest_name,
        on_done=_on_worker_done,
    )
