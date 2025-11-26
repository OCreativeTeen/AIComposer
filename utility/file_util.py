import json
import os
import shutil


def copy_file(source, destination):
    try:
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


def safe_file(file):
    if file and os.path.exists(file):
        return file
    return None


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
