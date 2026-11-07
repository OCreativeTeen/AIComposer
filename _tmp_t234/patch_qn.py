from pathlib import Path

# ---- config.py ----
p = Path(r'D:\AIComposer\config.py')
t = p.read_text(encoding='utf-8')
needle = 'COMFYUI_MOSS_URL = _env("COMFYUI_MOSS_URL", "http://192.168.1.30:8188")\n'
insert = needle + (
    '# t234u: Qwen(QN) 图片编辑与 MOSS 同机 ComfyUI；可用 COMFYUI_QN_URL 覆盖，默认同 MOSS\n'
    'COMFYUI_QN_URL = _env("COMFYUI_QN_URL", COMFYUI_MOSS_URL)\n'
)
if 'COMFYUI_QN_URL' not in t:
    if needle not in t:
        raise SystemExit('COMFYUI_MOSS_URL line missing')
    t = t.replace(needle, insert, 1)
    p.write_bytes(t.encode('utf-8'))
    print('config OK')
else:
    print('config already has QN')

# ---- sd_image_processor.py: append QN block ----
p = Path(r'D:\AIComposer\utility\sd_image_processor.py')
t = p.read_text(encoding='utf-8')
if 'generate_image_qwen_edit' in t:
    print('sd already has qwen')
else:
    block = r'''

# ---------------------------------------------------------------------------
# t234u: Qwen(QN) 图片编辑（ComfyUI · workflow/qwen_edit_3ref_api.json）
# ---------------------------------------------------------------------------
# 与 MOSS 同机（默认 COMFYUI_QN_URL = COMFYUI_MOSS_URL = 192.168.1.30:8188）。
# API 工作流：LoadImage base(8) → FluxKontextImageScale(117)
#   → TextEncodeQwenImageEditPlus 正面(39)/负面(36)：image1=缩放底图，image2/3=可选参考
#   → VAEEncode(88) → KSampler(37) → VAEDecode → SaveImage(9)
# image2/image3 为 optional：无参考时删掉槽位与 LoadImage，绝不拿底图垫参考（同 t231 教训）。
QN_EDIT_API_WORKFLOW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "workflow", "qwen_edit_3ref_api.json",
)
QN_EDIT_MAX_REFS = 2  # 工作流只有 image2 / image3 两个参考槽


def _qwen_follow_to_loadimage(workflow: Dict[str, Any], start_id) -> str:
    """从编码器的 imageN 链路追到 LoadImage 节点 id。"""
    nid = str(start_id)
    seen = set()
    while nid and nid not in seen:
        seen.add(nid)
        node = workflow.get(nid) or {}
        if node.get("class_type") == "LoadImage":
            return nid
        img = (node.get("inputs") or {}).get("image")
        if isinstance(img, (list, tuple)) and img:
            nid = str(img[0])
            continue
        break
    raise ValueError(f"QN 工作流无法从节点 {start_id} 追到 LoadImage")


def _qwen_slot_load_ids(workflow: Dict[str, Any]) -> dict:
    """返回 {"image1": load_id, "image2": load_id|None, "image3": load_id|None}（按正面编码器）。"""
    ks = _one_node(workflow, "KSampler")
    pos_id = str(workflow[ks]["inputs"]["positive"][0])
    enc = workflow[pos_id]["inputs"]
    if "image1" not in enc:
        raise ValueError("QN 工作流正面编码器没有 image1（底图）")
    out = {"image1": _qwen_follow_to_loadimage(workflow, enc["image1"][0])}
    for key in ("image2", "image3"):
        if key in enc and isinstance(enc[key], (list, tuple)) and enc[key]:
            out[key] = _qwen_follow_to_loadimage(workflow, enc[key][0])
        else:
            out[key] = None
    return out


def adapt_prompt_for_qwen_edit(prompt: str) -> tuple:
    """封面 extract-step：复用 MOSS 口吻（同属本地图编辑，避免多格嵌套）。"""
    return adapt_prompt_for_moss_edit(prompt)


def build_qwen_edit_prompt(workflow: Dict[str, Any], *, base_name: str, ref_names: list,
                           prompt: str, seed: int,
                           filename_prefix: str = "qwen_edit",
                           negative=None) -> Dict[str, Any]:
    """填 qwen_edit_3ref_api：底图 + 最多 2 张真实参考；空参考槽删除（不垫底图）。"""
    import copy

    wf = copy.deepcopy(workflow)
    slots = _qwen_slot_load_ids(wf)
    refs = [n for n in list(ref_names or []) if n][:QN_EDIT_MAX_REFS]
    wf[slots["image1"]]["inputs"]["image"] = base_name
    ref_keys = ["image2", "image3"]
    used_keys = []
    for i, name in enumerate(refs):
        key = ref_keys[i]
        lid = slots.get(key)
        if not lid:
            raise ValueError(f"QN 工作流缺少 {key} 对应的 LoadImage")
        wf[lid]["inputs"]["image"] = name
        used_keys.append(key)

    # 未用参考：从正/负编码器去掉 imageN，并删除对应 LoadImage
    drop_keys = [k for k in ref_keys if k not in used_keys]
    for enc_id in _find_nodes(wf, "TextEncodeQwenImageEditPlus"):
        inp = wf[enc_id]["inputs"]
        for k in drop_keys:
            inp.pop(k, None)
    for k in drop_keys:
        lid = slots.get(k)
        if lid:
            wf.pop(lid, None)

    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    neg_id = str(wf[ks]["inputs"]["negative"][0])
    wf[pos_id]["inputs"]["prompt"] = (prompt or "").strip()
    if negative is not None:
        wf[neg_id]["inputs"]["prompt"] = (negative or "").strip()
    wf[ks]["inputs"]["seed"] = int(seed)
    save_ids = _find_nodes(wf, "SaveImage")
    if save_ids:
        wf[save_ids[0]]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def generate_image_qwen_edit(prompt: str, images, *, server=None, seed=None,
                             workflow_path=None, timeout_s: float = 1800.0,
                             status=None, negative=None):
    """ComfyUI 跑 Qwen(QN) 图片编辑。images[0]=底图，images[1:]=参考（最多 2，可无）。

    返回 PIL.Image。server 默认 config.COMFYUI_QN_URL（与 MOSS 同机）。
    extract-step 提示走 adapt_prompt_for_qwen_edit（同 MOSS 防嵌套）。
    """
    prompt = _to_simplified(prompt)
    adapted, adapt_neg = adapt_prompt_for_qwen_edit(prompt)
    prompt = adapted
    if negative is None and adapt_neg:
        negative = adapt_neg
    import io
    import random
    import time
    import uuid

    def say(msg):
        print(f"[ComfyUI QN] {msg}")
        if callable(status):
            try:
                status(msg)
            except Exception:
                pass

    paths = [p for p in list(images or []) if p and os.path.isfile(p)]
    if not paths:
        raise FileNotFoundError("QN 编辑需要至少一张底图")
    base = (server or getattr(config, "COMFYUI_QN_URL", "")
            or getattr(config, "COMFYUI_MOSS_URL", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("没有设置 ComfyUI 地址（config.COMFYUI_QN_URL）")
    wf_file = workflow_path or QN_EDIT_API_WORKFLOW
    if not os.path.isfile(wf_file):
        raise FileNotFoundError(f"QN 工作流不存在：{wf_file}")
    say(f"ComfyUI {base} · 工作流 {os.path.basename(wf_file)}")
    with open(wf_file, encoding="utf-8-sig") as f:
        workflow = json.load(f)
    seed = int(seed) if seed is not None else random.randint(1, 2**31 - 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def upload(path, name):
        with open(path, "rb") as f:
            r = requests.post(
                f"{base}/upload/image",
                files={"image": (name, f)},
                data={"type": "input", "overwrite": "true"},
                timeout=300,
            )
        r.raise_for_status()
        up = r.json()
        return (up.get("subfolder") + "/" if up.get("subfolder") else "") + up["name"]

    say(f"上传底图 {os.path.basename(paths[0])}")
    base_name = upload(paths[0], f"qn_{stamp}_base_{os.path.basename(paths[0])}")
    ref_names = []
    for i, rp in enumerate(paths[1:1 + QN_EDIT_MAX_REFS], 1):
        say(f"上传参考图 {i} {os.path.basename(rp)}")
        ref_names.append(upload(rp, f"qn_{stamp}_ref{i}_{os.path.basename(rp)}"))
    if len(paths) - 1 > QN_EDIT_MAX_REFS:
        say(f"参考图超过 {QN_EDIT_MAX_REFS} 张，只用前 {QN_EDIT_MAX_REFS} 张")
    say(f"图像槽位：底图 + {len(ref_names)} 张参考（不垫空槽）")

    wf = build_qwen_edit_prompt(
        workflow, base_name=base_name, ref_names=ref_names, prompt=prompt, seed=seed,
        filename_prefix=f"qwen_edit_{stamp}", negative=negative,
    )
    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    slot_keys = sorted(k for k in wf[pos_id]["inputs"] if k.startswith("image"))
    say(f"正面提示词 {len(prompt)} 字；image slots={slot_keys}")
    print("[ComfyUI QN] positive prompt:\n" + prompt[:1200])

    client_id = str(uuid.uuid4())
    r = requests.post(f"{base}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI /prompt HTTP {r.status_code}: {r.text[:800]}")
    prompt_id = r.json()["prompt_id"]
    say(f"已提交 prompt_id={prompt_id}（seed={seed}，底图 + {len(ref_names)} 参考）")

    started = time.monotonic()
    last_say = 0.0
    entry = None
    while time.monotonic() - started < timeout_s:
        try:
            h = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()
        except requests.RequestException as e:
            h = {}
            print(f"[ComfyUI QN] /history 读取失败：{e}")
        entry = h.get(prompt_id)
        if entry and (entry.get("status") or {}).get("completed") is not None:
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                err = next((m[1] for m in st.get("messages", []) if m and m[0] == "execution_error"), {})
                raise RuntimeError(
                    f"ComfyUI 运行出错（{err.get('node_type')}）：{str(err.get('exception_message'))[:500]}"
                )
            if entry.get("outputs"):
                break
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 15:
            say(f"生成中 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(2.0)
    else:
        raise RuntimeError(f"等了 {int(timeout_s)} 秒，ComfyUI 还没生成完（prompt_id={prompt_id}）")

    imgs = []
    for out in (entry.get("outputs") or {}).values():
        imgs += [x for x in (out.get("images") or []) if x.get("filename")]
    if not imgs:
        raise RuntimeError(f"ComfyUI 完成了但没有图片输出：{json.dumps(entry.get('outputs'), ensure_ascii=False)[:300]}")
    v = imgs[0]
    say(f"下载 {v['filename']}")
    with requests.get(
        f"{base}/view",
        params={"filename": v["filename"], "subfolder": v.get("subfolder", ""), "type": v.get("type", "output")},
        timeout=600,
    ) as resp:
        resp.raise_for_status()
        data = resp.content
    return Image.open(io.BytesIO(data)).convert("RGB")
'''
    t = t.rstrip() + '\n' + block
    # strip any BOM
    if t.startswith('\ufeff'):
        t = t.lstrip('\ufeff')
    p.write_bytes(t.encode('utf-8'))
    print('sd_image_processor QN appended, lines', len(t.splitlines()))

