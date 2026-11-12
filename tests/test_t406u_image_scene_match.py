# -*- coding: utf-8 -*-
"""t406u: 图片对场景（PDF 抽图 / 视频幻灯片 → Strata 看图 → 顺序对到场景，记在 ref_images）。"""
import json
import os
import pathlib
import tempfile
import unittest

import numpy as np

from utility import material_image_matcher as mim

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _scenes(n):
    return [{"episode": "1", "caption": f"场{i}", "visual": f"画面{i}", "speaking": f"台词{i}"} for i in range(n)]


def _imgs(*topics, source="video"):
    return [{"path": f"C:/w/s{k:03d}.png", "source": source, "index": k, "desc": t, "text": ""}
            for k, t in enumerate(topics, 1)]


def _topic_judge(calls=None):
    """假 Strata：图的 desc 写着「场N」就挑第 N 场（只在候选里挑），否则 None。"""
    def judge(info, cands):
        if calls is not None:
            calls.append([i for i, _s in cands])
        want = info.get("desc") or ""
        for i, s in cands:
            if want == s["caption"]:
                return i
        return None
    return judge


class SequentialMatchTest(unittest.TestCase):
    def test_in_order_and_many_per_scene(self):
        m = mim.sequential_match(_imgs("场0", "场0", "场1", "场2"), _scenes(4), _topic_judge(), log=lambda *_: None)
        self.assertEqual({k: [os.path.basename(i["path"]) for i in v] for k, v in m.items()},
                         {0: ["s001.png", "s002.png"], 1: ["s003.png"], 2: ["s004.png"]})

    def test_skip_unmatched_and_lookahead(self):
        calls = []
        m = mim.sequential_match(_imgs("标题页", "场2", "场1"), _scenes(6), _topic_judge(calls), window=3,
                                 log=lambda *_: None)
        # 标题页对不上 → 跳过；下一张窗口放宽；场1 在场2 之后不回头
        self.assertEqual(list(m), [2])
        self.assertEqual(calls[0], [0, 1, 2])
        self.assertEqual(calls[1], [0, 1, 2, 3, 4, 5])
        self.assertEqual(calls[2][0], 2)

    def test_judge_error_and_empty_desc_skipped(self):
        def bad(info, cands):
            raise RuntimeError("boom")
        imgs = _imgs("场0") + [{"path": "x.png", "source": "pdf", "page": 3, "desc": "", "text": ""}]
        self.assertEqual(mim.sequential_match(imgs, _scenes(2), bad, log=lambda *_: None), {})


class StrataJudgeTest(unittest.TestCase):
    def test_parses_scene_number_and_rejects_out_of_window(self):
        scenes = _scenes(5)
        cands = [(2, scenes[2]), (3, scenes[3])]
        seen = {}

        def ask(system, user):
            seen["user"] = user
            return '{"scene": 4}'
        self.assertEqual(mim.make_strata_judge(ask)({"desc": "d", "text": "字"}, cands), 3)
        self.assertIn("[3] Caption: 场2", seen["user"])
        self.assertIn("Text in the picture: 字", seen["user"])
        self.assertIsNone(mim.make_strata_judge(lambda s, u: '{"scene": 1}')({"desc": "d"}, cands))
        self.assertIsNone(mim.make_strata_judge(lambda s, u: '{"scene": 0}')({"desc": "d"}, cands))


class RefImagesTest(unittest.TestCase):
    def test_append_without_duplicates_mixed_sources(self):
        scene = {"visual": "v", "ref_images": [{"path": "C:/w/a/p001.png", "source": "pdf", "page": 1}]}
        pdf = [{"path": "C:/w/a/p001.png", "source": "pdf", "page": 1, "desc": "x"},
               {"path": "C:/w/a/p002_1.png", "source": "pdf", "page": 2, "desc": "y"}]
        vid = [{"path": "C:/w/b/s003.png", "source": "video", "index": 3, "time": 12.5, "desc": "z"}]
        self.assertEqual(mim.add_ref_images(scene, pdf), 1)
        self.assertEqual(mim.add_ref_images(scene, vid), 1)
        self.assertEqual(mim.add_ref_images(scene, vid), 0)
        refs = scene["ref_images"]
        self.assertEqual([r["source"] for r in refs], ["pdf", "pdf", "video"])
        self.assertEqual(refs[1]["page"], 2)
        self.assertEqual(refs[2]["index"], 3)
        self.assertEqual(refs[2]["time"], 12.5)
        json.dumps(refs, ensure_ascii=False)

    def test_apply_matches_by_index_or_fingerprint(self):
        snap = _scenes(3)
        img = _imgs("场1")
        cur = json.loads(json.dumps(snap))
        self.assertEqual(mim.apply_matches(cur, snap, {1: img}), (1, 0))
        self.assertEqual(cur[1]["ref_images"][0]["path"], img[0]["path"])
        # 跑的时候前面插了一场：按内容找回第 1 场
        cur2 = [{"caption": "新"}] + json.loads(json.dumps(snap))
        self.assertEqual(mim.apply_matches(cur2, snap, {1: img}), (1, 0))
        self.assertIn("ref_images", cur2[2])
        cur3 = [{"caption": "完全不同"}]
        self.assertEqual(mim.apply_matches(cur3, snap, {1: img}), (0, 1))


