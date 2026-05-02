import json
import os
import shutil
import glob
from datetime import datetime
from typing import List, Dict, Union, Any, Optional
import re


def safe_clipboard_json_copy(text: Optional[str]) -> str:
    if text is None:
        return ""
    content = safe_clipboard_copy(text).strip()
    if not content:
        return ""

    if "```" in content:
        m = re.search(
            r"```\s*(?:json)?\s*\r?\n?(.*?)```",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if m:
            content = m.group(1).strip()
        else:
            content = re.sub(
                r"^\s*```\s*(?:json)?\s*",
                "",
                content,
                count=1,
                flags=re.IGNORECASE,
            )
            content = re.sub(r"\s*```\s*$", "", content).strip()

    lines = content.splitlines()
    if lines:
        first = lines[0].strip()
        if re.fullmatch(r"json\s*:?", first, flags=re.IGNORECASE):
            content = "\n".join(lines[1:]).strip()
            lines = content.splitlines()
    if lines:
        last = lines[-1].strip()
        if re.fullmatch(r"json\s*:?", last, flags=re.IGNORECASE):
            content = "\n".join(lines[:-1]).strip()

    return content.strip()


def safe_clipboard_copy(text: Optional[str]) -> str:
    """
    规范化从剪贴板取得的文本，使 json.loads 等解析更不易失败。
    将 NBSP、行/段分隔符（U+2028/U+2029）、零宽字符及常见 Unicode 空白
    转为普通空格或移除；并去掉 BOM。
    """
    if text is None:
        return ""
    t = text.replace("\ufeff", "")
    t = t.replace("\u00a0", " ").replace("\u202f", " ")
    t = t.replace("\u2028", " ").replace("\u2029", " ")
    for z in "\u200b\u200c\u200d\u2060":
        t = t.replace(z, "")
    for cp in range(0x2000, 0x200B):
        t = t.replace(chr(cp), " ")
    t = t.replace("\u1680", " ")
    t = t.replace("\u205f", " ")
    t = t.replace("\u3000", " ")
    return t


def make_safe_file_name(title, title_length=15):
    if not title:
        return "untitled"
    
    # 将空格替换为下划线
    safe_title = title.replace(' ', '_').replace('.', '_')
    
    # 移除 Windows 和 Unix 系统不允许的字符
    # Windows: < > : " / \ | ? *
    # Unix: / (以及控制字符)
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', safe_title)
    
    # 移除 Windows 保留名称（CON, PRN, AUX, NUL, COM1-9, LPT1-9）
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + \
                    [f'COM{i}' for i in range(1, 10)] + \
                    [f'LPT{i}' for i in range(1, 10)]
    if safe_title.upper() in reserved_names:
        safe_title = '_' + safe_title
    
    # 移除尾随空格和点（Windows 不允许）
    safe_title = safe_title.rstrip(' .')
    
    # 如果清理后为空，使用默认名称
    if not safe_title.strip():
        safe_title = "untitled"
    
    # 限制长度
    safe_title = safe_title[:title_length] if title_length > 0 else safe_title
    
    # 再次移除尾随空格和点（可能在截断后产生）
    safe_title = safe_title.rstrip(' .')
    
    return safe_title



def safe_move_overwrite(source, destination):
    try:
        if os.path.exists(destination):
            os.remove(destination)
        shutil.move(source, destination)
        return destination
    except Exception as e:
        print(f"❌ Error moving file: {e}")
        return None



def safe_copy_overwrite(source, destination):
    # shutil.copyfile(left_video.file_path, temp_left_path)
    try:
        # 确保目标目录存在
        dest_dir = os.path.dirname(destination)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        # 如果目标文件已存在，先删除以确保覆盖
        if os.path.exists(destination):
            os.remove(destination)
        
        # 复制文件（保留元数据）
        shutil.copy2(source, destination)
        return destination
    except Exception as e:
        print(f"❌ Error copying file: {e}")
        return None


def safe_remove(file):
    try:
        if file:
            os.remove(file)
    except:
        pass


def safe_file(file, is_dir=False):
    if not file or not os.path.exists(file):
        return None
    if is_dir and not os.path.isdir(file):
        return None
    if not is_dir and not os.path.isfile(file):
        return None
    return file


def read_text(file):
    with open(file, 'r', encoding="utf-8") as f:
        return f.read()


def write_text(file, text_content):
    with open(file, "w", encoding="utf-8") as f:
        f.write(text_content)


def read_json(file):
    with open(file, 'r', encoding="utf-8") as f:
        return json.load(f)      # parse


def write_json(file, json_content):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(json_content, f, ensure_ascii=False, indent=2)


def get_file_path(data, field):
    if data is None:
        return None
    path = data.get(field)
    if path and os.path.exists(path):
        return path
    # remove the field if it's missing or invalid
    data.pop(field, None)
    return None


def is_image_file(file_path):
    """检查文件是否为图像文件"""
    if not os.path.isfile(file_path):
        return False
    image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
    file_ext = os.path.splitext(file_path)[1].lower()
    return file_ext in image_extensions


def is_audio_file(file_path):
    """检查文件是否为音频文件"""
    if not os.path.isfile(file_path):
        return False
    audio_extensions = {'.mp3', '.wav', '.m4a', '.flac', '.aac'}
    file_ext = os.path.splitext(file_path)[1].lower()
    return file_ext in audio_extensions


def is_video_file(file_path):
    """检查文件是否为视频文件"""
    if not os.path.isfile(file_path):
        return False
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv'}
    file_ext = os.path.splitext(file_path)[1].lower()
    return file_ext in video_extensions


def check_folder_files(folder_path, file_extension):
    """Check if the folder_path has any files with the given file_extension"""
    if not safe_file(folder_path, True):
        return False
    # Check if the folder_path has any files with the given file_extension
    pattern = os.path.join(folder_path, "*" + file_extension)
    files = glob.glob(pattern)
    return len(files) > 0


def ending_punctuation(text):
    if text.endswith(".") or text.endswith("?") or text.endswith("!") or text.endswith(";") or text.endswith("...") or text.endswith("..") or text.endswith("。") or text.endswith("！") or text.endswith("？") or text.endswith("；") or text.endswith("…"):
        return True
    else:
        return False


def build_scene_media_prefix(pid, scene_id, media_type, animate_type, with_timestamp):
    scene_id = str(scene_id)
    if with_timestamp:
        timestamp = datetime.now().strftime("%d%H%M%S")
        return media_type + "_" + pid  + "_" + scene_id + "_" + animate_type + "_" + timestamp
    else:
        return media_type + "_" + pid  + "_" + scene_id + "_" + animate_type


def clean_memory(cuda=True, verbose=True):
    """超级激进的内存清理"""
    import gc
    # Python GC
    for _ in range(3):
        gc.collect()
    # CUDA
    try:
        import torch
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        torch.cuda.ipc_collect()
    except:
        pass



def parse_json(content_string: str, expect_list: bool = False) -> Union[Dict, List]:
    """
    解析JSON字符串，支持多种格式和清理操作
    
    Args:
        content_string: 要解析的JSON字符串
        expect_list: 是否期望返回列表格式。如果为True，会将字典自动转换为列表
        
    Returns:
        解析后的JSON对象（Dict或List）
    """
    
    def validate_and_convert_type(parsed_result: Any) -> Union[Dict, List]:
        """根据expect_list参数验证和转换类型"""
        if expect_list:
            if isinstance(parsed_result, list):
                return parsed_result
            elif isinstance(parsed_result, dict):
                print(f"警告：返回了 {type(parsed_result)} 而不是期望的列表格式，自动转换为列表")
                return [parsed_result]
            else:
                print(f"警告：返回了 {type(parsed_result)} 而不是期望的JSON格式")
                return []
        else:
            return parsed_result
    
    # Step 1: 移除<think>标签及其内容
    if content_string is None or content_string.strip() == "":
        return [] if expect_list else {}
    
    content_string = content_string.replace("\r\n", "\n").replace("\r", "\n")
    content_string = re.sub(r'<think>.*?</think>', '', content_string, flags=re.DOTALL)
    
    # Step 2: 移除首尾空白
    content_string = content_string.strip()
    
    # Step 2.5: 修复常见的 JSON 错误（如缺少逗号）
    # JSON 合法的转义：\" \\ \/ \b \f \n \r \t \uXXXX
    _VALID_ESCAPE_NEXT = frozenset('"\\/bfnrtu')

    def fix_common_json_errors(text: str) -> str:
        """修复常见的 JSON 格式错误，特别是 LLM 生成的错误"""
        # 使用字符级解析来安全地修复错误（保护字符串内容）
        result = []
        i = 0
        in_string = False
        escape_next = False

        while i < len(text):
            char = text[i]

            # 处理转义字符
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue

            if char == '\\':
                if in_string and i + 1 < len(text):
                    next_ch = text[i + 1]
                    if next_ch not in _VALID_ESCAPE_NEXT:
                        # 无效转义（如路径中的 \0 \D 等），将 \ 转义为 \\ 使下一字符为字面量
                        result.append('\\')
                        result.append('\\')
                        i += 1
                        continue
                result.append(char)
                escape_next = True
                i += 1
                continue
            
            # 跟踪字符串状态
            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            
            # 只在字符串外处理修复
            if not in_string:
                # 修复缺少逗号：`"key": "value" "key2":` -> `"key": "value", "key2":`
                # 模式：值结束引号 + 空白 + 键开始引号 + ... + 冒号
                if char == '"' and result and result[-1] == '"':
                    # 检查后面是否是新键的模式
                    j = i + 1
                    # 跳过空白
                    while j < len(text) and text[j] in ' \t\n\r':
                        j += 1
                    if j < len(text) and text[j] == '"':
                        # 可能是新键，继续查找冒号
                        k = j + 1
                        found_colon = False
                        while k < len(text):
                            if text[k] == '\\':
                                k += 2
                                continue
                            if text[k] == '"':
                                # 键结束，查找冒号
                                k += 1
                                while k < len(text) and text[k] in ' \t\n\r':
                                    k += 1
                                if k < len(text) and text[k] == ':':
                                    found_colon = True
                                break
                            k += 1
                        
                        if found_colon:
                            # 确认是缺少逗号的情况，添加逗号
                            result.append(',')
                
                # 修复多余的逗号：`,,` -> `,`
                if char == ',' and i + 1 < len(text) and text[i+1] == ',':
                    result.append(',')
                    i += 1  # 跳过第二个逗号
                    continue
                
                # 修复末尾多余的逗号：`,}` -> `}` 或 `,]` -> `]`
                if char == ',':
                    j = i + 1
                    while j < len(text) and text[j] in ' \t\n\r':
                        j += 1
                    if j < len(text) and text[j] in '}]':
                        # 跳过这个逗号
                        i += 1
                        continue
            
            # 普通字符
            result.append(char)
            i += 1
        
        fixed_text = ''.join(result)
        
        # 使用正则表达式进行额外的修复（作为补充）
        # 修复缺少逗号：`"value" "key":` -> `"value", "key":`
        # 匹配：引号 + 空白 + 引号 + 键名 + 引号 + 空白 + 冒号
        # 这个模式匹配值结束和新键开始之间缺少逗号的情况
        pattern = r'("(?:[^"\\]|\\.)*")\s+("(?:[^"\\]|\\.)*"\s*:)'
        fixed_text = re.sub(pattern, r'\1,\2', fixed_text)
        
        # 修复多余的逗号
        fixed_text = re.sub(r',\s*,+', ',', fixed_text)  # `,,` 或 `,,,` -> `,`
        fixed_text = re.sub(r',\s*([}\]])', r'\1', fixed_text)  # `,}` -> `}` 或 `,]` -> `]`
        
        return fixed_text
    
    # 应用 JSON 错误修复
    content_string = fix_common_json_errors(content_string)
    
    # Step 3: 首先尝试从 ```json ... ``` 代码块中提取JSON
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, content_string, re.DOTALL)
    if matches:
        try:
            json_content = matches[0].strip()
            parsed_result = json.loads(json_content)
            return validate_and_convert_type(parsed_result)
        except json.JSONDecodeError as e:
            print(f"从代码块解析JSON失败: {e}")
            # 继续尝试其他方法
    
    # Step 4: 尝试直接解析整个响应（最常见情况）
    try:
        parsed_result = json.loads(content_string)
        return validate_and_convert_type(parsed_result)
    except json.JSONDecodeError as e:
        print(f"直接解析失败: {e}")
        # 继续尝试其他方法
    
    # Step 5: 尝试提取JSON数组或对象（使用更精确的模式）
    # 查找以 [ 或 { 开头的JSON结构
    json_start = -1
    bracket_count = 0
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(content_string):
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
            
        if not in_string:
            if char in '[{':
                if json_start == -1:
                    json_start = i
                if char == '[':
                    bracket_count += 1
                else:
                    brace_count += 1
            elif char in ']}':
                if char == ']':
                    bracket_count -= 1
                else:
                    brace_count -= 1
                
                # 如果所有括号都匹配了，我们找到了完整的JSON
                if json_start != -1 and bracket_count == 0 and brace_count == 0:
                    json_str = content_string[json_start:i+1]
                    try:
                        parsed_result = json.loads(json_str)
                        return validate_and_convert_type(parsed_result)
                    except json.JSONDecodeError:
                        # 重置计数器，寻找下一个可能的JSON
                        json_start = -1
                        bracket_count = 0
                        brace_count = 0
    
    # Step 6: 最后的尝试 - 轻量级清理（仅用于明显损坏的JSON）
    try:
        # 再次应用 JSON 错误修复（以防前面的步骤没有完全修复）
        cleaned = fix_common_json_errors(content_string)
        
        # 移除控制字符（除了换行、回车、制表符）
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        
        # 移除首尾的引号（如果整个字符串被引号包裹）
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
            # 处理转义的引号
            cleaned = cleaned.replace('\\"', '"')
        
        # 修复多余的逗号（只在明显错误的情况下）
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        
        parsed_result = json.loads(cleaned)
        return validate_and_convert_type(parsed_result)
    except json.JSONDecodeError as e:
        print(f"轻量级清理后解析失败: {e}")
    
    # Step 7: 如果所有方法都失败，提供详细的错误信息
    preview = content_string[:500] if len(content_string) > 500 else content_string
    print(f"JSON解析失败，字符串预览：\n{preview}")
    raise Exception(f"无法从响应中提取有效的JSON。原始长度: {len(content_string)} 字符")
