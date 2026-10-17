"""ConfigMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import config_prompt
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import config
from project_manager import ProjectConfigManager, save_project_config
import project_manager
from utility.ffmpeg_processor import FfmpegProcessor


class ConfigMixin:
    def _parse_video_size_combo_label(self, lbl: str):
        s = (lbl or "").replace("×", "x").replace("X", "x").strip()
        a, b = s.lower().split("x", 1)
        return int(a.strip()), int(b.strip())

    def _set_video_size_combo_values(self, vw: int, vh: int):
        if not hasattr(self, "video_size_combo"):
            return
        label = f"{int(vw)}×{int(vh)}"
        vals = list(self._video_size_presets)
        if label not in vals:
            vals = list(vals) + [label]
        self.video_size_combo["values"] = vals
        self._programmatic_video_size = True
        self.video_size_combo.set(label)
        self._programmatic_video_size = False

    def _revert_video_size_combo(self):
        if not project_manager.PROJECT_CONFIG:
            return
        vw, vh = project_manager.video_size_pair(
            project_manager.PROJECT_CONFIG.get("video_width"),
            project_manager.PROJECT_CONFIG.get("video_height"),
        )
        self._set_video_size_combo_values(vw, vh)

    def _on_video_output_size_selected(self, event=None):
        if self._programmatic_video_size or self._loading_config or self._block_video_size_apply:
            return
        wf = getattr(self, "workflow", None)
        if wf is None:
            return
        sel = self.video_size_combo.get()
        try:
            nw, nh = self._parse_video_size_combo_label(sel)
        except (ValueError, TypeError, AttributeError):
            messagebox.showerror("尺寸", f"无法解析分辨率：{sel!r}", parent=self.root)
            self._revert_video_size_combo()
            return
        pc = project_manager.PROJECT_CONFIG
        if not pc:
            return
        cur_w, cur_h = project_manager.video_size_pair(pc.get("video_width"), pc.get("video_height"))
        if (nw, nh) == (cur_w, cur_h):
            return

        has_list_media = bool(wf.project_source_media_path() or wf._row_media_path())
        if has_list_media:
            size_note = "这条已有音频或视频，各场的 clip 和 zero 保持不动。"
        else:
            size_note = (
                "将按频道模板（config.make_backgroud_medias：169_ 横屏 / 916_ 竖屏）"
                "重写所有场景的 zero、zero_image、zero_audio、clip、clip_audio、clip_image。"
            )
        if not messagebox.askyesno(
            "更改成片尺寸",
            f"将输出尺寸由 {cur_w}×{cur_h} 改为 {nw}×{nh}。\n\n{size_note}\n\n是否继续？",
            parent=self.root,
        ):
            self._revert_video_size_combo()
            return

        old_w, old_h = cur_w, cur_h
        try:
            pc["video_width"] = nw
            pc["video_height"] = nh
            size_key = f"{nw}x{nh}"
            if size_key in ("1920x1080", "1080x1920"):
                project_manager.LAST_VIDEO_SIZE = size_key
                config.save_yt_tools_prefs({"video_size": size_key})
            wf.reapply_all_scenes_template_medias(nw, nh)
            ProjectConfigManager.set_global_config(pc)
            save_project_config(parent=self.root)
            self.refresh_gui_scenes()
            if has_list_media:
                done = f"已更新为 {nw}×{nh}。各场的 clip 和 zero 保持不动，下次新建项目也用这个尺寸。"
            else:
                done = f"已更新为 {nw}×{nh}，各场景模板底稿已刷新，项目配置已保存。"
            messagebox.showinfo("尺寸", done, parent=self.root)
        except Exception as e:
            pc["video_width"] = old_w
            pc["video_height"] = old_h
            ProjectConfigManager.set_global_config(pc)
            try:
                wf.ffmpeg_processor = FfmpegProcessor(wf.pid, wf.language, old_w, old_h)
            except Exception:
                pass
            self._revert_video_size_combo()
            try:
                wf.load_scenes()
            except Exception:
                pass
            try:
                save_project_config(parent=self.root)
            except Exception:
                pass
            self.refresh_gui_scenes()
            messagebox.showerror(
                "尺寸",
                f"更新失败，已恢复配置为 {old_w}×{old_h} 并从磁盘重载场景列表：\n{e}",
                parent=self.root,
            )

    def load_config(self):
        """加载当前项目的配置"""
        try:
            # 用户选择 YT 管理/下载时尚未创建或选择项目，PROJECT_CONFIG 为空是正常的
            if project_manager.PROJECT_CONFIG is None:
                return
            
            # 临时禁用自动保存，避免加载过程中触发保存
            self._loading_config = True
            self.apply_config_to_gui(project_manager.PROJECT_CONFIG)
            
            # 检查是否有有效PID
            saved_pid = project_manager.PROJECT_CONFIG.get('pid', '')
            if not saved_pid:
                print("⚠️ 项目配置中没有有效的PID")
                exit()

            # 同步标题到workflow
            saved_video_title = project_manager.PROJECT_CONFIG.get('video_title', '默认标题')
            if saved_video_title and saved_video_title != '默认标题':
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, saved_video_title)
                # 只在workflow已创建时设置标题
                if hasattr(self, 'workflow') and self.workflow is not None:
                    self.workflow.set_title(saved_video_title)

        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
            exit()
        finally:
            # 重新启用自动保存
            self._loading_config = False

    def apply_config_to_gui(self, config_data):
        """将配置数据应用到GUI组件"""
        try:
            # 加载PID (只读标签)
            pid = config_data.get('pid', '')
            if hasattr(self, 'shared_pid'):
                self.shared_pid.config(text=pid)
                
            # 加载语言 (只读标签)
            language = config_data.get('language', 'tw')
            if hasattr(self, 'shared_language'):
                values = list(self.shared_language.cget("values") or [])
                if language and language not in values:
                    self.shared_language["values"] = [language] + values
                self.shared_language.set(language or "tw")
                
            # 加载频道 (只读标签)
            channel = config_data.get('channel', 'strange_zh')
            if hasattr(self, 'shared_channel'):
                self.shared_channel.config(text=channel)

            vw, vh = project_manager.video_size_pair(
                config_data.get('video_width'), config_data.get('video_height')
            )
            self._set_video_size_combo_values(vw, vh)
            self._load_topic_fields(config_data)
                
            # 加载视频标题
            video_title = config_data.get('video_title', '默认标题')
            if hasattr(self, 'video_title'):
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, video_title)
                
            # 加载宣传视频滚动持续时间
            promo_scroll_duration = config_data.get('promo_scroll_duration', 7.0)
            self.promo_scroll_duration = promo_scroll_duration
            
            if hasattr(self, "scene_language"):
                self._load_project_look_into_controls()
            self._refresh_narrator_button()
            try:  # 全集生成的笔记本列表：后台刷新，失败只记一行
                from utility import notebooklm_cdp

                notebooklm_cdp.refresh_notebooks_in_background()  # 没开 9222 Chrome 会在后台自己启动
            except Exception as exc:
                print(f"NotebookLM 笔记本列表没有刷新：{exc}")
            print(f"✅ 已将配置应用到GUI: 频道={channel}, 语言={language}, PID={pid}")
            
        except Exception as e:
            print(f"❌ 应用配置到GUI时出错: {e}")

    def on_closing(self):
        """处理窗口关闭事件"""
        try:
            # 显示保存确认对话框
            if not self.show_save_confirmation_on_exit():
                return  # 用户取消了，不关闭应用
        
            print("🔄 正在关闭应用...")
            
            # 停止后台视频检查线程
            self.stop_video_check_thread()
            
            # 停止状态更新定时器
            if hasattr(self, 'status_update_timer_id') and self.status_update_timer_id is not None:
                self.root.after_cancel(self.status_update_timer_id)
                self.status_update_timer_id = None
            
            # 停止视频播放并释放资源
            if hasattr(self, 'video_cap') and self.video_cap:
                self.video_cap.release()
            if hasattr(self, 'video_after_id') and self.video_after_id:
                self.root.after_cancel(self.video_after_id)
                
            # 清理临时音频文件
            self.cleanup_temp_audio_files()
            
            print("✅ 应用已正常关闭")
            
        except Exception as e:
            print(f"❌ 关闭时出错: {e}")
        finally:
            self.root.destroy()

    def show_save_confirmation_on_exit(self):
        """退出时显示保存确认对话框"""
        try:
            pid = project_manager.PROJECT_CONFIG.get('pid', '未知PID')
            title = project_manager.PROJECT_CONFIG.get('video_title', '未知标题')
            
            # 检查是否有未保存的更改
            current_data = self.get_current_config_data()
            has_changes = current_data != project_manager.PROJECT_CONFIG
            
            if has_changes:
                result = messagebox.askyesnocancel(
                    "保存项目配置", 
                    f"是否保存当前项目的配置？\n\n项目: {pid}\n标题: {title}\n\n点击'是'保存并退出\n点击'否'不保存直接退出\n点击'取消'返回应用",
                    icon='question'
                )
                
                if result is None:  # 用户点击取消
                    return False  # 不关闭应用
                elif result:  # 用户点击是
                    self.save_config()
                    print(f"✅ 已保存项目配置: {pid} - {title}")
                else:  # 用户点击否
                    print(f"⚠️ 项目配置未保存: {pid} - {title}")
            else:
                print(f"📋 项目配置无变化，无需保存: {pid} - {title}")
                
            return True  # 继续关闭应用
            
        except Exception as e:
            print(f"❌ 保存确认对话框出错: {e}")
            return True  # 出错时继续关闭应用

    def get_current_config_data(self):
        """获取当前的配置数据（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype 等所有字段）"""
        config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
        # 仅覆盖 GUI 可编辑的字段
        config_data.update({
            'pid': self.get_pid(),
            'language': (self.shared_language.get() or "").strip(),
            'channel': self.shared_channel.cget('text'),
            'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '默认视频标题',
            'video_width': project_manager.video_size_pair(config_data.get('video_width'), config_data.get('video_height'))[0],
            'video_height': project_manager.video_size_pair(config_data.get('video_width'), config_data.get('video_height'))[1],
            'topic_category': (self.topic_category_var.get() or "").strip(),
            'topic_subtype': (self.topic_subtype_var.get() or "").strip(),
            'tags': self._topic_tags_value(),
            'visual_style': (self.scene_visual_style.get() or "").strip() or config_data.get("visual_style"),
            'dialogue_mode': config.normalize_dialogue_mode(
                (self.scene_dialogue_mode.get() or "").strip() or config_data.get("dialogue_mode")
            ),
            'scene_style': config_prompt.normalize_scene_style(self.scene_style.get()),
            'title_font': (self.scene_language.get() or "").strip() or config_data.get("title_font"),
            'setting_region': (self.setting_region.get() or "").strip(),
            'setting_era': (self.setting_era.get() or "").strip(),
        })

        # Add audio_prepares data if available
        workflow = self.workflow
        if workflow and hasattr(workflow, 'audio_prepares'):
            config_data['audio_prepares'] = workflow.video_prepares

        return config_data

    def cleanup_temp_audio_files(self):
        """清理临时音频文件"""
        try:
            import glob
            temp_files = glob.glob("temp_audio_*.wav")
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                    print(f"🗑️ 已清理临时音频文件: {temp_file}")
                except:
                    pass
        except Exception as e:
            print(f"⚠️ 清理临时文件时出错: {e}")

    def save_config(self):
        """保存当前项目配置（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype 等所有字段）"""
        try:
            workflow = self.workflow
            # 以现有配置为基底，避免丢失 topic_category/topic_subtype 等
            config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
            config_data.pop('debut_content', None)
            # 仅覆盖 GUI 可编辑的字段
            config_data.update({
                'pid': self.get_pid(),
                'language': (self.shared_language.get() or "").strip(),
                'channel': self.shared_channel.cget('text'),
                'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '视频标题',
                'video_width': project_manager.video_size_pair(config_data.get('video_width'), config_data.get('video_height'))[0],
                'video_height': project_manager.video_size_pair(config_data.get('video_width'), config_data.get('video_height'))[1],
                'topic_category': (self.topic_category_var.get() or "").strip(),
                'topic_subtype': (self.topic_subtype_var.get() or "").strip(),
                'tags': self._topic_tags_value(),
                'visual_style': (self.scene_visual_style.get() or "").strip() or config_data.get("visual_style"),
                'dialogue_mode': config.normalize_dialogue_mode(
                    (self.scene_dialogue_mode.get() or "").strip() or config_data.get("dialogue_mode")
                ),
                'scene_style': config_prompt.normalize_scene_style(self.scene_style.get()),
            'title_font': (self.scene_language.get() or "").strip() or config_data.get("title_font"),
                'setting_region': (self.setting_region.get() or "").strip(),
                'setting_era': (self.setting_era.get() or "").strip(),
            })

            # Save audio_prepares data if available
            if workflow and hasattr(workflow, 'audio_prepares'):
                config_data['audio_prepares'] = workflow.video_prepares

            # 更新当前项目配置（统一通过 set_global_config）
            ProjectConfigManager.set_global_config(config_data)
            save_project_config(parent=self.root)
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")

    def bind_scene_navigation_shortcuts(self):
        """全局：Alt+←/→ 和 Ctrl+Shift+←/→ 上一/下一场景；Ctrl+Alt+←/→ 上一/下一集；Ctrl+Shift+Alt+←/→ 首/末场景。"""
        def _has_scenes():
            return getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None)

        def _prev(event=None):
            if not _has_scenes():
                return
            self.prev_scene()
            return "break"

        def _next(event=None):
            if not _has_scenes():
                return
            self.next_scene()
            return "break"

        def _first(event=None):
            if not _has_scenes():
                return
            self.first_scene()
            return "break"

        def _last(event=None):
            if not _has_scenes():
                return
            self.last_scene()
            return "break"

        def _alt_ok(event) -> bool:
            """Alt+←/→ 翻场景：只在主窗口里生效（含讲话框，讲话框里 Ctrl+←/→ 另有用途，所以翻场景用 Alt）。"""
            widget = getattr(event, "widget", None)
            if widget is None:
                return True
            try:
                return widget.winfo_toplevel() is self.root
            except (tk.TclError, AttributeError):
                return False

        def _alt_prev(event=None):
            if event is not None and not _alt_ok(event):
                return
            return _prev(event)

        def _alt_next(event=None):
            if event is not None and not _alt_ok(event):
                return
            return _next(event)

        def _prev_episode(event=None):
            if not _has_scenes():
                return
            self.prev_episode()
            return "break"

        def _next_episode(event=None):
            if not _has_scenes():
                return
            self.next_episode()
            return "break"

        for seq in (
            "<Control-Shift-Left>",
            "<Control-Shift-KP_Left>",
        ):
            self.root.bind_all(seq, _prev)
        for seq in (
            "<Control-Shift-Right>",
            "<Control-Shift-KP_Right>",
        ):
            self.root.bind_all(seq, _next)
        # 更快的翻页：Alt+←/→ 上一/下一场景（Ctrl+←/→ 留给文本框移动光标和讲话框挪字）
        for seq in ("<Alt-Left>", "<Alt-KP_Left>", "<Alt-Key-Left>"):
            self.root.bind_all(seq, _alt_prev)
        for seq in ("<Alt-Right>", "<Alt-KP_Right>", "<Alt-Key-Right>"):
            self.root.bind_all(seq, _alt_next)
        # Ctrl+Alt+←/→：上一集 / 下一集，与「本集内容」旁边的两个按钮相同。
        for seq in ("<Control-Alt-Left>", "<Control-Alt-KP_Left>", "<Alt-Control-Left>"):
            self.root.bind_all(seq, _prev_episode)
        for seq in ("<Control-Alt-Right>", "<Control-Alt-KP_Right>", "<Alt-Control-Right>"):
            self.root.bind_all(seq, _next_episode)
        # Alt 左右键在部分 Tk 下需写成 Alt-Control-Shift（与 Control-Shift-Alt 等价）
        for seq in (
            "<Control-Shift-Alt-Left>",
            "<Control-Shift-Alt-KP_Left>",
            "<Alt-Control-Shift-Left>",
            "<Control-Alt-Shift-Left>",
        ):
            self.root.bind_all(seq, _first)
        for seq in (
            "<Control-Shift-Alt-Right>",
            "<Control-Shift-Alt-KP_Right>",
            "<Alt-Control-Shift-Right>",
            "<Control-Alt-Shift-Right>",
        ):
            self.root.bind_all(seq, _last)

    def bind_edit_events(self):
        """绑定编辑事件"""
        # 绑定场景信息编辑字段的Enter键事件，用于自动保存
        scene_text_fields = [
            self.scene_speaking,
            self.scene_visual,
            self.scene_caption,
        ]
        for field in scene_text_fields:
            # Ctrl+Enter：保存且不插入换行
            field.bind('<Control-Return>', self.on_scene_field_enter)
            field.bind('<Control-Enter>', self.on_scene_field_enter)
            # Enter：立即写回场景与 JSON，并保留默认换行
            field.bind('<Return>', self.on_scene_field_return_commit)
            field.bind('<KP_Enter>', self.on_scene_field_return_commit)
            field.bind('<FocusOut>', self.on_scene_field_focus_out)

        for field in (self.shared_language, self.scene_visual_style, self.scene_dialogue_mode, self.scene_style, self.scene_language, self.setting_era):
            field.bind("<<ComboboxSelected>>", self._save_project_look)
            field.bind("<FocusOut>", self._save_project_look)
        self.setting_region.bind("<<ComboboxSelected>>", self._on_setting_region_selected)
        self.setting_region.bind("<FocusOut>", self._save_project_look)
        
        # 讲话：仅在此框 — Ctrl+S 拆分克隆；Ctrl+←/→ 移动片段；Ctrl+M 合并下一场景讲话并删下一场景（仅讲话，不碰音视频）
        self.scene_speaking.bind("<Control-s>", self._on_speaking_ctrl_s_split_clone)
        self.scene_speaking.bind("<Control-S>", self._on_speaking_ctrl_s_split_clone)
        self.scene_speaking.bind("<Control-Right>", self._on_speaking_ctrl_right_move_tail_to_next)
        self.scene_speaking.bind("<Control-Left>", self._on_speaking_ctrl_left_move_head_to_prev)
        self.scene_speaking.bind("<Control-m>", self._on_speaking_ctrl_m_merge_next_speaking)
        self.scene_speaking.bind("<Control-M>", self._on_speaking_ctrl_m_merge_next_speaking)
        for seq in ("<Control-Shift-Left>", "<Control-Shift-KP_Left>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_shift_nav_prev)
        for seq in ("<Control-Shift-Right>", "<Control-Shift-KP_Right>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_shift_nav_next)
        for seq in ("<Control-Alt-Left>", "<Control-Alt-KP_Left>", "<Alt-Control-Left>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_alt_prev_episode)
        for seq in ("<Control-Alt-Right>", "<Control-Alt-KP_Right>", "<Alt-Control-Right>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_alt_next_episode)
        for _w in (self.scene_speaking,):
            _w.bind("<Insert>", self._on_scene_insert_silence_marker)

        print("📝 已绑定场景编辑字段：Enter 立即保存；Ctrl+Enter 保存不换行；失焦 500ms 防抖保存；讲话 Ctrl+S/←/→/M；讲话/旁白 Insert→静音菜单")

    def bind_config_change_events(self):
        """绑定配置变化事件"""
        # PID, 语言和频道现在都是只读的，不需要绑定变化事件
            
        # 绑定video_title变化事件
        if hasattr(self, 'video_title'):
            self.video_title.bind('<KeyRelease>', self.on_video_title_change)
            self.video_title.bind('<FocusOut>', self.on_video_title_change)
            self.video_title.bind('<Double-Button-1>', self.on_video_title_double_click)
        if hasattr(self, 'topic_category_combo'):
            self.topic_category_combo.bind('<<ComboboxSelected>>', self._on_topic_category_selected)
        if hasattr(self, 'topic_subtype_combo'):
            self.topic_subtype_combo.bind('<<ComboboxSelected>>', self._on_topic_fields_changed)
        if hasattr(self, 'topic_tags_entry'):
            self.topic_tags_entry.bind('<FocusOut>', self._on_topic_fields_changed)
            self.topic_tags_entry.bind('<Return>', self._on_topic_fields_changed)

    def _topic_choice_rows(self) -> list:
        channel = ""
        if project_manager.PROJECT_CONFIG:
            channel = (project_manager.PROJECT_CONFIG.get("channel") or "").strip()
        if not channel and hasattr(self, "shared_channel"):
            channel = (self.shared_channel.cget("text") or "").strip()
        try:
            choices, categories, _tags = config.load_topics(channel)
        except Exception:
            return [], []
        return list(choices or []), list(categories or [])

    def _subtypes_for_category(self, category: str, choices: list) -> list:
        subtypes = []
        for item in choices or []:
            if not isinstance(item, dict) or item.get("topic_category") != category:
                continue
            for subtype_item in item.get("topic_subtypes", []) or []:
                if not isinstance(subtype_item, dict):
                    continue
                name = (subtype_item.get("topic_subtype") or "").strip()
                if name and name not in subtypes:
                    subtypes.append(name)
        return subtypes

    def _topic_tags_value(self):
        from utility.tags_text import parse_tags_list

        text = (self.topic_tags_var.get() or "").strip() if hasattr(self, "topic_tags_var") else ""
        return parse_tags_list(text) if text else []

    def _load_topic_fields(self, config_data: dict) -> None:
        if not hasattr(self, "topic_category_combo"):
            return
        choices, categories = self._topic_choice_rows()
        self._topic_choices = choices
        category = (config_data.get("topic_category") or "").strip()
        subtype = (config_data.get("topic_subtype") or "").strip()
        tags = config_data.get("tags")
        if isinstance(tags, list):
            tags_text = " | ".join(str(t) for t in tags if str(t).strip())
        else:
            tags_text = (tags or "").strip() if isinstance(tags, str) else ""
        if category and category not in categories:
            categories = list(categories) + [category]
        self.topic_category_combo["values"] = categories
        self.topic_category_var.set(category)
        subtypes = self._subtypes_for_category(self.topic_category_var.get(), choices)
        self.topic_subtype_combo["values"] = subtypes
        self.topic_subtype_var.set(subtype if subtype in subtypes else "")
        self.topic_tags_var.set(tags_text)

    def _on_topic_category_selected(self, _event=None) -> None:
        if self._loading_config:
            return
        choices = getattr(self, "_topic_choices", None) or []
        subtypes = self._subtypes_for_category(self.topic_category_var.get(), choices)
        self.topic_subtype_combo["values"] = subtypes
        if self.topic_subtype_var.get() not in subtypes:
            self.topic_subtype_var.set("")
        self._on_topic_fields_changed()

    def _on_topic_fields_changed(self, _event=None) -> None:
        if self._loading_config or not project_manager.PROJECT_CONFIG:
            return
        project_manager.PROJECT_CONFIG["topic_category"] = (self.topic_category_var.get() or "").strip()
        project_manager.PROJECT_CONFIG["topic_subtype"] = (self.topic_subtype_var.get() or "").strip()
        project_manager.PROJECT_CONFIG["tags"] = self._topic_tags_value()
        self.save_config()
