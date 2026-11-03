"""t190u: MiniMax 双机（t194u: 5070Ti @ .36 + 5060 @ .30）。

单场「提交」：轮流用两台，上次用过的那台排后面；挑中的那台忙（/queue 里有任务）或连不上就换另一台，
都忙就挑排队最少的。全集提交：每台能连上的机器一个工人，从同一个队列里拿场景，先做完的接下一场；
生成、下载在工人线程里，导入（原声 · Clip · 替换）通过 post 回主线程、一场一场地做。
"""
import os
import threading
import time
from collections import deque

import requests

import config

DUAL_KEY = "minimax_dual"
_PREF_LAST = "minimax_dual_last"
_pick_lock = threading.Lock()


def dual_servers() -> list:
    return list(config.MINIMAX_VARIANTS)


def server_label(key: str) -> str:
    try:
        return config.MINIMAX_VARIANTS[key]["label"]
    except Exception:  # noqa: BLE001
        return str(key)


def comfy_queue_load(url: str, timeout: float = 4.0):
    """GET /queue → 正在跑 + 排队的任务数；连不上返回 None。"""
    try:
        r = requests.get(str(url).rstrip("/") + "/queue", timeout=timeout)
        r.raise_for_status()
        d = r.json() or {}
        return len(d.get("queue_running") or []) + len(d.get("queue_pending") or [])
    except Exception:  # noqa: BLE001
        return None


def probe_servers(keys=None, timeout: float = 4.0) -> dict:
    """两台一起查 /queue：{key: 任务数 或 None（连不上）}。"""
    keys = list(keys or dual_servers())
    out = {}

    def one(k):
        out[k] = comfy_queue_load(config.minimax_variant(k)["url"], timeout)

    ts = [threading.Thread(target=one, args=(k,), daemon=True) for k in keys]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout + 2)
    return {k: out.get(k) for k in keys}


def choose_server(loads: dict, last: str = "") -> str:
    """上次没用的那台优先；它忙就用空闲的；都忙挑任务最少的；都连不上返回 ''。"""
    up = [k for k, v in loads.items() if v is not None]
    if not up:
        return ""
    order = sorted(up, key=lambda k: k == last)
    for k in order:
        if loads[k] == 0:
            return k
    return min(order, key=lambda k: loads[k])


def pick_dual_server(status=None) -> str:
    with _pick_lock:
        try:
            last = config.minimax_variant_key(config.load_yt_tools_prefs().get(_PREF_LAST) or "")  # t194u: 旧键迁移
        except Exception:  # noqa: BLE001
            last = ""
        loads = probe_servers()
        key = choose_server(loads, last)
        if not key:
            raise RuntimeError("MiniMax 双机：两台 ComfyUI 都连不上（"
                               + "、".join(server_label(k) for k in loads) + "）")
        try:
            config.save_yt_tools_prefs({_PREF_LAST: key})
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 双机上次用的机器没有记下：{exc}")
        msg = "MiniMax 双机：用 " + server_label(key) + "（" + "，".join(
            f"{server_label(k)} {'连不上' if v is None else f'{v} 个任务'}" for k, v in loads.items()) + "）"
        print("🎬 " + msg)
        if callable(status):
            status(msg)
        return key


