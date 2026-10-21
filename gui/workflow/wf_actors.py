"""ActorsMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import threading
import pygame
import config
import config_prompt
from PIL import Image, ImageTk
from project_manager import save_project_config
import project_manager
from utility.file_util import safe_copy_overwrite, show_auto_close_popup
from utility.voicebox_speech_service import VoiceboxService, _VB_SPEAKER_MARK_RE
from gui.choice_dialog import askchoice


class ActorsMixin:
    def _narrator_button_text(self, name: str = "") -> str:
        """按钮上只写讲员本人，例如 woman/qin/chinese。"""
        name = (name or project_manager.project_narrator() or "").strip()
        if not name or project_manager.actor_is_absent(name):
            return "不出现"
        return name

    def _refresh_narrator_button(self, name: str = "") -> None:
        btn = getattr(self, "_narrator_avatar_btn", None)
        if btn is not None:
            text = self._narrator_button_text(name)
            width = sum(2 if ord(ch) > 127 else 1 for ch in text) + 2
            btn.config(text=text, width=max(width, 8))

    def _actor_button_text(self, label: str, body: str, *, full: bool = False) -> str:
        body = (body or "").strip()
        if full and body:
            return f"{label} {body}"
        parts = [p for p in body.split("/") if p]
        if len(parts) >= 4 and not parts[-1].isdigit():
            short = parts[-1]
        else:
            short = parts[1] if len(parts) >= 2 else body
        short = short.strip()
        if len(short) > 8:
            short = short[:8]
        if not short:
            return label
        return f"{label} {short}"

    @staticmethod
    def _motion_chip_text(motion: str) -> str:
        motion = (motion or "").strip()
        if not motion or "已经在画面" in motion:
            return ""
        short = {
            "从容自然地 - 走进画面，讲完走出": "走进走出",
            "淡入画面，讲完淡出": "淡入淡出",
            "边品茶, 边讲述 - 淡入画面，讲完淡出": "茶叙式",
            "跳进画面，讲完跳出": "跳进跳出",
            "自然地 - 骑马走进画面，讲完骑马走出": "骑马进出",
        }
        shown = short.get(motion, motion)
        if len(shown) > 18:
            return shown[:18] + "…"
        return shown

    def _render_actor_buttons(self) -> None:
        row = getattr(self, "scene_actor_row", None)
        if row is None:
            return
        for child in row.winfo_children():
            child.destroy()
        entries = project_manager.actor_entries(self._actor_text)
        self._actor_buttons = []
        self._actor_drag_index = None
        self._actor_drag_moved = False
        if not entries:
            ttk.Label(row, text="（没有人物）").pack(side=tk.LEFT, padx=(0, 4))
        for entry in entries:
            if entry.get("role") == "host" and project_manager.actor_is_absent(entry.get("body") or ""):
                continue
            self._pack_actor_button(row, entry)

    def _pack_actor_button(self, row, entry: dict) -> None:
        body = (entry.get("body") or "").strip()
        base, motion = project_manager.split_actor_motion(body)
        if entry.get("role") == "host":
            text = self._actor_button_text("讲员", base, full=True) if base else "讲员"
        else:
            text = self._actor_button_text(entry.get("label") or "人物", base)
        motion_text = self._motion_chip_text(motion)
        if motion_text:
            text = f"{text} {motion_text}"
        # 可以 Tab / 点一下获得焦点（蓝框 + 浅蓝底），再按 Delete / BackSpace 删除。
        chip = tk.Frame(
            row, bg="white", relief="sunken", bd=1, cursor="fleur", takefocus=1,
            highlightthickness=2, highlightbackground="white", highlightcolor="#1a73e8",
        )
        label = tk.Label(chip, text=text, bg="white", cursor="fleur", anchor="w")
        label.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        chip._actor_entry = dict(entry)
        chip._actor_label = text
        chip.pack(side=tk.LEFT, padx=(0, 4))
        chip.update_idletasks()
        chip.configure(width=max(int(label.winfo_reqwidth() * 1.5) + 12, 72), height=label.winfo_reqheight() + 6)
        chip.pack_propagate(False)
        for widget in (chip, label):
            widget.bind("<ButtonPress-1>", self._actor_press)
            widget.bind("<B1-Motion>", self._actor_motion)
            widget.bind("<ButtonRelease-1>", self._actor_release)
            widget.bind("<Double-Button-1>", self._actor_double)
        chip.bind("<FocusIn>", lambda _e, c=chip, l=label: self._actor_chip_focus(c, l, True))
        chip.bind("<FocusOut>", lambda _e, c=chip, l=label: self._actor_chip_focus(c, l, False))
        chip.bind("<Delete>", self._actor_delete_key)
        chip.bind("<BackSpace>", self._actor_delete_key)
        self._actor_buttons.append(chip)

    def _actor_chip(self, widget):
        buttons = getattr(self, "_actor_buttons", None) or []
        while widget is not None and widget not in buttons:
            widget = getattr(widget, "master", None)
        return widget

    @staticmethod
    def _actor_chip_focus(chip, label, on: bool) -> None:
        bg = "#9fc5ff" if on else "white"
        try:
            chip.configure(bg=bg, highlightbackground="#1a73e8" if on else "white")
            label.configure(bg=bg)
        except tk.TclError:
            pass

    def _actor_delete_key(self, event) -> str:
        chip = self._actor_chip(event.widget)
        entry = getattr(chip, "_actor_entry", None)
        if isinstance(entry, dict):
            self._delete_actor_from_chip(entry)
        return "break"

    def _delete_actor_from_chip(self, entry: dict, *, ask=None) -> str:
        """人物栏按 Delete：问「本集所有场景同名都删？」是 = 本集每一场；否 = 只这一场；取消 = 不动。

        ``ask`` 只给测试用（返回 True / False / None）。返回 "episode" / "scene" / "cancel" / "none"。
        """
        body, _motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
        name = body.strip()
        if not name or project_manager.actor_is_absent(name):
            return "none"
        parent = self.root
        if ask is None:
            answer = messagebox.askyesnocancel(
                "删除", f"删除「{name}」：\n是 = 本集所有场景里同名的都删\n否 = 只删这一场\n取消 = 不删", parent=parent
            )
        else:
            answer = ask(name)
        if answer is None:
            return "cancel"
        if not answer:
            rows = self._scene_actor_rows()
            if len(rows) <= 1:
                messagebox.showinfo("删除", "这一场至少要留下一个讲员或人物。", parent=parent)
                return "none"
            _kept, removed = self._drop_scene_actor(entry)
            if not removed:
                messagebox.showinfo("删除", "这一场的名单里没有这一位。", parent=parent)
                return "none"
            if not self._apply_current_scene_actor_delete(entry):
                return "none"
            self._after_actor_delete()
            return "scene"
        workflow = getattr(self, "workflow", None)
        cur = workflow.get_scene_by_index(self.current_scene_index) if workflow else None
        if not isinstance(cur, dict):
            return "none"
        changed = 0
        kept_last = 0
        self._sync_speaking_widget_to_scene(cur)
        for scene in workflow.scenes_in_story(cur):
            if not isinstance(scene, dict):
                continue
            text = self._actor_text if scene is cur else (scene.get("actor") or "")
            index = project_manager.actor_index_by_name(text, name)
            if not index:
                continue
            if not project_manager.apply_actor_delete(scene, text, index):
                kept_last += 1  # 只剩这一位：整场不动
                continue
            if scene is cur:
                self._actor_text = scene.get("actor") or ""
            changed += 1
        if changed:
            self._show_scene_speaking(cur)
            workflow.save_scenes_to_json()
        self._render_actor_buttons()
        self._after_actor_delete()
        note = f"本集 {changed} 场删掉了「{name}」。"
        if kept_last:
            note += f"\n{kept_last} 场里只有这一位，按「至少留一个讲员或人物」没有删。"
        show_auto_close_popup(self.root, "删除", note, duration_ms=2500)
        return "episode"

    def _after_actor_delete(self) -> None:
        """删除后把焦点放回人物栏第一格，方便继续删。"""
        buttons = getattr(self, "_actor_buttons", None) or []
        if buttons:
            try:
                buttons[0].focus_set()
            except tk.TclError:
                pass

    def _actor_press(self, event) -> None:
        btn = self._actor_chip(event.widget)
        if btn is not None:
            try:
                btn.focus_set()
            except tk.TclError:
                pass
        try:
            self._actor_drag_index = self._actor_buttons.index(btn)
        except ValueError:
            self._actor_drag_index = None
        self._actor_drag_moved = False
        self._actor_drag_x = event.x_root

    def _actor_motion(self, event) -> None:
        src = self._actor_drag_index
        buttons = getattr(self, "_actor_buttons", None) or []
        if src is None or not buttons or src >= len(buttons):
            return
        if not self._actor_drag_moved and abs(event.x_root - self._actor_drag_x) < 6:
            return
        target = None
        best = None
        for i, btn in enumerate(buttons):
            center = btn.winfo_rootx() + max(btn.winfo_width(), 1) / 2
            dist = abs(event.x_root - center)
            if best is None or dist < best:
                best = dist
                target = i
        if target is None or target == src:
            return
        self._actor_drag_moved = True
        moved = buttons.pop(src)
        buttons.insert(target, moved)
        self._actor_drag_index = target
        for btn in buttons:
            btn.pack_forget()
        for btn in buttons:
            btn.pack(side=tk.LEFT, padx=(0, 4))

    def _actor_release(self, event) -> None:
        buttons = getattr(self, "_actor_buttons", None) or []
        index = self._actor_drag_index
        moved = self._actor_drag_moved
        self._actor_drag_index = None
        self._actor_drag_moved = False
        if index is None or index >= len(buttons):
            return
        if getattr(self, "_actor_skip_release", False):
            self._actor_skip_release = False
            return
        if not moved:
            chip = buttons[index]
            pending = getattr(self, "_actor_click_after", None)
            if pending:
                try:
                    self.root.after_cancel(pending)
                except tk.TclError:
                    pass
            self._actor_click_after = self.root.after(280, lambda c=chip: self._actor_single_click(c))
            return
        rows = []
        for btn in buttons:
            row = getattr(btn, "_actor_entry", None)
            if not isinstance(row, dict):
                continue
            row = dict(row)
            body = (row.get("body") or "").strip()
            if row.get("role") == "host" and (not body or project_manager.actor_is_absent(body)):
                continue
            if body:
                rows.append(row)
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _actor_double(self, event) -> None:
        self._actor_skip_release = True
        pending = getattr(self, "_actor_click_after", None)
        if pending:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
            self._actor_click_after = None
        chip = self._actor_chip(event.widget)
        entry = getattr(chip, "_actor_entry", None) or {}
        self._open_actor_preview(entry)

    def _actor_single_click(self, chip) -> None:
        self._actor_click_after = None
        entry = getattr(chip, "_actor_entry", None) or {}
        path = self._actor_entry_portrait(entry)
        who = getattr(chip, "_actor_label", "") or "这个人"
        body, _motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
        if path:
            self.copy_image_to_clipboard(path, silent=True)
            show_auto_close_popup(self.root, "剪贴板", f"{who} 的参考形象已拷贝", duration_ms=1000)
            return
        if entry.get("role") == "person" and body and not project_manager.actor_is_absent(body):
            show_auto_close_popup(self.root, "剪贴板", f"{who} 没有参考图，没有拷贝", duration_ms=1000)
            return
        self._open_actor_preview(entry)

    def _open_actor_preview(self, entry: dict) -> None:
        if entry.get("role") == "host":
            self._review_actor_host()
            return
        self._review_actor_person((entry.get("body") or "").strip())

    def _actor_entry_portrait(self, entry: dict) -> str:
        body, _motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
        if project_manager.actor_is_absent(body):
            return ""
        if entry.get("role") == "host":
            # 讲员：avatar/<风格>/ → avatar/Realistic/ → avatar/，每一层先全名、再前三段（同 actor.pdf）。
            names = [body]
            bits = [part for part in body.split("/") if part]
            if len(bits) >= 3:
                names.append("/".join(bits[:3]))
            return config.find_avatar_png([self._portrait_stem(n) for n in names], self._portrait_style())
        return self._person_portrait_path(body)

    def _portrait_style(self) -> str:
        """找形象图用的画面风格：界面上的场景画面风格 → 项目 visual_style → 上次选的。"""
        var = getattr(self, "scene_visual_style", None)
        try:
            value = (var.get() or "").strip() if var is not None else ""
        except Exception:
            value = ""
        return config.match_visual_style(value) or value or project_manager.current_visual_style()

    def _set_actor_text(self, text: str, *, save_scene: bool = False) -> None:
        self._actor_text = project_manager.normalize_actor_text(text)
        self._render_actor_buttons()
        if not save_scene:
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        old = (scene.get("actor") or "").strip()
        if old == self._actor_text:
            return
        scene["actor"] = self._actor_text
        self.workflow.save_scenes_to_json()

    def _review_actor_host(self) -> None:
        current = project_manager.actor_host_name(self._actor_text)

        def chosen(name: str) -> None:
            self._set_actor_text(project_manager.actor_with_host(self._actor_text, name), save_scene=True)

        host = next(
            (row for row in project_manager.actor_entries(self._actor_text) if row.get("role") == "host"),
            {"role": "host", "label": "讲员", "body": current or "不出现"},
        )
        self.review_project_narrator(current=current, on_confirm=chosen, actor_entry=host)

    @staticmethod
    def _portrait_stem(name: str) -> str:
        stem = (name or "").strip().replace("\\", "/").replace("/", "_")
        for ch in '<>:"|?*':
            stem = stem.replace(ch, "_")
        return stem.strip(" .")

    def _ensure_actor_voice_sample(self, name: str, role: str, picked: str = "") -> str:
        """按预览里选中的声音名生成一句试听，存到 avatar/voice，文件名就是这个声音名。"""
        voice_name = project_manager.resolve_actor_voice(name) or (name or "").strip()
        bits = [part.strip() for part in voice_name.split("/") if part.strip()]
        lang = bits[2].lower() if len(bits) >= 3 else "chinese"
        if lang not in ("chinese", "english"):
            lang = "chinese"
        look = "/".join(bits[:3]) if len(bits) >= 3 else voice_name
        chosen = (picked or "").strip() or config_prompt.chosen_actor_voice(name, role)
        stem = self._portrait_stem(chosen)
        if not stem:
            raise RuntimeError("这一位没有可选的声音")
        folder = os.path.join(config.AVATAR_PATH, "voice")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, stem + ".wav")
        if os.path.isfile(dest) and os.path.getsize(dest) > 100:
            return dest
        line = "你好, 请问我能帮你做些什么?" if lang == "chinese" else "Hi how are you doing?"
        service = getattr(self, "speech_service", None)
        if service is None:
            pid = getattr(getattr(self, "workflow", None), "pid", None) or "avatar"
            service = VoiceboxService(pid)
            self.speech_service = service
        from utility.voicebox_speech_service import VOICES, _ensure_voices_for_project

        _ensure_voices_for_project(getattr(service, "pid", "") or "avatar")
        speaker = chosen if any(
            str(row.get("name") or "").strip().lower() == chosen.lower() for row in VOICES
        ) else look
        wav = service.synthesize_speaker_text_to_wav(speaker, line, "en" if lang == "english" else "zh")
        if not wav or not os.path.isfile(wav):
            raise RuntimeError("声音没有生成")
        safe_copy_overwrite(wav, dest)
        return dest

    def _narrator_portrait_path(self, name: str) -> str:
        """voices.json 的 name 把 / 换成 _：avatar/<风格>/ → avatar/Realistic/ → avatar/ 里的 png。"""
        stem = WorkflowGUI._portrait_stem(name)
        if not stem:
            return ""
        return config.find_avatar_png([stem], self._portrait_style())

    def _narrator_portrait_dest(self, name: str) -> str:
        """讲员贴图存到 avatar/<当前风格>/（不动根目录和其他风格的图）。"""
        stem = self._portrait_stem(name)
        if not stem:
            return ""
        folder = config.avatar_style_dest_dir(self._portrait_style())
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, stem + ".png")

    def _project_avatar_dir(self) -> str:
        pid = self.get_pid()
        path = os.path.join(config.get_project_path(pid), "avatar")
        os.makedirs(path, exist_ok=True)
        return path

    def _narrator_browse_names(self) -> list:
        return [""] + [x for x in config.narrator_person_options() if (x or "").strip()]

    def _project_person_names(self) -> list:
        """这个项目 avatar 目录里的人物，再加上这一场里还没有图片的人物。"""
        found = []
        folder = ""
        try:
            folder = self._project_avatar_dir()
        except Exception:
            folder = ""
        token = config.visual_style_token(self._portrait_style())
        folders = [folder] + ([os.path.join(folder, token)] if folder and token else [])
        for folder in folders:
            if not folder or not os.path.isdir(folder):
                continue
            for fn in sorted(os.listdir(folder)):
                low = fn.lower()
                if not low.endswith(config.AVATAR_IMAGE_EXTS) or ".bak" in low:
                    continue
                stem = os.path.splitext(fn)[0]  # 同一 stem 的 png / jpg / webp 只列一次
                if not stem or stem.startswith("_"):
                    continue
                raw = stem.replace("_", "/")
                if raw not in found:
                    found.append(raw)
        try:
            rows = self._scene_actor_rows()
        except Exception:
            rows = []
        for row in rows:
            if row.get("role") != "person":
                continue
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            if not body or project_manager.actor_is_absent(body) or body in found:
                continue
            found.append(body)
        return found

    def _person_portrait_dest(self, name: str) -> str:
        body, _motion = project_manager.split_actor_motion((name or "").strip())
        stem = self._portrait_stem(body)
        if not stem:
            return ""
        return os.path.join(self._project_avatar_dir(), stem + ".png")

    def _person_portrait_path(self, name: str) -> str:
        """项目人物：<项目>/avatar/<风格>/ → <项目>/avatar/（贴图仍存在 <项目>/avatar/）。不退到通用头像库。"""
        dest = self._person_portrait_dest(name)
        if not dest:
            return ""
        folder, stem = os.path.dirname(dest), os.path.splitext(os.path.basename(dest))[0]
        token = config.visual_style_token(self._portrait_style())
        for level in ([os.path.join(folder, token)] if token else []) + [folder]:
            path = config.find_image_by_stem(level, stem)  # .png / .jpg / .jpeg / .webp，.png 优先
            if path:
                return path
        return ""

    @staticmethod
    def _backup_portrait(path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        folder, base = os.path.split(path)
        stem, ext = os.path.splitext(base)
        n = 1
        while True:
            bak = os.path.join(folder, f"{stem}.bak{n}{ext}")
            if not os.path.exists(bak):
                os.replace(path, bak)
                return
            n += 1

    def _paste_portrait_file(self, dest: str, parent) -> bool:
        """把剪贴板里的图存成 dest。原来有文件就先改名备份。"""
        from PIL import ImageGrab

        if not dest:
            messagebox.showwarning("头像", "先选定一个名字。", parent=parent)
            return False
        clip = ImageGrab.grabclipboard()
        if clip is None:
            messagebox.showwarning("头像", "剪贴板里没有图片。", parent=parent)
            return False
        try:
            if isinstance(clip, list):
                src = next((p for p in clip if p and os.path.isfile(p)), "")
                if not src:
                    messagebox.showwarning("头像", "剪贴板里没有图片。", parent=parent)
                    return False
                img = Image.open(src)
            else:
                img = clip
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            self._backup_portrait(dest)
            img.save(dest, "PNG")
        except Exception as e:
            messagebox.showerror("头像", f"保存失败：{e}", parent=parent)
            return False
        return True

    @staticmethod
    def _speaking_as_host_only(text: str) -> str:
        """讲稿只在开头标一次〈1〉，后面的换人标记去掉，整段都由讲员说。"""
        raw = (text or "").strip()
        if not raw:
            return ""
        body = _VB_SPEAKER_MARK_RE.sub(" ", raw)
        lines = []
        for line in body.splitlines():
            piece = " ".join(line.split())
            if piece:
                lines.append(piece)
        body = "\n".join(lines).strip()
        if not body:
            return ""
        return "<1> " + body

    def _force_speaking_to_host(self, scope: str, narrator: str = "") -> None:
        if not getattr(self, "workflow", None):
            return
        narrator = (narrator or "").strip()
        if project_manager.actor_is_absent(narrator):
            narrator = (project_manager.project_narrator() or "").strip()
        if project_manager.actor_is_absent(narrator):
            messagebox.showinfo("全改讲员", "先选定一个讲员。", parent=self.root)
            return
        current = self.workflow.get_scene_by_index(self.current_scene_index)
        if not isinstance(current, dict):
            return
        if hasattr(self, "scene_speaking"):
            current["speaking"] = self.scene_speaking.get("1.0", tk.END).strip()
        if scope == "episode":
            targets = self.workflow.scenes_in_story(current) or [current]
        elif scope == "all":
            targets = [s for s in (self.workflow.scenes or []) if isinstance(s, dict)]
        else:
            targets = [current]
        changed = 0
        actor_changed = 0
        for scene in targets:
            old = (scene.get("speaking") or "").strip()
            new = self._speaking_as_host_only(old)
            if new != old:
                scene["speaking"] = new
                changed += 1
            old_actor = (scene.get("actor") or "").strip()
            new_actor = project_manager.normalize_actor_text(
                project_manager.actor_with_host(old_actor, narrator)
            )
            if new_actor != project_manager.normalize_actor_text(old_actor):
                scene["actor"] = new_actor
                actor_changed += 1
        if hasattr(self, "scene_speaking"):
            loading = getattr(self, "_scene_widgets_loading", False)
            self._scene_widgets_loading = True
            try:
                self.scene_speaking.delete("1.0", tk.END)
                self.scene_speaking.insert("1.0", current.get("speaking") or "")
            finally:
                self._scene_widgets_loading = loading
        self._set_actor_text(current.get("actor") or "")
        self.workflow.save_scenes_to_json()
        if scope == "episode":
            where = "这一集"
        elif scope == "all":
            where = "全部场景"
        else:
            where = "这一场"
        show_auto_close_popup(
            self.root,
            "全改讲员",
            f"已把{where}的讲员换成 {narrator}。讲员改了 {actor_changed} 场，讲稿改了 {changed} 场。",
        )

    def _review_actor_person(self, body: str) -> None:
        body, _motion = project_manager.split_actor_motion((body or "").strip())
        if not body:
            return
        names = self._project_person_names()
        if body not in names:
            names.append(body)
        self._open_portrait_dialog(
            title="人物",
            names=names,
            current=body,
            dest_for=self._person_portrait_dest,
            path_for=self._person_portrait_path,
            hint="Ctrl+V 把剪贴板图片存成这个人物。没有就显示没有。人物已经在画面里，拷贝图案直接拷这张图。",
            allow_empty=False,
            ask_motion=False,
            actor_entry={"role": "person", "label": "人物", "body": body},
        )

    def _open_portrait_dialog(
        self,
        *,
        title: str,
        names: list,
        current: str,
        dest_for,
        path_for,
        hint: str,
        allow_empty: bool,
        on_confirm=None,
        ask_motion: bool = False,
        actor_entry: dict | None = None,
        parent=None,
        host_only: bool = False,
    ) -> None:
        """头像预览。左右键换人；Ctrl+V 粘贴图片，旧图先备份。拷贝图案。"""
        if not names:
            return
        win = parent or self.root
        current = (current or "").strip()
        try:
            index = names.index(current)
        except ValueError:
            index = 0

        dlg = tk.Toplevel(win)
        dlg.title(title)
        dlg.transient(win)
        dlg.grab_set()
        dlg.resizable(False, False)

        name_var = tk.StringVar()
        ttk.Label(dlg, textvariable=name_var, font=("TkDefaultFont", 12, "bold")).pack(pady=(12, 4))
        opened_motion = ""
        if actor_entry:
            _opened_body, opened_motion = project_manager.split_actor_motion((actor_entry.get("body") or "").strip())
        if opened_motion:
            ttk.Label(dlg, text=f"这一场：（{opened_motion}）", wraplength=640).pack(pady=(0, 4))
        image_label = ttk.Label(dlg)
        image_label.pack(padx=16, pady=4)
        voice_row = ttk.Frame(dlg)
        voice_row.pack(pady=(0, 8))
        ttk.Label(voice_row, text="声音").pack(side=tk.LEFT, padx=(0, 8))
        voice_var = tk.StringVar()
        voice_box = ttk.Combobox(voice_row, textvariable=voice_var, state="readonly", width=18)
        voice_box.pack(side=tk.LEFT)
        hear_btn = ttk.Button(voice_row, text="听声音")
        hear_btn.pack(side=tk.LEFT, padx=(8, 0))
        hint_var = tk.StringVar(value=hint)
        ttk.Label(dlg, textvariable=hint_var, wraplength=640).pack(pady=(0, 8))
        holder = {
            "photo": None,
            "index": index,
            "names": list(names),
            "path_for": path_for,
            "dest_for": dest_for,
            "mode": "host" if ask_motion else "person",
            "override_name": "",
            "voice_ready": False,
        }
        host_hint = "左右键在讲员里换。讲员是 D:\\AI_MEDIA\\avatar 里那一份固定名单。最左表示这场没有讲员，名单里不写。拷贝图案拷当前图，并问怎么进出画面。场景里写了讲员就出镜，没写就是画外旁白。确认照现在选的写进这一场并关掉。要删掉某一位，在人物栏点一下选中，再按 Delete。全改讲员把选定范围内每一场的讲员换成当前这一位，讲稿收成只在开头标〈1〉。增加人物时可以换掉某一位，或不换就放在最后。已经四个人时，放在最后会换掉第四个。"
        person_hint = "左右键在这个项目的人物里换。人物图片在项目的 avatar 目录。增加人物时可以换掉某一位，或不换就放在最后。已经四个人时，放在最后会换掉第四个。没有图片时不拷贝。Ctrl+V 可以贴上形象。确认照现在选的写进这一场并关掉。要删掉某一位，在人物栏点一下选中，再按 Delete。"

        def remember_voice(name: str, voice: str) -> None:
            pc = project_manager.PROJECT_CONFIG
            if not isinstance(pc, dict) or not name or not voice:
                return
            role = "host" if holder.get("mode") == "host" else "person"
            key = config_prompt.actor_voice_storage_key(name, role)
            if not key:
                return
            table = pc.get("actor_voices")
            if not isinstance(table, dict):
                table = {}
                pc["actor_voices"] = table
            if table.get(key) == voice:
                return
            table[key] = voice
            save_project_config(parent=dlg)

        def show_voice(name: str) -> None:
            holder["voice_ready"] = False
            if not name or project_manager.actor_is_absent(name):
                voice_box.configure(values=())
                voice_var.set("")
                voice_box.state(["disabled"])
                return
            role = "host" if holder.get("mode") == "host" else "person"
            options = list(config_prompt.voice_choices_for_actor(name))
            voice_box.configure(values=options)
            if not options:
                voice_var.set("")
                voice_box.state(["disabled"])
                return
            voice_box.state(["!disabled"])
            saved = config_prompt.chosen_actor_voice(name, role)
            voice_var.set(saved if saved in options else options[0])
            holder["voice_ready"] = True
            if len(options) == 1:
                remember_voice(name, options[0])

        def on_voice_picked(_event=None) -> None:
            if not holder.get("voice_ready"):
                return
            names_now = holder["names"]
            if not names_now:
                return
            name = names_now[holder["index"]]
            remember_voice(name, voice_var.get().strip())

        def preview_voice() -> None:
            names_now = holder["names"]
            if not names_now:
                return
            name = holder.get("override_name") or names_now[holder["index"]]
            if not name or project_manager.actor_is_absent(name):
                messagebox.showinfo("听声音", "这一位没有声音。", parent=dlg)
                return
            hear_btn.state(["disabled"])
            role = "host" if holder.get("mode") == "host" else "person"
            picked = voice_var.get().strip()

            def work() -> None:
                try:
                    path = self._ensure_actor_voice_sample(name, role, picked)
                except Exception as exc:
                    err = str(exc)

                    def failed(msg=err) -> None:
                        hear_btn.state(["!disabled"])
                        messagebox.showerror("听声音", msg, parent=dlg)

                    dlg.after(0, failed)
                    return

                def play(sample=path) -> None:
                    hear_btn.state(["!disabled"])
                    try:
                        if not pygame.mixer.get_init():
                            pygame.mixer.init()
                        old = holder.get("preview_channel")
                        if old is not None:
                            old.stop()
                        sound = pygame.mixer.Sound(sample)
                        holder["preview_sound"] = sound
                        holder["preview_channel"] = sound.play()
                    except Exception as exc:
                        messagebox.showerror("听声音", str(exc), parent=dlg)

                dlg.after(0, play)

            threading.Thread(target=work, daemon=True).start()

        hear_btn.configure(command=preview_voice)

        def show_at(i: int) -> None:
            holder["override_name"] = ""
            names_now = holder["names"]
            if not names_now:
                holder["index"] = 0
                name_var.set("还没有人物")
                holder["photo"] = None
                image_label.config(image="", text="还没有人物")
                show_voice("")
                return
            holder["index"] = max(0, min(i, len(names_now) - 1))
            name = names_now[holder["index"]]
            if not name:
                name_var.set("不出现")
                show_voice("")
                holder["photo"] = None
                image_label.config(image="", text="不出现")
                return
            name_var.set(name)
            show_voice(name)
            path = holder["path_for"](name)
            if not path:
                holder["photo"] = None
                image_label.config(image="", text="没有头像")
                return
            try:
                img = Image.open(path)
                img.thumbnail((420, 560), Image.Resampling.LANCZOS)
                holder["photo"] = ImageTk.PhotoImage(img)
                image_label.config(image=holder["photo"], text="")
            except OSError:
                holder["photo"] = None
                image_label.config(image="", text="没有头像")

        def shift(step: int) -> None:
            names_now = holder["names"]
            if len(names_now) < 2:
                return
            nxt = max(0, min(holder["index"] + step, len(names_now) - 1))
            show_at(nxt)

        def paste(_event=None) -> str:
            names_now = holder["names"]
            if not names_now:
                return "break"
            name = names_now[holder["index"]]
            if not name:
                messagebox.showinfo(title, "不出现的人不用粘贴图片。", parent=dlg)
                return "break"
            if self._paste_portrait_file(holder["dest_for"](name), dlg):
                show_at(holder["index"])
            return "break"

        def ask_motion_choice() -> str:
            dlg.grab_release()
            picked = askchoice(
                "这个人怎么进出画面",
                [
                    ("走进走出", "从容自然地 - 走进画面，讲完走出"),
                    ("淡入淡出", "淡入画面，讲完淡出"),
                    ("茶叙式",   "边品茶, 边讲述 - 淡入画面，讲完淡出"),
                    ("跳进跳出", "跳进画面，讲完跳出"),
                    ("骑马进出", "自然地 - 骑马走进画面，讲完骑马走出")
                ],
                dlg,
            )
            dlg.grab_set()
            return picked[0] if picked else ""

        def apply_choice(name: str, motion: str) -> None:
            """把打开时的那一格换成现在选定的人。收成性别、年龄段、民族，名字放最后。"""
            role = "host" if holder.get("mode") == "host" else "person"
            bare = (name or "").strip()
            if project_manager.actor_is_absent(bare):
                if role == "host" and actor_entry:
                    self._clear_scene_host(dlg)
                elif on_confirm is not None and role == "host":
                    on_confirm("")
                return
            body = project_manager.actor_body_with_default_age(bare)
            if motion:
                base, _old = project_manager.split_actor_motion(body)
                body = project_manager._with_actor_motion(base, motion)
            if role == "person" and self._scene_has_person(body):
                return
            if actor_entry:
                self._replace_opened_actor(actor_entry, role, body)
                return
            if on_confirm is not None and role == "host":
                on_confirm(bare)

        def finish() -> None:
            if holder.get("override_name"):
                name = holder["override_name"]
            else:
                names_now = holder["names"]
                if holder.get("mode") == "person" and not names_now:
                    messagebox.showinfo("人物", "先选定一个人物。", parent=dlg)
                    return
                name = (names_now[holder["index"]] if names_now else "") or ""
            if holder.get("mode") == "person" and not name:
                messagebox.showinfo("人物", "先选定一个人物。", parent=dlg)
                return
            motion = ""
            _kept_body, kept_motion = ("", "")
            if actor_entry:
                _kept_body, kept_motion = project_manager.split_actor_motion((actor_entry.get("body") or "").strip())
            if holder.get("mode") == "host" and name and not project_manager.actor_is_absent(name):
                motion = kept_motion or ask_motion_choice()
                if not motion:
                    return
            elif holder.get("mode") == "person":
                motion = kept_motion
            if not name or project_manager.actor_is_absent(name):
                portrait = ""
            elif holder.get("override_name"):
                portrait = self._narrator_portrait_path(name) or ""
            else:
                portrait = holder["path_for"](name) or ""
            if portrait:
                self.copy_image_to_clipboard(portrait, silent=True)
            elif name and not project_manager.actor_is_absent(name):
                show_auto_close_popup(self.root, "剪贴板", f"{name} 没有参考图，没有拷贝", duration_ms=1000)
            apply_choice(name, motion)
            dlg.destroy()

        def confirm() -> None:
            """确认：照现在选的这一位写进这一场（声音换了就已经存过），不拷贝图，然后关掉。"""
            if holder.get("override_name"):
                name = holder["override_name"]
            else:
                names_now = holder["names"]
                name = (names_now[holder["index"]] if names_now else "") or ""
            if holder.get("mode") == "person" and not name:
                messagebox.showinfo("人物", "先选定一个人物。", parent=dlg)
                return
            kept_motion = ""
            if actor_entry:
                _b, kept_motion = project_manager.split_actor_motion((actor_entry.get("body") or "").strip())
            apply_choice(name, kept_motion)
            dlg.destroy()

        def add_person() -> None:
            dlg.grab_release()
            try:
                before = list(holder["names"])
                self._add_manual_scene_person(dlg, actor_entry)
            finally:
                try:
                    dlg.grab_set()
                except tk.TclError:
                    pass
            if holder.get("mode") != "person":
                return
            holder["names"] = self._project_person_names()
            added = [name for name in holder["names"] if name not in before]
            show_at(holder["names"].index(added[-1]) if added else holder["index"])

        def ask_force_host_speaking() -> None:
            if holder.get("mode") != "host":
                return
            dlg.grab_release()
            try:
                picked = askchoice(
                    "讲稿改成讲员",
                    [
                        ("scene", "当前这场"),
                        ("episode", "这一集"),
                        ("all", "全部场景"),
                    ],
                    dlg,
                )
            finally:
                try:
                    dlg.grab_set()
                except tk.TclError:
                    pass
            if not picked:
                return
            if holder.get("override_name"):
                narrator = holder["override_name"]
            else:
                names_now = holder["names"]
                narrator = (names_now[holder["index"]] if names_now else "") or ""
            self._force_speaking_to_host(picked[1], narrator)

        def apply_domain_chrome() -> None:
            if holder["mode"] == "host":
                dlg.title("讲员")
                hint_var.set(host_hint)
                switch_btn.config(text="切换成人物")
                if not force_btn.winfo_ismapped():
                    force_btn.pack(side=tk.LEFT, padx=6, before=confirm_btn)
            else:
                dlg.title("人物")
                hint_var.set(person_hint)
                switch_btn.config(text="切换成讲员")
                force_btn.pack_forget()
            if not add_btn.winfo_ismapped():
                add_btn.pack(side=tk.LEFT, padx=6, before=confirm_btn)

        def toggle_domain() -> None:
            if holder["mode"] == "host":
                holder["mode"] = "person"
                holder["names"] = self._project_person_names()
                holder["path_for"] = self._person_portrait_path
                holder["dest_for"] = self._person_portrait_dest
                start = 0
                body = ""
                if actor_entry and actor_entry.get("role") == "person":
                    body, _motion = project_manager.split_actor_motion(actor_entry.get("body") or "")
                if body and body in holder["names"]:
                    start = holder["names"].index(body)
            else:
                holder["mode"] = "host"
                holder["names"] = self._narrator_browse_names()
                holder["path_for"] = self._narrator_portrait_path
                holder["dest_for"] = self._narrator_portrait_dest
                current_host = project_manager.project_narrator()
                start = holder["names"].index(current_host) if current_host in holder["names"] else 0
            holder["override_name"] = ""
            apply_domain_chrome()
            show_at(start)

        btns = ttk.Frame(dlg)
        btns.pack(pady=(0, 12))
        ttk.Button(btns, text="拷贝图案", command=finish).pack(side=tk.LEFT, padx=6)
        switch_btn = ttk.Button(btns, text="切换成人物", command=toggle_domain)
        if not host_only:
            switch_btn.pack(side=tk.LEFT, padx=6)
        force_btn = ttk.Button(btns, text="全改讲员", command=ask_force_host_speaking)
        add_btn = ttk.Button(btns, text="增加人物", command=add_person)
        confirm_btn = ttk.Button(btns, text="确认", command=confirm)
        confirm_btn.pack(side=tk.LEFT, padx=6)
        cancel_btn = ttk.Button(btns, text="取消", command=dlg.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=6)
        apply_domain_chrome()

        voice_box.bind("<<ComboboxSelected>>", on_voice_picked)
        image_label.bind("<Button-1>", lambda _e: shift(1))
        image_label.bind("<Button-3>", lambda _e: shift(-1))
        dlg.bind("<Left>", lambda _e: shift(-1))
        dlg.bind("<Right>", lambda _e: shift(1))
        dlg.bind("<Control-v>", paste)
        dlg.bind("<Return>", lambda _e: finish(False))
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        show_at(index)
        dlg.update_idletasks()
        x = win.winfo_rootx() + max(0, (win.winfo_width() - dlg.winfo_reqwidth()) // 2)
        y = win.winfo_rooty() + max(0, (win.winfo_height() - dlg.winfo_reqheight()) // 2)
        dlg.geometry(f"+{x}+{y}")
        dlg.focus_set()
        dlg.wait_window()

    def _scene_actor_rows(self) -> list:
        return project_manager.actor_entries(self._actor_text)

    def _drop_scene_actor(self, entry: dict) -> tuple[list, bool]:
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        kept = []
        removed = False
        for row in self._scene_actor_rows():
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or body == target_body)
            if same and not removed:
                removed = True
                continue
            kept.append(row)
        return kept, removed

    def _delete_scene_actor(self, entry: dict | None, parent) -> bool:
        if not entry:
            return False
        rows = self._scene_actor_rows()
        if len(rows) <= 1:
            messagebox.showinfo("删除", "这一场至少要留下一个讲员或人物。", parent=parent)
            return False
        kept, removed = self._drop_scene_actor(entry)
        if not removed:
            messagebox.showinfo("删除", "这一场的名单里没有这一位。", parent=parent)
            return False
        if not messagebox.askyesno("删除", "删除这一位？这一场的人物里就没有他了。", parent=parent):
            return False
        return self._apply_current_scene_actor_delete(entry)

    def _scene_actor_delete_index(self, entry: dict) -> int:
        """``_drop_scene_actor`` 删的那一行在 <N> 名单里的位置（从 1 起）。讲员按角色找，人物按全名找。"""
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        for i, row in enumerate(project_manager.actor_speaker_rows(self._actor_text), start=1):
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            if row.get("role") == target_role and (target_role == "host" or body == target_body):
                return i
        return 0

    def _sync_speaking_widget_to_scene(self, scene) -> None:
        if isinstance(scene, dict) and hasattr(self, "scene_speaking"):
            try:
                scene["speaking"] = self.scene_speaking.get("1.0", tk.END).strip()
            except tk.TclError:
                pass

    def _show_scene_speaking(self, scene) -> None:
        if not (isinstance(scene, dict) and hasattr(self, "scene_speaking")):
            return
        loading = getattr(self, "_scene_widgets_loading", False)
        self._scene_widgets_loading = True
        try:
            if self.scene_speaking.get("1.0", tk.END).strip() != (scene.get("speaking") or "").strip():
                self.scene_speaking.delete("1.0", tk.END)
                self.scene_speaking.insert("1.0", scene.get("speaking") or "")
        except tk.TclError:
            pass
        finally:
            self._scene_widgets_loading = loading

    def _apply_current_scene_actor_delete(self, entry: dict) -> bool:
        """当前场景删掉 ``entry``：改名单，并按新编号改 speaking 的 <N>（见 ``project_manager.apply_actor_delete``）。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        index = self._scene_actor_delete_index(entry)
        if not isinstance(scene, dict) or not index:
            kept, _removed = self._drop_scene_actor(entry)
            self._set_actor_text(project_manager.format_actor_entries(kept), save_scene=True)
            return True
        self._sync_speaking_widget_to_scene(scene)
        if not project_manager.apply_actor_delete(scene, self._actor_text, index):
            return False
        self._set_actor_text(scene.get("actor") or "")
        scene["actor"] = self._actor_text
        self._show_scene_speaking(scene)
        self.workflow.save_scenes_to_json()
        return True

    def _clear_scene_host(self, parent) -> bool:
        """这场没有讲员。从名单里拿掉，不写「不出现」。"""
        people = [
            row for row in self._scene_actor_rows()
            if row.get("role") != "host" and not project_manager.actor_is_absent(row.get("body") or "")
        ]
        if not people:
            messagebox.showinfo("讲员", "这一场至少要留下一个讲员或人物。", parent=parent)
            return False
        self._set_actor_text(project_manager.format_actor_entries(people), save_scene=True)
        return True

    def _replace_opened_actor(self, entry: dict | None, role: str, body: str) -> None:
        """把打开预览时的那一格换成现在这个人，位置不动。换成讲员时，原来的讲员让开。"""
        role = "host" if role == "host" else "person"
        body = (body or "").strip() or "不出现"
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        rows = []
        replaced = False
        for row in self._scene_actor_rows():
            row_body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or row_body == target_body)
            if same and not replaced:
                rows.append({"role": role, "label": "讲员" if role == "host" else "人物", "body": body})
                replaced = True
                continue
            if role == "host" and row.get("role") == "host":
                continue
            rows.append(row)
        if not replaced:
            if role == "person" and self._scene_has_person(body):
                return
            rows.append({"role": role, "label": "讲员" if role == "host" else "人物", "body": body})
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _scene_has_person(self, body: str) -> bool:
        want, _motion = project_manager.split_actor_motion(project_manager.actor_body_with_default_age(body))
        if not want or project_manager.actor_is_absent(want):
            return False
        for row in self._scene_actor_rows():
            if row.get("role") != "person":
                continue
            got, _motion = project_manager.split_actor_motion(row.get("body") or "")
            if got == want:
                return True
        return False

    def _ask_manual_person(self, parent) -> str:
        """手工加一位人物。名字可空，有名字就写在最后。"""
        box = tk.Toplevel(parent)
        box.title("增加人物")
        box.transient(parent)
        box.grab_set()
        box.resizable(False, False)
        result = {"body": ""}
        gender = tk.StringVar(value="woman")
        bucket = tk.StringVar(value="mature")
        race = tk.StringVar(value="chinese")
        person_name = tk.StringVar()

        frm = ttk.Frame(box, padding=12)
        frm.pack()
        ttk.Label(frm, text="男女").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(frm, textvariable=gender, values=("woman", "man"), state="readonly", width=18).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(frm, text="年龄段").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=bucket,
            values=("kids", "youth", "teenager", "mature", "senior"),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="中英").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(frm, textvariable=race, values=("chinese", "english"), state="readonly", width=18).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(frm, text="名字").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=person_name, width=20).grid(row=3, column=1, sticky="w")
        ttk.Label(frm, text="可以不填。有名字就写在最后。").grid(row=3, column=2, sticky="w", padx=8)
        ttk.Label(
            frm,
            text="加上之后可以拖到第几位。没有图片时不带参考图。双击这位，Ctrl+V 可以贴上形象。",
            wraplength=360,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def ok() -> None:
            body = (
                f"{gender.get().strip() or 'woman'}/"
                f"{bucket.get().strip() or 'mature'}/"
                f"{race.get().strip() or 'chinese'}"
            )
            who = person_name.get().strip()
            if who:
                body = f"{body}/{who}"
            result["body"] = body
            box.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text="加上", command=ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="取消", command=box.destroy).pack(side=tk.LEFT, padx=6)
        box.bind("<Return>", lambda _e: ok())
        box.bind("<Escape>", lambda _e: box.destroy())
        box.protocol("WM_DELETE_WINDOW", box.destroy)
        box.focus_set()
        box.wait_window()
        return result["body"]

    def _present_actor_rows(self) -> list:
        return [
            row for row in self._scene_actor_rows()
            if not project_manager.actor_is_absent(row.get("body") or "")
        ]

    def _actor_slot_index(self, entry: dict | None) -> int:
        rows = self._scene_actor_rows()
        if not rows:
            return -1
        if not entry:
            return len(rows) - 1
        target_role = entry.get("role")
        target_body, _motion = project_manager.split_actor_motion(entry.get("body") or "")
        for index, row in enumerate(rows):
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or body == target_body)
            if same:
                return index
        return len(rows) - 1

    def _add_manual_scene_person(self, parent, after_entry: dict | None = None) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            messagebox.showinfo("增加人物", "先打开一场。", parent=parent)
            return
        body = self._ask_manual_person(parent)
        if not body:
            return
        rows = list(self._scene_actor_rows())
        present = self._present_actor_rows()
        new_row = {"role": "person", "label": "人物", "body": body}
        current_index = self._actor_slot_index(after_entry)
        present_index_of_current = None
        seen = 0
        for index, row in enumerate(rows):
            if project_manager.actor_is_absent(row.get("body") or ""):
                continue
            if index == current_index:
                present_index_of_current = seen
            seen += 1
        choices = []
        for index, row in enumerate(present):
            who, _motion = project_manager.split_actor_motion(row.get("body") or "")
            mark = "（当前）" if index == present_index_of_current else ""
            choices.append((f"slot{index}", f"替换第{index + 1}位{mark}：{who}"))
        if len(present) >= 4:
            choices.append(("append", "放在最后，换掉第四个"))
        else:
            choices.append(("append", "放在最后"))
        picked = askchoice("新的人放在哪里", choices, parent)
        if not picked:
            return
        place = picked[1]
        if place == "append":
            if len(present) >= 4:
                seen = 0
                for index, row in enumerate(rows):
                    if project_manager.actor_is_absent(row.get("body") or ""):
                        continue
                    seen += 1
                    if seen == 4:
                        rows[index] = new_row
                        break
            else:
                rows.append(new_row)
        elif place.startswith("slot"):
            try:
                slot = int(place[4:])
            except ValueError:
                return
            seen = 0
            for index, row in enumerate(rows):
                if project_manager.actor_is_absent(row.get("body") or ""):
                    continue
                if seen == slot:
                    rows[index] = new_row
                    break
                seen += 1
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _ask_apply_narrator_to_all_scenes(self, name: str, parent=None) -> None:
        """上面的讲员换了以后，问要不要把每一场已有的讲员换成这一位。"""
        workflow = getattr(self, "workflow", None)
        scenes = [s for s in (getattr(workflow, "scenes", None) or []) if isinstance(s, dict)]
        if not scenes:
            return
        target = (name or "").strip()
        if project_manager.actor_is_absent(target):
            target = ""
        pending = []
        for scene in scenes:
            old = (scene.get("actor") or "").strip()
            if not project_manager.actor_host_name(old):
                continue
            new = project_manager.actor_with_host(old, target)
            if new == old:
                continue
            pending.append((scene, new))
        if not pending:
            return
        who = target or "不出现"
        ok = messagebox.askyesno(
            "讲员",
            f"上面的讲员已换成 {who}。\n要把每一场里的讲员都换成这一位吗？\n有 {len(pending)} 场会改。人物不动。",
            parent=parent or self.root,
        )
        if not ok:
            return
        for scene, new in pending:
            scene["actor"] = new
        workflow.save_scenes_to_json()
        current = None
        try:
            current = workflow.get_scene_by_index(self.current_scene_index)
        except Exception:
            current = None
        if isinstance(current, dict):
            self._set_actor_text(current.get("actor") or "")

    def review_project_narrator(self, current: str | None = None, on_confirm=None, actor_entry=None, parent=None) -> None:
        """左右键翻讲员头像。默认写回项目 narrator；传入 on_confirm 则交给调用方。"""
        win = parent or self.root
        pc = project_manager.PROJECT_CONFIG
        if parent is None and not isinstance(pc, dict):
            messagebox.showwarning("讲员", "请先加载或创建项目。", parent=win)
            return
        names = [""] + [x for x in config.narrator_person_options() if (x or "").strip()]
        if len(names) == 1:
            messagebox.showwarning("讲员", "voices.json 里没有可选讲员。", parent=win)
            return
        if current is None:
            current = project_manager.project_narrator()

        def chosen(name: str) -> None:
            if on_confirm is not None:
                on_confirm(name)
                return
            if isinstance(pc, dict):
                pc["narrator"] = name
            project_manager.LAST_NARRATOR = name
            save_project_config(parent=win)
            self._refresh_narrator_button(name)
            self.root.after(10, lambda n=name: self._ask_apply_narrator_to_all_scenes(n))

        self._open_portrait_dialog(
            title="讲员",
            names=names,
            current=(current or "").strip(),
            dest_for=self._narrator_portrait_dest,
            path_for=self._narrator_portrait_path,
            hint="← 最左是不出现：不进画面，也不说话。拷贝图案拷当前图，并问怎么进出画面。",
            allow_empty=True,
            on_confirm=chosen,
            ask_motion=True,
            actor_entry=actor_entry,
            parent=win,
            host_only=parent is not None,
        )

    def _scene_actor_defined(self, scene: dict) -> bool:
        for row in project_manager.actor_entries(scene.get("actor") or ""):
            body = (row.get("body") or "").strip()
            if body and not project_manager.actor_is_absent(body):
                return True
        return False

    def _ensure_default_actor(self, scene: dict) -> None:
        """人物名单是空的时候，放上第一个讲员，后面的文字都归 <1>。"""
        if self._scene_actor_defined(scene):
            return
        names = self._span_voice_names()
        voice = names[0] if names else "woman/mature/chinese"
        scene["actor"] = f"讲员：{voice}"


# verbatim references to WorkflowGUI.<attr> in the methods above resolve to this mixin
WorkflowGUI = ActorsMixin
