# -*- coding: utf-8 -*-
"""t236u headless: privacy toggle/restore + wiring (no real YouTube / channel)."""
from __future__ import annotations

import py_compile
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(r"D:\AIComposer")
sys.path.insert(0, str(ROOT))

files = [
    ROOT / "gui" / "dl" / "youtube_dl.py",
    ROOT / "utility" / "telegram_youtube_relay.py",
    ROOT / "gui" / "workflow" / "wf_finalize_publish.py",
]

print("=== py_compile ===")
for f in files:
    py_compile.compile(str(f), doraise=True)
    print("OK", f.relative_to(ROOT))


class FakeReq:
    def __init__(self, data=None):
        self._data = data or {}

    def execute(self):
        return self._data


class FakeVideos:
    def __init__(self, store):
        self.store = store
        self.updates = []
        self.deletes = []

    def list(self, part=None, id=None):
        st = self.store.get(id)
        if not st:
            return FakeReq({"items": []})
        return FakeReq({"items": [{"id": id, "status": dict(st)}]})

    def update(self, part=None, body=None):
        body = dict(body or {})
        vid = body["id"]
        status = dict(body.get("status") or {})
        self.updates.append({"id": vid, "status": status})
        # simulate YouTube clearing publishAt when not private
        cur = dict(self.store.get(vid) or {})
        cur["privacyStatus"] = status.get("privacyStatus", cur.get("privacyStatus"))
        if status.get("privacyStatus") == "private" and status.get("publishAt"):
            cur["publishAt"] = status["publishAt"]
        else:
            cur.pop("publishAt", None)
        for k in ("selfDeclaredMadeForKids", "containsSyntheticMedia"):
            if k in status:
                cur[k] = status[k]
        self.store[vid] = cur
        return FakeReq({"id": vid, "status": cur})

    def delete(self, id=None):
        self.deletes.append(id)
        self.store.pop(id, None)
        return FakeReq({})


class FakeYoutube:
    def __init__(self, store):
        self._videos = FakeVideos(store)

    def videos(self):
        return self._videos


print("\n=== privacy helpers ===")
from gui.dl import youtube_dl as ydl

assert ydl.youtube_video_id_from_url("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
assert ydl.youtube_video_id_from_url("https://youtu.be/abcdefghijk") == "abcdefghijk"

store = {
    "vidSched": {
        "privacyStatus": "private",
        "publishAt": "2026-12-01T15:00:00Z",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    },
    "vidUnl": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
}
yt = FakeYoutube(store)

snap = ydl.get_video_status(yt, "vidSched")
assert snap["privacyStatus"] == "private"
assert snap["publishAt"] == "2026-12-01T15:00:00Z"
print("get_video_status scheduled OK")

# temp unlisted then restore
msgs = []
with mock.patch("time.sleep", lambda *_a, **_k: None):
    with ydl.temporary_unlisted_for_download(yt, "vidSched", status=msgs.append, settle_s=0) as snap2:
        assert store["vidSched"]["privacyStatus"] == "unlisted"
        assert "publishAt" not in store["vidSched"]
        assert snap2["privacyStatus"] == "private"
        assert snap2["publishAt"] == "2026-12-01T15:00:00Z"
# restored
assert store["vidSched"]["privacyStatus"] == "private"
assert store["vidSched"]["publishAt"] == "2026-12-01T15:00:00Z"
print("temporary_unlisted_for_download restore OK:", msgs)

# unlisted video: no change
with mock.patch("time.sleep", lambda *_a, **_k: None):
    with ydl.temporary_unlisted_for_download(yt, "vidUnl", settle_s=0):
        assert store["vidUnl"]["privacyStatus"] == "unlisted"
assert len(yt.videos().updates) >= 2  # only scheduled toggled
print("unlisted skip-toggle OK")

# set scheduled from unlisted
ydl.set_video_privacy(
    yt, "vidUnl", "private",
    publish_at=datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc),
)
assert store["vidUnl"]["privacyStatus"] == "private"
assert store["vidUnl"]["publishAt"].startswith("2026-12-25")
print("set_video_privacy scheduled OK")

# switch to unlisted clears schedule
ydl.set_video_privacy(yt, "vidUnl", "unlisted")
assert store["vidUnl"]["privacyStatus"] == "unlisted"
assert "publishAt" not in store["vidUnl"]
print("set_video_privacy unlisted clears publishAt OK")

ydl.delete_youtube_video(yt, "vidUnl")
assert "vidUnl" not in store
assert "vidUnl" in yt.videos().deletes
print("delete_youtube_video OK")

print("\n=== telegram relay uses temp unlisted (mocked) ===")
import utility.telegram_youtube_relay as relay

calls = {"dl": 0, "with_ctx": 0}

class Ctx:
    def __enter__(self):
        calls["with_ctx"] += 1
        return {"privacyStatus": "private", "publishAt": "2026-12-01T15:00:00Z"}

    def __exit__(self, *a):
        return False

fake_yt = object()

def fake_download(*_a, **_k):
    calls["dl"] += 1
    # create a fake file
    import tempfile, os
    p = os.path.join(tempfile.gettempdir(), "t236_tg_fake.mp4")
    with open(p, "wb") as f:
        f.write(b"\x00" * 10)
    return {"video": p, "title": "t"}

row = {
    relay.URL_KEY: "https://www.youtube.com/watch?v=abcdefghijk",
    relay.ID_KEY: "abcdefghijk",
    relay.TITLE_KEY: "title",
    relay.DESC_KEY: "desc",
}

with mock.patch.object(relay, "telegram_publish_enabled", lambda: False):
    try:
        relay.send_published_youtube_to_telegram(row)
        raise AssertionError("should fail when telegram disabled")
    except RuntimeError as e:
        assert "Telegram 未配置" in str(e)

with mock.patch("utility.telegram_youtube_relay.telegram_publish_enabled", lambda: True), \
     mock.patch("gui.dl.youtube_dl.youtube_from_saved_token", return_value=fake_yt), \
     mock.patch("gui.dl.youtube_dl.temporary_unlisted_for_download", side_effect=lambda *a, **k: Ctx()), \
     mock.patch("utility.youtube_download.download_youtube", side_effect=fake_download), \
     mock.patch("utility.telegram_notify.notify_youtube_publish_extras", return_value=["tg ok"]), \
     mock.patch("utility.youtube_download.download_dir", return_value=str(ROOT / "_tmp_t236")), \
     mock.patch("project_manager.PROJECT_CONFIG", {"channel": "testch"}):
    lines = relay.send_published_youtube_to_telegram(row, channel_id="testch", retries=0)
assert calls["with_ctx"] == 1 and calls["dl"] == 1
assert any("tg ok" in x or "下载" in x for x in lines)
print("relay wraps download in temporary_unlisted OK:", lines[:2])

print("\n=== finalize wiring (source) ===")
fin = (ROOT / "gui" / "workflow" / "wf_finalize_publish.py").read_text(encoding="utf-8")
assert "def _adjust_youtube_publish" in fin
assert "def _delete_published_youtube" in fin
assert "t236u: 已有 YouTube 成片" in fin
assert '("adjust"' in fin or '("adjust",' in fin
assert "republish" in fin
assert "channel_id=str(_ch" in fin
assert "temporary_unlisted_for_download" in (ROOT / "utility" / "telegram_youtube_relay.py").read_text(encoding="utf-8")
print("finalize + relay wiring OK")

print("\n=== ALL PASS ===")
