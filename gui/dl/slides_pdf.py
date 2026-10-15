"""slide download / PDF scene source (moved verbatim from gui/downloader.py)."""
import os
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
from utility.pdf_util import _images_to_temp_pdf, _pdf_page_count


_SUMMARY_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".jfif",
    ".heic",
    ".heif",
)


def _pdf_pages_as_scene_source(pdf_path: str) -> tuple[str, int, bool]:
    """{content} 只写文件名和页数。具体画面让模型自己看 PDF。"""
    n = _pdf_page_count(pdf_path)
    if n <= 0:
        return "", 0, False
    text = (
        f"PDF file: {os.path.basename(pdf_path)}\n"
        f"Page count: {n}\n"
        "Pages may contain pictures and a little text. Read the PDF for the content. "
        "For each person in a picture, judge the age band from the face and body: "
        "kids, youth, teenager, mature, or senior. The words rarely state an age."
    )
    return text, n, False


def _download_slide_files(limit: int = 80) -> tuple[str, list[str]]:
    """下载文件夹里最近的 PDF 和图片。"""
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(folder):
        return folder, []
    found: list[str] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return folder, []
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf" or ext in _SUMMARY_IMAGE_SUFFIXES:
            found.append(path)
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return folder, found[: max(1, int(limit))]


def _slide_thumb_image(path: str, side: int = 140):
    """PDF 用第一页，图片用原图，缩成小预览。"""
    from PIL import Image

    if (path or "").lower().endswith(".pdf"):
        import fitz

        doc = fitz.open(path)
        try:
            if len(doc) <= 0:
                raise ValueError("empty pdf")
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        finally:
            doc.close()
    else:
        img = Image.open(path)
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
    img.thumbnail((side, side))
    return img


