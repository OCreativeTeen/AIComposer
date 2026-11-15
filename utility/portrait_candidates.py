# -*- coding: utf-8 -*-
"""t443u: 人物窗里左右键翻的「候选肖像」（不依赖 Tk）。

- 项目里：<项目>/avatar/ 和 <项目>/avatar/<风格>/ 里别的人物的图（不含这一位自己的那张、不含 .bak 备份）。
- 故事预览（还没有项目）：先翻频道自己的 D:\\AI_MEDIA\\program\\<频道>\\avatar\\<风格>\\（t444u），
  那里没有这个风格的图再退回 D:\\AI_MEDIA\\avatar\\<风格>\\ 里的图（风格 = 画面风格括号里的英文，例如
  三维卡通 (Pixar-Art Cartoon) → Pixar-Art-Cartoon）；对不上任何风格文件夹就翻全部风格。
- 选中一张 = 复制成这一位的肖像（原来的先改名 .bakN 备份；别的人的图不动）。
"""
from __future__ import annotations

import os
import shutil

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
# avatar 根目录下不是画面风格的文件夹
NON_STYLE_DIRS = {"back", "effect", "voice", "original", "story"}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p or ""))


def list_images(folder: str) -> list:
    """folder 里的图片（不进子文件夹；跳过 .bak 备份和 _ 开头的，例如 _blank.png），按文件名排。"""
    if not folder or not os.path.isdir(folder):
        return []
    out = []
    for fn in sorted(os.listdir(folder), key=str.lower):
        low = fn.lower()
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in IMAGE_EXTS or ".bak" in low or stem.startswith("_"):
            continue
        path = os.path.join(folder, fn)
        if os.path.isfile(path):
            out.append(os.path.abspath(path))
    return out


def style_folders(root: str) -> list:
    """avatar 根目录下各画面风格的文件夹名（去掉 back / effect / voice / original / story / _备份）。"""
    if not root or not os.path.isdir(root):
        return []
    return [d for d in sorted(os.listdir(root), key=str.lower)
            if os.path.isdir(os.path.join(root, d)) and d.lower() not in NON_STYLE_DIRS and not d.startswith("_")]


def match_style_folder(root: str, token: str) -> str:
    """风格 token（例如 Pixar-Art-Cartoon）对应的文件夹名（不分大小写）；对不上返回 ""。"""
    t = (token or "").strip().lower()
    if not t:
        return ""
    for d in style_folders(root):
        if d.lower() == t:
            return d
    return ""


def look_score(path: str, body: str) -> int:
    """图片文件名（gender_age_eth…）和这一位的 性别/年龄/民族 对上几样：越多越靠前。"""
    bits = [b.strip().lower() for b in (body or "").split("（")[0].split("(")[0].split("/") if b.strip()]
    stem = os.path.splitext(os.path.basename(path))[0].lower().split("_")
    score = 0
    for i, b in enumerate(bits[:3]):
        if i < len(stem) and stem[i] == b:
            score += 4 - i  # 性别最重要
    return score


def _ranked(paths: list, body: str) -> list:
    return [p for _s, _i, p in sorted(((-look_score(p, body), i, p) for i, p in enumerate(paths)))]


def channel_avatar_dir(channel_path: str) -> str:
    """频道（program/<频道>）自己的 avatar 目录；channel_path 为空返回 ""。"""
    channel_path = (channel_path or "").strip()
    return os.path.join(channel_path, "avatar") if channel_path else ""


def library_candidates(root: str, token: str, body: str = "", channel_root: str = "") -> tuple:
    """故事预览：avatar/<风格>/ 里的图，和这一位样子对得上的排前面。返回 (图片列表, 说明)。
    风格对不上任何文件夹 → 全部风格文件夹的图，说明写「全部风格」。

    t444u：channel_root（program/<频道>/avatar）先：它下面这个风格的文件夹里有图，就只翻它
    （说明写「<频道>/<风格>」）；没有这个风格 / 文件夹是空的，再退回 root（通用 avatar）。"""
    if channel_root and _norm(channel_root) != _norm(root):
        ch_folder = match_style_folder(channel_root, token)
        if ch_folder:
            ch_paths = list_images(os.path.join(channel_root, ch_folder))
            if ch_paths:
                channel = os.path.basename(os.path.dirname(os.path.abspath(channel_root)))
                return _ranked(ch_paths, body), f"{channel}/{ch_folder}" if channel else ch_folder
    folder = match_style_folder(root, token)
    if folder:
        return _ranked(list_images(os.path.join(root, folder)), body), folder
    paths = []
    for d in style_folders(root):
        paths += list_images(os.path.join(root, d))
    label = f"全部风格（没有「{token}」文件夹）" if token else "全部风格"
    return _ranked(paths, body), label


def project_candidates(avatar_dir: str, token: str = "", exclude=(), body: str = "") -> list:
    """项目里：<项目>/avatar/<风格>/ 和 <项目>/avatar/ 里的图，去掉 exclude（这一位自己的肖像）。"""
    skip = {_norm(p) for p in exclude or () if p}
    seen, out = set(), []
    folders = ([os.path.join(avatar_dir, token)] if token else []) + [avatar_dir]
    for folder in folders:
        for p in list_images(folder):
            k = _norm(p)
            if k in skip or k in seen:
                continue
            seen.add(k)
            out.append(p)
    return _ranked(out, body)


def backup_existing(dest: str) -> list:
    """dest 同名（任何图片扩展名）的旧肖像改名 <stem>.bakN<ext>。返回备份了哪些。"""
    folder = os.path.dirname(dest)
    stem = os.path.splitext(os.path.basename(dest))[0]
    moved = []
    if not os.path.isdir(folder):
        return moved
    for fn in os.listdir(folder):
        s, ext = os.path.splitext(fn)
        if s.lower() != stem.lower() or ext.lower() not in IMAGE_EXTS:
            continue
        path = os.path.join(folder, fn)
        n = 1
        while os.path.exists(os.path.join(folder, f"{s}.bak{n}{ext}")):
            n += 1
        bak = os.path.join(folder, f"{s}.bak{n}{ext}")
        os.replace(path, bak)
        moved.append(bak)
    return moved


def apply_portrait_choice(src: str, dest: str) -> str:
    """把选中的图复制成这一位的肖像 dest（.png）。原来的先备份；src 本身不动。返回写好的路径。"""
    if not src or not os.path.isfile(src) or not dest:
        raise FileNotFoundError(src or dest or "")
    if os.path.splitext(_norm(src))[0] == os.path.splitext(_norm(dest))[0]:
        return src  # 选的就是这一位自己的肖像
    dest = os.path.splitext(dest)[0] + ".png"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    backup_existing(dest)
    if os.path.splitext(src)[1].lower() == ".png":
        shutil.copy2(src, dest)
    else:
        from PIL import Image

        with Image.open(src) as img:
            (img if img.mode in ("RGB", "RGBA") else img.convert("RGBA")).save(dest, "PNG")
    return dest
