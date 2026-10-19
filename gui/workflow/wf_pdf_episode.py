"""PdfEpisodeMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import config
from PIL import Image, ImageTk
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import get_file_path, safe_clipboard_json_copy, show_auto_close_popup
from gui.choice_dialog import askchoice


class PdfEpisodeMixin:
    def open_adjust_episode_dialog(self):
        """手动调整集的边界：前面的场景归上一集，或从本场起归下一集。"""
        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("调整集", "请先选中一个场景。", parent=self.root)
            return
        self.update_current_scene()
        index = self.current_scene_index
        scenes = self.workflow.scenes or []
        start, end = self.workflow.episode_run_bounds(index)
        cur_name = self.workflow.scene_group(scenes[index])
        prev_name = self.workflow.scene_group(scenes[start - 1]) if start > 0 else ""
        next_name = self.workflow.scene_group(scenes[end + 1]) if end + 1 < len(scenes) else ""
        before = index - start + 1  # 本集开头到当前场景，含当前场景
        after = end - index + 1  # 当前场景到本集结尾，含当前场景

        dlg = tk.Toplevel(self.root)
        dlg.title("调整集")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        main = ttk.Frame(dlg, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            main,
            text=(
                f"现在是第 {cur_name} 集，当前是本集第 {before} 场，"
                f"本集共 {end - start + 1} 场。"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))

        focus_scene = scenes[index]

        def run(kind: str, direction: str) -> None:
            if kind == "merge":
                target, reason = self.workflow.merge_adjacent_episode(index, direction)
            else:
                target, reason = self.workflow.move_to_adjacent_episode(index, direction)
            if not target:
                messagebox.showwarning("调整集", reason, parent=dlg)
                return
            info = dict(getattr(self.workflow, "last_episode_op", {}) or {})
            self.workflow.save_scenes_to_json()
            dlg.destroy()
            # 还停在同一个场景（它的新位置）。
            for i, sc in enumerate(self.workflow.scenes or []):
                if sc is focus_scene:
                    self.current_scene_index = i
                    break
            self.refresh_gui_scenes()
            self._offer_episode_leftover_cleanup(info)
            if kind == "merge":
                msg = f"第 {info.get('absorbed')} 集已并进第 {target} 集"
            else:
                msg = f"已归到第 {target} 集"
            renamed = info.get("renamed") or []
            if renamed:
                msg += "；后面的集号往前补：" + "、".join(f"{n}→{m}" for n, m in renamed)
            if info.get("renumber_skipped"):
                messagebox.showwarning("调整集", info["renumber_skipped"], parent=self.root)
            missing = info.get("pages_missing") or []
            if missing:
                msg += f"；有 {len(missing)} 页原图已经不在（页码 {', '.join(map(str, missing))}），这几场的页码清掉了"
            show_auto_close_popup(self.root, "调整集", msg)

        is_first = index == start
        is_last = index == end
        # 整集都挪走会把本集挪空：那种情况用合并。
        prev_ok = bool(prev_name) and not is_last
        next_ok = bool(next_name) and not is_first
        prev_text = (
            f"本集开头到当前场景的 {before} 场，归到上一集（第 {prev_name} 集）"
            if prev_ok
            else "本集开头到当前场景归到上一集"
        )
        next_text = (
            f"当前场景到本集结尾的 {after} 场，归到下一集（第 {next_name} 集）"
            if next_ok
            else "当前场景到本集结尾归到下一集"
        )
        prev_btn = ttk.Button(main, text=prev_text, command=lambda: run("move", "prev"))
        prev_btn.pack(fill=tk.X, pady=(0, 6))
        next_btn = ttk.Button(main, text=next_text, command=lambda: run("move", "next"))
        next_btn.pack(fill=tk.X)
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        cur_num = self.workflow._episode_number(cur_name)
        split_ok = index < end and cur_num is not None

        def run_split() -> None:
            if not messagebox.askyesno(
                "调整集",
                f"从第{before}场之后分成新的一集（第{cur_num + 1}集）？\n"
                f"本集留下第 1–{before} 场，后面 {end - index} 场成为第{cur_num + 1}集，后面各集集号往后挪一个。",
                parent=dlg,
            ):
                return
            new_ep, reason = self.workflow.split_episode_after(index)
            if not new_ep:
                messagebox.showwarning("调整集", reason, parent=dlg)
                return
            info = dict(getattr(self.workflow, "last_episode_op", {}) or {})
            self.workflow.save_scenes_to_json()
            dlg.destroy()
            for i, sc in enumerate(self.workflow.scenes or []):
                if sc is focus_scene:
                    self.current_scene_index = i
                    break
            self.refresh_gui_scenes()
            msg = f"后面 {info.get('scenes')} 场成为第 {new_ep} 集"
            renamed = info.get("renamed") or []
            if renamed:
                msg += "；后面的集号往后挪：" + "、".join(f"{a}→{b}" for a, b in sorted(renamed))
            missing = info.get("pages_missing") or []
            if missing:
                msg += f"；有 {len(missing)} 页原图已经不在（页码 {', '.join(map(str, missing))}）"
            show_auto_close_popup(self.root, "调整集", msg)

        split_btn = ttk.Button(main, text="从本场之后分成新一集", command=run_split)
        split_btn.pack(fill=tk.X, pady=(0, 6))
        if not split_ok:
            split_btn.state(["disabled"])
        merge_prev_btn = ttk.Button(
            main, text="与上一集合并（本集接在上一集后面）", command=lambda: run("merge", "prev")
        )
        merge_prev_btn.pack(fill=tk.X, pady=(0, 6))
        merge_next_btn = ttk.Button(
            main, text="与下一集合并（下一集接在本集后面）", command=lambda: run("merge", "next")
        )
        merge_next_btn.pack(fill=tk.X)
        if not prev_ok:
            prev_btn.state(["disabled"])
        if not next_ok:
            next_btn.state(["disabled"])
        if not prev_name:
            merge_prev_btn.state(["disabled"])
            ttk.Label(main, text="没有上一集。", foreground="#888888").pack(anchor=tk.W, pady=(6, 0))
        if not next_name:
            merge_next_btn.state(["disabled"])
            ttk.Label(main, text="没有下一集。", foreground="#888888").pack(anchor=tk.W, pady=(6, 0))
        if is_first and next_name:
            ttk.Label(
                main, text=f"当前是第1场：整集移走请用『与下一集合并』。", foreground="#888888"
            ).pack(anchor=tk.W, pady=(6, 0))
        if is_last and prev_name:
            ttk.Label(
                main, text="当前是最后一场：整集移走请用『与上一集合并』。", foreground="#888888"
            ).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            main,
            text="动之前 scenes.json 和 PDF 导入记录会备份到项目的 _backup 文件夹。",
            foreground="#888888",
        ).pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(main, text="取消", command=dlg.destroy).pack(anchor=tk.E, pady=(10, 0))
        try:
            dlg.geometry(f"+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 120}")
        except tk.TclError:
            pass
        dlg.grab_set()

    def _offer_episode_leftover_cleanup(self, info: dict) -> None:
        """并掉的那一集（或被挪空的那一集）文件夹里只剩没用到的文件：问一下要不要删。"""
        folder = (info or {}).get("leftover_dir") or ""
        if not folder or not os.path.isdir(folder):
            return
        episode = info.get("absorbed") or info.get("source") or "?"
        files = self.workflow.folder_leftovers(folder)
        if not files:
            self.workflow.trash_leftovers(folder, str(episode))  # 空文件夹直接去掉
            return
        shown = "\n".join(os.path.basename(f) for f in files[:12])
        if len(files) > 12:
            shown += f"\n……（共 {len(files)} 个）"
        ok = messagebox.askyesno(
            "调整集",
            f"第{episode}集文件夹还剩 {len(files)} 个没有用到的文件，删除吗？\n\n{folder}\n\n{shown}",
            parent=self.root,
        )
        if not ok:
            messagebox.showinfo("调整集", f"这些文件留在：\n{folder}", parent=self.root)
            return
        res = self.workflow.trash_leftovers(folder, str(episode))
        where = "回收站" if res.get("method") == "recycle_bin" else res.get("trash_dir")
        text = f"已删除 {res.get('count', 0)} 个文件（放进 {where}）。"
        if res.get("failed"):
            text += "\n有些没删掉：\n" + "\n".join(res["failed"][:8])
        messagebox.showinfo("调整集", text, parent=self.root)

    def _on_media_drop_pdf(self, pdf_path: str, origin: str = "drop", cross_episodes: bool = False) -> None:
        """拖进来的 PDF（origin="drop"）或全集生成下载的 PDF（origin="全集生成"）：先拆到临时目录预览；
        分配给场景时才复制进本集 media 文件夹。每次拆页都记进本集（当前场景所在集）的 PDF 导入记录。

        ``cross_episodes``：全集生成选了「本集到结束」且跨了几集。这时「写到结束」写完本集后接着写后面各集，
        每页复制进那一集自己的 media 文件夹（接在那一集已有页之后编号）。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("PDF", "请先选中一个场景。", parent=self.root)
            return
        group_name = self.workflow.scene_group(scene)
        if not str(scene.get("episode") or "").strip():
            scene["episode"] = group_name
            scene.pop("group", None)
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            folder, pages = self.workflow.split_pdf_to_staging(pdf_path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("PDF", f"拆页失败：{e}", parent=self.root)
            return
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        if not pages:
            messagebox.showwarning("PDF", "这个 PDF 没有可用的页。", parent=self.root)
            return
        print(f"✅ PDF 拆成 {len(pages)} 页，临时目录：{folder}")
        try:
            self.workflow.record_pdf_import(group_name, pdf_path, folder, len(pages), origin)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 记录 PDF 导入失败：{e}")
        staging = {
            "dir": folder,
            "base": self.workflow.episode_next_page_base(group_name),
            "pdf": os.path.abspath(pdf_path),
            "cross_episodes": bool(cross_episodes),
        }
        self._open_pdf_page_review(
            folder, list(pages), group_name, os.path.basename(pdf_path), initial_index=0, staging=staging
        )

    def _episode_page_pngs(self, group_name: str) -> list[str]:
        """media/<episode>/ 里按页码排好的页面图。"""
        return self.workflow._episode_png_paths(group_name)

    def _resolve_scene_episode_pdf(self, scene: dict) -> str:
        """当前场景 episode_pdf 指向的文件。找不到就返回空。"""
        name = str(scene.get("episode_pdf") or "").strip()
        if not name:
            return ""
        if os.path.isfile(name):
            return os.path.abspath(name)
        base = os.path.basename(name)
        group_name = self.workflow.scene_group(scene)
        media = config.get_media_path(self.workflow.pid)
        gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
        candidates = [
            os.path.join(gen_dir, base) if gen_dir else "",
            os.path.join(media, group_name, base),
            os.path.join(media, base),
        ]
        pc = project_manager.PROJECT_CONFIG
        slide = (pc.get("slide") or "").strip() if isinstance(pc, dict) else ""
        if slide and os.path.basename(slide) == base:
            candidates.append(slide)
        for path in candidates:
            if path and os.path.isfile(path):
                return os.path.abspath(path)
        return ""

    def _scenes_as_prompt_content(self, scenes: list, episode_name: str) -> str:
        """把这一集（或一场）的场景描述收成提示词材料，不带媒体路径。"""
        fields = ("caption", "visual", "speaking", "voiceover", "actor")
        blocks = [f"Episode {episode_name}. {len(scenes)} scene(s)."]
        for i, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            lines = [f"Scene {i}"]
            for key in fields:
                text = str(scene.get(key) or "").strip()
                if text:
                    lines.append(f"{key}: {text}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks).strip()

    def _episode_pdf_for_prompt(self, scene: dict) -> str:
        group_name = self.workflow.scene_group(scene)
        generated = self.workflow.episode_pdf_path(group_name)
        if os.path.isfile(generated):
            return generated
        return self._resolve_scene_episode_pdf(scene)

    def _ask_episode_prompt(self, choices: list, materials: list) -> tuple[str, str] | None:
        """一个窗口里选提示词，材料用下拉框，默认这一集的内容。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("拷贝哪一种提示词？")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()
        result: list = [None]
        material_labels = [label for _, label in materials]
        material_by_label = {label: key for key, label in materials}

        main = ttk.Frame(dlg, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main, text="拷贝哪一种提示词？", font=("Arial", 12, "bold")).pack(pady=(4, 10))

        mat_row = ttk.Frame(main)
        mat_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(mat_row, text="材料").pack(side=tk.LEFT, padx=(0, 8))
        material_var = tk.StringVar(value=material_labels[0])
        ttk.Combobox(
            mat_row,
            textvariable=material_var,
            values=material_labels,
            state="readonly",
            width=22,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def on_choice(label: str):
            result[0] = (label, material_by_label.get(material_var.get(), materials[0][0]))
            dlg.destroy()

        for choice_label, _template in choices:
            ttk.Button(
                main,
                text=choice_label,
                width=36,
                command=lambda lb=choice_label: on_choice(lb),
            ).pack(pady=3, fill=tk.X)
        ttk.Button(main, text="取消", width=16, command=dlg.destroy).pack(pady=(12, 4))

        dlg.update_idletasks()
        width = max(420, dlg.winfo_reqwidth())
        height = dlg.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dlg.geometry(f"{width}x{height}+{x}+{y}")
        dlg.wait_window()
        return result[0]

    def copy_episode_prompt(self):
        """按频道里的场景提示词，用这一集的文字或 PDF 填好，拷到剪贴板。"""
        from gui.downloader import (
            _format_nb_prompt_template,
            _pdf_pages_as_scene_source,
            _prompt_choice_entries,
            _prompt_text_for_material,
        )

        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("拷提", "请先选中一个场景。", parent=self.root)
            return
        pc = project_manager.PROJECT_CONFIG or {}
        channel = (pc.get("channel") or getattr(self.workflow, "channel", "") or "").strip()
        choices = _prompt_choice_entries(channel)
        if not choices:
            messagebox.showwarning("拷提", "这个频道没有场景提示词。", parent=self.root)
            return
        materials = [
            ("episode_text", "这一集的内容"),
            ("scene_text", "当前场景的文字"),
            ("pdf", "这一集的 PDF"),
        ]
        picked = self._ask_episode_prompt(choices, materials)
        if not picked:
            return
        label, kind = picked
        template = ""
        for choice_label, choice_template in choices:
            if choice_label == label:
                template = choice_template
                break
        if not template:
            return
        group_name = self.workflow.scene_group(scene)
        if kind == "scene_text":
            content = self._scenes_as_prompt_content([scene], group_name)
        elif kind == "pdf":
            pdf_path = self._episode_pdf_for_prompt(scene)
            content, _page_count, _ = _pdf_pages_as_scene_source(pdf_path)
            if not content:
                messagebox.showwarning("拷提", "这一集没有可引用的 PDF。", parent=self.root)
                return
        else:
            indices = self.workflow.group_scene_indices(group_name)
            episode_scenes = [
                self.workflow.scenes[i]
                for i in indices
                if 0 <= i < len(self.workflow.scenes)
            ]
            content = self._scenes_as_prompt_content(episode_scenes, group_name)
        if not content:
            messagebox.showwarning("拷提", "这一集没有可拷贝的场景文字。", parent=self.root)
            return
        ch_cfg = config.get_channel_config(channel) or {}
        topic = (pc.get("topic") or ch_cfg.get("topic") or "").strip()
        narrator = (pc.get("narrator") or "").strip()
        language = config.llm_language_label(
            getattr(self.workflow, "language", "") or pc.get("language") or ""
        )
        prompt = _format_nb_prompt_template(
            template,
            content=content,
            instruction="",
            language=language,
            topic=topic,
            narrator=narrator,
        )
        prompt = _prompt_text_for_material(prompt, "pdf" if kind == "pdf" else "analyzed")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
            self.root.update_idletasks()
        except tk.TclError:
            messagebox.showwarning("拷提", "没能写入剪贴板。", parent=self.root)
            return
        show_auto_close_popup(self.root, "拷提", f"已拷贝提示词：{label}")

    def paste_episode_scenes(self):
        """把剪贴板里的场景 JSON 合并回这一集。只覆盖 JSON 里有的文案字段。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("贴回", "请先选中一个场景。", parent=self.root)
            return
        try:
            raw = safe_clipboard_json_copy(self.root.clipboard_get())
        except tk.TclError:
            raw = ""
        parsed = config.parse_json_from_text(raw) if raw else None
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, dict) for item in parsed):
            messagebox.showwarning(
                "贴回",
                "剪贴板里不是场景 JSON。需要一个场景对象，或一组场景。",
                parent=self.root,
            )
            return
        picked = askchoice(
            "贴回到哪里？只覆盖 JSON 里有的字段，图片和声音留着。",
            [
                ("from_start", "从本集开头写入"),
                ("from_here", "从当前场景往后"),
            ],
            self.root,
        )
        if not picked:
            return
        self.update_current_scene()
        group_name = self.workflow.scene_group(scene)
        indices = self.workflow.group_scene_indices(group_name)
        if picked[1] == "from_here":
            indices = [i for i in indices if i >= self.current_scene_index]
        if not indices:
            messagebox.showwarning("贴回", "这一集没有可写入的场景。", parent=self.root)
            return
        keep = self._SCENE_IMPORT_SKIP_KEYS | {
            "id",
            "episode",
            "group",
            "episode_page",
            "episode_pdf",
            "group_page",
            "group_pdf",
            "clip",
            "zero",
            "narration",
            "background_music",
        }
        written = 0
        fields = 0
        for offset, item in enumerate(parsed):
            if offset >= len(indices):
                break
            cleaned = {
                key: val
                for key, val in item.items()
                if key not in keep and not str(key).endswith(("_image", "_audio", "_last"))
            }
            n = self._apply_scene_import_item(self.workflow.scenes[indices[offset]], cleaned)
            if n:
                written += 1
                fields += n
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        used = min(len(parsed), len(indices))
        extra = len(parsed) - used
        msg = f"写入了 {used} 场，覆盖了 {fields} 个字段。"
        if extra > 0:
            msg += f" 剪贴板里还有 {extra} 场没有落下去，这一集后面没有空位了。"
        messagebox.showinfo("贴回", msg, parent=self.root)

    def copy_current_episode_pdf(self):
        """拷贝这一集的 PDF。有页面图时才在这里合成；文件夹时间和 PDF 一致就直接拷。"""
        from gui.downloader import _copy_file_to_clipboard_hdrop

        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        group_name = self.workflow.scene_group(scene)
        pngs = self.workflow._episode_png_paths(group_name)
        rebuilt = False
        if pngs:
            pdf_path = self.workflow.episode_pdf_path(group_name)
            if not self.workflow.episode_pdf_is_current(group_name):
                try:
                    self.root.config(cursor="watch")
                    self.root.update_idletasks()
                    pdf_path = self.workflow.build_episode_pdf(group_name)
                    rebuilt = True
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("拷集", f"合成 PDF 失败：{e}", parent=self.root)
                    return
                finally:
                    try:
                        self.root.config(cursor="")
                    except tk.TclError:
                        pass
        else:
            pdf_path = self._resolve_scene_episode_pdf(scene)
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showwarning("拷集", "这一集没有可拷贝的 PDF。", parent=self.root)
            return
        if _copy_file_to_clipboard_hdrop(self.root, pdf_path):
            note = "已重新生成并拷贝" if rebuilt else "已拷贝"
            show_auto_close_popup(
                self.root,
                "拷集",
                f"{note}这一集的 PDF：\n{os.path.basename(pdf_path)}",
            )

    def _assign_scene_clip_image_from_file(self, scene: dict, image_path: str) -> None:
        """把已经拆好的页图拷到场景的 clip_image，不缩放、不转格式。"""
        ext = os.path.splitext(image_path)[1].lower() or ".webp"
        refresh_scene_media(scene, "clip_image", ext, image_path, True)

    def _tag_scene_pdf_page(self, scene: dict, group_name: str, page_no: int, pdf_name: str) -> None:
        scene["episode"] = group_name
        scene["episode_page"] = int(page_no)
        scene["episode_pdf"] = pdf_name
        scene.pop("group", None)
        scene.pop("group_page", None)
        scene.pop("group_pdf", None)

    def _pool_clip_slot_image(self, scene: dict, image_type: str, image_path: str) -> None:
        """clip 的起始图或结束图换了以后，加进这一集的图片库：接在最大编号后面，不覆盖。

        起始图记成这一场的页；结束图只放进库里，不改这一场的页。
        """
        if image_type not in ("clip_image", "clip_image_last"):
            return
        if not isinstance(scene, dict) or not image_path or not os.path.isfile(image_path):
            return
        self.workflow.write_scene_page_png(
            scene, image_path, tag_scene=(image_type == "clip_image")
        )

    def _after_clip_image_changed(self, scene: dict, summary: str) -> None:
        """起始图换了以后，问要不要用新图加这一场的音频重做 clip 视频（没有音频就不问）。"""
        audio = get_file_path(scene, "clip_audio") if isinstance(scene, dict) else ""
        if not audio or not os.path.isfile(audio):
            show_auto_close_popup(self.root, "放入", summary)
            return
        self.root.after(200, lambda: self._offer_still_videos_after_pdf([scene], summary))

    def _offer_still_videos_after_pdf(self, scenes: list, summary: str) -> None:
        """页图写进 clip_image 之后，直接用新图加音频重做这些场景的 clip 视频（不再询问）。"""
        scenes = [s for s in scenes if isinstance(s, dict)]
        if not scenes:
            messagebox.showinfo("PDF", summary, parent=self.root)
            return
        show_auto_close_popup(
            self.root,
            "重新生成 clip 视频",
            f"{summary}\n\n正在用新的 clip 图片加 clip 音频重新生成 {len(scenes)} 场的 clip 视频"
            "（替换原来的；没有 clip 音频的场景会跳过）。",
        )
        self._run_still_clip_videos(scenes)

    def _pdf_import_label(self, entry: dict) -> str:
        """来源下拉框里一条导入记录的名字：<pdf 名> · N页 · 时间。"""
        when = str(entry.get("imported_at") or "")
        when = when[5:16] if len(when) >= 16 else when  # MM-DD HH:MM
        origin = "全集生成" if entry.get("origin") == "全集生成" else ""
        parts = [entry.get("pdf_name") or "PDF", f"{int(entry.get('page_count') or 0)}页", when]
        if origin:
            parts.append(origin)
        return " · ".join(p for p in parts if p)

    def _open_pdf_page_review(
        self,
        folder: str,
        pages: list[str],
        group_name: str,
        pdf_name: str,
        initial_index: int = 0,
        staging: dict | None = None,
    ) -> None:
        """翻页查看页图。左右方向键翻页；当前页 → 当前场景；从当前页写到本集结束。

        顶上的「来源」下拉框：本集媒体文件夹（双击 clip 的原样），或本集导入过的某个 PDF 的拆页文件夹。
        选 PDF 时分配会先把页复制进本集 media 文件夹再写到场景（同拖进 PDF 后的预览）。
        ``staging`` 给了就是刚导入的那个 PDF，打开时选中它。
        """
        dlg = tk.Toplevel(self.root)
        dlg.title(f"PDF 页面 · 第 {group_name} 集")
        dlg.geometry("980x820")
        dlg.minsize(720, 580)
        dlg.transient(self.root)
        MEDIA_LABEL = "本集媒体文件夹"
        media_folder = os.path.join(config.get_media_path(self.workflow.pid), group_name)
        # 当前来源：staging 为 None = 本集媒体文件夹
        state = {"staging": staging, "pdf_name": pdf_name, "folder": folder, "missing": False}
        history: list[dict] = []
        # 本集媒体文件夹来源分配时记的 episode_pdf：双击打开时就是本集 PDF；从导入预览切回来时用当前场景的本集 PDF
        if staging is None:
            media_pdf_name = pdf_name
        else:
            cur = self.workflow.get_scene_by_index(self.current_scene_index) or {}
            media_pdf_name = os.path.basename(self._resolve_scene_episode_pdf(cur) or "") if isinstance(cur, dict) else ""
        idx = [max(0, min(int(initial_index or 0), max(0, len(pages) - 1)))]

        def _fresh_pages() -> list:
            """预览读哪里：PDF 拆页目录（staging），或本集 media 文件夹。"""
            st = state["staging"]
            if st:
                return self.workflow.staged_page_paths(st["dir"])
            if state["missing"]:
                return []
            return self._episode_page_pngs(group_name)

        def _episode_no(page_no: int) -> int:
            """临时页号 → 本集页号（接在已有页之后，同旧的拆页编号）。"""
            st = state["staging"]
            return int(st["base"]) + int(page_no) if st else int(page_no)

        def _assign_image(scene: dict, i: int) -> int:
            """分配第 i 页给场景：PDF 来源时先复制进本集 media 文件夹。返回本集页号。"""
            page_no = _page_number(i)
            src = pages[i]
            st = state["staging"]
            if st:
                page_no = _episode_no(page_no)
                src = self.workflow.stage_page_into_episode(src, group_name, page_no)
            self._assign_scene_clip_image_from_file(scene, src)
            self._tag_scene_pdf_page(scene, group_name, page_no, state["pdf_name"])
            return page_no

        # ---- 来源 ----
        src_row = ttk.Frame(dlg)
        src_row.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(src_row, text="来源").pack(side=tk.LEFT, padx=(0, 6))
        source_var = tk.StringVar(value=MEDIA_LABEL)
        source_box = ttk.Combobox(src_row, textvariable=source_var, state="readonly", width=70)
        source_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        source_note = tk.Label(src_row, text="", anchor="w", fg="#888888")
        source_note.pack(side=tk.LEFT, padx=(8, 0))

        photo_holder: list = [None]
        showing = [False]

        canvas = tk.Canvas(dlg, bg="#222", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        status = ttk.Label(dlg, text="", anchor="w")
        status.pack(fill=tk.X, padx=8, pady=(6, 2))
        usage_lbl = tk.Label(dlg, text="", anchor="w", font=("Microsoft YaHei UI", 11, "bold"))
        usage_lbl.pack(fill=tk.X, padx=8, pady=(0, 2))
        hint_lbl = tk.Label(dlg, text="", anchor="w", fg="#1a4fa0")
        hint_lbl.pack(fill=tk.X, padx=8, pady=(0, 2))
        path_lbl = ttk.Label(dlg, text=folder, anchor="w")
        path_lbl.pack(fill=tk.X, padx=8)

        def _cross() -> bool:
            st = state["staging"]
            return bool(st and st.get("cross_episodes"))

        def _forward_targets(page_i: int) -> list:
            """跨集「写到结束」要写的 [(场景序号, 集名)]：本集从当前场景起，再接后面各集全部场景，页用完为止。"""
            indices = self.workflow.group_scene_indices(group_name)
            cur = self.current_scene_index
            if cur not in indices:
                return []
            out = [(i, group_name) for i in indices[indices.index(cur):]]
            later = self.workflow.episode_groups_from(self.workflow.scenes[cur])[1:]
            for g in later:
                out.extend((i, g) for i in self.workflow.group_scene_indices(g))
            return out[: max(0, len(pages) - page_i)]

        def _forward_hint(page_i: int) -> str:
            """“写到本集结束”按下去会写哪几场，不会超出本集（跨集模式会接着写后面各集）。"""
            if _cross():
                targets = _forward_targets(page_i)
                if not targets:
                    return f"当前场景不在第 {group_name} 集，不能“写到结束”。"
                groups_hit = []
                for _i, g in targets:
                    if g not in groups_hit:
                        groups_hit.append(g)
                return (
                    f"写到结束（跨集）：从当前场景起写 {len(targets)} 场，"
                    f"第 {groups_hit[0]}" + (f"–{groups_hit[-1]}" if len(groups_hit) > 1 else "") + " 集，"
                    f"用 {len(targets)} 张图；每集的页复制进那一集自己的文件夹。"
                )
            indices = self.workflow.group_scene_indices(group_name)
            cur = self.current_scene_index
            if cur not in indices:
                return f"当前场景不在第 {group_name} 集，不能“写到本集结束”。"
            pos = indices.index(cur)
            left_scenes = len(indices) - pos
            left_pages = len(pages) - page_i
            n = min(left_scenes, left_pages)
            return (
                f"写到本集结束：从当前场景（本集第 {pos + 1} 场）起，写到本集第 {pos + n} 场"
                f"（本集共 {len(indices)} 场），用 {n} 张图；"
                + ("本集最后一场到此为止。" if left_pages >= left_scenes else "图先用完。")
            )

        def _scene_label() -> str:
            n = len(self.workflow.group_scene_indices(group_name))
            return f"第 {group_name} 集 · 本集 {n} 个场景"

        def _page_users(page_no: int) -> list[str]:
            """这一页被本集哪些场景用着，返回类似 '本集第 3 场（全部第 12 场）' 的说明。"""
            users: list[str] = []
            for pos, gi in enumerate(self.workflow.group_scene_indices(group_name), start=1):
                scene = self.workflow.scenes[gi]
                try:
                    n = int(scene.get("episode_page") or 0)
                except (TypeError, ValueError):
                    n = 0
                if n == page_no:
                    users.append(f"本集第 {pos} 场（全部第 {gi + 1} 场）")
            return users

        def _show_page(_event=None):
            if showing[0] or not dlg.winfo_exists():
                return
            showing[0] = True
            try:
                _show_page_body()
            finally:
                showing[0] = False

        def _show_page_body():
            # 每次都重新读文件夹，总页数以文件夹里实际有的图为准，和场景数无关。
            pages[:] = _fresh_pages()
            canvas.delete("all")
            if not pages:
                photo_holder[0] = None
                msg = "这个来源的拆页文件夹和原 PDF 都不在了。" if state["missing"] else "这个来源里没有页图。"
                canvas.create_text(20, 20, text=msg, anchor="nw", fill="#aaaaaa", font=("Microsoft YaHei UI", 14))
                status.config(text=f"0 张图    {_scene_label()}")
                usage_lbl.config(text="")
                hint_lbl.config(text="")
                return
            idx[0] = max(0, min(idx[0], len(pages) - 1))
            i = idx[0]
            path = pages[i]
            try:
                img = Image.open(path).convert("RGB")
            except Exception as e:  # noqa: BLE001
                status.config(text=f"无法打开 {os.path.basename(path)}：{e}")
                return
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw < 80 or ch < 80:
                cw, ch = 900, 560
            iw, ih = img.size
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            photo_holder[0] = photo
            canvas.create_image(cw // 2, ch // 2, image=photo)
            page_no = _page_number(i)
            if state["staging"]:
                # PDF 来源：这一页还没复制进本集，只能看本集同号的页有没有人用（分配后才算）
                users = []
                usage_text = f"PDF 第 {page_no} 页 → 分配后成为本集第 {_episode_no(page_no)} 页"
                usage_color = "#1a4fa0"
                badge = f"{state['pdf_name']} · 第 {page_no} 页"
                badge_color = "#FFD54F"
            else:
                users = _page_users(_episode_no(page_no))
                if users:
                    usage_text = f"第 {page_no} 页 → 已分给：" + "、".join(users)
                    usage_color = "#0a6b0a"
                    badge = "场景：" + "、".join(u.split("（")[0] for u in users)
                    badge_color = "#7CFC7C"
                else:
                    usage_text = f"第 {page_no} 页 → 还没有被任何场景使用"
                    usage_color = "#b00020"
                    badge = "还没有被任何场景使用"
                    badge_color = "#FF8A80"
            usage_lbl.config(text=usage_text, fg=usage_color)
            hint_lbl.config(text=_forward_hint(i))
            canvas.create_text(
                13, 13, text=badge, anchor="nw", fill="#000000", font=("Microsoft YaHei UI", 14, "bold")
            )
            canvas.create_text(
                11, 11, text=badge, anchor="nw", fill=badge_color, font=("Microsoft YaHei UI", 14, "bold")
            )
            where = "PDF 拆页" if state["staging"] else "本集文件夹"
            status.config(
                text=(
                    f"{where}共 {len(pages)} 张图，当前第 {i + 1} / {len(pages)} 张"
                    f"（{os.path.basename(path)}）    {_scene_label()}"
                )
            )

        def _step(delta: int):
            pages[:] = _fresh_pages()
            if not pages:
                return
            idx[0] = (idx[0] + delta) % len(pages)
            _show_page()

        def _page_number(i: int) -> int:
            """第 i 张图在 PDF 里的页码（文件名里的数字）。"""
            stem = os.path.splitext(os.path.basename(pages[i]))[0]
            return int(stem) if stem.isdigit() else i + 1

        def _assign_current():
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not scene:
                messagebox.showwarning("PDF", "请先在主窗口选中一个场景。", parent=dlg)
                return
            if not pages:
                return
            try:
                page_no = _assign_image(scene, idx[0])
                self.workflow.save_scenes_to_json()
                self.display_image_on_canvas_for_track("clip_image")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("PDF", f"写入 clip_image 失败：{e}", parent=dlg)
                return
            dlg.destroy()
            self.root.after(
                50,
                lambda sc=[scene], msg=f"第 {page_no} 页已写入当前场景（第 {group_name} 集）。": (
                    self._offer_still_videos_after_pdf(sc, msg)
                ),
            )

        def _assign_forward():
            """从正在看的这一页起，写入当前场景和本集后面的场景。场数不改。

            写到本集最后一场，或者页用完为止，两者先到的那个。场景比页数多时，多出的场景不动。
            """
            scene_i = self.current_scene_index
            if scene_i < 0 or scene_i >= len(self.workflow.scenes):
                messagebox.showwarning("PDF", "请先在主窗口选中一个场景。", parent=dlg)
                return
            if not pages:
                return
            page_i = idx[0]
            written = 0
            first_page = _episode_no(_page_number(page_i))
            last_page_no = first_page
            written_scenes: list = []
            if _cross():
                # 跨集：本集照旧（_assign_image），后面各集每页复制进那一集的 media 文件夹，接在已有页之后编号。
                bases: dict = {}
                counts: dict = {}
                groups_hit: list = []
                try:
                    for gi, g in _forward_targets(page_i):
                        scene = self.workflow.scenes[gi]
                        if g == group_name:
                            last_page_no = _assign_image(scene, page_i)
                        else:
                            if g not in bases:
                                bases[g] = self.workflow.episode_next_page_base(g)
                            counts[g] = counts.get(g, 0) + 1
                            page_no = bases[g] + counts[g]
                            src = self.workflow.stage_page_into_episode(pages[page_i], g, page_no)
                            self._assign_scene_clip_image_from_file(scene, src)
                            self._tag_scene_pdf_page(scene, g, page_no, state["pdf_name"])
                        if g not in groups_hit:
                            groups_hit.append(g)
                        written += 1
                        written_scenes.append(scene)
                        page_i += 1
                    self.workflow.save_scenes_to_json()
                    self.display_image_on_canvas_for_track("clip_image")
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("PDF", f"写入 clip_image 失败：{e}", parent=dlg)
                    return
                dlg.destroy()
                span = (f"第 {groups_hit[0]}–{groups_hit[-1]} 集" if len(groups_hit) > 1
                        else f"第 {groups_hit[0]} 集" if groups_hit else "")
                summary = f"从 PDF 第 {_page_number(idx[0])} 页起，写入了{span}共 {written} 场。"
                self.root.after(
                    50,
                    lambda sc=list(written_scenes), msg=summary: self._offer_still_videos_after_pdf(sc, msg),
                )
                return
            try:
                while scene_i < len(self.workflow.scenes) and page_i < len(pages):
                    scene = self.workflow.scenes[scene_i]
                    if not isinstance(scene, dict) or self.workflow.scene_group(scene) != group_name:
                        break
                    last_page_no = _assign_image(scene, page_i)
                    written += 1
                    written_scenes.append(scene)
                    scene_i += 1
                    page_i += 1
                self.workflow.save_scenes_to_json()
                self.display_image_on_canvas_for_track("clip_image")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("PDF", f"写入 clip_image 失败：{e}", parent=dlg)
                return
            dlg.destroy()
            summary = (
                f"从第 {first_page} 页起，写入了当前场景及本集后面共 {written} 场"
                + (f"（到第 {last_page_no} 页）" if written else "")
                + "。"
            )
            self.root.after(
                50,
                lambda sc=list(written_scenes), msg=summary: self._offer_still_videos_after_pdf(sc, msg),
            )

        bar = ttk.Frame(dlg)
        bar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(bar, text="上一页", command=lambda: _step(-1)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="下一页", command=lambda: _step(1)).pack(side=tk.LEFT, padx=(0, 16))

        def _open_external():
            st = state["staging"]
            if not st or not st.get("pdf"):
                return
            try:
                os.startfile(st["pdf"])
            except OSError as exc:
                messagebox.showwarning("PDF", f"打不开：{exc}", parent=dlg)

        ext_btn = ttk.Button(bar, text="外部打开 PDF", command=_open_external)
        ext_btn.pack(side=tk.RIGHT)
        assign_btn = ttk.Button(bar, text="当前页 → 当前场景", command=_assign_current)
        assign_btn.pack(side=tk.LEFT, padx=(0, 6))
        forward_btn = ttk.Button(
            bar, text=("写到结束（跨集）" if _cross() else "写到本集结束"), command=_assign_forward
        )
        forward_btn.pack(side=tk.LEFT)

        def _sync_buttons():
            st = state["staging"]
            can_open = bool(st and st.get("pdf") and os.path.isfile(st["pdf"]))
            ext_btn.state(["!disabled"] if can_open else ["disabled"])
            ok = not state["missing"]
            forward_btn.config(text=("写到结束（跨集）" if _cross() else "写到本集结束"))
            for b in (assign_btn, forward_btn):
                b.state(["!disabled"] if ok else ["disabled"])

        def _labels() -> list[str]:
            return [MEDIA_LABEL] + [self._pdf_import_label(e) for e in history]

        def _reload_history():
            history[:] = self.workflow.pdf_import_history(group_name)
            source_box.config(values=_labels())

        def _select_source(pos: int):
            """pos 0 = 本集媒体文件夹；1.. = history[pos-1]。"""
            state["missing"] = False
            source_note.config(text="")
            if pos <= 0 or pos > len(history):
                state.update(staging=None, pdf_name=media_pdf_name, folder=media_folder)
                source_var.set(MEDIA_LABEL)
                dlg.title(f"PDF 页面 · 第 {group_name} 集 · {MEDIA_LABEL}")
                path_lbl.config(text=media_folder)
            else:
                entry = history[pos - 1]
                try:
                    dlg.config(cursor="watch")
                    dlg.update_idletasks()
                    found, how = self.workflow.ensure_pdf_import_pages(group_name, entry)
                except Exception as e:  # noqa: BLE001
                    found, how = [], "missing"
                    print(f"⚠️ 重新拆页失败：{e}")
                finally:
                    try:
                        dlg.config(cursor="")
                    except tk.TclError:
                        pass
                state.update(
                    staging={
                        "dir": entry.get("split_dir") or "",
                        "base": self.workflow.episode_next_page_base(group_name),
                        "pdf": entry.get("source_path") or "",
                    },
                    pdf_name=entry.get("pdf_name") or "",
                    folder=entry.get("split_dir") or "",
                )
                if how == "missing":
                    state["missing"] = True
                    source_note.config(text="（拆页文件夹和原 PDF 都不在了）", fg="#888888")
                elif how == "resplit":
                    source_note.config(text="（拆页文件夹不在，已从原 PDF 重新拆）", fg="#1a4fa0")
                    _reload_history()
                source_box.current(pos)
                dlg.title(f"PDF 页面 · 第 {group_name} 集 · {entry.get('pdf_name') or 'PDF'}")
                path_lbl.config(text=state["folder"], foreground=("#888888" if state["missing"] else ""))
            idx[0] = 0
            _sync_buttons()
            _show_page()

        def _on_source(_event=None):
            _select_source(source_box.current())

        source_box.bind("<<ComboboxSelected>>", _on_source)
        _reload_history()
        # 打开时选哪个：刚导入的 PDF（staging）就选它那条，否则本集媒体文件夹（原样）
        first_pos = 0
        if staging:
            first_pos = next(
                (n for n, e in enumerate(history, start=1)
                 if self.workflow._same_dir(e.get("split_dir"), staging.get("dir"))),
                0,
            )
        if staging and first_pos == 0:
            # 没有记录（不应发生）：照旧直接看这个临时目录
            source_var.set(os.path.basename(staging.get("dir") or "PDF"))
            path_lbl.config(text=staging.get("dir") or "")
            _sync_buttons()
        elif first_pos:
            source_box.current(first_pos)
            state["folder"] = history[first_pos - 1].get("split_dir") or folder
            path_lbl.config(text=state["folder"])
            dlg.title(f"PDF 页面 · 第 {group_name} 集 · {pdf_name}")
            _sync_buttons()
        else:
            source_box.current(0)
            dlg.title(f"PDF 页面 · 第 {group_name} 集 · {MEDIA_LABEL}")
            _sync_buttons()
            if not pages and history:
                # 本集文件夹里还没有页图：直接看最新导入的 PDF
                dlg.after(10, lambda: _select_source(1))

        def _on_left(_event=None):
            if isinstance(_event.widget, ttk.Combobox):
                return None
            _step(-1)
            return "break"

        def _on_right(_event=None):
            if isinstance(_event.widget, ttk.Combobox):
                return None
            _step(1)
            return "break"

        dlg.bind_all("<Left>", _on_left)
        dlg.bind_all("<Right>", _on_right)

        def _release_keys(_event=None):
            if _event is not None and _event.widget is not dlg:
                return
            try:
                dlg.unbind_all("<Left>")
                dlg.unbind_all("<Right>")
            except tk.TclError:
                pass

        dlg.bind("<Destroy>", _release_keys)
        canvas.bind("<Configure>", _show_page)
        # 测试和其他代码用：切换来源、分配
        dlg._pdf_review = {
            "select_source": _select_source,
            "assign_current": _assign_current,
            "assign_forward": _assign_forward,
            "forward_hint": _forward_hint,
            "state": state,
            "pages": pages,
            "labels": _labels,
            "idx": idx,
        }
        dlg.after(50, _show_page)
        dlg.after(80, canvas.focus_set)
