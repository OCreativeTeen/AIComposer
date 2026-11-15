"""t444u: 翻候选肖像先用频道自己的 program/<频道>/avatar/<风格>/，没有再退回通用 avatar/<风格>/。"""
import os
import pathlib
import shutil
import tempfile
import unittest

from utility import portrait_candidates as pc

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _png(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (4, 4), (0, 255, 0)).save(path)
    return os.path.abspath(path)


class ChannelAvatarFirstTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "avatar")
        self.ch = os.path.join(self.tmp, "program", "counseling", "avatar")
        self.g_w = _png(os.path.join(self.lib, "Watercolor", "woman_mature_chinese.png"))
        self.g_p = _png(os.path.join(self.lib, "Pixar-Art-Cartoon", "man_mature_chinese.png"))
        self.c_m = _png(os.path.join(self.ch, "Watercolor", "man_mature2_chinese.jpg"))
        self.c_w = _png(os.path.join(self.ch, "Watercolor", "woman_mature2_chinese.jpg"))
        _png(os.path.join(self.ch, "Watercolor", "_blank.png"))
        os.makedirs(os.path.join(self.ch, "Oil-Painting"))  # 频道里这个风格是空的

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_channel_dir_helper(self):
        self.assertEqual(pc.channel_avatar_dir(""), "")
        self.assertEqual(pc.channel_avatar_dir(os.path.join(self.tmp, "program", "counseling")), self.ch)

    def test_channel_style_first_only(self):
        paths, label = pc.library_candidates(self.lib, "watercolor", "woman/mature2/chinese", channel_root=self.ch)
        self.assertEqual(paths, [self.c_w, self.c_m])  # 只翻频道的，样子对得上的排前面，_blank 跳过
        self.assertEqual(label, "counseling/Watercolor")

    def test_fallback_when_channel_style_missing_or_empty(self):
        paths, label = pc.library_candidates(self.lib, "Pixar-Art-Cartoon", "", channel_root=self.ch)
        self.assertEqual((paths, label), ([self.g_p], "Pixar-Art-Cartoon"))
        os.makedirs(os.path.join(self.lib, "Oil-Painting"))
        oil = _png(os.path.join(self.lib, "Oil-Painting", "man_youth_chinese.png"))
        paths, label = pc.library_candidates(self.lib, "Oil-Painting", "", channel_root=self.ch)
        self.assertEqual((paths, label), ([oil], "Oil-Painting"))

    def test_no_channel_same_as_before(self):
        a = pc.library_candidates(self.lib, "Watercolor", "woman/mature/chinese")
        b = pc.library_candidates(self.lib, "Watercolor", "woman/mature/chinese", channel_root="")
        c = pc.library_candidates(self.lib, "Watercolor", "woman/mature/chinese", channel_root=os.path.join(self.tmp, "nope"))
        self.assertEqual(a, ([self.g_w], "Watercolor"))
        self.assertEqual(a, b)
        self.assertEqual(a, c)


class WiringTest(unittest.TestCase):
    def test_panel_and_editor_pass_channel(self):
        panel = (ROOT / "gui" / "dl" / "story_actor_panel.py").read_text(encoding="utf-8")
        self.assertIn("channel_path=None", panel)
        self.assertIn("channel_root=self.panel.channel_avatar_dir()", panel)
        editor = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn("channel_path=_story_channel_path,", editor)
        self.assertIn("config.get_channel_path(self._channel_config_key())", editor)


if __name__ == "__main__":
    unittest.main()
