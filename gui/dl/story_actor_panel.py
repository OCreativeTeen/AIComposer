"""STORY 预览窗的人物栏：和魔法工作流右侧「本场内容」的人物栏同一种用法。

- 每个讲员 / 人物是一枚小卡片（chip），按住左右拖可以换顺序。
- 双击卡片：预览 / 修改（讲员从音色表里选；人物填 性别/年龄段/民族/名字），可贴图作为形象。
- 双击空白处：加一个讲员或人物。
- 卡片获得焦点后按 Ctrl+V：把剪贴板里的图存成这一位的形象图。Delete：删掉这一位（点一下卡片选中，再按 Delete；编辑窗里没有删除按钮）。

名单用和场景 ``actor`` 字段相同的文字格式（``讲员：xxx | 人物1：woman/mature/chinese/封氏``），
解析 / 拼写都走 project_manager 里现成的函数，所以和工作流里的名单完全一样。
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox

import config
import project_manager

GENDERS = ["woman", "man", "girl", "boy"]
AGES = ["kids", "youth", "teenager", "mature", "senior"]
ETHNICITIES = ["chinese", "english"]


def portrait_stem(name: str) -> str:
    """同 ``wf_actors._portrait_stem``：/ 换成 _，去掉文件名不允许的字符。"""
    stem = (name or "").strip().replace("\\", "/").replace("/", "_")
    for ch in '<>:"|?*':
        stem = stem.replace(ch, "_")
    return stem.strip(" .")


def cast_rows(actor_text: str) -> list:
    """名单文字 → ``[{role, label, body}]``，去掉「不出现」的讲员。"""
    rows = []
    for row in project_manager.actor_entries(actor_text or ""):
        body = (row.get("body") or "").strip()
        if not body or project_manager.actor_is_absent(body):
            continue
        rows.append(row)
    return rows


class StoryActorPanel(ttk.Frame):
    """人物栏。``get_text()`` / ``set_text()`` 读写名单；名单变了调用 ``on_change(text)``。

    ``person_dir``：可调用，返回人物形象图目录（有项目时用项目 avatar，没有时用 AVATAR_PATH/story）。
    ``style``：可调用，返回当前画面风格（找讲员形象图用）。
    """

    def __init__(self, master, *, text: str = "", on_change=None, person_dir=None, style=None,
                 on_row_edit=None, on_row_delete=None, on_reorder=None):
        super().__init__(master)
        # 改 / 删一个演员时通知外面（STORY 预览：同步改所有场景的 actor / speaking）
        self._on_row_edit = on_row_edit
        self._on_row_delete = on_row_delete
        self._on_reorder = on_reorder
        self._text = project_manager.normalize_actor_text(text or "")
        self._on_change = on_change
        self._person_dir = person_dir
        self._style = style
        self._chips: list = []
        self._drag_index = None
        self._drag_moved = False
        self._drag_x = 0
        self._skip_release = False
        self.row = tk.Frame(self, bg="#f4f4f4", relief="groove", bd=1, height=28)
        self.row.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.row.bind("<Double-Button-1>", lambda _e: self._add_actor())
        self._render()

    # ---------- 名单 ----------
    def get_text(self) -> str:
        return self._text

    def set_text(self, text: str, *, notify: bool = True) -> None:
        self._text = project_manager.normalize_actor_text(text or "")
        self._render()
        if notify and callable(self._on_change):
            try:
                self._on_change(self._text)
            except Exception as exc:  # noqa: BLE001
                print(f"人物栏：保存名单失败 {exc}")

    def host_name(self) -> str:
        for row in cast_rows(self._text):
            if row.get("role") == "host":
                return project_manager.split_actor_motion(row.get("body") or "")[0]
        return ""

    def _rows_from_chips(self) -> list:
        return [dict(getattr(c, "_actor_entry", {}) or {}) for c in self._chips]

    # ---------- 卡片 ----------
    def _render(self) -> None:
        for child in self.row.winfo_children():
            child.destroy()
        self._chips = []
        rows = cast_rows(self._text)
        if not rows:
            hint = tk.Label(self.row, text="（没有人物：双击这里添加讲员 / 人物）", bg="#f4f4f4", fg="#777")
            hint.pack(side=tk.LEFT, padx=6, pady=2)
            hint.bind("<Double-Button-1>", lambda _e: self._add_actor())
            return
        for row in rows:
            self._pack_chip(row)

    @staticmethod
    def _chip_text(row: dict) -> str:
        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        if row.get("role") == "host":
            return f"讲员 {body}" if body else "讲员"
        parts = [p for p in body.split("/") if p]
        name = parts[3] if len(parts) >= 4 else ""
        look = "/".join(parts[:3]) if parts else body
        label = row.get("label") or "人物"
        return f"{label} {name}（{look}）" if name else f"{label}（{look}）"

    def _pack_chip(self, row: dict) -> None:
        text = self._chip_text(row)
        chip = tk.Frame(
            self.row, bg="white", relief="sunken", bd=1, cursor="fleur", takefocus=1,
            highlightthickness=2, highlightbackground="white", highlightcolor="#1a73e8",
        )
        fg = "#0b5394" if row.get("role") == "host" else "black"
        label = tk.Label(chip, text=text, bg="white", fg=fg, cursor="fleur", anchor="w")
        label.pack(fill=tk.BOTH, expand=True, padx=6, pady=1)
        chip._actor_entry = dict(row)
        chip.pack(side=tk.LEFT, padx=(2, 2), pady=2)
        for widget in (chip, label):
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)
            widget.bind("<Double-Button-1>", self._double)
        chip.bind("<FocusIn>", lambda _e, c=chip, l=label: self._focus(c, l, True))
        chip.bind("<FocusOut>", lambda _e, c=chip, l=label: self._focus(c, l, False))
        chip.bind("<Delete>", lambda _e, c=chip: self._delete_chip(c))
        chip.bind("<BackSpace>", lambda _e, c=chip: self._delete_chip(c))
        chip.bind("<Control-v>", lambda _e, c=chip: self._paste_to_chip(c))
        chip.bind("<Control-V>", lambda _e, c=chip: self._paste_to_chip(c))
        self._chips.append(chip)

    @staticmethod
    def _focus(chip, label, on: bool) -> None:
        bg = "#9fc5ff" if on else "white"
        try:
            chip.configure(bg=bg, highlightbackground="#1a73e8" if on else "white")
            label.configure(bg=bg)
        except tk.TclError:
            pass

    def _chip_of(self, widget):
        while widget is not None and widget not in self._chips:
            widget = getattr(widget, "master", None)
        return widget

    def _press(self, event) -> None:
        chip = self._chip_of(event.widget)
        if chip is not None:
            try:
                chip.focus_set()
            except tk.TclError:
                pass
        self._drag_index = self._chips.index(chip) if chip in self._chips else None
        self._drag_moved = False
        self._drag_x = event.x_root

    def _motion(self, event) -> None:
        src = self._drag_index
        if src is None or src >= len(self._chips):
            return
        if not self._drag_moved and abs(event.x_root - self._drag_x) < 6:
            return
        best, target = None, None
        for i, chip in enumerate(self._chips):
            center = chip.winfo_rootx() + max(chip.winfo_width(), 1) / 2
            dist = abs(event.x_root - center)
            if best is None or dist < best:
                best, target = dist, i
        if target is None or target == src:
            return
        self._drag_moved = True
        self._chips.insert(target, self._chips.pop(src))
        self._drag_index = target
        for chip in self._chips:
            chip.pack_forget()
        for chip in self._chips:
            chip.pack(side=tk.LEFT, padx=(2, 2), pady=2)

    def _release(self, _event) -> None:
        moved = self._drag_moved
        self._drag_index = None
        self._drag_moved = False
        if self._skip_release:
            self._skip_release = False
            return
        if moved:
            if callable(self._on_reorder):
                try:
                    self._on_reorder([dict(r) for r in self._rows_from_chips()])
                except Exception as exc:  # noqa: BLE001
                    print(f"演员栏：同步场景顺序失败 {exc}")
            # 人物在新顺序里重新编号，讲员留在被放到的位置。
            self.set_text(project_manager.format_actor_entries(self._rows_from_chips()))

    def _double(self, event) -> str:
        self._skip_release = True
        chip = self._chip_of(event.widget)
        if chip is not None:
            self._edit_actor(self._chips.index(chip))
        return "break"

    def _delete_chip(self, chip) -> str:
        if chip not in self._chips:
            return "break"
        idx = self._chips.index(chip)
        rows = self._rows_from_chips()
        who = self._chip_text(rows[idx])
        if messagebox.askyesno("人物", f"从名单里删掉「{who}」吗？", parent=self):
            self._notify_row("delete", rows[idx])
            rows.pop(idx)
            self.set_text(project_manager.format_actor_entries(rows))
        return "break"

    def _notify_row(self, what: str, old_row: dict, new_row: dict | None = None) -> None:
        cb = self._on_row_edit if what == "edit" else self._on_row_delete
        if not callable(cb):
            return
        try:
            cb(dict(old_row), dict(new_row)) if what == "edit" else cb(dict(old_row))
        except Exception as exc:  # noqa: BLE001
            print(f"演员栏：同步场景失败 {exc}")

    # ---------- 形象图 ----------
    def _style_now(self) -> str:
        try:
            return (self._style() if callable(self._style) else "") or ""
        except Exception:  # noqa: BLE001
            return ""

    def _person_folder(self) -> str:
        folder = ""
        if callable(self._person_dir):
            try:
                folder = self._person_dir() or ""
            except Exception:  # noqa: BLE001
                folder = ""
        return folder or os.path.join(config.AVATAR_PATH, "story")

    def portrait_path(self, row: dict) -> str:
        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        if not body or project_manager.actor_is_absent(body):
            return ""
        if row.get("role") == "host":
            names = [body]
            bits = [p for p in body.split("/") if p]
            if len(bits) >= 3:
                names.append("/".join(bits[:3]))
            try:
                return config.find_avatar_png([portrait_stem(n) for n in names], self._style_now()) or ""
            except Exception:  # noqa: BLE001
                return ""
        return config.find_image_by_stem(self._person_folder(), portrait_stem(body)) or ""

    def portrait_dest(self, row: dict) -> str:
        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        stem = portrait_stem(body)
        if not stem:
            return ""
        if row.get("role") == "host":
            folder = config.avatar_style_dest_dir(self._style_now())
        else:
            folder = self._person_folder()
        return os.path.join(folder, stem + ".png")

    def paste_portrait(self, row: dict, parent=None) -> bool:
        """剪贴板里的图存成这一位的形象图。原来有图先改名备份（同 wf_actors）。"""
        from PIL import Image, ImageGrab

        parent = parent or self
        dest = self.portrait_dest(row)
        if not dest:
            messagebox.showwarning("形象图", "先填好这一位的名字 / 样子。", parent=parent)
            return False
        clip = ImageGrab.grabclipboard()
        if isinstance(clip, list):
            src = next((p for p in clip if p and os.path.isfile(p)), "")
            clip = Image.open(src) if src else None
        if clip is None:
            messagebox.showwarning("形象图", "剪贴板里没有图片。", parent=parent)
            return False
        try:
            img = clip if clip.mode in ("RGB", "RGBA") else clip.convert("RGBA")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.isfile(dest):
                stem, ext = os.path.splitext(dest)
                n = 1
                while os.path.exists(f"{stem}.bak{n}{ext}"):
                    n += 1
                os.replace(dest, f"{stem}.bak{n}{ext}")
            img.save(dest, "PNG")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("形象图", f"保存失败：{exc}", parent=parent)
            return False
        return True

    def _paste_to_chip(self, chip) -> str:
        if chip in self._chips:
            row = self._rows_from_chips()[self._chips.index(chip)]
            if self.paste_portrait(row):
                messagebox.showinfo("形象图", f"已保存：{self._chip_text(row)}", parent=self)
        return "break"

    # ---------- 新增 / 修改 ----------
    def _add_actor(self) -> None:
        self._edit_actor(None)

    def _edit_actor(self, index) -> None:
        rows = self._rows_from_chips()
        row = dict(rows[index]) if index is not None and index < len(rows) else None
        has_host = any(r.get("role") == "host" for i, r in enumerate(rows) if i != index)
        ActorEditDialog(self, row, allow_host=not has_host, on_done=lambda new, i=index: self._apply_edit(i, new))

    def _apply_edit(self, index, new_row) -> None:
        rows = self._rows_from_chips()
        if new_row is None:  # 删除
            if index is not None and index < len(rows):
                self._notify_row("delete", rows[index])
                rows.pop(index)
        elif index is None:
            if new_row.get("role") == "host":
                rows.insert(0, new_row)  # 讲员默认放在第 1 位（主持 / 讲述人）
            else:
                rows.append(new_row)
        else:
            self._notify_row("edit", rows[index], new_row)
            rows[index] = new_row
        if len(rows) > 4:
            messagebox.showinfo("人物", "一场最多四个人（含讲员），多出来的不会进画面。", parent=self)
        self.set_text(project_manager.format_actor_entries(rows))


class ActorEditDialog(tk.Toplevel):
    """一位讲员 / 人物的预览与修改：样子、名字、形象图（Ctrl+V 贴图）。"""

    def __init__(self, panel: StoryActorPanel, row, *, allow_host: bool, on_done):
        super().__init__(panel.winfo_toplevel())
        self.panel = panel
        self.on_done = on_done
        self.is_new = row is None
        row = row or {"role": "person", "body": "woman/mature/chinese"}
        self.title("新增人物" if self.is_new else "人物")
        self.transient(panel.winfo_toplevel())
        self.resizable(False, False)
        self._photo = None

        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        parts = [p for p in body.split("/") if p]
        self.role_var = tk.StringVar(value=row.get("role") or "person")
        self.host_var = tk.StringVar(value=body if row.get("role") == "host" else "")
        self.gender_var = tk.StringVar(value=parts[0] if len(parts) > 0 else "woman")
        self.age_var = tk.StringVar(value=parts[1] if len(parts) > 1 else "mature")
        self.eth_var = tk.StringVar(value=parts[2] if len(parts) > 2 else "chinese")
        self.name_var = tk.StringVar(value="/".join(parts[3:]) if len(parts) > 3 else "")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(frm)
        left.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N)
        role_row = ttk.Frame(left)
        role_row.pack(anchor=tk.W, pady=(0, 6))
        rb_host = ttk.Radiobutton(role_row, text="讲员", value="host", variable=self.role_var, command=self._sync)
        rb_host.pack(side=tk.LEFT)
        ttk.Radiobutton(role_row, text="人物", value="person", variable=self.role_var, command=self._sync).pack(side=tk.LEFT, padx=(8, 0))
        if not allow_host and self.role_var.get() != "host":
            rb_host.state(["disabled"])

        self.host_frm = ttk.Frame(left)
        ttk.Label(self.host_frm, text="讲员（音色表）").pack(anchor=tk.W)
        opts = [x for x in config.narrator_person_options() if (x or "").strip()]
        if self.host_var.get() and self.host_var.get() not in opts:
            opts = [self.host_var.get()] + opts
        if not self.host_var.get() and opts:
            self.host_var.set(opts[0])
        host_combo = ttk.Combobox(self.host_frm, textvariable=self.host_var, values=opts, width=30)
        host_combo.pack(anchor=tk.W)
        host_combo.bind("<<ComboboxSelected>>", lambda _e: self._show_portrait())

        self.person_frm = ttk.Frame(left)
        for lbl, var, vals in (("性别", self.gender_var, GENDERS), ("年龄段", self.age_var, AGES), ("民族", self.eth_var, ETHNICITIES)):
            r = ttk.Frame(self.person_frm)
            r.pack(anchor=tk.W, pady=1)
            ttk.Label(r, text=lbl, width=6).pack(side=tk.LEFT)
            cb = ttk.Combobox(r, textvariable=var, values=vals, width=14)
            cb.pack(side=tk.LEFT)
            cb.bind("<<ComboboxSelected>>", lambda _e: self._show_portrait())
        r = ttk.Frame(self.person_frm)
        r.pack(anchor=tk.W, pady=1)
        ttk.Label(r, text="名字", width=6).pack(side=tk.LEFT)
        name_entry = ttk.Entry(r, textvariable=self.name_var, width=16)
        name_entry.pack(side=tk.LEFT)
        name_entry.bind("<FocusOut>", lambda _e: self._show_portrait())
        ttk.Label(self.person_frm, text="例：woman/mature/chinese/封氏", foreground="#777").pack(anchor=tk.W, pady=(2, 0))

        self.voice_var = tk.StringVar()
        self.voice_frm = ttk.Frame(left)
        ttk.Label(self.voice_frm, text="\u58f0\u97f3", width=6).pack(side=tk.LEFT)
        self.voice_box = ttk.Combobox(self.voice_frm, textvariable=self.voice_var, values=(), width=14, state="readonly")
        self.voice_box.pack(side=tk.LEFT)
        for w in (host_combo,):
            w.bind("<<ComboboxSelected>>", lambda _e: (self._show_portrait(), self._refresh_voice()), add="+")
        for child in self.person_frm.winfo_children():
            for cb in child.winfo_children():
                if isinstance(cb, ttk.Combobox):
                    cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_voice(), add="+")

        btns = ttk.Frame(left)
        btns.pack(side=tk.BOTTOM, anchor=tk.W, pady=(10, 0))
        ttk.Button(btns, text="贴图 (Ctrl+V)", command=self._paste).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btns, text="确认", command=self._ok).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.LEFT)

        self.img_lbl = tk.Label(frm, text="（没有形象图）\nCtrl+V 贴图", width=24, height=12, bg="#eee", relief="sunken")
        self.img_lbl.pack(side=tk.LEFT, padx=(12, 0))
        self.bind("<Control-v>", lambda _e: self._paste())
        self.bind("<Control-V>", lambda _e: self._paste())
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._sync()
        self.grab_set()

    def _row(self) -> dict:
        if self.role_var.get() == "host":
            return {"role": "host", "label": "讲员", "body": (self.host_var.get() or "").strip()}
        bits = [self.gender_var.get(), self.age_var.get(), self.eth_var.get()]
        bits = [(b or "").strip() for b in bits]
        name = (self.name_var.get() or "").strip().replace("|", "").replace("/", "")
        body = "/".join(b for b in bits if b) + (f"/{name}" if name else "")
        return {"role": "person", "label": "人物", "body": body}

    def _sync(self) -> None:
        if self.role_var.get() == "host":
            self.person_frm.pack_forget()
            self.host_frm.pack(anchor=tk.W)
        else:
            self.host_frm.pack_forget()
            self.person_frm.pack(anchor=tk.W)
        self.voice_frm.pack_forget()
        self.voice_frm.pack(anchor=tk.W, pady=(4, 0))
        self._refresh_voice()
        self._show_portrait()

    def _refresh_voice(self) -> None:
        """t95u: \u58f0\u97f3\u4e0b\u62c9:\u7528\u6237\u9009\u5b9a\u4f18\u5148,\u5426\u5219\u6309\u6027\u522b/\u5e74\u9f84/\u65cf\u88d4\u9ed8\u8ba4\u3002"""
        import config_prompt

        row = self._row()
        opts = tuple(config_prompt.voice_choices_for_actor(row.get("body") or ""))
        self.voice_box.configure(values=opts)
        cur = self.voice_var.get()
        if cur not in opts:
            self.voice_var.set(config_prompt.chosen_actor_voice(row.get("body") or "", row["role"]) if opts else "")

    def _save_voice(self, row: dict) -> None:
        import config_prompt

        voice = (self.voice_var.get() or "").strip()
        pc = project_manager.PROJECT_CONFIG
        if not voice or not isinstance(pc, dict):
            return
        key = config_prompt.actor_voice_storage_key(row.get("body") or "", row["role"])
        if not key:
            return
        table = pc.get("actor_voices")
        if not isinstance(table, dict):
            table = {}
            pc["actor_voices"] = table
        if table.get(key) == voice:
            return
        table[key] = voice
        try:
            project_manager.save_project_config(parent=self.panel.winfo_toplevel())
        except Exception:  # noqa: BLE001
            pass

    def _show_portrait(self) -> None:
        path = self.panel.portrait_path(self._row())
        if not path:
            self._photo = None
            self.img_lbl.configure(image="", text="（没有形象图）\nCtrl+V 贴图", width=24, height=12)
            return
        try:
            from PIL import Image, ImageTk

            img = Image.open(path)
            img.thumbnail((220, 260))
            self._photo = ImageTk.PhotoImage(img)
            self.img_lbl.configure(image=self._photo, text="", width=img.width, height=img.height)
        except Exception:  # noqa: BLE001
            self.img_lbl.configure(image="", text=os.path.basename(path))

    def _paste(self) -> str:
        if self.panel.paste_portrait(self._row(), parent=self):
            self._show_portrait()
        return "break"

    def _ok(self) -> None:
        row = self._row()
        if not (row.get("body") or "").strip():
            messagebox.showwarning("人物", "先选 / 填好这一位。", parent=self)
            return
        self._save_voice(row)
        self.destroy()
        self.on_done(row)
