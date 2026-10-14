import json, os, sys
sys.path.insert(0, r"D:\AIComposer")
import config, project_manager
from storyproducer import prompts
OUT = r"D:\AIComposer\_soul_samples"
def topics(ch):
    return json.load(open(rf"D:\AI_MEDIA\program\{ch}\topics.json", encoding="utf-8-sig"))
def comic_row():
    d = json.load(open(r"D:\AI_MEDIA\program\comic\list_by_topic\Chinese__AncientStory.json", encoding="utf-8-sig"))
    r = next((x for x in d if (x.get("analyzed_content") or "").strip()), d[0] if d else {})
    return r, "real"
SYN_FLY = ("某市低空物流试点方案：海岛三条航线，日均 40 架次，单票时效由船运 6 小时缩短至 35 分钟。"
           "方案包括起降点建设、数据链冗余设计、指挥调度平台与保险安排。现已完成 3 个月试运行，"
           "累计 2,100 架次，无安全事故。寻求地方政府与物流企业合作扩大至 10 条航线。") * 3
SYN_MV = ("她每年清明都回到江南老镇的渡口，那里是外婆当年送别外公的地方。外公一去未归，"
          "外婆守着一盏灯等了四十年。如今外婆走了，她把那盏灯点亮，放进河里，看它慢慢漂远。")
t_fly = topics("flylink"); t_mv = topics("music_story"); t_cm = topics("comic")
cases = []
r, kind = comic_row()
if not r.get("topic_subtype"):
    r = dict(r); r["topic_category"] = t_cm[0]["topic_category"]; r["topic_subtype"] = t_cm[0]["topic_subtypes"][0]["topic_subtype"]; kind += "+assigned-topic"
cases.append(("comic", "comic", r, kind))
cases.append(("flylink", "industry_aviation", {"title": "低空物流试点", "analyzed_content": SYN_FLY,
              "topic_category": t_fly[2]["topic_category"], "topic_subtype": t_fly[2]["topic_subtypes"][1]["topic_subtype"]}, "synthetic"))
cases.append(("music_story", "music_story", {"title": "渡口的灯", "analyzed_content": SYN_MV,
              "topic_category": t_mv[1]["topic_category"], "topic_subtype": t_mv[1]["topic_subtypes"][1]["topic_subtype"]}, "synthetic"))
for name, key, row, kind in cases:
    labels = [l for l, _ in prompts.lm_choices(key)]
    if not labels:
        print(name, "no templates"); continue
    p = prompts.build_gemini_prompt(row, channel_id=key, lm_label=labels[0], language="zh")
    story = len((row.get("analyzed_content") or "").strip())
    blk = project_manager.build_soul_prompt_block(key, row["topic_category"], row["topic_subtype"], language="x", story_chars=story)
    fn = os.path.join(OUT, f"{name}__{labels[0].replace(' ', '_').replace('·', '').replace('.', '').replace('/', '_')}.txt")
    open(fn, "w", encoding="utf-8").write(p)
    print(f"{name} [{kind}] tpl={labels[0]} sub={row['topic_subtype']} story={story} soul_block={len(blk)} prompt={len(p)} warm_in_block={'non-judgmental' in blk} faith_in_block={'Faith' in blk} -> {fn}")
