#!/usr/bin/env python3
"""CLI 入口：从 ``program/video_choice_queue.json`` 逐条取用 GUI 导出的视频选择。"""

from aiagent.video_choice_queue import main

if __name__ == "__main__":
    raise SystemExit(main())