def minimax_generate(prompt, image_path, image_paths, extra, dest_dir, backend, status=None, server_key=None) -> str:
    """t190u: 原来 llm_api 里的 MiniMax 分支（单场提交和双机全集共用）。返回 mp4 路径。"""
    from utility import sd_image_processor as _sdp

    extra = dict(extra or {})
    _st = status if callable(status) else (lambda m: print("🎬 " + str(m)))
    if server_key:
        key = server_key
    elif str(backend or "").strip().lower() == DUAL_KEY:
        key = pick_dual_server(_st)
    else:
        key = config.minimax_variant_key(backend) or config.MINIMAX_DEFAULT_VARIANT
    v = config.minimax_variant(key)
    _secs = float(_sdp.minimax_snap_seconds(extra.get("duration") or "10s"))  # t200u: 7 / 10 / 12（6→7，15→12）
    _imgs = [p for p in (image_paths or []) if p] if isinstance(image_paths, (list, tuple)) else []
    if not image_path and _imgs:
        image_path = _imgs[0]
    _last = _imgs[1] if extra.get("frames") == "two" and len(_imgs) > 1 else None
    # t216u: 「参考图工作流（人物肖像）」：换 R2V 工作流，起始图后面的图是人物肖像（最多 8 张）
    _refs = None
    _wf_choice = str(extra.get("h3_workflow") or "")
    if _sdp.minimax_workflow_for(_wf_choice):  # t228u: r2v / r2v_fast8（FastH3 8 步）
        v = dict(v)
        v["workflow"] = _sdp.minimax_workflow_for(_wf_choice)
        if extra.get("frames") != "two":
            _n = int(extra.get("portrait_refs") or 0)
            _refs = list(_imgs[1:1 + _n])[: _sdp.R2V_MAX_REFS - 1]
    _audio = str(extra.get("scene_audio") or "").strip() or None
    _adur = _sdp.h3_audio_seconds(_audio) if _audio and os.path.isfile(_audio) else 0.0
    _w, _h, _why = _sdp.minimax_size_for(str(extra.get("orientation") or "landscape"), _secs, bool(_audio), _adur)
    _vsecs = _sdp.minimax_audio_video_seconds(_adur) if _audio else _secs
    _st(f"CLI自动：{v['label']}（ComfyUI，实际发送=窗口里的 H3 格式提示词）生成视频 {_w}×{_h}（{_why}） "
        + f"{_vsecs:g}秒" + ("（跟场景音频）" if _audio else "") + ("，含结束图" if _last else "")
        + (f"，语速档 {float(extra['speech_speed']):g}（说快，导入时放慢）" if float(extra.get("speech_speed") or 1) < 0.999 else "")
        + " …")
    _dest = dest_dir or os.path.join(os.path.expanduser("~"), "Downloads")
    _name = time.strftime("minimax_h3_%Y%m%d_%H%M%S") + "_" + key.replace("minimax_", "") + ".mp4"
    if _audio and _adur > _sdp.MINIMAX_MAX_SECONDS:
        # t201u: 音频 > 12 秒：同一台机器上分段依次生成、裁准、接起来、换原声，返回一个 mp4 给原来的导入
        from utility import minimax_segments as _seg

        def _one(img, p, secs, aud, last, out, st):
            return _generate_one(_sdp, img, p, secs, _w, _h, out, v, st, aud, last, refs=_refs)

        return _seg.run_segmented(
            gen_one=_one, image_path=image_path, prompt=prompt, audio_path=_audio, audio_seconds=_adur,
            dest_dir=_dest, base_name=_name[:-4], last_image_path=_last, status=_st, is_unreachable=is_unreachable,
            timeline=extra.get("speaker_timeline"))  # t150u
    return _generate_one(_sdp, image_path, prompt, _secs, _w, _h, os.path.join(_dest, _name), v, _st, _audio, _last,
                         refs=_refs)


def _generate_one(_sdp, image_path, prompt, secs, w, h, out_path, v, status, audio, last, refs=None):
    """一次 ComfyUI 生成（离线测试里换成假的）。refs: t216u 参考图工作流的人物肖像。"""
    return _sdp.generate_video_comfy(
        image_path, prompt, secs, w, h,
        output_path=out_path,
        server=v["url"], status=status, workflow_path=v["workflow"],
        audio_path=audio, last_image_path=last, ref_image_paths=refs,
    )


def is_unreachable(exc) -> bool:
    """连不上 / 超时（换另一台整场重来），其它错误同一台再试一次。"""
    e = exc
    while e is not None:
        if isinstance(e, (requests.ConnectionError, requests.Timeout)):
            return True
        e = e.__cause__ or e.__context__
    return False


