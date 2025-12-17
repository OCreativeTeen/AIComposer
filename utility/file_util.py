import json
import os
import shutil
from datetime import datetime
import project_manager
import config



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



media_count = 0
pid = None

def refresh_scene_media(scene, media_type, media_postfix, replacement=None, make_replacement_copy=False):
    global media_count, pid
    new_media_stem = media_type + "_" + str(scene["id"]) + "_" + str(int(datetime.now().timestamp()*100 + media_count%100))
    media_count = (media_count + 1) % 100

    old_media_path = scene.get(media_type, None)
    if pid is None:
        pid = project_manager.PROJECT_CONFIG.get('pid')
    scene[media_type] = config.get_media_path(pid) + "/" + new_media_stem + media_postfix

    if replacement:
        safe_copy_overwrite(replacement, scene[media_type])
        if not make_replacement_copy:
            safe_remove(replacement)
    return old_media_path, scene[media_type]



def build_scene_media_prefix(pid, scene_id, media_type, animate_type, with_timestamp):
    scene_id = str(scene_id)
    if with_timestamp:
        timestamp = datetime.now().strftime("%d%H%M%S")
        return media_type + "_" + pid  + "_" + scene_id + "_" + animate_type + "_" + timestamp
    else:
        return media_type + "_" + pid  + "_" + scene_id + "_" + animate_type


def clean_memory(cuda=True, verbose=True):
    import gc, sys, os, ctypes
    
    # 尝试导入 psutil，如果不存在则设为 None
    try:
        import psutil
        has_psutil = True
    except ImportError:
        psutil = None
        has_psutil = False
        if verbose:
            print("⚠️ 警告: psutil 未安装，将跳过内存统计。建议运行: pip install psutil")

    if cuda:
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except:
            has_cuda = False
    else:
        has_cuda = False

    if verbose:
        print("\n=== Aggressive Memory Cleanup ===")

    # 1. Python GC
    if verbose: print("[1/4] Forcing Python GC…")
    gc.collect(); gc.collect(); gc.collect()

    # 2. CUDA cleanup
    if has_cuda:
        if verbose: print("[2/4] Clearing CUDA VRAM…")
        try:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception as e:
            print("CUDA cleanup error:", e)

    # 3. OS memory trim
    if verbose: print("[3/4] Releasing process memory to OS…")

    if sys.platform == "win32":
        # Windows working set trim
        try:
            ctypes.windll.kernel32.SetProcessWorkingSetSize(
                -1, ctypes.c_size_t(-1), ctypes.c_size_t(-1)
            )
        except Exception as e:
            print("Windows trim error:", e)

    elif sys.platform == "linux":
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except Exception as e:
            print("Linux trim error:", e)

    # 4. Final GC
    if verbose: print("[4/4] Final GC…")
    gc.collect()

    # Summary
    if has_psutil:
        try:
            process = psutil.Process(os.getpid())
            mem = process.memory_info().rss / 1024**2
            if verbose:
                print(f"=== Cleanup Complete | RAM now: {mem:.2f} MB ===\n")
        except Exception as e:
            if verbose:
                print(f"=== Cleanup Complete (内存统计失败: {e}) ===\n")
    else:
        if verbose:
            print("=== Cleanup Complete ===\n")