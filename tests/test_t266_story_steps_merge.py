"""t266: 短故事并入故事对话；步数 0–6 决定故事对话的结构；删掉「只重新生成第 k 集」；叙事方式下拉缩窄一半。

需要真实 config / downloader 的检查在子进程里跑，不装桩，只读，不写任何项目 / 列表数据。"""
import json
import os
import re
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
THREE = ["播客", "故事对话", "故事表演"]
THREE_KEYS = ["podcast", "story_speak", "story_act"]
LEGACY_SHORT = ("短故事", "Step Story", "step story", "Short Story", "2 Step Story", "4 Step Story", "6 Step Story",
                "step_story", "story_mini")
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


def _steps_prompt(steps, host=nm.HOST_NONE, label="故事对话"):
    return cc.resolve_dynamic_scene_template(label, cc.COUNSELING_SERIES_STORY_SPEAK, {"steps": steps, "host_case": host})


class ThreeModesOnly(unittest.TestCase):
    """短故事不在任何叙事方式列表里：预览、视频生成、魔法工作流下拉、CLI、人物设置、节目生成。"""

    def test_table_and_every_dropdown(self):
        self.assertEqual([k for k, _l in nm.MODES], THREE_KEYS)
        self.assertEqual(list(nm.MODE_LABELS), THREE)
        self.assertNotIn("step_story", nm.NARRATIVE)
        self.assertEqual(list(cp.STORY_STYLE_LABELS), THREE)  # 魔法工作流下拉 + 视频生成窗口单选
        self.assertEqual([k for k, _l in cp.STORY_STYLE_CHOICES], THREE_KEYS)
        self.assertEqual(list(cc.SERIES_STYLE_LABELS.values()), THREE)
        self.assertEqual(sorted(cpr.MODE_RULES), sorted(THREE_KEYS))
        self.assertEqual(list(cpr.MODE_NAMES.values()), THREE)
        wf = _read("gui", "workflow", "wf_layout.py")
        self.assertIn("values=list(config_prompt.STORY_STYLE_LABELS)", wf)
        vd = _read("gui", "video_prompt_dialog.py")
        self.assertIn("for value, label in config_prompt.STORY_STYLE_CHOICES:", vd)

    def test_preview_dropdown_and_cli_lists(self):
        res = _real(
            'import json, config\n'
            'from cli import commands\n'
            'out = {"choices": {ch: [l for l, _t in (c.get("scenes_prompt_choices") or [])]\n'
            '                   for ch, c in config.CHANNEL_CONFIG.items()},\n'
            '       "fallback": commands.scene_lm_choice_labels_fallback()}\n'
            'print(json.dumps(out, ensure_ascii=False))')
        self.assertEqual(res["choices"]["counseling"], THREE)
        for ch, labels in res["choices"].items():
            for lab in labels:
                self.assertNotIn("短故事", lab, ch)
                self.assertNotIn("Short Story", lab, ch)
        self.assertEqual(res["choices"]["industry_aviation"][0], cc.STEP_STORY_LABEL)  # FlyLink 自己的固定步数故事还在
        # CLI 后备列表（config 读不到时）也没有短故事 / N Step Story；真实 config 里读到的就是下拉
        flat = list(dict.fromkeys(l for ch in res["choices"].values() for l in ch))  # t272: 连环画现在和 counseling 同一组三种方式，去重
        self.assertEqual(res["fallback"], flat[:len(res["fallback"])]
                         if res["fallback"][0] in res["choices"]["counseling"] else res["fallback"])
        cli_src = _read("cli", "commands.py")
        fb = cli_src[cli_src.index("def scene_lm_choice_labels_fallback"):cli_src.index("def scene_lm_choice_labels_resolved")]
        for gone in ('"短故事"', '"Short Story"', '"2 Step Story"', '"3 Step Story"', '"4 Step Story"'):
            self.assertNotIn(gone, fb, gone)

    def test_every_legacy_value_loads_as_story_dialogue(self):
        for old in LEGACY_SHORT:
            self.assertEqual(nm.normalize(old), "story_speak", old)
            self.assertEqual(cp.normalize_story_style(old), "story_speak", old)
        for old in ("短故事", "Step Story", "Short Story", "3 Step Story", "6 Step Story"):
            self.assertEqual(cc.canonical_prompt_label(old), "故事对话", old)
            self.assertEqual(cc.series_style_key(old), "story_speak", old)
            self.assertTrue(cc.is_series_label(old), old)
            self.assertFalse(cc.is_step_story_label(old), old)
            self.assertEqual(cpr.mode_for_label(old), "story_speak", old)
            self.assertEqual(cpr.program_mode_narrative(old), ("故事对话", "story_speak", "story"), old)
        self.assertEqual(nm.new_project_default("短故事"), "story_speak")
        self.assertEqual(nm.speaking_rule("step_story"), nm.speaking_rule("story_speak"))

    def test_legacy_label_carries_its_old_step_count(self):
        self.assertEqual(cc.legacy_step_label("3 Step Story"), 3)
        self.assertEqual(cc.legacy_step_label("Short Story"), 1)
        for label, want in (("短故事", 4), ("Step Story", 4), ("Short Story", 1), ("2 Step Story", 2), ("6 Step Story", 6),
                            ("故事对话", None), ("播客", None), ("Mini Story", None)):
            self.assertEqual(cc.legacy_story_steps(label), want, label)

    def test_program_window_follows_three_modes(self):
        res = _real(
            'import json\nfrom gui.dl import prompts_notebooklm as pn\n'
            'print(json.dumps({l: pn.program_mode_key(l) for l in %r}, ensure_ascii=False))' % (THREE + list(LEGACY_SHORT)))
        for lab, key in zip(THREE, THREE_KEYS):
            self.assertEqual(res[lab], key, lab)
        for old in ("短故事", "Step Story", "4 Step Story", "Short Story", "step_story"):
            self.assertEqual(res[old], "story_speak", old)