# ---- picture_prompt_dialog.py ----
p = Path(r'D:\AIComposer\gui\picture_prompt_dialog.py')
t = p.read_text(encoding='utf-8')
old = 'picked = ask_llm_and_account(dlg, extra_backends=(("moss", "MOSS"),))'
new = 'picked = ask_llm_and_account(dlg, extra_backends=(("moss", "MOSS"), ("qn", "QN")))'
if old not in t:
    raise SystemExit('picture dialog extra_backends missing')
t = t.replace(old, new, 1)
t = t.replace(
    '「提交」先问后端（Grok / Gemini / MOSS）和 Chrome 账户；MOSS 本机 ComfyUI，不用账户。',
    '「提交」先问后端（Grok / Gemini / MOSS / QN）和 Chrome 账户；MOSS/QN 本机 ComfyUI，不用账户。',
    1,
)
p.write_bytes(t.encode('utf-8'))
print('picture_prompt_dialog OK')

# ---- wf_prompt_flows.py ----
p = Path(r'D:\AIComposer\gui\workflow\wf_prompt_flows.py')
t = p.read_text(encoding='utf-8')

repls = [
(
'''            # t229u: grok（默认）/ gemini / moss（本机 ComfyUI）
            b = str(backend or "").strip().lower()
            extra = {}
            if b == "gemini":
                extra["image_backend"] = "gemini"
            elif b == "moss":
                extra["image_backend"] = "moss"
            if account and b != "moss":
                extra["chrome_account"] = account
''',
'''            # t229u / t234u: grok（默认）/ gemini / moss / qn（本机 ComfyUI）
            b = str(backend or "").strip().lower()
            extra = {}
            if b == "gemini":
                extra["image_backend"] = "gemini"
            elif b == "moss":
                extra["image_backend"] = "moss"
            elif b == "qn":
                extra["image_backend"] = "qn"
            if account and b not in ("moss", "qn"):
                extra["chrome_account"] = account
'''
),
(
'''            if llm == "moss":
                picked = ("moss", "")
                print("🖼 从封面逐场提取：用上次的选择 MOSS（本机 ComfyUI）")
            elif llm in ("grok", "gemini") and chrome_account.profile_dir(acct):
''',
'''            if llm == "moss":
                picked = ("moss", "")
                print("🖼 从封面逐场提取：用上次的选择 MOSS（本机 ComfyUI）")
            elif llm == "qn":
                picked = ("qn", "")
                print("🖼 从封面逐场提取：用上次的选择 QN（本机 ComfyUI）")
            elif llm in ("grok", "gemini") and chrome_account.profile_dir(acct):
'''
),
(
'''                extra_backends=(("moss", "MOSS"),),
''',
'''                extra_backends=(("moss", "MOSS"), ("qn", "QN")),
'''
),
(
'''        use_gemini = b == "gemini"
        use_moss = b == "moss"
        who = "MOSS" if use_moss else ("Gemini" if use_gemini else "Grok")
''',
'''        use_gemini = b == "gemini"
        use_moss = b == "moss"
        use_qn = b == "qn"
        who = (
            "MOSS" if use_moss else
            "QN" if use_qn else
            ("Gemini" if use_gemini else "Grok")
        )
'''
),
(
'''        def moss_worker():
            """t229u: 本机 ComfyUI 跑 moss_edit_3ref_api.json；每一场单独提交。"""
            from utility.sd_image_processor import generate_image_moss_edit
            n = len(jobs)
            for k, job in enumerate(jobs, 1):
                scene, prompt, images = job[0], job[1], job[2]
                if stop["flag"]:
                    failed.append(f"其余 {n - k + 1} 场：已停止")
                    break
                label = in_episode_label(scene, k)
                head = f"正在处理第 {k}/{n} 张（本集{label}，MOSS）"
                ui(lambda h=head: var.set(h))
                try:
                    img = generate_image_moss_edit(prompt, list(images), status=scene_status(head))
                    if img is None or not hasattr(img, "save"):
                        raise RuntimeError("没有拿到图")
                    ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{label}：{exc}")
''',
'''        def moss_worker():
            """t229u: 本机 ComfyUI 跑 moss_edit_3ref_api.json；每一场单独提交。"""
            from utility.sd_image_processor import generate_image_moss_edit
            n = len(jobs)
            for k, job in enumerate(jobs, 1):
                scene, prompt, images = job[0], job[1], job[2]
                if stop["flag"]:
                    failed.append(f"其余 {n - k + 1} 场：已停止")
                    break
                label = in_episode_label(scene, k)
                head = f"正在处理第 {k}/{n} 张（本集{label}，MOSS）"
                ui(lambda h=head: var.set(h))
                try:
                    img = generate_image_moss_edit(prompt, list(images), status=scene_status(head))
                    if img is None or not hasattr(img, "save"):
                        raise RuntimeError("没有拿到图")
                    ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{label}：{exc}")

        def qn_worker():
            """t234u: 本机 ComfyUI 跑 qwen_edit_3ref_api.json；每一场单独提交。"""
            from utility.sd_image_processor import generate_image_qwen_edit
            n = len(jobs)
            for k, job in enumerate(jobs, 1):
                scene, prompt, images = job[0], job[1], job[2]
                if stop["flag"]:
                    failed.append(f"其余 {n - k + 1} 场：已停止")
                    break
                label = in_episode_label(scene, k)
                head = f"正在处理第 {k}/{n} 张（本集{label}，QN）"
                ui(lambda h=head: var.set(h))
                try:
                    img = generate_image_qwen_edit(prompt, list(images), status=scene_status(head))
                    if img is None or not hasattr(img, "save"):
                        raise RuntimeError("没有拿到图")
                    ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{label}：{exc}")
'''
),
(
'''                if use_moss:
                    moss_worker()
                else:
                    with chrome_account.use(account):  # t129u: 选的 Chrome 账户
''',
'''                if use_moss:
                    moss_worker()
                elif use_qn:
                    qn_worker()
                else:
                    with chrome_account.use(account):  # t129u: 选的 Chrome 账户
'''
),
]
for old, new in repls:
    if old not in t:
        raise SystemExit('wf block missing:\n' + old[:120])
    t = t.replace(old, new, 1)
