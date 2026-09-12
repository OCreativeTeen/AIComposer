"""Headless story-video producer — no Tk / no GUI bridge.

Runs the same Hermes pipeline (pick → scenes → NotebookLM covers → Grok
image/video → record clips) by calling CLI logic in-process.

Do not import ``gui.downloader`` UI, ``cli.bridge``, or the existing
``run_bot.bat`` / ``run_telegram_client.bat`` from this package's pipeline.
"""

from __future__ import annotations

__all__ = ["StoryEngine"]


def __getattr__(name: str):
    if name == "StoryEngine":
        from storyproducer.engine import StoryEngine

        return StoryEngine
    raise AttributeError(name)
