# -*- coding: utf-8 -*-
"""t234u headless wiring test for QN (Qwen edit) backend."""
from __future__ import annotations

import json
import os
import py_compile
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(r"D:\AIComposer")
sys.path.insert(0, str(ROOT))

files = [
    ROOT / "config.py",
    ROOT / "utility" / "sd_image_processor.py",
    ROOT / "gui" / "picture_prompt_dialog.py",
    ROOT / "gui" / "workflow" / "wf_prompt_flows.py",
    ROOT / "utility" / "llm_api.py",
]

print("=== py_compile ===")
ok = True
for f in files:
    try:
        py_compile.compile(str(f), doraise=True)
        print(f"OK  {f.relative_to(ROOT)}")
    except Exception as e:
        ok = False
        print(f"FAIL {f.relative_to(ROOT)}: {e}")

print("\n=== config ===")
import config
print("COMFYUI_MOSS_URL =", repr(config.COMFYUI_MOSS_URL))
print("COMFYUI_QN_URL   =", repr(config.COMFYUI_QN_URL))
assert config.COMFYUI_QN_URL == config.COMFYUI_MOSS_URL
assert "192.168.1.30:8188" in config.COMFYUI_QN_URL

print("\n=== workflow node map ===")
wf_path = ROOT / "workflow" / "qwen_edit_3ref_api.json"
wf0 = json.loads(wf_path.read_text(encoding="utf-8-sig"))
node_map = {}
for nid, node in sorted(wf0.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
    cls = node.get("class_type")
    title = (node.get("_meta") or {}).get("title", "")
    node_map[nid] = (cls, title)
    print(f"  {nid}: {cls}  ({title})")

from utility import sd_image_processor as sip

print("\n=== constants / slots ===")
print("QN_EDIT_API_WORKFLOW =", sip.QN_EDIT_API_WORKFLOW)
print("QN_EDIT_MAX_REFS =", sip.QN_EDIT_MAX_REFS)
assert sip.QN_EDIT_MAX_REFS == 2
assert Path(sip.QN_EDIT_API_WORKFLOW).name == "qwen_edit_3ref_api.json"
slots = sip._qwen_slot_load_ids(wf0)
print("slots:", slots)
assert slots["image1"] == "8"
assert slots["image2"] == "50"
assert slots["image3"] == "51"
# follow chain: image1 goes through FluxKontextImageScale 117
assert sip._qwen_follow_to_loadimage(wf0, "117") == "8"
assert sip._qwen_follow_to_loadimage(wf0, "50") == "50"

print("\n=== build_qwen_edit_prompt: base only (strip unused) ===")
p0 = sip.build_qwen_edit_prompt(
    wf0, base_name="base.png", ref_names=[], prompt="hello qwen", seed=42
)
enc = p0["39"]["inputs"]
print("pos encode keys:", sorted(enc.keys()))
assert enc["prompt"] == "hello qwen"
assert "image1" in enc
assert "image2" not in enc
assert "image3" not in enc
assert "50" not in p0 and "51" not in p0
assert p0["8"]["inputs"]["image"] == "base.png"
assert p0["37"]["inputs"]["seed"] == 42
# negative encoder also stripped
neg = p0["36"]["inputs"]
assert "image2" not in neg and "image3" not in neg
print("base-only strip OK")

print("\n=== build: base + 1 ref ===")
p1 = sip.build_qwen_edit_prompt(
    wf0, base_name="base.png", ref_names=["r1.png"], prompt="p", seed=1
)
assert "image2" in p1["39"]["inputs"] and "image3" not in p1["39"]["inputs"]
assert "50" in p1 and "51" not in p1
assert p1["50"]["inputs"]["image"] == "r1.png"
assert p1["50"]["inputs"]["image"] != "base.png"
print("1-ref OK (no pad)")

print("\n=== build: base + 2 refs ===")
p2 = sip.build_qwen_edit_prompt(
    wf0, base_name="base.png", ref_names=["r1.png", "r2.png"], prompt="p", seed=1
)
assert "image2" in p2["39"]["inputs"] and "image3" in p2["39"]["inputs"]
assert p2["50"]["inputs"]["image"] == "r1.png"
assert p2["51"]["inputs"]["image"] == "r2.png"
print("2-ref OK")

print("\n=== build: >2 refs truncated ===")
p3 = sip.build_qwen_edit_prompt(
    wf0, base_name="base.png", ref_names=["r1.png", "r2.png", "r3.png"], prompt="p", seed=1
)
assert p3["50"]["inputs"]["image"] == "r1.png"
assert p3["51"]["inputs"]["image"] == "r2.png"
print("truncate OK")

print("\n=== adapt_prompt_for_qwen_edit ===")
a, n = sip.adapt_prompt_for_qwen_edit("把图1的人物换成图2和图3拼贴")
a2, n2 = sip.adapt_prompt_for_moss_edit("把图1的人物换成图2和图3拼贴")
assert (a, n) == (a2, n2)
print("adapt == moss adapt; sample:", repr(a[:100]))

print("\n=== generate_image_qwen_edit (mocked network) ===")
tmpdir = tempfile.mkdtemp(prefix="qn_test_")
base_img = os.path.join(tmpdir, "base.png")
ref_img = os.path.join(tmpdir, "ref.png")
from PIL import Image
Image.new("RGB", (16, 16), (10, 20, 30)).save(base_img)
Image.new("RGB", (16, 16), (40, 50, 60)).save(ref_img)

posted = {}
history_ready = {"n": 0}

class FakeResp:
    def __init__(self, data, status=200, text=""):
        self._data = data
        self.status_code = status
        self.text = text or json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

def fake_post(url, **kwargs):
    if url.endswith("/upload/image"):
        name = kwargs["files"]["image"][0]
        return FakeResp({"name": name, "subfolder": ""})
    if url.endswith("/prompt"):
        posted["url"] = url
        posted["body"] = kwargs.get("json")
        return FakeResp({"prompt_id": "pid-qn-1"})
    raise AssertionError(f"unexpected POST {url}")

def fake_get(url, **kwargs):
    if "/history/" in url:
        history_ready["n"] += 1
        return FakeResp({
            "pid-qn-1": {
                "status": {"completed": True, "status_str": "success", "messages": []},
                "outputs": {
                    "9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}
                },
            }
        })
    if "/view" in url:
        import io
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (7, 8, 9)).save(buf, format="PNG")
        class R:
            status_code = 200
            content = buf.getvalue()
            def raise_for_status(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return R()
    raise AssertionError(f"unexpected GET {url}")

status_msgs = []
with mock.patch.object(sip.requests, "post", side_effect=fake_post):
    with mock.patch.object(sip.requests, "get", side_effect=fake_get):
        img = sip.generate_image_qwen_edit(
            "edit with 图2", [base_img, ref_img], status=status_msgs.append
        )

assert posted["url"] == config.COMFYUI_QN_URL.rstrip("/") + "/prompt"
body = posted["body"]["prompt"]
enc = body["39"]["inputs"]
assert "image3" not in enc
assert "51" not in body
assert "image2" in enc
assert body["50"]["inputs"]["image"].startswith("qn_")
# adapt should have rewritten prompt somehow (or at least passed through adapt)
assert isinstance(enc["prompt"], str) and enc["prompt"]
print("generate OK; server=", posted["url"])
print("slots after build:", sorted(k for k in enc if k.startswith("image")))
print("status msgs sample:", status_msgs[:3])
print("result size:", img.size)

print("\n=== UI wiring ===")
ppd = (ROOT / "gui" / "picture_prompt_dialog.py").read_text(encoding="utf-8")
assert 'extra_backends=(("moss", "MOSS"), ("qn", "QN"))' in ppd
print("picture_prompt_dialog ask_llm_and_account: MOSS + QN")

wfpf = (ROOT / "gui" / "workflow" / "wf_prompt_flows.py").read_text(encoding="utf-8")
assert 'extra["image_backend"] = "qn"' in wfpf
assert 'b not in ("moss", "qn")' in wfpf
assert "use_qn = b == \"qn\"" in wfpf
assert "def qn_worker():" in wfpf
assert "generate_image_qwen_edit" in wfpf
assert "elif use_qn:" in wfpf
print("wf_prompt_flows: open_manual / last-pref / batch qn_worker / skip chrome for qn")

llm = (ROOT / "utility" / "llm_api.py").read_text(encoding="utf-8")
assert '(("moss", "MOSS"), ("qn", "QN"))' in llm
assert 'b if b in ("gemini", "moss", "qn") else "grok"' in llm
assert "generate_image_qwen_edit" in llm
assert 'use_qn = video_backend == "qn"' in llm
print("llm_api: _bk_opts + make_image qn branch")

print("\n=== WHERE QN APPEARS ===")
print("1) 图片修改 dialog (picture_prompt_dialog): radio QN via ask_llm_and_account extra_backends")
print("2) 从封面逐场提取 (wf_prompt_flows): last-pref qn + picker extra_backends + batch qn_worker")
print("3) LLM 手动窗 (llm_api): image backend radios include QN; CLI make_image qn path")
print("4) config.COMFYUI_QN_URL (default = COMFYUI_MOSS_URL)")
print("5) sd_image_processor: build_qwen_edit_prompt / generate_image_qwen_edit / adapt_prompt_for_qwen_edit")

if not ok:
    print("\nCOMPILE FAILURES")
    sys.exit(1)
print("\n=== ALL PASS ===")
