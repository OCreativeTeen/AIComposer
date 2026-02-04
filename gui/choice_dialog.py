"""
选择对话框模块

提供通用的选择对话框功能
"""

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