class StepsDriveTheStructure(unittest.TestCase):
    def test_choices_and_default(self):
        self.assertEqual(cc.STORY_STEPS_CHOICES, (0, 1, 2, 3, 4, 5, 6))
        self.assertEqual(cc.STORY_STEPS_DEFAULT, 0)
        self.assertEqual((cc.STORY_STEPS_FREE, cc.STORY_STEPS_MAX), (0, 6))
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("for i in config_channel.STORY_STEPS_CHOICES", se)
        self.assertIn("tk.StringVar(value=str(config_channel.STORY_STEPS_DEFAULT))", se)
        self.assertIn('"dialogue": _dlg_steps or str(config_channel.STORY_STEPS_DEFAULT)', se)

    def test_fixed_story_steps(self):
        f = cc.fixed_story_steps
        self.assertEqual(f("故事对话"), 0)  # 没给步数 = 自由规划（旧故事对话）
        self.assertEqual(f("故事对话", {"steps": 0}), 0)
        self.assertEqual(f("故事对话", {"steps": "0"}), 0)
        for n in range(1, 7):
            self.assertEqual(f("故事对话", {"steps": n}), n)
        self.assertEqual(f("3 Step Story"), 3)  # 旧 label 带自己的步数
        self.assertEqual(f("短故事", {"steps": 5}), 5)
        self.assertEqual(f("故事对话", {"steps": "abc"}), 0)
        for lab in ("播客", "故事表演", "Lyrics to Story", cc.STEP_IMAGE_LABEL):  # 别的方式不看步数
            self.assertEqual(f(lab, {"steps": 4}), 0, lab)
        self.assertEqual(f(cc.STEP_STORY_LABEL, {"steps": 0}), cc.STEP_STORY_DEFAULT)  # FlyLink 固定步数故事至少 1 步
        self.assertEqual(f(cc.STEP_STORY_LABEL), cc.STEP_STORY_DEFAULT)

    def test_zero_is_free_planning_the_old_story_dialogue(self):
        free = cc.COUNSELING_SERIES_STORY_SPEAK
        for host in CASES:
            out0 = _steps_prompt(0, host)
            outn = cc.resolve_dynamic_scene_template("故事对话", free, {"host_case": host})  # 没有步数也是 0
            self.assertEqual(out0, outn)
            self.assertIn("*** EPISODES: ONE EPISODE", out0)
            self.assertIn("PATH A", out0)  # 系列模板：按故事需要分段 / 分集
            self.assertNotIn("has 0 scene", out0)
            self.assertNotIn("###STEP###", out0)
        # 共 N 集只在步数 0 时有效
        three = cc.resolve_dynamic_scene_template("故事对话", free, {"steps": 0, "episodes": 3})
        self.assertIn("EXACTLY 3 EPISODES", three)

    def test_n_is_exactly_n_scenes_one_story(self):
        for n in range(1, 7):
            out = _steps_prompt(n)
            self.assertIn(f"the whole (ONE) story has {n} scenes", out, n)
            self.assertIn(f"(the story has {n} scene ({n} json objects))", out, n)
            self.assertNotIn("###", out)
            self.assertNotIn("*** EPISODES:", out)  # 固定 N 场 = 一个故事，不分集
            self.assertNotIn("PATH A", out)
        # 共 N 集（episodes）对固定 N 场没有作用
        self.assertEqual(cc.resolve_dynamic_scene_template("故事对话", "", {"steps": 3, "episodes": 5}),
                         cc.resolve_dynamic_scene_template("故事对话", "", {"steps": 3, "episodes": 1}))
        self.assertNotEqual(_steps_prompt(1), _steps_prompt(2))
        self.assertIn("300–500", _steps_prompt(1))  # 1 步每场更长（旧短故事的写法）
        self.assertIn("150–300", _steps_prompt(2))
        # 旧的 "N Step Story" label 走故事对话 + 步数 N
        self.assertEqual(cc.resolve_dynamic_scene_template("3 Step Story", cc.COUNSELING_SERIES_STORY_SPEAK, {"host_case": "none"}),
                         _steps_prompt(3))

    def test_same_speaking_and_performance_rules_for_every_step_count(self):
        for host in CASES:
            spk, perf = nm.speaking_rule("story_speak", host), nm.performance_rule("story_speak", host)
            for n in range(0, 7):
                out = _steps_prompt(n, host)
                self.assertEqual(out.count(spk), 1, (host, n))
                self.assertEqual(out.count(perf), 1, (host, n))
                self.assertEqual(out.count(nm.RULES_BLOCK_HEAD), 1, (host, n))
                self.assertEqual(out.count(nm.SELF_TALK_RULE), 1, (host, n))  # 自言自语不口型：只写一次
                for other in CASES:
                    if other != host:
                        self.assertNotIn(nm.speaking_rule("story_speak", other), out, (host, n, other))
                fields = {f for _a, f, _b, _c in string.Formatter().parse(out) if f}
                self.assertTrue(fields <= {"language", "topic", "instruction", "content", "cast", "narrator",
                                           "episodes", "episode"}, (host, n, fields))

    def test_host_choice_same_as_free_planning(self):
        """故事对话 N 步和 0 步一样：人物栏有讲员 → 讲员留着，只做简短旁白（开场 / 过渡 / 收尾），写在这 N 场里面；没有讲员 → 不写。"""
        for n in range(1, 7):
            for host in (nm.HOST_PORTRAIT, nm.HOST_VOICEOVER):
                out = _steps_prompt(n, host)
                self.assertNotIn(cc.STEP_STORY_NO_HOST_MARK, out, (n, host))
                self.assertIn("The 讲员 listed in the CAST of this prompt is the narrator only", out)
                self.assertIn(f"INSIDE the {n} scenes, never as extra scenes", out)
                self.assertIn("the 讲员's lines are marked <1>", out)
                self.assertIn("Dialogue between the story people, as in 故事对话", out)
                self.assertNotIn("Series · Story Speak", out)
                # 规则块里的讲员规则 = 步数 0 的那一份
                self.assertIn(nm.scene_data_rule("story_speak", host), out)
            none = _steps_prompt(n, nm.HOST_NONE)
            self.assertIn(cc.STEP_STORY_NO_HOST_MARK, none)
            self.assertNotIn("is the narrator only", none)
            self.assertNotIn("Scene data: the 讲员", none)
        # 步数 0 的系列模板里讲员也是同一个角色：只做旁白
        self.assertIn("is the narrator only", cc.COUNSELING_SERIES_STORY_SPEAK)
        # 没有讲员时的固定 N 场 = 旧短故事的原文（讲员写法只在有讲员时才出现）
        self.assertIn(cc.STEP_STORY_NO_HOST_MARK, cc.COUNSELING_STORY_STEP)
        self.assertEqual(cc.build_story_dialogue_steps(4, nm.HOST_NONE), cc.COUNSELING_STORY_STEP)
        self.assertEqual(cc.build_story_dialogue_steps(4, nm.HOST_PORTRAIT), cc.build_step_story(cc.COUNSELING_STORY_CORE_HOST, 4))

    def test_templates_have_no_braces_besides_fields(self):
        for host in CASES:
            for n in range(0, 7):
                list(string.Formatter().parse(_steps_prompt(n, host)))  # 单个花括号会报错

    def test_program_generation_does_not_read_the_steps(self):
        """节目生成只跟「叙事方式」走，不读步数：步数 0 / 1–6 的节目生成是同一份。"""
        res = _real(r'''
import json
from gui.dl import prompts_notebooklm as pn
vd = {"story_actors": "讲员：woman/mature/chinese/秦 | 人物1：woman/youth/chinese/小美 | 人物2：man/youth/chinese/阿明"}
print(json.dumps({lab: pn.build_program_cast_block(vd, lab, "slides", "panel", host_case="portrait")
                  for lab in ("故事对话", "短故事", "4 Step Story")}, ensure_ascii=False))
''')
        self.assertEqual(res["短故事"], res["故事对话"])
        self.assertEqual(res["4 Step Story"], res["故事对话"])
        src = _read("gui", "dl", "scene_editor.py")
        prog = src[src.index("program_mode_narrative(_series_label"):src.index("program_mode=_series_label")]
        self.assertNotIn("steps", prog)
        self.assertNotIn("step_count_var", prog)

    def test_funnel_old_label_and_steps_end_to_end(self):
        res = _real(r'''
import json
import config_prompt as cp
import gui.downloader as d
fake = type("F", (), {"_channel_config_key": lambda s: "counseling", "language": "Chinese", "channel": "counseling"})()
HOST = "讲员：woman/mature/chinese/秦"
P = "人物1：man/youth/chinese/阿明（低头） | 人物2：woman/youth/chinese/小美"
out = {}
for name, lab, params, cast, portrait in (
        ("free_host", "故事对话", {"steps": 0}, HOST + " | " + P, True),
        ("n3_host", "故事对话", {"steps": 3}, HOST + " | " + P, True),
        ("n3_voice", "故事对话", {"steps": 3}, HOST + " | " + P, False),
        ("n3_nohost", "故事对话", {"steps": 3}, P, True),
        ("legacy3", "3 Step Story", None, HOST + " | " + P, True),
        ("legacy_short", "短故事", {"steps": 2}, P, True),
        ("n3_ep_ignored", "故事对话", {"steps": 3, "episodes": 4, "episode": 2, "episode_only": True}, P, True)):
    cp.host_portrait_finder = lambda *a, **k: (lambda row: "x.png" if portrait else "")
    out[name] = d.MediaGUIManager._combined_prompt_text_for_label(
        fake, {"analyzed_content": "一封旧信", "story_actors": cast}, lab, prompt_params=params)
print(json.dumps(out, ensure_ascii=False))
''')
        def lab(name):
            return res[name][0]

        def txt(name):
            return res[name][1]
        for name in res:
            self.assertEqual(lab(name), "故事对话", name)  # 旧 label 也落在故事对话
        self.assertIn("*** EPISODES:", txt("free_host"))
        self.assertIn("PATH A", txt("free_host"))
        for name, n in (("n3_host", 3), ("n3_voice", 3), ("n3_nohost", 3), ("legacy3", 3), ("legacy_short", 2),
                        ("n3_ep_ignored", 3)):
            self.assertIn(f"the whole (ONE) story has {n} scenes", txt(name), name)
            self.assertNotIn("*** EPISODES:", txt(name), name)
            self.assertEqual(txt(name).count(nm.RULES_BLOCK_HEAD), 1, name)
        # 讲员留在人物栏里（只做旁白）；没有讲员时不写、也不留
        for name in ("n3_host", "n3_voice", "legacy3"):
            self.assertIn("H woman/mature/chinese/秦", txt(name), name)  # t280: 新写法（讲员 H …，人物不带 人物N：）
            self.assertNotIn(cc.STEP_STORY_NO_HOST_MARK, txt(name), name)
            self.assertIn("is the narrator only", txt(name), name)
        self.assertIn(nm.speaking_rule("story_speak", "portrait"), txt("n3_host"))
        self.assertIn(nm.speaking_rule("story_speak", "voiceover"), txt("n3_voice"))
        for name in ("n3_nohost", "legacy_short", "n3_ep_ignored"):
            self.assertIn(cc.STEP_STORY_NO_HOST_MARK, txt(name), name)
            self.assertNotIn("is the narrator only", txt(name), name)
        self.assertEqual(txt("n3_ep_ignored"), txt("n3_nohost"))  # 第几集 / 只重生 / 共 N 集对固定 N 场没有作用


