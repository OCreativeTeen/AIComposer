"""SceneDisplayMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import os
import tkinter as tk
import tkinter.messagebox as messagebox
import time
import config
import config_prompt
import project_manager
from gui.choice_dialog import ask_speaking_concise_review_dialog


class SceneDisplayMixin:
    def refresh_gui_scenes(self):
        """刷新场景列表（节流：每秒最多执行一次）"""
        current_time = time.time()
        time_since_last = current_time - self.refresh_gui_scenes_last_time
        
        # 如果距离上次执行不到1秒，取消之前的延迟任务，安排新的延迟执行
        if time_since_last < 1.0:
            # 取消之前的延迟任务（如果存在）
            if self.refresh_gui_scenes_after_id is not None:
                self.root.after_cancel(self.refresh_gui_scenes_after_id)
            
            # 安排延迟执行，确保距离上次执行至少1秒
            delay_ms = int((1.0 - time_since_last) * 1000)
            self.refresh_gui_scenes_after_id = self.root.after(delay_ms, self._refresh_gui_scenes_impl)
            return
        
        # 如果距离上次执行超过1秒，立即执行
        self._refresh_gui_scenes_impl()

    def _refresh_gui_scenes_impl(self):
        """刷新场景列表的实际实现"""
        self.refresh_gui_scenes_last_time = time.time()
        self.refresh_gui_scenes_after_id = None
        
        # self.workflow.load_scenes()
        if self.current_scene_index >= len(self.workflow.scenes) :
            self.current_scene_index = 0

        # 清理所有轨道的 VideoCapture（避免使用旧场景的视频）
        self.cleanup_track_video_captures()

        # 检查现有图像
        self.update_scene_display()
        
        # 更新视频进度显示
        self.update_video_progress_display()

        # 重置轨道偏移量到新场景的起始位置
        self.reset_track_offset()

        # 延迟加载第一帧，确保canvas已完全渲染
        self.load_all_images_preview()

        self.update_add_scene_insert_buttons_state()

    def _extension_scene_value_to_combo_string(self, ext_val):
        """将 JSON 中的 extension 数值映射为 extension_values 中的项；无法匹配则 '0'。"""
        try:
            fv = float(ext_val) if ext_val is not None else 0.0
        except (TypeError, ValueError):
            fv = 0.0
        allowed = getattr(self, "extension_values", ("0", "0.4", "0.6", "0.8"))
        for s in allowed:
            try:
                if abs(fv - float(s)) < 1e-6:
                    return s
            except ValueError:
                continue
        return "0"

    def update_scene_display(self):
        """更新场景显示"""
        if len(self.workflow.scenes) == 0:
            self.scene_label.config(text="0 / 0")
            self._refresh_marker_label()
            self._refresh_episode_label()
            self.clear_scene_fields()
            self.clear_video_preview()
            self._refresh_speech_span_bar()
            return

        self._scene_widgets_loading = True
        try:
            self._update_scene_display_impl()
        finally:
            self._scene_widgets_loading = False
            self._refresh_speech_span_bar()

    def _refresh_episode_label(self):
        """本集内容左上角：当前场景属于第几集。"""
        label = getattr(self, "episode_label", None)
        if label is None:
            return
        text = "第 - 集"
        wf = getattr(self, "workflow", None)
        if wf and wf.scenes:
            scene = wf.get_scene_by_index(self.current_scene_index)
            if isinstance(scene, dict):
                text = wf.episode_label(wf.scene_group(scene), always_id=True)
        label.config(text=text)

    def _update_scene_display_impl(self):
        self.scene_label.config(text=f"{self.current_scene_index + 1} / {len(self.workflow.scenes)}")
        self._refresh_marker_label()
        self._refresh_episode_label()
        scene_data = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_data:
            self._scene_form_scene = None
            return
        self._scene_form_scene = scene_data

        # 设置宣传复选框状态
        clip_animation = scene_data.get("clip_animation", "S2V")
        self.clip_animate.set(clip_animation)
        
        # 加载当前场景的图像类型设置
        narration_animate = scene_data.get("narration_animation", "S2V")
        self.narration_animation.set(narration_animate)

        self.extension_var.set(self._extension_scene_value_to_combo_string(scene_data.get("extension", 0)))

        speaking_text = scene_data.get("speaking", "") or ""
        old_voiceover = (scene_data.get("voiceover") or "").strip()
        if old_voiceover and "<" not in speaking_text:
            if speaking_text.strip():
                speaking_text = speaking_text.rstrip() + f" <2> {old_voiceover}"
            else:
                speaking_text = f"<1> {old_voiceover}"
            scene_data["speaking"] = speaking_text
            scene_data.pop("voiceover", None)
            self.workflow.save_scenes_to_json()
        if project_manager.scene_is_story_act(scene_data):
            speaking_text = project_manager.speaking_box_text(scene_data)  # Story Act：显示 story_content
        self.scene_speaking.delete("1.0", tk.END)
        self.scene_speaking.insert("1.0", speaking_text)

        normalized_actor = project_manager.normalize_actor_text(scene_data.get("actor", ""))
        if normalized_actor != (scene_data.get("actor") or "").strip():
            scene_data["actor"] = normalized_actor
            self.workflow.save_scenes_to_json()
        self._set_actor_text(normalized_actor)

        self.scene_visual.delete("1.0", tk.END)
        self.scene_visual.insert("1.0", scene_data.get("visual", ""))

        self.scene_caption.delete("1.0", tk.END)
        self.scene_caption.insert("1.0", scene_data.get("caption", ""))
        if scene_data.pop("narrator", None) is not None:
            self.workflow.save_scenes_to_json()
        #self.scene_cinematography.delete("1.0", tk.END)
        # 如果 cinematography 是字典，格式化显示；如果是字符串，直接显示
        #cinematography_value = scene_data.get("cinematography", "")
        #if isinstance(cinematography_value, dict):
        #    self.scene_cinematography.insert("1.0", json.dumps(cinematography_value, ensure_ascii=False, indent=2))
        #else:
        #    self.scene_cinematography.insert("1.0", cinematography_value)
        status = scene_data.get("clip_status", "")
        self._scene_title_label.config(text=f"本场内容: {status}" if status else "本场内容")
        self._refresh_speech_estimate(scene_data)
        self.video_edit_frame.update()

    def _refresh_speech_estimate(self, scene=None) -> None:
        """t165u: 工具栏「音频转录」后面的讲话长度估算。"""
        lbl = getattr(self, "_speech_est_label", None)
        if lbl is None:
            return
        try:
            lbl.config(text=config_prompt.scene_speech_label(scene) if isinstance(scene, dict) else "")
        except Exception as exc:  # noqa: BLE001
            lbl.config(text="")
            print(f"⚠️ 讲话长度估算失败：{exc}")

    def clear_scene_fields(self):
        self._scene_widgets_loading = True
        try:
            self.clip_animate.set("")
            self.extension_var.set("0")

            self.scene_speaking.delete("1.0", tk.END)
            self._set_actor_text("")
            self.scene_visual.delete("1.0", tk.END)
            self.scene_caption.delete("1.0", tk.END)
            self._scene_form_scene = None
        finally:
            self._scene_widgets_loading = False

    def on_scene_text_review(
        self,
        text_field,
        event=None,
        *,
        title="审阅文案",
        source_field=None,
        remix_system_prompt=None,
    ):
        """双击左键：审阅 / Remix 文案，确定后写回当前场景对应字段。
        t207u: 「Remix (全集)」= 从这一场到本集最后一场，每场按单场 Remix 做，结果按「确定」写回。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return "break"
        lang = getattr(self.workflow, "language", None) or "tw"
        lang_label = config.llm_language_label(lang)
        src_field = source_field or text_field
        prompt_tpl = remix_system_prompt or config_prompt.SPEAKING_CONCISE_PROMPT
        system_prompt = prompt_tpl.format(language=lang_label)
        is_visual = text_field == "visual" and not remix_system_prompt

        def source_of(sc) -> str:
            return config.chinese_convert((sc.get(src_field) or ""), lang)

        def make_remix(sc):
            actor_seed = (sc.get("actor") or "").strip()

            def _remix_text(t: str) -> str:
                out = self.llm_api_local.generate_text(system_prompt, (t or "").strip())
                return config.chinese_convert(out, lang)

            def _remix(t: str):
                if not is_visual:
                    return _remix_text(t)
                # t161u / t223u Remix path: same remix_scene_full as new-project cover analysis —
                # actors first (count/seats, actor-is-truth), then visual (keep story plot).
                try:
                    from utility.file_util import get_file_path
                    from utility.visual_remix import remix_scene_full

                    image = get_file_path(sc, "clip_image")
                    res = remix_scene_full(t, image, actor_text=actor_seed, language_label=lang_label,
                                           speaking=sc.get("speaking") or "")
                    print(f"🖼 视觉 Remix：带起始图 {os.path.basename(image)} 交给 Strata 看图改写"
                          + (f"；补上说话人 {res['missing']}" if res.get("missing") else ""))
                    return config.chinese_convert(res["visual"], lang), config.chinese_convert(res["actor"], lang)
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 视觉 Remix 看图失败，改用纯文字：{exc}")
                    speaking = (sc.get("speaking") or "").strip()
                    if not speaking:
                        return _remix_text(t)  # 没有讲话：和以前一样
                    try:  # t199u: 纯文字也按讲话同步
                        from utility.visual_remix import remix_visual_text

                        names = [config_prompt._speaker_identity(r)[0] for r in config_prompt._scene_speakers(sc)]
                        return config.chinese_convert(
                            remix_visual_text(t, names=names, language_label=lang_label, speaking=speaking), lang)
                    except Exception as exc2:  # noqa: BLE001
                        print(f"⚠️ 视觉 Remix 按讲话的纯文字改写失败，用原来的纯文字：{exc2}")
                        return _remix_text(t)

            return _remix

        def apply_result(sc, confirmed, *, save=True):
            """和「确定」一样写回（视觉时连 人物）；sc 是界面当前场才刷新输入框。"""
            import project_manager

            cur = self.workflow.get_scene_by_index(self.current_scene_index)
            if isinstance(confirmed, tuple):  # t161u: 视觉 + 人物
                confirmed, new_actor = (tuple(confirmed) + (None,))[:2]
                new_actor = project_manager.normalize_actor_text(new_actor or "")
                if new_actor and new_actor != (sc.get("actor") or "").strip():
                    sc["actor_before_remix"] = sc.get("actor") or ""
                    sc["actor"] = new_actor
                    if cur is sc:
                        self._set_actor_text(new_actor)
                    print(f"🖼 视觉 Remix：人物 → {new_actor}")
            confirmed = (confirmed or "").strip()
            if not confirmed:
                return False
            sc[text_field] = confirmed
            widget = {"speaking": self.scene_speaking, "visual": self.scene_visual,
                      "caption": self.scene_caption}.get(text_field)
            if widget is not None and cur is sc:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", confirmed)
            if save:
                self.workflow.save_scenes_to_json()
            return True

        def remix_all(dlg) -> bool:
            story = [s for s in (self.workflow.scenes_in_story(scene) or []) if isinstance(s, dict)]
            start = next((i for i, s in enumerate(story) if s is scene), None)
            targets = story[start:] if start is not None else [scene]
            if not messagebox.askyesno(
                "Remix (全集)",
                f"从这一场到本集最后一场，共 {len(targets)} 场，逐场 Remix「{title.split('—')[-1].strip()}」，"
                "结果直接写回（不逐场审阅）。\n继续？",
                parent=dlg,
            ):
                return False
            self._remix_all_scenes(targets, text_field, source_of, make_remix, apply_result)
            return True

        initial_edit = config.chinese_convert((scene.get(text_field) or ""), lang) if source_field else None
        confirmed = ask_speaking_concise_review_dialog(
            self.root,
            source_of(scene),
            remix_fn=make_remix(scene),
            title=title,
            initial_edit=initial_edit,
            extra_label="人物（Remix 后的建议，可修改；确定时一起写进 人物 栏）" if is_visual else None,
            extra_initial=(scene.get("actor") or "").strip(),
            remix_all_fn=remix_all,
        )
        if confirmed is None:
            return "break"
        apply_result(scene, confirmed)
        return "break"

    def _remix_all_scenes(self, targets, text_field, source_of, make_remix, apply_result) -> None:
        """t207u: 后台逐场 Remix（工人线程只调 LLM，不碰 Tk），每场结果在 UI 线程写回并保存；失败跳过，最后汇报。"""
        import queue
        import threading
        from tkinter import ttk

        n = len(targets)
        win = tk.Toplevel(self.root)
        win.title(f"Remix (全集) · {n} 场")
        win.transient(self.root)
        var = tk.StringVar(value="准备 …")
        ttk.Label(win, textvariable=var, wraplength=420, padding=12).pack(fill=tk.BOTH)
        stop = {"flag": False}
        ttk.Button(win, text="停止（做完这一场后）", command=lambda: stop.update(flag=True)).pack(pady=(0, 10))
        q: "queue.Queue" = queue.Queue()
        jobs = [(sc, source_of(sc), make_remix(sc)) for sc in targets]  # UI 线程里先取好每场的原文
        stats = {"ok": 0, "failed": []}

        def label(sc, k):
            return f"{k}/{n}（场景 id {sc.get('id')}）"

        def work():
            for k, (sc, raw, fn) in enumerate(jobs, 1):
                if stop["flag"]:
                    q.put(("stopped", n - k + 1, None, None))
                    break
                q.put(("progress", k, sc, None))
                if not (raw or "").strip():
                    q.put(("fail", k, sc, "原文是空的"))
                    continue
                try:
                    q.put(("ok", k, sc, fn(raw)))
                except Exception as exc:  # noqa: BLE001
                    q.put(("fail", k, sc, exc))
            q.put(("done", 0, None, None))

        def poll():
            while True:
                try:
                    kind, k, sc, val = q.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    var.set(f"Remix 第 {k}/{n} 场 …")
                    print(f"🔁 Remix (全集) {text_field}：{label(sc, k)} 开始")
                elif kind == "ok":
                    try:
                        if apply_result(sc, val):
                            stats["ok"] += 1
                            print(f"✅ Remix (全集) {text_field}：{label(sc, k)} 已写回")
                        else:
                            stats["failed"].append(f"{label(sc, k)}：结果是空的")
                    except Exception as exc:  # noqa: BLE001
                        stats["failed"].append(f"{label(sc, k)}：写回失败 {exc}")
                elif kind == "fail":
                    stats["failed"].append(f"{label(sc, k)}：{val}")
                    print(f"⚠️ Remix (全集) {text_field}：{label(sc, k)} 失败 {val}")
                elif kind == "stopped":
                    stats["failed"].append(f"其余 {k} 场：已停止")
                elif kind == "done":
                    try:
                        win.destroy()
                    except tk.TclError:
                        pass
                    note = f"Remix (全集) 完成：{stats['ok']}/{n} 场已写回。"
                    if stats["failed"]:
                        note += "\n\n没处理 / 失败：\n" + "\n".join(stats["failed"][:30])
                    print(note)
                    messagebox.showinfo("Remix (全集)", note, parent=self.root)
                    return
            self.root.after(200, poll)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, poll)


    def update_current_scene(self, event=None):
        if getattr(self, "_scene_widgets_loading", False):
            return None
        if not getattr(self, "workflow", None):
            return None
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return None
        # 输入框还停在上一场时，不能写进已经滑到这个位置的下一场。
        bound = getattr(self, "_scene_form_scene", None)
        if bound is not None and bound is not scene:
            return None
        
        # 处理 cinematography 字段：尝试解析 JSON 字符串
        #cinematography_text = self.scene_cinematography.get("1.0", tk.END).strip()
        #cinematography_value = cinematography_text
        #if cinematography_text:
        #    try:
                # 尝试解析为 JSON 对象
        #        cinematography_value = json.loads(cinematography_text)
        #    except json.JSONDecodeError:
        #        # 如果不是有效 JSON，保持为字符串
        #        cinematography_value = cinematography_text
        ext_val = float(self.extension_var.get() or 0)
        if ext_val <= 0:
            if "extension" in scene:
                del scene["extension"]
        else:
            scene["extension"] = ext_val

        project_manager.store_speaking_box_text(scene, self.scene_speaking.get("1.0", tk.END))
        self._refresh_speech_estimate(scene)  # t165u
        scene.update({
            "actor": (self._actor_text or "").strip(),
            "visual": self.scene_visual.get("1.0", tk.END).strip(),
            "caption": self.scene_caption.get("1.0", tk.END).strip(),

            "clip_animation": self.clip_animate.get(),
            "narration_animation": self.narration_animation.get()
        })
        scene.pop("visual_style", None)
        scene.pop("title_font", None)
        scene.pop("narrator", None)
        scene.pop("voiceover", None)
        self.workflow.save_scenes_to_json()
        return scene

    def on_video_title_change(self, event=None):
        """当视频标题发生变化时的回调函数"""
        # 如果正在加载配置，不要自动保存
        gui_title = self.video_title.get().strip()
        if gui_title and gui_title != "......":
            gui_title = config.chinese_convert(gui_title, self.workflow.language)
            self.workflow.title = gui_title
            print(f"🏷️ Workflow title updated: {gui_title}")
            # save summary to project_manager.PROJECT_CONFIG
            project_manager.PROJECT_CONFIG["video_title"] = gui_title
            self.save_config()

    def on_video_title_double_click(self, event=None):
        """双击「标题」：问要不要按场景内容重新生成项目名称建议；是 → 选名称后走原来的改名保存。"""
        if not messagebox.askyesno(
            "项目名称", "要根据场景内容重新生成项目名称建议吗？", parent=self.root
        ):
            return None
        from gui.project_title_suggest import ask_project_title

        scenes = [s for s in (getattr(self.workflow, "scenes", None) or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showinfo("项目名称", "还没有场景内容。", parent=self.root)
            return "break"
        current = (self.video_title.get() or "").strip()

        def _chosen(name: str) -> None:
            # 原来的改名路径：标题栏 → workflow.title + PROJECT_CONFIG["video_title"] + save_config（同步 project_profile）
            self.video_title.delete(0, tk.END)
            self.video_title.insert(0, name)
            self.on_video_title_change()
            new_name = (project_manager.PROJECT_CONFIG or {}).get("video_title") or name
            ok, list_path, err = project_manager.save_list_row_project_name_for_config(
                project_manager.PROJECT_CONFIG, new_name
            )
            if ok:
                print(f"✅ 项目名称已写回列表：{list_path}")
            else:
                messagebox.showwarning("项目名称", f"名称已改，但没有写回列表行：{err}", parent=self.root)

        ask_project_title(self.root, current=current, scenes=scenes, on_chosen=_chosen)
        return "break"

    def on_scene_field_enter(self, event=None):
        """当在场景编辑字段中按下Ctrl+Enter时的回调"""
        # 保存当前场景信息到JSON并传播到相同raw_scene_index的场景
        self.update_current_scene()
        return "break"  # 阻止默认的换行行为

    def _cancel_scene_debounce_timer(self):
        tid = getattr(self, "_save_timer", None)
        if tid:
            try:
                self.root.after_cancel(tid)
            except (ValueError, tk.TclError):
                pass
        self._save_timer = None

    def on_scene_field_return_commit(self, event=None):
        """多行文本框内按 Enter：立即写回当前场景与 JSON（仍插入换行）。"""
        if getattr(self, "_scene_widgets_loading", False):
            return
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            return
        self._cancel_scene_debounce_timer()
        self.update_current_scene()

    def on_scene_field_focus_out(self, event=None):
        """当场景编辑字段失去焦点时的回调"""
        # 延迟保存以避免频繁操作（仅取消有效的 after id，避免 None/已失效 id 触发 ValueError）
        self._cancel_scene_debounce_timer()
        self._save_timer = self.root.after(500, lambda: self.update_current_scene())

    def _on_extension_change(self):
        """延长秒数变化：0 则不写 extension 字段，否则写入 float"""
        if not self.workflow.scenes or self.current_scene_index >= len(self.workflow.scenes):
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        val = float(self.extension_var.get() or 0)

        def _apply_extension_to_scene(target, ext_val):
            if ext_val <= 0:
                if "extension" in target:
                    del target["extension"]
            else:
                target["extension"] = ext_val

        # 选一次，写进每一个场景的 extension，不再逐场重选，也不再询问。
        for s in self.workflow.scenes:
            if isinstance(s, dict):
                _apply_extension_to_scene(s, val)
        _apply_extension_to_scene(scene, val)

        self.workflow.save_scenes_to_json()
