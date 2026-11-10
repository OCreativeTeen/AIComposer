# PROMPT TIP: name refs as "Picture 2" / "Picture 3" (base = Picture 1) and restate
# key attributes (ethnicity, hair, clothing colour) in English.
# Default turbo path: Lightning 4-step LoRA, steps 4, cfg 1.0, euler/simple.
#!/usr/bin/env python3
"""
ComfyUI API 客户端：发送 1 张底图 + 最多 2 张人物肖像参考 + 文字提示词，取回生成图片。
适配：Qwen-Image-Edit-2509 + Lightning 4-step LoRA（qwen_edit_3ref_api.json，TextEncodeQwenImageEditPlus）。

用法：
  python qwen_edit_api_client.py --base scene.png --refs alice.png bob.png \
      --prompt "Place the person from Picture 2 and the person from Picture 3 into the living room of Picture 1..." \
      --out D:\\AI_MEDIA\\working\\qwen_edit_result.png --seed 42

依赖的 ComfyUI 原生接口：
  POST /upload/image
  POST /prompt
  GET  /history/{id}
  GET  /view?filename=&subfolder=&type=
"""
import argparse, copy, json, os, random, sys, time, uuid
import requests

CONFIG = {
    "server": "http://192.168.1.227:8188",
    "workflow_api_path": "qwen_edit_3ref_api.json",

    "base_image_node": "8",
    # image2 / image3 on TextEncodeQwenImageEditPlus (image1 is the scaled base)
    "ref_image_nodes": ["50", "51"],
    "encoder_nodes": ["39", "36"],
    "encoder_ref_fields": ["image2", "image3"],

    "positive_text_node": "39",
    "positive_text_field": "prompt",
    "negative_text_node": "36",
    "negative_text_field": "prompt",

    "ksampler_node": "37",
    "save_node": "9",

    "poll_interval_sec": 2,
    "timeout_sec": 900,
}


def upload_image(server, path):
    with open(path, "rb") as f:
        r = requests.post(f"{server}/upload/image",
                          files={"image": (os.path.basename(path), f, "application/octet-stream")},
                          data={"type": "input", "overwrite": "true"}, timeout=120)
    r.raise_for_status()
    j = r.json()
    return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]


def build_prompt(wf, base_name, ref_names, text, seed, steps=None, cfg=None, negative=None):
    wf = copy.deepcopy(wf)
    c = CONFIG

    def node(nid):
        if nid not in wf:
            sys.exit(f"[错误] 节点 ID {nid!r} 不在 workflow JSON 中，请检查 CONFIG")
        return wf[nid]

    node(c["base_image_node"])["inputs"]["image"] = base_name
    if len(ref_names) > len(c["ref_image_nodes"]):
        sys.exit(f"[错误] Qwen-Image-Edit-2509 Plus 最多 1 张底图 + 2 张参考，收到 {len(ref_names)} 张参考")
    for nid, name in zip(c["ref_image_nodes"], ref_names):
        node(nid)["inputs"]["image"] = name
    for i in range(len(ref_names), len(c["ref_image_nodes"])):
        wf.pop(c["ref_image_nodes"][i], None)
        field = c["encoder_ref_fields"][i]
        for e in c["encoder_nodes"]:
            node(e)["inputs"].pop(field, None)

    pn = node(c["positive_text_node"])
    pn["inputs"][c["positive_text_field"]] = text
    if negative is not None and c.get("negative_text_node"):
        node(c["negative_text_node"])["inputs"][c["negative_text_field"]] = negative

    if c.get("ksampler_node"):
        ks = node(c["ksampler_node"])["inputs"]
        if "seed" in ks:
            ks["seed"] = seed
        elif "noise_seed" in ks:
            ks["noise_seed"] = seed
        if steps is not None:
            ks["steps"] = steps
        if cfg is not None:
            ks["cfg"] = cfg
    return wf


def queue(server, prompt, client_id):
    r = requests.post(f"{server}/prompt", json={"prompt": prompt, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"[错误] /prompt 返回 {r.status_code}: {r.text}")
    return r.json()["prompt_id"]


def wait_history(server, pid):
    t0 = time.time()
    while time.time() - t0 < CONFIG["timeout_sec"]:
        r = requests.get(f"{server}/history/{pid}", timeout=30)
        if r.ok and pid in r.json():
            h = r.json()[pid]
            st = h.get("status", {})
            if st.get("status_str") == "error":
                sys.exit(f"[错误] 执行失败: {json.dumps(st.get('messages'), ensure_ascii=False)[:2000]}")
            if st.get("completed", True):
                return h
        time.sleep(CONFIG["poll_interval_sec"])
    sys.exit("[错误] 等待超时")


def download_outputs(server, hist, out_path):
    outs = hist["outputs"]
    nodes = [CONFIG["save_node"]] if CONFIG.get("save_node") and CONFIG["save_node"] in outs else list(outs)
    saved = []
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    for nid in nodes:
        for img in outs[nid].get("images", []):
            r = requests.get(f"{server}/view", params={
                "filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}, timeout=120)
            r.raise_for_status()
            root, ext = os.path.splitext(out_path)
            p = out_path if not saved else f"{root}_{len(saved)}{ext or '.png'}"
            with open(p, "wb") as f:
                f.write(r.content)
            saved.append(p)
    return saved


def default_out_path():
    win = r"D:\AI_MEDIA\working\qwen_edit_result.png"
    if os.name == "nt" and os.path.isdir(r"D:\AI_MEDIA\working"):
        return win
    return "qwen_edit_result.png"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Qwen-Image-Edit-2509 ComfyUI API client (Lightning turbo: 4 steps / CFG 1.0)")
    ap.add_argument("--base", required=True, help="底图/场景图 (Picture 1)")
    ap.add_argument("--refs", nargs="*", default=[], help="人物肖像参考图（最多 2 张 = Picture 2/3）")
    ap.add_argument("--prompt", required=True, help="编辑指令（建议英文，引用 Picture 1/2/3）")
    ap.add_argument("--negative", default=None, help="反向提示词（默认用工作流里的）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None, help="覆盖采样步数（默认工作流 Lightning 4 步）")
    ap.add_argument("--cfg", type=float, default=None, help="覆盖 CFG（默认工作流 Lightning 1.0）")
    ap.add_argument("--server", default=None)
    ap.add_argument("--workflow", default=None)
    a = ap.parse_args()

    server = a.server or CONFIG["server"]
    wf_path = a.workflow or CONFIG["workflow_api_path"]
    if not os.path.isabs(wf_path) and not os.path.exists(wf_path):
        here = os.path.dirname(os.path.abspath(__file__))
        alt = os.path.join(here, os.path.basename(wf_path))
        if os.path.exists(alt):
            wf_path = alt
    wf = json.load(open(wf_path, encoding="utf-8"))
    if "nodes" in wf:
        sys.exit("[错误] 这是 UI 格式 JSON，需要 API 格式（节点 ID 为键，含 class_type）")

    base_name = upload_image(server, a.base)
    ref_names = [upload_image(server, p) for p in a.refs]
    seed = a.seed if a.seed is not None else random.randint(0, 2**48)
    prompt = build_prompt(wf, base_name, ref_names, a.prompt, seed, steps=a.steps, cfg=a.cfg, negative=a.negative)

    pid = queue(server, prompt, str(uuid.uuid4()))
    print(f"已提交 prompt_id={pid} seed={seed} refs={len(ref_names)}，等待生成…")
    hist = wait_history(server, pid)
    files = download_outputs(server, hist, a.out or default_out_path())
    print("完成：", files)


if __name__ == "__main__":
    main()
