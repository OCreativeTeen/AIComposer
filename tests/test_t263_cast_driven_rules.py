"""t263: 讲员的情况永远由真实数据决定（没有「不知道」）；场景生成必须先有人物；播客和故事对话是两回事；
故事对话（t266: 短故事已并入，步数 0 或 1–6 共用说话规则）；故事表演没有「叙述场景」。

需要真实 config / downloader 的检查在子进程里跑，不装桩，只读，不写任何项目 / 列表数据。"""
import json
import os
import string
import subprocess
import sys
import unittest

from tests.test_video_speaker_semantics import _install_stubs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_install_stubs()

import config_channel as cc  # noqa: E402
import config_prompt as cp  # noqa: E402
from utility import cast_preset as cpr  # noqa: E402
from utility import narration_modes as nm  # noqa: E402

CASES = (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER, nm.HOST_NONE)
LABELS = {"播客": "podcast", "故事对话": "story_speak", "故事表演": "story_act"}  # t266: 短故事已并入故事对话
HOST = "讲员：woman/mature/chinese/秦"
PEOPLE = "人物1：man/youth/chinese/阿明（低头） | 人物2：woman/youth/chinese/小美"


def _real(code):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2500:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class NoUnknownCase(unittest.TestCase):
    def test_no_any_host_case_in_the_code(self):
        self.assertFalse(hasattr(nm, "HOST_ANY"))
        self.assertEqual(nm.HOST_CASES, CASES)
        for rel in (("config_prompt.py",), ("config_channel.py",), ("gui", "dl", "prompts_notebooklm.py"),
                    ("gui", "dl", "scene_editor.py"), ("gui", "slide_prompt_dialog.py"),
                    ("gui", "video_prompt_dialog.py"), ("gui", "downloader.py"), ("utility", "narration_modes.py")):
            self.assertNotIn("HOST_ANY", _read(*rel), rel)

    def test_unknown_value_is_never_three_cases(self):
        for key in LABELS.values():
            self.assertEqual(nm.rules_block(key, "any"), nm.rules_block(key, nm.HOST_NONE), key)
            for txt in (nm.speaking_rule(key, "any"), nm.performance_rule(key, "any")):
                for needle in ("(a)", "(b)", "(c)", "THREE CASES"):
                    self.assertNotIn(needle, txt)

    def test_video_host_case_from_data(self):
        res = _real(r"""
import json
import project_manager as pm, config_prompt as cp
from utility import narration_modes as nm
host = {"role": "host", "label": "讲员", "body": "woman/mature/chinese/秦"}
p1 = {"role": "person", "label": "人物1", "body": "man/youth/chinese/阿明"}
sc = {"id": 1, "actor": pm.format_actor_entries([host, p1]), "speaking": "<1> 你好。"}
no_host = {"id": 1, "actor": pm.format_actor_entries([p1]), "speaking": ""}
out = {}
for mode in ("podcast", "story_speak", "story_act"):
    out[mode] = [cp._video_host_case(mode, [sc], True), cp._video_host_case(mode, [sc], False),
                 cp._video_host_case(mode, [no_host], True)]
fin = {}
cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png")
fin["yes"] = cp._video_host_case("podcast", [sc])  # 不给 -> 现查
cp.host_portrait_finder = lambda *a, **k: (lambda row: "")
fin["no"] = cp._video_host_case("podcast", [sc])
cp.host_portrait_finder = lambda *a, **k: (lambda row: 1 / 0)  # 讲员库出错 = 没有肖像（唯一的「查不了」，画外音）
fin["boom"] = cp._video_host_case("podcast", [sc])
out["finder"] = fin
print(json.dumps(out, ensure_ascii=False))
""")
        for mode in ("podcast", "story_speak", "story_act"):
            self.assertEqual(res[mode], [nm.HOST_PORTRAIT, nm.HOST_VOICEOVER, nm.HOST_NONE], mode)
        self.assertEqual(res["finder"], {"yes": nm.HOST_PORTRAIT, "no": nm.HOST_VOICEOVER, "boom": nm.HOST_VOICEOVER})

    def test_voiceover_host_keeps_actor_positions_for_dialogue_modes(self):
        """播客 / 故事对话里 <N> 是 actor 里的第几个人：没有肖像的讲员不出镜，但位置不能动。"""
        res = _real(r"""
import json
import project_manager as pm, config_prompt as cp
host = {"role": "host", "label": "讲员", "body": "woman/mature/chinese/秦"}
p1 = {"role": "person", "label": "人物1", "body": "woman/youth/chinese/小美"}
sc = {"id": 1, "visual": "书房。", "actor": pm.format_actor_entries([host, p1]),
      "speaking": "<1> 这封信后来怎么样了？ <2> 他一直没寄出去。"}
cast = cp._video_cast([sc], True)
out = {}
for mode in ("podcast", "story_speak", "story_act"):
    m, case, vis_cast, vis_scenes, dir_scenes = cp._video_act_plan(mode, cast, [sc], False)
    out[mode] = [case, [r["role"] for r in vis_cast], vis_scenes[0]["actor"], dir_scenes[0]["actor"], sc["actor"]]
print(json.dumps(out, ensure_ascii=False))
""")
        for mode in ("podcast", "story_speak"):
            case, roles, vis_actor, dir_actor, orig = res[mode]
            self.assertEqual(case, nm.HOST_VOICEOVER)
            self.assertEqual(roles, ["person"])  # 出镜名单里没有讲员
            self.assertEqual(vis_actor, orig)  # 场景数据（位置）不动
            self.assertNotIn("讲员", dir_actor)  # 方向句里没有讲员
        case, roles, vis_actor, dir_actor, orig = res["story_act"]
        self.assertNotIn("讲员", vis_actor)  # 故事表演：讲员的话走 narration，actor 里去掉讲员

    def test_all_prompts_follow_the_derived_case(self):
        """每个 prompt 都只写 derived 出来的那一种；三种都换一遍。"""
        for key in ("podcast", "story_speak", "story_act"):
            seen = set()
            for h in CASES:
                spk = nm.speaking_rule(key, h)
                self.assertNotIn(spk, seen)
                seen.add(spk)


