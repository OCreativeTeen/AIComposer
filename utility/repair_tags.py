"""t447u: 一次性修复坏掉的 tags（列表被写成字符串、来回存了几层、被逗号切碎）。

用法（在 D:\\AIComposer 下）::

    .\\venv\\Scripts\\python.exe -m utility.repair_tags --dry-run      # 只统计，不改文件
    .\\venv\\Scripts\\python.exe -m utility.repair_tags                # 真修：每个要改的文件先备份成 <文件>.bak_tags_<时间>

默认扫媒体根目录（config.BASE_MEDIA_PATH）下所有 .json（跳过 _backup / temp / .git 目录和备份文件），
可以用 --root 指定别的目录（可多次）。只动名为 "tags" 的字段，而且只动两种：
  * 字符串（"a, b"、"['a', 'b']" …）→ 列表；
  * 列表里有坏掉的项（两头带 [ ] ' " \\ ）→ 清理成干净列表。
干净的列表一律不动。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utility.tags_text import normalize_tags  # noqa: E402

SKIP_DIRS = {"_backup", "temp", ".git", "__pycache__", "node_modules", "venv", ".venv"}
# 这些文件里的 tags 本来就是显示用的文字（例如 CLI 队列 video_choice_queue.json），不改
SKIP_FILES = {"video_choice_queue.json"}
MAX_BYTES = 200 * 1024 * 1024
_BAD_EDGE = ("[", "]", "'", '"', "\\")


def tags_need_fix(value) -> str:
    """要修返回 "string" / "broken"，不用修返回 ""。"""
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        for t in value:
            if not isinstance(t, str):
                return "broken"
            s = t.strip()
            if s != t or s.startswith(_BAD_EDGE) or s.endswith(_BAD_EDGE):
                return "broken"
    return ""


def fix_tags_in(data, stats: dict, samples: list, where: str = ""):
    """递归修 data 里所有 "tags" 字段（原地改）。返回改了几处。"""
    n = 0
    if isinstance(data, dict):
        for k, v in list(data.items()):
            if k == "tags":
                kind = tags_need_fix(v)
                if kind:
                    new = normalize_tags(v)
                    data[k] = new
                    stats[kind] = stats.get(kind, 0) + 1
                    n += 1
                    if len(samples) < 12:
                        samples.append((where, repr(v)[:160], new))
                    continue
            n += fix_tags_in(v, stats, samples, where)
    elif isinstance(data, list):
        for x in data:
            n += fix_tags_in(x, stats, samples, where)
    return n


def iter_json_files(roots):
    for root in roots:
        if os.path.isfile(root) and root.lower().endswith(".json"):
            yield root
            continue
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            for f in files:
                low = f.lower()
                if not low.endswith(".json") or ".bak" in low or low in SKIP_FILES:
                    continue
                yield os.path.join(d, f)


def _indent_of(text: str):
    for line in text.splitlines()[1:6]:
        stripped = line.lstrip(" ")
        if stripped and len(stripped) < len(line):
            return len(line) - len(stripped)
        if line.startswith("\t"):
            return "\t"
    return None


def repair(roots, dry_run: bool = True, out=print) -> dict:
    stats = {"files_scanned": 0, "files_changed": 0, "string": 0, "broken": 0, "unreadable": 0}
    samples: list = []
    changed_files: list = []
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for path in iter_json_files(roots):
        try:
            if os.path.getsize(path) > MAX_BYTES:
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            text = raw.decode("utf-8-sig")
            if '"tags"' not in text:
                stats["files_scanned"] += 1
                continue
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            stats["unreadable"] += 1
            continue
        stats["files_scanned"] += 1
        n = fix_tags_in(data, stats, samples, path)
        if not n:
            continue
        stats["files_changed"] += 1
        changed_files.append((path, n))
        if dry_run:
            continue
        bak = f"{path}.bak_tags_{stamp}"
        shutil.copy2(path, bak)
        nl = "\r\n" if b"\r\n" in raw else "\n"
        body = json.dumps(data, ensure_ascii=False, indent=_indent_of(text))
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(body.replace("\n", nl) + (nl if text.endswith(("\n",)) else ""))
    stats["fields"] = stats["string"] + stats["broken"]
    out(("[dry-run] " if dry_run else "") + "扫描 JSON 文件 %(files_scanned)d 个，读不了 %(unreadable)d 个" % stats)
    out("要修的文件 %(files_changed)d 个；tags 字段 %(fields)d 处：字符串→列表 %(string)d，坏掉的列表 %(broken)d" % stats)
    for path, n in changed_files[:40]:
        out(f"  {n:4d}  {path}")
    if len(changed_files) > 40:
        out(f"  … 还有 {len(changed_files) - 40} 个文件")
    if samples:
        out("例子（原值 → 修好）：")
        for where, old, new in samples:
            out(f"  {os.path.basename(where)}: {old}  →  {new}")
    if not dry_run and changed_files:
        out(f"每个改过的文件都备份成 <文件>.bak_tags_{stamp}")
    stats["changed_files"] = changed_files
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="修复坏掉的 tags（一律存成干净列表）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不改文件")
    ap.add_argument("--root", action="append", help="要扫的目录或 .json 文件（默认媒体根目录）")
    args = ap.parse_args(argv)
    roots = args.root
    if not roots:
        import config

        roots = [config.BASE_MEDIA_PATH]
    roots = [r for r in roots if os.path.exists(r)]
    if not roots:
        print("找不到要扫的目录")
        return 1
    print("扫描：" + "；".join(roots))
    repair(roots, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
