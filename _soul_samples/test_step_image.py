import sys, os, json, glob, subprocess, difflib
sys.path.insert(0, r"D:\AIComposer")
import config, config_channel, config_prompt
from storyproducer import prompts
OUT = r"D:\AIComposer\_soul_samples"
vs = config.VISUAL_STYLE_OPTIONS[1]
for k in (1, 2):
    p = prompts.build_gemini_prompt({}, channel_id="counseling", lm_label=config_channel.STEP_IMAGE_LABEL, steps=k, visual_style=vs)
    assert f"step {k} image" in p and vs in p
    open(os.path.join(OUT, f"counseling__StepImage_step{k}.txt"), "w", encoding="utf-8").write(p)
    print("step image", k, len(p))
# old constants from HEAD
old = subprocess.run(["git", "-C", r"D:\AIComposer", "show", "HEAD:config_channel.py"], capture_output=True).stdout.decode("utf-8")
oldp = subprocess.run(["git", "-C", r"D:\AIComposer", "show", "HEAD:config_prompt.py"], capture_output=True).stdout.decode("utf-8")
o = {}; exec(compile(old, "old_cc", "exec"), o)
op = {}; exec(compile(oldp, "old_cp", "exec"), op)
for name in ("COUNSELING", "FLYLINK"):
    new1 = config_channel.build_step_story(getattr(config_channel, name + "_STORY_CORE"), 1)
    print(name, "1-step == old Short Story:", new1 == o[name + "_STORY_SHORT"],
          "| 2..4 same:", all(config_channel.build_step_story(getattr(config_channel, name + "_STORY_CORE"), n) == o[f"{name}_STORY_{n}STEP"] for n in (2, 3, 4)))
print("DIRECT_STEP_n_IMAGE same:", all(getattr(config_prompt, f"DIRECT_STEP_{n}_IMAGE") == op[f"DIRECT_STEP_{n}_IMAGE"] for n in (1, 2, 3, 4)))
row = None
for f in sorted(glob.glob(r"D:\AI_MEDIA\program\counseling\list_by_topic\*.json")):
    d = json.load(open(f, encoding="utf-8-sig"))
    row = next((x for x in d if len((x.get("analyzed_content") or "")) > 1500 and x.get("topic_subtype")), None)
    if row: break
a = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label="Step Story", language="zh", steps=1)
b = prompts.build_gemini_prompt(row, channel_id="counseling", lm_label="Short Story", language="zh")
open(os.path.join(OUT, "counseling__StepStory_1step.txt"), "w", encoding="utf-8").write(a)
diff = "".join(difflib.unified_diff(o["COUNSELING_STORY_SHORT"].splitlines(True), config_channel.build_step_story(config_channel.COUNSELING_STORY_CORE, 1).splitlines(True), "old_Short_Story", "Step_Story_1"))
open(os.path.join(OUT, "StepStory_1step_vs_ShortStory.diff"), "w", encoding="utf-8").write(diff or "(identical)\n")
print("legacy 'Short Story' == Step Story 1:", a == b, "| diff:", "identical" if not diff else len(diff))
print("labels", [l for l, _ in prompts.lm_choices("counseling")], [l for l, _ in prompts.lm_choices("flylink")])
