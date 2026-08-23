#!/usr/bin/env python3
"""Rebuild program/video_choice_queue.json from the 武志紅講心理 channel list.

Takes the first N *unprocessed* rows (no scene_content) starting at the first
such row, and writes them into the queue so `pick_video_choice.py next` can
launch the detail editor.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import aiagent.video_choice_queue as vcq

LIST_PATH = r"D:\AI_MEDIA\program\counseling\list\武志紅講心理.json"
CHANNEL_ID = "counseling"
CHANNEL_PATH = r"D:\AI_MEDIA\program\counseling"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

rows = json.load(open(LIST_PATH, encoding="utf-8"))
assert isinstance(rows, list), "list json must be a list"

# First unprocessed index = first row lacking scene_content
start = None
for i, r in enumerate(rows):
    if isinstance(r, dict) and not r.get("scene_content"):
        start = i
        break
assert start is not None, "no unprocessed row found"

unprocessed = [
    r for r in rows[start:]
    if isinstance(r, dict) and not r.get("scene_content")
]
selected = unprocessed[:N]
print(f"list total rows={len(rows)}  first_unprocessed_idx={start}  "
      f"selected={len(selected)}")

titles = [(r.get("title") or r.get("video_title") or "?")[:40] for r in selected]
for t in titles:
    print("  -", t)

written, skipped, path = vcq.export_video_details_to_queue(
    selected,
    channel_id=CHANNEL_ID,
    channel_path=CHANNEL_PATH,
    list_json_path=LIST_PATH,
    yt_language="tw",
    visual_style="realistic + 中国画(水墨/花鸟/山水)",
    narrator="man/wj/chinese",
)
print(f"\nqueue written: {written} items, {skipped} skipped -> {path}")

# Show resulting queue state
data = vcq.load_queue()
print(f"total={len(data['items'])} cursor={data['cursor']}")
for it in data["items"]:
    print("  choice_id=%s title=%s yt_lang=%s has_scene=%s"
          % (it.get("choice_id"), (it.get("title") or "")[:30],
             it.get("yt_language"), it.get("has_scene_content")))
