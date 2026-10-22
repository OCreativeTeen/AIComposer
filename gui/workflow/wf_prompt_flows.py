"""PromptFlowsMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import json
import config
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
            stored_slide = (src.get("slide") or "").strip()
            if not cover and stored_cover:
                cover = stored_cover
            if not slide and stored_slide and os.path.isfile(stored_slide):
                slide = os.path.abspath(stored_slide)
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
        if slide:
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

        def open_manual(prompt: str, images: list[str], backend: str = "grok") -> None:
            def _on_image_response(pil_img):
                self._replace_current_clip_image_from_pil(pil_img)

            extra = {"image_backend": "gemini"} if str(backend or "").strip().lower() == "gemini" else {}
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

        open_picture_prompt_dialog(
            self.root,
            self._nb_picture_btn,
            batch_scenes=batch_scenes,
            run_batch=self._run_picture_batch,
            get_scene=current_scene,
            get_style=get_style,
            get_place=get_place,
            open_manual=open_manual,
            host_narrator=project_manager.project_narrator(),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("picture_prompt"),
            save_choice=save_choice,
            actor_avatar_dir=os.path.join(config.get_project_path(self.get_pid()), "avatar"),
        )

    def _run_picture_batch(self, jobs: list, backend: str, skipped: list) -> None:
        """图片修改 · 本集所有场景：每一场单独走 CLI自动（Grok / Gemini 网页图生图），结果写回那一场。

        手动窗口只能一场一场贴，所以批量直接调 CLI自动 用的同一个 make_image。
        """
        import queue
        import threading
        import time
        from tkinter import ttk

        if not jobs:
            messagebox.showinfo("图片修改", "本集没有可处理的场景。\n" + "\n".join(skipped[:20]), parent=self.root)
            return
        use_gemini = str(backend or "").strip().lower() == "gemini"
        who = "Gemini" if use_gemini else "Grok"
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
            story = self.workflow.scenes_in_story(scene) if self.workflow else []
            for i, s in enumerate(story or []):
                if s is scene:
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

        def apply(scene, img, label):
            """UI 线程：写回这一场的图，有 clip 音频就马上排队重做这一场的静态 clip 视频。"""
            try:
                self._replace_current_clip_image_from_pil(img, scene=scene, defer_video=True)
                done[0] += 1
                updated.append(scene)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{label}：写回失败 {exc}")
                return
            if self._stale_still_clip_scenes([scene]):
                clip_q.put((scene, label))

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
                ui(finish)

        def scene_status(head):
            def status(msg, h=head):
                ui(lambda: var.set(f"{h}\n{msg}"))
            return status

        def per_call_worker():
            """Grok（或旧方式）：每一场单独调 make_image。"""
            if use_gemini:
                from utility import gemini_cdp as engine
            else:
                from utility import grok_cdp as engine
            n = len(jobs)
            for k, job in enumerate(jobs, 1):
                scene, prompt, images = job[0], job[1], job[2]
                if stop["flag"]:
                    failed.append(f"其余 {n - k + 1} 场：已停止")
                    break
                label = in_episode_label(scene, k)
                head = f"正在处理第 {k}/{n} 张（本集{label}）"
                ui(lambda h=head: var.set(h))
                try:
                    img = engine.make_image(prompt, list(images), status=scene_status(head))
                    if img is None or not hasattr(img, "save"):
                        raise RuntimeError("没有拿到图")
                    ui(lambda s=scene, i=img, l=label: apply(s, i, l))
                except Exception as exc:  # noqa: BLE001
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
                parts.append(f"Scene {k} of {n}. Image 1 = the base picture of this scene. Edit only Image 1.")
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
                return "\n".join(parts), base + attach

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
            try:
                if use_gemini:
                    gemini_session_worker()
                else:
                    per_call_worker()
            finally:
                # 经 UI 线程排在最后一个 apply 之后：图都写回、clip 队列清空后才 finish
                ui(lambda: clip_q.put(None))

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
            if failed:
                note += "\n\n没处理 / 失败：\n" + "\n".join(failed[:30])
            messagebox.showinfo("图片修改", note, parent=self.root)
            # 最后再查一遍：这一段里 clip 视频还比图旧的场景（以前漏做的）一起重做。
            self._rebuild_still_clips_after_batch([], jobs)

        threading.Thread(target=clip_worker, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

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

    def _rebuild_still_clips_after_batch(self, updated: list, jobs: list, tries: int = 0) -> None:
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
                self.root.after(1000, lambda: self._rebuild_still_clips_after_batch(updated, jobs, tries + 1))
            return
        self._run_still_clip_videos(targets)

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
            from gui.workflow.wf_common import _user_downloads_folder

            folder = _user_downloads_folder()
            if folder and os.path.isdir(folder):
                return folder
            folder = config.get_project_path(self.workflow.pid) + "/download"
            os.makedirs(folder, exist_ok=True)
            return folder

        def _on_video_file_response(path: str) -> None:
            """CLI自动 生成的 mp4：打开导入视频，来源=下载，片段列表预选这个文件（不自动导入）。"""
            if not path or not os.path.isfile(path):
                return
            show_auto_close_popup(self.root, "生场视频", f"视频已下载：\n{os.path.basename(path)}")
            self.root.after(
                200,
                lambda: self.choose_import_video(initial_source="download", preselect_file=os.path.basename(path)),
            )

        def save_video_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("video_prompt") == choice:
                return
            cfg["video_prompt"] = choice
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
            simple_actions=[
                ("仅当前场景", lambda: self._run_clip_video("still", "single")),
                ("本集从这一场起", lambda: self._run_clip_video("still", "story")),
                ("全部场景", lambda: self._run_clip_video("still", "all")),
                ("WAN 生成（以后再用）", lambda: self._run_clip_video("wan", "single")),
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
            cross_episodes: bool = False,
        ) -> None:
            """提交：手工 LLM 窗口 CLI自动 → NotebookLM Studio（kind）→ 下载 → 系统程序打开。"""
            import os
            from pathlib import Path

            working = config.WORKING_DIR

            def _open_file(path: str) -> None:
                """Studio 下载结果移到 D:\\AI_MEDIA\\working（同名覆盖）。PDF 走拆页预览 / 分配；其余直接打开。"""
                import shutil

                try:
                    os.makedirs(working, exist_ok=True)
                    dest = os.path.join(working, os.path.basename(path))
                    if os.path.abspath(dest) != os.path.abspath(path):
                        if os.path.exists(dest):
                            os.remove(dest)
                        shutil.move(path, dest)
                    path = dest
                except OSError as exc:
                    print(f"⚠️ 移动到 working 失败，用原位置：{exc}")
                if path.lower().endswith(".pdf"):
                    self.root.after(
                        50,
                        lambda p=path: self._on_media_drop_pdf(p, origin="全集生成", cross_episodes=cross_episodes),
                    )
                    return
                try:
                    os.startfile(path)
                except OSError as exc:
                    messagebox.showwarning("打开失败", f"打不开：{exc}\n{path}", parent=self.root)

            extra = {"output": kind}
            # 画面比例用项目的宽高（1920×1080 → 16:9，1080×1920 → 9:16）。
            _pc = project_manager.PROJECT_CONFIG or {}
            extra["video_size"] = project_manager.video_size_key(_pc.get("video_width"), _pc.get("video_height"))
            if notebook_url:
                extra["notebook_url"] = notebook_url
            if source_pdf:
                extra["source_pdf"] = source_pdf  # CLI自动：先上传为笔记本来源，再生成
            if actor_pdf:
                extra["actor_pdf"] = actor_pdf  # 本集人物：content.pdf 之后上传
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