class OnlyThisEpisodeIsGone(unittest.TestCase):
    def test_no_checkbox_no_spinbox_no_params(self):
        se = _read("gui", "dl", "scene_editor.py")
        for gone in ("series_only_var", "series_only_chk", "series_ep_var", "series_ep_combo", "只重新生成第",
                     "_sync_series_episode_choices"):
            self.assertNotIn(gone, se, gone)
        body = se[se.index("def _scene_prompt_params"):se.index("def _pdf_instruction_for")]
        self.assertNotIn("episode_only", body)
        self.assertNotIn('"episode":', body)
        self.assertIn('"episodes": 1 if _fixed else _int_of(series_total_var, 1)', body)  # 固定 N 场不分集
        self.assertIn('text="共"', se)  # 共 N 集 还在
        dl = _read("gui", "downloader.py")
        for gone in ("episode_only", "merge_episode_scenes"):
            self.assertNotIn(gone, dl)
        for gone in ("episode_only", "merge_episode_scenes", "only=True"):
            self.assertNotIn(gone, _read("storyproducer", "prompts.py"))
        for name in ("episode_only", "merge_episode_scenes"):
            self.assertFalse(hasattr(cc, name), name)

    def test_generation_is_always_every_episode(self):
        # 旧参数（episode / episode_only）不再有任何作用：永远是全部集
        for label, tpl in (("播客", cc.COUNSELING_TALK_SCENES), ("故事对话", cc.COUNSELING_SERIES_STORY_SPEAK),
                           ("故事表演", cc.COUNSELING_SERIES_STORY_ACT)):
            plain = cc.resolve_dynamic_scene_template(label, tpl, {"episodes": 3, "steps": 0})
            legacy = cc.resolve_dynamic_scene_template(label, tpl, {"episodes": 3, "steps": 0, "episode": 2,
                                                                    "episode_only": True})
            self.assertEqual(plain, legacy, label)
            self.assertIn("EXACTLY 3 EPISODES", plain, label)
            self.assertNotIn("ONLY EPISODE", plain, label)
        self.assertEqual(cc.normalize_scene_episodes([{"episode": "2"}, {}], 1), [])
        sc = [{"episode": "1"}, {"episode": "2"}, {"episode": "3"}]
        self.assertEqual(cc.normalize_scene_episodes(sc, 3), [])

    def test_pdf_instruction_for_fixed_steps(self):
        # t273: PDF 一律一页一个场景：故事对话的步数（1–6）对 PDF 不管用（t266 原来是「步数压过页数」）；
        # 只有 FlyLink 自己的固定步数故事（模板本身就是固定 N 场）仍由它的步数定。
        se = _read("gui", "dl", "scene_editor.py")
        body = se[se.index("def _pdf_instruction_for"):se.index("# t447u: 「内容主题 / FYI」")]
        self.assertIn("config_channel.fixed_story_steps(label, p) if config_channel.is_step_story_label(label) else 0", body)
        self.assertIn("one scene per page does not apply", body)  # 只剩固定步数故事 / 直接生成系列节目两种
        self.assertNotIn("only", body.split("def _pdf_instruction_for")[1].split("return")[0])
        params = se[se.index("def _scene_prompt_params"):se.index("def _pdf_instruction_for")]
        self.assertIn("if _steps_ignored_now():", params)
        self.assertIn("_steps = 0", params)