p.write_bytes(t.encode('utf-8'))
print('wf_prompt_flows OK')

# ---- llm_api.py ----
p = Path(r'D:\AIComposer\utility\llm_api.py')
t = p.read_text(encoding='utf-8')
repls = [
(
'''                # t229u: 图片可选 grok / gemini / moss
                return b if b in ("gemini", "moss") else "grok"
''',
'''                # t229u / t234u: 图片可选 grok / gemini / moss / qn
                return b if b in ("gemini", "moss", "qn") else "grok"
'''
),
(
'''                _bk_opts += (("moss", "MOSS"),)  # t229u: 本机 ComfyUI moss_edit_3ref
''',
'''                _bk_opts += (("moss", "MOSS"), ("qn", "QN"))  # t229u/t234u: 本机 ComfyUI
'''
),
(
'''                        use_gemini = video_backend == "gemini"  # t132u: 下面一行选的后端（初值来自 image_backend）
                        use_moss = video_backend == "moss"  # t229u: 本机 ComfyUI MOSS
                        who = "MOSS" if use_moss else ("Gemini" if use_gemini else "Grok Imagine")
''',
'''                        use_gemini = video_backend == "gemini"  # t132u: 下面一行选的后端（初值来自 image_backend）
                        use_moss = video_backend == "moss"  # t229u: 本机 ComfyUI MOSS
                        use_qn = video_backend == "qn"  # t234u: 本机 ComfyUI Qwen
                        who = (
                            "MOSS" if use_moss else
                            "QN" if use_qn else
                            ("Gemini" if use_gemini else "Grok Imagine")
                        )
'''
),
(
'''                        if use_moss:
                            from .sd_image_processor import generate_image_moss_edit
                            img = generate_image_moss_edit(prompt, list(image_paths), status=_cli_set_status)
''',
'''                        if use_moss:
                            from .sd_image_processor import generate_image_moss_edit
                            img = generate_image_moss_edit(prompt, list(image_paths), status=_cli_set_status)
                        elif use_qn:
                            from .sd_image_processor import generate_image_qwen_edit
                            img = generate_image_qwen_edit(prompt, list(image_paths), status=_cli_set_status)
'''
),
]
for old, new in repls:
    if old not in t:
        raise SystemExit('llm_api block missing:\n' + old[:160])
    t = t.replace(old, new, 1)

# Also: chrome account skip for qn in manual window if any moss-only checks nearby
# Search leftover patterns that need qn
p.write_bytes(t.encode('utf-8'))
print('llm_api OK')

# verify ask_llm no_account uses backend values from extra — qn included automatically
print('done patching')
