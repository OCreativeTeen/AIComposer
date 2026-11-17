"""STORY 预览窗的人物栏：和魔法工作流右侧「本场内容」的人物栏同一种用法。

- 每个讲员 / 人物是一枚小卡片（chip），按住左右拖可以换顺序。
- 双击卡片：预览 / 修改（讲员从音色表里选；人物填 性别/年龄段/民族/名字），可贴图作为形象。
- 双击空白处：加一个讲员或人物。
- 卡片获得焦点后按 Ctrl+V：把剪贴板里的图存成这一位的形象图。Delete：删掉这一位（点一下卡片选中，再按 Delete；编辑窗里没有删除按钮）。
- t280: 单击 = 只选这一枚；Ctrl+单击 = 加选 / 取消选（选中的卡片蓝底）。Delete 删掉所有选中的（先问一次）；讲员也可以删。
  「人物合并」（在「动态生成人物」下面）：选了 2 个以上人物才能按；讲员不参加合并。
- t280: 人物预览窗里「生成肖像」：Strata 按所有场景里这一位的描述 + 地域 / 时代 / 舞台写提示词，Grok 文生图（utility/portrait_gen）。

名单用和场景 ``actor`` 字段相同的文字格式（t280 新写法：``H xxx | woman/mature/chinese/封氏``；旧的 讲员： / 人物N： 照样认），
解析 / 拼写都走 project_manager 里现成的函数，所以和工作流里的名单完全一样。
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
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


# t279: 人物栏 = 整个故事的名单：最多 10 个人物 + 1 个讲员（每一场的 actor 还是最多 4 个人）。
# 两行，每行 5 个人物；讲员（H）在最左边单独一格、占两行。卡片上的编号只是显示：人物N → N，讲员 → H。
CHIPS_PER_ROW = 5
CHIP_ROWS = 2
REF_WIDTH = 1000  # 量字宽时按人物栏 1000px 宽算（还没摆出来 / 测试里）
CHIP_EXTRA_PX = 28  # 一枚卡片除了字以外占的宽：字两边 6+6、标签自己的边 3+3、卡片边框 1+1、焦点框 2+2、卡片之间 2+2
ROW_MARGIN_PX = 8  # 人物栏框子自己的边，留一点
HOST_TEXT_MAX_PX = 120  # 讲员那一格的字最多这么宽


def chip_text(row: dict) -> str:
    """t279: 卡片上的完整文字：``1 贾雨村（man/mature/chinese）``、``H <讲员>``（编号只是显示；t280: 存的文字是新写法，讲员 ``H …``，人物不带标签）。"""
    body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
    sid = project_manager.actor_display_id(row)
    if row.get("role") == "host":
        return f"H {body}" if body else "H"
    parts = [p for p in body.split("/") if p]
    name = parts[3] if len(parts) >= 4 else ""
    look = "/".join(parts[:3]) if parts else body
    head = f"{sid} " if sid else ""
    return f"{head}{name}（{look}）" if name else f"{head.strip()}（{look}）"


def fit_text(text: str, font, max_px: int) -> str:
    """量字宽：放不下就从后面截掉，末尾写 ``..``。"""
    text = text or ""
    if max_px <= 0 or font.measure(text) <= max_px:
        return text
    while text and font.measure(text + "..") > max_px:
        text = text[:-1]
    return text + ".."


def person_text_px(total_px: int, host_px: int = 0) -> int:
    """一行 5 个人物时，每枚人物卡片里的字最多多宽（总宽减去讲员那一格，平分成 5 份，再减掉卡片自己的边）。"""
    return max(30, int((max(total_px, 200) - host_px - ROW_MARGIN_PX) / CHIPS_PER_ROW) - CHIP_EXTRA_PX)


def cast_rows(actor_text: str, max_present: int = project_manager.CAST_MAX_PRESENT) -> list:
    """名单文字 → ``[{role, label, body}]``，去掉「不出现」的讲员。t279: 最多 10 个人物 + 1 个讲员。"""
    rows = []
    for row in project_manager.actor_entries(actor_text or "", max_present, project_manager.CAST_MAX_PEOPLE):
        body = (row.get("body") or "").strip()
        if not body or project_manager.actor_is_absent(body):
            continue
        rows.append(row)
    return rows


class StoryActorPanel(ttk.Frame):
    """人物栏。``get_text()`` / ``set_text()`` 读写名单；名单变了调用 ``on_change(text)``。

    ``person_dir``：可调用，返回人物形象图目录（有项目时用项目 avatar，没有时用 AVATAR_PATH/story）。
    ``style``：可调用，返回当前画面风格（找讲员形象图用）。
    ``channel_path``：可调用，返回频道目录 program/<频道>（t444u：翻候选肖像先用它的 avatar/<风格>/）。
    """

    # t279: 名单最多留几个人：10 个人物 + 1 个讲员（动态 / 不动态一样）。
    max_present = project_manager.CAST_MAX_PRESENT

    def __init__(self, master, *, text: str = "", on_change=None, person_dir=None, style=None,
                 on_row_edit=None, on_row_delete=None, on_reorder=None, channel_path=None, max_present=None,
                 on_merge=None, portrait_context=None):
        super().__init__(master)
        # t280: 人物合并：on_merge(选中的行（第一个选中的在前）, 新的 性别/年龄/族裔/名字) 改所有场景；
        # portrait_context() -> {"scenes": [...], "setting": "...", "style": "..."}（生成肖像用）
        self._on_merge = on_merge
        self._portrait_context = portrait_context
        self._selected: list = []  # 选中的卡片，按选的先后
        self._merge_btn = None
        if max_present:
            self.max_present = int(max_present)
        # 改 / 删一个演员时通知外面（STORY 预览：同步改所有场景的 actor / speaking）
        self._on_row_edit = on_row_edit
        self._on_row_delete = on_row_delete
        self._on_reorder = on_reorder
        self._text = self._normalize(text)
        self._on_change = on_change
        self._person_dir = person_dir
        self._style = style
        self._channel_path = channel_path
        self._chips: list = []
        self._drag_index = None
        self._drag_moved = False
        self._drag_x = 0
        self._skip_release = False
        self._tip_win = None
        self._fit_width = 0
        self.row = tk.Frame(self, bg="#f4f4f4", relief="groove", bd=1)
        self.row.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.row.bind("<Double-Button-1>", lambda _e: self._add_actor())
        self.row.bind("<Configure>", self._on_row_resize, add="+")
        # t279: 两行（每行 5 个人物），框子一直是两行高；讲员在第 0 列，人物在第 1–5 列平分
        line_h = self._chip_height()
        for r in range(CHIP_ROWS):
            self.row.grid_rowconfigure(r, minsize=line_h)
        for c in range(1, CHIPS_PER_ROW + 1):
            self.row.grid_columnconfigure(c, weight=1, uniform="cast_chip")
        self._render()

    # ---------- 名单 ----------
    def get_text(self) -> str:
        return self._text

    def _normalize(self, text: str) -> str:
        return project_manager.normalize_actor_text(text or "", self.max_present, project_manager.CAST_MAX_PEOPLE)

    def set_text(self, text: str, *, notify: bool = True) -> None:
        self._text = self._normalize(text)
        self._render()
        if notify and callable(self._on_change):
            try:
                self._on_change(self._text)
            except Exception as exc:  # noqa: BLE001
                print(f"人物栏：保存名单失败 {exc}")

    def host_name(self) -> str:
        for row in cast_rows(self._text, self.max_present):
            if row.get("role") == "host":
                return project_manager.split_actor_motion(row.get("body") or "")[0]
        return ""

    def _rows_from_chips(self) -> list:
        return [dict(getattr(c, "_actor_entry", {}) or {}) for c in self._chips]

    # ---------- 卡片 ----------
    def _render(self) -> None:
        self._tip(None, False)
        for child in self.row.winfo_children():
            child.destroy()
        self._chips = []
        self._selected = []
        self._update_merge_btn()
        rows = cast_rows(self._text, self.max_present)
        if not rows:
            hint = tk.Label(self.row, text="（没有人物：双击这里添加讲员 / 人物）", bg="#f4f4f4", fg="#777")
            hint.grid(row=0, column=0, columnspan=CHIPS_PER_ROW + 1, sticky="w", padx=6, pady=2)
            hint.bind("<Double-Button-1>", lambda _e: self._add_actor())
            return
        for row in rows:
            self._pack_chip(row)
        self._layout_chips()

    @staticmethod
    def _chip_text(row: dict) -> str:
        return chip_text(row)

    def _chip_height(self) -> int:
        try:
            return tkfont.nametofont("TkDefaultFont").metrics("linespace") + 12
        except tk.TclError:
            return 26

    def _avail_width(self) -> int:
        try:
            width = int(self.row.winfo_width())
        except tk.TclError:
            width = 0
        return width if width > 200 else REF_WIDTH

    def _layout_chips(self) -> None:
        """t279: 讲员在第 0 列占两行；人物按顺序排成两行，每行 5 个（第 1–5 列）；字放不下就截成 ``..``。"""
        for chip in self._chips:
            chip.grid_forget()
        persons = [c for c in self._chips if c._actor_entry.get("role") != "host"]
        host = next((c for c in self._chips if c._actor_entry.get("role") == "host"), None)
        if host is not None:
            host.grid(row=0, column=0, rowspan=CHIP_ROWS, sticky="nsw", padx=(2, 2), pady=2)
        for j, chip in enumerate(persons):
            chip.grid(row=j // CHIPS_PER_ROW, column=1 + j % CHIPS_PER_ROW, sticky="w", padx=(2, 2), pady=2)
        self._fit_labels()

    def _fit_labels(self) -> None:
        width = self._avail_width()
        self._fit_width = width
        host = next((c for c in self._chips if c._actor_entry.get("role") == "host"), None)
        host_px = 0
        try:
            if host is not None:
                font = tkfont.Font(font=host._actor_text_label.cget("font"))
                host_px = min(font.measure(host._actor_full), HOST_TEXT_MAX_PX) + CHIP_EXTRA_PX
            for chip in self._chips:
                label = chip._actor_text_label
                font = tkfont.Font(font=label.cget("font"))
                limit = HOST_TEXT_MAX_PX if chip is host else person_text_px(width, host_px)
                text = fit_text(chip._actor_full, font, limit)
                if label.cget("text") != text:
                    label.configure(text=text)
        except tk.TclError:
            pass

    def _on_row_resize(self, _event=None) -> None:
        width = self._avail_width()
        if abs(width - self._fit_width) > 8:
            self._fit_labels()

    def _tip(self, chip, show: bool) -> None:
        """t279: 卡片上的字被截了时，鼠标放上去显示完整文字。"""
        win = getattr(self, "_tip_win", None)
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass
            self._tip_win = None
        if not show or chip is None:
            return
        try:
            if chip._actor_text_label.cget("text") == chip._actor_full:
                return
            win = tk.Toplevel(chip)
            win.wm_overrideredirect(True)
            tk.Label(win, text=chip._actor_full, bg="#ffffe0", relief="solid", bd=1,
                     wraplength=520, justify=tk.LEFT).pack()
            win.wm_geometry(f"+{chip.winfo_rootx()}+{chip.winfo_rooty() + chip.winfo_height() + 2}")
            self._tip_win = win
        except tk.TclError:
            pass

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
        chip._actor_full = text
        chip._actor_text_label = label
        for widget in (chip, label):
            widget.bind("<Enter>", lambda _e, c=chip: self._tip(c, True), add="+")
            widget.bind("<Leave>", lambda _e, c=chip: self._tip(c, False), add="+")
        for widget in (chip, label):
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<Control-Button-1>", self._ctrl_press)  # t280: Ctrl+单击 加选 / 取消选
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)
            widget.bind("<Double-Button-1>", self._double)
        chip.bind("<FocusIn>", lambda _e, c=chip, l=label: self._focus(c, l, True))
        chip.bind("<FocusOut>", lambda _e, c=chip, l=label: self._focus(c, l, False))
        chip.bind("<Delete>", lambda _e, c=chip: self._delete_selected(c))
        chip.bind("<BackSpace>", lambda _e, c=chip: self._delete_selected(c))
        chip.bind("<Control-v>", lambda _e, c=chip: self._paste_to_chip(c))
        chip.bind("<Control-V>", lambda _e, c=chip: self._paste_to_chip(c))
        self._chips.append(chip)

    @staticmethod
    def _focus(chip, label, on: bool) -> None:
        """t280: 焦点只画边框；蓝底表示「选中」（_paint）。"""
        try:
            chip.configure(highlightbackground="#1a73e8" if on else "white")
        except tk.TclError:
            pass

    # ---------- t280: 选中（单击 / Ctrl+单击） ----------
    SELECT_BG = "#9fc5ff"

    def _paint(self) -> None:
        for chip in self._chips:
            bg = self.SELECT_BG if chip in self._selected else "white"
            try:
                chip.configure(bg=bg)
                chip._actor_text_label.configure(bg=bg)
            except tk.TclError:
                pass

    def _select(self, chips) -> None:
        self._selected = [c for c in chips if c in self._chips]
        self._paint()
        self._update_merge_btn()

    def selected_indexes(self) -> list:
        """选中的卡片在名单里的位置（按选的先后）。"""
        return [self._chips.index(c) for c in self._selected if c in self._chips]

    def _ctrl_press(self, event) -> str:
        chip = self._chip_of(event.widget)
        if chip is None or chip not in self._chips:
            return "break"
        sel = list(self._selected)
        if chip in sel:
            sel.remove(chip)
        else:
            sel.append(chip)
        self._select(sel)
        try:
            chip.focus_set()
        except tk.TclError:
            pass
        self._drag_index = None
        self._drag_moved = False
        return "break"

    def _merge_indexes(self) -> list:
        rows = self._rows_from_chips()
        return [i for i in self.selected_indexes() if i < len(rows) and rows[i].get("role") != "host"]

    def can_merge(self) -> bool:
        return len(self._merge_indexes()) >= 2

    def attach_merge_button(self, btn) -> None:
        """「人物合并」按钮：选了 2 个以上人物才能按。"""
        self._merge_btn = btn
        self._update_merge_btn()

    def _update_merge_btn(self) -> None:
        btn = getattr(self, "_merge_btn", None)
        if btn is None:
            return
        try:
            btn.state(["!disabled"] if self.can_merge() else ["disabled"])
        except (tk.TclError, AttributeError):
            pass

    def merge_selected(self):
        """打开合并窗（按「人物合并」）。返回窗口（测试用）；不能合并返回 None。"""
        idx = self._merge_indexes()
        if len(idx) < 2:
            messagebox.showinfo("人物合并", "先选 2 个以上人物（单击选一个，Ctrl+单击加选）。讲员不参加合并。", parent=self)
            return None
        rows = self._rows_from_chips()
        return CastMergeDialog(self, [rows[i] for i in idx], on_done=lambda body, ix=tuple(idx): self._apply_merge(list(ix), body))

    def _apply_merge(self, indexes: list, body: str) -> None:
        from utility import cast_merge

        rows = self._rows_from_chips()
        body = (body or "").strip()
        if not body or len(indexes) < 2:
            return
        # 名单里已经有一个和新名字一样的人（没选上）：也并进来，免得出现两个同样的人
        new_key = cast_merge.default_key({"role": "person", "body": body})
        for i, r in enumerate(rows):
            if i not in indexes and r.get("role") != "host" and cast_merge.default_key(r) == new_key:
                indexes = indexes + [i]
        picked = [dict(rows[i]) for i in indexes]
        self._merge_assets(picked, body)  # t281: 肖像和声音也并过来
        if callable(self._on_merge):
            try:
                self._on_merge(picked, body)
            except Exception as exc:  # noqa: BLE001
                print(f"人物栏：合并时同步场景失败 {exc}")
        self.set_text(project_manager.format_actor_entries(cast_merge.merge_cast_rows(rows, indexes, body)))

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
            if chip in self._chips:
                self._select([chip])  # t280: 单击 = 只选这一枚
        self._drag_index = self._chips.index(chip) if chip in self._chips else None
        if chip is not None and chip in self._chips and chip._actor_entry.get("role") == "host":
            self._drag_index = None  # t279: 讲员固定在最左那一格，不拖
        self._drag_moved = False
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _motion(self, event) -> None:
        src = self._drag_index
        if src is None or src >= len(self._chips):
            return
        if not self._drag_moved and max(abs(event.x_root - self._drag_x),
                                        abs(event.y_root - getattr(self, "_drag_y", event.y_root))) < 6:
            return
        best, target = None, None
        for i, chip in enumerate(self._chips):  # t279: 两行，按到卡片中心的距离（横竖都算）找最近的人物
            if chip._actor_entry.get("role") == "host":
                continue
            cx = chip.winfo_rootx() + max(chip.winfo_width(), 1) / 2
            cy = chip.winfo_rooty() + max(chip.winfo_height(), 1) / 2
            dist = (event.x_root - cx) ** 2 + (event.y_root - cy) ** 2
            if best is None or dist < best:
                best, target = dist, i
        if target is None or target == src:
            return
        self._drag_moved = True
        self._chips.insert(target, self._chips.pop(src))
        self._drag_index = target
        self._layout_chips()

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

    def _merge_assets(self, picked: list, body: str) -> dict:
        """t281: 合并时肖像 / 声音也并：留第一个选中的人的，他没有就用后面第一个有的；
        别的肖像改名 .bakN 备份（不删）；声音表里旧的记录留着，只给合并后的人记上。"""
        from utility import cast_merge

        out = {}
        try:
            out["portrait"] = cast_merge.merge_portrait_files(
                [self.portrait_path(r) for r in picked], self.portrait_dest({"role": "person", "body": body}))
        except Exception as exc:  # noqa: BLE001
            print(f"人物合并：肖像没有并好 {exc}")
        try:
            out["voice"] = cast_merge.merge_voice_settings(
                project_manager.PROJECT_CONFIG, [r.get("body") for r in picked], body)
            if out["voice"].get("changed"):
                project_manager.save_project_config(parent=self.winfo_toplevel())
        except Exception as exc:  # noqa: BLE001
            print(f"人物合并：声音没有并好 {exc}")
        return out

    def _delete_chip(self, chip) -> str:
        """删一枚（旧入口）：等于只选它再删。"""
        if chip not in self._chips:
            return "break"
        self._select([chip])
        return self._delete_selected(chip)

    def _delete_selected(self, chip=None) -> str:
        """t280: Delete：删掉所有选中的卡片（讲员也可以删），先问一次。"""
        sel = [c for c in self._selected if c in self._chips]
        if chip is not None and chip in self._chips and chip not in sel:
            sel = [chip]
        if not sel:
            return "break"
        rows = self._rows_from_chips()
        idx = sorted(self._chips.index(c) for c in sel)
        who = "、".join(f"「{self._chip_text(rows[i])}」" for i in idx)
        if messagebox.askyesno("人物", f"从名单里删掉{who}吗？（所有场景里的这些人和他们的台词也会去掉）", parent=self):
            for i in idx:
                self._notify_row("delete", rows[i])
            from utility.cast_merge import remove_cast_rows

            self.set_text(project_manager.format_actor_entries(remove_cast_rows(rows, idx)))
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
    def portrait_context(self) -> dict:
        """t280: 生成肖像用：{"scenes", "setting", "style"}（外面没给就只有风格）。"""
        ctx = {}
        if callable(self._portrait_context):
            try:
                ctx = dict(self._portrait_context() or {})
            except Exception as exc:  # noqa: BLE001
                print(f"人物栏：读场景失败 {exc}")
                ctx = {}
        ctx.setdefault("scenes", [])
        ctx.setdefault("setting", "")
        if not ctx.get("style"):
            ctx["style"] = self._style_now()
        return ctx

    def _style_now(self) -> str:
        try:
            return (self._style() if callable(self._style) else "") or ""
        except Exception:  # noqa: BLE001
            return ""

    def channel_avatar_dir(self) -> str:
        """频道自己的 avatar 目录（program/<频道>/avatar）；不知道频道返回 ""。"""
        from utility.portrait_candidates import channel_avatar_dir

        try:
            path = self._channel_path() if callable(self._channel_path) else (self._channel_path or "")
        except Exception:  # noqa: BLE001
            path = ""
        return channel_avatar_dir(path or "")

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

    def library_dest(self, row: dict) -> str:
        """t281: 「生成肖像」存的地方 = 频道的肖像库 program/<频道>/avatar/<画面风格>/<性别_年龄_族裔_名字>.png
        （左右键翻的候选就从这里读；风格文件夹名按已有的对上，不分大小写，没有就新建）。
        不知道频道时存进通用库 D:\\AI_MEDIA\\avatar\\<画面风格>\\。"""
        from utility.portrait_candidates import match_style_folder

        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        stem = portrait_stem(body)
        if not stem:
            return ""
        token = config.visual_style_token(self._style_now()) or ""
        root = self.channel_avatar_dir() or config.AVATAR_PATH
        folder = (match_style_folder(root, token) or token) if token else ""
        return os.path.join(root, folder, stem + ".png") if folder else os.path.join(root, stem + ".png")

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
        cap = project_manager.CAST_MAX_PEOPLE  # t279: 人物栏最多 10 个人物（讲员另算，只有 1 个）
        kept, n_person = [], 0
        for r in rows:
            if r.get("role") != "host":
                n_person += 1
                if n_person > cap:
                    continue
            kept.append(r)
        if len(kept) != len(rows):
            rows = kept
            messagebox.showinfo(
                "人物", f"人物栏最多 {cap} 个人物（讲员另算），多出来的没有加。一场的画面里还是最多 4 个人。", parent=self)
        self.set_text(project_manager.format_actor_entries(rows))


class CastMergeDialog(tk.Toplevel):
    """t280: 人物合并窗：性别 / 年龄段 / 族裔 三个下拉 + 名字（按第一个选中的人预填）。确定 = on_done(新的 id)；取消什么都不做。"""

    def __init__(self, panel, rows: list, *, on_done):
        super().__init__(panel.winfo_toplevel())
        self.panel = panel
        self.on_done = on_done
        self.title("人物合并")
        self.transient(panel.winfo_toplevel())
        self.resizable(False, False)
        first = (rows[0].get("body") if rows else "") or ""
        g, a, e, n = self.prefill(first)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        names = "\n".join("· " + chip_text(r) for r in rows)
        ttk.Label(frm, text="把这些人合并成一个人（所有场景都改成这一位）：", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(frm, text=names, justify=tk.LEFT, foreground="#333").pack(anchor="w", pady=(4, 8))
        grid = ttk.Frame(frm)
        grid.pack(anchor="w")
        self.gender_var = tk.StringVar(value=g)
        self.age_var = tk.StringVar(value=a)
        self.eth_var = tk.StringVar(value=e)
        self.name_var = tk.StringVar(value=n)
        for col, (lbl, var, vals) in enumerate((("性别", self.gender_var, GENDERS), ("年龄段", self.age_var, AGES),
                                                ("族裔", self.eth_var, ETHNICITIES))):
            ttk.Label(grid, text=lbl).grid(row=0, column=col, sticky="w", padx=(0, 6))
            ttk.Combobox(grid, textvariable=var, values=vals, width=11, state="readonly").grid(
                row=1, column=col, sticky="w", padx=(0, 6))
        ttk.Label(grid, text="名字").grid(row=0, column=3, sticky="w")
        self.name_entry = ttk.Entry(grid, textvariable=self.name_var, width=18)
        self.name_entry.grid(row=1, column=3, sticky="w")
        ttk.Label(frm, text="合并后放在第一个选中的人的位置；每一场原来的括号说明保留。", foreground="#555").pack(anchor="w", pady=(8, 0))
        btns = ttk.Frame(frm)
        btns.pack(pady=(10, 0))
        ttk.Button(btns, text="确定", command=self._ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=6)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.name_entry.focus_set()

    @staticmethod
    def prefill(body: str) -> tuple:
        """``woman/mature/chinese/名字（…）`` → (性别, 年龄段, 族裔, 名字)；不认识的用默认值。"""
        from utility.cast_merge import split_id

        base = project_manager.split_actor_motion((body or "").strip())[0]
        parts = [p.strip() for p in base.split("/")]
        parsed = split_id(base)
        g = parts[0] if parts and parts[0] in GENDERS else (parsed.get("gender") if parsed.get("gender") in GENDERS else "woman")
        a = parts[1] if len(parts) > 1 and parts[1] in AGES else (parsed.get("age") if parsed.get("age") in AGES else "mature")
        e = parts[2] if len(parts) > 2 and parts[2] in ETHNICITIES else (parsed.get("eth") if parsed.get("eth") in ETHNICITIES else "chinese")
        n = parts[3] if len(parts) > 3 and parts[3] else (parsed.get("name") or "")
        return g, a, e, n

    def body(self) -> str:
        name = (self.name_var.get() or "").replace("|", "").replace("/", "").strip()
        return f"{self.gender_var.get()}/{self.age_var.get()}/{self.eth_var.get()}/{name}" if name else ""

    def _ok(self) -> None:
        body = self.body()
        if not body:
            messagebox.showwarning("人物合并", "先填名字。", parent=self)
            return
        self.destroy()
        self.on_done(body)


class ActorEditDialog(tk.Toplevel):
    """一位讲员 / 人物的预览与修改。t443u: 和魔法工作流的「人物」窗同一套部件（gui/actor_portrait_widgets）：
    最上面是大图；性别 / 年龄 / 民族 / 名字，下一行括号描述（可写）；声音。
    左右键不换人：人物翻 D:\\AI_MEDIA\\avatar\\<画面风格>\\ 里的图，「用这张」或确认 = 设为这一位的形象图。"""

    def __init__(self, panel: StoryActorPanel, row, *, allow_host: bool, on_done):
        from gui.actor_portrait_widgets import PersonEditBlock, PortraitBrowser, focus_in_text_field

        super().__init__(panel.winfo_toplevel())
        self.panel = panel
        self.on_done = on_done
        self.is_new = row is None
        row = row or {"role": "person", "body": "woman/mature/chinese"}
        self._opened = dict(row)
        self.title("新增人物" if self.is_new else "人物")
        self.transient(panel.winfo_toplevel())
        self.resizable(True, True)
        self.minsize(660, 820)

        full = (row.get("body") or "").strip()
        body = project_manager.split_actor_motion(full)[0]
        self.role_var = tk.StringVar(value=row.get("role") or "person")
        self.host_var = tk.StringVar(value=body if row.get("role") == "host" else "")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        # 图在最上面，占满宽度
        self.img_lbl = tk.Label(frm, text="（没有形象图）\nCtrl+V 贴图", bg="#eee", relief="sunken")
        self.img_lbl.pack(fill=tk.X, pady=(0, 2))
        self.caption_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.caption_var, foreground="#555", wraplength=620).pack(pady=(0, 4))
        self.browser = PortraitBrowser(self.img_lbl, self.caption_var, size=(560, 600))
        self.title_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.title_var, font=("TkDefaultFont", 12, "bold")).pack(pady=(2, 6))

        role_row = ttk.Frame(frm)
        role_row.pack(pady=(0, 6))
        rb_host = ttk.Radiobutton(role_row, text="讲员", value="host", variable=self.role_var, command=self._sync)
        rb_host.pack(side=tk.LEFT)
        ttk.Radiobutton(role_row, text="人物", value="person", variable=self.role_var, command=self._sync).pack(side=tk.LEFT, padx=(8, 0))
        if not allow_host and self.role_var.get() != "host":
            rb_host.state(["disabled"])

        self.host_frm = ttk.Frame(frm)
        ttk.Label(self.host_frm, text="讲员（音色表）").pack(side=tk.LEFT, padx=(0, 6))
        opts = [x for x in config.narrator_person_options() if (x or "").strip()]
        if self.host_var.get() and self.host_var.get() not in opts:
            opts = [self.host_var.get()] + opts
        if not self.host_var.get() and opts:
            self.host_var.set(opts[0])
        host_combo = ttk.Combobox(self.host_frm, textvariable=self.host_var, values=opts, width=30)
        host_combo.pack(side=tk.LEFT)
        host_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_fields())

        self.person_frm = PersonEditBlock(frm)
        self.person_frm.fill(full if row.get("role") != "host" else "woman/mature/chinese")
        self.person_frm.on_change(self._on_fields)

        self.voice_var = tk.StringVar()
        self.voice_frm = ttk.Frame(frm)
        ttk.Label(self.voice_frm, text="声音").pack(side=tk.LEFT, padx=(0, 8))
        self.voice_box = ttk.Combobox(self.voice_frm, textvariable=self.voice_var, values=(), width=18, state="readonly")
        self.voice_box.pack(side=tk.LEFT)

        self.hint_var = tk.StringVar()
        self.hint_lbl = ttk.Label(frm, textvariable=self.hint_var, wraplength=620, foreground="#555")

        self.btns = ttk.Frame(frm)
        ttk.Button(self.btns, text="贴图 (Ctrl+V)", command=self._paste).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(self.btns, text="用这张", command=self._use_picked).pack(side=tk.LEFT, padx=(0, 6))
        self.gen_btn = ttk.Button(self.btns, text="生成肖像", command=self._gen_portrait)  # t280
        self.gen_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(self.btns, text="确认", command=self._ok).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(self.btns, text="取消", command=self.destroy).pack(side=tk.LEFT)

        self.img_lbl.bind("<Button-1>", lambda _e: self.browser.step(1))
        self.img_lbl.bind("<Button-3>", lambda _e: self.browser.step(-1))
        self.bind("<Left>", lambda _e: None if focus_in_text_field(self) else self._step(-1))
        self.bind("<Right>", lambda _e: None if focus_in_text_field(self) else self._step(1))
        self.bind("<Control-v>", lambda _e: self._paste())
        self.bind("<Control-V>", lambda _e: self._paste())
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._ident = None
        self._sync()
        self.grab_set()
        self.focus_set()

    def _step(self, delta: int) -> str:
        self.browser.step(delta)  # 没有候选图就什么都不做
        return "break"

    def _row(self) -> dict:
        if self.role_var.get() == "host":
            return {"role": "host", "label": "讲员", "body": (self.host_var.get() or "").strip()}
        from utility.actor_edit_fields import actor_paren_is_motion, parse_actor_edit_fields

        body = self.person_frm.body().replace("|", "")
        if self._opened.get("role") != "host":
            _base, orig = project_manager.split_actor_motion((self._opened.get("body") or "").strip())
            if body and actor_paren_is_motion(orig) and not parse_actor_edit_fields(body)["note"]:
                body = project_manager._with_actor_motion(project_manager.split_actor_motion(body)[0], orig)
        return {"role": "person", "label": "人物", "body": body}

    def _sync(self) -> None:
        for w in (self.host_frm, self.person_frm, self.voice_frm, self.hint_lbl, self.btns):
            w.pack_forget()
        if self.role_var.get() == "host":
            self.host_frm.pack(pady=(0, 6))
            self.hint_var.set("讲员的形象在 D:\\AI_MEDIA\\avatar\\<风格>\\ 里按音色表名字固定；Ctrl+V 可以换图。")
        else:
            self.person_frm.pack(pady=(0, 6))
            self.hint_var.set("左右键翻 D:\\AI_MEDIA\\avatar\\<画面风格>\\ 里的图（不换人），「用这张」或确认 = 设为这一位的形象图；"
                              "原来的改名 .bak 备份。Ctrl+V 贴图。括号描述写进人物名单。")
        self.voice_frm.pack(pady=(4, 6))
        self.hint_lbl.pack(pady=(0, 6))
        self.btns.pack(pady=(4, 0))
        self._ident = None
        self._on_fields()

    def _on_fields(self) -> None:
        row = self._row()
        self.title_var.set(row.get("body") or "")
        ident = (row["role"], project_manager.split_actor_motion(row.get("body") or "")[0])
        if ident == self._ident:
            return  # 只改括号描述：不重翻图、不重置声音
        self._ident = ident
        self._refresh_voice()
        self._show_portrait()

    def _candidates(self, row: dict) -> tuple:
        if row.get("role") == "host":
            return [], ""
        from utility.portrait_candidates import library_candidates

        token = config.visual_style_token(self.panel._style_now())
        own = self.panel.portrait_path(row)
        paths, label = library_candidates(config.AVATAR_PATH, token, row.get("body") or "",
                                          channel_root=self.panel.channel_avatar_dir())
        own_key = os.path.normcase(os.path.abspath(own)) if own else ""
        return [p for p in paths if os.path.normcase(os.path.abspath(p)) != own_key], label

    def _show_portrait(self) -> None:
        row = self._row()
        cands, label = self._candidates(row)
        self.browser.reset(self.panel.portrait_path(row), cands, label,
                           empty_text="（没有形象图）  ← → 翻图库 / Ctrl+V 贴图")

    def _use_picked(self) -> bool:
        src = self.browser.picked()
        row = self._row()
        if not src or row.get("role") == "host":
            return False
        dest = self.panel.portrait_dest(row)
        if not dest:
            messagebox.showwarning("形象图", "先填好这一位的名字 / 样子。", parent=self)
            return False
        from utility.portrait_candidates import apply_portrait_choice

        try:
            apply_portrait_choice(src, dest)
        except OSError as exc:
            messagebox.showerror("形象图", f"设为形象图失败：{exc}", parent=self)
            return False
        self._ident = None
        self._show_portrait()
        return True

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

    def show_candidate(self, path: str) -> None:
        """t281: 大图翻到 path 这张候选（刚生成的肖像）；候选里没有就放在最前面。"""
        if not path or not os.path.isfile(path):
            return
        key = os.path.normcase(os.path.abspath(path))
        items = list(self.browser.items)
        k = next((i for i, p in enumerate(items) if os.path.normcase(os.path.abspath(p)) == key), -1)
        if k < 0:
            items.insert(0, path)
            k = 0
        self.browser.items = items
        self.browser.pos = k
        self.browser.show()

    def _paste(self) -> str:
        if self.panel.paste_portrait(self._row(), parent=self):
            self._show_portrait()
        return "break"

    def _gen_portrait(self, *, runner=None) -> None:
        """t280: 生成肖像：Strata 写提示词（所有场景里这一位的描述 + 地域 / 时代 / 舞台 + 风格）→ Grok 文生图
        → 存成这一位的形象图（原来的 .bak 备份）→ 显示。讲员不用（讲员形象按音色表）。"""
        row = self._row()
        if row.get("role") == "host":
            messagebox.showinfo("生成肖像", "讲员的形象按音色表固定，不生成。", parent=self)
            return
        body = project_manager.split_actor_motion((row.get("body") or "").strip())[0]
        dest = self.panel.library_dest(row)  # t281: 存进频道肖像库（当前画面风格），左右键能翻到
        if not body or len([b for b in body.split("/") if b.strip()]) < 4 or not dest:
            messagebox.showwarning("生成肖像", "先填好 性别 / 年龄 / 族裔 / 名字。", parent=self)
            return
        from utility import portrait_gen

        ctx = self.panel.portrait_context()
        try:
            self.gen_btn.state(["disabled"])
        except tk.TclError:
            pass
        self.hint_var.set("生成肖像：Strata 写提示词 → Grok 出图（手动窗口里可以贴图）…")

        def job():
            return portrait_gen.generate_portrait(body, ctx.get("scenes") or [], dest,
                                                  setting=ctx.get("setting") or "", style=ctx.get("style") or "",
                                                  ratio=ctx.get("ratio") or "")

        def done(res):
            try:
                if not self.winfo_exists():
                    return
                self.gen_btn.state(["!disabled"])
            except tk.TclError:
                return
            if res.get("ok"):
                self._ident = None
                self._show_portrait()
                self.show_candidate(res.get("path") or "")
                self.hint_var.set(f"已生成肖像，存进频道肖像库：{res.get('path')}。"
                                  "「用这张」或确认 = 设为这一位的肖像。")
            else:
                self.hint_var.set("")
                messagebox.showwarning("生成肖像", res.get("error") or "没有生成。", parent=self)

        (runner or portrait_gen.run_in_background)(self, job, done)

    def _ok(self) -> None:
        row = self._row()
        if not (row.get("body") or "").strip():
            messagebox.showwarning("人物", "先选 / 填好这一位。", parent=self)
            return
        self._use_picked()  # t443u: 正在看图库里的候选图 → 先设为这一位的形象图
        self._save_voice(row)
        self.destroy()
        self.on_done(row)
