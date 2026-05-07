"""
选择对话框模块

提供通用的选择对话框功能
"""

import os
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.messagebox as messagebox
from typing import Callable, Optional


def _askchoice_normalize_pairs(choices):
    """将 choices 规范为 [(return_value, button_label), ...]。
    支持 str（返回值与按钮文案相同）或 (value, label) 二元组。
    """
    pairs = []
    for c in choices:
        if isinstance(c, (tuple, list)) and len(c) >= 2:
            pairs.append((c[0], str(c[1])))
        else:
            s = str(c)
            pairs.append((s, s))
    return pairs


def askchoice(title, choices, parent=None):
    """每个选项一个按钮，点击即选并关闭；点「取消」返回 None。

    choices:
      - list[str]：按钮文案与返回值均为该字符串
      - list[tuple]：每项 (return_value, button_label)，按钮显示 label，返回时 value 为 return_value

    返回:
      - None：用户取消
      - (label, value)：label 为按钮上显示的文案；value 为对应返回值（纯 str 选项时二者相同）
    """
    if not choices:
        return None

    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None

    pairs = _askchoice_normalize_pairs(choices)
    num_choices = len(pairs)
    max_label_len = max(len(lbl) for _, lbl in pairs)

    dialog = tk.Toplevel(parent)
    dialog.title(title[:80] + ("…" if len(title) > 80 else ""))

    button_height = 36
    title_height = 72
    cancel_height = 52
    padding = 24
    calculated_height = title_height + (num_choices * button_height) + cancel_height + padding
    min_height = 220

    dialog.update_idletasks()
    if parent:
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
    else:
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

    max_height = int(screen_height * 0.85)
    dialog_height = max(min_height, min(calculated_height, max_height))
    # 长英文标签时加宽窗口；按钮 width 为字符数
    dialog_width = min(920, max(360, 48 + int(min(max_label_len, 100) * 7.0)))

    dialog.resizable(False, False)

    if parent:
        dialog.transient(parent)
    dialog.grab_set()

    x = (screen_width // 2) - (dialog_width // 2)
    y = (screen_height // 2) - (dialog_height // 2)
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    result = None

    def on_choice(val, lbl: str):
        nonlocal result
        result = (lbl, val)
        dialog.destroy()

    main = ttk.Frame(dialog, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    label = ttk.Label(
        main,
        text=title,
        font=("Arial", 12, "bold"),
        wraplength=dialog_width - 40,
        justify=tk.CENTER,
    )
    label.pack(pady=(8, 12))

    btn_char_w = min(100, max(25, min(max_label_len + 2, 95)))

    for val, lbl in pairs:
        ttk.Button(
            main,
            text=lbl,
            width=btn_char_w,
            command=lambda v=val, lb=lbl: on_choice(v, lb),
        ).pack(pady=4, fill=tk.X)

    ttk.Button(main, text="取消", width=min(btn_char_w, 28), command=dialog.destroy).pack(pady=(14, 6))

    dialog.wait_window()
    return result


def pack_text_buttons(parent, rows, cancel=None, width=48):
    """自上而下排列 ttk 按钮；用于「一点即执行」的自定义对话框（如讲话拷贝）。

    rows: [(label, command), ...]
    cancel: None 或 (label, command)，置于最下方并加大上边距。
    返回所有按钮控件列表（含取消），便于统一 disable 等。
    """
    buttons = []
    for label, cmd in rows:
        b = ttk.Button(parent, text=label, width=width, command=cmd)
        b.pack(fill=tk.X, pady=2)
        buttons.append(b)
    if cancel is not None:
        cl, cc = cancel
        b = ttk.Button(parent, text=cl, width=width, command=cc)
        b.pack(fill=tk.X, pady=(8, 0))
        buttons.append(b)
    return buttons


def ask_speaking_concise_review_dialog(
    parent,
    original_content: str,
    remix_fn: Callable[[str], str],
    *,
    title: str = "审阅文案",
) -> Optional[str]:
    """弹窗：只读「原文」+ 可编辑定稿区；「Remix」对当前编辑区全文调用 ``remix_fn``；「确定」返回定稿（用于 $$$/@@@ 同一正文）。

    remix_fn: 接受当前编辑文本，返回 LLM 摘要结果（调用方负责 ``chinese_convert`` 等）。
    取消返回 None。
    """
    result: list[Optional[str]] = [None]

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(True, True)

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        main,
        text="原文（只读参考）",
        font=("Arial", 10, "bold"),
    ).pack(anchor=tk.W)
    orig_w = scrolledtext.ScrolledText(
        main,
        wrap=tk.WORD,
        height=7,
        width=72,
        font=("Arial", 10),
        state=tk.DISABLED,
        background="#f5f5f5",
    )
    orig_w.pack(fill=tk.BOTH, expand=False, pady=(2, 8))
    orig_w.config(state=tk.NORMAL)
    orig_w.insert("1.0", original_content or "")
    orig_w.config(state=tk.DISABLED)

    ttk.Label(
        main,
        text="定稿（可手工修改；Remix 基于当前编辑区全文重新摘要）",
        font=("Arial", 10, "bold"),
    ).pack(anchor=tk.W)
    edit_w = scrolledtext.ScrolledText(
        main,
        wrap=tk.WORD,
        height=10,
        width=72,
        font=("Arial", 10),
    )
    edit_w.pack(fill=tk.BOTH, expand=True, pady=(2, 8))
    edit_w.insert("1.0", original_content or "")

    btn_bar = ttk.Frame(main)
    btn_bar.pack(fill=tk.X, pady=(4, 0))

    def reset_from_original() -> None:
        edit_w.delete("1.0", tk.END)
        edit_w.insert("1.0", original_content or "")

    def do_remix() -> None:
        raw = original_content #edit_w.get("1.0", tk.END)
        try:
            out = remix_fn(raw)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Remix 失败", str(e), parent=dlg)
            return
        edit_w.delete("1.0", tk.END)
        edit_w.insert("1.0", (out or "").strip())

    def on_ok() -> None:
        text = edit_w.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("审阅", "定稿正文不能为空。", parent=dlg)
            return
        result[0] = text
        dlg.destroy()

    def on_cancel() -> None:
        dlg.destroy()

    ttk.Button(btn_bar, text="还原原文", command=reset_from_original).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_bar, text="Remix(LLM)", command=do_remix).pack(side=tk.LEFT, padx=(0, 6))

    btn_row2 = ttk.Frame(main)
    btn_row2.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(btn_row2, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row2, text="确定", command=on_ok).pack(side=tk.RIGHT)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.update_idletasks()
    w_m, h_m = 720, min(640, dlg.winfo_reqheight() + 20)
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"{w_m}x{h_m}+{(sw - w_m) // 2}+{(sh - h_m) // 2}")
    dlg.wait_window()
    return result[0]