class SceneGenerationNeedsActors(unittest.TestCase):
    def test_check_messages_point_to_the_button(self):
        for label in LABELS:
            for cast in (None, "", "讲员：woman/mature/chinese/秦"):
                ok, why = cpr.validate_cast_for_mode(LABELS[label], cast)
                self.assertFalse(ok, (label, cast))
                self.assertIn("「人物设置」", why, (label, cast))
        ok, why = cpr.validate_cast_for_mode("story_act", "")
        self.assertIn("人物栏现在是空的", why)
        ok, why = cpr.validate_cast_for_mode("podcast", PEOPLE)  # 只有人物没有讲员
        self.assertFalse(ok)
        self.assertIn("讲员", why)
        self.assertTrue(cpr.validate_cast_for_mode("podcast", HOST + " | 人物1：woman/youth/chinese/小美")[0])
        for key in ("story_speak", "story_act"):  # 讲员可有可无
            self.assertTrue(cpr.validate_cast_for_mode(key, PEOPLE)[0])
            self.assertTrue(cpr.validate_cast_for_mode(key, HOST + " | " + PEOPLE)[0])
        self.assertTrue(cpr.validate_cast_for_mode("", "")[0])  # 不是这四种方式：不检查

    def test_every_entry_point_is_guarded(self):
        dl = _read("gui", "downloader.py")
        self.assertIn("scene_cast_check(video_detail, prompt_label)", dl)
        self.assertIn("raise ValueError(_cast_why)", dl)
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("_cast_preset.validate_cast_for_mode(_cast_mode, _cast_now)", se)  # 点「场景生成」
        self.assertIn("_scene_cast_check(video_detail,", se)  # 选方式 / 拷提示词
        self.assertIn('text="人物设置"', se)  # 生成讲员 + 人物、可以重新生成的按钮

    def test_funnel_blocks_without_cast_and_builds_with_cast(self):
        res = _real(r'''
import json
import config_prompt as cp
import gui.downloader as d
fake = type("F", (), {"_channel_config_key": lambda s: "counseling", "language": "Chinese", "channel": "counseling"})()
HOST = "讲员：woman/mature/chinese/秦"
P = "人物1：man/youth/chinese/阿明（低头） | 人物2：woman/youth/chinese/小美"
out = {"blocked": {}, "prompts": {}}
for lab in ("播客", "故事对话", "故事表演"):
    for name, cast in (("none", None), ("empty", ""), ("host_only", HOST)):
        try:
            d.MediaGUIManager._generate_scene_content_from_notebooklm_prompt(fake, {"analyzed_content": "一封旧信", "story_actors": cast}, lab)
            out["blocked"][lab + "/" + name] = "NOT BLOCKED"
        except ValueError as e:
            out["blocked"][lab + "/" + name] = str(e)
    for case, cast, portrait in (("portrait", HOST + " | " + P, True), ("voiceover", HOST + " | " + P, False), ("none", P, True)):
        cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png" if portrait else "")
        out["prompts"][lab + "/" + case] = d.MediaGUIManager._combined_prompt_text_for_label(
            fake, {"analyzed_content": "一封旧信", "story_actors": cast}, lab, prompt_params={"episodes": 1})[1]
print(json.dumps(out, ensure_ascii=False))
''')
        for k, v in res["blocked"].items():
            if k.endswith(("/none", "/empty")) or k.startswith("播客/host_only"):
                self.assertIn("「人物设置」", v, k)
        for lab, key in (("播客", "podcast"), ("故事表演", "story_act"), ("故事对话", "story_speak")):
            self.assertIn("「人物设置」", res["blocked"][lab + "/none"])
        self.assertNotEqual(res["blocked"]["故事对话/host_only"], "NOT BLOCKED")  # 讲员不算人物：0 个人物
        for lab, key in LABELS.items():
            for case in CASES:
                p = res["prompts"][lab + "/" + case]
                use = case
                for rule in (nm.speaking_rule(key, use), nm.performance_rule(key, use)):
                    self.assertEqual(p.count(rule), 1, (lab, case))
                for other in CASES:
                    if other != use:
                        self.assertNotIn(nm.speaking_rule(key, other), p, (lab, case, other))
                self.assertEqual(p.count(nm.RULES_BLOCK_HEAD), 1, (lab, case))
                self.assertNotIn("(a)", nm.speaking_rule(key, use))
        # 故事表演：三种情况用三份模板
        act = {c: res["prompts"]["故事表演/" + c] for c in CASES}
        self.assertIn("who has a portrait (肖像)", act["portrait"])
        self.assertIn("who has no portrait (肖像)", act["voiceover"])
        self.assertIn("the CAST has no 讲员. Nobody speaks at all", act["none"])
        self.assertNotIn('"speaking"', act["none"].split("*** NARRATION MODE RULES")[0])
        for c in CASES:
            for gone in ("narrator scene", "presenting scene", "THREE CASES"):
                self.assertNotIn(gone, act[c])


