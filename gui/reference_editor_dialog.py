"""参考内容编辑器对话框 - 基于 Story 分析的参考案例与素材。"""

import json
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk

from config import parse_json_from_text
from utility.file_util import safe_clipboard_json_copy
from utility.llm_api import LLMApi


class ReferenceEditorDialog:
    """参考内容编辑器 - 基于 Story 分析的参考案例与素材（搜索/生成逻辑待后续集成）"""

    def __init__(self, parent, current_story, reference_filter):
        self.parent = parent
        self.current_story = current_story
        self.reference_filter = reference_filter
        self.generated_content = []
        self.llm_api = LLMApi()
        self.create_dialog()

    def create_dialog(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("参考内容编辑器")
        self.dialog.geometry("800x500")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 800) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"800x500+{x}+{y}")

        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="参考内容 (References)：分析与案例素材，供主持人参考，亦作为生成分析内容的输入", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.reference_editor = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=15)
        self.reference_editor.pack(fill=tk.BOTH, expand=True)
        self.reference_editor.insert('1.0', self.current_story)
        self.reference_editor.bind('<Double-1>', self._on_paste_from_clipboard)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="从 NotebookLM 获取", command=self._fetch_from_notebooklm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="确定", command=self.on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

    def _on_paste_from_clipboard(self, event=None):
        try:
            clipboard_content = safe_clipboard_json_copy(self.dialog.clipboard_get())
            if clipboard_content:
                self.reference_editor.insert(tk.INSERT, clipboard_content)
        except tk.TclError:
            pass

    def _fetch_from_notebooklm(self):
        try:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(self.reference_filter  + "\n---------\n" + self.current_story)
        except tk.TclError:
            pass

        messagebox.showinfo("提示", "已将筛选 Prompt 复制到剪贴板。\n\n请到 NotebookLM 中使用该 prompt 生成参考列表。\n\n点击确定后，将打开粘贴窗口，请将生成的 JSON 粘贴到该窗口中（双击可快速粘贴剪贴板），然后确认以继续勾选需要的参考项。")

        paste_dialog = tk.Toplevel(self.dialog)
        paste_dialog.title("粘贴 NotebookLM 生成内容")
        paste_dialog.geometry("700x400")
        paste_dialog.transient(self.dialog)
        paste_dialog.grab_set()
        paste_dialog.update_idletasks()
        x = (paste_dialog.winfo_screenwidth() - 700) // 2
        y = (paste_dialog.winfo_screenheight() - 400) // 2
        paste_dialog.geometry(f"700x400+{x}+{y}")

        ttk.Label(paste_dialog, text="请将 NotebookLM 生成的 JSON 粘贴到下方（双击可从剪贴板粘贴）", font=('TkDefaultFont', 10)).pack(anchor='w', padx=20, pady=(20, 5))
        paste_text = scrolledtext.ScrolledText(paste_dialog, wrap=tk.WORD, width=80, height=12)
        paste_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        def paste_on_double_click(e):
            clipboard_content = safe_clipboard_json_copy(paste_dialog.clipboard_get())
            paste_text.insert(tk.INSERT, clipboard_content)

        paste_text.bind('<Double-1>', paste_on_double_click)


        def on_paste_confirm():
            raw = paste_text.get('1.0', tk.END).strip()
            if not raw:
                messagebox.showerror("错误", "请先粘贴 NotebookLM 生成的内容")
                return
            
            parsed = parse_json_from_text(raw)
            if not parsed:
                messagebox.showerror("错误", "无法解析为 JSON 对象，请确认粘贴的是包含 story 与 analysis 的 JSON")
                return

            self.generated_content = parsed
            paste_dialog.destroy()


        btn_f = ttk.Frame(paste_dialog)
        btn_f.pack(fill=tk.X, pady=10)
        ttk.Button(btn_f, text="确认", command=on_paste_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="取消", command=paste_dialog.destroy).pack(side=tk.LEFT, padx=5)
        paste_dialog.wait_window()

        if not self.generated_content:
            return

        def show_section_select_dialog(section_title, items):
            """显示一个区块的勾选对话框，返回用户勾选后的列表；取消则返回 None。"""
            if not items:
                return []
            select_dialog = tk.Toplevel(self.dialog)
            select_dialog.title(section_title)
            select_dialog.geometry("650x450")
            select_dialog.transient(self.dialog)
            select_dialog.grab_set()
            select_dialog.update_idletasks()
            x = (select_dialog.winfo_screenwidth() - 650) // 2
            y = (select_dialog.winfo_screenheight() - 450) // 2
            select_dialog.geometry(f"650x450+{x}+{y}")

            ttk.Label(select_dialog, text="勾选需要保留的参考项，然后点击确认", font=('TkDefaultFont', 10)).pack(anchor='w', padx=20, pady=(20, 5))
            canvas_frame = ttk.Frame(select_dialog)
            canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
            canvas = tk.Canvas(canvas_frame)
            scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable = ttk.Frame(canvas)
            scrollable.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0, 0), window=scrollable, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            vars_items = []
            for i, item in enumerate(items):
                cb_var = tk.BooleanVar(value=True)
                vars_items.append((cb_var, item))
                if isinstance(item, dict):
                    source = item.get("source_name", "") or ""
                    fpath = item.get("transcribed_file", "") or ""
                    fpath_tail = fpath[-36:] if len(fpath) > 36 else fpath
                    reason = item.get("reason", "") or ""
                    lines = []
                    if source:
                        lines.append(f"来源: {source}")
                    if fpath_tail:
                        lines.append(f"文件名: {fpath_tail}")
                    if reason:
                        lines.append(f"原因: {reason}")
                    display_text = "\n".join(lines) if lines else json.dumps(item, ensure_ascii=False)[:120] + ("..." if len(json.dumps(item, ensure_ascii=False)) > 120 else "")
                else:
                    display_text = json.dumps(item, ensure_ascii=False)[:120] + ("..." if len(json.dumps(item, ensure_ascii=False)) > 120 else "")
                row_f = ttk.Frame(scrollable)
                row_f.pack(fill=tk.X, pady=6)
                ttk.Checkbutton(row_f, variable=cb_var).pack(side=tk.LEFT, padx=(0, 8), anchor='n')
                ttk.Label(row_f, text=display_text, wraplength=520, justify='left').pack(side=tk.LEFT, fill=tk.X, expand=True)

            selected_result = [None]

            def on_confirm():
                selected_result[0] = [item for (cb_var, item) in vars_items if cb_var.get()]
                select_dialog.destroy()

            btn_f2 = ttk.Frame(select_dialog)
            btn_f2.pack(fill=tk.X, pady=10)
            ttk.Button(btn_f2, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f2, text="取消", command=select_dialog.destroy).pack(side=tk.LEFT, padx=5)
            select_dialog.wait_window()
            return selected_result[0]


        self.generated_content = show_section_select_dialog("勾选参考项：Story（故事/案例）", self.generated_content)
        if not self.generated_content:
            return

        self.reference_editor.delete('1.0', tk.END)
        self.reference_editor.insert('1.0', json.dumps(self.generated_content, indent=2, ensure_ascii=False))


    def on_confirm(self):
        self.dialog.destroy()

    def on_cancel(self):
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.generated_content
