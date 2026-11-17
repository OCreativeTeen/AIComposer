"""t436u 阶段 1：分集由手工选的「共 N 集」决定。共 1 集 = 不分集；共 N 集 = 一次生成全部 N 集。
t266: 「只重新生成第 k 集」（复选框、第 k 集下拉、episode_only、merge_episode_scenes）已删除：每次生成都是全部集。"""
import pathlib
import string
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

import config_channel as cc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = "\n--------------------------------------------------\nINPUT\n"


def _formattable(text):
    list(string.Formatter().parse(text))  # 单个花括号会报错


class BlockTest(unittest.TestCase):
    def test_one_episode_default(self):
        t = cc.COUNSELING_TALK_SCENES
        self.assertIn("*** EPISODES: ONE EPISODE", t)
        self.assertNotIn("5 to 15", t)
        self.assertEqual(t.count(cc.EPISODES_BLOCK_HEAD), 1)

    def test_exactly_n(self):
        r = cc.with_episode_plan(cc.COUNSELING_TALK_SCENES, 3)
        self.assertIn("*** EPISODES: EXACTLY 3 EPISODES", r)
        self.assertNotIn("ONE EPISODE", r)
        self.assertEqual(r.count(cc.EPISODES_BLOCK_HEAD), 1)
        self.assertEqual(r.count(INPUT), 1)
        self.assertLess(r.index("EXACTLY 3"), r.index(INPUT))
        self.assertIn('"1" to "3"', r)
        _formattable(r)

    def test_only_k_is_gone(self):
        # t266: 没有「只写第 k 集」了：with_episode_plan 不再有 episode / only 参数
        import inspect
        for fn in (cc.with_episode_plan, cc.episode_plan_block, cc.series_episode_template, cc.normalize_scene_episodes):
            params = inspect.signature(fn).parameters
            self.assertNotIn("only", params, fn.__name__)
            self.assertNotIn("episode", params, fn.__name__)
        r = cc.with_episode_plan(cc.COUNSELING_TALK_SCENES, 4)
        self.assertNotIn("ONLY EPISODE", r)
        self.assertNotIn("THIS RUN: EPISODE", r)

    def test_template_without_block(self):
        plain = "Write scenes.\n" + INPUT + "{content}\n"
        self.assertEqual(cc.with_episode_plan(plain, 1), plain)
        r = cc.with_episode_plan(plain, 2)
        self.assertLess(r.index("EXACTLY 2"), r.index(INPUT))
        r = cc.with_episode_plan("no input marker", 2)
        self.assertIn("EXACTLY 2 EPISODES", r)


class ResolveTest(unittest.TestCase):
    def _series_label(self):
        return "故事表演"  # t262: 主持人节目已并入故事表演（旧的 Series · Counselor 也读作它）

    def test_series_label(self):
        lbl = self._series_label()
        self.assertTrue(cc.is_series_label(lbl))
        t = cc.COUNSELING_SERIES_STORY_ACT
        one = cc.resolve_dynamic_scene_template(lbl, t, {"episodes": 1})
        self.assertIn("ONE EPISODE", one)
        three = cc.resolve_dynamic_scene_template(lbl, t, {"episodes": 3})
        self.assertIn("EXACTLY 3 EPISODES", three)
        self.assertNotIn("THIS RUN: EPISODE", three)
        # t266: 旧的 episode / episode_only 参数不再有任何作用：永远是全部集
        legacy = cc.resolve_dynamic_scene_template(lbl, t, {"episodes": 3, "episode": 2, "episode_only": True})
        self.assertEqual(legacy, three)
        self.assertNotIn("ONLY EPISODE", legacy)
        for x in (one, three, legacy):
            _formattable(x)

    def test_other_label_gets_plan(self):
        t = cc.COMIC_STRIP_SCENES
        r = cc.resolve_dynamic_scene_template("Comic Strip", t, {"episodes": 2})
        self.assertIn("EXACTLY 2 EPISODES", r)
        self.assertEqual(cc.resolve_dynamic_scene_template(cc.STEP_IMAGE_LABEL, "x", {"episodes": 3}), "x")

    def test_series_direct(self):
        lbl = cc.SERIES_DIRECT_LABEL
        all3 = cc.resolve_dynamic_scene_template(lbl, "", {"episodes": 3, "episode": 2})
        self.assertIn("Write ALL 3 episodes", all3)
        legacy = cc.resolve_dynamic_scene_template(lbl, "", {"episodes": 3, "episode": 2, "episode_only": True})
        self.assertEqual(legacy, all3)  # t266: 没有只写第 k 集了
        self.assertNotIn("Write ONLY episode", legacy)
        one = cc.resolve_dynamic_scene_template(lbl, "", {"episodes": 1})
        self.assertIn("single-episode program", one)
        for x in (all3, legacy, one):
            _formattable(x)

    def test_episode_only_removed(self):
        self.assertFalse(hasattr(cc, "episode_only"))
        self.assertFalse(hasattr(cc, "merge_episode_scenes"))


class NormalizeTest(unittest.TestCase):
    def test_one_episode_forces_1(self):
        sc = [{"episode": "2"}, {"episode": "3"}, {}]
        self.assertEqual(cc.normalize_scene_episodes(sc, 1), [])
        self.assertEqual([s["episode"] for s in sc], ["1", "1", "1"])

    def test_n_checked_not_changed(self):
        sc = [{"episode": "1"}, {"episode": "第2集"}, {"episode": "2"}]
        notes = cc.normalize_scene_episodes(sc, 3)
        self.assertEqual([s["episode"] for s in sc], ["1", "2", "2"])
        self.assertTrue(any("共 3 集" in n for n in notes))
        sc = [{"episode": "1"}, {"episode": "2"}, {"episode": "1"}]
        self.assertTrue(any("交叉" in n for n in cc.normalize_scene_episodes(sc, 2)))
        self.assertEqual(cc.normalize_scene_episodes([{"episode": "1"}, {"episode": "2"}], 2), [])

class WiringTest(unittest.TestCase):
    def test_downloader_and_editor(self):
        dl = (ROOT / "gui" / "downloader.py").read_text(encoding="utf-8")
        self.assertLess(dl.index("normalize_scene_episodes(scenes"), dl.index("align_story_speakers(scenes)"))
        # t266: 只重新生成第 k 集的整套逻辑已删除：下载器不再合并 / 替换某一集，编辑器没有复选框和第 k 集下拉
        self.assertNotIn("merge_episode_scenes", dl)
        self.assertNotIn("episode_only", dl)
        ed = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        for gone in ("series_only_var", "series_ep_var", "series_ep_combo", "series_only_chk", "episode_only", "只重新生成第"):
            self.assertNotIn(gone, ed, gone)
        self.assertIn('text="共"', ed)  # 「共 N 集」还在


if __name__ == "__main__":
    unittest.main()
