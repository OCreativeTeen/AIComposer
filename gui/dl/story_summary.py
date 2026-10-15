"""StorySummaryImpl: methods moved verbatim from gui/downloader.py:MediaGUIManager."""
import json
import threading
import config
import config_prompt
from utility.file_util import show_auto_close_popup
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
from gui.clipboard_util import _copy_text_to_clipboard
from gui.dl.youtube_dl import _normalize_channel_list_item_for_storage, _normalize_channel_videos_for_storage, _write_channel_list_json_file
from gui.dl.list_store import _video_detail_project_pid


class StorySummaryImpl:
    def _summarize_scene_list(self, parent, video_detail: dict, scenes: list, *, on_done=None) -> None:
        """用这一条的场景文字生成摘要，拷到剪贴板，并可写回列表的 summary。"""
        if not scenes:
            messagebox.showinfo("生成摘要", "这里没有场景内容。", parent=parent)
            if callable(on_done):
                on_done()
            return
        prof = self._story_profile(video_detail)
        lang_code = (
            (prof.get("language") or "").strip()
            or (getattr(self, "language", "") or "").strip()
            or "tw"
        )
        lang_name = config.llm_language_label(lang_code)
        system_prompt = config_prompt.SPEAKING_SUMMARY_SYSTEM_PROMPT.format(language=lang_name)
        user_prompt = json.dumps(scenes, ensure_ascii=False)

        def work() -> None:
            err = ""
            out = ""
            try:
                out = self.llm_api.generate_text(system_prompt, user_prompt) or ""
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                if callable(on_done):
                    on_done()
                if err or not str(out).strip():
                    messagebox.showerror("生成摘要", err or "没有生成出摘要。", parent=parent)
                    return
                self._show_story_summary_editor(parent, video_detail, str(out))

            try:
                parent.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _show_story_summary_editor(self, parent, video_detail: dict, text: str) -> None:
        _copy_text_to_clipboard(parent, text)
        dlg = tk.Toplevel(parent)
        dlg.title("生成摘要")
        dlg.transient(parent)
        dlg.grab_set()
        dlg.geometry("720x480")
        dlg.update_idletasks()
        px = (dlg.winfo_screenwidth() - 720) // 2
        py = (dlg.winfo_screenheight() - 480) // 2
        dlg.geometry(f"720x480+{px}+{py}")
        ttk.Label(
            dlg,
            text="已复制到剪贴板。可编辑后点「保存到故事摘要」，写入这一条列表的 summary。",
            wraplength=680,
        ).pack(anchor="w", padx=12, pady=(12, 6))
        body = scrolledtext.ScrolledText(dlg, wrap=tk.WORD, width=88, height=20, font=("Arial", 10))
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        body.insert("1.0", text)
        btn_f = ttk.Frame(dlg)
        btn_f.pack(fill=tk.X, padx=12, pady=(0, 12))

        def on_save() -> None:
            saved = body.get("1.0", tk.END).strip()
            video_detail["summary"] = saved
            if not self._persist_video_detail_story(video_detail, parent=dlg):
                return
            dlg.destroy()
            messagebox.showinfo("摘要", "概述已写入这一条故事的 summary。", parent=parent)

        ttk.Button(btn_f, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text="保存到故事摘要", command=on_save).pack(side=tk.RIGHT)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

    def _persist_video_detail_story(self, video_detail: dict, *, parent=None) -> bool:
        """将 ``video_detail`` 同步进 ``channel_videos`` 并写入 ``channel_list_json``。"""
        if not isinstance(video_detail, dict):
            return False
        list_path = (getattr(self.downloader, "channel_list_json", None) or "").strip()
        if not list_path:
            show_auto_close_popup(
                parent,
                "保存失败",
                "未打开频道列表 JSON，无法保存。",
                kind="error",
            )
            return False
        row_key = (video_detail.get("id") or video_detail.get("url") or "").strip()
        wf_pid = _video_detail_project_pid(video_detail)
        for row in self.downloader.channel_videos:
            if not isinstance(row, dict):
                continue
            rk = (row.get("id") or row.get("url") or "").strip()
            if row_key and rk and rk == row_key:
                if row is not video_detail:
                    row.clear()
                    row.update(video_detail)
                break
            if wf_pid and _video_detail_project_pid(row) == wf_pid:
                if row is not video_detail:
                    row.clear()
                    row.update(video_detail)
                break
        ch_path = self.channel_path or ""
        _normalize_channel_list_item_for_storage(video_detail, ch_path)
        _normalize_channel_videos_for_storage(
            self.downloader.channel_videos, ch_path
        )
        try:
            _write_channel_list_json_file(list_path, self.downloader.channel_videos)
            return True
        except OSError as e:
            show_auto_close_popup(
                parent,
                "保存失败",
                f"写入频道列表失败：{e}",
                kind="error",
            )
            return False
