"""t262: 主持人节目并入故事表演；故事表演按讲员（有肖像 / 没肖像 / 没有）分三种情况；
场景生成、视频生成、节目生成三处同一方式的说话 / 表演规则逐字节一样（共用 utility/narration_modes.py）。
t263: 讲员的情况（a 有肖像 / b 没肖像 / c 没有讲员）永远由真实数据决定，没有「不知道（any）」；
场景生成按人物栏里的讲员 + 他的肖像把规则拼进模板，不再写死在模板里。

需要真实 config / project_manager 的检查（讲员行解析、项目创建、节目生成）在子进程里跑，不装桩，只读，不写任何项目 / 列表数据。"""
import json
import os
import string
import subprocess
import sys
import unittest

from tests.test_video_speaker_semantics import _install_stubs, _scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_install_stubs()

import config_channel as cc  # noqa: E402
import config_prompt as cp  # noqa: E402
from utility import cast_preset as cpr  # noqa: E402
from utility import narration_modes as nm  # noqa: E402

STYLE = "三维卡通 (Pixar-Art-Cartoon)"
# t266: 短故事已并入故事对话，只剩三种方式（名字沿用 FOUR* 只是为了少改测试）
FOUR = ["播客", "故事对话", "故事表演"]
FOUR_KEYS = ["podcast", "story_speak", "story_act"]
CASES = (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER, nm.HOST_NONE)  # (a) (b) (c)
LEGACY_ACT = ("counselor", "Counselor", "Series · Counselor", "Series . Counselor", "主持人节目", "主持人節目",
              "tech", "exec", "技术方案汇报", "高管简报")


