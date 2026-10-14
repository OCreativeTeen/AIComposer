import json, os, sys, glob
sys.path.insert(0, r"D:\AIComposer")
import config, config_channel, project_manager
from storyproducer import prompts
OUT = r"D:\AIComposer\_soul_samples"
row = None
for f in sorted(glob.glob(r"D:\AI_MEDIA\program\counseling\list_by_topic\*.json")):
    if "faith" not in f.lower():
        continue
    d = json.load(open(f, encoding="utf-8-sig"))
    row = next((x for x in d if len((x.get("analyzed_content") or "").strip()) > 1500 and x.get("topic_subtype")), None)
    if row: break
assert row, "no row"
print("row:", row.get("title") or row.get("story_title"), row["topic_category"], "|", row["topic_subtype"], len(row["analyzed_content"]))
vs = config.VISUAL_STYLE_OPTIONS[3]
def save(name, p):
    fn = os.path.join(OUT, name); open(fn, "w", encoding="utf-8").write(p); return fn
for st in (3, 5):
    p = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label=config_channel.STEP_STORY_LABEL, language="zh", steps=st, visual_style=vs)
    assert f"has {st} scenes" in p and "###STEP###" not in p and "###K###" not in p and "CORE-INSIGHT" in p and vs in p
    print("step", st, len(p), save(f"counseling__StepStory_{st}steps.txt", p))
for k in (1, 2, 3):
    p = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label=config_channel.SERIES_DIRECT_LABEL, language="zh", episode=k, episodes=3, visual_style=vs)
    assert f"episode {k} of 3" in p and "###STEP###" not in p and "###K###" not in p and "CORE-INSIGHT" in p
    print("series", k, len(p), save(f"counseling__SeriesDirect_ep{k}of3.txt", p))
# equivalence & legacy
for st in (2, 3, 4):
    a = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label="Step Story", language="zh", steps=st)
    b = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label=f"{st} Step Story", language="zh")
    old = getattr(config_channel, f"COUNSELING_STORY_{st}STEP")
    print("legacy", st, a == b, config_channel.resolve_dynamic_scene_template("Step Story", config_channel.COUNSELING_STORY_STEP, {"steps": st}) == old)
print("labels", [l for l, _ in prompts.lm_choices("counseling")], [l for l, _ in prompts.lm_choices("flylink")][:4])

