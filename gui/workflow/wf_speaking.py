"""SpeakingMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import subprocess
import threading
import project_manager
from utility.file_util import get_file_path, show_auto_close_popup
from utility.voicebox_speech_service import split_speaking_turns
import copy
from gui.choice_dialog import askchoice


class SpeakingMixin:
    @staticmethod
    def _timing_record(scene) -> dict | None:
        """场景上的时间记录（不管 speaking 有没有被改过）。没有记录返回 None。"""
        stored = scene.get("speaking_timing") if isinstance(scene, dict) else None
        if isinstance(stored, dict) and isinstance(stored.get("sections"), list):
            return stored
        return None

    @classmethod
    def _timing_sections(cls, scene) -> list | None:
        """当前 speaking 仍然有效的时间段。没有记录、或 speaking 已经被改过，返回 None。"""
        record = cls._timing_record(scene)
        if record is None:
            return None
        if (record.get("text") or "").strip() != (scene.get("speaking") or "").strip():
            return None
        return record["sections"]

    @staticmethod
    def _store_timing(scene, sections: list, text: str | None = None) -> None:
        """写入时间记录。text 不给就用现在的 speaking。"""
        stamp = scene.get("speaking") if text is None else text
        scene["speaking_timing"] = {"text": (stamp or "").strip(), "sections": sections}

    def _speech_media_path(self, scene: dict | None) -> str:
        if not scene:
            return ""
        audio = get_file_path(scene, "clip_audio")
        if audio and os.path.isfile(audio):
            return audio
        video = get_file_path(scene, "clip")
        if video and os.path.isfile(video):
            return video
        return ""

    def _clip_duration(self, scene: dict | None) -> float:
        path = self._speech_media_path(scene)
        if not path or not getattr(self, "workflow", None):
            return 0.0
        try:
            return float(self.workflow.ffmpeg_processor.get_duration(path) or 0.0)
        except Exception:
            return 0.0

    def _speaking_turn_parts(self, text: str) -> list[tuple[int, str]]:
        parts = []
        for speaker, body in split_speaking_turns(text or ""):
            try:
                speaker = int(speaker)
            except (TypeError, ValueError):
                continue
            body = (body or "").strip()
            if speaker < 1 or speaker > 3 or not body:
                continue
            parts.append((speaker, body))
        return parts

    def _collapse_same_speaker_parts(self, parts) -> list[tuple[int, str]]:
        """挨在一起、又是同一个人的两段，合成一段。人没有换，不该再切开。"""
        merged = []
        for speaker, body in parts or []:
            body = (body or "").strip()
            if not body:
                continue
            if merged and merged[-1][0] == speaker:
                merged[-1] = (speaker, (merged[-1][1] + body).strip())
            else:
                merged.append((speaker, body))
        return merged

    def _apply_collapsed_speaking(self, scene: dict, original: str) -> str:
        parts = self._speaking_turn_parts(original)
        collapsed = self._collapse_same_speaker_parts(parts)
        if len(collapsed) >= len(parts):
            return (original or "").strip()
        text = "".join(f"<{speaker}> {body}" for speaker, body in collapsed)
        scene["speaking"] = text
        current = None
        if getattr(self, "workflow", None):
            current = self.workflow.get_scene_by_index(self.current_scene_index)
        if current is scene and threading.current_thread() is threading.main_thread():
            self._put_speaking_text(text)
        return text

    def _speaking_part_weight(self, body: str) -> int:
        """按字数分时间。每一句结尾多算一个字，当作句末那一点停顿。"""
        import re

        weight = 0
        cleaned = re.sub(r"[<＜]\d+\.\d+[>＞]", "", body or "")
        sentences = re.split(r"(?<=[。！？])", cleaned)
        for sentence in sentences:
            chars = len("".join(sentence.split()))
            if chars <= 0:
                continue
            weight += chars + 1
        if weight <= 0:
            weight = max(1, len("".join(cleaned.split())) + 1)
        return weight

    def _sections_from_stored(self, stored, text: str) -> list[dict]:
        parts = self._speaking_turn_parts(text)
        sections = []
        if not isinstance(stored, list):
            return sections
        for index, item in enumerate(stored):
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
                speaker = int(item.get("speaker") or 1)
            except (TypeError, ValueError):
                continue
            speaker = min(3, max(1, speaker))
            body = (item.get("text") or "").strip()
            if not body and index < len(parts):
                body = parts[index][1]
            sections.append({
                "speaker": speaker,
                "start": start,
                "end": end,
                "text": body,
            })
        return sections

    def _countable_char_indexes(self, body: str) -> list[int]:
        import re

        spans = [(m.start(), m.end()) for m in re.finditer(r"[<＜]\d+\.\d+[>＞]", body or "")]

        def in_silence(index: int) -> bool:
            return any(start <= index < end for start, end in spans)

        return [
            index for index, char in enumerate(body or "")
            if not char.isspace() and not in_silence(index)
        ]

    def _split_body_by_ratio(self, body: str, ratio: float) -> tuple[str, str]:
        indexes = self._countable_char_indexes(body or "")
        if len(indexes) < 2:
            return (body or "").strip(), ""
        cut_n = int(round(len(indexes) * ratio))
        cut_n = max(1, min(len(indexes) - 1, cut_n))
        cut_at = indexes[cut_n - 1] + 1
        return (body or "")[:cut_at].strip(), (body or "")[cut_at:].strip()

    def _speaking_from_sections(self, sections) -> str:
        parts = []
        for section in sections or []:
            text = (section.get("text") or "").strip()
            if not text:
                continue
            try:
                speaker = int(section.get("speaker") or 1)
            except (TypeError, ValueError):
                speaker = 1
            speaker = min(3, max(1, speaker))
            parts.append(f"<{speaker}> {text}")
        return "".join(parts)

    def _write_speaking_sections(self, scene: dict, sections) -> None:
        cleaned = []
        for section in sections or []:
            try:
                cleaned.append({
                    "speaker": min(3, max(1, int(section.get("speaker") or 1))),
                    "start": round(float(section.get("start")), 2),
                    "end": round(float(section.get("end")), 2),
                    "text": (section.get("text") or "").strip(),
                })
            except (TypeError, ValueError):
                continue
        speaking = self._speaking_from_sections(cleaned)
        scene["speaking"] = speaking
        self._store_timing(scene, cleaned, speaking)
        for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
            scene.pop(key, None)

    def _speaking_char_spans(self, text: str) -> list[tuple]:
        """原文里每一段的人物、正文起点和终点。"""
        import re

        raw = text or ""
        marks = list(re.finditer(r"[<＜](\d+)[>＞]", raw))
        spans = []
        if not marks:
            if raw.strip():
                spans.append((1, 0, len(raw)))
            return spans
        if marks[0].start() > 0 and raw[:marks[0].start()].strip():
            spans.append((1, 0, marks[0].start()))
        for index, mark in enumerate(marks):
            try:
                speaker = int(mark.group(1))
            except (TypeError, ValueError):
                continue
            if speaker < 1 or speaker > 3:
                continue
            body_end = marks[index + 1].start() if index + 1 < len(marks) else len(raw)
            if not raw[mark.end():body_end].strip():
                continue
            spans.append((speaker, mark.end(), body_end))
        return spans

    def _on_speaking_double_click_switch(self, event):
        """双击讲话稿的某一处，从这里换成第 1、2 或 3 人，并把当前这一段按字数切开。"""
        widget = getattr(self, "scene_speaking", None)
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if widget is None or not scene:
            return "break"
        try:
            here = widget.index(f"@{event.x},{event.y}")
            text = widget.get("1.0", "end-1c")
            offset = len(widget.get("1.0", here))
        except tk.TclError:
            return "break"
        import re
        for mark in re.finditer(r"[<＜]\d+[>＞]", text):
            if mark.start() <= offset < mark.end():
                messagebox.showinfo("换人", "点在人物记号上了，请点在文字中间。", parent=self.root)
                return "break"
        spans = self._speaking_char_spans(text)
        hit = None
        for index, (speaker, start, end) in enumerate(spans):
            if start <= offset <= end:
                hit = index
                break
        if hit is None:
            messagebox.showinfo("换人", "请点在一段文字里面。", parent=self.root)
            return "break"
        _speaker, body_start, body_end = spans[hit]
        left = text[body_start:offset]
        right = text[offset:body_end]
        if not left.strip() or not right.strip():
            messagebox.showinfo("换人", "请点在这段文字的中间。", parent=self.root)
            return "break"
        actor_text = (getattr(self, "_actor_text", "") or scene.get("actor") or "")
        present = 0
        for row in project_manager.actor_entries(actor_text):
            if not project_manager.actor_is_absent(row.get("body") or ""):
                present += 1
        present = min(3, present)
        if present < 1:
            messagebox.showinfo("换人", "这一场还没有人物。", parent=self.root)
            return "break"
        picked = askchoice(
            "从这里换成哪一个人？",
            [(str(number), f"第{number}人") for number in range(1, present + 1)],
            parent=self.root,
        )
        if not picked:
            return "break"
        try:
            speaker = min(3, max(1, int(picked[1])))
        except (TypeError, ValueError):
            return "break"
        sections = []
        stored = self._timing_sections(scene)
        if stored is not None:
            sections = self._sections_from_stored(stored, text)
        if len(sections) != len(spans):
            duration = float(self._clip_duration(scene) or 0.0)
            path = self._speech_media_path(scene)
            bounds = self._audio_activity_bounds(path, duration) if path and duration > 0 else None
            if bounds and bounds[1] > bounds[0]:
                sections = self._allocate_speaking_timing(text, bounds[0], bounds[1])
            elif duration > 0:
                sections = self._allocate_speaking_timing(text, 0.0, duration)
        if hit >= len(sections):
            messagebox.showinfo("换人", "这一段还没有时间，先重置再切。", parent=self.root)
            return "break"
        current = sections[hit]
        try:
            start = float(current.get("start"))
            end = float(current.get("end"))
        except (TypeError, ValueError):
            return "break"
        if end - start < 0.2:
            messagebox.showinfo("换人", "这一段太短，切不开。", parent=self.root)
            return "break"
        left_w = self._speaking_part_weight(left)
        right_w = self._speaking_part_weight(right)
        ratio = left_w / max(1, left_w + right_w)
        cut = start + (end - start) * ratio
        cut = max(start + 0.05, min(end - 0.05, cut))
        cut = round(cut, 2)
        first = dict(current)
        first["text"] = left.strip()
        first["end"] = cut
        second = {
            "speaker": speaker,
            "start": cut,
            "end": round(end, 2),
            "text": right.strip(),
        }
        sections[hit:hit + 1] = [first, second]
        self._speech_sections = sections
        self._write_speaking_sections(scene, sections)
        self._put_speaking_text(project_manager.speaking_box_text(scene))
        self.workflow.save_scenes_to_json()
        self._draw_speech_span_bar()
        return "break"

    def _put_speaking_text(self, text: str) -> None:
        widget = getattr(self, "scene_speaking", None)
        if widget is None:
            return
        self._scene_widgets_loading = True
        try:
            widget.delete("1.0", tk.END)
            widget.insert("1.0", text or "")
        except tk.TclError:
            pass
        finally:
            self._scene_widgets_loading = False

    def _reset_speaking_timing(self) -> None:
        """按这一场讲稿的字数，重新标出每段的起止。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        widget = getattr(self, "scene_speaking", None)
        if widget is not None:
            try:
                project_manager.store_speaking_box_text(scene, widget.get("1.0", tk.END))
            except tk.TclError:
                pass
        text = (scene.get("speaking") or "").strip()
        duration = self._clip_duration(scene)
        if duration <= 0 or not text:
            messagebox.showinfo("重置", "这一场没有声音或讲稿。", parent=self.root)
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass
        fresh = self._retimed_speaking_sections(scene)
        try:
            self.root.config(cursor="")
        except tk.TclError:
            pass
        if fresh is None:
            messagebox.showinfo("重置", "这一场的声音没有标出来。", parent=self.root)
            return
        self._speech_sections = fresh
        self._speech_span_duration = duration
        self.workflow.save_scenes_to_json()
        self._draw_speech_span_bar()
        show_auto_close_popup(self.root, "重置", "已按字数重新标好。")

    def _retime_scene_after_structure(self, scene) -> None:
        """分场或合场以后声音长短变了，按重置的办法重新标讲话时间。标不出来就清掉旧记录，下次再标。"""
        if not isinstance(scene, dict):
            return
        fresh = self._retimed_speaking_sections(scene)
        if fresh is None:
            scene.pop("speaking_timing", None)

    def _retimed_speaking_sections(self, scene) -> list | None:
        """按这场讲稿的字数，对照现在的声音长短，重新写下每段时间。相邻又是同一个人的，合成一段。"""
        if not isinstance(scene, dict):
            return None
        text = self._apply_collapsed_speaking(scene, (scene.get("speaking") or "").strip())
        duration = float(self._clip_duration(scene) or 0.0)
        path = self._speech_media_path(scene)
        if not text or duration <= 0 or not path:
            return None
        bounds = self._audio_activity_bounds(path, duration)
        if bounds is None:
            return None
        if bounds[1] <= bounds[0]:
            sections = []
        else:
            sections = self._allocate_speaking_timing(text, bounds[0], bounds[1])
        timing = []
        for section in sections:
            try:
                timing.append({
                    "speaker": min(3, max(1, int(section.get("speaker") or 1))),
                    "start": round(float(section.get("start")), 2),
                    "end": round(float(section.get("end")), 2),
                    "text": (section.get("text") or "").strip(),
                })
            except (TypeError, ValueError):
                continue
        self._store_timing(scene, timing, text)
        for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
            scene.pop(key, None)
        return timing

    def _attach_sections_to_neighbor(self, neighbor, moved, where: str, old_len: float, moved_len: float) -> None:
        text = (neighbor.get("speaking") or "").strip()
        stored = self._timing_sections(neighbor)
        has_record = stored is not None
        if not has_record:
            piece = self._speaking_from_sections(moved)
            if piece:
                if where == "head":
                    neighbor["speaking"] = (text + piece).strip()
                else:
                    neighbor["speaking"] = (piece + text).strip()
            neighbor.pop("speaking_timing", None)
            return
        existing = self._sections_from_stored(stored, text)
        if where == "head":
            placed = []
            for section in moved:
                row = dict(section)
                row["start"] = round(old_len + float(section.get("start") or 0.0), 2)
                row["end"] = round(old_len + float(section.get("end") or 0.0), 2)
                placed.append(row)
            self._write_speaking_sections(neighbor, existing + placed)
            return
        shifted = []
        for section in existing:
            row = dict(section)
            row["start"] = round(float(section.get("start") or 0.0) + moved_len, 2)
            row["end"] = round(float(section.get("end") or 0.0) + moved_len, 2)
            shifted.append(row)
        self._write_speaking_sections(neighbor, list(moved) + shifted)

    def _audio_activity_bounds(self, path: str, duration: float) -> tuple[float, float] | None:
        """整段声音里，人声从哪一秒开始、到哪一秒结束。"""
        import re
        from utility.ffmpeg_processor import ffmpeg_path

        try:
            result = subprocess.run(
                [ffmpeg_path, "-i", path, "-af", "silencedetect=noise=-30dB:d=0.28", "-f", "null", "-"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            return None
        silences = []
        pending = None
        for line in (result.stderr or "").splitlines():
            start_hit = re.search(r"silence_start:\s*([0-9.]+)", line)
            end_hit = re.search(r"silence_end:\s*([0-9.]+)", line)
            if start_hit:
                pending = float(start_hit.group(1))
            elif end_hit and pending is not None:
                silences.append((pending, float(end_hit.group(1))))
                pending = None
        if pending is not None:
            silences.append((pending, duration))
        speech = []
        cursor = 0.0
        for start, end in silences:
            if start - cursor > 0.12:
                speech.append((cursor, min(start, duration)))
            cursor = max(cursor, end)
        if duration - cursor > 0.12:
            speech.append((cursor, duration))
        if not speech:
            return (0.0, 0.0)
        return round(speech[0][0], 2), round(speech[-1][1], 2)

    def _allocate_speaking_timing(self, text: str, audio_start: float, audio_end: float) -> list[dict]:
        parts = self._collapse_same_speaker_parts(self._speaking_turn_parts(text))
        if not parts or audio_end <= audio_start:
            return []
        weights = [self._speaking_part_weight(body) for _speaker, body in parts]
        total = sum(weights) or 1
        span = audio_end - audio_start
        cursor = audio_start
        sections = []
        last = len(parts) - 1
        for index, ((speaker, body), weight) in enumerate(zip(parts, weights)):
            if index == last:
                end = audio_end
            else:
                end = cursor + span * weight / total
            start_r = round(cursor, 2)
            end_r = round(end, 2)
            if end_r < start_r:
                end_r = start_r
            sections.append({
                "speaker": speaker,
                "start": start_r,
                "end": end_r,
                "text": body,
            })
            cursor = end_r
        return sections

    def _collapse_same_speaker_sections(self, sections) -> list[dict]:
        """时间上挨着、又是同一个人的两段，合成一段。"""
        merged = []
        for section in sections or []:
            try:
                speaker = min(3, max(1, int(section.get("speaker") or 1)))
                start = float(section.get("start"))
                end = float(section.get("end"))
            except (TypeError, ValueError):
                continue
            body = (section.get("text") or "").strip()
            if merged and merged[-1]["speaker"] == speaker:
                prev = merged[-1]
                prev["start"] = round(min(float(prev["start"]), start), 2)
                prev["end"] = round(max(float(prev["end"]), end), 2)
                prev["text"] = ((prev.get("text") or "").strip() + body).strip()
                continue
            merged.append({
                "speaker": speaker,
                "start": round(start, 2),
                "end": round(end, 2),
                "text": body,
            })
        return merged

    def _detect_and_store_speaking_timing(self, scene: dict, text: str, duration: float) -> None:
        path = self._speech_media_path(scene)
        if not path:
            return
        bounds = self._audio_activity_bounds(path, duration)
        if bounds is None:
            return
        if bounds[1] <= bounds[0]:
            self._store_timing(scene, [], text)
            self._speech_sections = []
            for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
                scene.pop(key, None)
            self.workflow.save_scenes_to_json()
            return
        text = self._apply_collapsed_speaking(scene, text)
        sections = self._allocate_speaking_timing(text, bounds[0], bounds[1])
        self._speech_sections = sections
        self._clamp_speech_spans()
        self._store_timing(scene, [], text)
        self._save_speech_spans()

    @staticmethod
    def _speaking_join_prev_then_moved(prev_tail: str, moved_head: str) -> str:
        """上一段末尾接上移入的首段；若上一段末尾无句读则插入中文句号。"""
        a = (prev_tail or "").rstrip()
        b = (moved_head or "").lstrip()
        if not b:
            return a
        if not a:
            return b
        if a[-1] in "。！？；…":
            return a + b
        return a + "。" + b

    @staticmethod
    def _speaking_join_moved_then_next(moved_tail: str, next_head: str) -> str:
        """移入的尾段拼在下一场景原文前；中间按需加中文句号。"""
        a = (moved_tail or "").rstrip()
        b = (next_head or "").lstrip()
        if not a:
            return b
        if not b:
            return a
        if a[-1] in "。！？；…":
            return a + b
        return a + "。" + b

    def _speaking_shortcuts_guard(self) -> bool:
        if getattr(self, "_scene_widgets_loading", False):
            return False
        if not self.workflow or not getattr(self.workflow, "scenes", None):
            return False
        if self.current_scene_index < 0 or self.current_scene_index >= len(self.workflow.scenes):
            return False
        return True

    @staticmethod
    def _speaking_ctrl_arrow_shift_held(event) -> bool:
        """若同时按住 Shift，则应为全局场景导航（Ctrl+Shift+←/→），讲话框勿拦截。"""
        if event is None:
            return False
        try:
            st = int(getattr(event, "state", 0) or 0)
        except (TypeError, ValueError):
            return False
        return bool(st & 0x0001)  # Shift

    @staticmethod
    def _speaking_ctrl_arrow_alt_held(event) -> bool:
        """按住 Alt 时是换集（Ctrl+Alt+←/→），讲话框里的 Ctrl+←/→ 不要把这段字挪走。"""
        if event is None:
            return False
        try:
            st = int(getattr(event, "state", 0) or 0)
        except (TypeError, ValueError):
            return False
        return bool(st & 0x20000) or bool(st & 0x0008)

    def _on_speaking_ctrl_s_split_clone(self, event=None):
        """Ctrl+S：以光标为界拆分讲话；当前镜保留光标前，下一镜为深拷贝场景，讲话为光标后。"""
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return "break"
        ins = self.scene_speaking.index("insert")
        before = self.scene_speaking.get("1.0", ins)
        after = self.scene_speaking.get(ins, "end-1c")
        dup = copy.deepcopy(scene)
        dup["id"] = self.workflow.max_id(dup) + 1
        scene["speaking"] = before
        dup["speaking"] = after
        self.workflow.scenes.insert(self.current_scene_index + 1, dup)
        self.workflow.touch_episode_media(self.workflow.scene_group(dup))
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_right_move_tail_to_next(self, event=None):
        """Ctrl+Right：光标至文末移入下一镜讲话开头，与原文用中文句号衔接。"""
        if self._speaking_ctrl_arrow_shift_held(event) or self._speaking_ctrl_arrow_alt_held(event):
            return  # 不 break，交给 bind_all：Ctrl+Shift 换场景，Ctrl+Alt 换集
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        if self.current_scene_index + 1 >= len(self.workflow.scenes):
            messagebox.showinfo("提示", "没有下一场景", parent=self.root)
            return "break"
        ins = self.scene_speaking.index("insert")
        tail = self.scene_speaking.get(ins, "end-1c")
        if not tail.strip():
            messagebox.showinfo("提示", "光标后无内容可移动", parent=self.root)
            return "break"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        nxt = self.workflow.get_scene_by_index(self.current_scene_index + 1)
        if not scene or not nxt:
            return "break"
        head_kept = self.scene_speaking.get("1.0", ins)
        scene["speaking"] = head_kept
        nxt["speaking"] = self._speaking_join_moved_then_next(tail, nxt.get("speaking") or "")
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_left_move_head_to_prev(self, event=None):
        """Ctrl+Left：文首至光标移入上一镜讲话末尾，与上一镜原文用中文句号衔接。"""
        if self._speaking_ctrl_arrow_shift_held(event) or self._speaking_ctrl_arrow_alt_held(event):
            return  # 不 break，交给 bind_all：Ctrl+Shift 换场景，Ctrl+Alt 换集
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        if self.current_scene_index <= 0:
            messagebox.showinfo("提示", "没有上一场景", parent=self.root)
            return "break"
        ins = self.scene_speaking.index("insert")
        head = self.scene_speaking.get("1.0", ins)
        if not head.strip():
            messagebox.showinfo("提示", "光标前无内容可移动", parent=self.root)
            return "break"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        prev = self.workflow.get_scene_by_index(self.current_scene_index - 1)
        if not scene or not prev:
            return "break"
        tail_kept = self.scene_speaking.get(ins, "end-1c")
        scene["speaking"] = tail_kept
        prev["speaking"] = self._speaking_join_prev_then_moved(prev.get("speaking") or "", head)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _speaking_merge_next_pair_or_error(self):
        """合并讲话：须存在下一场景，且列表中下一条即本故事内紧随当前镜的下一条。成功返回 (current, next_scene)，否则返回错误字符串。"""
        wf = self.workflow
        idx = self.current_scene_index
        if idx + 1 >= len(wf.scenes):
            return "没有下一场景"
        current = wf.get_scene_by_index(idx)
        nxt = wf.get_scene_by_index(idx + 1)
        if not current or not nxt:
            return "无法读取场景"
        ss = wf.scenes_in_story(current)
        if len(ss) <= 1:
            return "本故事内没有可合并的下一场景"
        try:
            pos = ss.index(current)
        except ValueError:
            return "无法定位当前场景"
        if pos + 1 >= len(ss):
            return "已是本故事最后一镜"
        if ss[pos + 1] is not nxt:
            return "列表中的下一场景不是本故事中的下一场景，无法合并讲话"
        return (current, nxt)

    def _on_speaking_ctrl_m_merge_next_speaking(self, event=None):
        """Ctrl+M：把本故事下一场景的 speaking 并入当前（中缝按需加中文句号），音视频不变；删除下一场景。"""
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        r = self._speaking_merge_next_pair_or_error()
        if isinstance(r, str):
            messagebox.showinfo("提示", r, parent=self.root)
            return "break"
        current, nxt = r
        if not messagebox.askyesno(
            "合并讲话",
            "将「下一场景」的讲话合并到当前场景的讲话（中间按需加中文句号）。\n\n"
            "当前场景的视频、音频、图片等媒体保持不变，不合并音轨。\n"
            "下一场景将从场景列表中删除。\n\n"
            "是否继续？",
            parent=self.root,
        ):
            return "break"
        current["speaking"] = self._speaking_join_prev_then_moved(
            current.get("speaking") or "",
            nxt.get("speaking") or "",
        )
        self.workflow.release_scene_page_png(nxt)
        self.workflow.scenes.pop(self.current_scene_index + 1)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_shift_nav_prev(self, event=None):
        """讲话框内 Ctrl+Shift+←：上一场景（优先于 Text 默认行为，与 bind_scene_navigation_shortcuts 一致）。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.prev_scene()
        return "break"

    def _on_speaking_ctrl_shift_nav_next(self, event=None):
        """讲话框内 Ctrl+Shift+→：下一场景（同上）。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.next_scene()
        return "break"

    def _on_speaking_ctrl_alt_prev_episode(self, event=None):
        """讲话框内 Ctrl+Alt+←：上一集，与「本集内容」旁的按钮相同。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.prev_episode()
        return "break"

    def _on_speaking_ctrl_alt_next_episode(self, event=None):
        """讲话框内 Ctrl+Alt+→：下一集。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.next_episode()
        return "break"
