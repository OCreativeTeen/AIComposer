"""
选择对话框模块

提供通用的选择对话框功能
"""

import tkinter as tk
import tkinter.ttk as ttk


def askchoice(title, choices, parent=None):
    """
    自定义的多选择对话框函数
    返回用户选择的选项字符串
    
    Args:
        title: 对话框标题
        choices: 选项列表
        parent: 父窗口（可选）
    
    Returns:
        用户选择的选项字符串，如果取消则返回 None
    """
    # 如果没有提供父窗口，尝试获取默认根窗口
    if parent is None:
        try:
            parent = tk._default_root
        except:
            parent = None
    
    # 创建一个简单的选择对话框
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("300x250")
    dialog.resizable(False, False)
    
    # 居中显示
    if parent:
        dialog.transient(parent)
    dialog.grab_set()
    
    # 居中窗口
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
    y = (dialog.winfo_screenheight() // 2) - (250 // 2)
    dialog.geometry(f"300x250+{x}+{y}")
    
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