def _real(code):
    """在真实环境（不装桩）跑一小段 python，返回最后一行打印的 JSON。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2500:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


_BASE_TEMPLATE = {
    "podcast": lambda: cc.COUNSELING_TALK_SCENES,
    "story_speak": lambda: cc.COUNSELING_SERIES_STORY_SPEAK,
    "story_act": lambda: cc.COUNSELING_SERIES_STORY_ACT,
}


def preview_prompt(key, host=nm.HOST_NONE, params=None):
    """场景生成里最终拼出来的模板（规则按讲员的真实情况 host 现拼进去）。"""
    p = dict(params or {})
    p["host_case"] = host
    return cc.resolve_dynamic_scene_template(nm.LABEL_OF[key], _BASE_TEMPLATE[key](), p)


PREVIEW_TEMPLATE = {k: (lambda k=k: preview_prompt(k)) for k in FOUR_KEYS}

# 视频生成 / 节目生成 子进程里共用的演员：讲员 + 两个人物（真实的行格式：" | " 分隔）
_REAL_SETUP = r'''
import json
import config, project_manager as pm, config_prompt as cp
from utility import narration_modes as nm
STYLE = "三维卡通 (Pixar-Art-Cartoon)"
HOST = {"role": "host", "label": "讲员", "body": "woman/mature/chinese/秦"}
P1 = {"role": "person", "label": "人物1", "body": "man/youth/chinese/阿明（低头）"}
P2 = {"role": "person", "label": "人物2", "body": "woman/youth/chinese/小美"}
def actors(*rows):
    return pm.format_actor_entries(list(rows))
def scene(actor, speaking, story=True):
    d = {"id": 1, "visual": "两人在老屋里。", "actor": actor, "speaking": speaking}
    if story:
        d["story_content"] = "阿明把信放回抽屉，小美看着他。"
    return d
def video(sc, host_portrait=None, mode="story_act", use_actor=True, use_speaking=True):
    return cp.build_video_flow_prompt(frames="one", background="none", evolve="keep", visual_style=STYLE,
        scene_content=[sc], language="zh", narrative="story", text="erase", use_visual=True,
        use_speaking=use_speaking, use_actor=use_actor, story_style=mode, host_portrait=host_portrait)
'''


class NotOfferedAnywhere(unittest.TestCase):
    """主持人节目（counselor）不再出现在任何窗口的选项里。"""

    def test_table_and_dropdown_labels(self):
        self.assertEqual([k for k, _l in nm.MODES], FOUR_KEYS)
        self.assertEqual(list(nm.MODE_LABELS), FOUR)
        self.assertEqual(list(cp.STORY_STYLE_LABELS), FOUR)  # 魔法工作流主下拉 + 视频生成窗口单选
        self.assertEqual([k for k, _l in cp.STORY_STYLE_CHOICES], FOUR_KEYS)
        self.assertNotIn("counselor", nm.NARRATIVE)
        self.assertNotIn("counselor", cc.SERIES_STYLE_LABELS)
        self.assertNotIn("counselor", cpr.MODE_RULES)
        self.assertNotIn("counselor", cpr.MODE_NAMES)
        self.assertFalse(hasattr(cc, "COUNSELING_SERIES_COUNSELOR_FRAME"))
        self.assertNotIn("主持人节目", list(cp.STORY_STYLE_LABELS))

    def test_preview_window_dropdown_has_four(self):
        """预览窗口「场景生成」下拉：每个有这组选项的频道，都没有 主持人节目 / Series · Counselor。"""
        res = _real(
            'import json, config\n'
            'out = {}\n'
            'for ch, c in config.CHANNEL_CONFIG.items():\n'
            '    ch_labels = [l for l, _t in (c.get("scenes_prompt_choices") or [])]\n'
            '    out[ch] = ch_labels\n'
            'print(json.dumps(out, ensure_ascii=False))')
        self.assertEqual(res["counseling"], FOUR)
        for ch, labels in res.items():
            for lab in labels:
                self.assertNotIn("主持人节目", lab, ch)
                self.assertNotIn("Counselor", lab, ch)

    def test_windows_read_the_one_table(self):
        wf = _read("gui", "workflow", "wf_layout.py")  # 魔法工作流主窗口「叙事方式」下拉
        self.assertIn("values=list(config_prompt.STORY_STYLE_LABELS)", wf)
        vd = _read("gui", "video_prompt_dialog.py")  # 视频生成窗口单选
        self.assertIn("for value, label in config_prompt.STORY_STYLE_CHOICES:", vd)
        self.assertNotIn('"counselor"', vd)
        cli = _read("cli", "commands.py")
        self.assertNotIn('"主持人节目"', cli)
        cfg = _read("config.py")
        self.assertNotIn("COUNSELOR_FRAME", cfg)

    def test_program_window_modes(self):
        """节目生成跟预览窗口的场景生成方式走：三种（t266: 短故事已并入故事对话），没有 counselor。"""
        seen = {}
        for lab in FOUR:
            shown, key, narrative = cpr.program_mode_narrative(lab)
            seen[lab] = (shown, key, narrative)
        self.assertEqual(seen, {"播客": ("播客", "podcast", "story"),
                                "故事对话": ("故事对话", "story_speak", "story"),
                                "故事表演": ("故事表演", "story_act", "story")})
        res = _real(
            'import json\nfrom gui.dl import prompts_notebooklm as pn\n'
            'print(json.dumps({l: pn.program_mode_key(l) for l in %r}, ensure_ascii=False))' % (FOUR + list(LEGACY_ACT)))
        for lab in FOUR:
            self.assertEqual(res[lab], FOUR_KEYS[FOUR.index(lab)], lab)
        for lab in LEGACY_ACT:
            self.assertEqual(res[lab], "story_act", lab)


class LegacyValuesLoadAsStoryAct(unittest.TestCase):
    def test_every_resolver(self):
        for old in LEGACY_ACT:
            self.assertEqual(nm.normalize(old), "story_act", old)
            self.assertEqual(cp.normalize_story_style(old), "story_act", old)
            self.assertEqual(cp.story_style_label(cp.normalize_story_style(old)), "故事表演", old)
            self.assertEqual(cp.story_style_narrative(old), "story", old)
            self.assertEqual(cpr.program_mode_narrative("", old)[:2], ("故事表演", "story_act"), old)  # 存的 story_style 值
        for old in ("Series · Counselor", "Series . Counselor", "Counselor", "主持人节目"):  # 存的下拉 label
            self.assertEqual(cpr.mode_for_label(old), "story_act", old)
            self.assertEqual(cpr.program_mode_narrative(old)[:2], ("故事表演", "story_act"), old)
            self.assertEqual(cc.canonical_prompt_label(old), "故事表演", old)
            self.assertEqual(cc.series_style_key(old), "story_act", old)
        self.assertEqual(cp.NARRATIVE_TO_STORY_STYLE["tech"], "story_act")
        self.assertEqual(cp.NARRATIVE_TO_STORY_STYLE["exec"], "story_act")

    def test_saved_project_values(self):
        import project_manager

        old = project_manager.PROJECT_CONFIG
        try:
            for raw in LEGACY_ACT:
                for cfg in ({"story_style": raw}, {"scene_prompt_label": raw},
                            {"project_profile": {"scene_prompt_label": raw}}):
                    project_manager.PROJECT_CONFIG = cfg
                    self.assertEqual(cp.project_story_style(), "story_act", (raw, cfg))
            for narr in ("tech", "exec"):
                project_manager.PROJECT_CONFIG = {"video_prompt": {"narrative": narr}}
                self.assertEqual(cp.project_story_style(), "story_act", narr)
            project_manager.PROJECT_CONFIG = {"story_style": "story_speak"}  # 别的项目不动
            self.assertEqual(cp.project_story_style(), "story_speak")
        finally:
            project_manager.PROJECT_CONFIG = old

    def test_video_prompt_with_legacy_value_uses_story_act_rules(self):
        for raw in ("counselor", "主持人节目", "tech"):
            p = cp.build_video_flow_prompt(
                frames="one", background="none", evolve="keep", visual_style=STYLE, scene_content=[_scene("")],
                language="zh", narrative=cp.story_style_narrative(raw), text="erase", use_visual=True,
                use_speaking=False, use_actor=True, story_style=raw)
            # 视频窗口当前方式 = 故事表演；场景里没有讲员 -> (c) 情况的规则
            self.assertIn(nm.performance_rule("story_act", nm.HOST_NONE), p, raw)
            self.assertIn("Video_choices:\n故事表演", p, raw)

    def test_old_project_in_scene_editor_canonicalizes(self):
        src = _read("gui", "dl", "scene_editor.py")
        self.assertIn("canonical_prompt_label", src)
        self.assertNotIn("COUNSELING_SERIES_COUNSELOR_FRAME", src)


class SharedRuleText(unittest.TestCase):
    def test_no_braces_and_exact_in_preview_template(self):
        for key in FOUR_KEYS:
            for host in CASES:
                spk, perf = nm.speaking_rule(key, host), nm.performance_rule(key, host)
                for txt in (spk, perf, nm.rules_block(key, host)):
                    self.assertTrue(txt.strip(), key)
                    self.assertNotIn("{", txt)
                    self.assertNotIn("}", txt)
                tpl = preview_prompt(key, host)
                self.assertEqual(tpl.count(spk), 1, (key, host))
                self.assertEqual(tpl.count(perf), 1, (key, host))
                fields = {f for _a, f, _b, _c in string.Formatter().parse(tpl) if f}
                self.assertTrue(fields <= {"language", "topic", "instruction", "content", "cast", "narrator", "episodes",
                                           "episode"}, (key, fields))

    def test_preview_final_prompt_keeps_rules_for_every_episode_setting(self):
        for key in FOUR_KEYS:
            for host in CASES:
                for params in ({}, {"episodes": 1}, {"episodes": 3, "episode": 2},
                               {"episodes": 3, "episode": 2, "episode_only": True}, {"steps": 2}):
                    out = preview_prompt(key, host, params)
                    for rule in (nm.speaking_rule(key, host), nm.performance_rule(key, host)):
                        self.assertEqual(out.count(rule), 1, (key, host, params))

    def test_templates_do_not_bake_in_rules(self):
        """t263: 规则不再写死在模板里：基础模板里没有规则段，规则只在 resolve 时按讲员情况拼进去。"""
        for key in ("podcast", "story_speak", "story_act"):
            self.assertNotIn(nm.RULES_BLOCK_HEAD, _BASE_TEMPLATE[key](), key)
        self.assertNotIn(nm.RULES_BLOCK_HEAD, cc.COUNSELING_STORY_STEP)
        self.assertNotIn("No cast was chosen", cc.COUNSELING_TALK_SCENES)
        self.assertNotIn("CAST is EMPTY", cc.COUNSELING_TALK_SCENES)

    def test_with_rules_block_inserts_before_scene_follow_marker(self):
        for key in FOUR_KEYS:
            body = "Write scenes.\n*** EPISODES: x\nINPUT {content}\n"
            out = nm.with_rules_block(body, key)
            self.assertIn(nm.speaking_rule(key), out)
            self.assertLess(out.index(nm.speaking_rule(key)), out.index("*** EPISODES:"))

    def test_story_act_text_per_case(self):
        a, b, c = (nm.speaking_rule("story_act", h) for h in (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER, nm.HOST_NONE))
        # 三种情况互不相同；没有「any」
        self.assertEqual(len({a, b, c}), 3)
        self.assertFalse(hasattr(nm, "HOST_ANY"))
        for txt in (a, b, c):
            self.assertIn("do not speak on camera", txt)  # 人物任何情况都不在镜头上说话
            self.assertIn("Sound effects only, never music", txt)
            for needle in ("(a)", "(b)", "(c)", "THREE CASES"):
                self.assertNotIn(needle, txt)
        self.assertIn("has a portrait (肖像)", a)
        self.assertIn("The 讲员 explains every scene", a)
        self.assertIn("shown on screen", a)
        self.assertIn("has no portrait (肖像)", b)
        self.assertIn("explains every scene as a background voice-over", b)
        self.assertIn("never shown on screen, no lip-sync", b)
        self.assertIn("there is no 讲员", c)
        self.assertIn("Nobody speaks at all", c)
        for case_txt in (nm.performance_rule("story_act", h) for h in CASES):
            self.assertIn("Sound effects only, never music", case_txt)
        self.assertEqual(nm.host_case(False), nm.HOST_NONE)
        self.assertEqual(nm.host_case(True, True), nm.HOST_PORTRAIT)
        self.assertEqual(nm.host_case(True, False), nm.HOST_VOICEOVER)
        self.assertEqual(nm.host_case(True), nm.HOST_VOICEOVER)

    def test_other_modes_only_change_with_a_real_host(self):
        # t266: 短故事已并入故事对话：旧存值读作故事对话，没有单独的 step_story 规则
        self.assertEqual(nm.normalize("短故事"), "story_speak")
        self.assertEqual(nm.speaking_rule("step_story"), nm.speaking_rule("story_speak"))
        self.assertIn("there is no 讲员", nm.speaking_rule("story_speak"))
        # 播客 / 故事对话：讲员在不在、有没有肖像各是一段话
        for key in ("podcast", "story_speak"):
            self.assertEqual(len({nm.rules_block(key, h) for h in CASES}), 3, key)


class VideoPromptCases(unittest.TestCase):
    """视频生成提示词：故事表演 a / b / c 三种情况都从真实数据里选（讲员行 + 肖像状态）。"""

    @classmethod
    def setUpClass(cls):
        cls.res = _real(_REAL_SETUP + r'''
host_speech = "<1> 今天讲一个关于信的故事。"
out = {}
out["a"] = video(scene(actors(HOST, P1, P2), host_speech, story=False), True)
out["b"] = video(scene(actors(HOST, P1, P2), host_speech, story=False), False)
out["c"] = video(scene(actors(P1, P2), ""), None, use_speaking=True)
# t263: 没有「不知道」。host_portrait 不给（None）= 按场景 actor 里的讲员现查讲员库（这里换成固定的查找，结果可重复）
_real_finder = cp.host_portrait_finder
sc_full = scene(actors(HOST, P1, P2), host_speech, story=True)
cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png")
out["derived_portrait"] = video(sc_full, None)
out["derived_unticked_portrait"] = video(sc_full, None, use_actor=False)  # 人物没勾：照样按真实讲员算
cp.host_portrait_finder = lambda *a, **k: (lambda row: "")
out["derived_voiceover"] = video(sc_full, None)
out["derived_unticked_voiceover"] = video(sc_full, None, use_actor=False)
out["derived_none"] = video(scene(actors(P1, P2), ""), None)
# 旧数据：有讲话但讲员不在出镜名单里（以前这条被静音）=> 背景画外音（b）
out["legacy_voiceover"] = video(scene(actors(P1, P2), host_speech), None)
# 讲员的肖像状态用真实函数从场景 + 肖像查找里得出（永远是 True / False）
sc = scene(actors(HOST, P1, P2), host_speech, story=False)
out["portrait_state"] = [cp.video_host_portrait([sc], lambda s: [(1, "秦", "x.png")]),
                         cp.video_host_portrait([sc], lambda s: [(2, "阿明", "y.png")]),
                         cp.video_host_portrait([sc], lambda s: []),
                         cp.video_host_portrait([scene(actors(P1, P2), "")], lambda s: []),
                         cp.video_host_portrait([sc], None),  # 查询函数没给：直接查讲员库（这里固定为没有）
                         cp.video_host_portrait([sc], lambda s: 1 / 0)]  # 场景肖像查询出错：改按讲员库查
cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png")
out["portrait_state"].append(cp.video_host_portrait([sc], None))
def _boom(row):
    raise RuntimeError("avatar library down")
cp.host_portrait_finder = lambda *a, **k: _boom
out["portrait_state"].append(cp.video_host_portrait([sc], None))  # 讲员库本身也出错：按没有肖像处理（画外音）
cp.host_portrait_finder = _real_finder
print(json.dumps(out, ensure_ascii=False))
''')

    def _count(self, p, rule):
        return p.count(rule)

    def test_case_a_host_with_portrait(self):
        p = self.res["a"]
        for rule in (nm.speaking_rule("story_act", nm.HOST_PORTRAIT), nm.performance_rule("story_act", nm.HOST_PORTRAIT)):
            self.assertEqual(p.count(rule), 1)
        self.assertIn("exactly 3 people are in this clip: 讲员, 阿明, 小美", p)  # 讲员出镜，和人物一起
        self.assertIn("actor: H woman/mature/chinese/秦 | man/youth/chinese/阿明", p)  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertIn("lip-synced", p.lower())
        self.assertNotIn("off-screen voice-over of the 讲员", p)

    def test_case_b_host_without_portrait_is_voice_over_only(self):
        p = self.res["b"]
        for rule in (nm.speaking_rule("story_act", nm.HOST_VOICEOVER), nm.performance_rule("story_act", nm.HOST_VOICEOVER)):
            self.assertEqual(p.count(rule), 1)
        self.assertIn("off-screen voice-over of the 讲员", p)
        self.assertIn("Do not show a narrator or host", p)
        self.assertIn("exactly 2 people are in this clip: 阿明, 小美", p)   # 讲员不在出镜名单
        self.assertNotIn("讲员：woman/mature/chinese/秦", p)                # 也不在 actor 载荷里
        self.assertNotIn("H woman/mature/chinese/秦", p)  # t280: 新写法也没有
        self.assertIn("narration: 今天讲一个关于信的故事。", p)
        self.assertIn("actor: man/youth/chinese/阿明（低头） | woman/", p)  # t280: 新写法（讲员 H …，人物不带 人物N：）

    def test_case_c_no_host(self):
        p = self.res["c"]
        for rule in (nm.speaking_rule("story_act", nm.HOST_NONE), nm.performance_rule("story_act", nm.HOST_NONE)):
            self.assertEqual(p.count(rule), 1)
        self.assertIn("Speech: nobody speaks.", p)
        self.assertIn("no narrator, no voice-over", p)
        self.assertIn("exactly 2 people are in this clip: 阿明, 小美", p)

    def test_no_unknown_case_anywhere(self):
        """t263: 没有「不知道」：不给 host_portrait、没勾人物，也是 a / b / c 中的一种，规则只写这一种。"""
        pairs = {"derived_portrait": nm.HOST_PORTRAIT, "derived_unticked_portrait": nm.HOST_PORTRAIT,
                 "derived_voiceover": nm.HOST_VOICEOVER, "derived_unticked_voiceover": nm.HOST_VOICEOVER,
                 "derived_none": nm.HOST_NONE}
        for k, case in pairs.items():
            p = self.res[k]
            for other in CASES:
                n = 1 if other == case else 0
                self.assertEqual(p.count(nm.speaking_rule("story_act", other)), n, (k, other))
                self.assertEqual(p.count(nm.performance_rule("story_act", other)), n, (k, other))
            for needle in ("(a) A 讲员", "(b) A 讲员", "THREE CASES"):
                self.assertNotIn(needle, p, k)

    def test_story_content_next_to_host_speech(self):
        """t263: 有讲员的故事表演：每一场既有讲员的讲解（speaking），也有人物演的事（story_content）。"""
        for k in ("derived_portrait", "derived_voiceover"):
            self.assertIn("阿明把信放回抽屉", self.res[k], k)

    def test_legacy_speech_without_host_row_is_voice_over(self):
        p = self.res["legacy_voiceover"]
        self.assertEqual(p.count(nm.speaking_rule("story_act", nm.HOST_VOICEOVER)), 1)
        self.assertIn("off-screen voice-over of the 讲员", p)
        self.assertIn("exactly 2 people are in this clip: 阿明, 小美", p)

    def test_portrait_state_from_real_scene_data(self):
        self.assertEqual(self.res["portrait_state"], [True, False, False, False, False, False, True, False])

    def test_invariants_every_case(self):
        for k in ("a", "b", "c", "derived_portrait", "derived_unticked_voiceover", "derived_none", "legacy_voiceover"):
            fixed = cp.ensure_video_no_subtitle_first_line(self.res[k])
            self.assertTrue(fixed.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), k)
            self.assertEqual(fixed.count(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), 1, k)  # 禁字幕只在最前面说一次
            self.assertIn("never music", self.res[k], k)


class ByteIdenticalAcrossThreePrompts(unittest.TestCase):
    """视频生成 / 场景生成 / 节目生成：每种方式的说话和表演规则逐字节一样。"""

    @classmethod
    def setUpClass(cls):
        cls.res = _real(_REAL_SETUP + r'''
from gui.dl import prompts_notebooklm as pn
HOST_SPEECH = "<1> 今天讲一个关于信的故事。"
PEOPLE_SPEECH = "<1> 你今天怎麼来了？ <2> 想你了。"
out = {"video": {}, "program": {}, "program_cases": {}, "video_cases": {}, "derived": {}}
for key, lab in nm.MODES:
    # 每种方式：视频 / 节目的人物都是真实的 讲员 + 两个人物，讲员肖像固定为「有」
    rows = (HOST, P1, P2)
    sc = scene(actors(*rows), HOST_SPEECH if key == "story_act" else PEOPLE_SPEECH, story=key == "story_act")
    cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png")
    out["video"][key] = video(sc, True, mode=key)
    out["program"][key] = pn.build_program_cast_block({"story_actors": actors(*rows)}, lab, "slides", "panel",
                                                      host_case=None if key != "story_act" else "portrait")
for case, hp, rows in (("portrait", True, (HOST, P1, P2)), ("voiceover", False, (HOST, P1, P2)), ("none", None, (P1, P2))):
    sp = "<1> 今天讲一个关于信的故事。" if case != "none" else ""
    out["video_cases"][case] = video(scene(actors(*rows), sp, story=case != "voiceover"), hp)
    out["program_cases"][case] = pn.build_program_cast_block({"story_actors": actors(*rows)}, "故事表演", "slides", "panel", host_case=case)
# 节目生成里的讲员情况从真实演员文字 + 肖像查找得出
find_yes, find_no = (lambda row: "a.png"), (lambda row: "")
t_host, t_people = actors(HOST, P1, P2), actors(P1, P2)
cp.host_portrait_finder = lambda *a, **k: find_no  # 没给查找函数：默认按讲员库查（这里固定为没有）
out["derived"] = {"portrait": cp.program_host_case([t_host], find_yes), "voiceover": cp.program_host_case([t_host], find_no),
                  "none": cp.program_host_case([t_people], find_yes), "default_finder": cp.program_host_case([t_host], None),
                  "no_cast": cp.program_host_case([], None), "none_input": cp.program_host_case(None, None)}
# 节目生成不带 host_case 参数时自己按人物栏得出
out["derived_block"] = pn.build_program_cast_block({"story_actors": t_people}, "故事表演", "slides", "panel")
out["derived_block_host"] = pn.build_program_cast_block({"story_actors": t_host}, "故事表演", "slides", "panel")
print(json.dumps(out, ensure_ascii=False))
''')

    def test_each_mode_three_windows(self):
        for key in FOUR_KEYS:
            host = nm.HOST_PORTRAIT
            spk, perf = nm.speaking_rule(key, host), nm.performance_rule(key, host)
            tpl = preview_prompt(key, host)
            vid = self.res["video"][key]
            prog = self.res["program"][key]
            for src, name in ((tpl, "场景生成"), (prog, "节目生成"), (vid, "视频生成")):
                for rule in (spk, perf):
                    self.assertEqual(src.count(rule), 1, (key, name))
                    i = src.index(rule)
                    self.assertEqual(src[i:i + len(rule)].encode("utf-8"), rule.encode("utf-8"), (key, name))

    def test_story_act_cases_video_vs_program(self):
        for case in ("portrait", "voiceover", "none"):
            spk, perf = nm.speaking_rule("story_act", case), nm.performance_rule("story_act", case)
            for src in (self.res["video_cases"][case], self.res["program_cases"][case]):
                self.assertEqual(src.count(spk), 1, case)
                self.assertEqual(src.count(perf), 1, case)
        # 三种情况的文字互不相同
        self.assertEqual(len({nm.speaking_rule("story_act", c) for c in ("portrait", "voiceover", "none")}), 3)

    def test_program_host_case_from_real_data(self):
        self.assertEqual(self.res["derived"], {"portrait": "portrait", "voiceover": "voiceover", "none": "none",
                                               "default_finder": "voiceover", "no_cast": "none", "none_input": "none"})
        self.assertEqual(self.res["derived_block"].count(nm.speaking_rule("story_act", nm.HOST_NONE)), 1)
        self.assertEqual(self.res["derived_block_host"].count(nm.speaking_rule("story_act", nm.HOST_VOICEOVER)), 1)

    def test_short_story_is_merged_into_story_dialogue_in_program(self):
        # t266: 短故事已并入故事对话：没有 step_story 这个方式；旧值读作故事对话，规则就是故事对话那一份
        self.assertNotIn("step_story", self.res["program"])
        self.assertEqual(nm.speaking_rule("step_story"), nm.speaking_rule("story_speak", nm.HOST_NONE))
        self.assertEqual(nm.performance_rule("step_story"), nm.performance_rule("story_speak", nm.HOST_NONE))
        self.assertIn(nm.speaking_rule("story_speak", nm.HOST_PORTRAIT), self.res["program"]["story_speak"])

    def test_program_cast_block_never_names_counselor(self):
        for key in FOUR_KEYS:
            blk = self.res["program"][key]
            self.assertNotIn("Counselor", blk)
            self.assertNotIn("主持人节目", blk)


class ProgramFlowPrompt(unittest.TestCase):
    def test_slide_flow_per_mode_defers_to_shared_rules(self):
        for key in FOUR_KEYS:
            p = cp.build_slide_flow_prompt(target="slideshow", text="x", visual_style=STYLE,
                                          scene_content=[_scene("<1> 你好。 <2> 嗯。")], narrative="story",
                                          output="slides", content_source="content.pdf", mode=key)
            self.assertIn("follow the NARRATION MODE rules in PEOPLE AND PRESENTATION exactly", p, key)
            self.assertNotIn("Counselor", p, key)
        # 无 mode：旧行为不变
        p = cp.build_slide_flow_prompt(target="slideshow", text="x", visual_style=STYLE,
                                      scene_content=[_scene("<1> 你好。")], narrative="story", output="slides",
                                      content_source="content.pdf")
        self.assertNotIn("follow the NARRATION MODE rules in PEOPLE AND PRESENTATION exactly", p)

    def test_program_mode_notes(self):
        self.assertEqual(sorted(cp.PROGRAM_MODE_NOTES), ["podcast", "story_act"])
        self.assertTrue(cp.program_mode_note("主持人节目"))  # 旧值读作故事表演


class StoryActTemplate(unittest.TestCase):
    def test_one_template_per_host_case_and_no_narrator_scenes(self):
        """t263: 没有「叙述场景」：有讲员 = 每一场都由讲员讲解；没有讲员 = 没有任何说话。"""
        self.assertEqual(set(cc.STORY_ACT_TEMPLATES), set(CASES))
        for case, t in cc.STORY_ACT_TEMPLATES.items():
            for gone in ("THREE CASES", "narrator scene", "presenting scene", "Only with a 讲员", "Without a 讲员: none of these"):
                self.assertNotIn(gone, t, (case, gone))
            self.assertNotIn(nm.RULES_BLOCK_HEAD, t)  # 规则在 resolve 时拼进去
            fields = {f for _a, f, _b, _c in string.Formatter().parse(t) if f}
            self.assertTrue(fields <= {"language", "topic", "instruction", "content", "cast", "narrator", "episodes",
                                       "episode"}, (case, fields))
            self.assertNotIn("Series · Counselor", t)
            self.assertNotIn("主持人节目", t)
        self.assertIs(cc.COUNSELING_SERIES_STORY_ACT, cc.STORY_ACT_TEMPLATES[nm.HOST_NONE])

    def test_host_scenes_are_every_scene(self):
        for case in (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER):
            t = cc.STORY_ACT_TEMPLATES[case]
            self.assertIn("explains EVERY scene", t, case)
            self.assertIn("lists the 讲员 first (position 1)", t, case)
            self.assertIn("Every scene has ``story_content`` (what the 人物 act) AND ``speaking``", t, case)
            self.assertIn('"speaking": "The 讲员', t, case)
        self.assertIn("shows the 讲员 on screen", cc.STORY_ACT_TEMPLATES[nm.HOST_PORTRAIT])
        self.assertIn("never write the 讲员 into the picture", cc.STORY_ACT_TEMPLATES[nm.HOST_VOICEOVER])
        none = cc.STORY_ACT_TEMPLATES[nm.HOST_NONE]
        self.assertIn("No scene has ``speaking``", none)
        self.assertNotIn('"speaking"', none)

    def test_resolve_picks_the_template_by_host_case(self):
        for case in CASES:
            out = preview_prompt("story_act", case)
            self.assertIn(cc.STORY_ACT_TEMPLATES[case][:300].strip().split("\n")[0], out)
            self.assertEqual(out.count(nm.speaking_rule("story_act", case)), 1, case)
        # 不认识的 host_case 一律当没有讲员（不会写出三种情况）
        bad = cc.resolve_dynamic_scene_template("故事表演", cc.COUNSELING_SERIES_STORY_ACT, {"host_case": "any"})
        self.assertEqual(bad.count(nm.speaking_rule("story_act", nm.HOST_NONE)), 1)


class NewProjectDefault(unittest.TestCase):
    def test_four_modes_carried_into_new_project(self):
        for lab, key in zip(FOUR, FOUR_KEYS):
            self.assertEqual(nm.new_project_default(lab), key, lab)
        self.assertEqual(nm.new_project_default("短故事"), "story_speak")  # t266: 短故事已并入故事对话
        self.assertEqual(nm.new_project_default("主持人节目"), "story_act")  # 旧选择读作故事表演
        self.assertEqual(nm.new_project_default("Series · Counselor"), "story_act")
        self.assertEqual(nm.new_project_default("Mini Story", "podcast"), "podcast")

    def test_look_flows_into_project_creation(self):
        code = r"""
