"""program clipboard store + manager window (moved verbatim from gui/downloader.py)."""
import os
import json
import glob
import config
from datetime import datetime
from utility.file_util import write_json
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext


PROGRAM_CLIPBOARD_JSON_NAME = "program_clipboard.json"


LEGACY_CHANNEL_CLIPBOARD_JSON_NAME = "channel_clipboard.json"


_program_clipboard_manager_window: "ChannelClipboardManagerWindow | None" = None


def _program_clipboard_file() -> str:
    path = (getattr(config, "PROGRAM_CLIPBOARD_JSON", "") or "").strip()
    if path:
        return path
    root = (getattr(config, "BASE_AIAGENT_PATH", "") or "").strip()
    if not root:
        root = os.path.join(config.BASE_MEDIA_PATH or "/AI_MEDIA", "aiagent")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, PROGRAM_CLIPBOARD_JSON_NAME)


def _merge_legacy_clipboard_file_into_items(
    fp: str,
    items: list,
    seen: set,
    *,
    ch_name: str = "",
) -> None:
    try:
        with open(fp, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except Exception:
        return
    if not isinstance(legacy, dict):
        return
    for it in legacy.get("items") or []:
        if not isinstance(it, dict):
            continue
        eid = str(it.get("id") or "").strip()
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)
        src = (it.get("source") or "").strip()
        if ch_name and src and not src.startswith(ch_name + ":"):
            it = dict(it)
            it["source"] = f"{ch_name}:{src}"[:80]
        elif ch_name and not src:
            it = dict(it)
            it["source"] = ch_name[:80]
        items.append(it)


def _migrate_legacy_channel_clipboards(data: dict) -> dict:
    """一次性合并各频道子目录下旧剪贴板 JSON 到 ``aiagent/program_clipboard.json``。"""
    if not isinstance(data, dict):
        data = {"items": []}
    items = data.setdefault("items", [])
    seen = {str(x.get("id", "")) for x in items if isinstance(x, dict) and x.get("id")}
    root = (config.BASE_PROGRAM_PATH or "").strip()
    if not root:
        root = os.path.join(config.BASE_MEDIA_PATH or "/AI_MEDIA", "program")
    global_path = os.path.normcase(_program_clipboard_file())
    if root and os.path.isdir(root):
        if not data.get("_migrated_channel_clipboards_v1"):
            pattern = os.path.join(root, "*", LEGACY_CHANNEL_CLIPBOARD_JSON_NAME)
            for fp in glob.glob(pattern):
                ch_name = os.path.basename(os.path.dirname(fp))
                _merge_legacy_clipboard_file_into_items(fp, items, seen, ch_name=ch_name)
            data["_migrated_channel_clipboards_v1"] = True
        if not data.get("_migrated_channel_program_clipboards_v1"):
            pattern2 = os.path.join(root, "*", PROGRAM_CLIPBOARD_JSON_NAME)
            for fp in glob.glob(pattern2):
                if os.path.normcase(fp) == global_path:
                    continue
                ch_name = os.path.basename(os.path.dirname(fp))
                _merge_legacy_clipboard_file_into_items(fp, items, seen, ch_name=ch_name)
            data["_migrated_channel_program_clipboards_v1"] = True
    return data


def _load_program_clipboard_data() -> dict:
    path = _program_clipboard_file()
    if not os.path.isfile(path):
        data = {"items": []}
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"items": []}
    if not isinstance(data, dict):
        data = {"items": []}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    need_save = not (
        data.get("_migrated_channel_clipboards_v1")
        and data.get("_migrated_channel_program_clipboards_v1")
    )
    data = _migrate_legacy_channel_clipboards(data)
    items = data.get("items", [])
    if isinstance(items, list):
        deduped = _dedupe_program_clipboard_items_by_preview(items)
        if len(deduped) != len(items):
            data["items"] = deduped
            _save_program_clipboard_data(data)
    if need_save and data.get("_migrated_channel_clipboards_v1"):
        _save_program_clipboard_data(data)
    return data


