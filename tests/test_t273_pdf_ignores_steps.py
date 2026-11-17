# -*- coding: utf-8 -*-
"""t273: PDF 来源一律一页一个场景（所有后端），步数（1–6 固定场景数）对 PDF 不管用；非 PDF 来源的步数照旧。

假 Grok / Gemini / Strata，子进程里跑真 downloader，只读，不写任何项目 / 列表数据。"""
import json
import os
import unittest

from tests.test_t272_pdf_scenes_cast import _FAKE_SELF, _read, _real

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PdfIgnoresSteps(unittest.TestCase):
    def test_every_backend_gets_the_same_prompt_whatever_the_steps_are(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(3)
cast = "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"
seen = []
def gen(prompt, sys_, expect_list=True, attachment=None, extra=None):
    seen.append(prompt)
    return [{"visual": "v%d" % i, "actor": "", "speaking": ""} for i in range(3)]
f.llm_api_manual = type("M", (), {"generate_json": staticmethod(gen)})()
def run(steps, backend, att):
    vd = {"analyzed_content": "x", "story_actors": cast}
    if backend == "strata":
        out = []
        def ask(img, system, user):
            out.append(system); return json.dumps([{"visual": "v"}])
        G(f, vd, "故事对话", attachment=att, text_backend="strata", prompt_params={"steps": steps, "episodes": 1}, strata_ask=ask)
        return out[0]
    G(f, vd, "故事对话", content_override="x", attachment=att, text_backend=backend, prompt_params={"steps": steps, "episodes": 1})
    return seen[-1]
out = {}
for backend in ("grok", "gemini", "strata"):
    out[backend] = [run(0, backend, pdf), run(4, backend, pdf), run(6, backend, pdf)]
out["text"] = [run(0, "grok", ""), run(4, "grok", "")]   # 非 PDF：步数照旧
import shutil; shutil.rmtree(tmp, True)
print(json.dumps(out, ensure_ascii=False))
''')
        for backend in ("grok", "gemini", "strata"):
            a, b, c = res[backend]
            self.assertEqual(a, b, backend)  # 步数 4 / 6 对 PDF 没有任何作用
            self.assertEqual(a, c, backend)
        zero, four = res["text"]
        self.assertNotEqual(zero, four)  # 非 PDF：步数 4 还是固定 4 场
        self.assertNotEqual(res["grok"][1], four)

    def test_editor_zeroes_steps_for_pdf_and_hint_line_says_so(self):
        se = _read("gui", "dl", "scene_editor.py")
        # t277: 步数和「共 N 集」之间不再放说明；「步数不用」改在材料行下面那一行提示里
        self.assertNotIn("步数不用\"", se)
        self.assertNotIn("step_note", se)
        self.assertIn("PDF：一页一个场景，步数不用", _read("gui", "dl", "material_hint.py"))
        self.assertIn('_hint_sync = scene_ui.get("sync_material_hint")', se[se.index("def _sync_steps_for_pdf"):se.index("def _sync_episode_enable")])
        self.assertIn('_step_kind_of((prompt_combo_var.get() or "").strip()) == "dialogue"', se)  # 只管故事对话的步数
        self.assertIn('step_count_combo.configure(state="disabled" if off else "readonly")', se)
        self.assertIn('_material_is_pdf[0] = material_var.get() == "pdf"', se)
        sync = se[se.index("def _sync_dynamic_prompt_widgets"):se.index("prompt_combo_var.trace_add")]
        self.assertIn("_sync_steps_for_pdf()", sync)  # 切叙事方式也重新判断
        self.assertIn("0 if _steps_ignored_now() else _int_of(step_count_var, 0)", se)  # 共 N 集 按页算，不被步数锁住
        # 步数下拉里存的值不动（换回非 PDF 材料还是原来的步数）
        self.assertNotIn("step_count_var.set(0", se[se.index("def _steps_ignored_now"):se.index("def _sync_episode_enable")])

    def test_downloader_backstop_zeroes_steps_for_pdf_attachments(self):
        dl = _read("gui", "downloader.py")
        self.assertIn("prompt_params = dict(prompt_params or {}, steps=0)", dl)
        self.assertLess(dl.index("prompt_params = dict(prompt_params or {}, steps=0)"),
                        dl.index("return self._generate_pdf_scenes_per_page_strata("))


if __name__ == "__main__":
    unittest.main()
