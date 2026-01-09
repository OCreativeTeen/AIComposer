import json
import os
import shutil
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

    # 1. Python GC - 多次调用确保回收循环引用
    if verbose: print("[1/5] Forcing Python GC…")
    gc.collect(); gc.collect(); gc.collect()

    # 2. CUDA cleanup - 更彻底的 CUDA 内存清理
    if has_cuda:
        if verbose: print("[2/5] Clearing CUDA VRAM…")
        try:
            # 同步所有 CUDA 操作
            torch.cuda.synchronize()
            # 清空 CUDA 缓存
            torch.cuda.empty_cache()
            # 清理进程间通信内存
            torch.cuda.ipc_collect()
            # 重置 CUDA 内存统计（如果需要调试）
            if hasattr(torch.cuda, 'reset_peak_memory_stats'):
                torch.cuda.reset_peak_memory_stats()
            # 再次同步确保清理完成
            torch.cuda.synchronize()
            if verbose:
                allocated = torch.cuda.memory_allocated() / 1024**2
                reserved = torch.cuda.memory_reserved() / 1024**2
                print(f"    CUDA: allocated={allocated:.1f}MB, reserved={reserved:.1f}MB")
        except Exception as e:
            if verbose:
                print(f"    CUDA cleanup error: {e}")

    # 3. 再次 GC（CUDA 清理后可能释放了更多 Python 对象）
    if verbose: print("[3/5] Post-CUDA GC…")
    gc.collect()

    # 4. OS memory trim
    if verbose: print("[4/5] Releasing process memory to OS…")

    if sys.platform == "win32":
        # Windows working set trim - 更激进的内存释放
        try:
            kernel32 = ctypes.windll.kernel32
            # 获取当前进程句柄
            handle = kernel32.GetCurrentProcess()
            # 清空工作集
            kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
            # 尝试使用 EmptyWorkingSet（如果可用）
            try:
                psapi = ctypes.windll.psapi
                psapi.EmptyWorkingSet(handle)
            except:
                pass
        except Exception as e:
            if verbose:
                print(f"    Windows trim error: {e}")

    elif sys.platform == "linux":
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except Exception as e:
            if verbose:
                print(f"    Linux trim error: {e}")

    # 5. Final GC
    if verbose: print("[5/5] Final GC…")
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