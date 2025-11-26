import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox

class AnimationSelectorDialog:
    """动画选择对话框"""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = None
        self.dialog = None
        
        # 动画选项
        self.animation_options = {
            1: "静止图片",
            2: "向左移动", 
            3: "向右移动",
            4: "动画效果",
            5: "视频生成"
        }
        
    def show(self):
        """显示对话框并返回用户选择"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择动画效果")
        self.dialog.geometry("380x380")
        self.dialog.resizable(False, False)
        
        # 居中显示
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 计算居中位置
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (280 // 2)
        self.dialog.geometry(f"380x380+{x}+{y}")
        
        self._create_widgets()
        
        # 等待用户操作
        self.dialog.wait_window()
        return self.result
    
    def _create_widgets(self):
        """创建对话框控件"""
        # 主容器
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="🎬 选择图像动画效果", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 20))
        
        # 说明文本
        desc_label = ttk.Label(main_frame, 
                              text="请选择要应用于图像的动画效果：",
                              font=("Arial", 10))
        desc_label.pack(pady=(0, 15))
        
        # 选项框架
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # 选择变量
        self.selected_option = tk.IntVar(value=1)
        
        # 创建单选按钮
        for value, text in self.animation_options.items():
            rb = ttk.Radiobutton(options_frame, 
                               text=text,
                               variable=self.selected_option,
                               value=value,
                               style="Custom.TRadiobutton")
            rb.pack(anchor="w", pady=5, padx=10)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 确定按钮
        ok_button = ttk.Button(button_frame, text="确定", 
                              command=self._on_ok,
                              style="Accent.TButton")
        ok_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 取消按钮
        cancel_button = ttk.Button(button_frame, text="取消", 
                                 command=self._on_cancel)
        cancel_button.pack(side=tk.RIGHT)
        
        # 绑定键盘事件
        self.dialog.bind('<Return>', lambda e: self._on_ok())
        self.dialog.bind('<Escape>', lambda e: self._on_cancel())
        
        # 设置焦点
        ok_button.focus_set()
    
    def _on_ok(self):
        """确定按钮点击事件"""
        self.result = self.selected_option.get()
        self.dialog.destroy()
    
    def _on_cancel(self):
        """取消按钮点击事件"""
        self.result = None
        self.dialog.destroy()

def show_animation_selector(parent):
    """便捷函数：显示动画选择对话框"""
    dialog = AnimationSelectorDialog(parent)
    return dialog.show()
