"""t448u（t447u 方案 A–E）：中文场景生成方式、人物设置、节目生成故事风格、内容主题 / FYI、tags 修复。"""
import importlib.util
import json
import os
import pathlib
import shutil
import string
import tempfile
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

import config_channel as cc  # noqa: E402
import config_prompt as cp  # noqa: E402
from utility import cast_preset as cpr  # noqa: E402
from utility import story_fyi as sf  # noqa: E402
from utility.tags_text import normalize_tags, parse_tags_list  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _topic_reassign():
    spec = importlib.util.spec_from_file_location("_tr448", ROOT / "gui" / "workflow" / "topic_reassign.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LabelTest(unittest.TestCase):
    def test_new_names(self):
        self.assertEqual(cc.STEP_STORY_LABEL, "短故事")
        self.assertEqual(
            [cc.SERIES_STYLE_LABELS[k] for k in ("podcast", "story_speak", "story_act")],
            ["播客", "故事对话", "故事表演"],
        )
        self.assertNotIn("counselor", cc.SERIES_STYLE_LABELS)  # t262: 主持人节目已并入故事表演

    def test_old_labels_migrate(self):
        for old, new in (
            ("Series . Podcast", "播客"), ("Series · Podcast", "播客"),
            ("Series · Counselor", "故事表演"), ("Series . Counselor", "故事表演"),
            ("主持人节目", "故事表演"), ("Counselor", "故事表演"),  # t262: 旧的主持人节目读作故事表演
            ("Series · Story Speak", "故事对话"), ("Series · Story Only", "故事对话"),
            ("Series . Story Only", "故事对话"), ("Series · Story Act", "故事表演"),
            ("Step Story", "短故事"), ("3 Step Story", "短故事"), ("Short Story", "短故事"),
            ("故事表演", "故事表演"), ("Mini Story", "Mini Story"), ("", ""),
        ):
            self.assertEqual(cc.canonical_prompt_label(old), new, old)

    def test_mode_by_value_not_prefix(self):
        self.assertTrue(cc.is_series_label("播客"))
        self.assertTrue(cc.is_series_label("故事表演"))
        self.assertTrue(cc.is_series_label("Series . Podcast"))
        self.assertFalse(cc.is_series_label("短故事"))
        self.assertFalse(cc.is_series_label("Series something else"))
        self.assertEqual(cc.series_style_key("主持人节目"), "story_act")  # t262
        self.assertEqual(cc.series_style_key("Series · Story Only"), "story_speak")
        self.assertTrue(cc.is_step_story_label("短故事"))
        self.assertTrue(cc.is_step_story_label("Step Story"))
        self.assertTrue(cc.is_step_story_label("4 Step Story"))

    def test_counseling_choices_use_chinese(self):
        src = (ROOT / "config.py").read_text(encoding="utf-8")
        self.assertNotIn('("Series . Podcast"', src)
        self.assertNotIn('("Series · Counselor"', src)
        self.assertIn('config_channel.SERIES_STYLE_LABELS["story_act"]', src)


class StoryStyleTest(unittest.TestCase):
    def test_four_chinese_styles(self):
        # t258: 视频窗口和预览窗口同一张表：短故事 / 播客 / 故事对话 / 故事表演（预览下拉的顺序）；t262: 主持人节目已并入故事表演
        self.assertEqual([k for k, _ in cp.STORY_STYLE_CHOICES],
                         ["step_story", "podcast", "story_speak", "story_act"])
        self.assertEqual(list(cp.STORY_STYLE_LABELS), ["短故事", "播客", "故事对话", "故事表演"])

    def test_normalize(self):
        for v, k in (("播客", "podcast"), ("主持人节目", "story_act"), ("故事对话", "story_speak"),
                     ("故事表演", "story_act"), ("tech", "story_act"), ("exec", "story_act"),
                     ("高管简报", "story_act"), ("技术方案汇报", "story_act"), ("短故事", "step_story"),
                     ("Series · Counselor", "story_act"), ("counselor", "story_act"),
                     ("Series . Podcast", "podcast"), ("Series · Story Only", "story_speak")):
            self.assertEqual(cp.normalize_story_style(v), k, v)
        self.assertEqual(cp.NARRATIVE_TO_STORY_STYLE["tech"], "story_act")
        self.assertEqual(cp.story_style_label("tech"), "故事表演")
        self.assertEqual(cp.story_style_narrative("故事表演"), "story")
        self.assertEqual(cp.story_style_narrative("主持人节目"), "story")


class TemplateTest(unittest.TestCase):
    def test_counselor_template_removed(self):
        # t262: 主持人节目整个删掉，故事表演的模板接手（人物只演不说，讲员讲解）
        self.assertFalse(hasattr(cc, "COUNSELING_SERIES_COUNSELOR_FRAME"))
        t = cc.COUNSELING_SERIES_STORY_ACT
        self.assertNotIn("They perform the spoken content", t)
        self.assertNotIn("The 人物 can answer the 讲员", t)
        self.assertIn("They never speak on camera: no dialogue, no lines, no lip-sync.", t)

    def test_story_modes_do_not_invent(self):
        for t in (cc.COUNSELING_SERIES_STORY_SPEAK, cc.COUNSELING_SERIES_STORY_ACT):
            self.assertNotIn("CAST is EMPTY: invent", t)
            self.assertIn("Do not invent other story people", t)

    def test_story_act_narrator_and_sfx(self):
        t = cc.COUNSELING_SERIES_STORY_ACT
        self.assertNotIn("silent presence", t)
        # t263: 没有「叙述场景」：不分 narrator / presenting / story 场景
        self.assertNotIn("narrator scene", t)
        self.assertNotIn("presenting scene", t)
        self.assertIn("音效：", t)
        self.assertIn("never music", t)
        self.assertNotIn("There is NO ``speaking`` field and no ``voiceover`` field.", t)
        list(string.Formatter().parse(t))

    def test_story_act_branches_on_host(self):
        # t263: 每一份模板只写一种讲员情况（人物栏 + 肖像是已知的）：有肖像 / 没有肖像 / 没有讲员
        a, b, c = (cc.STORY_ACT_TEMPLATES[h] for h in ("portrait", "voiceover", "none"))
        self.assertEqual(len({a, b, c}), 3)
        self.assertIn("who has a portrait (肖像)", a)
        self.assertIn("who has no portrait (肖像)", b)
        self.assertIn("the CAST has no 讲员. Nobody speaks at all", c)
        for t in (a, b):
            self.assertIn("explains EVERY scene", t)
            self.assertIn("Every scene has ``story_content`` (what the 人物 act) AND ``speaking``", t)
        self.assertNotIn("explains EVERY scene", c)
        self.assertIn("No scene has ``speaking``", c)
        self.assertNotIn("THREE CASES", a + b + c)
        # 人物本身仍然只演不说、只有音效
        for t in (a, b, c):
            self.assertIn("They never speak on camera: no dialogue, no lines, no lip-sync.", t)
            self.assertIn("never music", t)

    def test_podcast_needs_two(self):
        self.assertFalse(cpr.validate_cast_for_mode("podcast", "讲员：woman/mature/chinese")[0])
        self.assertFalse(cpr.validate_cast_for_mode("podcast", "人物1：woman/kids/chinese/a")[0])
        self.assertTrue(cpr.validate_cast_for_mode("podcast", "讲员：x | 人物1：woman/kids/chinese/a")[0])
        self.assertTrue(cpr.MODE_RULES["story_act"][0])  # 故事表演的人物设置默认带讲员

    def test_narrator_scene_speaks_in_story_act_video(self):
        scene = {"actor": "讲员：woman/mature/chinese", "speaking": "<1> 今天讲一个家。", "visual": "书房"}
        lines, field = cp._video_speech_rules("story_act", "story", [], [scene], "", True)
        self.assertIn(field, ("speaking", "dialogue", "narration"))
        # t262: 讲员不在出镜名单里 = 背景画外音：不出镜、不对口型；有话要说，不是「没人说话」
        self.assertIn("off-screen voice-over of the 讲员", " ".join(lines))
        self.assertNotIn("Speech: nobody speaks", " ".join(lines))
        act = {"actor": "人物1：woman/youth/chinese/小美", "story_content": "她放下碗。音效：碗碰桌面。", "visual": "厨房"}
        lines2, field2 = cp._video_speech_rules("story_act", "story", [], [act], "", True)
        self.assertEqual(field2, "story_content")


class CastPresetTest(unittest.TestCase):
    def test_mode_for_label(self):
        self.assertEqual(cpr.mode_for_label("播客"), "podcast")
        self.assertEqual(cpr.mode_for_label("Series . Podcast"), "podcast")
        self.assertEqual(cpr.mode_for_label("故事表演"), "story_act")
        self.assertEqual(cpr.mode_for_label("短故事"), "step_story")
        self.assertEqual(cpr.mode_for_label("Mini Story"), "")

    def test_validate(self):
        two = "讲员：woman/mature/chinese | 人物1：woman/mature/chinese/林芳（妻子） | 人物2：man/mature/chinese/陈强（丈夫）"
        one = "讲员：woman/mature/chinese | 人物1：woman/mature/chinese/林芳"
        self.assertTrue(cpr.validate_cast_for_mode("story_speak", two)[0])
        self.assertFalse(cpr.validate_cast_for_mode("story_act", one)[0])
        self.assertFalse(cpr.validate_cast_for_mode("step_story", "讲员：x | 人物1：woman/kids/chinese/a")[0])
        self.assertTrue(cpr.validate_cast_for_mode("podcast", one)[0])
        self.assertFalse(cpr.validate_cast_for_mode("podcast", "讲员：woman/mature/chinese")[0])
        # t263: 播客 = 讲员（主持）+ 嘉宾；只有人物没有讲员不行，并且告诉用户去按「人物设置」
        ok, why = cpr.validate_cast_for_mode("podcast", "人物1：woman/kids/chinese/a | 人物2：man/kids/chinese/b")
        self.assertFalse(ok)
        self.assertIn("人物设置", why)
        # t262: 主持人节目已并入故事表演：没有单独的 counselor 人数规则
        self.assertNotIn("counselor", cpr.MODE_RULES)
        self.assertNotIn("counselor", cpr.MODE_NAMES)
        self.assertFalse(cpr.validate_cast_for_mode("story_speak", "人物1：不出现 | 人物2：woman/kids/chinese/a")[0])

    def test_parse_reply(self):
        reply = ("好的：\n人物1：woman/mature/chinese/林芳（妻子）\n讲员：man/mature/chinese\n"
                 "2. 人物2: Man / Senior / Chinese / 林伯(父亲)\n人物3：robot/x/y/z\n人物4：woman/kids/chinese/小雨（女儿）")
        got = cpr.parse_cast_reply(reply, "story_speak")
        self.assertEqual(got, ["woman/mature/chinese/林芳（妻子）", "man/senior/chinese/林伯（父亲）",
                               "woman/kids/chinese/小雨（女儿）"])
        self.assertEqual(len(cpr.parse_cast_reply(reply, "podcast")), 1)
        self.assertEqual(len(cpr.parse_cast_reply(reply, "step_story")), 2)

    def test_preset_and_reroll_history(self):
        seen = []

        def fake(system, user):
            seen.append((system, user))
            return "人物1：woman/mature/chinese/林芳（妻子）\n人物2：man/mature/chinese/陈强（丈夫）"

        vd = {}
        text, people = cpr.preset_cast("story_act", "一对夫妻的冷战", narrator="woman/mature/chinese",
                                       history=cpr.cast_history(vd), generate=fake)
        self.assertEqual(text, "讲员：woman/mature/chinese | 人物1：woman/mature/chinese/林芳（妻子） | "
                               "人物2：man/mature/chinese/陈强（丈夫）")
        self.assertIn("故事表演", seen[0][0])
        self.assertNotIn("already used", seen[0][1])
        cpr.remember_cast(vd, people)
        cpr.preset_cast("story_act", "一对夫妻的冷战", narrator="x", history=cpr.cast_history(vd), generate=fake)
        self.assertIn("DIFFERENT set of relationships", seen[1][1])
        self.assertIn("林芳（妻子）", seen[1][1])
        cpr.remember_cast(vd, ["a", "b"])
        cpr.remember_cast(vd, people)
        self.assertEqual(vd["cast_history"][0], " | ".join(people))
        self.assertEqual(len(vd["cast_history"]), 2)

    def test_step_story_has_no_host(self):
        text, _ = cpr.preset_cast("step_story", "x", narrator="woman/mature/chinese",
                                  generate=lambda s, u: "人物1：woman/kids/chinese/甲（姐姐）\n人物2：man/kids/chinese/乙（弟弟）")
        self.assertNotIn("讲员", text)

    def test_bad_reply_raises(self):
        with self.assertRaises(ValueError):
            cpr.preset_cast("story_speak", "x", generate=lambda s, u: "人物1：woman/kids/chinese/甲")
        with self.assertRaises(ValueError):  # t262: 没有 counselor 这个方式了
            cpr.preset_cast("counselor", "x", narrator="n", generate=lambda s, u: "没有人物")

    def test_counts_presets(self):
        self.assertEqual(cpr.MODE_RULES["podcast"][:3], (True, 1, 1))
        self.assertEqual(cpr.MODE_RULES["story_speak"][:3], (True, 2, 3))
        self.assertEqual(cpr.MODE_RULES["story_act"][:3], (True, 2, 3))
        self.assertEqual(cpr.MODE_RULES["step_story"][:3], (False, 2, 2))


class ProgramModeTest(unittest.TestCase):
    def test_follow_main_window(self):
        f = cpr.program_mode_narrative
        # t262: 节目生成四种方式（短故事是自己的一种）；谁说话由共用规则给，所以叙事形式都是 story；主持人节目读作故事表演
        self.assertEqual(f("播客"), ("播客", "podcast", "story"))
        self.assertEqual(f("主持人节目"), ("故事表演", "story_act", "story"))
        self.assertEqual(f("Series · Counselor"), ("故事表演", "story_act", "story"))
        self.assertEqual(f("故事对话"), ("故事对话", "story_speak", "story"))
        self.assertEqual(f("故事表演"), ("故事表演", "story_act", "story"))
        self.assertEqual(f("短故事"), ("短故事", "step_story", "story"))
        self.assertEqual(f("Series . Podcast"), ("播客", "podcast", "story"))
        self.assertEqual(f("Step Story"), ("短故事", "step_story", "story"))
        self.assertEqual(f("Mini Story", "story_act"), ("故事表演", "story_act", "story"))
        self.assertEqual(f("Mini Story", "tech"), ("故事表演", "story_act", "story"))
        self.assertEqual(f("", None), ("播客", "podcast", "story"))


class _Var:
    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class StoryFyiTest(unittest.TestCase):
    def test_migrate_store_effective(self):
        vd = {"instruction": "旧的导向说明"}
        hist, inc = sf.load_story_fyi(vd)
        self.assertEqual((hist, inc), (["旧的导向说明"], True))
        pp = {}
        vd["project_profile"] = pp
        self.assertTrue(sf.store_story_fyi(vd, "新主题", hist, True))
        self.assertEqual(vd["story_fyi"], "新主题")
        self.assertEqual(vd["story_fyi_history"], ["新主题", "旧的导向说明"])
        self.assertEqual(pp["story_fyi"], "新主题")
        self.assertFalse(sf.store_story_fyi(vd, "新主题", vd["story_fyi_history"], True))
        self.assertEqual(sf.effective_fyi(vd), "新主题")
        sf.store_story_fyi(vd, "新主题", vd["story_fyi_history"], False)
        self.assertEqual(sf.effective_fyi(vd), "")

    def test_no_tech_prefill(self):
        # t448u: 旧的 tech / exec 只默默归到故事表演（t262 前是主持人节目），不往 FYI 里预填
        self.assertFalse(hasattr(sf, "tech_prefill"))
        src = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertNotIn("tech_prefill", src)
        self.assertNotIn("fyi_set(_pre)", src)

    def test_adapter(self):
        box = {"t": "主题"}
        inc = _Var(True)
        a = sf.FyiTextAdapter(lambda: box["t"], lambda v: box.__setitem__("t", v), inc)
        self.assertEqual(a.get("1.0", "end").strip(), "主题")
        inc.set(False)
        self.assertEqual(a.get("1.0", "end"), "")
        a.delete("1.0", "end")
        a.insert("1.0", "CLI 设的")
        self.assertEqual(box["t"], "CLI 设的")
        self.assertTrue(inc.get())

    def test_story_fyi_goes_to_project(self):
        src = (ROOT / "project_manager.py").read_text(encoding="utf-8")
        start = src.index("LIST_ITEM_TOP_PROJECT_KEYS = (")
        self.assertIn('"story_fyi"', src[start:src.index(")", start)])

    def test_scene_editor_uses_fyi(self):
        src = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertNotIn('text="导向说明（{instruction}，可选）："', src)
        self.assertIn("FyiTextAdapter", src)
        self.assertIn('text="人物设置"', src)
        self.assertIn("validate_cast_for_mode", src)
        self.assertIn("get_fyi=", src)
        self.assertIn("program_mode=_series_label", src)
        self.assertNotIn("on_story_style", src)

    def test_program_dialog_has_no_style_radios(self):
        src = (ROOT / "gui" / "slide_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertNotIn("pack_story_style_choices", src)
        self.assertNotIn("for value, label in config_prompt.STORY_STYLE_CHOICES", src)
        self.assertIn("节目方式（在主窗口改）", src)


class TagsTest(unittest.TestCase):
    def _corrupt(self, tags, rounds):
        def old_parse(s):
            if "|" in s:
                return [x.strip() for x in s.split("|") if x.strip()]
            return [x.strip() for x in s.split(",") if x.strip()]

        s = str(tags)
        for _ in range(rounds):
            s = str(old_parse(s))
        return s

    def test_normalize_layers(self):
        for n in range(0, 5):
            bad = self._corrupt(["成瘾", "逃避", "亲子"], n)
            self.assertEqual(normalize_tags(bad), ["成瘾", "逃避", "亲子"], n)
            self.assertEqual(parse_tags_list(bad), ["成瘾", "逃避", "亲子"], n)
        self.assertEqual(normalize_tags(["['a'", "'b']", "b"]), ["a", "b"])
        # 坏掉的一项里用全角逗号连着几枚；干净列表里的全角逗号不拆
        self.assertEqual(normalize_tags(["['存在之哀，神圣连接，真·光环']"]), ["存在之哀", "神圣连接", "真·光环"])
        self.assertEqual(normalize_tags(["正常，标签"]), ["正常，标签"])

    def test_normalize_plain(self):
        self.assertEqual(normalize_tags("a, b"), ["a", "b"])
        self.assertEqual(normalize_tags("A=calm, warm | B=x"), ["A=calm, warm", "B=x"])
        self.assertEqual(normalize_tags("A=calm, warm, B=x"), ["A=calm, warm", "B=x"])
        self.assertEqual(normalize_tags(None), [])
        self.assertEqual(normalize_tags(["x", " x ", ""]), ["x"])
        self.assertEqual(parse_tags_list("a, b"), ["a", "b"])

    def test_topic_reassign_stores_lists(self):
        tr = _topic_reassign()
        self.assertEqual(tr._tags_like("['a', 'b']", ["a", "b"]), ["a", "b"])
        self.assertEqual(tr.tags_as_list(self._corrupt(["甲", "乙"], 3)), ["甲", "乙"])
        self.assertEqual(tr.tags_as_list("甲、乙;丙"), ["甲", "乙", "丙"])

    def test_repair_script(self):
        from utility import repair_tags

        tmp = tempfile.mkdtemp()
        try:
            bad = os.path.join(tmp, "program", "c", "list", "a.json")
            os.makedirs(os.path.dirname(bad))
            rows = [{"tags": self._corrupt(["甲", "乙"], 2)}, {"tags": ["丙"]},
                    {"project_profile": {"tags": "丁, 戊"}}, {"tags": ["['己'", "'庚']"]}]
            with open(bad, "w", encoding="utf-8", newline="\r\n") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            clean = os.path.join(tmp, "b.json")
            with open(clean, "w", encoding="utf-8") as f:
                json.dump({"tags": ["x"]}, f)
            with open(os.path.join(tmp, "video_choice_queue.json"), "w", encoding="utf-8") as f:
                json.dump([{"tags": "显示 | 文字"}], f, ensure_ascii=False)
            os.makedirs(os.path.join(tmp, "_backup"))
            with open(os.path.join(tmp, "_backup", "c.json"), "w", encoding="utf-8") as f:
                json.dump({"tags": "skip, me"}, f)
            before = _read(bad)
            out = []
            st = repair_tags.repair([tmp], dry_run=True, out=out.append)
            self.assertEqual((st["files_changed"], st["string"], st["broken"]), (1, 2, 1))
            self.assertEqual(_read(bad), before)
            self.assertFalse([p for p in os.listdir(os.path.dirname(bad)) if ".bak_tags_" in p])
            st = repair_tags.repair([tmp], dry_run=False, out=out.append)
            self.assertEqual(st["files_changed"], 1)
            baks = [p for p in os.listdir(os.path.dirname(bad)) if ".bak_tags_" in p]
            self.assertEqual(len(baks), 1)
            self.assertEqual(_read(os.path.join(os.path.dirname(bad), baks[0])), before)
            raw = _read(bad)
            self.assertIn(b"\r\n", raw)
            data = json.loads(raw.decode("utf-8"))
            self.assertEqual([data[0]["tags"], data[1]["tags"], data[2]["project_profile"]["tags"], data[3]["tags"]],
                             [["甲", "乙"], ["丙"], ["丁", "戊"], ["己", "庚"]])
            st = repair_tags.repair([tmp], dry_run=True, out=out.append)
            self.assertEqual(st["files_changed"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
