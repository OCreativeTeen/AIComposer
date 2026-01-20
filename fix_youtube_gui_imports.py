"""
修复 gui/youtube_downloader.py 中 YoutubeGUIManager 类的模块引用
将所有 tk, ttk, messagebox, os, json, re 等替换为 self.tk, self.ttk 等
"""

import re

def fix_imports_in_file(file_path):
    """修复文件中的模块引用"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 找到 YoutubeGUIManager 类的范围
    class_start = content.find('class YoutubeGUIManager:')
    if class_start == -1:
        print("未找到 YoutubeGUIManager 类")
        return
    
    # 找到类的结束位置（下一个类定义或文件结束）
    class_end = content.find('\nclass ', class_start + 1)
    if class_end == -1:
        class_end = len(content)
    
    class_content = content[class_start:class_end]
    before_class = content[:class_start]
    after_class = content[class_end:]
    
    # 需要替换的模块映射
    replacements = [
        (r'\btk\.', 'self.tk.'),
        (r'\bttk\.', 'self.ttk.'),
        (r'\bmessagebox\.', 'self.messagebox.'),
        (r'\bos\.', 'self.os.'),
        (r'\bjson\.', 'self.json.'),
        (r'\bre\.', 'self.re.'),
        (r'\bthreading\.', 'self.threading.'),
        (r'\buuid\.', 'self.uuid.'),
        (r'\bdatetime\.', 'self.datetime.'),
    ]
    
    # 但要注意：不要替换已经在 self. 后面的
    # 不要替换 import 语句中的
    # 不要替换字符串中的
    
    # 逐行处理，避免替换 import 语句和字符串
    lines = class_content.split('\n')
    fixed_lines = []
    in_string = False
    string_char = None
    
    for line in lines:
        # 跳过 import 语句
        if line.strip().startswith('import ') or line.strip().startswith('from '):
            fixed_lines.append(line)
            continue
        
        # 简单处理：只替换方法体内的引用
        # 检查是否是方法定义行
        if re.match(r'^\s+def\s+\w+\(', line):
            fixed_lines.append(line)
            continue
        
        # 替换模块引用
        fixed_line = line
        for pattern, replacement in replacements:
            # 只替换不在字符串中的引用
            # 简单检查：如果引号数量是偶数，说明不在字符串中
            if fixed_line.count('"') % 2 == 0 and fixed_line.count("'") % 2 == 0:
                fixed_line = re.sub(pattern, replacement, fixed_line)
        
        fixed_lines.append(fixed_line)
    
    fixed_class_content = '\n'.join(fixed_lines)
    fixed_content = before_class + fixed_class_content + after_class
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"已修复 {file_path}")

if __name__ == "__main__":
    fix_imports_in_file('gui/youtube_downloader.py')
    print("修复完成！")
