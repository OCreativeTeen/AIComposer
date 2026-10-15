"""ChannelVideosDialogImpl: methods moved verbatim from gui/downloader.py:MediaGUIManager."""
import os
import time
import shutil
import json
import threading
import copy
import config
import config_prompt
from datetime import datetime
from utility.file_util import show_auto_close_popup
from gui.choice_dialog import askchoice
from utility.tags_text import parse_tags_list
import project_manager
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
from utility.tags_text import _plain_item_tags
from utility.time_util import _should_update_upload_date
from gui.dl.youtube_dl import _normalize_channel_videos_for_storage, _write_channel_list_json_file, _youtube_row_display_title, _youtube_row_project_title, _youtube_row_source_title
from gui.dl.list_store import _apply_project_config_to_list_row, _channel_list_row_tree_key, _copy_story_list_row, _drop_cloned_duplicates_of_row, _find_cloned_project_pids_for_source, _fresh_story_row_id, _is_viewing_topic_category_program_list, _list_row_index_for_pid, _remove_pid_from_topic_category_lists, _upsert_topic_category_program_list_row, _video_detail_project_pid, _youtube_row_list_display_title
from gui.dl.gen_video_files import _get_gen_video_clip_segments, _normalize_gen_video_clip_segment
from gui.dl.publish_schedule import _gen_video_publish_mp4_if_ready, _publish_cell_display, _resolve_review_publish_mp4_path, _scan_input_media_publish_map
from gui.dl.workflow_launch import _launch_gui_wf_from_list_json, _launch_gui_wf_open_pid
from gui.downloader import _CHANNEL_LIST_TREE_TITLE_MAX_SRC_CHARS, _apply_video_detail_titles_from_ui, _configure_channel_list_treeview, _configure_video_pick_treeview, _project_look_from_row, _refresh_summary_window_title, _treeview_item_tags_safe, _video_detail_can_create_project, accept_summary_cover_image, schedule_summary_gen_video_clip_review