def post_nested_clipboard_menu(root, choices_dict, speaker, content, event, max_label_len=72):
    if not choices_dict:
        return "break"

    def _menu_label(s: str) -> str:
        t = (s or "").strip()
        if len(t) <= max_label_len:
            return t
        return t[: max_label_len - 1] + "…"

    def _copy(text: str) -> None:
        try:
            root.clipboard_clear()
            if content:
                if "$$$" in text:
                    text = text.replace("$$$", content)

                if speaker:
                    text = text.replace("###", speaker)
                else:
                    text = text.replace("###", "")
            root.clipboard_append(text)
            root.update_idletasks()
        except tk.TclError:
            pass

    m = tk.Menu(root, tearoff=0)
    for cn_key, items in choices_dict.items():
        sub = tk.Menu(m, tearoff=0)
        for text in items:
            sub.add_command(
                label=_menu_label(text),
                command=lambda t=text: _copy(t),
            )
        m.add_cascade(label=cn_key, menu=sub)
    try:
        if event is not None:
            m.post(event.x_root, event.y_root)
        else:
            m.post(root.winfo_rootx() + 40, root.winfo_rooty() + 40)
    except tk.TclError:
        pass
    return "break"


def _get_media_duration_sec(file_path):
    """返回视频时长（秒），无法读取或非视频则返回 None。"""
    try:
        import cv2
        lower = file_path.lower()
        if not lower.endswith((".mp4", ".avi", ".mov", ".webm", ".mkv")):
            return None
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        if fps and fps > 0 and n and n > 0:
            return float(n / fps)
    except Exception:
        pass
    return None


def _format_duration(sec):
    if sec is None:
        return "—"
    if sec < 0:
        return "—"
    if sec < 60:
        return f"{sec:.1f}s"
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m}:{s:04.1f}"


