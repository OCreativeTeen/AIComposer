"""t443u: 人物窗：图在最上面；左右键翻候选肖像（项目 avatar / 图库 avatar/<风格>/），不换人；两个窗共用部件。"""
import os
import pathlib
import tempfile
import unittest

from utility import portrait_candidates as pc

ROOT = pathlib.Path(__file__).resolve().parents[1]

try:
    import tkinter  # noqa: F401

    HAVE_TK = True
except ImportError:  # 盒子上没有 tkinter
    HAVE_TK = False


def _png(path, color=(255, 0, 0)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (4, 4), color).save(path)
    return os.path.abspath(path)


def _jpg(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (4, 4), (0, 0, 255)).save(path, "JPEG")
    return os.path.abspath(path)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for d in ("Pixar-Art-Cartoon", "Realistic", "back", "voice", "story", "_backup_x", "original"):
            os.makedirs(os.path.join(self.root, d))
        self.p_w = _png(os.path.join(self.root, "Pixar-Art-Cartoon", "woman_mature_chinese.png"))
        self.p_m = _png(os.path.join(self.root, "Pixar-Art-Cartoon", "man_mature_chinese.png"))
        self.p_wk = _png(os.path.join(self.root, "Pixar-Art-Cartoon", "woman_kids_chinese.png"))
        _png(os.path.join(self.root, "Pixar-Art-Cartoon", "woman_mature_chinese.bak1.png"))
        _png(os.path.join(self.root, "Pixar-Art-Cartoon", "_blank.png"))
        self.r_m = _png(os.path.join(self.root, "Realistic", "man_youth_english.png"))
        _png(os.path.join(self.root, "back", "b.png"))

    def test_style_folders(self):
        self.assertEqual(pc.style_folders(self.root), ["Pixar-Art-Cartoon", "Realistic"])
        self.assertEqual(pc.match_style_folder(self.root, "pixar-art-cartoon"), "Pixar-Art-Cartoon")
        self.assertEqual(pc.match_style_folder(self.root, "Watercolor"), "")

    def test_matched_style_ranked(self):
        paths, label = pc.library_candidates(self.root, "Pixar-Art-Cartoon", "woman/mature/chinese/封氏（红衣）")
        self.assertEqual(label, "Pixar-Art-Cartoon")
        self.assertEqual(paths, [self.p_w, self.p_wk, self.p_m])  # 不含 .bak、_blank

    def test_unknown_style_all(self):
        paths, label = pc.library_candidates(self.root, "Watercolor", "man/youth/english")
        self.assertIn("全部风格", label)
        self.assertEqual(paths[0], self.r_m)
        self.assertEqual(set(paths), {self.p_w, self.p_m, self.p_wk, self.r_m})

    def test_empty(self):
        self.assertEqual(pc.library_candidates(os.path.join(self.root, "none"), "X", ""), ([], "全部风格（没有「X」文件夹）"))


class ProjectTest(unittest.TestCase):
    def test_project_candidates_exclude_own(self):
        d = tempfile.mkdtemp()
        own = _png(os.path.join(d, "woman_mature_chinese_A.png"))
        b = _png(os.path.join(d, "man_mature_chinese_B.png"))
        c = _png(os.path.join(d, "Pixar-Art-Cartoon", "woman_youth_chinese_C.png"))
        _png(os.path.join(d, "x.bak2.png"))
        got = pc.project_candidates(d, "Pixar-Art-Cartoon", exclude=[own], body="woman/mature/chinese/A")
        self.assertEqual(got, [c, b])
        self.assertEqual(pc.project_candidates(d, "", exclude=[own, b]), [])