def _save_program_clipboard_data(data: dict) -> None:
    write_json(_program_clipboard_file(), data)


def _program_clipboard_preview_key(item: dict) -> str:
    """用于去重的 preview 键（相同 preview 视为重复条目）。"""
    pv = (item.get("preview") or "").strip()
    if pv:
        return pv
    content = (item.get("content") or "").strip()
    return content[:64] if content else ""


def _dedupe_program_clipboard_items_by_preview(items: list) -> list:
    """相同 preview 只保留最新一条（列表靠后的条目）。"""
    kept: list = []
    seen: set[str] = set()
    for it in reversed(items):
        if not isinstance(it, dict):
            continue
        key = _program_clipboard_preview_key(it)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(it)
    kept.reverse()
    return kept


def _program_clipboard_make_id(existing: set) -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = base
    n = 0
    while uid in existing:
        n += 1
        uid = f"{base}_{n}"
    return uid


def _program_clipboard_source_label(channel_path: str, source: str) -> str:
    src = (source or "").strip()
    ch = (channel_path or "").strip()
    if ch:
        ch_tag = os.path.basename(os.path.normpath(ch))
        if ch_tag and src and not src.startswith(ch_tag + ":"):
            return f"{ch_tag}:{src}"[:80]
        if ch_tag and not src:
            return ch_tag[:80]
    return src[:80]


def program_clipboard_append_item(content: str, source: str, *, channel_path: str = "") -> str:
    """追加一条到 ``program`` 根目录 JSON 剪贴板（全频道共享），返回条目 id。

    相同 ``preview`` 已存在则不再追加，返回已有条目 id。
    """
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
    data = _load_program_clipboard_data()
    items = data.setdefault("items", [])
    new_preview = text[:64]
    for it in items:
        if isinstance(it, dict) and _program_clipboard_preview_key(it) == new_preview:
            return str(it.get("id") or "")
    existing = {str(x.get("id", "")) for x in items if isinstance(x, dict)}
    eid = _program_clipboard_make_id(existing)
    items.append(
        {
            "id": eid,
            "preview": new_preview,
            "content": text,
            "source": _program_clipboard_source_label(channel_path, source),
        }
    )
    _save_program_clipboard_data(data)
    return eid


def channel_clipboard_append_item(channel_path: str, content: str, source: str) -> str:
    """兼容旧名：写入全局 program 剪贴板；``channel_path`` 仅用于 ``source`` 标注频道。"""
    return program_clipboard_append_item(content, source, channel_path=channel_path)