def ask_download_slide_pdf(parent) -> str:
    """从下载文件夹选一份 PDF，或按点击顺序把图片合成 PDF。取消时返回空字符串。"""
    from PIL import ImageTk

    folder, files = _download_slide_files()
    if not os.path.isdir(folder):
        messagebox.showinfo("选择图文", f"找不到下载文件夹：\n{folder}", parent=parent)
        return ""
    if not files:
        messagebox.showinfo("选择图文", "下载文件夹里没有 PDF 或图片。", parent=parent)
        return ""

    dlg = tk.Toplevel(parent)
    dlg.title("选择图文")
    dlg.geometry("980x680")
    dlg.minsize(720, 480)
    dlg.transient(parent)
    dlg.grab_set()
    result = {"path": ""}
    selected: list[str] = []
    cells: dict[str, dict] = {}
    thumb_side = 140
    columns = 5

    outer = ttk.Frame(dlg, padding=12)
    outer.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        outer,
        text="点一份 PDF，或按顺序点图片。第一下是第 1 页，再点一次已选的图片会取消。多张图片会合成一份 PDF，挂到这一条上。",
        wraplength=920,
    ).pack(anchor=tk.W, pady=(0, 4))
    ttk.Label(outer, text=folder, foreground="#555").pack(anchor=tk.W, pady=(0, 6))
    status_var = tk.StringVar(value="还没有选择。")
    ttk.Label(outer, textvariable=status_var).pack(anchor=tk.W, pady=(0, 6))

    canvas = tk.Canvas(outer, highlightthickness=0, bg="#f7f7f7")
    vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    inner = tk.Frame(canvas, bg="#f7f7f7")
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _fit_inner(event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        if event is not None and getattr(event, "widget", None) is canvas:
            canvas.itemconfigure(window_id, width=event.width)

    inner.bind("<Configure>", _fit_inner)
    canvas.bind("<Configure>", _fit_inner)

    def _on_wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(_event=None):
        canvas.bind_all("<MouseWheel>", _on_wheel)

    def _unbind_wheel(_event=None):
        try:
            canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)
    dlg.bind("<Destroy>", lambda event: _unbind_wheel() if event.widget is dlg else None)

    def _refresh_marks():
        order = {os.path.normcase(p): i + 1 for i, p in enumerate(selected)}
        for path, cell in cells.items():
            n = order.get(os.path.normcase(path))
            if n:
                cell["badge"].configure(text=str(n), bg="#1d6fbf", fg="white")
                cell["frame"].configure(highlightbackground="#1d6fbf", highlightthickness=3)
            else:
                cell["badge"].configure(text="", bg="white", fg="#333")
                cell["frame"].configure(highlightbackground="#cccccc", highlightthickness=1)
        if not selected:
            status_var.set("还没有选择。")
        elif len(selected) == 1 and selected[0].lower().endswith(".pdf"):
            status_var.set("已选 PDF：" + os.path.basename(selected[0]))
        else:
            status_var.set(f"已选 {len(selected)} 张图片，按 1、2、3… 的顺序合成 PDF。")

    def _on_pick(path: str):
        key = os.path.normcase(path)
        is_pdf = path.lower().endswith(".pdf")
        if is_pdf:
            if len(selected) == 1 and os.path.normcase(selected[0]) == key:
                selected.clear()
            else:
                selected.clear()
                selected.append(path)
        else:
            selected[:] = [p for p in selected if not p.lower().endswith(".pdf")]
            if any(os.path.normcase(p) == key for p in selected):
                selected[:] = [p for p in selected if os.path.normcase(p) != key]
            else:
                selected.append(path)
        _refresh_marks()

    for index, path in enumerate(files):
        cell = tk.Frame(
            inner,
            bg="white",
            highlightthickness=1,
            highlightbackground="#cccccc",
            cursor="hand2",
        )
        cell.grid(row=index // columns, column=index % columns, padx=6, pady=6, sticky="n")
        badge = tk.Label(
            cell, text="", width=3, font=("Microsoft YaHei UI", 12, "bold"), bg="white"
        )
        badge.pack(anchor=tk.W)
        img_lbl = tk.Label(
            cell, text="…", width=18, height=8, bg="#eeeeee", fg="#666666"
        )
        img_lbl.pack(padx=6)
        short = os.path.basename(path)
        if len(short) > 28:
            short = short[:12] + "…" + short[-12:]
        name_lbl = tk.Label(
            cell,
            text=short,
            wraplength=thumb_side,
            bg="white",
            fg="#222222",
            font=("Microsoft YaHei UI", 8),
            justify=tk.CENTER,
        )
        name_lbl.pack(padx=4, pady=(4, 6))
        cells[path] = {"frame": cell, "badge": badge, "img": img_lbl, "photo": None}
        for widget in (cell, badge, img_lbl, name_lbl):
            widget.bind("<Button-1>", lambda _event, p=path: _on_pick(p))

    pending = list(files)

    def _load_thumbs():
        if not dlg.winfo_exists() or not pending:
            return
        for _ in range(4):
            if not pending:
                break
            path = pending.pop(0)
            cell = cells.get(path)
            if cell is None:
                continue
            try:
                image = _slide_thumb_image(path, thumb_side)
                photo = ImageTk.PhotoImage(image)
                cell["photo"] = photo
                cell["img"].configure(image=photo, text="", width=0, height=0)
            except Exception:
                cell["img"].configure(text="无法预览")
        if pending:
            dlg.after(1, _load_thumbs)

    dlg.after(1, _load_thumbs)

    btn_row = ttk.Frame(outer)
    btn_row.pack(fill=tk.X, pady=(10, 0))

    def _confirm():
        if not selected:
            messagebox.showinfo("选择图文", "先点一份 PDF，或按顺序点图片。", parent=dlg)
            return
        if len(selected) == 1 and selected[0].lower().endswith(".pdf"):
            result["path"] = selected[0]
            _unbind_wheel()
            dlg.destroy()
            return
        try:
            dlg.configure(cursor="watch")
            dlg.update_idletasks()
            result["path"] = _images_to_temp_pdf(selected)
        except Exception as exc:
            dlg.configure(cursor="")
            messagebox.showerror("选择图文", f"图片合成 PDF 失败：\n{exc}", parent=dlg)
            return
        _unbind_wheel()
        dlg.destroy()

    def _cancel():
        result["path"] = ""
        _unbind_wheel()
        dlg.destroy()

    ttk.Button(btn_row, text="取消", command=_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row, text="使用", command=_confirm).pack(side=tk.RIGHT)
    dlg.protocol("WM_DELETE_WINDOW", _cancel)
    dlg.wait_window()
    return (result.get("path") or "").strip()