class ChannelVideosDialogImpl:
    def _show_channel_videos_dialog(self, *, auto_open_summary_row_keys: list[str] | None = None):
        # 创建视频管理对话框
        dialog = tk.Toplevel(self.root)
        if self.content_mode:
            dialog.title(f"TOPIC | {self.downloader.channel_name}")
        else:
            dialog.title(f"LIST | {self.downloader.channel_name}")
        dialog.geometry("2100x1000")
        dialog.transient(self.root)
        
        # 顶部信息和控制栏
        top_frame = ttk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：信息标签和刷新按钮
        info_frame = ttk.Frame(top_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        if self.content_mode:
            info_text = f"{self.downloader.channel_name} | 共 {len(self.downloader.channel_videos)} 个视频"
        else:
            info_text = f"频道: {self.downloader.channel_name} | 共 {len(self.downloader.channel_videos)} 个视频"
        info_label = ttk.Label(info_frame, text=info_text, font=("Arial", 12, "bold"))
        info_label.pack(side=tk.LEFT)
        
        #for video in self.downloader.channel_videos:
        #    video.pop('component_tags', None)
        #       transcribed_file = video.get('transcribed_file', '')
        #    if transcribed_file:
        #        content = config.fetch_text_from_json(transcribed_file)
        #        # if content is None or empty, then remove this video from self.downloader.channel_videos
        #        if content:
        #            video['content'] = content
        #        else:
        #            self.downloader.channel_videos.remove(video)
        #
        #with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
        #    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
        
        def _reload_channel_list_from_disk() -> None:
            path = (self.downloader.channel_list_json or "").strip()
            if not path or not os.path.isfile(path):
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                return
            if not isinstance(loaded, list):
                return
            _normalize_channel_videos_for_storage(loaded, self.channel_path or "")
            self.downloader.channel_videos = loaded

        # 添加刷新按钮（从磁盘重载列表，避免与 JSON 不同步）
        ttk.Button(
            info_frame,
            text="🔄 刷新",
            command=lambda: (_reload_channel_list_from_disk(), populate_tree()),
        ).pack(side=tk.RIGHT, padx=5)
        
        # 第二行：过滤和排序控制
        control_frame = ttk.Frame(top_frame)
        control_frame.pack(fill=tk.X)
        
        # 最小观看次数过滤
        ttk.Label(control_frame, text="最小观看次数:").pack(side=tk.LEFT, padx=(0, 5))
        min_view_var = tk.StringVar(value="0")
        min_view_entry = ttk.Entry(control_frame, textvariable=min_view_var, width=15)
        min_view_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # 排序方式
        sort_mode_var = tk.StringVar(value="hot_degree")  # 默认按热度排序
        
        def toggle_sort():
            """切换排序方式"""
            current_mode = sort_mode_var.get()
            if current_mode == "hot_degree":
                sort_mode_var.set("view_count")
                sort_button.config(text="排序: 观看次数 ↓")
            elif current_mode == "view_count":
                sort_mode_var.set("upload_date")
                sort_button.config(text="排序: 上传日期 ↓")
            elif current_mode == "upload_date":
                sort_mode_var.set("duration")
                sort_button.config(text="排序: 时长 ↓")
            else:  # duration
                sort_mode_var.set("hot_degree")
                sort_button.config(text="排序: 热度 ↓")
            populate_tree()
        
        sort_button = ttk.Button(control_frame, text="排序: 热度 ↓", command=toggle_sort)
        sort_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键自动应用过滤
        min_view_entry.bind('<Return>', lambda e: populate_tree())
        
        # Smart Select 功能
        ttk.Label(control_frame, text="智能选择:").pack(side=tk.LEFT, padx=(10, 5))
        smart_select_var = tk.StringVar()
        smart_select_entry = ttk.Entry(control_frame, textvariable=smart_select_var, width=20)
        smart_select_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        topic_subtype_var = tk.StringVar(value="全部")
        if self.content_mode:
            ttk.Label(control_frame, text="子类型:").pack(side=tk.LEFT, padx=(10, 5))
            subtype_names = self._topic_subtype_filter_names()
            topic_subtype_combo = ttk.Combobox(
                control_frame,
                textvariable=topic_subtype_var,
                values=subtype_names,
                state="readonly",
                width=36,
            )
            topic_subtype_combo.pack(side=tk.LEFT, padx=(0, 5))
            topic_subtype_combo.bind("<<ComboboxSelected>>", lambda _e: _on_subtype_filter())
            ttk.Label(control_frame, text="标签:").pack(side=tk.LEFT, padx=(10, 5))
            topic_tag_var = tk.StringVar(value="全部")
            topic_tag_combo = ttk.Combobox(
                control_frame,
                textvariable=topic_tag_var,
                values=["全部"],
                state="readonly",
                width=18,
            )
            topic_tag_combo.pack(side=tk.LEFT, padx=(0, 5))
            topic_tag_combo.bind("<<ComboboxSelected>>", lambda _e: populate_tree())
        else:
            topic_category_var = tk.StringVar()
            topic_category_combo = ttk.Combobox(
                control_frame,
                textvariable=topic_category_var,
                values=self.topic_categories,
                state="readonly",
                width=20,
            )
            topic_category_combo.pack(side=tk.LEFT, padx=(0, 5))

            def on_topic_category_selected(event=None):
                selected_value = topic_category_var.get()
                if selected_value:
                    self.main_topic_category = selected_value

            topic_category_combo.bind("<<ComboboxSelected>>", on_topic_category_selected)

        def smart_select():
            """根据输入文本智能选择匹配的视频（在 title 和 content 中搜索关键字）"""
            search_text = smart_select_var.get().strip().lower()
            if not search_text:
                return
            
            tree.selection_remove(*tree.selection())
            
            # 在 title 和 content 中搜索关键字，匹配则选中
            matched_count = 0
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                url = item_tags[0]
                video_detail = self.get_video_detail(url)
                if not video_detail:
                    continue
                title = (
                    _youtube_row_source_title(video_detail)
                    + " "
                    + _youtube_row_project_title(video_detail)
                ).lower()

                transcript = config.read_transcript_text_from_video_detail(video_detail) or ""
                analyzed = video_detail.get("analyzed_content") or ""
                content = (transcript + "\n" + analyzed).strip().lower()
                if search_text in title or search_text in content:
                    tree.selection_add(item)
                    matched_count += 1
            
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
            
            if matched_count > 0:
                first_matched = None
                for item in tree.get_children():
                    if item in tree.selection():
                        first_matched = item
                        break
                if first_matched:
                    tree.see(first_matched)
                    tree.focus(first_matched)
            
        # 绑定回车键
        smart_select_entry.bind('<Return>', lambda e: smart_select())

        ttk.Label(
            dialog,
            text=(
                "「分析/场景/成片」列：✓=已摘要  ⚠=场景未齐  「片」=gen_video 下已有本条成片 "
                "（成片 ``<id>.mp4``；封面 ``<id>.webp``，``id`` 为 YouTube 视频 id 或项目 pid）；"
                "摘要窗可拖放或 Ctrl+V 粘贴 mp4 / 图片（mp4 将打开审阅窗裁剪排序后拼接加水印）；"
                "拖放 mp4 后自动刷新，也可点顶部「刷新」。"
            ),
            font=("Arial", 9),
            foreground="#333",
            wraplength=1980,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 2))
        
        # 创建Treeview显示视频列表
        columns = ("title", "views", "duration", "upload_date", "status", "analyzed", "topic_category", "topic_subtype", "tags")
        if self.content_mode:
            columns = ("title", "source_channel") + tuple(c for c in columns[1:] if c != "topic_category")
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", 
                            yscrollcommand=scrollbar.set, selectmode="extended")
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 设置列标题和宽度
        tree.heading("#0", text="序号")
        tree.heading("title", text="标题")
        if "source_channel" in columns:
            tree.heading("source_channel", text="频道")
        tree.heading("views", text="观看次数")
        tree.heading("duration", text="时长")
        tree.heading("upload_date", text="上传日期")
        tree.heading("status", text="状态")
        tree.heading(
            "analyzed",
            text="分析/场景/成片",
        )
        if "topic_category" in columns:
            tree.heading("topic_category", text="主题分类")
        tree.heading("topic_subtype", text="主题子类型")
        tree.heading("tags", text="标签")

        _configure_channel_list_treeview(tree)
        if self.content_mode:
            tree.column("source_channel", width=128, minwidth=88, stretch=False, anchor="w")
            tree.column("topic_subtype", width=260, minwidth=160, stretch=False, anchor="w")
        

        def _scene_content_nonempty(v):
            sc = v.get("scene_content")
            if not sc:
                return False
            if isinstance(sc, list):
                return bool(sc)
            if isinstance(sc, str):
                t = sc.strip()
                if not t:
                    return False
                try:
                    parsed = json.loads(t)
                    return bool(parsed) if isinstance(parsed, list) else bool(parsed)
                except json.JSONDecodeError:
                    return bool(t)
            return False

        def _refresh_tag_filter_choices():
            if not self.content_mode:
                return
            picked_sub = (topic_subtype_var.get() or "").strip()
            names = []
            for video in self.downloader.channel_videos:
                if picked_sub and picked_sub != "全部":
                    if (video.get("topic_subtype") or "").strip() != picked_sub:
                        continue
                for name in _plain_item_tags(video):
                    if name not in names:
                        names.append(name)
            values = ["全部"] + names
            topic_tag_combo["values"] = values
            if (topic_tag_var.get() or "全部") not in values:
                topic_tag_var.set("全部")

        def _on_subtype_filter(_event=None):
            if self.content_mode:
                topic_tag_var.set("全部")
            populate_tree()

        def populate_tree():
            """填充或刷新树视图"""
            _refresh_tag_filter_choices()
            # 清空现有项目
            for item in tree.get_children():
                tree.delete(item)
            
            # 获取最小观看次数
            try:
                min_view_count = int(min_view_var.get() or "0")
            except ValueError:
                min_view_count = 0
            
            # 过滤视频：只显示观看次数大于等于最小值的视频
            picked_subtype = (topic_subtype_var.get() or "").strip() if self.content_mode else ""
            picked_tag = (topic_tag_var.get() or "").strip() if self.content_mode else ""
            filtered_videos = []
            for video in self.downloader.channel_videos:
                view_count = video.get('view_count', 0)
                if view_count < min_view_count:
                    continue
                if picked_subtype and picked_subtype != "全部":
                    if (video.get("topic_subtype") or "").strip() != picked_subtype:
                        continue
                if picked_tag and picked_tag != "全部":
                    if picked_tag not in _plain_item_tags(video):
                        continue
                filtered_videos.append(video)
            
            # 排序视频
            sort_mode = sort_mode_var.get()
            if sort_mode == "hot_degree":
                # 计算每个视频的热度值（每日观看次数）
                def calculate_hot_degree(video):
                    view_count = video.get('view_count', 0)
                    upload_date = video.get('upload_date', '')
                    if upload_date and len(upload_date) == 8:
                        try:
                            # 热度 = 观看次数 / 日期范围天数
                            date_obj = datetime.strptime(upload_date, '%Y%m%d')
                            days = (self.downloader.latest_date - date_obj).days + 1
                            return view_count / (days if days > 0 else 1)
                        except:
                            pass
                    # 如果无法计算，返回0
                    return 0.0
                
                filtered_videos.sort(key=calculate_hot_degree, reverse=True)

            elif sort_mode == "upload_date":
                # 按上传日期降序排序（最新的在前）
                filtered_videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
            elif sort_mode == "view_count":
                # 按观看次数降序排序
                filtered_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            elif sort_mode == "duration":
                # 按时长降序排序（时长长的在前）
                def _duration_key(v):
                    d = v.get('duration') or 0
                    if isinstance(d, str):
                        d = float(d) if d else 0
                    return int(float(d))
                filtered_videos.sort(key=_duration_key, reverse=True)
            
            # 检查视频状态并填充数据
            downloaded_count = 0
            transcribed_count = 0
            summarized_count = 0
            hottest_degree = 0.0
            input_publish_map = _scan_input_media_publish_map()

            for idx, video in enumerate(filtered_videos, 1):
                #video.pop('text_content', None)
                # 格式化时长
                duration_sec = video.get('duration', 0)
                # 确保 duration_sec 是数字类型，并转换为整数
                if duration_sec:
                    if isinstance(duration_sec, str):
                        duration_sec = float(duration_sec)
                    duration_sec = int(float(duration_sec))  # 转换为整数
                    minutes = duration_sec // 60
                    seconds = duration_sec % 60
                    duration_str = f"{minutes}:{seconds:02d}"
                else:
                    duration_str = "N/A"
                
                # 格式化观看次数
                view_count = video.get('view_count', 0)
                view_str = f"{view_count:,}" if view_count else "N/A"
                
                # 格式化上传日期（支持 YYYYMMDD 或 YYYY-MM-DD，有日期即显示，不再依赖 latest_date）
                ud_raw = video.get('upload_date') or ''
                upload_date = str(ud_raw).strip() if ud_raw else ''
                ud_8 = (upload_date.replace('-', '')[:8] if upload_date else '')
                if ud_8 and len(ud_8) == 8:
                    upload_date_str = f"{ud_8[:4]}-{ud_8[4:6]}-{ud_8[6:]}"
                    if self.downloader.latest_date:
                        try:
                            days = (self.downloader.latest_date - datetime.strptime(ud_8, '%Y%m%d')).days + 1
                            degree = view_count / (days if days > 0 else 1)
                            if hottest_degree < degree:
                                hottest_degree = degree
                        except (ValueError, TypeError):
                            pass
                else:
                    upload_date_str = "N/A"
                
                # 检查视频状态
                status_str, video_file, audio_file = self.check_video_status(video)
                
                # 统计
                if "✅ 已下载" in status_str:
                    downloaded_count += 1
                if "✅ 已转录" in status_str:
                    transcribed_count += 1
                if "✅ 已摘要" in status_str:
                    summarized_count += 1
                
                # 获取主题相关字段
                topic_category = video.get('topic_category', '')
                topic_subtype = video.get('topic_subtype', '')
                problem_tags = video.get('tags', '')
                if isinstance(problem_tags, list):
                    problem_tags = " | ".join(str(t) for t in problem_tags if t is not None)
                elif not isinstance(problem_tags, str):
                    problem_tags = str(problem_tags) if problem_tags else ""

                tag_cell = problem_tags
                if len(tag_cell) > 120:
                    tag_cell = tag_cell[:120] + "…"

                analyzed_mark = ""
                if video.get("analyzed_content"):
                    analyzed_mark += "✓"
                if not _scene_content_nonempty(video):
                    analyzed_mark += "⚠"
                # gen_video 下任一候选 stem 的 .mp4 存在则标「片」
                if _gen_video_publish_mp4_if_ready(video):
                    analyzed_mark += "片"
                mp4_for_publish = _resolve_review_publish_mp4_path(
                    video, input_publish_map
                )
                row_title = _youtube_row_list_display_title(
                    video, max_src_chars=_CHANNEL_LIST_TREE_TITLE_MAX_SRC_CHARS
                )
                row_title_full = _youtube_row_list_display_title(video)
                source_channel = (video.get("channel") or video.get("uploader") or "").strip()
                row_values = [
                    row_title,
                    view_str,
                    duration_str,
                    upload_date_str,
                    status_str,
                    analyzed_mark,
                ]
                if self.content_mode:
                    row_values.insert(1, source_channel)
                else:
                    row_values.append(topic_category[:30] if topic_category else "")
                row_values.extend((
                    topic_subtype[:30] if topic_subtype else "",
                    tag_cell,
                ))
                tree.insert("", tk.END, text=str(idx), 
                           values=tuple(row_values),
                           tags=(   _channel_list_row_tree_key(video), 
                                    row_title_full, 
                                    video_file or '', 
                                    audio_file or '', 
                                    str(view_count), 
                                    video.get('upload_date', ''), 
                                    str(duration_sec), 
                                    self.downloader.channel_name,
                                    mp4_for_publish)
                                )
            
            _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
            _write_channel_list_json_file(
                self.downloader.channel_list_json, self.downloader.channel_videos
            )

            # 更新顶部信息标签
            counts = (
                f"共 {len(filtered_videos)}/{len(self.downloader.channel_videos)} 个视频 | "
                f"已下载: {downloaded_count} | 已转录: {transcribed_count} | "
                f"已摘要: {summarized_count} | 热度: {hottest_degree:.2f}"
            )
            if self.content_mode:
                info_text = f"{self.downloader.channel_name} | {counts}"
            else:
                info_text = f"频道: {self.downloader.channel_name} | {counts}"
            info_label.config(text=info_text)
        

        # 初始填充树视图
        populate_tree()
        
        # 选择统计标签
        stats_label = ttk.Label(dialog, text="已选择: 0 个视频", font=("Arial", 10))
        stats_label.pack(pady=5)
        
        def update_selection_count():
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
        tree.bind("<<TreeviewSelect>>", lambda e: update_selection_count())

        def _unique_video_details_from_tree_selection():
            """同一 URL 在树上可能对应多行；批量操作时按 URL 去重，每个 video_detail 只处理一次。"""
            seen_urls = set()
            details = []
            for item in tree.selection():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                url_key = (item_tags[0] or "").strip()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                vd = self.get_video_detail(url_key)
                if vd is not None:
                    details.append(vd)
            return details
        

        def delete_selected_videos():
            """删除选中的视频：从列表移除并删除相关文件"""
            if not tree.selection():
                return
            uniq_details = _unique_video_details_from_tree_selection()
            if not uniq_details:
                return
            
            # 确认删除
            if not messagebox.askyesno("确认删除", f"确定要删除 {len(uniq_details)} 个视频吗？\n\n这将从列表中移除并删除相关的文件（mp4、srt、json）。",
                                           parent=dialog):
                return
            
            deleted_count = 0
            failed_count = 0
            
            # 收集要删除的视频ID和文件
            videos_to_remove = []
            files_to_delete = []
            
            for video_detail in uniq_details:
                videos_to_remove.append(video_detail)
                filename_prefix = self.downloader.generate_video_prefix(video_detail)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if (
                            filename.endswith(".srt")
                            or filename.endswith(".json")
                            or filename.endswith(".txt")
                        ):
                            files_to_delete.append(file_path)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if filename.endswith('.mp4') or filename.endswith('.mp3') or filename.endswith('.wav'):
                            files_to_delete.append(file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"✅ 已删除文件: {os.path.basename(file_path)}")
            
            # 从videos列表中移除
            for video_detail in videos_to_remove:
                if video_detail in self.downloader.channel_videos:
                    self.downloader.channel_videos.remove(video_detail)
                    deleted_count += 1
            
            _write_channel_list_json_file(
                self.downloader.channel_list_json, self.downloader.channel_videos
            )
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
            
            # 刷新列表
            populate_tree()
            
            # 显示结果
            if failed_count > 0:
                show_auto_close_popup(
                    dialog,
                    "删除完成",
                    f"已删除 {deleted_count} 个视频\n\n{failed_count} 个文件删除失败",
                    kind="error",
                )
            else:
                show_auto_close_popup(
                    dialog,
                    "删除完成",
                    f"已成功删除 {deleted_count} 个视频及其相关文件",
                )
        
        story_clip = {"rows": []}

        def _focus_is_text_entry():
            w = dialog.focus_get()
            if w is None:
                return False
            return w.winfo_class() in ("Entry", "TEntry", "Text")

        def copy_selected_stories(_event=None):
            """Ctrl+C：记下选中的故事，供 Ctrl+V 粘成新条目。"""
            if not self.content_mode or _focus_is_text_entry():
                return
            rows = _unique_video_details_from_tree_selection()
            if not rows:
                return "break"
            story_clip["rows"] = [copy.deepcopy(r) for r in rows]
            show_auto_close_popup(
                dialog,
                "已复制",
                f"已复制 {len(rows)} 条故事。在列表里按 Ctrl+V 粘贴。",
            )
            try:
                tree.focus_set()
            except tk.TclError:
                pass
            return "break"

        def paste_copied_stories(_event=None):
            """Ctrl+V：插入副本。新 id，并清掉项目信息。"""
            if not self.content_mode or _focus_is_text_entry():
                return
            srcs = [r for r in (story_clip.get("rows") or []) if isinstance(r, dict)]
            if not srcs:
                return "break"
            videos = self.downloader.channel_videos
            existing = {
                str(v.get("id") or "").strip()
                for v in videos
                if isinstance(v, dict) and str(v.get("id") or "").strip()
            }
            copies = [
                _copy_story_list_row(src, _fresh_story_row_id(existing)) for src in srcs
            ]
            insert_at = len(videos)
            selected = _unique_video_details_from_tree_selection()
            anchor = selected[-1] if selected else None
            if anchor is not None and anchor in videos:
                insert_at = videos.index(anchor) + 1
            for offset, row in enumerate(copies):
                videos.insert(insert_at + offset, row)
            new_key = _channel_list_row_tree_key(copies[-1])
            try:
                _normalize_channel_videos_for_storage(
                    videos, self.channel_path or ""
                )
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, videos
                )
            except OSError as exc:
                for row in copies:
                    if row in videos:
                        videos.remove(row)
                show_auto_close_popup(dialog, "粘贴失败", str(exc), kind="error")
                return "break"
            populate_tree()
            if new_key:
                try:
                    for item in tree.get_children():
                        tags = _treeview_item_tags_safe(tree, item)
                        if tags and tags[0] == new_key:
                            tree.selection_set(item)
                            tree.see(item)
                            tree.focus(item)
                            break
                except tk.TclError:
                    pass
            show_auto_close_popup(
                dialog,
                "已粘贴",
                f"已加入 {len(copies)} 条。编号是新的，项目信息已清掉，只留下故事材料。",
            )
            return "break"

        # 绑定Delete键
        def on_key_press(event):
            if event.keysym == 'Delete':
                delete_selected_videos()
        tree.bind('<KeyPress>', on_key_press)
        if self.content_mode:
            for seq, handler in (
                ("<Control-c>", copy_selected_stories),
                ("<Control-C>", copy_selected_stories),
                ("<Control-v>", paste_copied_stories),
                ("<Control-V>", paste_copied_stories),
            ):
                tree.bind(seq, handler)
                dialog.bind(seq, handler)
        # 确保tree可以获得焦点以便接收键盘事件
        tree.focus_set()

        tree.bind("<Button-1>", lambda e: tree.focus_set())

        # 摘要窗口单例：切换上一条/下一条时复用同一 Toplevel，仅重建内容
        summary_window_ref = {"w": None}

        class _SummaryNavFakeEvt:
            y = None

        def _nav_summary_delta(delta):
            """Ctrl+←/→：按列表顺序切换条目并刷新摘要窗。"""
            sw = summary_window_ref.get("w")
            if not sw or not sw.winfo_exists():
                return "break"
            ctx = getattr(sw, "_summary_drop_ctx", None)
            if not isinstance(ctx, dict):
                return "break"
            items = list(tree.get_children())
            if not items:
                return "break"

            i = None
            selected = tree.selection()
            if selected and selected[0] in items:
                i = items.index(selected[0])
            else:
                vd = ctx.get("vd")
                if isinstance(vd, dict):
                    cur_key = _channel_list_row_tree_key(vd)
                    if cur_key:
                        try:
                            i = next(
                                idx
                                for idx, it in enumerate(items)
                                if (_treeview_item_tags_safe(tree, it) or [None])[0] == cur_key
                            )
                        except StopIteration:
                            pass
            if i is None:
                return "break"

            j = i + delta
            if j < 0 or j >= len(items):
                return "break"
            nxt = items[j]
            tree.selection_set(nxt)
            tree.see(nxt)
            tree.focus(nxt)
            on_focus(_SummaryNavFakeEvt(), ctx.get("nav_low_priority", False))
            return "break"

        def _bind_ctrl_arrow_nav(widget):
            for seq, delta in (
                ("<Control-Left>", -1),
                ("<Control-Right>", 1),
                ("<Control-KeyPress-Left>", -1),
                ("<Control-KeyPress-Right>", 1),
            ):
                widget.bind(
                    seq,
                    lambda e, d=delta: _nav_summary_delta(d),
                    add="+",
                )

        def _bind_summary_nav_subtree(widget):
            _bind_ctrl_arrow_nav(widget)
            for ch in widget.winfo_children():
                _bind_summary_nav_subtree(ch)

        def _resummarize_one_video_detail(vd, parent=None):
            host = parent or dialog
            if not isinstance(vd, dict):
                return
            self.update_text_content(vd)
            if not self.generate_analyzed_content_for_video(vd, force_rewrite=True):
                messagebox.showwarning(
                    "重摘",
                    "无法重新摘要：缺少足够转录原文，或生成失败。",
                    parent=host,
                )
                return
            self.prepare_category_for_content(vd, self.topic_choices)
            try:
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
            except OSError:
                pass
            populate_tree()
            show_auto_close_popup(host, "重摘", "已重新生成 analyzed content。")

        def _run_project_start_for_video_detail(
            vd,
            parent,
            *,
            forced_action=None,
            bound_pid=None,
            topic_category=None,
            topic_subtype=None,
            topic_tags=None,
            on_reopen_summary=None,
            after_persist=None,
        ):
            """启动/打开工作流项目。forced_action: None=完整流程；open=仅打开；new=仅新建。"""
            if not isinstance(vd, dict):
                return

            def _topic_category_val(cfg=None):
                return (
                    (topic_category or "").strip()
                    or ((cfg or {}).get("topic_category") or "").strip()
                    or (vd.get("topic_category") or "").strip()
                )

            def _topic_subtype_val(cfg=None):
                return (
                    (topic_subtype or "").strip()
                    or ((cfg or {}).get("topic_subtype") or "").strip()
                    or (vd.get("topic_subtype") or "").strip()
                )

            def _topic_tags_val(cfg=None):
                if topic_tags is not None and str(topic_tags).strip():
                    parsed = parse_tags_list(str(topic_tags))
                    if parsed:
                        return parsed
                if cfg and cfg.get("tags") is not None:
                    return cfg.get("tags")
                tags = vd.get("tags")
                if isinstance(tags, list):
                    return tags or None
                if isinstance(tags, str) and tags.strip():
                    return parse_tags_list(tags) or None
                return None

            channel_videos = self.downloader.channel_videos or []
            existing_pid = (bound_pid or _video_detail_project_pid(vd) or "").strip()
            if not existing_pid:
                linked = _find_cloned_project_pids_for_source(vd, channel_videos)
                if len(linked) == 1:
                    existing_pid = linked[0]
            list_path = (self.downloader.channel_list_json or "").strip()

            from project_manager import (
                create_project_with_initial_raw,
                LAST_NARRATOR,
                LAST_VISUAL_STYLE,
            )

            def _load_bound_project_cfg(for_pid: str = ""):
                wanted = (for_pid or existing_pid or "").strip()
                cfg = None
                if wanted:
                    row_ix = _list_row_index_for_pid(channel_videos, wanted)
                    if row_ix >= 0 and list_path and os.path.isfile(list_path):
                        item = channel_videos[row_ix]
                        cfg = project_manager.project_config_from_list_item(
                            item, list_path, row_ix
                        )
                if (not cfg or not cfg.get("pid")) and wanted:
                    cfg = project_manager.load_project_config_by_pid(wanted)
                return cfg

            def _persist_channel_list_and_refresh_tree(
                select_key: str = "",
                *,
                reopen_summary: bool = False,
            ) -> None:
                try:
                    _normalize_channel_videos_for_storage(
                        self.downloader.channel_videos, self.channel_path or ""
                    )
                    _write_channel_list_json_file(
                        self.downloader.channel_list_json, self.downloader.channel_videos
                    )
                except OSError:
                    pass
                try:
                    populate_tree()
                except Exception:
                    pass
                u = (select_key or "").strip()
                if u:
                    try:
                        for item in tree.get_children():
                            t = _treeview_item_tags_safe(tree, item)
                            if t and t[0] == u:
                                tree.selection_set(item)
                                tree.see(item)
                                tree.focus(item)
                                break
                    except tk.TclError:
                        pass
                if reopen_summary and u and callable(on_reopen_summary):
                    try:
                        on_reopen_summary()
                    except Exception:
                        pass
                elif callable(after_persist):
                    try:
                        after_persist()
                    except Exception:
                        pass

            def _open_bound_project(
                cfg: dict,
                cfg_pid: str,
                *,
                topic_list_path: str | None = None,
            ) -> None:
                tc = _topic_category_val(cfg)
                if not tc:
                    messagebox.showwarning(
                        "无法打开",
                        f"PID：{cfg_pid}\n\n缺少 topic_category，请先保存主题分类。",
                        parent=parent,
                    )
                    return

                launch_cfg = dict(cfg)
                launch_cfg["topic_category"] = tc
                if not (launch_cfg.get("channel") or "").strip():
                    launch_cfg["channel"] = os.path.basename(self.channel_path)

                target_path = (topic_list_path or "").strip()
                target_ix = -1
                if target_path:
                    target_ix = project_manager.find_list_row_index_by_pid(target_path, cfg_pid)
                else:
                    target_path, target_ix, _ = project_manager.find_project_topic_list_row(launch_cfg)

                if target_ix < 0 and not topic_list_path:
                    yn_fix = messagebox.askyesno(
                        "主题分表缺少该项目",
                        f"list_by_topic/{config.topic_category_list_file_basename(tc)} 中未找到 pid「{cfg_pid}」。\n\n"
                        "是否写入主题分表？",
                        parent=parent,
                    )
                    if not yn_fix:
                        return
                    try:
                        topic_row = copy.deepcopy(vd)
                        _apply_project_config_to_list_row(
                            topic_row, launch_cfg, channel_path=self.channel_path or ""
                        )
                        target_path = _upsert_topic_category_program_list_row(
                            self.channel_path, tc, topic_row
                        )
                        target_ix = project_manager.find_list_row_index_by_pid(
                            target_path, cfg_pid
                        )
                    except Exception as exc:
                        show_auto_close_popup(parent, "写入主题分表失败", str(exc), kind="error")
                        return

                if target_ix < 0:
                    show_auto_close_popup(
                        parent,
                        "无法打开",
                        f"主题分表中找不到 pid「{cfg_pid}」。",
                        kind="error",
                    )
                    return

                opened = _launch_gui_wf_from_list_json(target_path, target_ix, parent=parent)
                if not opened:
                    _launch_gui_wf_open_pid(cfg_pid, parent=parent)

            def _after_new_project_created(
                selected_config,
                *,
                superseded_pid: str = "",
            ):
                _pid = (selected_config.get("pid") or "").strip()
                if not _pid:
                    return
                ch_path = self.channel_path or ""
                list_path = (self.downloader.channel_list_json or "").strip()
                tc = (
                    (vd.get("topic_category") or selected_config.get("topic_category") or "")
                    .strip()
                )
                viewing_topic_list = self.content_mode or _is_viewing_topic_category_program_list(
                    ch_path, list_path, tc
                )
                old_pid = (superseded_pid or "").strip()

                if viewing_topic_list:
                    # 当前列表已是主题分表：项目信息写回这一条，不另建一行。
                    _apply_project_config_to_list_row(
                        vd, selected_config, channel_path=ch_path
                    )
                    select_key = _channel_list_row_tree_key(vd)
                else:
                    # 在频道热门总表中：仅更新源 YouTube 行，不向总表克隆重复行
                    _apply_project_config_to_list_row(
                        vd, selected_config, channel_path=ch_path
                    )
                    self.downloader.channel_videos = _drop_cloned_duplicates_of_row(
                        self.downloader.channel_videos, vd
                    )
                    select_key = _channel_list_row_tree_key(vd)
                    if old_pid and old_pid != _pid:
                        _remove_pid_from_topic_category_lists(ch_path, old_pid)

                _persist_channel_list_and_refresh_tree(select_key, reopen_summary=False)

                if not tc:
                    if viewing_topic_list:
                        messagebox.showwarning(
                            "项目已写入当前条目",
                            f"PID：{_pid}\n\n这条还没有 topic_category，暂时不能打开工作流。",
                            parent=parent,
                        )
                    else:
                        messagebox.showwarning(
                            "项目已创建",
                            f"PID：{_pid}\n\n缺少 topic_category，未写入 list_by_topic。\n"
                            "请先保存主题分类后再打开工作流。",
                            parent=parent,
                        )
                    return
                if viewing_topic_list:
                    topic_list_path = list_path
                else:
                    try:
                        topic_list_path = _upsert_topic_category_program_list_row(
                            ch_path, tc, copy.deepcopy(vd)
                        )
                    except Exception as exc:
                        show_auto_close_popup(
                            parent,
                            "项目已创建",
                            f"PID：{_pid}\n\n写入主题分表失败：\n{exc}",
                            kind="error",
                        )
                        return

                _open_bound_project(selected_config, _pid, topic_list_path=topic_list_path)

            def _create_new_project_from_raw(
                analyzed_content,
                scene_content,
                *,
                narrator=None,
                visual_style=None,
                language=None,
                topic_category_kw=None,
                topic_subtype_kw=None,
                topic_tags_kw=None,
                superseded_pid: str = "",
                dialogue_mode=None,
            ):
                if not _scene_content_nonempty(
                    {"scene_content": scene_content}
                ):
                    messagebox.showwarning(
                        "提示",
                        "scene_content 须为有效 JSON array，无法启动新项目。\n"
                        "可拖入/粘贴场景 JSON，或在「场景」中编辑。",
                        parent=parent,
                    )
                    return
                ac = (analyzed_content or "").strip() if analyzed_content else ""
                ch = os.path.basename(self.channel_path)
                lang = (language or getattr(self, "language", None) or "tw").strip() or "tw"
                result, selected_config = create_project_with_initial_raw(
                    parent=self.root,
                    channel=ch,
                    language=lang,
                    narrator=narrator if narrator is not None else LAST_NARRATOR,
                    visual_style=visual_style if visual_style is not None else LAST_VISUAL_STYLE,
                    analyzed_content=ac or None,
                    scene_content=scene_content,
                    topic_category=topic_category_kw if topic_category_kw is not None else _topic_category_val(),
                    topic_subtype=topic_subtype_kw if topic_subtype_kw is not None else _topic_subtype_val(),
                    topic_tags=topic_tags_kw if topic_tags_kw is not None else _topic_tags_val(),
                    dialogue_mode=dialogue_mode,
                )
                if result == "new" and selected_config:
                    _after_new_project_created(
                        selected_config,
                        superseded_pid=superseded_pid,
                    )

            if forced_action == "open":
                if not existing_pid:
                    messagebox.showwarning("无法打开", "本条尚无 project_profile / 绑定项目。", parent=parent)
                    return
                cfg = _load_bound_project_cfg(existing_pid)
                cfg_pid = (cfg.get("pid") or "").strip() if isinstance(cfg, dict) else ""
                if not cfg_pid:
                    messagebox.showwarning(
                        "无法打开已有项目",
                        f"未找到 pid「{existing_pid}」的项目配置。",
                        parent=parent,
                    )
                    return
                if cfg_pid != existing_pid:
                    messagebox.showwarning(
                        "项目配置不一致",
                        f"列表 pid 为「{existing_pid}」，配置内 pid 为「{cfg_pid}」。",
                        parent=parent,
                    )
                    return
                _open_bound_project(
                    cfg, cfg_pid, topic_list_path=list_path or None
                )
                return

            if forced_action == "new":
                _look_vs, _look_talk, _look_nar = _project_look_from_row(vd)
                _create_new_project_from_raw(
                    vd.get("analyzed_content"),
                    vd.get("scene_content"),
                    narrator=_look_nar,
                    visual_style=_look_vs,
                    language=vd.get("language"),
                    topic_category_kw=_topic_category_val(),
                    topic_subtype_kw=_topic_subtype_val(),
                    topic_tags_kw=_topic_tags_val(),
                    superseded_pid=existing_pid or "",
                    dialogue_mode=_look_talk,
                )
                return

            if existing_pid:
                cfg = _load_bound_project_cfg(existing_pid)
                if isinstance(cfg, dict) and (cfg.get("pid") or "").strip():
                    cfg_pid = (cfg.get("pid") or "").strip()
                    if cfg_pid != existing_pid:
                        messagebox.showwarning(
                            "项目配置不一致",
                            f"本条 ``project_profile.pid`` 为「{existing_pid}」，但载入的配置内 pid 为「{cfg_pid}」。\n"
                            "将按「新建项目」流程继续（需有 RAW 内容）。",
                            parent=parent,
                        )
                    else:
                        picked = askchoice(
                            "已有绑定项目",
                            [
                                ("open", f"打开已有项目（{cfg_pid}）"),
                                (
                                    "clone",
                                    "参照该项目新建（复制 RAW 等到新项目，可再改）",
                                ),
                            ],
                            parent=parent,
                        )
                        if not picked:
                            return
                        _action = picked[1]
                        if _action == "open":
                            _open_bound_project(cfg, cfg_pid)
                            return
                        if _action == "clone":
                            ac = cfg.get("analyzed_content") or vd.get("analyzed_content")
                            sc = cfg.get("scene_content") or vd.get("scene_content")
                            _look_vs, _look_talk, _look_nar = _project_look_from_row(vd, cfg)
                            _create_new_project_from_raw(
                                ac,
                                sc,
                                narrator=_look_nar,
                                visual_style=_look_vs,
                                language=cfg.get("language"),
                                topic_category_kw=_topic_category_val(cfg),
                                topic_subtype_kw=_topic_subtype_val(cfg),
                                topic_tags_kw=_topic_tags_val(cfg),
                                superseded_pid=cfg_pid,
                                dialogue_mode=_look_talk,
                            )
                            return
                else:
                    messagebox.showwarning(
                        "无法打开已有项目",
                        f"未找到 pid「{existing_pid}」的项目配置（列表中无 project_profile，且主题分表/列表中也未找到）。\n"
                        "将按「新建项目」流程继续。",
                        parent=parent,
                    )

            _look_vs, _look_talk, _look_nar = _project_look_from_row(vd)
            _create_new_project_from_raw(
                vd.get("analyzed_content"),
                vd.get("scene_content"),
                narrator=_look_nar,
                visual_style=_look_vs,
                topic_category_kw=_topic_category_val(),
                topic_subtype_kw=_topic_subtype_val(),
                topic_tags_kw=_topic_tags_val(),
                dialogue_mode=_look_talk,
            )

        def _regenerate_project_for_video_detail(vd, parent):
            """确认后删掉这条已有项目的工作流文件，再用当前内容新建一个新 pid。"""
            if not isinstance(vd, dict):
                return
            old_pid = (_video_detail_project_pid(vd) or "").strip()
            if not old_pid:
                messagebox.showwarning("重新生成项目", "这条还没有项目。", parent=parent)
                return
            if not _video_detail_can_create_project(vd):
                messagebox.showwarning(
                    "重新生成项目",
                    "scene_content 须为有效 JSON array，无法重新生成。\n"
                    "可拖入/粘贴场景 JSON，或在「场景」中编辑。",
                    parent=parent,
                )
                return
            ok = messagebox.askyesno(
                "重新生成项目",
                f"将删除项目 {old_pid} 的工作流文件（场景、媒体），\n"
                f"并另建一个新的项目号。\n\n"
                f"这条里的文案和场景内容会保留，用来填写新项目。\n\n"
                f"确定删除并重新生成吗？",
                parent=parent,
            )
            if not ok:
                return
            folder = config.resolve_project_dir(old_pid, create=False)
            if os.path.isdir(folder):
                # 尽量删。被别的进程占用删不掉的文件就留在原地，以后手工删，不阻止重新生成。
                shutil.rmtree(folder, ignore_errors=True)
            vd.pop(project_manager.PROJECT_PROFILE_KEY, None)
            vd.pop("project_id", None)
            vd.pop("project_pid", None)
            vd.pop("pid", None)
            try:
                _normalize_channel_videos_for_storage(
                    self.downloader.channel_videos, self.channel_path or ""
                )
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
                populate_tree()
            except Exception:
                pass
            _run_project_start_for_video_detail(
                vd,
                parent,
                forced_action="new",
                topic_category=(vd.get("topic_category") or "").strip() or None,
                topic_subtype=(vd.get("topic_subtype") or "").strip() or None,
                topic_tags=vd.get("tags"),
            )

        def _open_project_for_video_detail(
            vd,
            parent,
            *,
            topic_category=None,
            topic_subtype=None,
            topic_tags=None,
        ):
            """当前这条已有项目则直接打开；还没有则把新建项目的信息写回这一条。"""
            if not isinstance(vd, dict):
                return
            existing_pid = (_video_detail_project_pid(vd) or "").strip()
            if existing_pid:
                _run_project_start_for_video_detail(
                    vd,
                    parent,
                    forced_action="open",
                    bound_pid=existing_pid,
                    topic_category=topic_category,
                    topic_subtype=topic_subtype,
                    topic_tags=topic_tags,
                )
                return
            if not _video_detail_can_create_project(vd):
                messagebox.showwarning(
                    "打开项目",
                    "scene_content 须为有效 JSON array，无法启动新项目。\n"
                    "可拖入/粘贴场景 JSON，或在「场景」中编辑。",
                    parent=parent,
                )
                return
            _run_project_start_for_video_detail(
                vd,
                parent,
                forced_action="new",
                topic_category=topic_category,
                topic_subtype=topic_subtype,
                topic_tags=topic_tags,
            )

        def on_enter_key(event):
            on_focus(event, low_priority=False)

        def on_double_click(event):
            on_focus(event, low_priority=True, prefer_project=True)

        def on_focus(event, low_priority=False, prefer_project=False):
            # 处理鼠标事件和键盘事件
            if hasattr(event, 'y') and event.y:
                # 鼠标事件：通过坐标识别行
                item = tree.identify_row(event.y)
            else:
                # 键盘事件：获取当前选中的项
                selected = tree.selection()
                if not selected:
                    return
                item = selected[0]
            
            if not item:
                return

            if item not in tree.selection():
                tree.selection_set(item)
            
            item_tags = _treeview_item_tags_safe(tree, item)
            if not item_tags:
                return
            video_detail = self.get_video_detail(item_tags[0])
            if not video_detail:
                return

            if prefer_project and (_video_detail_project_pid(video_detail) or "").strip():
                _open_project_for_video_detail(
                    video_detail,
                    dialog,
                    topic_category=(video_detail.get("topic_category") or "").strip() or None,
                    topic_subtype=(video_detail.get("topic_subtype") or "").strip() or None,
                    topic_tags=video_detail.get("tags"),
                )
                return

            # get index of the selected item & save to a variable
            selected_index = tree.item(item, "text").split(".")[0]
            topic_type = video_detail.get('topic_subtype', '')
            topic_category = video_detail.get('topic_category', '')
            topic_subtype = video_detail.get('topic_subtype', '')
            topic_tags = video_detail.get('tags', '')
            if isinstance(topic_tags, list):
                topic_tags = ' | '.join(topic_tags)
            elif not isinstance(topic_tags, str):
                topic_tags = str(topic_tags) if topic_tags else ''
            if not low_priority or not topic_type or not topic_type.strip() or not topic_category or not topic_category.strip() :
                # show a messagebox to let user know the summary is generating (non-blocking)
                # self.root.after(0, lambda: messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=self.root))
                self.update_text_content(video_detail)
                topic_type = video_detail.get('topic_subtype', '')
                topic_category = video_detail.get('topic_category', '')
                topic_subtype = video_detail.get('topic_subtype', '')
                topic_tags = video_detail.get('tags', '')
                if isinstance(topic_tags, list):
                    topic_tags = ' | '.join(topic_tags)
                elif not isinstance(topic_tags, str):
                    topic_tags = str(topic_tags) if topic_tags else ''

            # 摘要窗口：首次新建，之后 Ctrl+左/右切换条目时复用同一窗口并重建内容
            if summary_window_ref.get("w") and summary_window_ref["w"].winfo_exists():
                summary_window = summary_window_ref["w"]
                try:
                    from gui.cli_bridge import set_screen_ready

                    set_screen_ready(config.SCREEN_STORY_ROOT, False)
                except Exception:
                    pass
                for child in summary_window.winfo_children():
                    child.destroy()
            else:
                summary_window = tk.Toplevel(dialog)
                summary_window_ref["w"] = summary_window
                summary_window.resizable(True, True)
                summary_window.transient(dialog)
            if not getattr(summary_window, "_summary_drop_ctx", None):
                summary_window._summary_drop_ctx = {"mgr": None, "vd": None}
            summary_window._summary_drop_ctx["mgr"] = self
            summary_window._summary_drop_ctx["vd"] = video_detail
            summary_window._summary_drop_ctx["refresh_channel_tree"] = populate_tree
            summary_window._summary_drop_ctx["summary_title_index"] = selected_index
            summary_window._summary_drop_ctx["summary_dnd_title_suffix"] = ""
            _refresh_summary_window_title(summary_window, video_detail)
            main_frame = ttk.Frame(summary_window, padding=6)
            main_frame.pack(fill=tk.BOTH, expand=True)

            _look_nar = _project_look_from_row(video_detail)[2]
            source_title_var = tk.StringVar(
                value=_youtube_row_source_title(video_detail)
            )
            story_narrator_var = tk.StringVar(value=_look_nar)
            has_project_profile = project_manager.list_json_row_has_project_profile(
                video_detail
            )
            category_var = tk.StringVar(value=topic_category)
            subtype_var = tk.StringVar(value=topic_subtype)
            tags_var = tk.StringVar(value=topic_tags)
            feature_media_var = tk.StringVar(value="")

            def refresh_feature_media_row():
                if not summary_window.winfo_exists():
                    return
                sc_n = 0
                sc = video_detail.get("scene_content")
                if isinstance(sc, list):
                    sc_n = len(sc)
                feature_media_var.set(f"场景 {sc_n} 条" if sc_n else "")

            refresh_feature_media_row()
            if isinstance(summary_window._summary_drop_ctx, dict):
                summary_window._summary_drop_ctx[
                    "refresh_feature_media_row"
                ] = refresh_feature_media_row
                summary_window._summary_drop_ctx["feature_media_var"] = feature_media_var

                def refresh_title_fields():
                    try:
                        source_title_var.set(_youtube_row_source_title(video_detail))
                    except (NameError, tk.TclError):
                        pass
                    _refresh_summary_window_title(summary_window, video_detail)

                summary_window._summary_drop_ctx[
                    "refresh_title_fields"
                ] = refresh_title_fields

            # 保存按钮
            def save_story_info():
                """保存主题信息"""
                drop_ctx = getattr(summary_window, "_summary_drop_ctx", None)
                if isinstance(drop_ctx, dict):
                    read_analyzed = drop_ctx.get("read_analyzed_draft")
                    if callable(read_analyzed):
                        drafted = read_analyzed()
                        if drafted is not None:
                            text = drafted.strip() if isinstance(drafted, str) else str(drafted).strip()
                            if text:
                                video_detail["analyzed_content"] = text
                            else:
                                video_detail.pop("analyzed_content", None)
                _apply_video_detail_titles_from_ui(
                    video_detail,
                    source_title=source_title_var.get(),
                    project_title=_youtube_row_project_title(video_detail)
                    if has_project_profile
                    else "",
                    channel_path=self.channel_path or "",
                )
                category = category_var.get().strip()
                subtype = subtype_var.get().strip()
                tags_text = tags_var.get().strip()
                
                # 解析标签：KEY=value 与旧版纯文本；| 或「逗号+下一段 KEY=」分隔
                tags_list = parse_tags_list(tags_text) if tags_text else []
                
                # 更新视频详情
                if category:
                    video_detail['topic_category'] = category
                else:
                    video_detail.pop('topic_category', None)
                if subtype:
                    video_detail['topic_subtype'] = subtype
                else:
                    video_detail.pop('topic_subtype', None)
                if tags_list:
                    video_detail['tags'] = tags_list
                else:
                    video_detail.pop('tags', None)
                # 保存到文件
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
                
                # 刷新树视图（如果对话框还存在）
                try:
                    populate_tree()
                except:
                    pass
                try:
                    refresh_publish_row()
                except Exception:
                    pass
                try:
                    _refresh_summary_window_title(summary_window, video_detail)
                except Exception:
                    pass

                save_scene = None
                drop_ctx = getattr(summary_window, "_summary_drop_ctx", None)
                if isinstance(drop_ctx, dict):
                    save_scene = drop_ctx.get("save_scene_content")
                if callable(save_scene):
                    ok, msg = save_scene()
                    if not ok:
                        show_auto_close_popup(summary_window, "场景内容", msg or "没有写回场景内容。", kind="error")
                        return

                show_auto_close_popup(summary_window, "成功", "名称、分析报告和场景内容已保存")


            publish_info_var = tk.StringVar(value="发布: …")

            def refresh_publish_row():
                if not summary_window.winfo_exists():
                    return
                imap = _scan_input_media_publish_map()
                txt, st, _ = _publish_cell_display(video_detail, imap)
                urow = (video_detail.get("url") or "").strip()
                pub_hist = (video_detail.get("publish") or "").strip()
                ud = (video_detail.get("upload_date") or "").strip()
                if st == "published" or pub_hist or urow or ud:
                    parts = []
                    if urow:
                        parts.append(
                            f"url:{urow[:64]}{'…' if len(urow) > 64 else ''}"
                        )
                    if pub_hist:
                        parts.append(f"记录:{pub_hist}")
                    if ud:
                        parts.append(f"upload_date:{ud}")
                    extra = ("  |  " + "  |  ".join(parts)) if parts else ""
                    publish_info_var.set(f"发布: {txt}{extra}")
                else:
                    publish_info_var.set(f"发布: {txt}")

                try:
                    refresh_feature_media_row()
                except Exception:
                    pass

            refresh_publish_row()
            if isinstance(summary_window._summary_drop_ctx, dict):
                summary_window._summary_drop_ctx["refresh_publish_row"] = refresh_publish_row

            def _after_content_field_saved():
                try:
                    populate_tree()
                except Exception:
                    pass

            from gui.cli_bridge import bind_screen, unbind_screen

            def _cli_set_story_cover(image_path: str):
                drop_ctx = getattr(summary_window, "_summary_drop_ctx", None)
                if not isinstance(drop_ctx, dict):
                    return False, "STORY context missing"
                path = (image_path or "").strip()
                return accept_summary_cover_image(
                    path,
                    summary_window,
                    drop_ctx,
                    interactive=False,
                    async_ui=False,
                    refresh_ui=True,
                )

            def _cli_open_clip_review(value: str):
                drop_ctx = getattr(summary_window, "_summary_drop_ctx", None)
                if not isinstance(drop_ctx, dict):
                    return False, "STORY context missing"
                mgr_local = drop_ctx.get("mgr")
                vd_local = drop_ctx.get("vd")
                if mgr_local is None or not isinstance(vd_local, dict):
                    return False, "STORY video_detail missing"
                from cli.video_choice_queue import align_clip_paths_to_scene_content
                from utility.grok_video_results import grok_clip_segments_from_video_detail

                segments = _get_gen_video_clip_segments(vd_local)
                paths: list[str] = []
                raw = (value or "").strip()
                if raw:
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list) and parsed:
                            if isinstance(parsed[0], dict):
                                for seg in parsed:
                                    if not isinstance(seg, dict):
                                        continue
                                    n = _normalize_gen_video_clip_segment(seg)
                                    if n:
                                        paths.append(n["path"])
                            else:
                                for p in parsed:
                                    if not isinstance(p, str) or not p.strip():
                                        continue
                                    np = os.path.normpath(os.path.abspath(p.strip()))
                                    if os.path.isfile(np) and np.lower().endswith(".mp4"):
                                        paths.append(np)
                    except (json.JSONDecodeError, TypeError):
                        np = os.path.normpath(os.path.abspath(raw))
                        if os.path.isfile(np) and np.lower().endswith(".mp4"):
                            paths = [np]
                if not segments:
                    if not paths:
                        segments = grok_clip_segments_from_video_detail(vd_local)
                    elif paths:
                        paths = align_clip_paths_to_scene_content(vd_local, paths)
                if not segments and not paths:
                    return False, (
                        "没有可审阅的场景 clip。"
                        "先 grv 下载各场景 video（会写入 workflow.grok_video_results）。"
                    )
                if segments:
                    schedule_summary_gen_video_clip_review(
                        summary_window,
                        mgr=mgr_local,
                        vd=vd_local,
                        ctx=drop_ctx,
                        initial_segments=segments,
                    )
                    preview = "\n".join(
                        f"  场景 {i}. {os.path.basename(seg['path'])}"
                        for i, seg in enumerate(segments, 1)
                    )
                    n = len(segments)
                else:
                    schedule_summary_gen_video_clip_review(
                        summary_window,
                        mgr=mgr_local,
                        vd=vd_local,
                        ctx=drop_ctx,
                        mp4_paths=paths,
                    )
                    preview = "\n".join(
                        f"  场景 {i}. {os.path.basename(p)}"
                        for i, p in enumerate(paths, 1)
                    )
                    n = len(paths)
                return (
                    True,
                    f"已打开审阅窗（{n} 段，按 scene_content 场景 1→{n} 顺序）。"
                    f"请在窗口内调整并确认生成成片。\n{preview}",
                )

            def _unbind_story_root(event=None):
                if event is not None and getattr(event, "widget", None) is not summary_window:
                    return
                unbind_screen(config.SCREEN_STORY_ROOT)

            def _scene_is_in_this_window():
                return None

            bind_screen(
                config.SCREEN_STORY_ROOT,
                summary_window,
                {
                    "scene": {"click": _scene_is_in_this_window},
                    "save": {"click": save_story_info},
                    "cover_image": {"set": _cli_set_story_cover},
                    "clip_review": {"set": _cli_open_clip_review},
                },
                ready=False,
            )
            summary_window.bind("<Destroy>", _unbind_story_root)

            scene_host = ttk.Frame(main_frame)
            # The SCENE editor (and its materials panel) takes all extra height.
            scene_host.pack(fill=tk.BOTH, expand=True)

            summary_window._summary_drop_ctx["nav_low_priority"] = low_priority
            if not getattr(summary_window, "_summary_nav_root_bound", False):
                _bind_ctrl_arrow_nav(summary_window)
                summary_window._summary_nav_root_bound = True
            _bind_summary_nav_subtree(main_frame)

            def _after_scene_title():
                try:
                    refresh_title_fields()
                except (NameError, tk.TclError):
                    pass

            def _open_project_from_summary():
                _open_project_for_video_detail(
                    video_detail,
                    summary_window,
                    topic_category=(category_var.get() or "").strip() or None,
                    topic_subtype=(subtype_var.get() or "").strip() or None,
                    topic_tags=tags_var.get(),
                )

            def _regen_project_from_summary():
                _regenerate_project_for_video_detail(video_detail, summary_window)

            def _resummarize_from_summary():
                _resummarize_one_video_detail(video_detail, summary_window)

            if isinstance(summary_window._summary_drop_ctx, dict):
                summary_window._summary_drop_ctx["story_title_var"] = source_title_var

            self.open_content_field_editor(
                summary_window,
                video_detail,
                "scene_content",
                on_saved=_after_content_field_saved,
                on_story_title_updated=_after_scene_title,
                main_character=(story_narrator_var.get() or "").strip(),
                channel_path=self.channel_path or "",
                embed_in=scene_host,
                on_open_project=_open_project_from_summary,
                on_regen_project=_regen_project_from_summary,
                on_save_story=save_story_info,
                on_resummarize=_resummarize_from_summary,
            )

            summary_window.focus_set()

            def _mark_story_bridge_ready():
                try:
                    from gui.cli_bridge import set_screen_ready

                    set_screen_ready(config.SCREEN_STORY_ROOT, True)
                except Exception:
                    pass

            summary_window.after_idle(_mark_story_bridge_ready)

        # 绑定双击事件
        tree.bind("<Double-1>", on_double_click)
        # 绑定 Enter 键（键盘）
        tree.bind("<Return>", on_enter_key)
        if not getattr(dialog, "_summary_nav_tree_bound", False):
            _bind_ctrl_arrow_nav(tree)
            _bind_ctrl_arrow_nav(dialog)
            dialog._summary_nav_tree_bound = True

        def _open_summary_for_row_keys(row_keys: list[str] | set[str]) -> bool:
            keys = {str(k).strip() for k in (row_keys or []) if str(k).strip()}
            if not keys:
                return False
            for item in tree.get_children():
                t = _treeview_item_tags_safe(tree, item)
                if not t:
                    continue
                tag0 = (t[0] or "").strip()
                if tag0 in keys:
                    tree.selection_set(item)
                    tree.see(item)
                    tree.focus(item)
                    on_focus(_SummaryNavFakeEvt(), low_priority=True)
                    return True
            for item in tree.get_children():
                t = _treeview_item_tags_safe(tree, item)
                if not t:
                    continue
                vd = self.get_video_detail((t[0] or "").strip())
                if not isinstance(vd, dict):
                    continue
                candidates = {
                    _channel_list_row_tree_key(vd),
                    (vd.get("url") or "").strip(),
                    project_manager.list_json_row_id(vd),
                    project_manager.list_json_row_workflow_pid(vd),
                }
                if keys & {c for c in candidates if c}:
                    tree.selection_set(item)
                    tree.see(item)
                    tree.focus(item)
                    on_focus(_SummaryNavFakeEvt(), low_priority=True)
                    return True
            return False

        def _auto_open_summary_for_row_keys():
            _open_summary_for_row_keys(auto_open_summary_row_keys or [])

        from gui.cli_bridge import bind_screen, unbind_screen

        def _cli_open_row(value: str):
            raw = (value or "").strip()
            if not raw:
                return False, "open_row: empty value"
            keys: list[str]
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    keys = [str(k).strip() for k in parsed if str(k).strip()]
                else:
                    keys = [str(parsed).strip()]
            except json.JSONDecodeError:
                keys = [k.strip() for k in raw.split(",") if k.strip()]
            if not keys:
                return False, "open_row: no keys"

            def _do_open():
                if not _open_summary_for_row_keys(keys):
                    pass

            dialog.after(0, _do_open)
            return True, f"open_row scheduled — {keys[0][:60]}"

        def _unbind_video_list(event=None):
            if event is not None and getattr(event, "widget", None) is not dialog:
                return
            unbind_screen(config.SCREEN_VIDEO_LIST)

        bind_screen(
            config.SCREEN_VIDEO_LIST,
            dialog,
            {
                "open_row": {"set": _cli_open_row},
            },
        )
        dialog.bind("<Destroy>", _unbind_video_list)
        try:
            config.set_gui_window_path([config.GUI_WINDOW_LEVEL_LIST])
        except Exception:
            pass

        if auto_open_summary_row_keys:
            dialog.after(250, _auto_open_summary_for_row_keys)
        
        # 底部按钮框架（先创建框架，按钮在后面定义函数后添加）
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)


        def update_video_list():
            """重新抓取当前频道视频列表，与现有列表比较，将新视频弹窗展示供用户勾选添加"""
            if not self.downloader.channel_list_json or not self.downloader.channel_videos:
                messagebox.showwarning("提示", "当前没有加载视频列表", parent=dialog)
                return
            channel_id = None
            for v in self.downloader.channel_videos:
                cid = (v.get('channel_id') or '').strip()
                if cid and len(cid) >= 10:
                    channel_id = cid
                    break
            if not channel_id:
                # 从任意视频重新拉取基本信息（含 channel_id）
                for v in self.downloader.channel_videos:
                    video_url = v.get('url', '').strip()
                    if video_url and ('youtube.com/watch' in video_url or 'youtu.be/' in video_url):
                        try:
                            video_data = self.downloader.get_video_detail(video_url, '')
                            if video_data:
                                cid = (video_data.get('channel_id') or '').strip()
                                if cid and len(cid) >= 10:
                                    channel_id = cid
                                    v['channel_id'] = cid
                                    for fld in ('channel', 'uploader'):
                                        if fld in video_data and video_data[fld]:
                                            v[fld] = video_data[fld]
                                    _write_channel_list_json_file(
                                        self.downloader.channel_list_json, self.downloader.channel_videos
                                    )
                                    break
                        except Exception:
                            continue
            if not channel_id:
                show_auto_close_popup(dialog, "错误", "无法获取频道ID，请使用「获取热门视频列表」重新导入频道", kind="error")
                return
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

            def fetch_task():
                result = self.downloader.fetch_channel_new_videos(channel_url, max_videos=5000)
                dialog.after(0, lambda: _show_new_videos_popup(result))

            def _show_new_videos_popup(result):
                if result is None:
                    show_auto_close_popup(dialog, "错误", "抓取视频列表失败", kind="error")
                    return
                new_videos, all_fetched = result
                updated_count = 0
                # 用最新抓取数据更新已有视频（观看次数、上传日期等），不浪费本次调用
                if all_fetched:
                    for v in self.downloader.channel_videos:
                        vid = v.get('id') or ''
                        if not vid:
                            t = _youtube_row_display_title(v).lower()
                            for fid, fdata in all_fetched.items():
                                if _youtube_row_display_title(fdata).lower() == t:
                                    vid = fid
                                    break
                        if vid and vid in all_fetched:
                            fetched = all_fetched[vid]
                            for fld in getattr(
                                self.downloader,
                                "YOUTUBE_META_FIELDS",
                                (
                                    "title",
                                    "url",
                                    "duration",
                                    "view_count",
                                    "uploader",
                                    "channel",
                                    "channel_id",
                                    "upload_date",
                                    "thumbnail",
                                    "description",
                                ),
                            ):
                                if fld == "upload_date" and not _should_update_upload_date(v):
                                    continue
                                if fld in fetched:
                                    v[fld] = fetched[fld]
                            v.pop("video_title", None)
                            updated_count += 1
                    if updated_count:
                        _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
                        _write_channel_list_json_file(
                            self.downloader.channel_list_json, self.downloader.channel_videos
                        )
                        if self.downloader.channel_videos and any(v.get('upload_date') for v in self.downloader.channel_videos):
                            self.downloader.latest_date = max(
                                (datetime.strptime(v["upload_date"], "%Y%m%d") for v in self.downloader.channel_videos if v.get("upload_date")),
                                default=self.downloader.latest_date
                            )
                        populate_tree()
                if not new_videos:
                    msg = "没有发现新视频"
                    if updated_count:
                        msg += f"，已更新 {updated_count} 个现有视频的观看次数等信息"
                    show_auto_close_popup(dialog, "提示", msg + "。")
                    return

                popup = tk.Toplevel(dialog)
                popup.title("新视频 - 选择要添加的视频")
                popup.geometry("900x500")
                popup.transient(dialog)

                cols = ("title", "views", "duration", "upload_date")
                tree_frame = ttk.Frame(popup)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                scrollbar = ttk.Scrollbar(tree_frame)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                new_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                        yscrollcommand=scrollbar.set, selectmode="extended")
                new_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.config(command=new_tree.yview)

                new_tree.heading("title", text="标题")
                new_tree.heading("views", text="观看次数")
                new_tree.heading("duration", text="时长")
                new_tree.heading("upload_date", text="上传日期")
                _configure_video_pick_treeview(new_tree)

                def fmt_duration(sec):
                    if not sec:
                        return "-"
                    m, s = divmod(int(sec), 60)
                    h, m = divmod(m, 60)
                    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

                def fmt_upload_date(ud):
                    if not ud:
                        return "-"
                    ud = str(ud).replace("-", "")[:8]
                    if len(ud) == 8:
                        return f"{ud[:4]}-{ud[4:6]}-{ud[6:]}"
                    return ud or "-"

                video_to_iid = {}
                for i, v in enumerate(new_videos):
                    view_count = v.get('view_count', 0)
                    views_str = f"{view_count:,}" if isinstance(view_count, (int, float)) else str(view_count)
                    duration_str = fmt_duration(v.get('duration', 0))
                    upload_date = fmt_upload_date(v.get('upload_date', ''))
                    title = _youtube_row_display_title(v)[:120]
                    iid = new_tree.insert("", tk.END, values=(title, views_str, duration_str, upload_date))
                    video_to_iid[iid] = v

                def add_selected():
                    selected = new_tree.selection()
                    to_add = [video_to_iid[iid] for iid in selected if iid in video_to_iid]
                    if not to_add:
                        messagebox.showinfo("提示", "请至少选择一个视频", parent=popup)
                        return
                    for v in to_add:
                        self.downloader.channel_videos.append(v)
                    self.downloader.channel_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
                    _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
                    _write_channel_list_json_file(
                        self.downloader.channel_list_json, self.downloader.channel_videos
                    )
                    popup.destroy()
                    populate_tree()
                    show_auto_close_popup(dialog, "成功", f"已添加 {len(to_add)} 个视频到列表")

                btn_frame = ttk.Frame(popup)
                btn_frame.pack(fill=tk.X, padx=10, pady=5)
                ttk.Button(btn_frame, text="全选", command=lambda: [new_tree.selection_add(item) for item in new_tree.get_children()]).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="取消全选", command=lambda: new_tree.selection_remove(*new_tree.get_children())).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="添加选中", command=add_selected).pack(side=tk.RIGHT, padx=5)
                ttk.Button(btn_frame, text="关闭", command=popup.destroy).pack(side=tk.RIGHT, padx=5)

            show_auto_close_popup(dialog, "提示", "正在抓取频道视频列表，请稍候...")
            thread = threading.Thread(target=fetch_task)
            thread.daemon = True
            thread.start()


        def fetch_info_selected():
            """对选中的、无 upload_date 的视频重新拉取元信息，更新后保存列表"""
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            videos = []
            for video_detail in _unique_video_details_from_tree_selection():
                if video_detail and not (video_detail.get('upload_date') or '').strip():
                    videos.append(video_detail)
            if not videos:
                show_auto_close_popup(dialog, "提示", "所选视频均已包含 upload_date，无需更新")
                return
            if not messagebox.askyesno("确认", f"将为 {len(videos)} 个视频重新拉取 upload_date 等信息，是否继续？", parent=dialog):
                return
            self.downloader._check_and_update_cookies(wait_forever=False)
            total = len(videos)
            success_count = [0]
            failed_count = [0]

            def fetch_task():
                for idx, video_detail in enumerate(videos, 1):
                    try:
                        url = video_detail.get('url', '')
                        if not url:
                            failed_count[0] += 1
                            continue
                        _ln = _youtube_row_display_title(video_detail)
                        print(f"[{idx}/{total}] 拉取信息: {_ln[:50]}")
                        fresh = self.downloader.get_video_detail(url, self.downloader.channel_name or 'Unknown')
                        if fresh and fresh.get('upload_date'):
                            ud = str(fresh['upload_date'] or '').strip()
                            if ud:
                                if len(ud) == 10:
                                    ud = ud.replace('-', '')
                                video_detail['upload_date'] = ud[:8]
                                print(f"  ✅ 已更新 upload_date: {ud[:8]}")
                            for k in ('title', 'duration', 'view_count', 'uploader', 'channel', 'channel_id', 'thumbnail', 'description'):
                                if k in fresh and fresh[k] is not None:
                                    video_detail[k] = fresh[k]
                            video_detail.pop('video_title', None)
                            success_count[0] += 1
                        else:
                            failed_count[0] += 1
                        try:
                            _write_channel_list_json_file(
                                self.downloader.channel_list_json, self.downloader.channel_videos
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"  ❌ 失败: {e}")
                        failed_count[0] += 1
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
                dialog.after(
                    0,
                    lambda: [
                        populate_tree(),
                        show_auto_close_popup(
                            dialog,
                            "完成",
                            f"成功: {success_count[0]} 个，失败: {failed_count[0]} 个",
                        ),
                    ],
                )

            threading.Thread(target=fetch_task, daemon=True).start()

        def download_selected():
            if not tree.selection():
                return
            # 获取选中视频的信息（按 URL 去重）
            selected_videos = _unique_video_details_from_tree_selection()
            # filter out the videos that are already downloaded
            def needs_download(video):
                audio_path = video.get('audio_path') or ''
                return not audio_path or not os.path.exists(audio_path)
            
            selected_videos = [video for video in selected_videos if needs_download(video)]
            if not selected_videos:
                return
            
            # 确认下载
            if not messagebox.askyesno("确认下载", f"确定要下载 {len(selected_videos)} 个视频吗？", parent=dialog):
                return
                    
            self.downloader._check_and_update_cookies()

            total = len(selected_videos)
            completed = [0]
            failed = [0]

            def download_task():
                for idx, video_detail in enumerate(selected_videos, 1):
                    try:
                        dn = _youtube_row_display_title(video_detail)
                        # 已存在 mp3 则跳过
                        prefix = self.downloader.generate_video_prefix(video_detail)
                        mp3_path = f"{self.youtube_dir}/media/{prefix}.mp3"
                        if os.path.exists(mp3_path):
                            video_detail['audio_path'] = mp3_path
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            print(f"[{idx}/{total}] 跳过（已存在）: {dn}")
                            try:
                                _write_channel_list_json_file(
                                    self.downloader.channel_list_json, self.downloader.channel_videos
                                )
                            except Exception:
                                pass
                            continue
                        print(f"[{idx}/{total}] 下载: {dn}")
                        file_path = self.downloader.download_audio_only(video_detail)
                        if file_path and os.path.exists(file_path):
                            file_fix = self.youtube_dir + "/media/" + self.downloader.generate_video_prefix(video_detail)+".mp3"
                            os.rename(file_path, file_fix)
                            video_detail['audio_path'] = file_fix
                            file_path = file_fix
                        #if file_path and os.path.exists(file_path):
                        #    video_detail['video_path'] = file_path
                        #    video_detail['audio_path'] = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(file_path, "mp3")
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                            print(f"✅ 完成: {os.path.basename(file_path)} ({file_size:.1f} MB)")
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            try:
                                _write_channel_list_json_file(
                                    self.downloader.channel_list_json, self.downloader.channel_videos
                                )
                            except Exception:
                                pass
                        else:
                            print(f"❌ 失败: {dn}")
                            video_detail["audio_download_status"] = "failed"
                            failed[0] += 1
                        
                    except Exception as e:
                        print(f"❌ 错误: {_youtube_row_display_title(video_detail)} - {str(e)}")
                        video_detail["audio_download_status"] = "failed"
                        failed[0] += 1
                
                # 下载完成
                print(f"\n{'='*50}")
                print(f"批量下载完成！")
                print(f"成功: {completed[0]} 个")
                print(f"失败: {failed[0]} 个")
                
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
                print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
                # 在主线程中刷新列表
                dialog.after(0, populate_tree)
            
            # 在后台线程中下载
            thread = threading.Thread(target=download_task)
            thread.daemon = True
            thread.start()


        _TRANSCRIPT_FILE_SUFFIXES = [
            ".srt",
            ".zh.srt",
            ".en.srt",
            ".json",
            ".zh.json",
            ".en.json",
            ".txt",
        ]

        def _video_already_has_transcript(video_detail):
            if (video_detail.get("transcribed_file") or "").strip():
                self.update_text_content(video_detail)
                return True
            if self.match_media_file(
                video_detail, "transcribed_file", _TRANSCRIPT_FILE_SUFFIXES
            ):
                self.update_text_content(video_detail)
                return True
            return False

        def _save_channel_list_json():
            try:
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
            except Exception:
                pass

        def _sync_transcribe_upload_date(video_detail):
            if (
                video_detail.get("upload_date")
                and _should_update_upload_date(video_detail)
            ):
                for v in self.downloader.channel_videos:
                    if v.get("url") == video_detail.get("url"):
                        v["upload_date"] = video_detail["upload_date"]
                        break

        def _apply_transcribe_success(video_detail, transcribed_file):
            self.update_text_content(video_detail, transcribed_file)
            _sync_transcribe_upload_date(video_detail)
            _save_channel_list_json()

        def _collect_videos_needing_transcript(*, require_audio=False):
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return None
            videos = []
            for video_detail in _unique_video_details_from_tree_selection():
                if _video_already_has_transcript(video_detail):
                    continue
                if require_audio and not self.downloader._ensure_audio_path(video_detail):
                    continue
                videos.append(video_detail)
            return videos

        def _run_transcribe_batch(
            videos_to_transcribe,
            *,
            task_name,
            confirm_title,
            confirm_verb,
            empty_warning,
            transcribe_fn,
            fail_message,
            pre_task=None,
        ):
            if videos_to_transcribe is None:
                return
            if not videos_to_transcribe:
                messagebox.showwarning("提示", empty_warning, parent=dialog)
                return
            message = f"将{confirm_verb} {len(videos_to_transcribe)} 个视频\n\n是否继续？"
            if not messagebox.askyesno(confirm_title, message, parent=dialog):
                return
            if pre_task:
                pre_task()

            def task():
                success_count = 0
                failed_count = 0
                try:
                    for video_detail in videos_to_transcribe:
                        time.sleep(0.05)
                        try:
                            transcribed_file = transcribe_fn(video_detail)
                            if transcribed_file:
                                print(f"  ✅ {task_name}成功")
                                _apply_transcribe_success(video_detail, transcribed_file)
                                success_count += 1
                            else:
                                print(f"  ❌ {fail_message}")
                                failed_count += 1
                        except Exception as e:
                            print(f"  ❌ {task_name}失败: {str(e)}")
                            failed_count += 1
                    _save_channel_list_json()
                    print(f"\n{'='*50}")
                    print(f"{task_name}完成！成功: {success_count} 个，失败: {failed_count} 个")
                finally:
                    def _refresh():
                        populate_tree()
                        try:
                            show_auto_close_popup(
                                dialog,
                                f"{task_name}完成",
                                f"成功: {success_count} 个，失败: {failed_count} 个",
                            )
                        except Exception:
                            pass

                    dialog.after(0, _refresh)

            threading.Thread(target=task, daemon=True).start()

        def audio_transcribe_selected():
            _run_transcribe_batch(
                _collect_videos_needing_transcript(require_audio=True),
                task_name="音频转录",
                confirm_title="确认音频转录",
                confirm_verb="用本地音频转录",
                empty_warning="没有可音频转录的视频（需已下载音频且尚未转录）",
                transcribe_fn=lambda vd: self.downloader.transcribe_audio_detail(
                    vd, self.language
                ),
                fail_message="音频转录失败",
            )

        def transcribe_selected():
            _run_transcribe_batch(
                _collect_videos_needing_transcript(require_audio=False),
                task_name="转录",
                confirm_title="确认转录",
                confirm_verb="转录",
                empty_warning="没有可转录的视频",
                transcribe_fn=lambda vd: self.downloader.transcribe_video_detail(
                    vd, self.language, batch_mode=True
                ),
                fail_message=(
                    "转录失败：无法下载字幕或音频转录失败"
                    if config.TRANSCRIBE_FALLBACK_TO_AUDIO
                    else "转录失败：无法下载字幕（音频转录 fallback 已关闭）"
                ),
                pre_task=lambda: (
                    self.downloader.reset_batch_transcribe_strategy(),
                    self.downloader._check_and_update_cookies(wait_forever=False),
                ),
            )


        def tag_selected():
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            for video_detail in _unique_video_details_from_tree_selection():
                self.update_text_content(video_detail)
                self.prepare_category_for_content(video_detail, self.topic_choices)

            populate_tree()


        def export_selected_choices():
            """将树中选中行导出到 aiagent/video_choice_queue.json，供 CLI 逐条取用。"""
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            from cli.video_choice_queue import export_video_details_to_queue

            details = _unique_video_details_from_tree_selection()
            if not details:
                messagebox.showwarning("提示", "未找到有效的视频条目", parent=dialog)
                return
            ch_path = self.channel_path or ""
            ch_id = config.get_channel_id(os.path.basename(ch_path)) if ch_path else ""
            list_path = (self.downloader.channel_list_json or "").strip()
            added, skipped, out_path = export_video_details_to_queue(
                details,
                channel_id=ch_id,
                channel_path=ch_path,
                list_json_path=list_path,
                title_fn=_youtube_row_display_title,
                yt_language=project_manager.LAST_YT_LANGUAGE,
                visual_style=project_manager.LAST_VISUAL_STYLE,
                narrator=project_manager.LAST_NARRATOR,
            )
            if added == 0:
                messagebox.showwarning(
                    "输出选择",
                    f"无有效条目可写入（跳过 {skipped} 条）。\n\n{out_path}",
                    parent=dialog,
                )
                return
            messagebox.showinfo(
                "输出选择",
                f"已覆盖写入 {added} 条"
                + (f"（跳过 {skipped} 条无效/重复）" if skipped else "")
                + f"\n\n{out_path}\n\n"
                "Telegram / Hermes 取用：打开 cli\\run_bot.bat（听筒会从队列打开摘要）。\n"
                "纯手工：不必开听筒，在本列表里打开摘要即可。",
                parent=dialog,
            )

        def list_summary():
            # new list for items in the list, only item with summary, include fields:
            # analyzed_content, title, url, topic_category, topic_subtype, tags
            summary_list = []
            seen_urls = set()
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                url_key = (video_detail.get('url') or item_tags[0] or '').strip()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                if video_detail.get("analyzed_content"):
                    summary_list.append({
                        'analyzed_content': video_detail.get("analyzed_content"),
                        'title': _youtube_row_display_title(video_detail),
                        'url': video_detail.get('url', ''),
                        'id': video_detail.get('id', ''),
                        'topic_category': video_detail.get('topic_category', ''),
                        'topic_subtype': video_detail.get('topic_subtype', ''),
                        'tags': video_detail.get('tags', ''),
                    })
            if not summary_list:
                messagebox.showwarning("提示", "没有可简表的视频", parent=dialog)
                return

            # save the summary_list to windows Download folder, file name same as channel_list_json, but with _summary.txt suffix
            with open(os.path.join(os.path.expanduser("~"), "Downloads", os.path.basename(self.downloader.channel_list_json)+"_summary.txt"), "w", encoding="utf-8") as f:
                json.dump(summary_list, f, ensure_ascii=False, indent=2)


        def summarize_selected(rewrite=False):
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            summary_list = []
            for video_detail in _unique_video_details_from_tree_selection():
                if not rewrite and video_detail.get("analyzed_content"):
                    summary_list.append( video_detail.get("analyzed_content") )
                    continue

                if not self.generate_analyzed_content_for_video(
                    video_detail, force_rewrite=rewrite
                ):
                    continue

                summary_list.append( video_detail.get("analyzed_content") )

                self.prepare_category_for_content(video_detail, self.topic_choices)

            if summary_list:
                summaries = ""
                for i, summary_content in enumerate(summary_list):
                    summaries += f"----------------------\nCase-Story {i+1}:\n {summary_content}\n\n"

                input_media_path = config.INPUT_MEDIA_PATH
                file_path = os.path.join(input_media_path, 'adjust_classification_on_case_study_summaries.txt')
                if os.path.exists(file_path):
                    os.remove(file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    classification_prompt = "Attached is the existing topics classification, each topic has a subtype. Below are some new case-study content, please adjust the existing topics, and then classify the new content clearly (find non-confusing category/subtype). These are typical psychological consultation problem case-studies:\n\n"
                    f.write(classification_prompt + summaries)

            populate_tree()


        def group_items_by_tag():
            """用当前筛选结果里的 analyzed_content，让便宜模型打上更细的分组 tag。"""
            if not self.content_mode:
                return
            picked_sub = (topic_subtype_var.get() or "").strip()
            batch = []
            for video in self.downloader.channel_videos:
                if picked_sub and picked_sub != "全部":
                    if (video.get("topic_subtype") or "").strip() != picked_sub:
                        continue
                body = (video.get("analyzed_content") or "").strip()
                if not body:
                    continue
                item_id = (video.get("id") or "").strip()
                if not item_id:
                    continue
                batch.append(video)
            if len(batch) < 2:
                messagebox.showwarning(
                    "分组标签",
                    "当前筛选里至少要有 2 条带分析内容、并且有 id 的视频。",
                    parent=dialog,
                )
                return
            scope = picked_sub if picked_sub and picked_sub != "全部" else "当前列表"
            if not messagebox.askyesno(
                "分组标签",
                f"按「{scope}」里的 {len(batch)} 条分析，分成更细的小组并写回每条的 tag。\n"
                "一条可以落在两个小组里，但会尽量分开。\n"
                "原来从预设标签里选的 tag 会被这批结果替换。",
                parent=dialog,
            ):
                return

            lines = []
            id_to_video = {}
            for video in batch:
                item_id = (video.get("id") or "").strip()
                id_to_video[item_id] = video
                title = _youtube_row_display_title(video) or item_id
                excerpt = (video.get("analyzed_content") or "").strip()
                if len(excerpt) > 700:
                    excerpt = excerpt[:700] + "…"
                lines.append(f"id={item_id}\n标题: {title}\n{excerpt}")
            lang_label = config.llm_language_label(self.language)
            system_prompt = config_prompt.GROUP_ITEM_TAGS_PROMPT.format(language=lang_label)
            user_prompt = "\n\n".join(lines)

            def work():
                err = ""
                parsed = None
                try:
                    parsed = self.llm_api_local.generate_json(
                        system_prompt, user_prompt, expect_list=False
                    )
                except Exception as exc:
                    err = str(exc)

                def apply():
                    if err:
                        show_auto_close_popup(dialog, "分组失败", err, kind="error")
                        return
                    groups = parsed.get("groups") if isinstance(parsed, dict) else None
                    if not isinstance(groups, list) or not groups:
                        messagebox.showwarning(
                            "分组标签", "模型没有返回分组。", parent=dialog
                        )
                        return
                    assigned: dict[str, list[str]] = {item_id: [] for item_id in id_to_video}
                    for group in groups:
                        if not isinstance(group, dict):
                            continue
                        tag = str(group.get("tag") or "").strip()
                        if not tag or "=" in tag:
                            continue
                        raw_ids = group.get("ids") or []
                        if isinstance(raw_ids, str):
                            raw_ids = [raw_ids]
                        for raw_id in raw_ids:
                            item_id = str(raw_id or "").strip()
                            if item_id not in assigned:
                                continue
                            if tag not in assigned[item_id]:
                                assigned[item_id].append(tag)
                    for item_id, tags in assigned.items():
                        id_to_video[item_id]["tags"] = tags
                    try:
                        _write_channel_list_json_file(
                            self.downloader.channel_list_json,
                            self.downloader.channel_videos,
                        )
                    except Exception as exc:
                        show_auto_close_popup(dialog, "写入失败", str(exc), kind="error")
                        return
                    topic_tag_var.set("全部")
                    populate_tree()
                    used = sorted({tag for tags in assigned.values() for tag in tags})
                    show_auto_close_popup(
                        dialog,
                        "已分组",
                        "写出的标签：\n" + ("、".join(used) if used else "（无）"),
                    )

                self.root.after(0, apply)

            threading.Thread(target=work, daemon=True).start()
            show_auto_close_popup(dialog, "分组标签", "正在按分析内容分组，请稍等。")


        # 在所有函数定义后创建按钮
        if self.content_mode:
            ttk.Button(bottom_frame, text="分组标签", command=group_items_by_tag).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="输出选择", command=export_selected_choices).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="输出简表", command=list_summary).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="摘要选择", command=lambda: summarize_selected(False)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="分类选择", command=tag_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="转录选择", command=transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="音频转录", command=audio_transcribe_selected).pack(side=tk.RIGHT, padx=5)
        if not self.content_mode:
            ttk.Button(bottom_frame, text="下载选择", command=download_selected).pack(side=tk.RIGHT, padx=5)
            ttk.Button(bottom_frame, text="信息更新", command=fetch_info_selected).pack(side=tk.RIGHT, padx=5)
            ttk.Button(bottom_frame, text="列表更新", command=update_video_list).pack(side=tk.RIGHT, padx=5)