class PodcastIsNotStoryDialogue(unittest.TestCase):
    def test_rule_texts_are_different_things(self):
        for h in CASES:
            pod, dia = nm.speaking_rule("podcast", h), nm.speaking_rule("story_speak", h)
            self.assertNotEqual(pod, dia, h)
            self.assertNotEqual(nm.performance_rule("podcast", h), nm.performance_rule("story_speak", h), h)
        pod = nm.speaking_rule("podcast", nm.HOST_PORTRAIT)
        self.assertIn("a discussion between the 讲员 (the host) and the 嘉宾", pod)
        self.assertIn("talk ABOUT the story as a third party", pod)
        self.assertIn("the people of the story never speak", pod)
        self.assertIn("Neither is a character of the story", pod)
        pperf = nm.performance_rule("podcast", nm.HOST_PORTRAIT)
        self.assertIn("nobody performs the story", pperf)
        self.assertIn("no one re-enacts it and no story character appears", pperf)
        dia = nm.speaking_rule("story_speak", nm.HOST_PORTRAIT)
        self.assertIn("carry the story by talking to each other", dia)
        self.assertNotIn("嘉宾", dia)
        self.assertNotIn("discussion", dia)

    def test_scene_template_is_a_host_and_guest_podcast(self):
        t = cc.COUNSELING_TALK_SCENES
        self.assertIn("A host (the 讲员) and a guest (a 人物, the 嘉宾) talk about the story", t)
        self.assertIn("a two-person podcast. The 讲员 is the host, the 人物 is the guest (嘉宾)", t)
        self.assertIn("the host and the guest only discuss the story", t)
        self.assertIn("never play the story's people", t)
        for gone in ("CAST is EMPTY", "No cast was chosen", "Only the 讲员: the 讲员 alone speaks", "FIRST listed 人物 is the host"):
            self.assertNotIn(gone, t)
        self.assertNotEqual(t, cc.COUNSELING_SERIES_STORY_SPEAK)

    def test_every_window_reads_the_same_podcast_text(self):
        pod = nm.rules_block("podcast", nm.HOST_PORTRAIT)
        self.assertIn(nm.speaking_rule("podcast", nm.HOST_PORTRAIT), pod)
        res = _real(r'''
import json
from gui.dl import prompts_notebooklm as pn
from utility import narration_modes as nm
vd = {"story_actors": "讲员：woman/mature/chinese/秦 | 人物1：woman/youth/chinese/小美"}
print(json.dumps(pn.build_program_cast_block(vd, "播客", "slides", "panel", host_case="portrait"), ensure_ascii=False))
''')
        self.assertEqual(res.count(nm.speaking_rule("podcast", nm.HOST_PORTRAIT)), 1)
        self.assertEqual(res.count(nm.performance_rule("podcast", nm.HOST_PORTRAIT)), 1)

    def test_blue_note_in_the_video_window(self):
        note = cp.story_style_mode_text("podcast", True)
        self.assertIn("嘉宾", note)
        self.assertIn("只谈不演", note)
        self.assertNotIn("主持人讲述", note)
        self.assertNotEqual(note, cp.story_style_mode_text("story_speak", True))


