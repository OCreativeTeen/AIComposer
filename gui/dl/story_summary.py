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
    def _story_summary_prompts(self, video_detail: dict, scenes: list, analysis: str = "") -> tuple:
        """t112u: 摘要提示词(频道 soul + 分析报告 + 场景)。"""
        import os

        prof = self._story_profile(video_detail)
        lang_code = (
            (prof.get("language") or "").strip()
            or (getattr(self, "language", "") or "").strip()
            or "tw"
        )
        channel = (prof.get("channel") or "").strip() or os.path.basename(
            os.path.normpath(getattr(self, "channel_path", "") or "")
        )
        if not (analysis or "").strip():
            raw = video_detail.get("analyzed_content") if isinstance(video_detail, dict) else ""
            analysis = raw if isinstance(raw, str) else str(raw or "")
        return config_prompt.build_story_summary_prompts(
            video_detail, scenes, analysis, config.llm_language_label(lang_code), channel
        )

    def _auto_summarize_story(self, parent, video_detail: dict, scenes: list, analysis: str = "", *, view=None) -> None:
        """t112u: 场景生成后自动生成摘要(后台),直接写进这一条的 summary。失败只打日志。"""
        if not scenes:
            return
        try:
            system_prompt, user_prompt = self._story_summary_prompts(video_detail, scenes, analysis)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 自动摘要:提示词没做出来:{exc}")
            return
        # t113u: view = STORY 窗的摘要框 {"start"(), "done"(text)->bool 是否已显示, "fail"(msg)}
        view = view if isinstance(view, dict) else {}

        def _call(key, *a):
            fn = view.get(key)
            if callable(fn):
                try:
                    return fn(*a)
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 摘要框更新失败:{exc}")
            return None

        _call("start")

        def _fail(msg: str) -> None:
            print(f"⚠️ 自动摘要失败:{msg}")
            try:
                parent.after(0, lambda: _call("fail", msg))
            except (tk.TclError, RuntimeError):
                pass

        def work() -> None:
            try:
                out = (self.llm_api.generate_text(system_prompt, user_prompt) or "").strip()
            except Exception as exc:  # noqa: BLE001
                _fail(str(exc))
                return
            if not out:
                _fail("LLM 没有返回内容。")
                return
            try:  # t168u: 每次生成的摘要都追加进生成历史
                from gui.dl import gen_history
                # t169u: 记真正回答的那一个：_last_source = Strata 的模型 id，或 manual（手动窗口里贴回的）
                src = str(getattr(self.llm_api, "_last_source", "") or getattr(self.llm_api, "model", "") or "")
                gen_history.record(video_detail, "summaries", gen_history.display_backend(src), out)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 摘要没有记进历史：{exc}")

            def done() -> None:
                try:
                    shown = _call("done", out)
                    if shown is False:
                        print("ℹ️ 自动摘要生成好了,但摘要框正在被编辑,没有覆盖。")
                        return
                    video_detail["summary"] = out
                    if self._persist_video_detail_story(video_detail, parent=parent):
                        print(f"✅ 自动摘要已写入 summary({len(out)} 字)")
                        if shown is None:  # 没有摘要框时才弹提示
                            show_auto_close_popup(parent, "摘要", "已自动生成摘要，写入这一条的 summary。")
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 自动摘要没有保存:{exc}")

            try:
                parent.after(0, done)
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True, name="story-summary").start()

    def _summarize_scene_list(self, parent, video_detail: dict, scenes: list, *, on_done=None) -> None:
        """用这一条的场景文字生成摘要，拷到剪贴板，并可写回列表的 summary。"""
        if not scenes:
            messagebox.showinfo("生成摘要", "这里没有场景内容。", parent=parent)
            if callable(on_done):
                on_done()
            return
        system_prompt, user_prompt = self._story_summary_prompts(video_detail, scenes)

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