class DropdownWidth(unittest.TestCase):
    def test_half_of_the_old_width(self):
        self.assertEqual(cc.PROMPT_COMBO_WIDTH, 14)
        self.assertEqual(cc.PROMPT_COMBO_WIDTH * 2, 28)  # 原来是 28
        self.assertEqual(cc.prompt_combo_width(THREE), 14)  # counseling 的三个名字：正好一半
        self.assertEqual(cc.prompt_combo_width([]), 14)
        # 别的频道名字是长英文名：放宽到不截断（不超过原来的 28）
        self.assertGreater(cc.prompt_combo_width(["SUNO 2 Layers Poetry"]), 14)
        self.assertLessEqual(cc.prompt_combo_width(["x" * 80]), 28)
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("width=config_channel.prompt_combo_width([opt[0] for opt in nb_prompt_choices])", se)
        i = se.index("config_channel.prompt_combo_width(")
        self.assertNotIn("width=28", se[i - 400:i + 200])  # 叙事方式下拉不再写死 28（PDF 版式下拉的 28 是另一个控件）

    def test_counseling_uses_14(self):
        res = _real('import json, config, config_channel as cc\n'
                    'print(json.dumps(cc.prompt_combo_width([l for l, _t in config.CHANNEL_CONFIG["counseling"]["scenes_prompt_choices"]])))')
        self.assertEqual(res, 14)