class ApplyTest(unittest.TestCase):
    def test_copy_with_backup_src_untouched(self):
        d = tempfile.mkdtemp()
        src = _png(os.path.join(d, "lib", "woman_mature_chinese.png"), (0, 255, 0))
        dest = os.path.join(d, "avatar", "woman_mature_chinese_封氏.png")
        _png(dest)
        _jpg(os.path.join(d, "avatar", "woman_mature_chinese_封氏.jpg"))
        out = pc.apply_portrait_choice(src, dest)
        self.assertEqual(out, dest)
        self.assertTrue(os.path.isfile(src))
        names = sorted(os.listdir(os.path.join(d, "avatar")))
        self.assertEqual(names, ["woman_mature_chinese_封氏.bak1.jpg", "woman_mature_chinese_封氏.bak1.png",
                                 "woman_mature_chinese_封氏.png"])
        from PIL import Image

        with Image.open(dest) as im:
            self.assertEqual(im.getpixel((0, 0))[:3], (0, 255, 0))

    def test_jpg_converted_and_own_noop(self):
        d = tempfile.mkdtemp()
        src = _jpg(os.path.join(d, "lib", "a.jpg"))
        dest = os.path.join(d, "avatar", "p.png")
        self.assertEqual(pc.apply_portrait_choice(src, dest), dest)
        from PIL import Image

        with Image.open(dest) as im:
            self.assertEqual(im.format, "PNG")
        own = _jpg(os.path.join(d, "avatar", "q.jpg"))
        self.assertEqual(pc.apply_portrait_choice(own, os.path.join(d, "avatar", "q.png")), own)
        self.assertTrue(os.path.isfile(own))
        with self.assertRaises(FileNotFoundError):
            pc.apply_portrait_choice(os.path.join(d, "none.png"), dest)


@unittest.skipUnless(HAVE_TK, "需要 tkinter")
class BrowserTest(unittest.TestCase):
    def test_step_cycle(self):
        from gui.actor_portrait_widgets import PortraitBrowser

        class Lbl:
            def configure(self, **kw):
                self.kw = kw

        class Var:
            def set(self, v):
                self.v = v

        b = PortraitBrowser(Lbl(), Var())
        b.reset("own.png", [], "x")
        self.assertFalse(b.step(1))  # 没有候选：什么都不做
        self.assertEqual(b.picked(), "")
        b.reset("own.png", ["a.png", "b.png"], "Pixar")
        self.assertTrue(b.step(1))
        self.assertEqual(b.picked(), "a.png")
        b.step(1)
        self.assertEqual(b.picked(), "b.png")
        b.step(1)
        self.assertEqual(b.picked(), "")  # 回到现在的肖像
        b.step(-1)
        self.assertEqual(b.picked(), "b.png")


class WiringTest(unittest.TestCase):
    def test_both_dialogs_share_widgets(self):
        wf = (ROOT / "gui/workflow/wf_actors.py").read_text(encoding="utf-8")
        dlg = wf[wf.index("    def _open_portrait_dialog("):wf.index("    def _scene_actor_rows(")]
        self.assertIn("PersonEditBlock(dlg)", dlg)
        self.assertIn("PortraitBrowser(image_label", dlg)
        self.assertLess(dlg.index("image_label.pack("), dlg.index("ttk.Label(dlg, textvariable=name_var"))
        shift = dlg[dlg.index("def shift("):dlg.index("def apply_picked(")]
        self.assertLess(shift.index("browser.step(step)"), shift.index("show_at(nxt)"))
        self.assertIn("focus_in_text_field(dlg) else shift(-1)", dlg)
        self.assertIn("apply_picked(name)", dlg[dlg.index("def confirm("):])
        self.assertIn("project_candidates(", wf)
        story = (ROOT / "gui/dl/story_actor_panel.py").read_text(encoding="utf-8")
        ed = story[story.index("class ActorEditDialog"):]
        self.assertIn("PersonEditBlock(frm)", ed)
        self.assertIn("PortraitBrowser(self.img_lbl", ed)
        self.assertIn("library_candidates(config.AVATAR_PATH", ed)
        self.assertLess(ed.index("self.img_lbl.pack("), ed.index("role_row.pack("))
        self.assertIn("self._use_picked()", ed[ed.index("def _ok("):])


if __name__ == "__main__":
    unittest.main()