def _load_preview_image(file_path, max_w=320, max_h=240):
    """从视频或图片文件加载预览图，返回可显示的 PhotoImage 或 None"""
    try:
        import cv2
        from PIL import Image, ImageTk
        lower = file_path.lower()
        frame = None
        if lower.endswith(('.mp4', '.avi', '.mov', '.webm', '.mkv')):
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
            if frame is None:
                return None
        elif lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
            frame = cv2.imread(file_path)
            if frame is None:
                return None
        else:
            return None
        h, w = frame.shape[:2]
        if w > max_w or h > max_h:
            scale = min(max_w / w, max_h / h)
            nw, nh = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        return ImageTk.PhotoImage(pil_img)
    except Exception:
        return None


def askchoice_media_preview(title, choices, folder_path, parent=None):
    """
    带预览的媒体选择对话框（支持 mp4 与图片）。
    左侧为文件列表，右侧为选中文件的预览图。
    choices: 文件名列表；folder_path: 文件所在目录。
    返回选中的文件名，取消返回 None。
    """
    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None

    if not choices:
        return None

    dialog = tk.Toplevel(parent)
    dialog.title(title)

    # 窗口尺寸：左侧列表 + 右侧预览
    dialog_width = 560
    dialog_height = 450
    dialog.geometry(f"{dialog_width}x{dialog_height}")
    dialog.resizable(True, True)

    if parent:
        dialog.transient(parent)
    dialog.grab_set()

    # 居中
    dialog.update_idletasks()
    if parent:
        x = (parent.winfo_screenwidth() - dialog_width) // 2
        y = (parent.winfo_screenheight() - dialog_height) // 2
    else:
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
    dialog.geometry(f"+{x}+{y}")

    result = [None]  # 用 list 以便在闭包中修改

    main = ttk.Frame(dialog, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main, text=title, font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 8))

    content = ttk.Frame(main)
    content.pack(fill=tk.BOTH, expand=True)

    # 左侧：文件列表
    left = ttk.Frame(content)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    list_frame = ttk.LabelFrame(left, text="文件列表", padding=5)
    list_frame.pack(fill=tk.BOTH, expand=True)
    scroll = ttk.Scrollbar(list_frame)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    listbox = tk.Listbox(list_frame, height=12, yscrollcommand=scroll.set, font=("Consolas", 9))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.config(command=listbox.yview)
    for c in choices:
        listbox.insert(tk.END, c)

    # 右侧：预览
    right = ttk.Frame(content)
    right.pack(side=tk.RIGHT, padx=(10, 0), fill=tk.Y)
    preview_frame = ttk.LabelFrame(right, text="预览", padding=5)
    preview_frame.pack()
    preview_label = tk.Label(preview_frame, text="选择文件以查看预览", bg="gray90")
    preview_label.pack()
    duration_label = ttk.Label(
        preview_frame,
        text="时长 —",
        font=("Consolas", 9),
        foreground="gray25",
    )
    duration_label.pack(pady=(4, 0))
    preview_photo = [None]  # 保持引用避免被 GC

    def _update_duration_for_path(full):
        sec = _get_media_duration_sec(full)
        if sec is not None:
            duration_label.config(text=f"时长 {_format_duration(sec)}")
        else:
            lower = full.lower()
            if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")):
                duration_label.config(text="时长 —（图片）")
            else:
                duration_label.config(text="时长 —")

    def on_select(e):
        sel = listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        fn = choices[idx]
        full = os.path.join(folder_path, fn)
        img = _load_preview_image(full)
        if img:
            preview_photo[0] = img
            preview_label.config(image=img, text="")
        else:
            preview_photo[0] = None
            preview_label.config(image="", text="(无预览)")
        _update_duration_for_path(full)

    def on_confirm():
        sel = listbox.curselection()
        if sel:
            result[0] = choices[sel[0]]
        dialog.destroy()

    listbox.bind("<<ListboxSelect>>", on_select)
    listbox.bind("<Double-1>", lambda e: on_confirm())

    # 默认选中第一项并显示预览
    if choices:
        listbox.selection_set(0)
        listbox.see(0)
        full = os.path.join(folder_path, choices[0])
        img = _load_preview_image(full)
        if img:
            preview_photo[0] = img
            preview_label.config(image=img, text="")
        else:
            preview_label.config(image="", text="(无预览)")
        _update_duration_for_path(full)

    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(btn_frame, text="确定", command=on_confirm).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT)

    dialog.wait_window()
    return result[0]
