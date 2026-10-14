import sys, os, json, glob
sys.path.insert(0, r"D:\AIComposer")
import config, config_channel, config_prompt
from storyproducer import prompts
OUT = r"D:\AIComposer\_soul_samples"
row = None
for f in sorted(glob.glob(r"D:\AI_MEDIA\program\counseling\list_by_topic\*.json")):
    d = json.load(open(f, encoding="utf-8-sig"))
    row = next((x for x in d if isinstance(x.get("scene_content"), list) and len(x["scene_content"]) >= 3), None)
    if row: break
assert row, "no row with scene_content"
vs = config.VISUAL_STYLE_OPTIONS[2]
p = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label=config_channel.SCENE_SUMMARY_IMAGE_LABEL, visual_style=vs)
same = p == config_prompt.build_slide_flow_prompt(target="single", text="none", narrative="story", use_visual=True, use_speaking=True, use_actor=False, visual_style=vs, scene_content=row["scene_content"])
fn = os.path.join(OUT, "counseling__SceneSummaryImage.txt"); open(fn, "w", encoding="utf-8").write(p)
print("row:", row.get("title"), "scenes:", len(row["scene_content"]), "prompt chars:", len(p), "style in:", vs in p, "== slide single:", same)
print("empty ->", repr(prompts.build_gemini_prompt({"scene_content": []}, channel_id="counseling", lm_label=config_channel.SCENE_SUMMARY_IMAGE_LABEL)))
print([l for l, _ in prompts.lm_choices("counseling")])
print(p[:1500])
