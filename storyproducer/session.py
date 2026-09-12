"""In-memory current-story session for the headless producer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StorySession:
    """One active queue item + its channel-list ``video_detail`` row."""

    queue_item: dict[str, Any] = field(default_factory=dict)
    video_detail: dict[str, Any] = field(default_factory=dict)
    lm_label: str = ""
    visual_style: str = ""
    narrator: str = ""
    instruction: str = ""
    gemini_paths: list[str] = field(default_factory=list)
    gemini_pick: int = 0
    cover_path: str = ""
    nbi_index: int = 0
    grv_variant: int = 3

    def title(self) -> str:
        vd = self.video_detail if isinstance(self.video_detail, dict) else {}
        item = self.queue_item if isinstance(self.queue_item, dict) else {}
        return (
            (vd.get("title") or vd.get("video_title") or item.get("title") or "")
            .strip()
            or "?"
        )

    def channel_id(self) -> str:
        item = self.queue_item if isinstance(self.queue_item, dict) else {}
        vd = self.video_detail if isinstance(self.video_detail, dict) else {}
        return (item.get("channel_id") or vd.get("channel_id") or "").strip()

    def language(self) -> str:
        item = self.queue_item if isinstance(self.queue_item, dict) else {}
        vd = self.video_detail if isinstance(self.video_detail, dict) else {}
        return (
            item.get("yt_language")
            or item.get("language")
            or vd.get("language")
            or "tw"
        ).strip() or "tw"

    def scene_content(self) -> list | None:
        sc = (self.video_detail or {}).get("scene_content")
        if isinstance(sc, list) and sc:
            return sc
        return None

    def scene_count(self) -> int:
        sc = self.scene_content()
        return len(sc) if sc else 0

    def actor_for_scene(self, index_0: int) -> str:
        sc = self.scene_content() or []
        if 0 <= index_0 < len(sc) and isinstance(sc[index_0], dict):
            return (sc[index_0].get("actor") or "").strip()
        return ""

    def is_loaded(self) -> bool:
        return bool(self.queue_item) and bool(self.video_detail)
