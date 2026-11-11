"""t400u: 人物预览窗拆分/拼回性别、年龄、民族、名字和括号描述（不依赖 Tk）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility.actor_edit_fields import (  # noqa: E402
    ACTOR_AGES,
    ACTOR_GENDERS,
    ACTOR_RACES,
    actor_edit_combo_values,
    actor_paren_is_motion,
    format_actor_edit_fields,
    parse_actor_edit_fields,
)


class ActorEditFieldsTest(unittest.TestCase):
    def test_custom_tokens_kept_not_defaulted(self):
        fields = parse_actor_edit_fields("男女/29-31歲/東亞")
        self.assertEqual(fields["gender"], "男女")
        self.assertEqual(fields["age"], "29-31歲")
        self.assertEqual(fields["race"], "東亞")
        self.assertEqual(fields["name"], "")
        self.assertEqual(fields["note"], "")
        self.assertEqual(format_actor_edit_fields(**fields), "男女/29-31歲/東亞")

    def test_standard_actor_and_name(self):
        fields = parse_actor_edit_fields("woman/mature/chinese")
        self.assertEqual(fields, {
            "gender": "woman", "age": "mature", "race": "chinese", "name": "", "note": "",
        })
        fields = parse_actor_edit_fields("woman/mature/chinese/29歲")
        self.assertEqual(fields["name"], "29歲")
        self.assertEqual(fields["age"], "mature")
        self.assertEqual(format_actor_edit_fields(**fields), "woman/mature/chinese/29歲")

    def test_english_aliases_map_to_canonical(self):
        fields = parse_actor_edit_fields("female/adult/English/Ann")
        self.assertEqual(fields["gender"], "woman")
        self.assertEqual(fields["age"], "mature")
        self.assertEqual(fields["race"], "english")
        self.assertEqual(fields["name"], "Ann")

    def test_parenthetical_description_fullwidth_and_ascii(self):
        fields = parse_actor_edit_fields("woman/mature/chinese/林（穿红衣，坐在左边）")
        self.assertEqual(fields["name"], "林")
        self.assertEqual(fields["note"], "穿红衣，坐在左边")
        self.assertEqual(
            format_actor_edit_fields(**fields),
            "woman/mature/chinese/林（穿红衣，坐在左边）",
        )
        fields = parse_actor_edit_fields("man/youth/chinese/阿明 (holding a book)")
        self.assertEqual(fields["name"], "阿明")
        self.assertEqual(fields["note"], "holding a book")
        self.assertEqual(
            format_actor_edit_fields(**fields),
            "man/youth/chinese/阿明（holding a book）",
        )

    def test_motion_paren_is_not_description(self):
        body = "woman/mature/chinese/林（从容自然地 - 走进画面，讲完走出）"
        fields = parse_actor_edit_fields(body)
        self.assertEqual(fields["name"], "林")
        self.assertEqual(fields["note"], "")
        self.assertTrue(actor_paren_is_motion("从容自然地 - 走进画面，讲完走出"))
        self.assertTrue(actor_paren_is_motion("淡入畫面，講完淡出"))
        self.assertFalse(actor_paren_is_motion("穿红衣，坐在左边"))
        self.assertEqual(format_actor_edit_fields(**fields), "woman/mature/chinese/林")

    def test_format_strips_slash_and_parens(self):
        self.assertEqual(
            format_actor_edit_fields("woman", "mature", "chinese", "林/二", "（穿红衣）"),
            "woman/mature/chinese/林二（穿红衣）",
        )
        self.assertEqual(format_actor_edit_fields("man", "youth", "chinese"), "man/youth/chinese")
        self.assertEqual(parse_actor_edit_fields(""), {
            "gender": "", "age": "", "race": "", "name": "", "note": "",
        })

    def test_combo_values_prepend_unknown(self):
        self.assertEqual(
            actor_edit_combo_values(ACTOR_GENDERS, "男女"),
            ("男女", "man", "woman"),
        )
        self.assertEqual(
            actor_edit_combo_values(ACTOR_AGES, "29-31歲"),
            ("29-31歲",) + ACTOR_AGES,
        )
        self.assertEqual(
            actor_edit_combo_values(ACTOR_RACES, "東亞"),
            ("東亞", "chinese", "english"),
        )
        self.assertEqual(actor_edit_combo_values(ACTOR_GENDERS, "woman"), ACTOR_GENDERS)
        self.assertEqual(actor_edit_combo_values(ACTOR_AGES, ""), ACTOR_AGES)

    def test_dialog_source_keeps_raw_body_and_editable_fields(self):
        src = (ROOT / "gui/workflow/wf_actors.py").read_text(encoding="utf-8")
        person = src[src.index("    def _review_actor_person("):src.index("    def _open_portrait_dialog(")]
        self.assertIn('actor_entry={"role": "person", "label": "人物", "body": raw}', person)
        self.assertIn("parse_actor_edit_fields", src)
        self.assertIn("format_actor_edit_fields", src)
        dlg = src[src.index("    def _open_portrait_dialog("):src.index("    def _scene_actor_rows(")]
        self.assertIn('text="括号描述"', dlg)
        self.assertIn('state="normal"', dlg)
        self.assertIn("edit_note", dlg)
        self.assertIn("new_id != opened_id", dlg)
        # 人物预览这三栏不再用只读下拉把「男女」一类值换成默认值
        fill = dlg[dlg.index("def _fill_edit"):dlg.index("def _on_edit_change")]
        self.assertNotIn('else "woman"', fill)
        self.assertNotIn('else "mature"', fill)
        self.assertNotIn('else "chinese"', fill)


if __name__ == "__main__":
    unittest.main()