import json
import project_manager as pm
from utility import narration_modes as nm
seen = {}
class FakeDialog:
    def __init__(self, **kw):
        seen.clear(); seen.update(kw)
        self.story_result = {"action": "cancel"}
        self.selected_config = None
        self.dialog = type("D", (), {"winfo_exists": lambda s: False})()
pm.ProjectSelectionDialog = FakeDialog
pm.ProjectConfigManager = lambda *a, **k: object()
res = {}
for lab in %s:
    key = nm.new_project_default(lab)
    pm.create_project_with_initial_raw(parent=None, channel="counseling", language="zh", narrator=None, visual_style=None,
        analyzed_content=None, scene_content=[{"caption": "x"}], topic_category=None, topic_subtype=None, topic_tags=None,
        story_style=key)
    res[lab] = [key, seen.get("initial_story_style"), pm.config_prompt.normalize_story_style(seen.get("initial_story_style"))]
print(json.dumps(res, ensure_ascii=False))
""" % repr(FOUR + ["主持人节目"])
        res = _real(code)
        for lab, key in zip(FOUR, FOUR_KEYS):
            self.assertEqual(res[lab], [key, key, key], lab)
        self.assertEqual(res["主持人节目"], ["story_act", "story_act", "story_act"])

    def test_scene_editor_and_video_window_use_it(self):
        src = _read("gui", "dl", "scene_editor.py")
        self.assertIn("_nm.new_project_default(label)", src)
        self.assertIn('look["story_style"] = st', src)
        import project_manager

        old = project_manager.PROJECT_CONFIG
        try:
            for lab, key in zip(FOUR, FOUR_KEYS):
                project_manager.PROJECT_CONFIG = {"story_style": key}
                self.assertEqual(cp.project_story_style(), key)
                project_manager.PROJECT_CONFIG = {"scene_prompt_label": lab}
                self.assertEqual(cp.project_story_style(), key)
        finally:
            project_manager.PROJECT_CONFIG = old
        vd = _read("gui", "video_prompt_dialog.py")
        self.assertIn("style_var = tk.StringVar(value=config_prompt.project_story_style())", vd)


class Invariants(unittest.TestCase):
    def _video(self, mode, speaking):
        return cp.build_video_flow_prompt(
            frames="one", background="none", evolve="keep", visual_style=STYLE, scene_content=[_scene(speaking)],
            language="zh", narrative=cp.story_style_narrative(mode), text="erase", use_visual=True,
            use_speaking=bool(speaking), use_actor=True, story_style=mode)

    def test_no_subtitle_rules_every_mode(self):
        for key in FOUR_KEYS:
            for speaking in ("<1> 你好。 <2> 嗯。", "<1s> 我不能再这样了。明天一定要开口。", ""):
                fixed = cp.ensure_video_no_subtitle_first_line(self._video(key, speaking))
                self.assertTrue(fixed.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), key)

    def test_self_talk_no_lipsync_every_mode(self):
        for key in FOUR_KEYS:
            p = self._video(key, "<1s> 我一直以为…… <2> 你怎么了？ <1> 没事。")
            self.assertIn("no lip-sync", p.lower(), key)
            self.assertIn(cp.SPEAKER_MARK_IDENTITY_RULE, p, key)

    def test_self_talk_tag_stripped_before_tts(self):
        from utility.speaking_marks import parse_speaking_turns

        turns = parse_speaking_turns("<1s> 我一直以为…… <2> 你怎么了？ <1> 没事。")
        self.assertTrue(all("<" not in t.text for t in turns))

    def test_actor_positions_authoritative(self):
        p = self._video("story_speak", "<2> 先说。 <1> 后说。")
        self.assertIn("``actor``", p)


if __name__ == "__main__":
    unittest.main()
