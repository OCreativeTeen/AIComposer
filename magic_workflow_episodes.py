"""调整集 / 合并集：场景在相邻两集之间挪动、或整集合并时，连带处理这一集的图片库和 PDF 导入记录。集号是身份，一旦用过就不改；界面按 scenes.json 顺序显示第几集。

每集的东西都在 media/<集号>/ 里：编号页图（1.webp、2.webp…，是这一集的图片库）、<集号>.pdf、.<集号>.codec、
pdf_imports.json。场景自己的视频/音频/图（clip、zero、back…）放在 media/ 根目录，不分集，挪集时不用动。
"""
import json
import os
import shutil
from datetime import datetime

import config

_PAGE_EXTS = (".webp", ".jpg", ".jpeg", ".png")
EPISODE_TRASH_ROOT = r"D:\AI_MEDIA\working\_trash"
_GROUP_KEYS = ("group", "group_page", "group_pdf")


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _inside(path_norm: str, folder_norm: str) -> bool:
    return path_norm.startswith(folder_norm.rstrip("\\/") + os.sep)


def _free_path(path: str) -> str:
    """path 已经有文件时，改成 名字_2.扩展名、名字_3.扩展名……"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"


class EpisodeOpsMixin:
    """给 MagicWorkflow 用：要有 pid、scenes、scene_group、episode_media_dir、pdf_import_history 等。"""

    last_episode_op: dict = {}

    # ---- 小工具 ---------------------------------------------------------------------
    @staticmethod
    def _scene_page_no(scene) -> int:
        try:
            n = int(scene.get("episode_page") or 0)
        except (TypeError, ValueError, AttributeError):
            n = 0
        return n if n > 0 else 0

    def _page_files(self, episode: str, page: int) -> list[str]:
        folder = self.episode_media_dir(episode)
        out = []
        for ext in _PAGE_EXTS:
            p = os.path.join(folder, f"{page}{ext}")
            if os.path.isfile(p):
                out.append(p)
        return out

    def _episode_used_pages(self, episode: str) -> set[int]:
        """这一集图片库里已有的编号，加上这一集场景记着的页码。"""
        used: set[int] = set()
        folder = self.episode_media_dir(episode)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                stem, ext = os.path.splitext(name)
                if stem.isdigit() and ext.lower() in _PAGE_EXTS:
                    used.add(int(stem))
        for sc in self.scenes or []:
            if isinstance(sc, dict) and self.scene_group(sc) == episode:
                n = self._scene_page_no(sc)
                if n:
                    used.add(n)
        return used

    def referenced_paths(self) -> set[str]:
        """所有场景（所有集）里写着的文件路径，规范化后的集合。"""
        refs: set[str] = set()

        def walk(v):
            if isinstance(v, str):
                s = v.strip()
                if s and os.path.splitext(s)[1] and ("/" in s or "\\" in s):
                    try:
                        refs.add(_norm(s))
                    except (TypeError, ValueError):
                        pass
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)

        for sc in self.scenes or []:
            walk(sc)
        return refs

    def _numbered_page_refs(self) -> set[str]:
        """各集场景 episode_page 指着的页图（规范化路径）。"""
        out: set[str] = set()
        for sc in self.scenes or []:
            if not isinstance(sc, dict):
                continue
            n = self._scene_page_no(sc)
            if n:
                for p in self._page_files(self.scene_group(sc), n):
                    out.add(_norm(p))
        return out

    # ---- 备份 -----------------------------------------------------------------------
    def backup_episode_files(self, episodes: list[str], tag: str) -> list[str]:
        """动集之前：scenes.json 和这几集的 pdf_imports.json 拷一份到项目的 _backup/ 里（带时间）。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        scenes_path = config.get_scenes_path(self.pid)
        bdir = os.path.join(os.path.dirname(os.path.abspath(scenes_path)), "_backup")
        os.makedirs(bdir, exist_ok=True)
        out: list[str] = []
        # 先把内存里的场景写盘，备份的就是动之前的样子。
        try:
            self.save_scenes_to_json()
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 调整集备份前保存场景失败: {e}")
        if os.path.isfile(scenes_path):
            dest = os.path.join(bdir, f"scenes_{ts}_{tag}.json")
            shutil.copy2(scenes_path, dest)
            out.append(dest)
        for ep in dict.fromkeys(e for e in episodes if e):
            src = self.pdf_import_history_path(ep)
            if os.path.isfile(src):
                dest = os.path.join(bdir, f"pdf_imports_ep{ep}_{ts}_{tag}.json")
                shutil.copy2(src, dest)
                out.append(dest)
        return out

    # ---- 挪文件 ---------------------------------------------------------------------
    def _move_scene_pages(self, moving: list, src_ep: str, dest_ep: str) -> dict:
        """moving 里的场景（还在 src_ep）记着的页图搬到 dest_ep 的图片库，接在最大编号后面，不覆盖。

        同一页还被 src_ep 里留下的场景用着时只复制。返回 {"moved": [(旧, 新)], "copied": [...],
        "missing": [旧页码], "files": {旧路径规范化: 新路径}}。
        """
        moving_ids = {id(s) for s in moving}
        stay_pages = {
            self._scene_page_no(s)
            for s in self.scenes or []
            if isinstance(s, dict) and id(s) not in moving_ids and self.scene_group(s) == src_ep
        }
        used = self._episode_used_pages(dest_ep)
        nxt = (max(used) if used else 0) + 1
        dest_dir = self.episode_media_dir(dest_ep)
        mapping: dict[int, int | None] = {}
        res = {"moved": [], "copied": [], "missing": [], "files": {}}
        for sc in moving:
            old = self._scene_page_no(sc)
            if not old:
                continue
            if old not in mapping:
                files = self._page_files(src_ep, old)
                if not files:
                    mapping[old] = None
                    res["missing"].append(old)
                else:
                    new = nxt
                    nxt += 1
                    os.makedirs(dest_dir, exist_ok=True)
                    keep = old in stay_pages
                    for f in files:
                        d = _free_path(os.path.join(dest_dir, f"{new}{os.path.splitext(f)[1].lower()}"))
                        if keep:
                            shutil.copy2(f, d)
                        else:
                            shutil.move(f, d)
                        res["files"][_norm(f)] = d
                    mapping[old] = new
                    res["copied" if keep else "moved"].append((old, new))
            new = mapping[old]
            if new is None:
                sc.pop("episode_page", None)  # 图早就不在了，别让旧页码误指到目标集别的图
            else:
                sc["episode_page"] = new
        return res

    def _move_folder_refs(self, moving: list, src_dir: str, dest_dir: str, already: dict) -> int:
        """moving 场景里指向 src_dir 里面的文件路径：文件搬进 dest_dir（重名就改名），路径跟着改。"""
        src = _norm(src_dir)
        moving_ids = {id(s) for s in moving}
        done: dict[str, str] = dict(already or {})
        count = 0

        def still_used_elsewhere(pn: str) -> bool:
            for other in self.scenes or []:
                if not isinstance(other, dict) or id(other) in moving_ids:
                    continue
                for v in other.values():
                    if isinstance(v, str) and v.strip():
                        try:
                            if _norm(v) == pn:
                                return True
                        except (TypeError, ValueError):
                            continue
            return False

        for sc in moving:
            for k, v in list(sc.items()):
                if not isinstance(v, str) or not v.strip():
                    continue
                try:
                    pn = _norm(v)
                except (TypeError, ValueError):
                    continue
                if not _inside(pn, src):
                    continue
                if pn in done:
                    sc[k] = done[pn]
                    continue
                if not os.path.isfile(v):
                    continue
                dest = _free_path(os.path.join(dest_dir, os.path.relpath(pn, src)))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if still_used_elsewhere(pn):
                    shutil.copy2(v, dest)
                else:
                    shutil.move(v, dest)
                done[pn] = dest
                sc[k] = dest
                count += 1
        return count

    def _rename_folder_refs(self, old_dir: str, new_dir: str) -> int:
        """文件夹整个改名后：所有场景里指向旧文件夹里面的路径改成新文件夹。"""
        old = _norm(old_dir)
        n = 0
        for sc in self.scenes or []:
            if not isinstance(sc, dict):
                continue
            for k, v in list(sc.items()):
                if not isinstance(v, str) or not v.strip():
                    continue
                try:
                    pn = _norm(v)
                except (TypeError, ValueError):
                    continue
                if _inside(pn, old):
                    sc[k] = os.path.join(new_dir, os.path.relpath(pn, old))
                    n += 1
        return n

    def _relabel_scenes(self, moving: list, src_ep: str, dest_ep: str) -> None:
        for sc in moving:
            sc["episode"] = dest_ep
            for key in _GROUP_KEYS:
                sc.pop(key, None)
            if str(sc.get("episode_pdf") or "").strip() == f"{src_ep}.pdf":
                sc["episode_pdf"] = f"{dest_ep}.pdf"

    def _share_target_zero(self, moving: list, target: str) -> None:
        """同一集的场景共用一份 zero：搬过来的场景用目标集里的那一份（原来的做法）。"""
        moving_ids = {id(s) for s in moving}
        ref = next(
            (
                s for s in self.scenes or []
                if isinstance(s, dict)
                and self.scene_group(s) == target
                and id(s) not in moving_ids
                and (s.get("zero") or s.get("zero_audio"))
            ),
            None,
        )
        if ref is None:
            return
        for sc in moving:
            for key in ("zero", "zero_audio"):
                if ref.get(key):
                    sc[key] = ref[key]

    def _transfer_scenes(self, moving: list, src_ep: str, dest_ep: str) -> dict:
        pages = self._move_scene_pages(moving, src_ep, dest_ep)
        refs = self._move_folder_refs(
            moving, self.episode_media_dir(src_ep), self.episode_media_dir(dest_ep), pages["files"]
        )
        self._share_target_zero(moving, dest_ep)
        self._relabel_scenes(moving, src_ep, dest_ep)
        return {
            "pages_moved": pages["moved"],
            "pages_copied": pages["copied"],
            "pages_missing": pages["missing"],
            "other_files_moved": refs,
        }

    # ---- 一集没有场景了：并记录、挪开剩下的文件、后面的集号往前补 ----------------------------
    def _merge_pdf_imports(self, kept: str, absorbed: str) -> int:
        add = self.pdf_import_history(absorbed)
        if not add:
            return 0
        items: list[dict] = []
        seen: set[str] = set()
        for e in sorted(
            self.pdf_import_history(kept) + add,
            key=lambda e: str(e.get("imported_at") or ""),
            reverse=True,
        ):
            key = _norm(e.get("split_dir") or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(e)
        self._save_pdf_import_history(kept, items)  # 里面截到最多 PDF_IMPORT_HISTORY_CAP 条
        return len(add)

    def folder_leftovers(self, folder: str) -> list[str]:
        """文件夹里没有任何场景用着的文件（递归）。"""
        if not folder or not os.path.isdir(folder):
            return []
        refs = self.referenced_paths() | self._numbered_page_refs()
        out = []
        for d, _dirs, files in os.walk(folder):
            for name in files:
                p = os.path.join(d, name)
                if _norm(p) not in refs:
                    out.append(p)
        return sorted(out)

    def _retire_episode(self, absorbed: str, kept: str) -> dict:
        """absorbed 这一集已经没有场景了：PDF 导入记录并进 kept，文件夹挪成 media/_merged_ep<集>_<时间>/
        （只剩没用到的文件，等用户确认再删），后面的集号往前补。"""
        info = {
            "pdf_imports_merged": self._merge_pdf_imports(kept, absorbed),
            "absorbed_pdf": os.path.isfile(self.episode_pdf_path(absorbed)),
            "absorbed_history": len(self.pdf_import_history(absorbed)),
            "leftover_dir": "",
            "leftovers": [],
            "renamed": [],
            "renumber_skipped": "",
        }
        folder = self.episode_media_dir(absorbed)
        freed = True
        if os.path.isdir(folder):
            if not os.listdir(folder):
                try:
                    os.rmdir(folder)
                except OSError:
                    freed = False
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                aside = os.path.join(config.get_media_path(self.pid), f"_merged_ep{absorbed}_{ts}")
                try:
                    os.rename(folder, aside)
                    self._rename_folder_refs(folder, aside)
                    folder = aside
                except OSError as e:
                    freed = False
                    info["renumber_skipped"] = f"第 {absorbed} 集文件夹挪不开（{e}），剩下的文件还在原处。"
                info["leftover_dir"] = folder
                info["leftovers"] = self.folder_leftovers(folder)
        # 集号不再往前补：并掉的集号空着不用，别的集的文件夹和路径都不变。
        return info

    def trash_leftovers(self, folder: str, episode_label: str) -> dict:
        """删掉文件夹里没用到的文件：有 send2trash 就进回收站，没有就挪到
        D:\\AI_MEDIA\\working\\_trash\\<项目>_<集>_<时间>\\。还被场景用着的文件一律不动。删空后去掉文件夹。"""
        try:
            from send2trash import send2trash  # type: ignore
        except ImportError:
            send2trash = None
        files = self.folder_leftovers(folder)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_dir = "" if send2trash else os.path.join(EPISODE_TRASH_ROOT, f"{self.pid}_{episode_label}_{ts}")
        done = 0
        failed: list[str] = []
        for f in files:
            try:
                if send2trash:
                    send2trash(f)
                else:
                    dest = _free_path(os.path.join(trash_dir, os.path.relpath(f, folder)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(f, dest)
                done += 1
            except Exception as e:  # noqa: BLE001
                failed.append(f"{os.path.basename(f)}: {e}")
        for d, _dirs, _files in sorted(os.walk(folder), key=lambda t: len(t[0]), reverse=True):
            try:
                os.rmdir(d)
            except OSError:
                pass
        return {
            "method": "recycle_bin" if send2trash else "trash_dir",
            "trash_dir": trash_dir,
            "count": done,
            "failed": failed,
            "folder_removed": not os.path.isdir(folder),
        }

    # ---- 两个动作 --------------------------------------------------------------------
    def move_to_adjacent_episode(self, index: int, direction: str) -> tuple[str, str]:
        """手动调整集的边界。

        direction == "prev"：本集开头到当前场景（含当前场景）并进上一集（接在上一集最后）。
        direction == "next"：本集里从当前场景（含）起到本集结束的场景并进下一集（放在下一集最前）。
        搬过去的场景的页图搬进目标集的图片库（接在最大编号后面，不覆盖；还被本集留下的场景用着就复制），
        留下的场景页码不动。本集因此没有场景了，就按合并处理（记录并过去、剩下文件等确认、后面集号往前补）。
        成功返回 (目标集号, "")，否则 ("", 原因)。细节在 self.last_episode_op。
        """
        scenes = self.scenes or []
        start, end = self.episode_run_bounds(index)
        if start < 0:
            return "", "没有当前场景。"
        cur_name = self.scene_group(scenes[index])
        if direction == "prev":
            if start == 0:
                return "", "没有上一集。"
            moved = list(range(start, index + 1))
            target = self.scene_group(scenes[start - 1])
        elif direction == "next":
            if end >= len(scenes) - 1:
                return "", "没有下一集。"
            moved = list(range(index, end + 1))
            target = self.scene_group(scenes[end + 1])
        else:
            return "", "不认识的方向。"
        if not target or target == cur_name:
            return "", "找不到相邻的集。"
        if len(moved) >= end - start + 1:
            other = "上一集" if direction == "prev" else "下一集"
            return "", f"这样会把第 {cur_name} 集整集挪空。整集移走请用『与{other}合并』。"

        backups = self.backup_episode_files([cur_name, target], f"move_{direction}")
        moving = [scenes[i] for i in moved]
        info = {"op": f"move_{direction}", "source": cur_name, "target": target, "scenes": len(moving),
                "backups": backups}
        info.update(self._transfer_scenes(moving, cur_name, target))
        emptied = not any(isinstance(s, dict) and self.scene_group(s) == cur_name for s in scenes)
        info["source_emptied"] = emptied
        final = target
        if emptied:
            info.update(self._retire_episode(cur_name, target))
            for n, m in info.get("renamed") or []:
                if str(n) == final:
                    final = str(m)
                    break
        info["target_final"] = final
        self.touch_episode_media(final)
        if not emptied:
            self.touch_episode_media(cur_name)
        self.last_episode_op = info
        return final, ""

    def merge_adjacent_episode(self, index: int, direction: str) -> tuple[str, str]:
        """整集合并。direction == "prev"：本集接在上一集后面（留上一集）；"next"：下一集接在本集后面（留本集）。

        并过来的场景按原顺序接在留下那一集最后；页图搬进留下那一集的图片库（接在最大编号后面）；
        PDF 导入记录合并（新的在前，最多 20 条）；并掉那一集的文件夹挪开等确认删；后面的集号往前补。
        成功返回 (留下那一集最后的集号, "")。细节在 self.last_episode_op。
        """
        scenes = self.scenes or []
        start, end = self.episode_run_bounds(index)
        if start < 0:
            return "", "没有当前场景。"
        cur_name = self.scene_group(scenes[index])
        if direction == "prev":
            if start == 0:
                return "", "没有上一集。"
            kept, absorbed = self.scene_group(scenes[start - 1]), cur_name
        elif direction == "next":
            if end >= len(scenes) - 1:
                return "", "没有下一集。"
            kept, absorbed = cur_name, self.scene_group(scenes[end + 1])
        else:
            return "", "不认识的方向。"
        if not kept or not absorbed or kept == absorbed:
            return "", "找不到相邻的集。"

        backups = self.backup_episode_files([kept, absorbed], f"merge_{direction}")
        moving = [s for s in scenes if isinstance(s, dict) and self.scene_group(s) == absorbed]
        # 并过来的场景按原顺序接在留下那一集最后一场后面（相邻两集本来就挨着，一般不用挪）。
        moving_ids = {id(s) for s in moving}
        rest = [s for s in scenes if id(s) not in moving_ids]
        last_kept = max(i for i, s in enumerate(rest) if isinstance(s, dict) and self.scene_group(s) == kept)
        reordered = rest[: last_kept + 1] + moving + rest[last_kept + 1:]
        info = {"op": f"merge_{direction}", "kept": kept, "absorbed": absorbed, "scenes": len(moving),
                "kept_scenes_before": sum(1 for s in rest if isinstance(s, dict) and self.scene_group(s) == kept),
                "reordered": any(a is not b for a, b in zip(reordered, scenes)), "backups": backups}
        scenes[:] = reordered
        info.update(self._transfer_scenes(moving, absorbed, kept))
        info.update(self._retire_episode(absorbed, kept))
        final = kept
        for n, m in info.get("renamed") or []:
            if str(n) == final:
                final = str(m)
                break
        info["kept_final"] = final
        self.touch_episode_media(final)
        self.last_episode_op = info
        return final, ""


    # ---- 从本场之后分成新一集 -----------------------------------------------------------
    def split_episode_after(self, index: int) -> tuple[str, str]:
        """当前场景和它前面的留在本集；后面的场景成为新的一集，紧接在本集后面（scenes.json 顺序不变）。

        新集号 = 用过的最大集号 + 1（``next_group_name``），别的集一律不改号，文件夹不动。
        搬走的场景的页图和本集文件夹里的其他文件搬进新集文件夹（还被留下的场景用着就复制），路径跟着改。
        成功返回 (新集号, "")，否则 ("", 原因)。细节在 self.last_episode_op。
        """
        scenes = self.scenes or []
        start, end = self.episode_run_bounds(index)
        if start < 0:
            return "", "没有当前场景。"
        if index >= end:
            return "", "当前场景是本集最后一场，后面没有场景可以分出去。"
        cur = self.scene_group(scenes[index])
        new_ep = self.next_group_name()
        new_dir = self.episode_media_dir(new_ep)
        if os.path.exists(new_dir) or any(isinstance(s, dict) and self.scene_group(s) == new_ep for s in scenes):
            return "", f"新集号 #{new_ep} 已经被占着（media/{new_ep} 或场景），没有分集。"
        backups = self.backup_episode_files([cur], "split_after")
        moving = scenes[index + 1 : end + 1]
        os.makedirs(new_dir, exist_ok=True)
        try:
            info = self._transfer_scenes(moving, cur, new_ep)
        except OSError as e:
            return "", f"搬文件到新集文件夹时失败（{e}）。scenes.json 还没保存，可以用 _backup 里的备份对照。"
        hist = self.pdf_import_history_path(new_ep)
        with open(hist, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 1,
                    "imports": [],
                    "split_from": {
                        "episode": cur,
                        "after_scene": index - start + 1,
                        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        self.touch_episode_media(cur)
        self.touch_episode_media(new_ep)
        self.last_episode_op = {
            "op": "split_after", "source": cur, "new": new_ep, "scenes": len(moving),
            "pages_moved": info.get("pages_moved"), "pages_copied": info.get("pages_copied"),
            "pages_missing": info.get("pages_missing"), "other_files_moved": info.get("other_files_moved"),
            "renamed": [], "backups": backups,
        }
        return new_ep, ""
