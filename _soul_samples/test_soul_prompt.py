import json, os, sys, glob
sys.path.insert(0, r"D:\AIComposer")
import config, project_manager
from storyproducer import prompts
OUT = r"D:\AIComposer\_soul_samples"
LBT = r"D:\AI_MEDIA\program\counseling\list_by_topic"
def row(prefix):
    f = [p for p in glob.glob(os.path.join(LBT, "*.json")) if os.path.basename(p).startswith(prefix)][0]
    d = json.load(open(f, encoding="utf-8"))
    return next(r for r in d if (r.get("analyzed_content") or "").strip() and r.get("topic_subtype"))
labels = [l for l, _ in prompts.lm_choices("counseling")]
print("templates:", labels)
cases = [("Faith", row("Faith__"), labels[0]), ("Love", row("Love__"), labels[3]), ("Love2", row("Love__"), labels[1])]
for name, r, lbl in cases:
    p = prompts.build_gemini_prompt(r, channel_id="counseling", lm_label=lbl, visual_style="", language="tw")
    blk = project_manager.build_soul_prompt_block("counseling", r["topic_category"], r["topic_subtype"], language="x", story_chars=len((r.get("analyzed_content") or "").strip()))
    story = len((r.get("analyzed_content") or "").strip())
    fn = os.path.join(OUT, f"{name}__{lbl.replace(' ','_').replace('·','').replace('.','')}.txt")
    open(fn, "w", encoding="utf-8").write(p)
    print(f"{name} | {lbl} | {r['topic_subtype']} | prompt={len(p)} story={story} soul_block={len(blk)} digest_in_prompt={'CORE-INSIGHT' in p} soul_after_story={p.find('CORE-INSIGHT')>p.find((r['analyzed_content'] or '')[:40])} -> {fn}")
# no subtype fallback / other channel / unknown category
d,_,_,_ = project_manager.build_soul("counseling", cases[1][1]["topic_category"], "")
print("fallback root+category len", len(d))
for ch in [k for k in config.CHANNEL_CONFIG if k != "counseling"][:3]:
    try: print("other channel", ch, len(project_manager.build_soul_prompt_block(ch, "X", "Y")))
    except Exception as e: print("other channel", ch, "ERR", e)
print("unknown cat", len(project_manager.build_soul_prompt_block("counseling", "UNKNOWN", "")))
import gui.downloader as dl
class M:
    channel = "counseling"
    def _channel_config_key(self): return "counseling"
try:
    _, tpl, _ = dl._resolve_combined_prompt_template("counseling", label=labels[0])
    q = dl._build_notebooklm_prompt_for_row(M(), cases[0][1], tpl)
    open(os.path.join(OUT, "Faith__downloader_builder.txt"), "w", encoding="utf-8").write(q)
    print("downloader builder ok", len(q), "CORE-INSIGHT" in q)
except Exception as e:
    import traceback; traceback.print_exc()