class ChannelClipboardManagerWindow(tk.Toplevel):
    """全 program JSON 剪贴板：↑↓ 选择；Enter 默认复制到系统剪贴板并弹窗，或 on_pick 时仅回调；Delete 删项；Ctrl+Delete 清空。"""

    def __init__(
        self,
        parent,
        clipboard_host,
        *,
        select_last: bool = False,
        on_pick=None,
    ):
        super().__init__(parent)
        self.clipboard_host = clipboard_host
        self.on_pick = on_pick
        self.title("全频道剪贴板")
        self.geometry("920x460")
        self.minsize(640, 280)
        self._json_path = _program_clipboard_file()

        fr = ttk.Frame(self, padding=10)
        fr.pack(fill=tk.BOTH, expand=True)
        ttk.Label(fr, text=f"文件: {self._json_path}", font=("Consolas", 8), wraplength=880).pack(
            anchor=tk.W, pady=(0, 4)
        )
        self._hint_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self._hint_var, wraplength=880, justify=tk.LEFT).pack(anchor=tk.W)
        self.listbox = tk.Listbox(fr, height=18, width=110, font=("Consolas", 9), exportselection=False)
        sb = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        row = ttk.Frame(fr)
        row.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        bf = ttk.Frame(fr)
        bf.pack(fill=tk.X)
        self._activate_btn = ttk.Button(bf, text="复制并查看 (Enter)", command=self._on_activate)
        self._activate_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="刷新列表", command=lambda: self.refresh(select_last=False)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="关闭", command=self.destroy).pack(side=tk.RIGHT)

        self._items: list = []
        self._sync_pick_ui()
        self.refresh(select_last=select_last)

        self.listbox.bind("<Return>", self._on_return)
        self.listbox.bind("<KP_Enter>", self._on_return)
        self.listbox.bind("<Delete>", self._on_delete_one)
        self.bind("<Control-Delete>", self._on_clear_all)
        self.listbox.bind("<Double-Button-1>", lambda e: self._on_activate())

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.listbox.focus_set()


    def _sync_pick_ui(self):
        if self.on_pick is not None:
            self._hint_var.set(
                "↑↓ 选择 · Enter 将所选内容填入导向说明（无预览、不写系统剪贴板）· Delete 删除当前项 · Ctrl+Delete 清空全部"
            )
            self._activate_btn.configure(text="填入导向说明 (Enter)")
        else:
            self._hint_var.set(
                "↑↓ 选择 · Enter 复制到系统剪贴板并查看全文 · Delete 删除当前项 · Ctrl+Delete 清空全部"
            )
            self._activate_btn.configure(text="复制并查看 (Enter)")
    def refresh(self, select_last: bool = False):
        self.listbox.delete(0, tk.END)
        data = _load_program_clipboard_data()
        raw = data.get("items", [])
        self._items = _dedupe_program_clipboard_items_by_preview(
            [x for x in raw if isinstance(x, dict)]
        )
        for it in self._items:
            eid = it.get("id", "")
            src = (it.get("source") or "")[:16]
            pv = (it.get("preview") or "")[:72].replace("\n", " ")
            self.listbox.insert(tk.END, f"[{src}] {eid}  {pv}")
        if not self._items:
            return
        if select_last:
            i = len(self._items) - 1
        else:
            i = 0
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(i)
        self.listbox.activate(i)
        self.listbox.see(i)

    def _paste_to_system_clipboard(self, text: str) -> None:
        for w in (self.clipboard_host, self.winfo_toplevel()):
            if w is None:
                continue
            try:
                w.clipboard_clear()
                w.clipboard_append(text)
                w.update_idletasks()
                return
            except tk.TclError:
                continue

    def _on_return(self, event=None):
        self._on_activate()
        return "break"

    def _on_activate(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(self._items):
            return
        content = self._items[i].get("content", "") or ""
        if self.on_pick is not None:
            try:
                self.on_pick(content)
            except Exception:
                pass
            return
        self._paste_to_system_clipboard(content)
        self._popup_content_view(content)

    def _popup_content_view(self, content: str):
        top = tk.Toplevel(self)
        top.title("剪贴板条目 · 全文")
        top.geometry("820x560")
        top.transient(self)
        tx = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=98, height=28, font=("Consolas", 10))
        tx.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tx.insert("1.0", content)
        tx.configure(state=tk.DISABLED)
        bf = ttk.Frame(top)
        bf.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(bf, text="确定", command=top.destroy).pack(side=tk.RIGHT, padx=8)

    def _on_delete_one(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(self._items):
            return
        rm_id = self._items[i].get("id")
        data = _load_program_clipboard_data()
        data["items"] = [x for x in data.get("items", []) if isinstance(x, dict) and x.get("id") != rm_id]
        _save_program_clipboard_data(data)
        next_idx = max(0, i - 1)
        self.refresh(select_last=False)
        if self.listbox.size() > 0:
            next_idx = min(next_idx, self.listbox.size() - 1)
            self.listbox.selection_set(next_idx)
            self.listbox.activate(next_idx)
            self.listbox.see(next_idx)
        return "break"

    def _on_clear_all(self, event=None):
        if not messagebox.askyesno(
            "清空程序剪贴板",
            "确定删除 program 根目录 JSON 剪贴板中的全部条目？\n（所有频道共享，将一并清空。）",
            parent=self,
        ):
            return
        data = _load_program_clipboard_data()
        data["items"] = []
        _save_program_clipboard_data(data)
        self.refresh(select_last=False)
        return "break"
