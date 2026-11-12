"""PromptFlowsMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import json
import config
import config_prompt
from project_manager import save_project_config
import project_manager
from utility.file_util import show_auto_close_popup


class PromptFlowsMixin:
    def _project_cover_and_slide(self) -> tuple[str, str]:
        from gui.downloader import _find_gen_video_slide_for_row, _find_gen_video_webp_for_row

        pc = project_manager.PROJECT_CONFIG or {}
        row = self._current_feature_row()
        cover = ""
        slide = ""
        for src in (pc, row):
            if not isinstance(src, dict):
                continue
            stored_cover = project_manager.get_primary_cover_image(src)
            from utility.program_media import get_primary_program_media

            stored_slide = get_primary_program_media(src, "slides")
            if not cover and stored_cover:
                cover = stored_cover
            if not slide and stored_slide:
                slide = stored_slide
        if not cover:
            cover = _find_gen_video_webp_for_row(row) or ""
        if not slide:
            slide = _find_gen_video_slide_for_row(row) or ""
        return cover, slide

    def _cover_prompt_context(self) -> tuple[object | None, dict, str, str]:
        mgr = getattr(self, "youtube_gui", None)
        vd = self._current_feature_row()
        cover, slide = self._project_cover_and_slide()
        if cover:
            vd["cover_image"] = cover
        if slide and not isinstance(vd.get("slide"), list):
            vd["slide"] = slide
        sc = vd.get("scene_content") or []
        story_raw = json.dumps(sc, ensure_ascii=False, indent=2) if isinstance(sc, list) and sc else ""
        ch = (getattr(self.workflow, "channel", None) or "").strip()
        ch_path = config.get_channel_path(config.get_channel_id(ch)) if ch else ""
        if mgr is not None:
            ch_path = ch_path or getattr(mgr, "channel_path", "")
        return mgr, vd, story_raw, ch_path

    def _open_picture_prompt_flow(self) -> None:
        """图片修改：画风改变 + 叙事风格，再在手动窗口里拷当前图和提示词；也可以本集逐场自动处理。"""
        from gui.picture_prompt_dialog import open_picture_prompt_dialog

        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("图片修改", "没有当前场景", parent=self.root)
            return

        def current_scene():
            self.update_current_scene()
            if not self.workflow:
                return None
            return self.workflow.get_scene_by_index(self.current_scene_index)

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or ""
            )

        def get_place() -> tuple:
            return (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            )

        def save_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("picture_prompt") == choice:
                return
            cfg["picture_prompt"] = choice
            save_project_config(parent=self.root)

        def open_manual(prompt: str, images: list[str], backend: str = "grok", account: str = "", comfy=None,
                        upscale=None) -> None:
            def _on_image_response(pil_img):
                if upscale:  # t366u: 提高分辨率：先对齐到目标尺寸（Lanczos；比例变了居中裁），按这个尺寸写回
                    from utility.image_upscale import finish_upscale

                    if pil_img is not None and hasattr(pil_img, "size"):  # t377u: + 颜色统计对齐原图
                        pil_img = finish_upscale(pil_img, upscale, images[0] if images else None)
                    self._replace_current_clip_image_from_pil(pil_img, exact_size=tuple(upscale))
                    return
                self._replace_current_clip_image_from_pil(pil_img)

            # t229u / t234u: grok（默认）/ gemini / moss / qn（本机 ComfyUI）
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
            prompt = config_prompt.style_lock_first(prompt)  # t373u: 画风锁定永远是第一行
            if isinstance(comfy, dict) and comfy.get("comfy") and b in ("moss", "qn"):
                # t356u: ComfyUI 专用提示已经写好：带上反向提示词和输出画布，送出时不再改写
                extra["comfy_backend"] = b
                extra["comfy_negative"] = comfy.get("negative") or ""
                if comfy.get("size"):
                    extra["comfy_size"] = tuple(comfy["size"])
                if comfy.get("init_denoise") is not None:  # t377u: 提高分辨率 = 从原图开始采样（低 denoise）
                    extra["comfy_init_denoise"] = comfy["init_denoise"]
            self.llm_api.show_manual_window(
                prompt, "", images=images, on_image_response=_on_image_response,
                auto_cli=True, extra=extra,
            )

        def batch_scenes() -> tuple:
            """从当前场景到本集结束（scenes.json 顺序）。返回 (场景列表, 当前是本集第 k 场, 本集共 m 场)；前面的场不动。"""
            self.update_current_scene()
            cur = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
            if not isinstance(cur, dict):
                return [], 0, 0
            story = [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]
            k = next((i for i, s in enumerate(story) if s is cur), 0)
            return story[k:], k + 1, len(story)

        def _cover_sources() -> tuple:
            wf = getattr(self, "workflow", None)
            row = None
            try:
                row = self._current_feature_row()
            except Exception:
                row = None
            return (
                getattr(wf, "cover_seeded_path", "") if wf else "",
                getattr(wf, "_seed_cover_override", "") if wf else "",
                project_manager.PROJECT_CONFIG,
                row if isinstance(row, dict) else None,
            )

        def get_project_cover() -> str:
            from utility.scene_image_slots import resolve_project_cover_image

            seeded, override, pc, row = _cover_sources()
            return resolve_project_cover_image(
                cover_seeded_path=seeded,
                cover_override=override,
                project_config=pc,
                item=row,
            )

        def get_project_covers() -> list:
            from utility.scene_image_slots import list_project_cover_images

            seeded, override, pc, row = _cover_sources()
            return list_project_cover_images(
                cover_seeded_path=seeded,
                cover_override=override,
                project_config=pc,
                item=row,
            )

        open_picture_prompt_dialog(
            self.root,
            self._nb_picture_btn,
            batch_scenes=batch_scenes,
            run_batch=self._run_picture_batch,
            get_step_no=self._current_cover_step,
            get_project_cover=get_project_cover,
            get_project_covers=get_project_covers,
            get_scene=current_scene,
            get_style=get_style,
            get_place=get_place,
            open_manual=open_manual,
            host_narrator=project_manager.project_narrator(),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("picture_prompt"),
            save_choice=save_choice,
            actor_avatar_dir=os.path.join(config.get_project_path(self.get_pid()), "avatar"),
            review_portrait=self._portrait_review_from_worker,
        )

    def _auto_import_scene_video(self, scene: dict, path: str, on_done) -> None:
        """t173u / t179u: 全集提交：不开窗口，做和手动「导入视频 → 原声 → Clip → 替换」一模一样的事。

        参数取刚打开的导入视频对话框、选中这个文件、什么都不动时「替换」交出去的值：
        区间 = default_video_range（终点吸到最后一帧起点）、速度 1.0、音量 1、不淡变、混音 50%、
        先用同一个 _build_volume_adjusted_mp4_wav_pair 做裁剪对，再交给同一个 _apply_editor_pick(stage_download=True)。
        完成后 on_done(ok, 原因)。
        """
        import threading

        from gui.mp4_pick_preview_dialog import default_video_range

        def fail(why: str) -> None:
            print(f"⚠️ 全集提交自动导入失败：{why}")
            on_done(False, why)

        if not (isinstance(scene, dict) and path and os.path.isfile(path)):
            fail("视频文件不在了")
            return
        folder = os.path.dirname(os.path.abspath(path))
        try:
            same = os.path.normcase(folder) == os.path.normcase(os.path.abspath(self._project_input_dir("input_video")))
        except Exception:  # noqa: BLE001
            same = False

        rec = scene.get("video_speech_speed")
        if isinstance(rec, dict) and not rec.get("file"):
            rec["file"] = os.path.basename(path)  # t151u: 这一场的语速档只给这个文件
        config_prompt.attach_video_prompt_file(scene, path)  # t156u
        spd = config_prompt.recorded_speech_speed(scene, path) or 1.0

        def build_pair() -> None:
            try:
                start, end = default_video_range(path)
                pair = self._build_volume_adjusted_mp4_wav_pair(path, 1.0, start=start, end=end, speed=spd)
                err = ""
                print(f"🎚️ 全集提交自动导入：区间 {start:.3f}–{end:.3f} 秒，速度 {spd:g}"
                      + ("（生成时说快了，按语速档放慢）" if spd < 0.999 else "") + "，音量 1 倍")
            except Exception as exc:  # noqa: BLE001
                pair, err = None, f"裁剪失败：{exc}"
            self.root.after(0, lambda: stage(pair, err))

        def stage(pair, err: str) -> None:
            if err or not pair:
                fail(err or "裁剪失败")
                return
            mp4, wav = pair
            for i, sc in enumerate(self.workflow.scenes or []):  # 手动导入写的是当前场景
                if sc is scene:
                    self.current_scene_index = i
                    break
            pick = {
                "filename": os.path.basename(path), "mp4": mp4, "wav": wav, "action": "replace",
                "radio": "keep", "mix_volume": 0.5, "source": "project" if same else "download",
                "folder": folder, "dest": "clip", "audio": None,
                "video_fade_in": 0.0, "video_fade_out": 0.0, "audio_fade": False,
            }
            try:
                self._apply_editor_pick(pick, stage_download=True, on_done=on_done)
            except Exception as exc:  # noqa: BLE001
                fail(f"导入失败：{exc}")

        threading.Thread(target=build_pair, daemon=True).start()

    # ---- t370u: 生场视频动态分节（<Ns> / <s>），见 utility/video_segments.py ----
    def _video_segment_count(self, scene) -> int:
        from utility.speaking_marks import speaking_segment_count

        return speaking_segment_count(scene.get("speaking") or "") if isinstance(scene, dict) else 0

    def _split_video_segment(self, scene):
        """第 1 节克隆成新场景插在前面（只留这一节的讲话；场景音频按时间轴切开），返回 token；不能分返回 None。"""
        from project_manager import refresh_scene_media
        from utility import video_segments as vs

        wf = self.workflow
        scenes = getattr(wf, "scenes", None) if wf else None
        if not isinstance(scenes, list) or not isinstance(scene, dict):
            return None
        try:  # 先把输入框里还没存的改动写回这一场，再按它的讲话分节
            self.update_current_scene()
        except Exception:  # noqa: BLE001
            pass
        ap = wf.ffmpeg_audio_processor

        def cut_audio(path, start, length):
            return ap.audio_cut_fade(path, float(start), float(length), 0, 0)

        def store(sc, key, ext, path):
            refresh_scene_media(sc, key, ext, path)

        tok = vs.split_first_segment(
            scenes, scene, next_id=vs.new_scene_id(scenes), cut_audio=cut_audio,
            audio_seconds=lambda p: ap.get_duration(p), store_media=store,
        )
        if not tok:
            return None
        from utility.last_frame_chain import mark_segment_chain_pending

        mark_segment_chain_pending(tok["clone"])  # t386u: 这一节的末帧由 _chain_video_segment 增强，导入时不重复
        print(f"✂️ 分节：第 1/{tok['segments']} 节拆成新场景 id={tok['clone'].get('id')}（插在前面），"
              f"分界 {tok['cut']} 秒（{'时间轴' if tok['cut_source'] == 'timing' else '按字数估'}"
              f"{'，场景音频已切开' if tok['audio_cut'] else ''}）")
        try:
            wf.touch_episode_media(wf.scene_group(scene))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._rebuild_monologue_preview_clips(tok["clone"], scene)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 分节预览片没有重做：{exc}")
        for i, sc in enumerate(wf.scenes or []):  # 当前场 = 克隆；输入框马上换成克隆，旧讲话不会写回原场景
            if sc is tok["clone"]:
                self.current_scene_index = i
                break
        try:
            wf.save_scenes_to_json()
            refresh_now = getattr(self, "_refresh_gui_scenes_impl", None)
            (refresh_now if callable(refresh_now) else self.refresh_gui_scenes)()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 分节后保存 / 刷新失败：{exc}")
        return tok

    def _undo_video_segment(self, token) -> None:
        from utility import video_segments as vs

        from utility.last_frame_chain import clear_segment_chain_pending

        clear_segment_chain_pending((token or {}).get("clone"))  # t386u
        wf = self.workflow
        if not wf:
            return
        vs.undo_first_segment(getattr(wf, "scenes", None), token)
        scene = (token or {}).get("scene")
        for i, sc in enumerate(wf.scenes or []):
            if sc is scene:
                self.current_scene_index = i
                break
        try:
            wf.save_scenes_to_json()
            self.refresh_gui_scenes()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 分节退回后保存 / 刷新失败：{exc}")

    def _chain_video_segment(self, token, style, status, done, enhance="qn", account="") -> None:  # t395u
        """克隆那一节的视频末帧 → 尾帧增强（t376u：none / moss / qn / grok，保持原画风 + 项目画风）
        → 原场景 zero_image_last。后台线程跑；不增强或增强失败就用原末帧（缩到项目尺寸）。
        完成后在主线程 ``done(起始图, 是否增强, 说明)``。"""
        import threading

        from utility import video_segments as vs
        from utility.file_util import get_file_path
        from utility.scene_image_slots import write_chained_next_zero_image_last

        clone, scene = token["clone"], token["scene"]
        src = get_file_path(clone, "clip") or clone.get("clip") or ""
        fp = self.workflow.ffmpeg_processor

        def work() -> None:
            path, enhanced, note = "", False, ""
            try:
                frame = fp.extract_frame(src, False) if src and os.path.isfile(src) else None
                if not frame or not os.path.isfile(frame):
                    raise RuntimeError("这一节视频的末帧没取出来")
                path, enhanced, note = vs.enhance_segment_last_frame(
                    frame, mode=enhance, style=style, status=status, account=account)
                if not enhanced:
                    path = fp.resize_image_smart(frame) or frame
            except Exception as exc:  # noqa: BLE001
                path, note = "", str(exc)
            self.root.after(0, lambda: finish(path, enhanced, note))

        def finish(path, enhanced, note) -> None:
            from utility.last_frame_chain import clear_segment_chain_pending

            clear_segment_chain_pending(clone)  # t386u: 分节接完了；以后再导入这一场照常增强
            written = ""
            if path and os.path.isfile(path):
                try:
                    written = write_chained_next_zero_image_last(scene, path)
                    print(f"🔗 分节：{('「' + vs.last_frame_enhance_label(enhance) + '」增强后的') if enhanced else '原'}"
                          "末帧写进原场景 zero_image_last，作为下一节的起始图")
                except Exception as exc:  # noqa: BLE001
                    note = f"{note}；写 zero_image_last 失败：{exc}".strip("；")
            if not written:  # 导入时已经把原末帧接到下一场（= 原场景）的 zero_image_last
                written = str(scene.get("zero_image_last") or "")
                enhanced = False
            try:
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 分节接末帧后保存 / 刷新失败：{exc}")
            done(written, enhanced, note)

        threading.Thread(target=work, daemon=True).start()

    def _current_cover_step(self) -> int:
        """Original cover-panel number for the current scene (not the expanded list index)."""
        from utility.speaking_marks import ensure_cover_steps, scene_cover_step

        cur = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not isinstance(cur, dict):
            return 0
        story = [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]
        ensure_cover_steps(story or [cur])
        return int(scene_cover_step(cur) or 0)

    def _maybe_auto_extract_steps_from_cover(self, tries: int = 0) -> None:
        """t172u: 新项目从预览导入了封面、本集 2-6 场：按「图片修改」的提取第 N 步，逐场从封面画出这一场的图。

        选项固定：叙事风格 = 提取第 N 步，说明文字 = 关键字作背景，画风改变 = 保持画风，交给 LLM 的图 = 封面。
        提示词用图片修改同一个 build_step_image_clipbody；出图、写回 clip_image 走 _run_picture_batch（可停止）。
        条件不满足就安静跳过。
        """
        from gui.picture_prompt_dialog import PICTURE_SUBMIT_PREF, _project_video_size, ask_llm_and_account

        wf = getattr(self, "workflow", None)
        cover = (getattr(wf, "cover_seeded_path", "") or "") if wf else ""
        if cover and getattr(self, "_clip_video_worker_busy", False) and tries < 30:  # t206u: 等生场视频空闲
            self.root.after(2000, lambda: self._maybe_auto_extract_steps_from_cover(tries + 1))
            return
        if wf is not None:
            wf.cover_seeded_path = ""  # 只做一次
        if not cover or not os.path.isfile(cover):
            return
        scenes = [s for s in (wf.scenes or []) if isinstance(s, dict)]
        story = [s for s in wf.scenes_in_story(scenes[0]) if isinstance(s, dict)] if scenes else []
        if len(story) != len(scenes):  # 不止一集：不自动做
            return
        from utility.speaking_marks import ensure_cover_steps, unique_cover_step_count

        ensure_cover_steps(story)
        n = unique_cover_step_count(story)
        if not (2 <= n <= 6):
            return
        picked = None
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
                title=f"从封面提取每一场的图（Grok · 共 {n} 步，取消 = 不做）",
                fixed_backend="grok",
            )
        if not picked:
            print("ℹ️ 从封面逐场提取：取消，没有做。")
            print("ℹ️ 自动提取人物肖像：封面提取已取消，场景图没有生成，人物肖像也没有做。")
            return
        backend, account = picked
        pc = project_manager.PROJECT_CONFIG or {}
        style = (
            (self.scene_visual_style.get() or "").strip()
            or (pc.get("visual_style") or "").strip()
            or (project_manager.LAST_VISUAL_STYLE or "").strip()
        )
        aspect = config_prompt.output_aspect_line(_project_video_size())
        jobs = []
        from utility.scene_image_slots import cover_extract_source
        from utility.speaking_marks import iter_cover_extract_targets

        for sc, k in iter_cover_extract_targets(story):
            body = config_prompt.build_step_image_clipbody(
                k, visual_style=style, keep_style=True, caption="keywords", extract_only=True, fyi="",
            )
            try:  # 优先用冻结的封面原图 zero_image_last，避免已改过的 clip 当输入
                src = cover_extract_source(sc, cover)
            except Exception:  # noqa: BLE001
                src = cover if cover and os.path.isfile(cover) else ""
            if backend == "gemini":  # 同一个 Gemini 对话：比例行由批量那边放
                jobs.append((sc, body, [src], {"aspect": aspect, "actors": [], "base": src}))
            else:
                jobs.append((sc, (aspect + "\n\n" + body) if aspect else body, [src],
                             {"aspect": "", "actors": [], "base": src}))
        print(f"🖼 从封面逐场提取第 1–{n} 步（{backend}）：{os.path.basename(cover)}")
        # t198u: 每一场的图一写回，就带着这张图让 Strata 看图调整这一场的视觉，直接写回（不弹审阅窗）
        # t319u: 每一场的图写回后，马上从这一场的 clip_image 提取还没有肖像的人物（同一 Grok 账户，逐场）
        self._run_picture_batch(jobs, backend, [], account, auto=True, remix_visual=True, portraits=True)

    def _run_picture_batch(self, jobs: list, backend: str, skipped: list, account: str = "", *, auto: bool = False,
                           remix_visual: bool = False, portraits: bool = False) -> None:
        """图片修改 · 本集所有场景：每一场单独走 CLI自动（Grok / Gemini 网页图生图，或本机 MOSS ComfyUI），结果写回那一场。

        手动窗口只能一场一场贴，所以批量直接调 CLI自动 用的同一个 make_image。
        """
        import queue
        import threading
        import time
        from tkinter import ttk

        if not jobs:
            messagebox.showinfo("图片修改", "本集没有可处理的场景。\n" + "\n".join(skipped[:20]), parent=self.root)
            return
        # t373u: 每一场的提示词送出前把画风锁定挪到第一行（比例行 / FYI / 背景条件都在它后面）
        jobs = [(j[0], config_prompt.style_lock_first(j[1]), *j[2:]) if len(j) > 1 else j for j in jobs]
        b = str(backend or "").strip().lower()
        use_gemini = b == "gemini"
        use_moss = b == "moss"
        use_qn = b == "qn"
        who = (
            "MOSS" if use_moss else
            "QN" if use_qn else
            ("Gemini" if use_gemini else "Grok")
        )
        win = tk.Toplevel(self.root)
        win.title(f"图片修改 · 本集 {len(jobs)} 场（{who}）")
        win.transient(self.root)
        var = tk.StringVar(value="准备 …")
        ttk.Label(win, textvariable=var, wraplength=480, justify=tk.LEFT, padding=12).pack(fill=tk.BOTH)
        stop = {"flag": False}
        ttk.Button(win, text="停止（做完这一场后）", command=lambda: stop.update(flag=True)).pack(pady=(0, 10))
        failed = list(skipped)
        done = [0]

        def in_episode_label(scene, fallback) -> str:
            from utility.speaking_marks import scene_cover_step

            story = self.workflow.scenes_in_story(scene) if self.workflow else []
            for i, s in enumerate(story or []):
                if s is scene:
                    step = scene_cover_step(scene)
                    if step:
                        return f"第{i + 1}场/封面第{step}步"
                    return f"第{i + 1}场"
            return str(scene.get("id") or fallback)

        def ui(fn):
            try:
                self.root.after(0, fn)
            except Exception:
                pass

        updated: list = []
        rebuilt: list = []
        clip_q: queue.Queue = queue.Queue()
        remix_q: queue.Queue = queue.Queue()  # t198u: 自动调整视觉（只有从封面逐场提取时用）
        remixed: list = []
        ends = {"n": 0}

        def end_one():
            """UI 线程：clip 视频工人（和调整视觉工人）都结束了才 finish。"""
            ends["n"] += 1
            if ends["n"] >= (2 if remix_visual else 1):
                finish()

        def queue_remix(scene, label):
            """UI 线程：这一场的图刚写回 → 记下当时的视觉、图、人物，交给调整视觉工人。"""
            from utility.file_util import get_file_path

            image = get_file_path(scene, "clip_image")
            visual = scene.get("visual") or ""
            if not (visual.strip() and image and os.path.isfile(image)):
                print(f"ℹ️ 调整视觉：{label} 没有视觉文字或没有图，跳过")
                return
            lang = getattr(self.workflow, "language", None) or "tw"
            remix_q.put((scene, label, visual, image, scene.get("actor") or "", lang, scene.get("speaking") or ""))  # t161u: 整个 actor

        def apply_visual(scene, label, old, new, notes=None):
            """UI 线程：看图改写的结果直接写进这一场的视觉；原文留在 visual_before_remix。"""
            from utility.visual_remix import accept_auto_remix

            try:
                if (scene.get("visual") or "") != old:
                    print(f"ℹ️ 调整视觉：{label} 的视觉在这期间被改过，不覆盖")
                    return
                why = accept_auto_remix(old, new)
                if why:
                    print(f"ℹ️ 调整视觉：{label} {why}，保留原文")
                    return
                scene["visual_before_remix"] = old
                scene["visual"] = new
                if notes:  # t158u: 每个人这一场的样子写进 actor 括号
                    try:
                        new_actor = notes.get("actor") or ""
                        if (scene.get("actor") or "") != notes.get("actor_old"):
                            print(f"ℹ️ 调整人物：{label} 的人物在这期间被改过，不覆盖")
                        elif new_actor and new_actor != (scene.get("actor") or ""):
                            scene["actor_before_remix"] = scene.get("actor") or ""
                            scene["actor"] = new_actor
                            print(f"🖼 调整人物：{label} → {new_actor}")
                    except Exception as exc:  # noqa: BLE001
                        print(f"⚠️ 调整人物：{label} 写 actor 失败 {exc}")
                remixed.append(scene)
                print(f"🖼 调整视觉：{label} 已按图改写。原文：{old[:200]}")
                try:
                    cur = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
                    if cur is scene and getattr(self, "scene_visual", None) is not None:
                        self.scene_visual.delete("1.0", tk.END)
                        self.scene_visual.insert("1.0", new)
                        if hasattr(self, "_set_actor_text"):  # t161u
                            self._set_actor_text(scene.get("actor") or "")
                    self.workflow.save_scenes_to_json()
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 调整视觉：{label} 写回界面 / 保存失败 {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 调整视觉：{label} 写回失败 {exc}")

        def remix_worker():
            """t198u / t223u new-project cover-analysis path: same remix_scene_full as visual Remix —
            actors first (count = distinct 讲话 speakers; seats actor-is-truth), then visual.
            On look-failure leave visual unchanged (no text-only fallback); log only."""
            from utility.visual_remix import remix_scene_full
            import config

            try:
                while True:
                    item = remix_q.get()
                    if item is None:
                        break
                    scene, label, old, image, actor_old, lang, speaking = item
                    ui(lambda l=label: var.set(f"调整视觉（{l}，Strata 看图）…"))
                    try:
                        res = remix_scene_full(old, image, actor_text=actor_old,  # t161u: 视觉 + 人物样子 + 补缺的说话人
                                               language_label=config.llm_language_label(lang), speaking=speaking)
                        out = config.chinese_convert(res["visual"], lang)
                        notes = {"actor_old": actor_old, "actor": config.chinese_convert(res["actor"], lang)}
                    except Exception as exc:  # noqa: BLE001
                        failed.append(f"{label}：调整视觉失败，保留原文（{exc}）")
                        print(f"⚠️ 调整视觉：{label} 看图失败，保留原文：{exc}")
                        continue
                    ui(lambda s=scene, l=label, o=old, n=out, a=notes: apply_visual(s, l, o, n, a))
            finally:
                ui(end_one)

        written_events: dict = {}  # t319u: id(scene) → Event，apply 写完 clip_image 后通知工人线程
        upscale_of = {  # t366u: 提高分辨率的场：id(scene) → 目标尺寸
            id(j[0]): tuple(j[3]["upscale_size"]) for j in jobs
            if len(j) > 3 and isinstance(j[3], dict) and j[3].get("upscale_size")
        }
        upscale_base = {  # t377u: 提高分辨率的场：id(scene) → 原图（颜色统计对齐用）
            id(j[0]): j[3].get("base") for j in jobs
            if len(j) > 3 and isinstance(j[3], dict) and j[3].get("upscale_size")
        }

        def apply(scene, img, label):
            """UI 线程：写回这一场的图，有 clip 音频就马上排队重做这一场的静态 clip 视频。"""
            try:
                up = upscale_of.get(id(scene))
                if up:  # t366u: 提高分辨率：对齐到目标尺寸再写回；t377u: + 颜色统计对齐原图
                    from utility.image_upscale import finish_upscale

                    img = finish_upscale(img, up, upscale_base.get(id(scene)))
                self._replace_current_clip_image_from_pil(
                    img, scene=scene, defer_video=True,
                    exact_size=up,
                )
                done[0] += 1
                updated.append(scene)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{label}：写回失败 {exc}")
                return
            finally:
                evt = written_events.pop(id(scene), None)
                if evt is not None:
                    evt.set()  # t319u: 工人线程等这一场的 clip_image 写好再提取肖像
            if self._stale_still_clip_scenes([scene]):
                clip_q.put((scene, label))
            if remix_visual:
                queue_remix(scene, label)

        def clip_worker():
            """每换一张图就重做那一场的静态 clip 视频（一次一场，和生场视频共用忙碌标记）。"""
            while getattr(self, "_clip_video_worker_busy", False):
                time.sleep(1.0)  # 等前一个生场视频任务
            self._clip_video_worker_busy = True
            try:
                while True:
                    item = clip_q.get()
                    if item is None:
                        break
                    scene, label = item
                    try:
                        out = self._make_still_clip_video(scene)
                    except Exception as exc:  # noqa: BLE001
                        out = f"error {exc}"
                    if out == "ok":
                        rebuilt.append(scene)
                    else:
                        failed.append(f"{label}：静态 clip 视频没有重做（{out}）")
            finally:
                ui(end_one)

        portrait_ctx = self._portrait_extract_context() if portraits else None
        portrait_lines: list = []

        def portrait_step(scene, label):
            """t319u / t329u: 工人线程：这一场的图刚写好 → 只用这一场的 clip_image，人物一位一位给人看。

            已有肖像先给人看（不调 Grok）；没有就 Grok 提取一次再给人看。确认过的人以后的场景不再问；
            人按了「停止提取」就整批不再提取肖像；所有人都确认了也不再提取。Grok 失败：不开窗，下一场再试。"""
            if not portrait_ctx or portrait_ctx.get("stopped") or stop["flag"]:
                return
            from utility.actor_portrait_extract import (
                all_actors_confirmed,
                format_actor_result_line,
                generate_portrait_with_grok,
                review_portraits_for_scene,
            )

            if all_actors_confirmed([j[0] for j in jobs], portrait_ctx["confirmed"]):
                return
            ui(lambda h=f"{label}：提取人物肖像（等你看一眼）…": var.set(h))
            try:
                out = review_portraits_for_scene(
                    scene, portrait_ctx["avatar_dir"], covers=portrait_ctx["covers"], style=portrait_ctx["style"],
                    generate=lambda img, act, pr: generate_portrait_with_grok(img, act, pr, account=account),
                    review=lambda act, path, kind: self._portrait_review_from_worker(act, kind),
                    confirmed=portrait_ctx["confirmed"],
                    account=account,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 自动提取人物肖像：{label} 出错，跳过：{exc}")
                return
            for row in out.get("results") or []:
                portrait_lines.append(f"{label} {format_actor_result_line(row)}")
            if out.get("stopped"):
                portrait_ctx["stopped"] = True
                portrait_lines.append(f"{label} 你按了停止提取：后面的场景不再提取肖像")
            if out.get("reason") == "no_scene_clip_image":
                print(f"ℹ️ 自动提取人物肖像：{label} 没有自己的 clip_image（或还是封面拷贝），跳过")

        def scene_status(head):
            def status(msg, h=head):
                ui(lambda: var.set(f"{h}\n{msg}"))
            return status

        def comfy_kwargs(job) -> dict:
            """t356u: 图片修改已经给这一场写了 ComfyUI 专用提示（meta["comfy"]）→ 带反向提示 + 画布，不再改写。"""
            meta = job[3] if len(job) > 3 and isinstance(job[3], dict) else {}
            if not meta.get("comfy"):
                return {}
            size = tuple(meta.get("size") or ())
            kw = {"negative": meta.get("negative") or "", "adapt": False,
                  "width": size[0] if len(size) == 2 else None, "height": size[1] if len(size) == 2 else None}
            if meta.get("init_denoise") is not None:  # t377u: 提高分辨率 = 从原图开始采样（低 denoise）
                kw["init_denoise"] = meta["init_denoise"]
            return kw

        def moss_worker():
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
                    img = generate_image_moss_edit(prompt, list(images), status=scene_status(head), **comfy_kwargs(job))
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
                    img = generate_image_qwen_edit(prompt, list(images), status=scene_status(head), **comfy_kwargs(job))
                    if img is None or not hasattr(img, "save"):
                        raise RuntimeError("没有拿到图")
                    ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{label}：{exc}")

        def per_call_worker():
            """Grok（或旧方式）：每一场单独调 make_image。"""
            if use_gemini:
                from utility import gemini_cdp as engine
            else:
                from utility import grok_cdp as engine
            from utility import chrome_account
            n = len(jobs)
            if auto:  # t206u: 开始前确认 Chrome / CDP 就绪
                try:
                    engine.ensure_chrome(scene_status("检查 Chrome …"))
                    auto_extract_log(f"start {n} scenes backend={who} account={account or chrome_account.active()}")
                except Exception as exc:  # noqa: BLE001
                    auto_extract_log(f"chrome not ready: {exc!r}")
            for k, job in enumerate(jobs, 1):
                scene, prompt, images = job[0], job[1], job[2]
                if stop["flag"]:
                    failed.append(f"其余 {n - k + 1} 场：已停止")
                    break
                label = in_episode_label(scene, k)
                attempts = 2 if auto else 1  # t206u: 自动提取失败重试一次
                for attempt in range(1, attempts + 1):
                    head = f"正在处理第 {k}/{n} 张（本集{label}）" + (f" · 重试" if attempt > 1 else "")
                    ui(lambda h=head: var.set(h))
                    if auto:
                        auto_extract_log(f"{label} try{attempt} account={account} prompt_len={len(prompt)} "
                                         f"images={list(images)}")
                    try:
                        with chrome_account.use(account):  # t206u: 每次调用都重申账户
                            img = engine.make_image(prompt, list(images), status=scene_status(head))
                        if img is None or not hasattr(img, "save"):
                            raise RuntimeError("没有拿到图")
                        if auto:
                            auto_extract_log(f"{label} try{attempt} ok")
                        written_evt = threading.Event() if portraits else None
                        if written_evt is not None:
                            written_events[id(scene)] = written_evt
                        ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                        if written_evt is not None:
                            written_evt.wait(120)
                            if scene in updated:
                                portrait_step(scene, label)
                        break
                    except Exception as exc:  # noqa: BLE001
                        if auto:
                            auto_extract_log(f"{label} try{attempt} FAILED: {exc!r}")
                        if attempt >= attempts or stop["flag"]:
                            failed.append(f"{label}：{exc}")

        def gemini_session_worker():
            """Gemini：整批同一个对话，没有单独的开场消息。

            每个对话的第一条 = 基础图（Image 1）+ 人物形象图（Image 2..，按名字标好，最多共 5 张），
            提示词里说明形象图要记住，后面几场也用。之后每场只发基础图（加上这一场要用、但还没发过的形象图）。
            出错：开新对话，这一场按「第一条」的方式重发（基础图 + 形象图）。
            """
            from utility import gemini_cdp

            n = len(jobs)
            cap = gemini_cdp.MAX_IMAGES
            info, order = {}, []
            for job in jobs:
                meta = job[3] if len(job) > 3 and isinstance(job[3], dict) else {}
                for r in meta.get("actors") or []:
                    p = r.get("image") if isinstance(r, dict) else ""
                    if p and os.path.isfile(p) and p not in info:
                        info[p] = r
                        order.append(p)
            sent: set = set()  # 当前对话里已经发过的形象图

            def who(r):
                return f"{r.get('label') or '人物'} {r.get('name') or ''}".strip()

            def scene_rows(job):
                meta = job[3] if len(job) > 3 and isinstance(job[3], dict) else {}
                return [r for r in (meta.get("actors") or []) if isinstance(r, dict) and (r.get("name") or "").strip()]

            def build(k, job):
                """返回 (提示词, 要附的图)。"""
                meta = job[3] if len(job) > 3 and isinstance(job[3], dict) else {}
                rows = scene_rows(job)
                base = [p for p in list(job[2])[:1] if p]
                first = not sent
                need = [r.get("image") for r in rows if r.get("image") in info and r.get("image") not in sent]
                attach = []
                for p in need + (order if first else []):  # 第一条：这一场要的先放，再放其余形象图
                    if p not in attach and len(base) + len(attach) < cap:
                        attach.append(p)
                parts = [meta["aspect"], ""] if meta.get("aspect") else []
                from utility.speaking_marks import scene_cover_step, unique_cover_step_count

                step = scene_cover_step(job[0]) or k
                total = unique_cover_step_count([j[0] for j in jobs if isinstance(j[0], dict)]) or n
                parts.append(f"Scene {step} of {total}. Image 1 = the base picture of this scene. Edit only Image 1.")
                if attach:
                    parts.append("The other attached images are character portraits:")
                    for i, p in enumerate(attach, 2):
                        parts.append(f"- Image {i} = portrait of {who(info[p])}")
                    parts.append("Remember these portraits by name: the next scenes in this chat will only send the scene "
                                 "picture and refer to the characters by name.")
                if sent:
                    parts.append("Earlier images in this chat are not part of this request, except the character portraits you "
                                 "were given before (remember them by name).")
                if rows:
                    parts.append("People in this scene:")
                    for r in rows:
                        p = r.get("image") or ""
                        if p in attach:
                            parts.append(f"- {who(r)}: use the portrait Image {attach.index(p) + 2}")
                        elif p in sent:
                            parts.append(f"- {who(r)}: use the portrait of {who(r)} sent earlier in this chat")
                        else:
                            parts.append(f"- {who(r)}: no portrait; draw from the name and description, keep the look consistent")
                    parts.append(
                        "Replace the people in Image 1 with these characters: match each person by gender, age and role, "
                        "then redraw face, hair and clothing like their portrait. Keep pose, position, composition and lighting. "
                        "Never carry over a portrait's art style, background or lighting. Do not add or remove people."
                    )
                else:
                    parts.append("No cast is listed for this scene: do not put any of the portraits into it.")
                parts += ["Output exactly one image.", "", job[1]]
                return config_prompt.style_lock_first("\n".join(parts)), base + attach  # t373u

            try:
                with gemini_cdp.GeminiSession(status=scene_status("开新的 Gemini 对话")) as gs:
                    for k, job in enumerate(jobs, 1):
                        scene = job[0]
                        if stop["flag"]:
                            failed.append(f"其余 {n - k + 1} 场：已停止")
                            break
                        label = in_episode_label(scene, k)
                        head = f"正在处理第 {k}/{n} 张（本集{label}，同一个 Gemini 对话）"
                        ui(lambda h=head: var.set(h))
                        gs.set_status(scene_status(head))
                        for attempt in (1, 2):
                            prompt, files = build(k, job)
                            try:
                                img = gs.make_image(prompt, files, reject_paths=order)
                                if img is None or not hasattr(img, "save"):
                                    raise RuntimeError("没有拿到图")
                                sent.update(p for p in files[1:] if p in info)
                                ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                                break
                            except Exception as exc:  # noqa: BLE001
                                if attempt == 2:
                                    failed.append(f"{label}：重试后仍失败 · {exc}")
                                    break
                                print(f"图片修改：{label} 出错，开新对话（基础图 + 形象图）再试：{exc}")
                                gs.set_status(scene_status(f"{head}\n出错（{str(exc)[:60]}），开新对话重发基础图 + 人物形象图"))
                                try:
                                    gs.restart()
                                    sent.clear()
                                except Exception as exc2:  # noqa: BLE001
                                    failed.append(f"{label}：第1次失败 · {exc}；开新对话也失败 · {exc2}")
                                    break
            except Exception as exc:  # noqa: BLE001
                failed.append(f"开新的 Gemini 对话（连接 / 登录 / 新对话）失败：{exc}")

        def worker():
            from utility import chrome_account

            try:
                if use_moss:
                    moss_worker()
                elif use_qn:
                    qn_worker()
                else:
                    with chrome_account.use(account):  # t129u: 选的 Chrome 账户
                        if use_gemini:
                            gemini_session_worker()
                        else:
                            per_call_worker()
            finally:
                # 经 UI 线程排在最后一个 apply 之后：图都写回、clip 队列清空后才 finish
                ui(lambda: (clip_q.put(None), remix_q.put(None)))

        def finish():
            self._clip_video_worker_busy = False
            try:
                win.destroy()
            except tk.TclError:
                pass
            try:
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
            except Exception as exc:  # noqa: BLE001
                print(f"图片修改：刷新失败 {exc}")
            note = (f"图片修改完成（从当前场到本集结束）：{done[0]}/{len(jobs)} 场已换图，"
                    f"{len(rebuilt)} 场已重做静态 clip 视频。")
            if remix_visual:
                note += f"\n{len(remixed)} 场的视觉已按图调整（原文存在 visual_before_remix）。"
            if failed:
                note += "\n\n没处理 / 失败：\n" + "\n".join(failed[:30])
            if portrait_lines:
                print("🖼 自动提取人物肖像（逐场，来源 = 各场 clip_image）：\n" + "\n".join(portrait_lines))
            if auto:  # t176u: 自动提取不弹要按确定的窗，只显示几秒的提示
                print(note)
                show_auto_close_popup(self.root, "从封面逐场提取", note, duration_ms=4000)
            else:
                messagebox.showinfo("图片修改", note, parent=self.root)
            # 最后再查一遍：这一段里 clip 视频还比图旧的场景（以前漏做的）一起重做（本地 ffmpeg，静态图 + clip 音频）。
            self._rebuild_still_clips_after_batch([], jobs, quiet=auto)

        threading.Thread(target=clip_worker, daemon=True).start()
        if remix_visual:
            threading.Thread(target=remix_worker, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    def _portrait_extract_context(self) -> dict | None:
        """t319u: 肖像提取用的 项目 avatar 目录、画面风格（同人物窗 _portrait_style）、项目封面列表（用于排除封面拷贝）。"""
        try:
            import config

            avatar_dir = os.path.join(config.get_project_path(self.get_pid()), "avatar")
        except Exception:  # noqa: BLE001
            return None
        try:
            style = self._portrait_style()  # 和双击人物看肖像用同一个风格目录
        except Exception:  # noqa: BLE001
            style = project_manager.current_visual_style()
        covers = []
        try:
            from utility.scene_image_slots import list_project_cover_images

            wf = getattr(self, "workflow", None)
            covers = list_project_cover_images(
                cover_override=getattr(wf, "_seed_cover_override", "") if wf else "",
                project_config=project_manager.PROJECT_CONFIG,
            )
        except Exception:  # noqa: BLE001
            covers = []
        return {
            "avatar_dir": avatar_dir, "style": style, "covers": list(covers),
            "confirmed": self._portrait_confirmed_set(), "stopped": False,
        }

    @staticmethod
    def _portrait_confirmed_set() -> set:
        """t329u: 本项目已经确认过肖像的人物（角色:身份），存在项目配置 actor_portrait_confirmed。"""
        raw = (project_manager.PROJECT_CONFIG or {}).get("actor_portrait_confirmed") or []
        return {str(x) for x in raw if isinstance(x, str) and x}

    def _remember_portrait_confirmed(self, key: str) -> None:
        """UI 线程：把确认过的人物记进项目配置并保存。"""
        if not key or not isinstance(project_manager.PROJECT_CONFIG, dict):
            return
        have = list(project_manager.PROJECT_CONFIG.get("actor_portrait_confirmed") or [])
        if key in have:
            return
        have.append(key)
        project_manager.PROJECT_CONFIG["actor_portrait_confirmed"] = have
        try:
            project_manager.save_project_config()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 已确认肖像没有存进项目配置：{exc}")

    def _forget_portrait_confirmed(self, body: str) -> None:
        """t329u: 在人物窗里手动删了肖像 → 这一位不再算已确认（下次自动提取会再问）。"""
        from utility.actor_portrait_extract import confirm_key

        key = confirm_key({"role": "person", "body": body})
        have = list((project_manager.PROJECT_CONFIG or {}).get("actor_portrait_confirmed") or [])
        if key not in have:
            return
        project_manager.PROJECT_CONFIG["actor_portrait_confirmed"] = [k for k in have if k != key]
        try:
            project_manager.save_project_config()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 已确认肖像没有存进项目配置：{exc}")

    def _portrait_review_on_ui(self, actor: dict, kind: str, parent=None) -> str:
        """t329u: UI 线程：在人物窗里审这一位；确认就记进项目配置。返回 ok / deleted / stop。"""
        from utility.actor_portrait_extract import REVIEW_DELETED, REVIEW_IGNORED, REVIEW_OK, REVIEW_STOP, confirm_key

        try:
            answer = self._review_actor_portrait(actor.get("body") or "", kind=kind, parent=parent)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 审核肖像窗口出错：{exc}")
            return REVIEW_STOP
        if answer not in (REVIEW_DELETED, REVIEW_STOP, REVIEW_IGNORED):
            answer = REVIEW_OK
            self._remember_portrait_confirmed(confirm_key(actor))
        return answer

    def _portrait_review_from_worker(self, actor: dict, kind: str, parent=None) -> str:
        """工人线程调用：把审核窗排到 Tk 主线程，等人看完再返回（Grok 在工人线程跑，界面不卡）。"""
        import threading

        if threading.current_thread() is threading.main_thread():
            return self._portrait_review_on_ui(actor, kind, parent)
        box = {"answer": "stop"}
        done = threading.Event()

        def run():
            try:
                box["answer"] = self._portrait_review_on_ui(actor, kind, parent)
            finally:
                done.set()

        try:
            self.root.after(0, run)
        except Exception:  # noqa: BLE001 — 主窗口没了：停止
            return "stop"
        done.wait()
        return box["answer"]

    def _stale_still_clip_scenes(self, scenes: list) -> list:
        """clip 视频比 clip_image 旧（或没有 clip 视频）、且有 clip 音频的场景：需要用新图重做静态视频。"""
        from utility.file_util import get_file_path

        out = []
        for s in scenes or []:
            if not isinstance(s, dict):
                continue
            image = get_file_path(s, "clip_image")
            audio = get_file_path(s, "clip_audio")
            if not (image and os.path.isfile(image) and audio and os.path.isfile(audio)):
                continue
            clip = get_file_path(s, "clip")
            if not clip or not os.path.isfile(clip) or os.path.getmtime(clip) < os.path.getmtime(image):
                out.append(s)
        return out

    def _rebuild_still_clips_after_batch(self, updated: list, jobs: list, tries: int = 0, *, quiet: bool = False) -> None:
        """批量换图之后：换了图的场景，加上这一段里 clip 视频比图旧的场景（修复以前漏做的），一起重做静态 clip 视频。"""
        pool = [job[0] for job in jobs]
        targets = list(updated)
        for s in self._stale_still_clip_scenes(pool):
            if all(s is not t for t in targets):
                targets.append(s)
        targets = [s for s in targets if s in self._stale_still_clip_scenes(targets) or s in updated]
        if not targets:
            return
        if getattr(self, "_clip_video_worker_busy", False):
            if tries < 60:  # 等前一个生场视频任务（最多约 1 分钟）
                self.root.after(1000, lambda: self._rebuild_still_clips_after_batch(updated, jobs, tries + 1, quiet=quiet))
            return
        self._run_still_clip_videos(targets, quiet=quiet)

    def repair_stale_still_clips(self) -> None:
        """修复：本集里 clip 视频比 clip_image 旧的场景，用现在的 clip_image + clip_audio 重做静态 clip 视频。"""
        self.update_current_scene()
        cur = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not isinstance(cur, dict):
            return
        stale = self._stale_still_clip_scenes(self.workflow.scenes_in_story(cur))
        if not stale:
            show_auto_close_popup(self.root, "生场视频", "本集没有 clip 视频比图片旧的场景。")
            return
        self._run_still_clip_videos(stale)

    def _place_popup_near(self, dlg: tk.Toplevel, anchor, *, below: bool) -> None:
        """把弹出窗口放在锚点旁边。below 为真时放在下面，否则放在上面，不挡住锚点。"""
        dlg.withdraw()
        dlg.update_idletasks()
        try:
            anchor.update_idletasks()
            ax = int(anchor.winfo_rootx())
            ay = int(anchor.winfo_rooty())
            aw = max(int(anchor.winfo_width()), 1)
            ah = max(int(anchor.winfo_height()), 1)
        except (tk.TclError, TypeError, ValueError):
            ax = int(self.root.winfo_rootx()) + int(self.root.winfo_width()) - 480
            ay = int(self.root.winfo_rooty()) + 80
            aw, ah = 80, 28
        w = max(int(dlg.winfo_reqwidth()), 200)
        h = max(int(dlg.winfo_reqheight()), 80)
        sw = int(dlg.winfo_screenwidth())
        sh = int(dlg.winfo_screenheight())
        gap = 8
        if below:
            x = ax
            y = ay + ah + gap
            if y + h > sh - 8:
                y = max(8, ay - h - gap)
        else:
            x = ax + aw - w
            y = ay - h - gap
            if y < 8:
                y = min(max(8, sh - h - 8), ay + ah + gap)
        x = max(8, min(x, max(8, sw - w - 8)))
        y = max(8, min(y, max(8, sh - h - 8)))
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.deiconify()
        try:
            dlg.lift()
        except tk.TclError:
            pass

    def _open_video_prompt_flow(self) -> None:
        """视频提示：先选叙事风格、画面、背景、演进，再在手动窗口里拷画面和提示词。"""
        from gui.video_prompt_dialog import open_video_prompt_dialog

        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("视频提示", "没有当前场景", parent=self.root)
            return

        def current_scene():
            self.update_current_scene()
            if not self.workflow:
                return None
            return self.workflow.get_scene_by_index(self.current_scene_index)

        def get_image(key: str) -> str:
            scene = current_scene()
            path = scene.get(key) if isinstance(scene, dict) else ""
            if isinstance(path, str) and path and os.path.isfile(path):
                return path
            if key == "clip_audio" and isinstance(scene, dict):  # t155u: 同轨道备份那样找场景音频
                from utility.file_util import get_file_path

                path = get_file_path(scene, "clip_audio") or ""
                if path and os.path.isfile(path):
                    return path
            return ""

        def copy_text(text: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or config.VISUAL_STYLE_OPTIONS[0]
            )

        def _on_video_image_response(pil_img):
            _mgr, vd, _story_raw, ch_path = self._cover_prompt_context()
            if not isinstance(vd, dict):
                return
            ch = (getattr(self.workflow, "channel", None) or "").strip()
            from gui.downloader import save_pil_image_to_cover_array
            ok, dest, _err = save_pil_image_to_cover_array(
                pil_img,
                vd,
                channel=ch,
                filename_hint="video_prompt",
            )
            if ok and dest:
                project_manager.save_project_config()
                show_auto_close_popup(
                    self.root,
                    "视频提示",
                    f"返回的图片已保存到封面列表：\n{os.path.basename(dest)}",
                )

        def _video_download_dir() -> str:
            """导入视频「下载」来源看的目录：用户 Downloads（存在时），否则项目 download 文件夹。"""
            # generated clips go to the working dir (D:\AI_MEDIA\working), not Downloads
            folder = config.WORKING_DIR
            os.makedirs(folder, exist_ok=True)
            return folder
            folder = config.get_project_path(self.workflow.pid) + "/download"
            os.makedirs(folder, exist_ok=True)
            return folder

        def _on_video_file_response(path: str) -> None:
            """CLI自动 生成的 mp4：打开导入视频，来源=下载，片段列表预选这个文件（不自动导入）。"""
            if not path or not os.path.isfile(path):
                return
            batch = getattr(self, "_video_batch_files", None)
            if isinstance(batch, list):  # t172u: 全集提交中：先记下，全部做完再打开一次导入视频
                batch.append(path)
                return
            try:  # t151u: 当前场记下的语速档只给这个文件
                _sc = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
                _rec = _sc.get("video_speech_speed") if isinstance(_sc, dict) else None
                if isinstance(_rec, dict) and not _rec.get("file"):
                    _rec["file"] = os.path.basename(path)
                if isinstance(_sc, dict):
                    config_prompt.attach_video_prompt_file(_sc, path)  # t156u
            except Exception:  # noqa: BLE001
                pass
            show_auto_close_popup(self.root, "生场视频", f"视频已下载：\n{os.path.basename(path)}")
            self.root.after(
                200,
                lambda: self.choose_import_video(initial_source="download", preselect_file=os.path.basename(path)),
            )

        def _episode_from_current() -> tuple:
            """t172u: 全集提交：从当前场到本集结束。返回 (场景, 当前是本集第 k 场, 本集共 m 场)。"""
            self.update_current_scene()
            cur = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
            if not isinstance(cur, dict):
                return [], 0, 0
            story = [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]
            k = next((i for i, s in enumerate(story) if s is cur), 0)
            return story[k:], k + 1, len(story)

        def _select_scene(scene: dict) -> None:
            """t172u: 全集提交：把这一场设成当前场景（图、音频、内容都按它取）。"""
            self.update_current_scene()
            for i, sc in enumerate(self.workflow.scenes or []):
                if sc is scene:
                    self.current_scene_index = i
                    break
            self.refresh_gui_scenes()

        def _episode_done(files: list) -> None:
            # t173u: 每一场已自动导入（_auto_import_scene_video），这里不再打开导入视频
            self._video_batch_files = None

        def save_video_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            choice = {k: v for k, v in (choice or {}).items() if k != "narrative"}  # 叙事风格只存 story_style
            if not isinstance(cfg, dict) or cfg.get("video_prompt") == choice:
                return
            cfg["video_prompt"] = choice
            save_project_config(parent=self.root)

        def apply_look(look: dict) -> None:
            """t235u: 提交确认里改过的全场内容写回主窗口（画面风格 / 场景风格 / 讲员 / 地域 · 时代）。"""
            look = dict(look or {})
            vs = config.match_visual_style(look.get("visual_style") or "")
            if vs and hasattr(self, "scene_visual_style"):
                try:
                    self.scene_visual_style.set(vs)
                except Exception:  # noqa: BLE001
                    pass
            ss = config_prompt.normalize_scene_style(look.get("scene_style"))
            if hasattr(self, "scene_style"):
                try:
                    self.scene_style.set(ss or config_prompt.SCENE_STYLE_LABELS[0])
                except Exception:  # noqa: BLE001
                    pass
            region = (look.get("region") or "").strip()
            era = (look.get("era") or "").strip()
            if region not in config_prompt.SETTING_PLACES:
                region, era = "", ""
            eras = config_prompt.setting_era_labels(region)
            if era not in eras:
                era = eras[0] if eras else ""
            if hasattr(self, "setting_region"):
                try:
                    self.setting_region.set(region)
                    if hasattr(self, "setting_era"):
                        self.setting_era["values"] = eras
                        self.setting_era.set(era)
                except Exception:  # noqa: BLE001
                    pass
            nar = (look.get("narrator") or "").strip()
            pc = project_manager.PROJECT_CONFIG
            if isinstance(pc, dict):
                if pc.get("narrator") != nar:
                    pc["narrator"] = nar
                project_manager.LAST_NARRATOR = nar
            if callable(getattr(self, "_refresh_narrator_button", None)):
                try:
                    self._refresh_narrator_button(nar)
                except Exception:  # noqa: BLE001
                    pass
            try:
                project_manager.remember_setting_place(region, era)
            except Exception:  # noqa: BLE001
                pass
            try:
                project_manager.remember_scene_style(ss)
            except Exception:  # noqa: BLE001
                pass
            if vs:
                try:
                    project_manager.LAST_VISUAL_STYLE = vs
                except Exception:  # noqa: BLE001
                    pass
            if callable(getattr(self, "_save_project_look", None)):
                try:
                    self._save_project_look()
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 全场内容写回项目失败：{exc}")

        def on_story_style(key: str) -> None:
            """生场视频里选了叙事风格：写 project story_style，同步主窗口「故事风格」，记为上次选择。"""
            key = config_prompt.normalize_story_style(key)
            if not key:
                return
            if hasattr(self, "story_style"):
                label = config_prompt.story_style_label(key)
                if self.story_style.get() != label:
                    self.story_style.set(label)
            project_manager.remember_story_style(key)
            cfg = project_manager.PROJECT_CONFIG
            if isinstance(cfg, dict):
                vp = cfg.get("video_prompt")
                changed = cfg.get("story_style") != key
                if isinstance(vp, dict) and "narrative" in vp:
                    cfg["video_prompt"] = {k: v for k, v in vp.items() if k != "narrative"}
                    changed = True
                if changed:
                    cfg["story_style"] = key
                    save_project_config(parent=self.root)

        open_video_prompt_dialog(
            self.root,
            self._nb_story_video_btn,
            get_scenes=lambda: [s for s in [current_scene()] if isinstance(s, dict)],
            get_style=get_style,
            copy_text=copy_text,
            language=getattr(self.workflow, "language", "") or "",
            host_narrator=project_manager.project_narrator(),
            get_place=lambda: (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            ),
            get_image=get_image,
            copy_image=lambda path: bool(self.copy_image_to_clipboard(path, silent=True)),
            open_manual=lambda prompt, images, extra=None: self.llm_api.show_manual_window(
                prompt, "", images=images, on_image_response=_on_video_image_response,
                cli_kind="video", file_dest_dir=_video_download_dir(),
                on_file_response=_on_video_file_response, extra=extra,
            ),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("video_prompt"),
            save_choice=save_video_choice,
            on_story_style=on_story_style,
            apply_look=apply_look,
            get_actor_portraits=lambda sc: config_prompt.scene_speaker_portraits(sc, self._actor_entry_portrait),
            on_scene_record=lambda: self.workflow.save_scenes_to_json() if self.workflow else None,  # t151u
            episode={
                "scenes": _episode_from_current,
                "select": _select_scene,
                "begin": lambda: setattr(self, "_video_batch_files", []),
                "end": _episode_done,
                "import": self._auto_import_scene_video,
                # t370u: 生场视频动态分节（<Ns> / <s>）
                "segments": self._video_segment_count,
                "split": self._split_video_segment,
                "unsplit": self._undo_video_segment,
                "chain": self._chain_video_segment,
                # t190u: MiniMax 双机全集：工人线程里直接生成（不开手动窗口），key = minimax_5070ti / minimax_5060
                "generate": lambda prompt, images, extra, key, status: __import__(
                    "utility.minimax_dual", fromlist=["minimax_generate"]).minimax_generate(
                    prompt, None, images, extra, _video_download_dir(), "minimax_dual", status=status, server_key=key),
            },
            simple_actions=[
                ("仅当前场景", lambda: self._run_clip_video("still", "single")),
                ("本集从这一场起", lambda: self._run_clip_video("still", "story")),
                ("全部场景", lambda: self._run_clip_video("still", "all")),
                # t152u: WAN 生成按钮先不显示（_run_clip_video("wan", ...) 的代码还留着，以后再接回）
            ],
        )

    def _open_slide_prompt_flow(self) -> None:
        """全集生成：只取当前场景所在这一集的场景，选叙事风格后拷提示词。"""
        from gui.slide_prompt_dialog import open_slide_prompt_dialog

        self.update_current_scene()
        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("全集生成", "没有当前场景", parent=self.root)
            return

        def episode_scenes() -> list:
            self.update_current_scene()
            if not self.workflow:
                return []
            cur = self.workflow.get_scene_by_index(self.current_scene_index)
            if not isinstance(cur, dict):
                return []
            return [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]

        def copy_text(text: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or config.VISUAL_STYLE_OPTIONS[0]
            )

        def get_place() -> tuple:
            return (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            )

        def save_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("slide_prompt") == choice:
                return
            cfg["slide_prompt"] = choice
            save_project_config(parent=self.root)

        def scene_range(range_key: str) -> tuple[list, list]:
            """范围：本集，或本集到结束（本集和后面各集）。返回 (场景, 每场集名)。"""
            self.update_current_scene()
            if not self.workflow:
                return [], []
            cur = self.workflow.get_scene_by_index(self.current_scene_index)
            if not isinstance(cur, dict):
                return [], []
            # 每场的「集名」只用于显示（第N集分隔标题、范围说明），所以给的是 scenes.json 顺序里的位置，不是集号。
            pos = self.workflow.episode_position
            if range_key == "to_end":
                scenes, groups = self.workflow.scenes_from_episode_to_end(cur)
                return scenes, [str(pos(g) or g) for g in groups]
            g = self.workflow.scene_group(cur)
            scenes = [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]
            return scenes, [str(pos(g) or g)] * len(scenes)

        def open_slides_manual(
            prompt: str, kind: str = "slides", notebook_url: str = "", source_pdf: str = "", actor_pdf: str = "",
            cross_episodes: bool = False, extra_sources=None, times: int = 1, content_topic: str = "",
            audio_format: str = "",
        ) -> None:
            """提交：手工 LLM 窗口 CLI自动 → NotebookLM Studio（kind）→ 下载 → 系统程序打开。"""
            import os
            from pathlib import Path

            working = config.WORKING_DIR

            def _open_file(path: str, all_paths=None) -> None:
                """Studio 下载结果移到 working（不覆盖已有文件）。PDF 走拆页预览 / 分配；其余直接打开。"""
                from utility.program_media import settle_generated_file

                batch = [item for item in (all_paths or [path]) if item]
                for item in batch:
                    try:
                        item = settle_generated_file(item, working)
                    except Exception as exc:
                        print(f"⚠️ 移动到 working 失败，用原位置：{exc}")
                    if str(item).lower().endswith(".pdf"):
                        self.root.after(
                            50,
                            lambda p=item: self._on_media_drop_pdf(p, origin="全集生成", cross_episodes=cross_episodes),
                        )
                        continue
                    try:
                        os.startfile(item)
                    except OSError as exc:
                        messagebox.showwarning("打开失败", f"打不开：{exc}\n{item}", parent=self.root)

            from utility.program_media import clamp_studio_times

            extra = {"output": kind, "studio_times": clamp_studio_times(times)}
            # 画面比例用项目的宽高（1920×1080 → 16:9，1080×1920 → 9:16）。
            _pc = project_manager.PROJECT_CONFIG or {}
            extra["video_size"] = project_manager.video_size_key(_pc.get("video_width"), _pc.get("video_height"))
            if notebook_url:
                extra["notebook_url"] = notebook_url
            if source_pdf:
                extra["source_pdf"] = source_pdf  # CLI自动：先上传为笔记本来源，再生成
            if actor_pdf:
                extra["actor_pdf"] = actor_pdf  # 本集人物：content.pdf 之后上传
            extra["content_topic"] = (content_topic or "").strip()
            extra["audio_format"] = (audio_format or "").strip()
            self.llm_api.show_manual_window(
                prompt, "", auto_cli=True, cli_kind=kind or "slides",
                file_dest_dir=working, on_file_response=_open_file, extra=extra,
            )

        open_slide_prompt_dialog(
            self.root,
            getattr(self, "_slide_prompt_btn", None),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("slide_prompt"),
            save_choice=save_choice,
            get_scenes=episode_scenes,
            get_style=get_style,
            copy_text=copy_text,
            host_narrator=project_manager.project_narrator(),
            get_place=get_place,
            main_character="",
            open_manual=open_slides_manual,
            actor_avatar_dir=os.path.join(config.get_project_path(self.get_pid()), "avatar"),
            get_scene_range=scene_range,
        )

def auto_extract_log(msg: str) -> None:
    """t206u: 从封面逐场提取的每次尝试 / 失败写到 %LOCALAPPDATA%\\AIComposer\\auto_extract.log。"""
    import datetime

    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print("[auto_extract] " + line)
    try:
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AIComposer")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "auto_extract.log"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
