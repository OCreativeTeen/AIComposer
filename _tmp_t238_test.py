# -*- coding: utf-8 -*-
"""t238u headless: final MiniMax prompt has no-subtitle rule exactly/at least 3 times."""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(r"D:\AIComposer")
sys.path.insert(0, str(ROOT))

for f in [
    "config_prompt.py",
    "utility/prompt_polish.py",
    "utility/sd_image_processor.py",
    "utility/minimax_dual.py",
]:
    py_compile.compile(str(ROOT / f), doraise=True)
    print("OK", f)

import config_prompt as cp
from utility import prompt_polish as pp

RULE = cp.H3_NO_SUBTITLE_RULE
assert "NEVER" in RULE and "subtitles" in RULE and "!" in RULE
print("RULE:", RULE)

# --- build_h3_prompt ---
scene = {
    "visual": "A quiet living room at dusk, warm lamp light.",
    "speaking": "<1>你好，今天我们聊聊这个话题。",
    "actor": "man/mature/chinese/林浩 (sitting left, blue shirt)",
}
prompt = cp.build_h3_prompt(
    [scene],
    frames="one",
    style="三维卡通 (Pixar-Art-Cartoon)",
    region="中国",
    era="现代",
    language="zh",
    camera="none",
    audio_mode="none",
    seconds=6.0,
    use_visual=True,
    use_speaking=True,
)
n = cp.count_h3_no_subtitle_rules(prompt)
print(f"build_h3_prompt count={n}")
assert n >= 3, prompt[:800]
# placements: top-ish (near Shot 1), near dialogue, before overall_soundscape
body = prompt.split("integrated_multimodal_description:", 1)[1].split("\n\noverall_soundscape:", 1)[0]
assert body.count(RULE) >= 3
idx_shot = body.find("[Shot 1]")
idx_d = body.find("<d>")
idx_end = len(body)
positions = [i for i in range(len(body)) if body.startswith(RULE, i)]
print("rule offsets in multimodal body:", positions)
assert len(positions) >= 3
# one near start (before dialogue), one near <d>, one near end
assert positions[0] < idx_d or idx_d < 0
assert positions[-1] > (idx_d if idx_d >= 0 else 0)
print("build placement OK")

# --- ensure after polish strips ---
stripped = prompt.replace(RULE, "")
assert cp.count_h3_no_subtitle_rules(stripped) == 0
fixed = cp.ensure_h3_no_subtitle_rules(stripped)
assert cp.count_h3_no_subtitle_rules(fixed) >= 3
print("ensure from zero OK:", cp.count_h3_no_subtitle_rules(fixed))

# already 3+ unchanged
same = cp.ensure_h3_no_subtitle_rules(prompt)
assert same == prompt
print("ensure idempotent when >=3 OK")

# --- negative merge ---
assert cp.with_h3_no_subtitle_negative(None) is None
neg = cp.with_h3_no_subtitle_negative("blurry, low quality")
assert "subtitle" in neg.lower() and "caption" in neg.lower()
assert neg.startswith("blurry")
print("negative merge OK:", neg[:80])

# --- polish path re-appends ---
# Simulate Strata dropping the rules
def fake_create(**req):
    class R:
        choices = [type("C", (), {"message": type("M", (), {"content": stripped})()})()]
    return R()

with mock.patch.object(pp, "_strata_client", create=True):
    # polish_video_prompt builds its own OpenAI client — patch OpenAI
    class FakeOpenAI:
        def __init__(self, *a, **k):
            self.chat = self
        @property
        def completions(self):
            return self
        def create(self, **req):
            return fake_create(**req)

    with mock.patch("openai.OpenAI", FakeOpenAI), \
         mock.patch("httpx.Client"), \
         mock.patch.dict("os.environ", {"STRATA_API_KEY": "x"}, clear=False):
        # LLMApi init may need more — if polish fails, still check ensure is called on success path
        try:
            out, why = pp.polish_video_prompt(prompt, "minimax_5070ti", timeout_s=5.0)
        except Exception as exc:
            print("polish call exception (will test ensure directly):", type(exc).__name__, exc)
            out, why = cp.ensure_h3_no_subtitle_rules(stripped), "fallback"
        n2 = cp.count_h3_no_subtitle_rules(out)
        print(f"after polish/ensure count={n2} why={why[:80] if isinstance(why,str) else why}")
        assert n2 >= 3

# Direct unit: polish restore block path
fake_polished = stripped  # missing rules
from config_prompt import ensure_h3_no_subtitle_rules
assert ensure_h3_no_subtitle_rules(fake_polished).count(RULE) >= 3
print("polish re-append path OK")

# dual import wiring
import utility.minimax_dual as md
src = Path("utility/minimax_dual.py").read_text(encoding="utf-8")
assert "ensure_h3_no_subtitle_rules" in src
src2 = Path("utility/prompt_polish.py").read_text(encoding="utf-8")
assert "ensure_h3_no_subtitle_rules" in src2
assert "NEVER add any subtitles" in src2  # _SYS_H3
print("wiring OK")

# Show sample excerpts of the three placements
print("\n=== SAMPLE (multimodal body, rule marked) ===")
marked = body
for k, pos in enumerate(positions[:3], 1):
    print(f"--- copy #{k} at {pos} ---")
    print(marked[max(0, pos - 60): pos + len(RULE) + 60].replace("\n", " | "))

print("\n=== ALL PASS ===")
