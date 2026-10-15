"""module-level constants and helpers shared by WorkflowGUI mixins (moved verbatim from GUI_wf.py)."""
import os
import config
import project_manager


STANDARD_FPS = 60  # Match FfmpegProcessor.STANDARD_FPS


IMAGE_ACTION_CHOICES = {
    "人物替换" : [
        "Replace Narrator/Figure in 1st image with the IP in 2nd image",
        "Add IP in 2nd image into 1st image (in front, half body, facing actor)",
        "Add IP in 2nd image into 1st image (in front, half body, facing audience)",
        "Add IP in 2nd image into 1st image (right, half body, facing actor)",
        "Add IP in 2nd image into 1st image (right, half body, facing audience)",
        "Add IP in 2nd image into 1st image (left, half body, facing actor)",
        "Add IP in 2nd image into 1st image (left, half body, facing audience)"
    ],
    "删除元素" : [
        "Remove text in upper part of image",
        "Remove text in lower part of image",
        "Remove PIP (narrator) in the image",
        "Remove Narrator in the image",
        "Remove Narrator in the image left",
        "Remove Narrator in the image right",
        "Remove Narrator in the image bottom",
        "Remove all text in the image",
    ],
    "节目包装" : [
        "Show title '{channel_name}' in header (creative)",
        "Show title '{channel_name}' in footer (creative)"
    ],
    "风格控制" : [
        "Change Person to Realistic Style",
        "Change Person to Pixar Style (Avoid large, wide, exaggerated eyes)",
        "Change Person to Cinematic Style",
        "Make the eyes much much smaller in overall scale (both eye width & height), Shrink the eyelid and visible eye area a lot!."
    ]
}


def _workflow_channel_display_name() -> str:
    """当前项目频道显示名（CHANNEL_CONFIG.channel_name），无则回退 channel id。"""
    pc = project_manager.PROJECT_CONFIG or {}
    ch = (pc.get("channel") or "").strip()
    if ch:
        ch_cfg = config.get_channel_config(ch)
        name = (ch_cfg.get("channel_name") or "").strip()
        if name:
            return name
        return ch
    return "节目"


def _download_folder_list_matching_suffixes(folder_path: str, suffixes: tuple) -> list:
    """目录下文件名（仅文件）后缀匹配任一 suffixes。"""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    out = []
    for fn in os.listdir(folder_path):
        fp = os.path.join(folder_path, fn)
        if os.path.isfile(fp) and any(fn.lower().endswith(s) for s in suffixes):
            out.append(fn)
    return sorted(out)


def _user_downloads_folder() -> str:
    """当前用户 Windows Downloads（浏览器/工具默认下载位置）。"""
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _external_media_pick_folders() -> list[str]:
    """场景选 clip 时优先浏览的外部目录：Downloads，其次 L:（旧环境映射盘）。"""
    folders: list[str] = []
    seen: set[str] = set()
    for p in (_user_downloads_folder(), "L:"):
        if not p:
            continue
        try:
            norm = os.path.normcase(os.path.abspath(p))
        except OSError:
            continue
        if norm in seen or not os.path.isdir(p):
            continue
        seen.add(norm)
        folders.append(p)
    return folders