class DefaultsAndSavedValues(unittest.TestCase):
    def test_new_entry_defaults_to_story_dialogue(self):
        self.assertEqual(cc.default_scene_prompt_label(THREE), "故事对话")
        self.assertEqual(cc.default_scene_prompt_label(["Lyrics to Story", "2 Layers Story"]), "Lyrics to Story")
        self.assertEqual(cc.default_scene_prompt_label([]), "")
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("config_channel.default_scene_prompt_label([opt[0] for opt in nb_prompt_choices])", se)
        self.assertIn("config_channel.default_scene_prompt_label(", _read("gui", "downloader.py"))

    def test_saved_steps_are_kept_and_old_story_dialogue_projects_stay_free(self):
        se = _read("gui", "dl", "scene_editor.py")
        # 旧的短故事项目：存过步数就用存的；没存步数就用它原来的默认（4 / N Step Story 的 N）
        self.assertIn("config_channel.legacy_story_steps(_saved_prompt_raw)", se)
        self.assertIn("_saved_steps or str(config_channel.legacy_story_steps(_saved_prompt_raw))", se)
        # 故事对话的步数单独存（scene_steps_dialogue，0 也存）；旧故事对话项目里残留的 scene_steps 不会变成固定场景数
        self.assertIn('"scene_steps_dialogue"', se)
        self.assertIn('_dlg_steps = _saved_steps_dialogue', se)
        # 新条目默认 0
        self.assertIn('"dialogue": _dlg_steps or str(config_channel.STORY_STEPS_DEFAULT)', se)
        # 图片分解的「第几步」不吃故事对话的 0，也不存
        self.assertIn('"image": "1"', se)
        self.assertIn('if kind not in ("dialogue", "fixed"):', se)

    def test_flylink_keeps_its_own_fixed_step_story(self):
        out = cc.resolve_dynamic_scene_template(cc.STEP_STORY_LABEL, cc.FLYLINK_STORY_STEP, {"steps": 2})
        self.assertIn("2 scene", out)
        self.assertNotIn("EPISODES", out)
        self.assertEqual(cc.resolve_dynamic_scene_template(cc.STEP_STORY_LABEL, cc.FLYLINK_STORY_STEP, {"steps": 0}),
                         cc.resolve_dynamic_scene_template(cc.STEP_STORY_LABEL, cc.FLYLINK_STORY_STEP, {"steps": cc.STEP_STORY_DEFAULT}))


