# -*- coding: utf-8 -*-
"""t280: actor 新写法：人物写 性别/年龄段/族裔/名字（括号可选），不带 人物N：；讲员写 ``H …``；用 " | " 隔开。
解析照样认旧写法；写出来只有新写法；只在保存时迁移。提示词里描述 / 用到 actor 的地方都改成新写法。"""
import importlib
import os
import re
import sys
import types
import unittest

from tests.test_t272_pdf_scenes_cast import _read


# t280: 别的测试会在 sys.modules 里留下假的 config / project_manager；这里的测试用真的，跑完原样放回去。
_REAL_NAMES = ("config", "config_prompt", "config_channel", "project_manager")
_ROOT = os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SNAPSHOT = {}


def _is_real(mod) -> bool:
    f = getattr(mod, "__file__", None) or ""
    return bool(f) and os.path.normcase(os.path.dirname(os.path.abspath(f))) == _ROOT


def use_real_modules() -> None:
    _SNAPSHOT.clear()
    _SNAPSHOT.update(sys.modules)
    fakes = {n for n in _REAL_NAMES if n in sys.modules and not _is_real(sys.modules[n])}
    for n in list(sys.modules):
        mod = sys.modules.get(n)
        if n in fakes:
            del sys.modules[n]
            continue
        if n.split(".")[0] in ("utility", "gui") or n in _REAL_NAMES:
            g = getattr(mod, "__dict__", {}) or {}
            if any(isinstance(v, types.ModuleType) and v.__name__ in _REAL_NAMES and not _is_real(v)
                   for v in list(g.values())):
                del sys.modules[n]


def restore_modules() -> None:
    if not _SNAPSHOT:
        return
    for n in list(sys.modules):
        if n not in _SNAPSHOT:
            del sys.modules[n]
    sys.modules.update(_SNAPSHOT)
    _SNAPSHOT.clear()


pm = af = None


def setUpModule():
    global pm, af
    use_real_modules()
    pm = importlib.import_module("project_manager")
    af = importlib.import_module("utility.actor_format")


def tearDownModule():
    restore_modules()

OLD = "讲员：woman/mature/chinese/秦 | 人物1：man/youth/chinese/门子（低头） | 人物2：man/mature/chinese/贾雨村"
NEW = "H woman/mature/chinese/秦 | man/youth/chinese/门子（低头） | man/mature/chinese/贾雨村"


class Format(unittest.TestCase):
    def test_migrate_old_to_new(self):
        self.assertEqual(af.migrate(OLD), NEW)
        self.assertEqual(pm.migrate_actor_text(OLD), NEW)

    def test_migrate_is_idempotent_and_detects_new(self):
        self.assertTrue(af.is_new_format(NEW))
        self.assertFalse(af.is_new_format(OLD))
        self.assertEqual(af.migrate(NEW), NEW)

    def test_other_old_labels(self):
        self.assertEqual(af.migrate("人物：man/youth/chinese/甲 | 主持人：woman/mature/chinese/秦"),
                         "man/youth/chinese/甲 | H woman/mature/chinese/秦")

    def test_parsers_accept_both(self):
        old_rows = [(r["role"], r["body"]) for r in pm.actor_entries(OLD)]
        new_rows = [(r["role"], r["body"]) for r in pm.actor_entries(NEW)]
        self.assertEqual(old_rows, new_rows)
        self.assertEqual(new_rows[0], ("host", "woman/mature/chinese/秦"))

    def test_writer_emits_only_new(self):
        text = pm.format_actor_entries(pm.actor_entries(OLD))
        self.assertEqual(text, NEW)
        self.assertNotRegex(text, r"(人物\d*|讲员)[：:]")

    def test_split_label_and_entry(self):
        self.assertEqual(af.split_label("H woman/mature/chinese/秦"), ("host", "woman/mature/chinese/秦"))
        self.assertEqual(af.split_label("人物3：man/youth/chinese/甲")[0], "person")
        self.assertEqual(af.entry("host", "woman/mature/chinese/秦"), "H woman/mature/chinese/秦")
        self.assertEqual(af.entry("person", "man/youth/chinese/甲"), "man/youth/chinese/甲")

    def test_semicolon_inside_note_is_not_a_separator(self):
        segs = af.segments("man/youth/chinese/甲（低头；不语） | H woman/mature/chinese/秦")
        self.assertEqual(len(segs), 2)

    def test_migrate_scene_actors_on_save(self):
        scenes = [{"actor": OLD, "speaking": "<1>开场<2>老爷"}, {"actor": NEW}]
        n = pm.migrate_scene_actors(scenes)
        self.assertEqual(n, 1)
        self.assertEqual(scenes[0]["actor"], NEW)
        self.assertEqual(scenes[0]["speaking"], "<1>开场<2>老爷")  # 位置不变，<N> 不动


class Prompts(unittest.TestCase):
    def test_speaker_rule_is_positional_no_labels(self):
        import config_prompt

        rule = str(config_prompt.SCENE_SPEAKER_ID_RULE)
        self.assertIn("H", rule)
        self.assertNotRegex(rule, r"人物\d+：")

    def test_config_channel_has_no_old_label_examples(self):
        src = _read("config_channel.py")
        self.assertNotRegex(src, r"人物\d+：")
        self.assertNotRegex(src, r"讲员[：:]\s*(woman|man|girl|boy|\{)")
        for m in re.finditer(r"人物N：", src):
            self.assertRegex(src[max(0, m.start() - 12):m.start()], r"(never|no) $")

    def test_cast_block_lines(self):
        from gui.dl import prompts_notebooklm as p

        block = p.build_cast_block(NEW, 4)
        self.assertIn("  - H woman/mature/chinese/秦", block)
        self.assertIn("  - man/youth/chinese/门子", block)
        self.assertNotIn("人物1", block)

    def test_cast_preset_prompt_says_no_label(self):
        src = _read("utility", "cast_preset.py")
        self.assertIn("never 人物N： or 人物：", src)

    def test_workflow_host_written_with_H(self):
        self.assertIn('scene["actor"] = f"H {voice}"', _read("gui", "workflow", "wf_actors.py"))


if __name__ == "__main__":
    unittest.main()
