#!/usr/bin/env python3
"""
Magic Tool Launcher
A combined tool for YouTube transcription and thumbnail generation with language support.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from GUI_Magic_Tool import MagicToolGUI
    
    def main():
        """Main function to launch the Magic Tool"""
        print("启动 Magic Tools - 工具集...")
        print("功能包括:")
        print("- YouTube视频转录和翻译")
        print("- 缩略图生成")
        print("- 多语言支持 (zh/tw/en)")
        print()
        
        app = MagicToolGUI()
        app.run()
        
    if __name__ == "__main__":
        main()
        
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保所有依赖文件都在正确的位置")
    sys.exit(1)
except Exception as e:
    print(f"启动错误: {e}")
    sys.exit(1) 