class CliAndStoryProducer(unittest.TestCase):
    def test_n_step_name_still_works_as_story_dialogue_with_steps(self):
        res = _real(r'''
import json
from storyproducer.prompts import build_gemini_prompt
vd = {"analyzed_content": "一封旧信的故事。" * 20}
out = {}
for name, lab, kw in (("legacy4", "4 Step Story", {}), ("free", "故事对话", {}), ("n2", "故事对话", {"steps": 2}),
                      ("short", "Short Story", {}), ("ep_arg_gone", "故事对话", {"episodes": 3})):
    out[name] = build_gemini_prompt(vd, channel_id="counseling", lm_label=lab, **kw)
from utility.telegram_session import scene_count_from_prompt_text, scene_count_from_lm_label
out["counts"] = [scene_count_from_prompt_text(out["legacy4"]), scene_count_from_lm_label("4 Step Story"),
                 scene_count_from_prompt_text(out["free"])]
print(json.dumps(out, ensure_ascii=False))
''')
        self.assertIn("the whole (ONE) story has 4 scenes", res["legacy4"])
        self.assertIn("the whole (ONE) story has 2 scenes", res["n2"])
        self.assertIn("the whole (ONE) story has 1 scenes", res["short"])
        self.assertIn("*** EPISODES:", res["free"])
        self.assertIn("EXACTLY 3 EPISODES", res["ep_arg_gone"])
        self.assertEqual(res["counts"], [4, 4, 0])  # 步数 0（自由规划）没有固定场景数

    def test_scnlm_accepts_n_step_name_but_lists_story_dialogue(self):
        eng = _read("storyproducer", "engine.py")
        body = eng[eng.index("def cmd_scene_lm"):eng.index("def cmd_scene_visual_style")]
        self.assertIn("config_channel.legacy_step_label(want)", body)
        self.assertNotIn('"短故事"', body)
        self.assertNotIn('"Short Story"', body)
        ref = _read("cli", "CLI_REFERENCE.md")
        self.assertNotIn("| 1 | Short Story |", ref)
        self.assertIn("故事对话 · 步数 4", ref)


