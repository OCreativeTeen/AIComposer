"""FinalizePublishMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import sys
import subprocess
import json
import threading
from datetime import datetime
import uuid
import config
import config_prompt
from project_manager import refresh_scene_media, save_project_config
import project_manager
from utility.file_util import get_file_path, make_safe_file_name
from gui.wan_prompt_editor_dialog import show_wan_prompt_editor
from utility.ffmpeg_processor import resolve_watermark_for_project, resolve_headmark_for_project
from gui.downloader import ask_publish_schedule_dialog
from gui.publish_metadata_dialog import ask_publish_metadata_then_schedule, scene_content_list_for_publish


class FinalizePublishMixin:
    def _reveal_published_video(self, path: str) -> None:
        from gui.downloader import _open_feature_media_in_explorer

        _open_feature_media_in_explorer(path)

    def log_to_output(self, output_widget, message):
        """向输出控件写入日志信息"""
        if output_widget and hasattr(output_widget, 'insert'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            output_widget.insert(tk.END, f"[{timestamp}] {message}\n")
            output_widget.see(tk.END)
            output_widget.update_idletasks()

    def start_status_update_timer(self):
        """启动状态更新定时器"""
        # 如果已有定时器，先取消
        if self.status_update_timer_id is not None:
            self.root.after_cancel(self.status_update_timer_id)
        
        self.update_status_and_check_completion()
        # 每5秒更新一次状态，并保存定时器ID
        self.status_update_timer_id = self.root.after(5000, self.start_status_update_timer)

    def update_status_and_check_completion(self):
        """更新状态并检查任务完成情况"""
        # 检查是否有新完成的任务
        newly_completed = []
        for task_id, task_info in list(self.tasks.items()):
            if task_info["status"] in ["完成", "失败"] and task_id not in self.last_notified_tasks:
                newly_completed.append((task_id, task_info))
                self.last_notified_tasks.add(task_id)
                
                # 将完成的任务移到完成列表
                self.completed_tasks.append({
                    "id": task_id,
                    "info": task_info.copy(),
                    "completion_time": datetime.now()
                })
        
        # 通知新完成的任务
        for task_id, task_info in newly_completed:
            """通知任务完成"""
            task_type = task_info.get("type", "未知任务")
            task_status = task_info.get("status", "未知状态")
            pid = task_info.get("pid", "")
            
            if task_status == "完成":
                title = "✅ 任务完成"
                message = f"任务类型: {task_type}\n项目ID: {pid}\n状态: 成功完成"
                if "result" in task_info:
                    message += f"\n结果: {task_info['result']}"
            else:
                title = "❌ 任务失败"
                message = f"任务类型: {task_type}\n项目ID: {pid}\n状态: 执行失败"
                if "error" in task_info:
                    message += f"\n错误: {task_info['error']}"
            
            # 显示通知对话框（video_finalize 成功时多一个「播放视频」）
            if task_status == "完成" and task_type == "video_finalize":
                self._show_finalize_done_dialog(title, message, pid)
            else:
                messagebox.showinfo(title, message)



        
        # 检查生成的视频（后台持续检查）
        self.check_generated_videos_background()

    def start_video_check_thread(self):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return  # 未选择项目时（如 YT 管理）工作流为空是正常的，静默跳过

        if self.video_check_running:
            print("⚠️ 后台检查线程已在运行")
            return
        
        self.video_check_running = True
        self.video_check_stop_event.clear()
        
        def video_check_loop():
            """单例后台线程的主循环"""
            print("🚀 启动后台视频检查线程")
            
            while not self.video_check_stop_event.is_set():
                try:
                    self._perform_video_check()
                except Exception as e:
                    print(f"❌ 后台检查线程出错: {str(e)}")
                # 出错后等待5秒再继续
                self.video_check_stop_event.wait(5)
            
            print("🛑 后台视频检查线程已停止")
            self.video_check_running = False
        
        # 创建并启动daemon线程
        self.video_check_thread = threading.Thread(target=video_check_loop, daemon=True)
        self.video_check_thread.start()

    def stop_video_check_thread(self):
        """停止后台视频检查线程"""
        if self.video_check_running:
            print("🛑 正在停止后台视频检查线程...")
            self.video_check_stop_event.set()
            if self.video_check_thread:
                self.video_check_thread.join(timeout=2)

    def _perform_video_check(self):
        """执行视频检查任务（由单例线程调用）"""
        #animate_gen_list = []
        #for scene_index, scene in enumerate(self.workflow.scenes):
        #    #clip_animation = scene.get("clip_animation", "")
        #    #if clip_animation in config_prompt.ANIMATE_SOURCE and clip_animation != "":
        #    scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "clip", "", False)
        #    animate_gen_list.append((scene_name, "clip", scene))
        #    #narration_animation = scene.get("narration_animation", "")
        #    #if narration_animation in config_prompt.ANIMATE_SOURCE and narration_animation != "":
        #    scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "narration", "", False)
        #    animate_gen_list.append((scene_name, "narration", scene))

        #if animate_gen_list == []:
        #    return
        
        try:
            # 1. 检查 X:\output 中新生成的原始视频（监控逻辑）
            self.media_scanner.scanning("X:\\output")                      # clip_p202512231259_10005_S2V__00003-audio.mp4
            #self.media_scanner.scanning("Z:\\wan_video\\output_mp4")                     # clip_p202512231259_10005_INT_25115141_30__00001.mp4  ~~~ interpolate
            self.media_scanner.scanning("W:\\wan_video\\output_mp4")      # clip_p20251208_10708_ENH_13231028_0_.mp4   clip_p202512231259_10005_EHN_.mp4  ~~~ enhance

            self.workflow.save_scenes_to_json()

        except Exception as e:
            # 忽略单个场景的错误，继续检查其他场景
            print(f"❌ 后台检查线程出错: {str(e)}")
            pass

    def check_generated_videos_background(self):
        """定时器调用此方法，但不再创建新线程（单例线程已在运行）"""
        if not hasattr(self, 'workflow') or self.workflow is None:
            return  # 未选择项目时（如 YT 管理）静默跳过
        # 检查单例线程是否还在运行，如果没有则重启
        if not self.video_check_running or not self.video_check_thread or not self.video_check_thread.is_alive():
            print("⚠️ 检测到后台线程未运行，正在重启...")
            self.start_video_check_thread()

    def enhance_clip(self, track:str):
        """已停用。界面上的「增主轨」已去掉。sd_processor.enhance_clip 还留着。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, track, "30")
        self.refresh_gui_scenes()

    def publish_video(self):
        lang = getattr(self.workflow, "language", None) or "zh"
        pc = project_manager.PROJECT_CONFIG or {}
        scenes = getattr(self.workflow, "scenes", None) or []

        gui_title = ""
        if hasattr(self, "video_title"):
            gui_title = (self.video_title.get() or "").strip()
        wf_title = (getattr(self.workflow, "title", None) or "").strip()
        ch_name = config.get_channel_config(self.workflow.channel)["channel_name"]
        default_title = ch_name + "：" + (gui_title or wf_title)

        list_row = project_manager.load_video_detail_row_for_config(pc) or {}
        item_summary = (list_row.get("summary") or pc.get("summary") or "")
        analyzed = pc.get("analyzed_content") or list_row.get("analyzed_content") or ""
        review_script = config.read_transcript_text_from_video_detail(list_row)

        def _save_regenerated_summary(text: str) -> None:
            """重新生成的 summary 写回主题分表里本项目那一行（外层 summary），内存里的配置和行一起改。"""
            ok, list_path, err = project_manager.save_list_row_summary_for_config(pc, text)
            if isinstance(list_row, dict):
                list_row["summary"] = text
            if ok:
                print(f"✅ summary 已写回列表：{list_path}")
            else:
                raise RuntimeError(f"{err}（{list_path or '没有主题分表'}）")

        flow = ask_publish_metadata_then_schedule(
            self.root,
            language=lang,
            default_title=default_title,
            scene_content_list=scene_content_list_for_publish(
                language=lang,
                project_config=pc,
                workflow_scenes=scenes,
            ),
            analyzed_content=analyzed if isinstance(analyzed, str) else str(analyzed or ""),
            review_script_text=review_script,
            summary_text=item_summary if isinstance(item_summary, str) else str(item_summary or ""),
            poem_text=(
                (pc.get("poem") or "").strip()
                or (
                    (project_manager.load_video_detail_row_for_config(pc) or {}).get(
                        "poem"
                    )
                    or ""
                ).strip()
            ),
            video_detail=list_row or None,
            on_summary_regenerated=_save_regenerated_summary,
            generate_text_fn=self.llm_api_local.generate_text,
            schedule_dialog_fn=ask_publish_schedule_dialog,
            caption_scenes=scenes,
            metadata_dialog_title="上传视频 — 标题与描述",
        )
        if flow is None:
            return
        conv = config.chinese_convert(flow["title"].replace("\n", " "), lang)
        title_slug = make_safe_file_name(conv.replace("\n", " "), title_length=180)
        mode = flow["mode"]
        publish_at = flow["publish_at"]
        try:
            tg_lines = self.workflow.upload_video(
                title_slug,
                publish_at=publish_at,
                description=flow["description"],
                telegram_title=conv,
            )
        except Exception as e:
            messagebox.showerror("上传失败", str(e), parent=self.root)
            return
        tg_block = ""
        if tg_lines:
            tg_block = "\n\n--- Telegram ---\n" + "\n".join(tg_lines)
        if mode == "scheduled":
            messagebox.showinfo(
                "提示",
                "视频已以「私有 + 定时公开」上传。\n"
                "到点后将按 YouTube 规则自动公开。\n\n"
                "若需「首映 Premiere」或改为不公开列出，请在 YouTube Studio 中调整。"
                + tg_block,
                parent=self.root,
            )
        else:
            msg = "视频发布成功！"
            if vid := (project_manager.PROJECT_CONFIG or {}).get("published_youtube_video_id"):
                msg += f"\nhttps://www.youtube.com/watch?v={vid}"
            messagebox.showinfo("提示", msg + tg_block, parent=self.root)

    def _show_finalize_done_dialog(self, title, message, pid=None):
        """任务完成通知：OK + 播放视频（复用 play_finalize_video）。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=message, justify=tk.LEFT).pack(anchor="w", pady=(0, 12))
        btns = ttk.Frame(frame)
        btns.pack(anchor="e")

        def _play():
            dlg.destroy()
            self.play_finalize_video(pid=pid)

        ttk.Button(btns, text="播放视频", command=_play).pack(side=tk.LEFT, padx=(0, 8))
        ok = ttk.Button(btns, text="OK", command=dlg.destroy)
        ok.pack(side=tk.LEFT)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.update_idletasks()
        try:
            x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        ok.focus_set()
        dlg.grab_set()
        self.root.wait_window(dlg)

    def play_finalize_video(self, pid=None):
        """与 magic_workflow.finalize_video 相同的路径规则；用系统默认播放器打开（独立窗口、含声音）。"""
        final_path = config.publish_final_video_path(pid or self.workflow.pid)
        if not os.path.isfile(final_path):
            messagebox.showwarning(
                "Video播放",
                f"未找到最终成片：\n{final_path}\n请先使用「Video生成」导出。",
                parent=self.root,
            )
            return
        try:
            if os.name == "nt":
                os.startfile(os.path.normpath(final_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", final_path], start_new_session=True)
            else:
                subprocess.Popen(["xdg-open", final_path], start_new_session=True)
        except Exception as e:
            messagebox.showerror("Video播放", f"无法打开播放器：{e}", parent=self.root)

    def _ask_final_video_options(self):
        """最终视频生成方式，上面带一个速度。返回 (mode, speed)，取消返回 None。"""
        pc = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
        try:
            saved = float(pc.get("final_video_speed") or 1.0)
        except (TypeError, ValueError):
            saved = 1.0
        saved = max(0.7, min(1.3, saved))

        dlg = tk.Toplevel(self.root)
        dlg.title("最终视频生成方式")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()
        result = {"value": None}

        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="最终视频生成方式", font=("Arial", 12, "bold")).pack(pady=(4, 10))

        speed_row = ttk.Frame(frame)
        speed_row.pack(pady=(0, 10))
        ttk.Label(speed_row, text="速度").pack(side=tk.LEFT, padx=(0, 6))
        speed_var = tk.StringVar(value=f"{saved:.2f}")
        ttk.Combobox(
            speed_row,
            textvariable=speed_var,
            values=list(self._FINAL_SPEED_CHOICES),
            width=6,
        ).pack(side=tk.LEFT)
        ttk.Label(speed_row, text="倍。每一场先按这个速度变快或变慢，再延长，再转场。").pack(
            side=tk.LEFT, padx=(6, 0)
        )

        def pick(mode: str) -> None:
            try:
                speed = float((speed_var.get() or "1").strip())
            except ValueError:
                messagebox.showwarning("速度", "速度要写成数字，例如 0.9 或 1.1。", parent=dlg)
                return
            if speed < 0.5 or speed > 2.0:
                messagebox.showwarning("速度", "速度请写在 0.5 到 2.0 之间。", parent=dlg)
                return
            result["value"] = (mode, speed)
            dlg.destroy()

        for mode, label in (
            ("plain_zero", "无转场，用ZERO音轨"),
            ("plain", "无转场 (简单拼接)"),
            ("transitions", "带转场"),
            ("transitions_zero", "带转场，用ZERO音轨"),
        ):
            ttk.Button(frame, text=label, width=44, command=lambda m=mode: pick(m)).pack(pady=3)
        ttk.Button(frame, text="取消", width=20, command=dlg.destroy).pack(pady=(12, 2))

        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dlg.winfo_reqwidth()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dlg.winfo_reqheight()) // 2)
        dlg.geometry(f"+{x}+{y}")
        dlg.wait_window()
        picked = result["value"]
        if picked and isinstance(project_manager.PROJECT_CONFIG, dict):
            project_manager.PROJECT_CONFIG["final_video_speed"] = round(picked[1], 3)
            save_project_config(parent=self.root)
        return picked

    def run_finalize_video(self):
        picked = self._ask_final_video_options()
        if picked is None:
            return
        mode, final_speed = picked
        if mode == "transitions":
            with_transitions, replace_final_audio_with_zero = True, False
        elif mode == "transitions_zero":
            with_transitions, replace_final_audio_with_zero = True, True
        elif mode == "plain":
            with_transitions, replace_final_audio_with_zero = False, False
        else:
            with_transitions, replace_final_audio_with_zero = False, True

        pid = self.get_pid()
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "video_finalize",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }

        def run_task():
            try:
                start, end = self._marker_scene_bounds()
                self.log_to_output(
                    self.video_output,
                    f"视频生成：第 {start + 1}–{end + 1} 场，速度 {final_speed:.2f} 倍",
                )
                self.workflow.finalize_video(
                    with_transitions,
                    replace_final_audio_with_zero,
                    scene_start=start,
                    scene_end=end,
                    speed=final_speed,
                )
                self.log_to_output(self.video_output, "✅ 最终视频生成完成！")
                self.tasks[task_id]["status"] = "完成"
                final_path = config.publish_final_video_path(self.workflow.pid)
                self.root.after(0, lambda p=final_path: self._reveal_published_video(p))
            except Exception as e:
                self.log_to_output(self.video_output, f"❌ 最终视频生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)

        threading.Thread(target=run_task, daemon=True).start()

    def _open_finalize_menu(self) -> None:
        picked = self._ask_near_choices(
            self.btn_finalize,
            "成片",
            [
                ("generate", "视频生成"),
                ("publish", "视频发布"),
                ("play", "视频播放"),
                ("demo", "演示"),
            ],
        )
        if picked == "generate":
            self.run_finalize_video()
        elif picked == "publish":
            self.publish_video()
        elif picked == "play":
            self.play_finalize_video()
        elif picked == "demo":
            self.start_demo_playthrough()

    def _open_clean_menu(self) -> None:
        picked = self._ask_near_choices(
            self.btn_clean,
            "清理",
            [("media", "清媒体"), ("wan", "清WAN")],
        )
        if picked == "media":
            self.clean_media()
        elif picked == "wan":
            self.clean_wan()

    def clean_wan(self):
        self.workflow.clean_folder("/wan_video/interpolated")
        self.workflow.clean_folder("/wan_video/enhanced")
        self.workflow.clean_folder("/wan_video/original")

    def clean_media(self):
        """媒体清理"""
        self.workflow.clean_media()
        self.workflow.save_scenes_to_json()
        messagebox.showinfo("成功", "媒体清理成功！")

    def reverse_video(self):
        """翻转视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self._backup_clip_to_scene_back(current_scene)
        oldv, newv = refresh_scene_media(current_scene, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.reverse_video(oldv), newv)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

    def mirror_video(self):
        """镜像视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self._backup_clip_to_scene_back(current_scene)
        oldv, newv = refresh_scene_media(current_scene, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.mirror_video(oldv), newv)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

    def _resolve_watermark_config(self):
        """解析水印 PNG 路径与选项（与 NotebookLM add_watermark_cli 的 config.watermark 一致）。"""
        return resolve_watermark_for_project(project_manager.PROJECT_CONFIG or {})

    def _resolve_headmark_config(self):
        """解析左上角角标：优先 PROJECT_CONFIG.headmark，缺字段时并入当前频道 headmark。"""
        return resolve_headmark_for_project(project_manager.PROJECT_CONFIG or {})

    def _apply_watermark_to_flat_image_webp(self, webp_path: str) -> str:
        """在静态图右下角叠加当前频道水印，写入新 WEBP；无水印配置则返回原路径。"""
        wm_path, wm_opts = self._resolve_watermark_config()
        if not wm_path or not os.path.isfile(webp_path):
            return webp_path
        return self.workflow.ffmpeg_processor.apply_watermark_to_flat_image(
            webp_path, wm_path, wm_opts
        )

    def add_headmark(self):
        """为当前场景或本故事全部场景的主轨 clip 左上角叠加角标 PNG（headmark 配置，默认 program/<channel_id>/headmark.png）。"""
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有当前工作流", parent=self.root)
            return
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        hm_path, hm_opts = self._resolve_headmark_config()
        if not hm_path:
            messagebox.showerror(
                "顶标",
                "未找到左上角角标图片。\n"
                "请在项目 JSON 中配置 headmark.path，或将 PNG 放在 program/<频道>/ 下（如 headmark.png）。",
                parent=self.root,
            )
            return

        scope = messagebox.askyesnocancel(
            "顶标范围",
            "请选择叠加左上角角标范围：\n\n"
            "「是」本故事全部场景\n"
            "「否」仅当前场景\n"
            "「取消」不处理",
            parent=self.root,
        )
        if scope is None:
            return

        target_scenes = self.workflow.scenes_in_story(current_scene) if scope else [current_scene]

        self._clip_overlay_ffmpeg_batch_async(
            target_scenes,
            hm_path,
            hm_opts,
            "顶标",
            "加顶标失败",
            lambda fp, sr, dt, op, ot: fp.headmark_clip_with_preprocess(sr, dt, op, ot),
        )

    def add_watermark(self):
        """为当前场景或本故事全部场景的主轨 clip 加水印（PNG 见频道 program/<channel_id>/ 或项目 watermark 配置）。"""
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有当前工作流", parent=self.root)
            return
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        wm_path, wm_opts = self._resolve_watermark_config()
        if not wm_path:
            messagebox.showerror(
                "水印",
                "未找到水印图片。\n"
                "请在项目 JSON 中配置 watermark.path，或将 PNG 放在 program/<频道>/ 下（如 watermark.png）。",
                parent=self.root,
            )
            return

        scope = messagebox.askyesnocancel(
            "水印范围",
            "请选择加水印范围：\n\n"
            "「是」本故事全部场景\n"
            "「否」仅当前场景\n"
            "「取消」不处理",
            parent=self.root,
        )
        if scope is None:
            return

        target_scenes = self.workflow.scenes_in_story(current_scene) if scope else [current_scene]

        self._clip_overlay_ffmpeg_batch_async(
            target_scenes,
            wm_path,
            wm_opts,
            "水印",
            "加水印失败",
            lambda fp, sr, dt, op, ot: fp.watermark_clip_with_preprocess(sr, dt, op, ot),
        )

    def print_title(self):
        """将 caption 烧录为视频标题字幕（字体用本集内容里的字体）。"""
        current_scene = self.update_current_scene()
        content = current_scene['caption']
        if not content or content.strip() == "":
            messagebox.showinfo("加标题", "标题为空")
            return
        clip_video = get_file_path(current_scene, "clip")
        if not clip_video:
            messagebox.showinfo("加标题", "视频为空")
            return
       
        content = config.chinese_convert(content, self.workflow.language)
        if not content.lower().startswith("fl_"):
            content = "FL_" + content  # large footer title

        title_font_key = self.scene_language.get()
        if title_font_key in config.FONT_LIST:
            font = config.FONT_LIST[title_font_key]
        else:
            font = self.workflow.font_title

        self._backup_clip_to_scene_back(current_scene)
        v = self.workflow.ffmpeg_processor.add_script_to_video(clip_video, content, font)
        refresh_scene_media(current_scene, "clip", ".mp4", v)

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

    def _load_project_look_into_controls(self):
        """字体和风格记在项目上，不跟某一场走。"""
        pc = project_manager.PROJECT_CONFIG or {}
        font_key = (pc.get("title_font") or pc.get("language") or "").strip()
        if font_key not in config.FONT_LIST:
            font_key = "zh" if "zh" in config.FONT_LIST else next(iter(config.FONT_LIST))
        self.scene_language.set(font_key)
        style = config.match_visual_style(
            (pc.get("visual_style") or project_manager.LAST_VISUAL_STYLE or "")
        )
        if not style and config.VISUAL_STYLE_OPTIONS:
            style = config.VISUAL_STYLE_OPTIONS[0]
        if style:
            self.scene_visual_style.set(style)
        talk = config.normalize_dialogue_mode(pc.get("dialogue_mode") or "")
        if talk:
            self.scene_dialogue_mode.set(talk)
        scene_style = config_prompt.normalize_scene_style(pc.get("scene_style"))
        self.scene_style.set(scene_style or config_prompt.SCENE_STYLE_LABELS[0])
        region = (pc.get("setting_region") or "").strip()
        if region not in config_prompt.SETTING_PLACES:
            region = ""
        self.setting_region.set(region)
        eras = config_prompt.setting_era_labels(region)
        self.setting_era["values"] = eras
        era = (pc.get("setting_era") or "").strip()
        if era not in eras:
            era = eras[0] if eras else ""
        self.setting_era.set(era)

    def _on_setting_region_selected(self, event=None):
        """换地域后，时代只保留这一地域里的项，并选中第一项。"""
        region = (self.setting_region.get() or "").strip()
        eras = config_prompt.setting_era_labels(region)
        self.setting_era["values"] = eras
        if self.setting_era.get() not in eras:
            self.setting_era.set(eras[0] if eras else "")
        self._save_project_look()

    def _save_project_look(self, event=None):
        """把字体、风格写回项目配置。"""
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict):
            return
        font_key = (self.scene_language.get() or "").strip()
        style = (self.scene_visual_style.get() or "").strip()
        changed = False
        if font_key in config.FONT_LIST and pc.get("title_font") != font_key:
            pc["title_font"] = font_key
            changed = True
        if style and pc.get("visual_style") != style:
            pc["visual_style"] = style
            project_manager.LAST_VISUAL_STYLE = style
            changed = True
        talk = config.normalize_dialogue_mode(self.scene_dialogue_mode.get() or "")
        if talk and pc.get("dialogue_mode") != talk:
            pc["dialogue_mode"] = talk
            changed = True
        scene_style = config_prompt.normalize_scene_style(self.scene_style.get())
        if (pc.get("scene_style") or "") != scene_style:
            pc["scene_style"] = scene_style
            changed = True
        region = (self.setting_region.get() or "").strip()
        era = (self.setting_era.get() or "").strip()
        if pc.get("setting_region") != region:
            pc["setting_region"] = region
            changed = True
        if pc.get("setting_era") != era:
            pc["setting_era"] = era
            changed = True
        lang = (self.shared_language.get() or "").strip()
        if lang and pc.get("language") != lang:
            pc["language"] = lang
            if getattr(self, "workflow", None):
                self.workflow.language = lang
            changed = True
        if changed:
            save_project_config(parent=self.root)

    def generate_video(self, scene, previous_scene, next_scene, track):
        image_path = get_file_path(scene, track+"_image")
        image_last_path = get_file_path(scene, track+"_image_last")
        next_sound_path = get_file_path(next_scene, track+"_audio")
        sound_path = get_file_path(scene, track+"_audio")
        if not sound_path:
            return

        animate_mode = scene.get(track+"_animation", "S2V")
        if animate_mode not in config_prompt.ANIMATE_SOURCE or animate_mode.strip() == "":
            return

        wan_prompt = scene.get(track+"_prompt", "")
        
        # 如果 wan_prompt 是字符串（JSON格式），尝试解析为字典
        if isinstance(wan_prompt, str) and wan_prompt.strip():
            try:
                wan_prompt = json.loads(wan_prompt)
            except:
                print("none json wan_prompt")
        
        # 检查 prompt 是否为空（支持字符串和字典两种格式）
        if not wan_prompt or (isinstance(wan_prompt, str) and wan_prompt.strip() == "") or (isinstance(wan_prompt, dict) and len(wan_prompt) == 0):
            #wan_prompt = self.workflow.build_prompt(scene, "", track, animate_mode, False)
            wan_prompt = "..."
            scene[track+"_prompt"] = wan_prompt

        action_path = get_file_path(scene, self.selected_secondary_track)

        self.workflow.rebuild_scene_video(scene, track, animate_mode, image_path, image_last_path, sound_path, next_sound_path, action_path, wan_prompt)
        self.workflow.save_scenes_to_json()

    def regenerate_video(self, track, prompt_only):
        """打开 WAN 提示词编辑对话框并生成主轨道视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        
        # 定义生成视频的回调函数
        def generate_callback(scene, wan_prompt):
            scene[track+"_prompt"] = wan_prompt
            # 使用编辑后的 prompt 生成视频
            if not prompt_only:
                if track == "clip":
                    new_scenes = self.workflow.split_smart_scene(scene)
                    if new_scenes is None:
                        return
                    if len(new_scenes) > 1:
                        for s in new_scenes:
                            generate_callback(s, wan_prompt)
                    else:
                        previous_scene = self.workflow.get_previous_scene(self.current_scene_index)
                        next_scene = self.workflow.get_next_scene(self.current_scene_index)
                        self.generate_video(scene, previous_scene, next_scene, track)
                else:
                    previous_scene = self.workflow.get_previous_scene(self.current_scene_index)
                    next_scene = self.workflow.get_next_scene(self.current_scene_index)
                    self.generate_video(scene, previous_scene, next_scene, track)

            self.workflow.save_scenes_to_json()

            self.refresh_gui_scenes()
        
        # 显示编辑对话框
        show_wan_prompt_editor(self, self.workflow, generate_callback, current_scene, track)