class ShortStoryAndStoryDialogueShareRules(unittest.TestCase):
    """t266: 短故事已并入故事对话；步数（0 / 1–6）只改结构（场景数），说话 / 表演规则和讲员的写法不变。"""

    def test_same_rule_text_without_a_host(self):
        # 旧存值 step_story 读作故事对话：规则就是故事对话那一份
        self.assertEqual(nm.speaking_rule("step_story"), nm.speaking_rule("story_speak", nm.HOST_NONE))
        self.assertEqual(nm.performance_rule("step_story"), nm.performance_rule("story_speak", nm.HOST_NONE))
        self.assertEqual(nm.rules_block("step_story"), nm.rules_block("story_speak", nm.HOST_NONE))
        for h in CASES:
            self.assertEqual(nm.speaking_rule("step_story", h), nm.speaking_rule("story_speak", h))
        # 故事对话有讲员时，只多一小句讲员的话
        base = nm.speaking_rule("story_speak", nm.HOST_NONE)
        for h in (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER):
            with_host = nm.speaking_rule("story_speak", h)
            self.assertTrue(with_host.startswith(base.split(" Cast here:")[0]), h)

    def test_only_structural_differences_remain(self):
        """步数 0 = 按集规划（系列模板）；步数 1–6 = 固定场景数（一个故事）。讲员的规则两边一致：有讲员保留，没有讲员不写。"""
        free = cc.COUNSELING_SERIES_STORY_SPEAK
        self.assertNotIn(cc.STEP_STORY_NO_HOST_MARK, free)
        self.assertIn("*** EPISODES:", free)
        for host in CASES:
            out0 = cc.resolve_dynamic_scene_template("故事对话", free, {"steps": 0, "host_case": host})
            out4 = cc.resolve_dynamic_scene_template("故事对话", free, {"steps": 4, "host_case": host})
            out2 = cc.resolve_dynamic_scene_template("故事对话", free, {"steps": 2, "host_case": host})
            self.assertNotEqual(out4, out2)  # 场景数是步数的结构参数
            self.assertNotEqual(out4, out0)
            for out in (out0, out4, out2):
                self.assertEqual(out.count(nm.speaking_rule("story_speak", host)), 1, host)
                self.assertEqual(out.count(nm.performance_rule("story_speak", host)), 1, host)
            # 有讲员：固定 N 场的模板里讲员还在；没有讲员：写明没有讲员
            self.assertEqual(cc.STEP_STORY_NO_HOST_MARK in out4, host == nm.HOST_NONE, host)

    def test_program_window_uses_the_same_text(self):
        res = _real(r'''
import json
from gui.dl import prompts_notebooklm as pn
P = "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"
print(json.dumps({lab: pn.build_program_cast_block({"story_actors": P}, lab, "slides", "panel", host_case="none")
                  for lab in ("短故事", "Step Story", "故事对话")}, ensure_ascii=False))
''')
        for old in ("短故事", "Step Story"):  # t266: 旧的短故事 / Step Story 读作故事对话，节目生成里一字不差
            self.assertEqual(res[old], res["故事对话"], old)
        for rule in (nm.speaking_rule("story_speak", nm.HOST_NONE), nm.performance_rule("story_speak", nm.HOST_NONE)):
            self.assertEqual(res["故事对话"].count(rule), 1)


