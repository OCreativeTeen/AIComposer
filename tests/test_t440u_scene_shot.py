"""t440u: 场景 JSON 里每一场都要有 shot：没拆过 = "1-1"，拆开 = 1-N … N-N；已有的不改。"""
import pathlib
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

from utility import scene_prep as sp  # noqa: E402
from utility.scene_shot import ensure_scene_shots, missing_shots  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
LONG = "<1> " + "我们今天来聊一聊这个问题。" * 6 + "<2> " + "好的，没问题，我听着呢。" * 5  # 117 字


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class EnsureTest(unittest.TestCase):
    def test_fill_missing_only(self):
        scenes = [{"caption": "A"}, {"shot": "2-3"}, {"shot": ""}, {"shot": "特写"}, "x"]
        self.assertEqual(missing_shots(scenes), 2)
        self.assertEqual(ensure_scene_shots(scenes), 2)
        self.assertEqual([s["shot"] for s in scenes[:4]], ["1-1", "2-3", "1-1", "特写"])
        self.assertEqual(ensure_scene_shots(scenes), 0)
        self.assertEqual(ensure_scene_shots(None), 0)


class FakeStrata:
    def remix_full(self, visual, image, **_k):
        return {"visual": "新：" + visual, "actor": ""}

    def remix_text(self, visual, **_k):
        return "新的视觉：" + visual

    def remix_group(self, visual, parts, **_k):
        return [f"第{i}段：{visual}" for i in range(1, len(parts) + 1)]


class PrepShotTest(unittest.TestCase):
    def test_short_split_and_kept(self):
        scenes = [
            {"caption": "A", "visual": "客厅里两个人坐着说话。", "speaking": "<1> 你好。"},
            {"caption": "B", "visual": "他走到窗边看着外面。", "speaking": LONG},
            {"caption": "C", "visual": "门外有人敲门进来了。", "speaking": "<1> 谁？", "shot": "特写"},
        ]
        out, _ = sp.prepare_scenes(scenes, strata=FakeStrata(), log=lambda *_: None)
        self.assertEqual([s["shot"] for s in out], ["1-1", "1-2", "2-2", "特写"])

    def test_split_three(self):
        long3 = "<1> " + "我们今天来聊一聊这个问题。" * 20
        final, groups = sp.split_scenes([{"caption": "A", "speaking": long3}], "")
        sp._set_shots(final, groups)
        n = len(final)
        self.assertGreaterEqual(n, 3)
        self.assertEqual([s["shot"] for s in final], [f"{i}-{n}" for i in range(1, n + 1)])


class WiringTest(unittest.TestCase):
    def test_generation_after_merge(self):
        src = _src("gui/downloader.py")
        gen = src[src.index("config_channel.merge_episode_scenes("):src.index("            def apply():")]
        self.assertIn("ensure_scene_shots(scenes)", gen)
        self.assertLess(gen.index("align_story_speakers(scenes)"), gen.index("ensure_scene_shots(scenes)"))

    def test_save_and_load_paths(self):
        dl = _src("gui/downloader.py")
        body = dl[dl.index("def apply_scene_content_from_editor_text"):dl.index("def _normalize_scene_dict_entry")]
        self.assertIn("ensure_scene_shots(parsed)", body)
        self.assertIn("ensure_scene_shots(scene_content)", dl)  # 读频道列表
        mw = _src("magic_workflow.py")
        load = mw[mw.index("    def load_scenes(self):"):mw.index("        self.scenes = []\n", mw.index("    def load_scenes(self):"))]
        self.assertIn("ensure_scene_shots(self.scenes)", load)
        save = mw[mw.index("    def save_scenes_to_json(self):"):]
        self.assertIn("ensure_scene_shots(self.scenes)", save[:1500])
        self.assertIn("ensure_scene_shots(parsed)", _src("cli/commands.py"))
        self.assertIn("ensure_scene_shots(_sc_list)", _src("gui/dl/channel_videos_dialog.py"))
        self.assertIn("missing_shots(_parse_scene_json_list(raw))", _src("gui/dl/scene_editor.py"))


if __name__ == "__main__":
    unittest.main()