class DualRunner:
    """全集双机调度。job = {"i", "label", "scene", "prompt", "images", "extra"}。

    generate(job, key, status) → 路径（工人线程里跑）；post(fn) 把 fn 放回主线程；
    importer(scene, path, cb(ok, why)) 在主线程里调、一次只导一场；log(msg) / finish(results) 在主线程里调。
    """

    def __init__(self, servers, generate, post, importer, log, finish, should_stop=None, retry=True):
        self.servers = list(servers)
        self.generate, self.post, self.importer = generate, post, importer
        self.log, self.finish = log, finish
        self.should_stop = should_stop or (lambda: False)
        self.retry = retry
        self.cv = threading.Condition()
        self.q = deque()
        self.closed = False
        self.busy = 0
        self.alive = 0
        self.results = {}
        self._imp_q = deque()
        self._imp_busy = False

    # ---- 主线程这边 ----
    def add(self, job: dict) -> None:
        job.setdefault("tried", [])
        with self.cv:
            self.q.append(job)
            self.cv.notify_all()

    def fail(self, job: dict, why: str) -> None:
        with self.cv:
            self.results[job["i"]] = {"label": job.get("label", ""), "server": "", "ok": False, "msg": why, "path": ""}

    def close(self) -> None:
        with self.cv:
            self.closed = True
            self.cv.notify_all()

    def start(self) -> None:
        self.alive = len(self.servers)
        for k in self.servers:
            threading.Thread(target=self._work, args=(k,), daemon=True, name=f"minimax-{k}").start()

    def _import(self, job, path, cb) -> None:
        self._imp_q.append((job, path, cb))
        self._next_import()

    def _next_import(self) -> None:
        if self._imp_busy or not self._imp_q:
            return
        job, path, cb = self._imp_q.popleft()
        self._imp_busy = True
        self.log(f"{job['label']}：视频已下载，自动导入（原声 · Clip · 替换）…")
        state = {"done": False}

        def done(ok, why=""):
            if state["done"]:
                return
            state["done"] = True
            cb(ok, why)

            def nxt():
                self._imp_busy = False
                self._next_import()
            self.post(nxt)

        try:
            self.importer(job["scene"], path, done)
        except Exception as exc:  # noqa: BLE001
            done(False, f"导入出错：{exc}")

    # ---- 工人线程 ----
    def _take(self, key):
        with self.cv:
            while True:
                for j in list(self.q):
                    if key not in j["tried"]:
                        self.q.remove(j)
                        self.busy += 1
                        return j
                if self.closed and not self.q and self.busy == 0:
                    return None
                self.cv.wait(0.5)

    def _work(self, key) -> None:
        from utility import minimax_segments as _seg

        _seg.set_should_stop(self.should_stop)  # t201u: 分段时每段开始前看一下停止
        try:
            while True:
                j = self._take(key)
                if j is None:
                    break
                try:
                    self._do(j, key)
                except Exception as exc:  # noqa: BLE001
                    self._result(j, key, False, f"出错：{exc}")
                finally:
                    with self.cv:
                        self.busy -= 1
                        self.cv.notify_all()
        finally:
            with self.cv:
                self.alive -= 1
                last = self.alive == 0
            if last:
                self.post(lambda: self.finish(self.ordered_results()))

    def _say(self, msg) -> None:
        self.post(lambda m=msg: self.log(m))

    def _result(self, j, key, ok, msg, path="") -> None:
        with self.cv:
            self.results[j["i"]] = {"label": j.get("label", ""), "server": server_label(key) if key else "",
                                    "ok": ok, "msg": msg, "path": path, "tried": [server_label(k) for k in j["tried"]]}

    def _do(self, j, key) -> None:
        lab, sv = j["label"], server_label(key)
        if self.should_stop():
            self._result(j, key, False, "已停止，没有提交")
            return
        self._say(f"{lab} → {sv}：生成中…")
        try:
            path = self.generate(j, key, lambda m, _l=lab, _s=sv: self._say(f"{_l} @ {_s}：{m}"))
            if not (path and os.path.isfile(str(path))):
                raise RuntimeError("没有拿到视频文件")
        except Exception as exc:  # noqa: BLE001
            j["tried"].append(key)
            others = [k for k in self.servers if k not in j["tried"]]
            if self.retry and others and not self.should_stop():
                self._say(f"⚠️ {lab} 在 {sv} 失败（{exc}），换 {server_label(others[0])} 再试一次")
                with self.cv:
                    self.q.appendleft(j)
                    self.cv.notify_all()
                return
            self._say(f"❌ {lab} 在 {sv} 失败：{exc}")
            self._result(j, key, False, f"生成失败：{exc}")
            return
        ev = threading.Event()
        box = {}

        def cb(ok, why=""):
            box.update(ok=bool(ok), why=str(why or ""))
            ev.set()

        self.post(lambda: self._import(j, path, cb))
        if not ev.wait(timeout=1800):
            box.update(ok=False, why="导入超时")
        ok = box.get("ok", False)
        self._say(f"{'✅' if ok else '❌'} {lab} @ {sv}：" + ("已导入" if ok else f"导入失败：{box.get('why')}"))
        self._result(j, key, ok, "已导入" if ok else f"导入失败：{box.get('why')}", str(path))

    def ordered_results(self) -> list:
        with self.cv:
            return [dict(self.results[i], i=i) for i in sorted(self.results)]
