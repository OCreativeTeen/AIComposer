# -*- coding: utf-8 -*-
"""t410u: 项目里每一场的参考图（``ref_images``）。

- 建项目时（信息图来源除外），场景上记着的 ref_images 不论来自 PDF、视频、音频还是文字（手工加的也算），
  都复制进项目 ``media/<集>/``（和这一集的编号页图同一个文件夹），改名成 ``<本集第几场>_<序号><原扩展名>``
  （1_1.png、1_2.png、2_1.webp…），免得不同来源同名冲突。场景里的路径改成复制后的新路径，第一张就是这一场的图。
- 名字只在第一次复制进来时起一次，以后不再改：别的场景选用这张图时只记路径，不改名、不再复制。
- 旧项目每场只记一个 ``episode_page``（本集图片库里的编号页图）。打开选图时把它并进 ref_images。
- 选中一张图 → 放到这一场 ref_images 的最前面。
- 分集 / 挪集时，ref_images 指着的文件一律复制（不移动、不删除），一张图可能好几场在用。

这个模块不碰 Tk，也不依赖 MagicWorkflow，方便单测。
"""
import os
import re
import shutil

REF_FIELD = "ref_images"
IMAGE_EXTS = (".webp", ".png", ".jpg", ".jpeg", ".bmp", ".gif")
_PAGE_RANK = {".webp": 0, ".jpg": 1, ".jpeg": 1, ".png": 2}
_SCENE_NAME_RE = re.compile(r"^(\d+)_(\d+)$")


def norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(str(path or "")))


def inside(path: str, folder: str) -> bool:
    if not path or not folder:
        return False
    return norm(path).startswith(norm(folder).rstrip("\\/") + os.sep)


def entry_path(entry) -> str:
    if isinstance(entry, dict):
        return str(entry.get("path") or "").strip()
    if isinstance(entry, str):
        return entry.strip()
    return ""


def ref_entries(scene) -> list:
    refs = scene.get(REF_FIELD) if isinstance(scene, dict) else None
    return refs if isinstance(refs, list) else []