class NoNarratorScenes(unittest.TestCase):
    def test_story_act_has_no_narrator_scene_gating(self):
        for case, t in cc.STORY_ACT_TEMPLATES.items():
            for gone in ("narrator scene", "presenting scene", "Only with a 讲员", "Without a 讲员: none of these"):
                self.assertNotIn(gone, t, (case, gone))
        for h in CASES:
            for txt in (nm.speaking_rule("story_act", h), nm.performance_rule("story_act", h)):
                self.assertNotIn("narrator scene", txt)
                self.assertNotIn("presenting scene", txt)
        self.assertIn("explains every scene", nm.speaking_rule("story_act", nm.HOST_PORTRAIT))
        self.assertIn("explains every scene as a background voice-over", nm.speaking_rule("story_act", nm.HOST_VOICEOVER))
        self.assertIn("Nobody speaks at all, in any scene", nm.speaking_rule("story_act", nm.HOST_NONE))

    def test_video_story_act_voiceover_speaks_in_every_scene_with_speech(self):
        a = {"actor": "讲员：woman/mature/chinese/秦 | 人物1：woman/youth/chinese/小美", "speaking": "<1> 她把信放回抽屉。",
             "story_content": "小美合上抽屉。", "visual": "书房"}
        b = dict(a, speaking="<1> 这一幕说明她仍然没有开口。")
        lines, field = cp._video_speech_rules("story_act", "story", [], [a, b], "", True, nm.HOST_VOICEOVER)
        self.assertEqual(field, "narration")
        lines2, field2 = cp._video_speech_rules("story_act", "story", [], [a, b], "", True, nm.HOST_PORTRAIT)
        self.assertEqual(field2, "dialogue")
        # 有讲员时每一场的 story_content 和讲解一起发给视频
        payload = cp._video_payload([a, b], variant="act_one", host_narrator="", use_visual=True, use_speaking=True,
                                    cast=cp._video_cast([a, b], True), content_key="dialogue", with_act=True)
        self.assertTrue(all("story_content" in s and "dialogue" in s for s in payload), payload)


class InvariantsStillHold(unittest.TestCase):
    def test_no_subtitle_critical_line_once_first(self):
        for key in LABELS.values():
            p = cp.build_video_flow_prompt(
                frames="one", background="none", evolve="keep", visual_style="x",
                scene_content=[{"id": 1, "visual": "书房", "actor": "人物1：woman/youth/chinese/小美 | 人物2：man/youth/chinese/阿明",
                                "speaking": "<1s> 我不能再这样了。 <2> 你怎么了？"}],
                language="zh", narrative="story", text="erase", use_actor=True, story_style=key, host_portrait=False)
            fixed = cp.ensure_video_no_subtitle_first_line(p)
            self.assertTrue(fixed.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), key)
            self.assertEqual(fixed.count(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), 1, key)
            self.assertNotIn("永远不许加任何字幕！永远不许加任何字幕！", fixed, key)

    def test_self_talk_rule_and_tag_stripped_before_tts(self):
        for key in ("step_story", "story_speak"):  # step_story = 旧存值，读作故事对话
            for h in CASES:
                self.assertIn(nm.SELF_TALK_RULE, nm.speaking_rule(key, h), (key, h))
        from utility.speaking_marks import parse_speaking_turns

        self.assertTrue(all("<" not in t.text for t in parse_speaking_turns("<1s> 我一直以为…… <2> 你怎么了？ <1> 没事。")))


if __name__ == "__main__":
    unittest.main()
