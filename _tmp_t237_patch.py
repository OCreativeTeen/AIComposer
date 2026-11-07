# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(r"D:\AIComposer\gui\workflow\wf_prompt_flows.py")
text = path.read_text(encoding="utf-8")

old = '''        picked = None
        try:  # t176u: 直接用上次「图片修改」记住的 LLM + 账户；没有记录 / 账户不在了才弹选择窗
            import config
            from utility import chrome_account

            last = dict(config.load_yt_tools_prefs().get(PICTURE_SUBMIT_PREF) or {})
            llm = str(last.get("llm") or "").strip().lower()
            acct = chrome_account.normalize(last.get("account") or "")
            if llm == "moss":
                picked = ("moss", "")
                print("🖼 从封面逐场提取：用上次的选择 MOSS（本机 ComfyUI）")
            elif llm == "qn":
                picked = ("qn", "")
                print("🖼 从封面逐场提取：用上次的选择 QN（本机 ComfyUI）")
            elif llm in ("grok", "gemini") and chrome_account.profile_dir(acct):
                picked = (llm, acct)
                print(f"🖼 从封面逐场提取：用上次的选择 {llm} / {acct or '默认账户'}")
        except Exception as exc:  # noqa: BLE001
            print(f"从封面逐场提取：读上次的选择失败，改为弹窗：{exc}")
        if not picked:
            picked = ask_llm_and_account(
                self.root, pref_key=PICTURE_SUBMIT_PREF,
                title=f"从封面提取每一场的图（共 {n} 场，取消 = 不做）",
                extra_backends=(("moss", "MOSS"), ("qn", "QN")),
            )
'''

new = '''        picked = None
        try:  # t176u / t237u: 封面逐场提取固定用 Grok（QN/MOSS 效果差；手动「图片修改」仍可选 QN/MOSS）
            import config
            from utility import chrome_account

            last = dict(config.load_yt_tools_prefs().get(PICTURE_SUBMIT_PREF) or {})
            llm = str(last.get("llm") or "").strip().lower()
            acct = chrome_account.normalize(last.get("account") or "")
            if llm in ("qn", "moss"):
                print(f"🖼 从封面逐场提取：上次是 {llm.upper()}，改回 Grok")
                # 顺手把记住的后端改回 grok，避免下次又误用；账户先留着
                try:
                    config.save_yt_tools_prefs({PICTURE_SUBMIT_PREF: {"llm": "grok", "account": acct}})
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 封面提取：没有把上次后端改回 Grok：{exc}")
                llm = "grok"
            if llm == "grok" and chrome_account.profile_dir(acct):
                picked = ("grok", acct)
                print(f"🖼 从封面逐场提取：用 Grok / {acct or '默认账户'}")
        except Exception as exc:  # noqa: BLE001
            print(f"从封面逐场提取：读上次的选择失败，改为弹窗：{exc}")
        if not picked:
            # 只选 Chrome 账户；后端固定 Grok（取消 = 不做）
            picked = ask_llm_and_account(
                self.root, pref_key=PICTURE_SUBMIT_PREF,
                title=f"从封面提取每一场的图（Grok · 共 {n} 场，取消 = 不做）",
                fixed_backend="grok",
            )
'''

if "t237u: 封面逐场提取固定用 Grok" in text:
    print("already patched")
else:
    if old not in text:
        raise SystemExit("old block not found")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])
    print("patched")

import py_compile
py_compile.compile(str(path), doraise=True)
print("py_compile OK")

# sanity: manual picker still has QN/MOSS
ppd = Path(r"D:\AIComposer\gui\picture_prompt_dialog.py").read_text(encoding="utf-8")
assert 'extra_backends=(("moss", "MOSS"), ("qn", "QN"))' in ppd
print("manual picture submit picker still has MOSS/QN")

# show resulting block
lines = path.read_text(encoding="utf-8").splitlines()
for i in range(222, 260):
    print(f"{i+1}|{lines[i][:160]}")