class DescribeCacheTest(unittest.TestCase):
    def test_cache_by_path_and_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s001.png")
            pathlib.Path(p).write_bytes(b"x")
            n = {"calls": 0}

            def ask(path):
                n["calls"] += 1
                return '```json\n{"desc": "神的智慧", "text": "锦囊"}\n```'
            disk = {}
            self.assertEqual(mim.describe_image(p, ask=ask, disk=disk), {"desc": "神的智慧", "text": "锦囊"})
            mim.describe_image(p, ask=ask, disk=disk)
            self.assertEqual(n["calls"], 1)
            self.assertIn(mim.image_cache_key(p), disk)
            bad = mim.describe_image(os.path.join(d, "none.png"), ask=lambda _p: "no json")
            self.assertTrue(bad.get("error"))


class RunMatchTest(unittest.TestCase):
    def test_run_match_with_fakes(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for k in (1, 2, 3):
                p = os.path.join(d, f"s{k:03d}.png")
                pathlib.Path(p).write_bytes(bytes([k]))
                paths.append(p)
            topics = {paths[0]: "场0", paths[1]: "片尾", paths[2]: "场2"}

            def extract(_mat, _out):
                return [{"path": p, "source": "video", "index": i} for i, p in enumerate(paths, 1)]
            res = mim.run_match("v.mp4", "video", _scenes(3), out_dir=d, log=lambda *_: None, extract=extract,
                                vision_ask=lambda p: json.dumps({"desc": topics[p], "text": ""}),
                                judge=_topic_judge())
            self.assertEqual(sorted(res["matches"]), [0, 2])
            self.assertTrue(os.path.isfile(os.path.join(d, mim.DESC_CACHE_FILE)))
            text = mim.summary_text(res, 2)
            self.assertIn("抽出 3 张图，对上 2 张", text)
            self.assertIn("第 3 场：s003.png", text)


class ExtractTest(unittest.TestCase):
    def test_working_dir(self):
        self.assertEqual(mim.working_dir_for(r"D:\x\nblm_video_overview_1.mp4", r"D:\W"),
                         os.path.join(r"D:\W", "nblm_video_overview_1"))

    def test_slide_picker(self):
        a = np.full((54, 96), 200, "float32")
        b = a.copy()
        b[10:40, 10:80] = 40
        fade = (a + b) / 2
        dark = np.zeros((54, 96), "float32")
        seq = [dark, dark, a, a, a, fade, b, b, b, a, a]
        # a 停稳 → 1 张；淡入淡出那帧不停稳不要；b 停稳 → 1 张；又回到 a = 重复，不要
        self.assertEqual(mim.pick_slide_frames(seq), [3, 7])

    def test_pdf_text_pages_skipped_image_pages_kept(self):
        import fitz
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            png = os.path.join(d, "pic.png")
            Image.new("RGB", (200, 120), (30, 120, 200)).save(png)
            pdf = os.path.join(d, "doc.pdf")
            doc = fitz.open()
            doc.new_page().insert_text((72, 72), "only text")
            p2 = doc.new_page()
            p2.insert_image(p2.rect, filename=png)
            p3 = doc.new_page()
            p3.insert_text((72, 72), "text and a picture")
            p3.insert_image(fitz.Rect(72, 300, 372, 480), filename=png)
            doc.new_page().insert_image(fitz.Rect(10, 10, 30, 30), filename=png)  # 小图标不算
            doc.save(pdf)
            doc.close()
            out = mim.extract_pdf_images(pdf, os.path.join(d, "out"), log=lambda *_: None)
            self.assertEqual([os.path.basename(i["path"]) for i in out], ["p002.png", "p003_1.png"])
            self.assertEqual([i["page"] for i in out], [2, 3])
            self.assertTrue(all(os.path.isfile(i["path"]) for i in out))


class GuiWiringTest(unittest.TestCase):
    def test_menu_items_and_select_same_as_click(self):
        se = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn('label="抽图对场景…"', se)
        self.assertIn('label="抽幻灯片对场景…"', se)
        self.assertIn('label="选作生成材料", command=lambda: materials_panel.select_entry(entry)', se)
        self.assertIn("mim.run_match(", se)
        self.assertIn("mim.apply_matches(", se)
        mp = (ROOT / "gui" / "dl" / "materials_panel.py").read_text(encoding="utf-8")
        start = mp.index("def select_entry")
        body = mp[start:mp.index("def _double", start)]
        for need in ("self.focused_entry = entry", "self._paint_selection()", "self._on_select(entry)"):
            self.assertIn(need, body)


if __name__ == "__main__":
    unittest.main()