class InvariantsStillHold(unittest.TestCase):
    def test_no_subtitle_critical_line_once_first(self):
        for key in THREE_KEYS:
            p = cp.build_video_flow_prompt(
                frames="one", background="none", evolve="keep", visual_style="x",
                scene_content=[{"id": 1, "visual": "书房", "actor": "人物1：woman/youth/chinese/小美 | 人物2：man/youth/chinese/阿明",
                                "speaking": "<1s> 我不能再这样了。 <2> 你怎么了？"}],
                language="zh", narrative="story", text="erase", use_actor=True, story_style=key, host_portrait=False)
            fixed = cp.ensure_video_no_subtitle_first_line(p)
            self.assertTrue(fixed.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), key)
            self.assertEqual(fixed.count(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE), 1, key)
        # 旧的短故事 / step_story 存值进视频窗口也读作故事对话（自言自语不口型，人物位置以 actor 为准）
        legacy = cp.build_video_flow_prompt(
            frames="one", background="none", evolve="keep", visual_style="x",
            scene_content=[{"id": 1, "visual": "书房", "actor": "人物1：woman/youth/chinese/小美 | 人物2：man/youth/chinese/阿明",
                            "speaking": "<1s> 我不能再这样了。 <2> 你怎么了？"}],
            language="zh", narrative="story", text="erase", use_actor=True, story_style="短故事", host_portrait=False)
        self.assertIn(nm.speaking_rule("story_speak", nm.HOST_NONE), legacy)

    def test_self_talk_rule_in_every_step_variant(self):
        for n in range(0, 7):
            for h in CASES:
                self.assertIn(nm.SELF_TALK_RULE, _steps_prompt(n, h), (n, h))
        from utility.speaking_marks import parse_speaking_turns

        self.assertTrue(all("<" not in t.text for t in parse_speaking_turns("<1s> 我一直以为…… <2> 你怎么了？ <1> 没事。")))


if __name__ == "__main__":
    unittest.main()
