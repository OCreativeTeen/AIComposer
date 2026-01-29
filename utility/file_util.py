import json
import os
import shutil
import glob
from datetime import datetime



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