def scene_ref_paths(scene, *, existing_only: bool = True) -> list:
    """这一场 ref_images 里的路径（去重、按顺序）。默认只要磁盘上还在的。"""
    out, seen = [], set()
    for e in ref_entries(scene):
        p = entry_path(e)
        if not p:
            continue
        if existing_only and not os.path.isfile(p):
            continue
        k = norm(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(os.path.abspath(p))
    return out


def page_file(folder: str, page) -> str:
    """本集图片库里编号为 page 的页图（同号有几种格式时 webp 优先）。没有返回 ""。"""
    try:
        n = int(page or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0 or not folder:
        return ""
    for ext in sorted(_PAGE_RANK, key=_PAGE_RANK.get):
        p = os.path.join(folder, f"{n}{ext}")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def page_number_in_folder(path: str, folder: str) -> int:
    """path 是 folder 里的编号页图（文件名是纯数字）就返回编号，否则 0。"""
    if not path or not folder:
        return 0
    if norm(os.path.dirname(path)) != norm(folder):
        return 0
    stem, ext = os.path.splitext(os.path.basename(path))
    if ext.lower() in _PAGE_RANK and stem.isdigit():
        return int(stem)
    return 0


def scene_image_name(scene_no: int, k: int, ext: str) -> str:
    return f"{int(scene_no)}_{int(k)}{(ext or '.png').lower()}"


def free_scene_image_path(folder: str, scene_no: int, ext: str, start: int = 1) -> tuple:
    """folder 里第一个还没被占的 <scene_no>_<k>.*（任何扩展名占了都算占），返回 (路径, k)。"""
    taken = set()
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = _SCENE_NAME_RE.match(os.path.splitext(name)[0])
            if m and int(m.group(1)) == int(scene_no):
                taken.add(int(m.group(2)))
    k = max(1, int(start))
    while k in taken:
        k += 1
    return os.path.join(folder, scene_image_name(scene_no, k, ext)), k


def next_scene_image_path(folder: str, scene_no: int, ext: str) -> tuple:
    """t412u: 新加进来的图接在这一场已有序号的最大值后面：已有 _1.._5 → _6（中间空号不补）。返回 (路径, k)。"""
    highest = 0
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = _SCENE_NAME_RE.match(os.path.splitext(name)[0])
            if m and int(m.group(1)) == int(scene_no):
                highest = max(highest, int(m.group(2)))
    k = highest + 1
    path = os.path.join(folder, scene_image_name(scene_no, k, ext))
    while os.path.exists(path):  # 理论上不会：保险
        k += 1
        path = os.path.join(folder, scene_image_name(scene_no, k, ext))
    return path, k


def _with_path(entry, new_path: str, old_path: str = ""):
    rec = dict(entry) if isinstance(entry, dict) else {}
    rec["path"] = new_path
    if old_path and norm(old_path) != norm(new_path) and not rec.get("from"):
        rec["from"] = old_path
    return rec


def import_scene_ref_images(scene: dict, folder: str, scene_no: int, *, media_root: str = "",
                            copy=shutil.copy2) -> int:
    """把这一场 ref_images 里不在项目 media 里的图复制进 folder，名字 <scene_no>_<k><扩展名>，并改写路径。

    已经在 media_root（或 folder）里面的图不动、不改名（名字第一次进项目时就定了）。
    磁盘上已经没有的图保持原样。同一个文件只留一条。返回这次复制了几张。
    """
    refs = ref_entries(scene)
    if not refs:
        return 0
    root = media_root or folder
    os.makedirs(folder, exist_ok=True)
    out, seen, copied = [], set(), 0
    k = 1
    for e in refs:
        p = entry_path(e)
        if not p:
            continue
        key = norm(p)
        if key in seen:
            continue
        seen.add(key)
        if not os.path.isfile(p) or inside(p, root) or inside(p, folder):
            out.append(e)
            continue
        ext = os.path.splitext(p)[1] or ".png"
        dest, k = free_scene_image_path(folder, scene_no, ext, start=k)
        copy(p, dest)
        k += 1
        new = os.path.abspath(dest)
        seen.add(norm(new))
        out.append(_with_path(e, new, os.path.abspath(p)))
        copied += 1
    scene[REF_FIELD] = out
    return copied


def merge_legacy_page(scene: dict, folder: str, *, first: bool) -> bool:
    """旧记录：这一场 episode_page 指着本集图片库里的一张页图 → 并进 ref_images。

    first=True 放最前面（选图时：这就是这一场现在的图）；False 接在最后（建项目时 ref_images 优先）。
    已经在列表里就不动。返回有没有改。
    """
    if not isinstance(scene, dict):
        return False
    path = page_file(folder, scene.get("episode_page"))
    if not path:
        return False
    if norm(path) in {norm(entry_path(e)) for e in ref_entries(scene)}:
        return False
    rec = {"path": path, "source": "page"}
    refs = list(ref_entries(scene))
    if first:
        refs.insert(0, rec)
    else:
        refs.append(rec)
    scene[REF_FIELD] = refs
    return True


def select_ref_image(scene: dict, path: str, *, source: str = "picked") -> list:
    """选中的图放到这一场 ref_images 最前面（不在列表里就加进来）。不改文件名、不复制。"""
    path = os.path.abspath(path)
    key = norm(path)
    refs = list(ref_entries(scene))
    hit = None
    for e in refs:
        if norm(entry_path(e)) == key:
            hit = e
            break
    if hit is not None:
        refs.remove(hit)
    else:
        hit = {"path": path, "source": source}
    refs.insert(0, hit)
    scene[REF_FIELD] = refs
    return refs


def _folder_images(folder: str) -> list:
    """folder 里的图：编号页图按编号，<场>_<k> 按场和序号。别的图（封面等）不算。"""
    if not folder or not os.path.isdir(folder):
        return []
    scene_imgs = []
    best: dict = {}
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in IMAGE_EXTS or name.startswith("."):
            continue
        p = os.path.abspath(os.path.join(folder, name))
        if stem.isdigit() and ext in _PAGE_RANK:
            n = int(stem)
            if n not in best or _PAGE_RANK[ext] < best[n][0]:
                best[n] = (_PAGE_RANK[ext], p)
            continue
        m = _SCENE_NAME_RE.match(stem)
        if m:
            scene_imgs.append(((int(m.group(1)), int(m.group(2))), p))
    pages = [best[n][1] for n in sorted(best)]
    return pages + [p for _k, p in sorted(scene_imgs)]


def image_pool(scenes: list, extra_folders=()) -> list:
    """选图翻页用的图：按场景顺序，每一场自己的 ref_images（还在的）；然后是这些文件夹里还没出现过的图。"""
    out, seen = [], set()
    for sc in scenes or []:
        if not isinstance(sc, dict):
            continue
        for p in scene_ref_paths(sc):
            k = norm(p)
            if k not in seen:
                seen.add(k)
                out.append(p)
    for folder in extra_folders or ():
        for p in _folder_images(folder):
            k = norm(p)
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def start_index(pool: list, scene: dict) -> int:
    """打开选图时先停在这一场自己的第一张图。没有就 0。"""
    keys = [norm(p) for p in pool]
    for p in scene_ref_paths(scene):
        k = norm(p)
        if k in keys:
            return keys.index(k)
    return 0


def image_users(scenes: list, path: str) -> list:
    """哪些场景的 ref_images 里有这张图：[(场景下标, 是不是那一场的当前图)]。"""
    key = norm(path)
    out = []
    for i, sc in enumerate(scenes or []):
        paths = [norm(p) for p in scene_ref_paths(sc, existing_only=False)]
        if key in paths:
            out.append((i, paths.index(key) == 0))
    return out


def transfer_ref_images(scene: dict, src_dir: str, dest_dir: str, done: dict, *, next_page=None,
                        copy=shutil.copy2) -> int:
    """分集 / 挪集：这一场 ref_images 里在 src_dir 里面的图复制进 dest_dir，路径改到新文件（一律复制，不移动不删）。

    done：{旧路径规范化: 新路径}，同一个文件只复制一次（编号页图已经被搬过的也在里面）。
    编号页图（纯数字名）要接着 dest 的页号走，用 next_page() 拿新号；其它图保留原名，重名时加 _2、_3。
    返回这次复制了几张。
    """
    refs = ref_entries(scene)
    if not refs:
        return 0
    out, copied = [], 0
    for e in refs:
        p = entry_path(e)
        if not p:
            out.append(e)
            continue
        key = norm(p)
        if key in done:
            out.append(_with_path(e, done[key]))
            continue
        if not inside(p, src_dir) or not os.path.isfile(p):
            out.append(e)
            continue
        stem, ext = os.path.splitext(os.path.basename(p))
        if stem.isdigit() and ext.lower() in _PAGE_RANK and next_page is not None:
            dest = os.path.join(dest_dir, f"{int(next_page())}{ext.lower()}")
        else:
            dest = os.path.join(dest_dir, os.path.relpath(os.path.abspath(p), os.path.abspath(src_dir)))
        dest = _free_path(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        copy(p, dest)
        dest = os.path.abspath(dest)
        done[key] = dest
        out.append(_with_path(e, dest))
        copied += 1
    scene[REF_FIELD] = out
    return copied


def rename_ref_dir(scene: dict, old_dir: str, new_dir: str) -> int:
    """文件夹整个改名后：ref_images 里指向旧文件夹里面的路径改到新文件夹。"""
    n = 0
    refs = ref_entries(scene)
    for i, e in enumerate(refs):
        p = entry_path(e)
        if p and inside(p, old_dir):
            new = os.path.join(new_dir, os.path.relpath(os.path.abspath(p), os.path.abspath(old_dir)))
            refs[i] = _with_path(e, new) if isinstance(e, dict) else new
            n += 1
    return n


def _free_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"
