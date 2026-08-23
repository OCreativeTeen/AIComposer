"""Verification for hermes/wf_lib.py + hermes/nb.py.

Pure-function tests (geometry/parsing) run headless and assert real values.
GUI-dependent helpers are only smoke-checked for importability + signature,
since they require a live window and would mutate real pipeline state.
"""
import sys, os, json, inspect
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import numpy as np
import cv2

import wf_lib

FAILS = []
CHECKS = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + str(detail)) if detail else ''))
    CHECKS.append(name)
    if not cond:
        FAILS.append(name)


# --- button_rows / uniform_row on a synthetic toolbar -----------------------
img = np.full((300, 800, 3), 240, np.uint8)
truth = []
for i in range(5):                                   # 5 uniform 114x38 buttons
    x = 40 + i * 130
    cv2.rectangle(img, (x, 200), (x + 114, 238), (90, 90, 90), 1)
    truth.append(x + 57)
cv2.rectangle(img, (40, 60), (300, 88), (90, 90, 90), 1)   # a wider decoy
tmp = os.path.join(os.path.dirname(__file__), '_verify_toolbar.png')
cv2.imwrite(tmp, img)

rects = wf_lib.button_rows(tmp, 180, 260)
row = wf_lib.uniform_row(rects)
check('button_rows finds the 5 buttons', len(row) == 5, f'got {len(row)}')
check('uniform_row shares one y', len({d['cy'] for d in row}) == 1, {d['cy'] for d in row})
check('centers match truth (+-3px)',
      len(row) == 5 and all(abs(a['cx'] - b) <= 3 for a, b in zip(row, truth)),
      [d['cx'] for d in row])
check('decoy band excluded', all(d['cy'] > 150 for d in row))

sheet = wf_lib.contact_sheet(tmp, row, os.path.join(os.path.dirname(__file__), '_verify_sheet.png'))
sh = cv2.imread(sheet)
check('contact_sheet stacks 5 crops', sh is not None and sh.shape[0] >= 5 * 38, sh.shape if sh is not None else None)

# --- banner-tolerant JSON scan (the Step 2 extraction path) ----------------
page = ('pygame 2.6.1 banner\nHello here is your JSON\n'
        '[{"caption":"a","voiceover":"v","visual":"x","speaking":"s","actor":"m"},'
        '{"caption":"b","voiceover":"v","visual":"x","speaking":"s","actor":"m"}]\ntrailing chatter')
dec = json.JSONDecoder()
best = None
for i, ch in enumerate(page):
    if ch != '[':
        continue
    try:
        o, _ = dec.raw_decode(page, i)
    except ValueError:
        continue
    if isinstance(o, list) and o and isinstance(o[0], dict) and 'caption' in o[0]:
        if best is None or len(o) > len(best):
            best = o
check('scene JSON survives banners + trailing text', best is not None and len(best) == 2, best and len(best))
check('scene schema keys intact',
      best and sorted(best[0]) == ['actor', 'caption', 'speaking', 'visual', 'voiceover'])

# --- API surface -----------------------------------------------------------
for fn in ('click', 'activate', 'shot', 'find', 'app_children', 'find_windows', 'move', 'ctl', 'clip'):
    check(f'wf_lib.{fn} present', callable(getattr(wf_lib, fn, None)))
check('click is (hwnd,x,y,pre)', list(inspect.signature(wf_lib.click).parameters) == ['hwnd', 'x', 'y', 'pre'])

src = open(os.path.join(os.path.dirname(__file__), 'wf_lib.py'), encoding='utf-8').read()
check('click uses mouse_event not auto.Click (Tk COMError guard)',
      'mouse_event' in src and 'auto.Click' not in src)
check('geometry taken from UIA BoundingRectangle, not GetWindowRect',
      'BoundingRectangle' in src and 'GetWindowRect' not in src)

nbsrc = open(os.path.join(os.path.dirname(__file__), 'nb.py'), encoding='utf-8').read()
check('nb.py verifies pasted prompt length', 'GetValuePattern().Value' in nbsrc and 'len(v) < 500' in nbsrc)
check('nb.py uses SetFocus before paste', 'SetFocus()' in nbsrc)
check('nb.py has no bare Close matcher', "== 'Close'" not in nbsrc)

for f in (tmp, sheet):
    os.remove(f)

print('\n%d checks, %d failed' % (len(CHECKS), len(FAILS)))
if FAILS:
    print('FAILED:', FAILS)
sys.exit(1 if FAILS else 0)
