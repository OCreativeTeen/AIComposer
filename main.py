import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

# Try to import TkinterDnD for drag and drop support
try:
    import tkinterdnd2 as TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

class MainApplication:
    def __init__(self):
        # Create root window
        if DND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
            
        self.root.title("魔法工作流")
        self.root.geometry("1200x800")
        
        # Create menu bar
        self.create_menu()
        
        # Create main content area
        self.create_main_content()
        
    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开主工作流", command=self.open_main_workflow)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="综合工具集", command=self.launch_magic_tool)
        tools_menu.add_separator()
        tools_menu.add_command(label="转录工具", command=self.launch_transcript_tool)
        tools_menu.add_command(label="缩略图工具", command=self.launch_thumbnail_tool)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about)
        
    def create_main_content(self):
        """Create main content area"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Welcome message
        welcome_frame = ttk.LabelFrame(main_frame, text="欢迎", padding="20")
        welcome_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(welcome_frame, 
                 text="欢迎使用魔法工作流工具集\n\n"
                      "您可以通过菜单栏选择要使用的工具：\n"
                      "• 主工作流 - 完整的视频制作工作流程\n"
                      "• 综合工具集 - YouTube转录和缩略图生成\n"
                      "• 转录工具 - YouTube视频转录和翻译\n"
                      "• 缩略图工具 - 视频缩略图生成",
                 justify=tk.CENTER,
                 font=("TkDefaultFont", 12)).pack(expand=True)
        
        # Quick launch buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(button_frame, text="打开主工作流", 
                  command=self.open_main_workflow).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开综合工具集",
                  command=self.launch_magic_tool).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开转录工具",
                  command=self.launch_transcript_tool).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开缩略图工具",
                  command=self.launch_thumbnail_tool).pack(side=tk.LEFT, padx=5)
        
    def open_main_workflow(self):
        """Open main workflow GUI"""
        from magic_workflow_gui import MagicWorkflowGUI
        workflow_window = tk.Toplevel(self.root)
        app = MagicWorkflowGUI(workflow_window)
        
    def launch_magic_tool(self):
        """Launch magic tool (combined transcript and thumbnail)"""
        from GUI_Magic_Tool import MagicToolGUI
        tool = MagicToolGUI(tk.Toplevel(self.root))
        
    def launch_transcript_tool(self):
        """Launch transcript tool"""
        from transcript_tool import TranscriptTool
        tool = TranscriptTool(tk.Toplevel(self.root))
        
    def launch_thumbnail_tool(self):
        """Launch thumbnail tool"""
        from thumbnail_tool import ThumbnailTool
        tool = ThumbnailTool(tk.Toplevel(self.root))
        
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("关于", 
                          "魔法工作流工具集\n"
                          "版本 1.0\n\n"
                          "一个用于视频制作的综合工具集。\n"
                          "包含主工作流、转录工具和缩略图工具。")
        
    def run(self):
        """Start the application"""
        self.root.mainloop()

if __name__ == "__main__":
    app = MainApplication()
    app.run() 