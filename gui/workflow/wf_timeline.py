"""TimelineMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import pygame
from PIL import Image, ImageTk
from project_manager import refresh_scene_media, save_project_config
import project_manager
import cv2
from utility.file_util import get_file_path, show_auto_close_popup
from gui.workflow.wf_common import STANDARD_FPS


class TimelineMixin:
    def _marker_number(self, key: str, count: int):
        pc = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
        try:
            n = int(pc.get(key))
        except (TypeError, ValueError):
            return None
        if count <= 0 or n < 1 or n > count:
            return None
        return n

    def _refresh_marker_label(self) -> None:
        label = getattr(self, "marker_label", None)
        if label is None:
            return
        count = len(self.workflow.scenes) if getattr(self, "workflow", None) else 0
        if count <= 0:
            label.config(text="")
            return
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if start and end:
            label.config(text=f"{start}–{end}")
        elif start:
            label.config(text=f"{start}–")
        elif end:
            label.config(text=f"–{end}")
        else:
            label.config(text=f"1–{count}")

    def _set_scene_marker(self, which: str) -> None:
        """开始记下当前场为起点，结束记下当前场为终点。颠倒时把另一头拉到同一场。"""
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict) or not getattr(self, "workflow", None):
            return
        count = len(self.workflow.scenes)
        if count <= 0:
            return
        current = self.current_scene_index + 1
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if which == "start":
            start = current
            if end is not None and end < start:
                end = start
        else:
            end = current
            if start is not None and end < start:
                start = end
        if start is None:
            pc.pop("marker_start", None)
        else:
            pc["marker_start"] = start
        if end is None:
            pc.pop("marker_end", None)
        else:
            pc["marker_end"] = end
        save_project_config(parent=self.root)
        self._refresh_marker_label()

    def _clear_scene_markers(self) -> None:
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict):
            return
        pc.pop("marker_start", None)
        pc.pop("marker_end", None)
        save_project_config(parent=self.root)
        self._refresh_marker_label()

    def _marker_scene_bounds(self) -> tuple[int, int]:
        """返回要生成的场景下标，含首尾。没标完整时用第一场到最后一场。"""
        count = len(self.workflow.scenes)
        if count <= 0:
            return 0, 0
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if start and end:
            return start - 1, end - 1
        return 0, count - 1

    def format_time_with_centisec(self, sec):
        """Format time as MM:SS.CC (minutes:sec.centisec)"""
        if sec is None or sec < 0:
            return "00:00.00"
        
        minutes = int(sec // 60)
        remaining_sec = sec % 60
        secs = int(remaining_sec)
        centisec = int((remaining_sec - secs) * 100)
        
        return f"{minutes:02d}:{secs:02d}.{centisec:02d}"

    def update_video_progress_display(self):
        """更新视频进度显示（未播放时显示总时长）"""
        if not hasattr(self, 'workflow'):
            return

        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if current_scene:
                clip_video = get_file_path(current_scene, "clip")
                if clip_video:
                    total_duration = self.workflow.ffmpeg_processor.get_duration(clip_video)
                else:
                    total_duration = 0.0
                
                current = float(getattr(self, "_preview_playhead", 0) or 0)
                self.video_progress_label.config(
                    text=f"现在 {self.format_time_with_centisec(current)} / 共 {self.format_time_with_centisec(total_duration)}"
                )
            else:
                self.video_progress_label.config(text="现在 00:00.00 / 共 00:00.00")
                
        except Exception as e:
            self.video_progress_label.config(text="现在 00:00.00 / 共 00:00.00")
            print(f"⚠️ 更新视频进度显示失败: {e}")

    def _refresh_speech_span_bar(self) -> None:
        duration = 0.0
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if scene:
            duration = self._clip_duration(scene)
        if getattr(self, "_span_bar_scene", None) != self.current_scene_index:
            self._preview_playhead = 0.0
            self._span_bar_scene = self.current_scene_index
        self._speech_span_duration = duration
        self._speech_sections = []
        if scene and duration > 0:
            text = (scene.get("speaking") or "").strip()
            stored = self._timing_sections(scene)
            if stored is not None:
                self._speech_sections = self._sections_from_stored(stored, text)
            elif text:
                self._detect_and_store_speaking_timing(scene, text, duration)
        if duration > 0 and self._clamp_speech_spans():
            self._save_speech_spans()
        self._draw_speech_span_bar()

    def _clamp_speech_spans(self) -> bool:
        """把每段收在整段声音里，重叠的边拉开，中间空出来的间隔留着。"""
        duration = float(self._speech_span_duration or 0.0)
        if duration <= 0:
            return False
        changed = False
        sections = getattr(self, "_speech_sections", None) or []
        for index, section in enumerate(sections):
            start = float(section.get("start") or 0.0)
            end = float(section.get("end") or 0.0)
            if end < start:
                start, end = end, start
            start = max(0.0, min(duration, start))
            end = max(0.0, min(duration, end))
            if index > 0:
                prev_end = float(sections[index - 1].get("end") or 0.0)
                if start < prev_end:
                    start = prev_end
            if end < start + 0.05:
                end = min(duration, start + 0.05)
            if index + 1 < len(sections):
                next_start = float(sections[index + 1].get("start") or duration)
                if end > next_start:
                    end = next_start
            start = round(start, 2)
            end = round(end, 2)
            if section.get("start") != start or section.get("end") != end:
                section["start"] = start
                section["end"] = end
                changed = True
        return changed

    def _bar_span(self, canvas) -> tuple[int, int]:
        """上面那条右边留给方块把手。下面那条控件本身短这么宽，时间铺满自己的宽度。"""
        width = max(canvas.winfo_width(), 2) if canvas is not None else 2
        progress = getattr(self, "progress_canvas", None)
        if canvas is progress:
            return width, max(width - self._PROGRESS_KNOB, 1)
        return width, width

    def _x_from_second(self, canvas, second: float) -> int:
        duration = float(self._speech_span_duration or 0.0)
        _width, usable = self._bar_span(canvas)
        if duration <= 0:
            return 0
        second = max(0.0, min(duration, float(second)))
        return int(second / duration * usable)

    def _second_from_x(self, x: int, canvas=None) -> float:
        duration = float(self._speech_span_duration or 0.0)
        canvas = canvas or getattr(self, "speech_span_canvas", None)
        _width, usable = self._bar_span(canvas)
        if duration <= 0:
            return 0.0
        x = max(0, min(usable, int(x)))
        return max(0.0, min(duration, x / usable * duration))

    def _draw_progress_bar(self) -> None:
        canvas = getattr(self, "progress_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 22)
        duration = float(self._speech_span_duration or 0.0)
        play = float(getattr(self, "_preview_playhead", 0) or 0)
        if duration > 0:
            play = max(0.0, min(duration, play))
        if hasattr(self, "video_progress_label"):
            self.video_progress_label.config(
                text=f"现在 {self.format_time_with_centisec(play)} / 共 {self.format_time_with_centisec(duration)}"
            )
        canvas.create_rectangle(0, 0, width, height, fill="#d0d0d0", outline="")
        if duration <= 0:
            canvas.create_text(8, height / 2, anchor="w", text="播放", fill="#666666")
            return
        px = self._x_from_second(canvas, play)
        canvas.create_rectangle(0, 0, max(px, 0), height, fill="#1565c0", outline="")
        side = self._PROGRESS_KNOB
        top = max(1, (height - side) // 2)
        grabbed = bool(getattr(self, "_progress_grabbed", False))
        canvas.create_rectangle(
            px, top, min(width, px + side), top + side,
            fill="#1565c0" if grabbed else "#ffffff",
            outline="#111111",
            width=2,
        )
        tag = self.format_time_with_centisec(play)
        chip = 62
        if px < width / 2:
            chip_x0, text_x, anchor = min(width - chip - side, px + side + 4), min(width - 8, px + side + 8), "w"
        else:
            chip_x0, text_x, anchor = max(0, px - 4 - chip), max(8, px - 8), "e"
        canvas.create_rectangle(chip_x0, 2, chip_x0 + chip, height - 2, fill="#ffffff", outline="#111111")
        canvas.create_text(text_x, height / 2, anchor=anchor, text=tag, fill="#111111")

    def _cancel_progress_grab(self) -> None:
        after_id = getattr(self, "_progress_grab_after", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._progress_grab_after = None

    def _progress_press(self, event) -> None:
        if (self._speech_span_duration or 0) <= 0:
            return
        self._progress_grabbed = False
        self._cancel_progress_grab()
        self._progress_grab_after = self.root.after(450, self._progress_become_grabbed)

    def _progress_become_grabbed(self) -> None:
        self._progress_grab_after = None
        self._progress_grabbed = True
        try:
            self.progress_canvas.config(cursor="sb_h_double_arrow")
        except tk.TclError:
            pass
        self._draw_progress_bar()

    def _progress_drag(self, event) -> None:
        if not getattr(self, "_progress_grabbed", False):
            return
        self._seek_preview_to(self._second_from_x(event.x, self.progress_canvas), park_audio=False)

    def _progress_release(self, _event) -> None:
        self._cancel_progress_grab()
        grabbed = bool(getattr(self, "_progress_grabbed", False))
        self._progress_grabbed = False
        try:
            self.progress_canvas.config(cursor="hand2")
        except tk.TclError:
            pass
        if grabbed:
            self._park_preview_audio(float(getattr(self, "_preview_playhead", 0) or 0))
        self._draw_progress_bar()

    def _progress_double(self, event) -> None:
        if (self._speech_span_duration or 0) <= 0:
            return
        self._cancel_progress_grab()
        self._progress_grabbed = False
        try:
            self.progress_canvas.config(cursor="hand2")
        except tk.TclError:
            pass
        self._draw_progress_bar()
        self._open_progress_action_dialog(event.x)

    def _progress_action_plan(self) -> dict | None:
        duration = float(self._speech_span_duration or 0.0)
        if duration <= 0.2:
            return None
        play = max(0.0, min(duration, float(getattr(self, "_preview_playhead", 0) or 0)))
        sections = [dict(section) for section in (getattr(self, "_speech_sections", None) or [])]
        hit = None
        for index, section in enumerate(sections):
            try:
                start = float(section.get("start"))
                end = float(section.get("end"))
            except (TypeError, ValueError):
                continue
            if index == len(sections) - 1:
                inside = start - 0.001 <= play <= end + 0.001
            else:
                inside = start - 0.001 <= play < end
            if inside:
                hit = index
                break
        head = None
        tail = None
        if not sections:
            if 0.12 <= play <= duration - 0.12:
                head = {"cut": round(play, 2), "label": "把播放位置前面的空白移到前一场（含讲稿）", "speech": False}
                tail = {"cut": round(play, 2), "label": "把播放位置后面的空白移到后一场（含讲稿）", "speech": False}
        else:
            first = sections[0]
            last = sections[-1]
            first_start = float(first.get("start") or 0.0)
            first_end = float(first.get("end") or 0.0)
            last_start = float(last.get("start") or 0.0)
            last_end = float(last.get("end") or 0.0)
            if play < first_start - 0.001:
                head = {
                    "cut": round(first_start, 2),
                    "label": "把前面的空白移到前一场（含讲稿）",
                    "speech": False,
                }
            elif hit == 0:
                blank = "连同前面的空白" if first_start >= 0.12 else ""
                head = {
                    "cut": round(first_end, 2),
                    "label": f"把第一段{blank}移到前一场（含讲稿）",
                    "speech": True,
                }
            if play > last_end + 0.001:
                tail = {
                    "cut": round(last_end, 2),
                    "label": "把后面的空白移到后一场（含讲稿）",
                    "speech": False,
                }
            elif hit == len(sections) - 1:
                blank = "连同后面的空白" if duration - last_end >= 0.12 else ""
                tail = {
                    "cut": round(last_start, 2),
                    "label": f"把最后一段{blank}移到后一场（含讲稿）",
                    "speech": True,
                }
        split_ok = False
        if hit is not None:
            section = sections[hit]
            start = float(section.get("start") or 0.0)
            end = float(section.get("end") or 0.0)
            if play - start >= 0.12 and end - play >= 0.12 and end > start:
                ratio = (play - start) / (end - start)
                left, right = self._split_body_by_ratio(section.get("text") or "", ratio)
                split_ok = bool(left and right) or not (section.get("text") or "").strip()
                if (section.get("text") or "").strip() and not (left and right):
                    split_ok = False
        if head and (head["cut"] < 0.12 or duration - head["cut"] < 0.12):
            head = None
        if tail and (tail["cut"] < 0.12 or duration - tail["cut"] < 0.12):
            tail = None
        lead_zone = bool(sections) and play < float(sections[0].get("start") or 0.0) - 0.001
        tail_zone = bool(sections) and play > float(sections[-1].get("end") or 0.0) + 0.001
        on_first = (not sections) or lead_zone or hit == 0
        on_last = (not sections) or tail_zone or (hit is not None and hit == len(sections) - 1)
        cut_ok = 0.12 <= play <= duration - 0.12
        if hit is None and sections:
            place = "空白"
        elif hit is None:
            place = "这一场"
        else:
            place = f"第 {int(sections[hit].get('speaker') or 1)} 个人这一段"
        return {
            "play": play,
            "duration": duration,
            "sections": sections,
            "hit": hit,
            "place": place,
            "split": split_ok,
            "head": head,
            "tail": tail,
            "media_prev": cut_ok and on_first,
            "media_next": cut_ok and on_last,
        }

    def _open_progress_action_dialog(self, click_x: int | None = None) -> None:
        if getattr(self, "_progress_action_open", False):
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        plan = self._progress_action_plan()
        if not scene or not plan:
            return
        prev_scene, next_scene = self._adjacent_story_scenes(scene)
        self._progress_action_open = True
        dlg = tk.Toplevel(self.root)
        dlg.withdraw()
        dlg.title("播放位置")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        def close() -> None:
            self._progress_action_open = False
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", close)
        when = self.format_time_with_centisec(plan["play"])
        ttk.Label(dlg, text=f"播放到 {when}，在{plan['place']}。").pack(anchor="w", padx=14, pady=(12, 8))

        def run_split() -> None:
            close()
            self._split_speaking_at_playhead()

        def run_shift(where: str) -> None:
            close()
            self._shift_clip_to_neighbor(where)

        def run_media(where: str) -> None:
            close()
            self._shift_clip_to_neighbor(where, media_only=True)

        split_btn = ttk.Button(dlg, text="把这一段拆成两段", command=run_split)
        split_btn.pack(fill=tk.X, padx=14, pady=3)
        if not plan["split"]:
            split_btn.state(["disabled"])

        def run_split_scene() -> None:
            close()
            if messagebox.askyesno("分成两场", "从这个播放位置把这一场分成前后两场？", parent=self.root):
                self.split_scene()

        scene_split_btn = ttk.Button(dlg, text="从这里分成前后两场", command=run_split_scene)
        scene_split_btn.pack(fill=tk.X, padx=14, pady=3)
        if plan["play"] <= 0.08 or plan["play"] >= plan["duration"] - 0.08:
            scene_split_btn.state(["disabled"])

        head_btn = ttk.Button(
            dlg,
            text=(plan["head"] or {}).get("label") or "把前面的内容移到前一场（含讲稿）",
            command=lambda: run_shift("head"),
        )
        head_btn.pack(fill=tk.X, padx=14, pady=3)
        if not plan["head"] or prev_scene is None:
            head_btn.state(["disabled"])

        tail_btn = ttk.Button(
            dlg,
            text=(plan["tail"] or {}).get("label") or "把后面的内容移到后一场（含讲稿）",
            command=lambda: run_shift("tail"),
        )
        tail_btn.pack(fill=tk.X, padx=14, pady=3)
        if not plan["tail"] or next_scene is None:
            tail_btn.state(["disabled"])

        # 只搬画面和声音，讲稿不动，所以不受“同一集”限制：上一场、下一场是别的集也可以。
        any_prev = self.workflow.get_previous_scene(self.current_scene_index)
        any_next = self.workflow.get_next_scene(self.current_scene_index)

        media_prev_btn = ttk.Button(dlg, text="把播放点前面的画面和声音移到上一场（只移媒体）", command=lambda: run_media("head"))
        media_prev_btn.pack(fill=tk.X, padx=14, pady=3)
        if not plan.get("media_prev") or any_prev is None:
            media_prev_btn.state(["disabled"])

        media_next_btn = ttk.Button(dlg, text="把播放点后面的画面和声音移到下一场（只移媒体）", command=lambda: run_media("tail"))
        media_next_btn.pack(fill=tk.X, padx=14, pady=3)
        if not plan.get("media_next") or any_next is None:
            media_next_btn.state(["disabled"])

        def run_trim(drop_head: bool) -> None:
            close()
            self.trim_clip_at_playhead(drop_head, confirm=False)

        drop_front = ttk.Button(dlg, text="删掉这里前面的画面和声音", command=lambda: run_trim(True))
        drop_front.pack(fill=tk.X, padx=14, pady=3)
        if plan["play"] <= 0.08:
            drop_front.state(["disabled"])

        drop_back = ttk.Button(dlg, text="删掉这里后面的画面和声音", command=lambda: run_trim(False))
        drop_back.pack(fill=tk.X, padx=14, pady=3)
        if plan["play"] >= plan["duration"] - 0.08:
            drop_back.state(["disabled"])

        ttk.Button(dlg, text="取消", command=close).pack(fill=tk.X, padx=14, pady=(3, 12))
        self._place_progress_menu(dlg, click_x)
        dlg.grab_set()

    def _place_progress_menu(self, dlg: tk.Toplevel, click_x: int | None) -> None:
        """把菜单放在播放头上方，贴着进度条。"""
        canvas = getattr(self, "progress_canvas", None)
        dlg.update_idletasks()
        try:
            canvas.update_idletasks()
            ax = int(canvas.winfo_rootx())
            ay = int(canvas.winfo_rooty())
            aw = max(int(canvas.winfo_width()), 1)
            ah = max(int(canvas.winfo_height()), 1)
        except (tk.TclError, TypeError, ValueError, AttributeError):
            ax = int(self.root.winfo_rootx()) + 40
            ay = int(self.root.winfo_rooty()) + int(self.root.winfo_height()) - 160
            aw, ah = 400, 22
        w = max(int(dlg.winfo_reqwidth()), 220)
        h = max(int(dlg.winfo_reqheight()), 80)
        sw = int(dlg.winfo_screenwidth())
        sh = int(dlg.winfo_screenheight())
        try:
            local_x = aw // 2 if click_x is None else int(click_x)
        except (TypeError, ValueError):
            local_x = aw // 2
        local_x = max(0, min(aw, local_x))
        x = ax + local_x - w // 2
        y = ay - h - 8
        if y < 8:
            y = ay + ah + 8
        x = max(8, min(x, max(8, sw - w - 8)))
        y = max(8, min(y, max(8, sh - h - 8)))
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.deiconify()
        try:
            dlg.lift()
        except tk.TclError:
            pass

    def _split_speaking_at_playhead(self) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        plan = self._progress_action_plan()
        if not scene or not plan or not plan["split"] or plan["hit"] is None:
            return
        sections = plan["sections"]
        index = plan["hit"]
        section = sections[index]
        start = float(section.get("start") or 0.0)
        end = float(section.get("end") or 0.0)
        play = float(plan["play"])
        ratio = (play - start) / (end - start)
        left, right = self._split_body_by_ratio(section.get("text") or "", ratio)
        if (section.get("text") or "").strip() and not (left and right):
            messagebox.showinfo("拆开", "这一段字太少，分不开。", parent=self.root)
            return
        speaker = int(section.get("speaker") or 1)
        sections[index:index + 1] = [
            {"speaker": speaker, "start": round(start, 2), "end": round(play, 2), "text": left},
            {"speaker": speaker, "start": round(play, 2), "end": round(end, 2), "text": right},
        ]
        self._speech_sections = sections
        self._write_speaking_sections(scene, sections)
        self._put_speaking_text(scene.get("speaking") or "")
        self.workflow.save_scenes_to_json()
        self._draw_speech_span_bar()
        show_auto_close_popup(self.root, "拆开", f"这一段已分成第 {speaker} 个人的两段。")

    def _draw_speech_span_bar(self) -> None:
        canvas = getattr(self, "speech_span_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 24)
        duration = self._speech_span_duration or 0.0
        canvas.create_rectangle(0, 0, width, height, fill="#d9d9d9", outline="")
        sections = getattr(self, "_speech_sections", None) or []
        if duration <= 0:
            canvas.create_text(8, height / 2, anchor="w", text="没有可标注的声音", fill="#666666")
            if hasattr(self, "speech_span_label"):
                self.speech_span_label.config(text="")
            self._draw_progress_bar()
            return

        def x_at(second: float) -> int:
            return self._x_from_second(canvas, second)

        bits = []
        top, bottom = 1, height - 1
        for section in sections:
            start = section.get("start")
            end = section.get("end")
            speaker = int(section.get("speaker") or 1)
            title = str(speaker)
            if start is None or end is None or end <= start:
                continue
            color = self._SPEAKER_BAR_COLORS.get(speaker, "#2f6fed")
            x0, x1 = x_at(start), x_at(end)
            canvas.create_rectangle(x0, top, max(x1, x0 + 2), bottom, fill=color, outline="")
            canvas.create_rectangle(x0, top, min(x0 + 4, x1), bottom, fill="#1a1a1a", outline="")
            canvas.create_rectangle(max(x0, x1 - 4), top, x1, bottom, fill="#1a1a1a", outline="")
            if x1 - x0 > 18:
                canvas.create_text((x0 + x1) / 2, height / 2, text=title, fill="white")
            bits.append(f"{title} {float(start):.2f}–{float(end):.2f}")
        if hasattr(self, "speech_span_label"):
            self.speech_span_label.config(text="    ".join(bits))
        self._draw_progress_bar()

    def _speech_span_edge_at(self, x: int, _y: int):
        duration = self._speech_span_duration or 0.0
        if duration <= 0:
            return None

        def x_at(second: float) -> int:
            return self._x_from_second(self.speech_span_canvas, second)

        hits = []
        joins = []
        for index, section in enumerate(getattr(self, "_speech_sections", None) or []):
            for edge in ("start", "end"):
                value = section.get(edge)
                if value is None:
                    continue
                dist = abs(x - x_at(float(value)))
                if dist <= 8:
                    hits.append((dist, 0 if edge == "end" else 1, index, edge))
            if index + 1 < len(getattr(self, "_speech_sections", None) or []):
                nxt = self._speech_sections[index + 1]
                end = section.get("end")
                start = nxt.get("start")
                if end is None or start is None:
                    continue
                if abs(float(start) - float(end)) > 0.12:
                    continue
                if abs(x - x_at(float(end))) <= 10 or abs(x - x_at(float(start))) <= 10:
                    joins.append((abs(x - x_at(float(end))), index))
        if joins:
            joins.sort()
            return ("join", joins[0][1])
        if not hits:
            return None
        hits.sort()
        return ("edge", hits[0][2], hits[0][3])

    def _move_span_join(self, index: int, second: float) -> None:
        """两段贴在一起时，拖动共用的边，一边变长，另一边变短。"""
        sections = getattr(self, "_speech_sections", None) or []
        if index < 0 or index + 1 >= len(sections):
            return
        duration = float(self._speech_span_duration or 0.0)
        if duration <= 0:
            return
        left = sections[index]
        right = sections[index + 1]
        left_start = float(left.get("start") or 0.0)
        right_end = float(right.get("end") or 0.0)
        second = max(left_start + 0.05, min(float(second), right_end - 0.05))
        second = max(0.0, min(duration, second))
        second = round(second, 2)
        left["end"] = second
        right["start"] = second
        self._clamp_speech_spans()

    def _move_span_edge(self, index: int, edge: str, second: float) -> None:
        sections = getattr(self, "_speech_sections", None) or []
        if index < 0 or index >= len(sections):
            return
        duration = float(self._speech_span_duration or 0.0)
        section = sections[index]
        start = float(section.get("start") or 0.0)
        end = float(section.get("end") or 0.0)
        if duration <= 0:
            return
        prev_end = float(sections[index - 1]["end"]) if index > 0 else 0.0
        next_start = float(sections[index + 1]["start"]) if index + 1 < len(sections) else duration
        if edge == "start":
            second = max(prev_end, min(second, end - 0.05))
            section["start"] = round(second, 2)
        else:
            second = min(next_start, max(second, start + 0.05))
            section["end"] = round(max(0.0, min(duration, second)), 2)
        self._clamp_speech_spans()

    def _speech_span_press(self, event) -> None:
        hit = self._speech_span_edge_at(event.x, event.y)
        if hit:
            self._speech_span_drag = hit
            self._span_press_on_edge = True
            return
        self._speech_span_drag = None
        self._span_press_on_edge = False

    def _speech_span_drag_move(self, event) -> None:
        drag = getattr(self, "_speech_span_drag", None)
        if not drag:
            return
        second = self._second_from_x(event.x)
        kind = drag[0]
        if kind == "join":
            self._move_span_join(drag[1], second)
        else:
            self._move_span_edge(drag[1], drag[2], second)
        self._draw_speech_span_bar()

    def _speech_span_release(self, _event) -> None:
        if getattr(self, "_speech_span_drag", None):
            self._clamp_speech_spans()
            self._save_speech_spans()
        self._speech_span_drag = None

    def _halt_preview_loop(self) -> None:
        self.video_playing = False
        try:
            self.video_play_button.config(text="▶")
        except tk.TclError:
            pass
        if self.video_after_id:
            try:
                self.root.after_cancel(self.video_after_id)
            except Exception:
                pass
            self.video_after_id = None
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

    def _open_preview_cap(self) -> bool:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        video_path = get_file_path(scene, "clip") if scene else ""
        if not video_path or not os.path.isfile(video_path):
            return False
        if self.video_cap is None or not self.video_cap.isOpened():
            if self.video_cap:
                self.video_cap.release()
            self.video_cap = cv2.VideoCapture(video_path)
        return bool(self.video_cap and self.video_cap.isOpened())

    def _show_preview_frame_at(self, second: float) -> None:
        if not self._open_preview_cap():
            return
        target = max(0, int(float(second) * STANDARD_FPS))
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = self.video_cap.read()
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        if not ok or frame is None:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        canvas_width = self.video_canvas.winfo_width()
        canvas_height = self.video_canvas.winfo_height()
        if canvas_width > 1 and canvas_height > 1:
            pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
        else:
            pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
        self.current_video_frame = ImageTk.PhotoImage(pil_image)
        self.video_canvas.delete("all")
        x = (canvas_width or 640) // 2
        y = (canvas_height or 360) // 2
        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)

    def _seek_preview_to(self, second: float, park_audio: bool = True) -> None:
        self._halt_preview_loop()
        duration = float(self._speech_span_duration or 0.0)
        second = max(0.0, min(duration, float(second))) if duration > 0 else 0.0
        self._preview_playhead = second
        self.video_pause_time = second
        self.video_start_time = None
        self._show_preview_frame_at(second)
        self._draw_progress_bar()
        if park_audio:
            self._park_preview_audio(second)

    def _park_preview_audio(self, second: float, paused: bool = True) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        clip = get_file_path(scene, "clip_audio") if scene else ""
        if not clip or not os.path.isfile(clip):
            return
        try:
            pygame.mixer.music.load(clip)
            pygame.mixer.music.play(start=max(0.0, float(second)))
            if paused:
                pygame.mixer.music.pause()
        except Exception as exc:
            print(f"⚠️ 声音停到 {second:.2f} 秒失败: {exc}")

    def _span_section_at(self, second: float) -> int | None:
        for index, section in enumerate(getattr(self, "_speech_sections", None) or []):
            start = section.get("start")
            end = section.get("end")
            if start is None or end is None:
                continue
            if float(start) <= second <= float(end):
                return index
        return None

    def _release_preview_lock(self) -> None:
        self._halt_preview_loop()
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None
        self.stop_audio_playback()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        self.video_start_time = None
        self.video_pause_time = None

    def _retarget_spans_for_trim(self, cut_at: float, drop_head: bool) -> None:
        sections = getattr(self, "_speech_sections", None) or []
        kept = []
        for section in sections:
            start = section.get("start")
            end = section.get("end")
            if start is None or end is None:
                continue
            start = float(start)
            end = float(end)
            if drop_head:
                start -= cut_at
                end -= cut_at
                if end <= 0.05:
                    continue
                start = max(0.0, start)
            else:
                if start >= cut_at - 0.01:
                    continue
                end = min(end, cut_at)
            if end - start < 0.05:
                continue
            section["start"] = round(start, 2)
            section["end"] = round(end, 2)
            kept.append(section)
        self._speech_sections = kept
        self._speech_span_duration = max(0.0, (self._speech_span_duration or 0.0) - cut_at) if drop_head else cut_at
        self._clamp_speech_spans()
        self._save_speech_spans()

    def trim_clip_at_playhead(self, drop_head: bool, *, confirm: bool = True) -> None:
        """裁前丢掉播放线之前，裁后丢掉播放线之后。画面和声音一起切。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        video = get_file_path(scene, "clip")
        if not video or not os.path.isfile(video):
            messagebox.showinfo("裁切", "这一场没有画面。", parent=self.root)
            return
        duration = self._clip_duration(scene)
        if duration <= 0.2:
            messagebox.showinfo("裁切", "这一场太短，切不开。", parent=self.root)
            return
        cut_at = float(getattr(self, "_preview_playhead", 0) or 0)
        cut_at = max(0.0, min(duration, cut_at))
        title = "裁前" if drop_head else "裁后"
        if drop_head and cut_at <= 0.08:
            messagebox.showinfo(title, "播放线还在开头，前面没有可去掉的部分。", parent=self.root)
            return
        if (not drop_head) and cut_at >= duration - 0.08:
            messagebox.showinfo(title, "播放线已经在结尾，后面没有可去掉的部分。", parent=self.root)
            return
        if confirm:
            if drop_head:
                question = f"去掉 {cut_at:.2f} 秒之前的画面和声音？"
            else:
                question = f"去掉 {cut_at:.2f} 秒之后的画面和声音？"
            if not messagebox.askyesno(title, question, parent=self.root):
                return
        self._release_preview_lock()
        try:
            if drop_head:
                new_video = self.workflow.ffmpeg_processor.trim_video(video, start_time=cut_at)
            else:
                new_video = self.workflow.ffmpeg_processor.trim_video(video, start_time=0, end_time=cut_at)
        except Exception as exc:
            messagebox.showerror(title, f"画面没有切开：{exc}", parent=self.root)
            return
        if not new_video or not os.path.isfile(new_video):
            messagebox.showerror(title, "画面没有切开。", parent=self.root)
            return
        audio = get_file_path(scene, "clip_audio")
        new_audio = None
        if audio and os.path.isfile(audio):
            head, tail = self.workflow.ffmpeg_audio_processor.split_audio(audio, cut_at)
            new_audio = tail if drop_head else head
            if not new_audio or not os.path.isfile(new_audio):
                messagebox.showerror(title, "声音没有切开。", parent=self.root)
                return
        self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, "clip", ".mp4", new_video, True)
        if new_audio:
            refresh_scene_media(scene, "clip_audio", ".wav", new_audio, True)
        self._retarget_spans_for_trim(cut_at, drop_head)
        self._preview_playhead = 0.0
        self.video_pause_time = 0.0
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, title, "已去掉前面。" if drop_head else "已去掉后面。")

    def _save_speech_spans(self) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        timing = []
        for section in getattr(self, "_speech_sections", None) or []:
            try:
                timing.append({
                    "speaker": int(section.get("speaker") or 1),
                    "start": round(float(section.get("start")), 2),
                    "end": round(float(section.get("end")), 2),
                    "text": (section.get("text") or "").strip(),
                })
            except (TypeError, ValueError):
                continue
        record = self._timing_record(scene)
        self._store_timing(scene, timing, record.get("text") if record is not None else None)
        for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
            scene.pop(key, None)
        self.workflow.save_scenes_to_json()

    def _speech_span_double(self, event) -> None:
        if getattr(self, "_span_press_on_edge", False):
            return
        self._speech_span_drag = None
        key = self._span_section_at(self._second_from_x(event.x))
        if key is None:
            return
        self._ask_regenerate_span(key)
