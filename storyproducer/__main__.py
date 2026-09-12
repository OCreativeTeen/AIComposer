"""Entry: ``python -m storyproducer`` / ``python -m storyproducer client`` / ``bot``.

Does not replace ``python -m cli`` or ``cli\\run_telegram_client.bat``.
"""

from __future__ import annotations

import os
import sys


def _enable_utf8_stdio() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _enable_utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(
            "storyproducer — 故事视频流水线\n"
            "  python -m storyproducer client     无 GUI 自动流水线（grv + grvc）\n"
            "  python -m storyproducer gui        有 GUI：逐条打开 clip 审阅窗（vc）\n"
            "  python -m storyproducer client --target GEMINI_ONLY\n"
            "  python -m storyproducer bot        Telegram 听筒（人手发 CLI）\n"
            "  python -m storyproducer pick next  单条 CLI\n"
            "  python -m storyproducer help\n"
            "\n"
            "不要与 cli\\run_bot.bat / cli\\run_telegram_client.bat 同时跑（同一 Telegram token）。"
        )
        return 0
    head = args[0].lower()
    if head in ("client", "pipeline", "run"):
        from storyproducer.pipeline import main as client_main

        return client_main(args[1:])
    if head in ("gui", "vc", "review"):
        from storyproducer.gui_pipeline import main as gui_main

        return gui_main(args[1:])
    if head in ("bot", "listen", "inbox"):
        from storyproducer.telegram_bot import run_bot

        return run_bot()
    from storyproducer.engine import StoryEngine

    eng = StoryEngine()
    ok, msg = eng.dispatch(" ".join(args))
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
