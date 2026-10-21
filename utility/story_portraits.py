"""故事人物形象图归位：人物图放在项目自己的 avatar 目录；只有故事还没有项目时才放 AVATAR_PATH/story。

- ``adopt_story_portraits``：运行时用（故事预览打开时 / 建项目后），把这个故事人物在 avatar/story 里的图
  复制进项目 avatar（不删原图，因为别的故事可能也用这个名字）。
- 命令行迁移：python -m utility.story_portraits [--apply]
  默认 dry-run。--apply 时先把 avatar/story 整个备份到 avatar/_backup_story_<时间>，
  属于唯一一个项目的图搬过去，被多个项目用的图复制到每个项目并保留原图，不属于任何项目的图不动；
  列表 JSON / scenes.json 里指向搬走文件的绝对路径一并改写（改之前各自备份一份 .bak_portraits_<时间>）。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from datetime import datetime

import config
import project_manager
from utility.content_pdf import portrait_stem

_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def story_avatar_root() -> str:
    return os.path.join(config.AVATAR_PATH, "story")


def person_names(actor_text: str) -> list[str]:
    """名单文字里的「人物」（不含讲员 / 不出现），按顺序。"""
    out = []
    try:
        rows = project_manager.active_actor_entries(project_manager.actor_text_for_generation(actor_text or ""))
    except Exception:  # noqa: BLE001
        return out
    for row in rows:
        if row.get("role") == "host":
            continue
        body, _m = project_manager.split_actor_motion((row.get("body") or "").strip())
        body = body.strip()
        if body and not project_manager.actor_is_absent(body) and body not in out:
            out.append(body)
    return out


def story_portrait_files(names) -> list[str]:
    """avatar/story（含风格子目录）里属于这些名字的图。"""
    root = story_avatar_root()
    if not os.path.isdir(root):
        return []
    stems = {portrait_stem(n) for n in names if n}
    found = []
    for d, _dirs, files in os.walk(root):
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext.lower() in _EXTS and stem in stems:
                found.append(os.path.join(d, f))
    return sorted(found)


def _dest_for(src: str, avatar_dir: str) -> str:
    rel = os.path.relpath(src, story_avatar_root())  # 保留风格子目录
    return os.path.join(avatar_dir, rel)


def adopt_story_portraits(avatar_dir: str, actor_texts, *, move: bool = False) -> list[tuple[str, str]]:
    """把这些名单里人物在 avatar/story 的图放进 avatar_dir（已有同名就不覆盖）。返回 [(源, 目标)]。"""
    if not avatar_dir:
        return []
    names = []
    for t in actor_texts or []:
        if isinstance(t, str):
            names += [n for n in person_names(t) if n not in names]
    done = []
    for src in story_portrait_files(names):
        dest = _dest_for(src, avatar_dir)
        if os.path.exists(dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        (shutil.move if move else shutil.copy2)(src, dest)
        done.append((src, dest))
    return done


# ---------------------------------------------------------------- 迁移 ----
def _walk_strings(v, fn):
    """把 JSON 里每个字符串交给 fn（返回新串或 None），返回 (新值, 改了几处)。"""
    if isinstance(v, str):
        new = fn(v)
        return (new, 1) if new is not None and new != v else (v, 0)
    if isinstance(v, list):
        n = 0
        out = []
        for x in v:
            y, k = _walk_strings(x, fn)
            out.append(y)
            n += k
        return out, n
    if isinstance(v, dict):
        n = 0
        out = {}
        for key, x in v.items():
            y, k = _walk_strings(x, fn)
            out[key] = y
            n += k
        return out, n
    return v, 0


def _project_dir(channel_dir: str, pid: str) -> str:
    p = os.path.join(channel_dir, "project", pid)
    return p if os.path.isdir(p) else ""


def _scene_actor_texts(project_dir: str) -> list[str]:
    path = os.path.join(project_dir, "scenes.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    scenes = data if isinstance(data, list) else (data.get("scenes") if isinstance(data, dict) else [])
    return [s.get("actor") for s in scenes or [] if isinstance(s, dict) and isinstance(s.get("actor"), str)]


def _locked(path: str) -> bool:
    try:
        with open(path, "a+b"):
            return False
    except OSError:
        return True


def migrate(apply: bool = False) -> dict:
    root = story_avatar_root()
    program = config.BASE_PROGRAM_PATH
    report = {"apply": apply, "moved": [], "copied": [], "left": [], "refs": {}, "backups": [], "locked": [],
              "projects": {}}
    if not os.path.isdir(root):
        return report
    # 1) 每个项目：用到了哪些人物名（列表行 story_actors / 项目 profile + 项目 scenes.json）
    proj_names: dict[str, set] = {}
    list_files = sorted(set(glob.glob(os.path.join(program, "*", "list*", "*.json"))))
    for lf in list_files:
        channel_dir = os.path.dirname(os.path.dirname(lf))
        try:
            with open(lf, encoding="utf-8") as fh:
                rows = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            pid = project_manager.list_json_row_workflow_pid(row)
            pdir = _project_dir(channel_dir, pid) if pid else ""
            if not pdir:
                continue
            texts = [row.get("story_actors")]
            prof = row.get(project_manager.PROJECT_PROFILE_KEY)
            if isinstance(prof, dict):
                texts.append(prof.get("story_actors"))
            texts += _scene_actor_texts(pdir)
            names = proj_names.setdefault(pdir, set())
            for t in texts:
                if isinstance(t, str):
                    names.update(person_names(t))
    # 2) 每张图属于哪些项目
    owners: dict[str, list] = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext.lower() not in _EXTS:
                continue
            src = os.path.join(d, f)
            owners[src] = sorted(p for p, ns in proj_names.items() if stem in {portrait_stem(n) for n in ns})
    report["projects"] = {p: sorted(n) for p, n in proj_names.items() if any(p in o for o in owners.values())}
    for src, projs in owners.items():
        if not projs:
            report["left"].append(src)
            continue
        if _locked(src):
            report["locked"].append(src)
    if apply and report["locked"]:
        return report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if apply and any(owners.values()):
        bdir = os.path.join(config.AVATAR_PATH, f"_backup_story_{ts}")
        shutil.copytree(root, bdir)
        report["backups"].append(bdir)
    # 3) 搬 / 复制
    remap: dict[str, str] = {}
    for src, projs in owners.items():
        if not projs:
            continue
        dests = [_dest_for(src, os.path.join(p, "avatar")) for p in projs]
        for dest in dests:
            if apply:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not os.path.exists(dest):
                    shutil.copy2(src, dest)
        if len(projs) == 1:
            report["moved"].append((src, dests[0]))
            remap[os.path.normcase(os.path.abspath(src))] = dests[0]
            if apply and os.path.exists(dests[0]):
                os.remove(src)
        else:
            report["copied"].append((src, dests))
    # 4) 改写记录里的绝对路径（只改搬走的；复制的原图还在，路径照样有效）
    def fix(s: str):
        if not s or not os.path.splitext(s)[1]:
            return None
        try:
            key = os.path.normcase(os.path.abspath(s))
        except (TypeError, ValueError):
            return None
        return remap.get(key)

    targets = list_files + [os.path.join(p, "scenes.json") for p in proj_names]
    for path in targets:
        if not remap or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        new, n = _walk_strings(data, fix)
        if not n:
            continue
        report["refs"][path] = n
        if apply:
            if _locked(path):
                report["locked"].append(path)
                continue
            bak = f"{path}.bak_portraits_{ts}"
            shutil.copy2(path, bak)
            report["backups"].append(bak)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=2)
    return report


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rep = migrate(apply="--apply" in argv)
    print(("APPLY" if rep["apply"] else "DRY-RUN") + f"  story root: {story_avatar_root()}")
    for p, names in rep["projects"].items():
        print(f"  project {p}: persons {names}")
    for src, dest in rep["moved"]:
        print(f"  MOVE  {src}\n     -> {dest}")
    for src, dests in rep["copied"]:
        print(f"  COPY  {src}  (kept)\n     -> " + "\n     -> ".join(dests))
    for src in rep["left"]:
        print(f"  LEAVE {src}  (no project)")
    for path, n in rep["refs"].items():
        print(f"  REFS  {n} in {path}")
    for p in rep["locked"]:
        print(f"  LOCKED {p}")
    for b in rep["backups"]:
        print(f"  BACKUP {b}")
    print(f"moved={len(rep['moved'])} copied={len(rep['copied'])} left={len(rep['left'])} "
          f"ref_files={len(rep['refs'])} locked={len(rep['locked'])}")
    return 1 if rep["locked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())