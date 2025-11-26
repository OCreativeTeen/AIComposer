import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.messagebox as messagebox
import json
import os


class RawScenariosEditor:
    """Raw scenarios JSON editor dialog"""
    
    def __init__(self, parent, json_file_path):
        self.parent = parent
        self.json_file_path = json_file_path
        self.result = None
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建JSON编辑对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(f"Raw Scenarios Editor - {os.path.basename(self.json_file_path)}")
        self.dialog.geometry("1200x800")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 使对话框居中
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (1200 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (800 // 2)
        self.dialog.geometry(f"1200x800+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题和说明
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(title_frame, text="Raw Scenarios JSON Editor", 
                 font=("Arial", 16, "bold")).pack(side=tk.LEFT)
        
        ttk.Label(title_frame, text="编辑完成后点击保存按钮", 
                 font=("Arial", 10), foreground="gray").pack(side=tk.RIGHT)
        
        # 工具栏
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar_frame, text="格式化JSON", 
                  command=self.format_json).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(toolbar_frame, text="验证JSON", 
                  command=self.validate_json).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(toolbar_frame, text="重新加载", 
                  command=self.reload_file).pack(side=tk.LEFT, padx=(0, 10))
        
        # JSON编辑区域
        editor_frame = ttk.LabelFrame(main_frame, text="JSON内容", padding=10)
        editor_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 创建文本编辑器
        self.text_editor = scrolledtext.ScrolledText(
            editor_frame, 
            wrap=tk.NONE,
            font=("Consolas", 11),
            tabs=('2c',)
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True)
        
        # 加载JSON文件内容
        self.load_json_content()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="保存", 
                  command=self.save_and_close).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="取消", 
                  command=self.cancel).pack(side=tk.RIGHT)
        
        # 绑定快捷键
        self.dialog.bind('<Control-s>', lambda e: self.save_and_close())
        self.dialog.bind('<Escape>', lambda e: self.cancel())
        
        # 聚焦到编辑器
        self.text_editor.focus_set()
    
    def load_json_content(self):
        """加载JSON文件内容"""
        try:
            if os.path.exists(self.json_file_path):
                with open(self.json_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.text_editor.delete(1.0, tk.END)
                    self.text_editor.insert(1.0, content)
            else:
                self.text_editor.insert(1.0, "[]")
        except Exception as e:
            messagebox.showerror("错误", f"加载文件失败: {str(e)}")
    
    def format_json(self):
        """格式化JSON"""
        try:
            content = self.text_editor.get(1.0, tk.END).strip()
            if content:
                json_data = json.loads(content)
                formatted = json.dumps(json_data, ensure_ascii=False, indent=2)
                self.text_editor.delete(1.0, tk.END)
                self.text_editor.insert(1.0, formatted)
                messagebox.showinfo("成功", "JSON格式化完成")
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"格式化失败: {str(e)}")
    
    def validate_json(self):
        """验证JSON格式"""
        try:
            content = self.text_editor.get(1.0, tk.END).strip()
            if content:
                json.loads(content)
                messagebox.showinfo("成功", "JSON格式正确")
            else:
                messagebox.showwarning("警告", "内容为空")
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"验证失败: {str(e)}")
    
    def reload_file(self):
        """重新加载文件"""
        if messagebox.askyesno("确认", "重新加载文件将丢失当前的修改，确定继续吗？"):
            self.load_json_content()
    
    def save_and_close(self):
        """保存并关闭"""
        try:
            content = self.text_editor.get(1.0, tk.END).strip()
            if content:
                # 验证JSON格式
                json_data = json.loads(content)
                
                # 保存到文件
                with open(self.json_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.result = True
                messagebox.showinfo("成功", "文件保存成功")
                self.dialog.destroy()
            else:
                messagebox.showwarning("警告", "内容不能为空")
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误，无法保存: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def cancel(self):
        """取消"""
        if messagebox.askyesno("确认", "确定要取消编辑吗？未保存的修改将丢失。"):
            self.result = False
            self.dialog.destroy()
