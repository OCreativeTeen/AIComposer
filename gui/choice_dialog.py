"""
选择对话框模块

提供通用的选择对话框功能
"""

import os
import tkinter as tk
import tkinter.ttk as ttk


def askchoice(title, choices, parent=None):
    # 如果没有提供父窗口，尝试获取默认根窗口
    if parent is None:
        try:
            parent = tk._default_root
        except:
            parent = None
    
    # 创建一个简单的选择对话框
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    
    # 根据选项数量动态计算高度
    # 每个按钮约 35 像素高度（包括间距），标题约 50 像素，取消按钮约 50 像素
    # 最小高度 250，最大高度不超过屏幕高度的 80%
    num_choices = len(choices)
    button_height = 35  # 每个按钮的高度（包括间距）
    title_height = 50   # 标题区域高度
    cancel_height = 50  # 取消按钮区域高度
    padding = 20        # 上下边距
    
    calculated_height = title_height + (num_choices * button_height) + cancel_height + padding
    min_height = 250
    
    # 获取屏幕尺寸（使用父窗口或对话框本身）
    dialog.update_idletasks()
    if parent:
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
    else:
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
    
    max_height = int(screen_height * 0.8)
    
    dialog_height = max(min_height, min(calculated_height, max_height))
    dialog_width = 350
    
    dialog.resizable(False, False)
    
    # 居中显示
    if parent:
        dialog.transient(parent)
    dialog.grab_set()
    
    # 居中窗口
    x = (screen_width // 2) - (dialog_width // 2)
    y = (screen_height // 2) - (dialog_height // 2)
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    result = None
    
    def on_choice(choice):
        nonlocal result
        result = choice
        dialog.destroy()
    
    # 添加标题
    label = ttk.Label(dialog, text=title, font=("Arial", 12, "bold"))
    label.pack(pady=15)
    
    # 添加选择按钮
    for choice in choices:
        btn = ttk.Button(dialog, text=choice, width=25, 
                       command=lambda c=choice: on_choice(c))
        btn.pack(pady=5)
    
    # 添加取消按钮
    cancel_btn = ttk.Button(dialog, text="取消", width=25, 
                          command=lambda: dialog.destroy())
    cancel_btn.pack(pady=15)
    
    # 等待用户选择
    dialog.wait_window()
    return result


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
