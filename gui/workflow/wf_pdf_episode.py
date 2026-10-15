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
    def split_current_group(self):
        """从当前场景起，把连续的同一集划成新的一集。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("拆集", "请先选中一个场景。", parent=self.root)
            return
        new_name = self.workflow.split_group_at(self.current_scene_index)
        if not new_name:
            return
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, "拆集", f"从当前场景起为第 {new_name} 集")

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
                f"现在是第 {cur_name} 集，当前是本集第 {before + 1} 场，"
                f"本集共 {end - start + 1} 场。"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))

        def run(direction: str) -> None:
            target, reason = self.workflow.move_to_adjacent_episode(index, direction)
            if not target:
                messagebox.showwarning("调整集", reason, parent=dlg)
                return
            self.workflow.save_scenes_to_json()
            dlg.destroy()
            self.refresh_gui_scenes()
            show_auto_close_popup(self.root, "调整集", f"已归到第 {target} 集")

        prev_ok = bool(prev_name)
        next_ok = bool(next_name)
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
        prev_btn = ttk.Button(main, text=prev_text, command=lambda: run("prev"))
        prev_btn.pack(fill=tk.X, pady=(0, 6))
        next_btn = ttk.Button(main, text=next_text, command=lambda: run("next"))
        next_btn.pack(fill=tk.X)
        if not prev_ok:
            prev_btn.state(["disabled"])
            ttk.Label(main, text="没有上一集。", foreground="#888888").pack(anchor=tk.W, pady=(6, 0))
        if not next_ok:
            next_btn.state(["disabled"])
            ttk.Label(main, text="没有下一集。", foreground="#888888").pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(main, text="取消", command=dlg.destroy).pack(anchor=tk.E, pady=(10, 0))
        try:
            dlg.geometry(f"+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 120}")
        except tk.TclError:
            pass
        dlg.grab_set()

    def _on_media_drop_pdf(self, pdf_path: str) -> None:
        """视频画布拖入 PDF：按当前 episode 拆成 1.webp、2.webp…，再打开翻页预览。"""
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
            folder, pages = self.workflow.export_pdf_pages_to_group(pdf_path, group_name)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("PDF", f"拆分失败：{e}", parent=self.root)
            return
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        if not pages:
            messagebox.showwarning("PDF", "这份 PDF 没有拆出页面。", parent=self.root)
            return
        print(f"✅ PDF 已拆成 {len(pages)} 页，加进第 {group_name} 集图片库：{folder}")
        all_pages = self._episode_page_pngs(group_name)
        start_idx = 0
        try:
            first_new = os.path.abspath(pages[0])
            for i, path in enumerate(all_pages):
                if os.path.abspath(path) == first_new:
                    start_idx = i
                    break
        except (IndexError, OSError):
            start_idx = 0
        self._open_pdf_page_review(
            folder, all_pages, group_name, os.path.basename(pdf_path), initial_index=start_idx
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
        """页图写进 clip_image 之后，问要不要用新图加音频重做这些场景的 clip 视频。"""
        scenes = [s for s in scenes if isinstance(s, dict)]
        if not scenes:
            messagebox.showinfo("PDF", summary, parent=self.root)
            return
        if messagebox.askyesno(
            "重新生成 clip 视频",
            f"{summary}\n\n"
            f"要不要用新的 clip 图片加各场景的 clip 音频，重新生成这 {len(scenes)} 场的 clip 视频？\n"
            "选“是”会替换原来的 clip 视频；没有 clip 音频的场景会跳过。",
            parent=self.root,
        ):
            self._run_still_clip_videos(scenes)

    def _open_pdf_page_review(
        self,
        folder: str,
        pages: list[str],
        group_name: str,
        pdf_name: str,
        initial_index: int = 0,
    ) -> None:
        """翻页查看拆出的 PNG。左右方向键翻页；从当前页写到本集结束。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"PDF 页面 · 第 {group_name} 集")
        dlg.geometry("980x800")
        dlg.minsize(720, 560)
        dlg.transient(self.root)
        idx = [max(0, min(int(initial_index or 0), len(pages) - 1))]
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

        def _forward_hint(page_i: int) -> str:
            """“写到本集结束”按下去会写哪几场，不会超出本集。"""
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
            fresh = self._episode_page_pngs(group_name)
            if fresh:
                pages[:] = fresh
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
            canvas.delete("all")
            canvas.create_image(cw // 2, ch // 2, image=photo)
            page_no = _page_number(i)
            users = _page_users(page_no)
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
            status.config(
                text=(
                    f"本集文件夹共 {len(pages)} 张图，当前第 {i + 1} / {len(pages)} 张"
                    f"（{os.path.basename(path)}）    {_scene_label()}"
                )
            )

        def _step(delta: int):
            fresh = self._episode_page_pngs(group_name)
            if fresh:
                pages[:] = fresh
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
            page_no = _page_number(idx[0])
            try:
                self._assign_scene_clip_image_from_file(scene, pages[idx[0]])
                self._tag_scene_pdf_page(scene, group_name, page_no, pdf_name)
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
            page_i = idx[0]
            written = 0
            first_page = _page_number(page_i)
            last_page_no = first_page
            written_scenes: list = []
            try:
                while scene_i < len(self.workflow.scenes) and page_i < len(pages):
                    scene = self.workflow.scenes[scene_i]
                    if not isinstance(scene, dict) or self.workflow.scene_group(scene) != group_name:
                        break
                    self._assign_scene_clip_image_from_file(scene, pages[page_i])
                    last_page_no = _page_number(page_i)
                    self._tag_scene_pdf_page(scene, group_name, last_page_no, pdf_name)
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
        ttk.Button(bar, text="当前页 → 当前场景", command=_assign_current).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="写到本集结束", command=_assign_forward).pack(side=tk.LEFT)

        def _on_left(_event=None):
            _step(-1)
            return "break"

        def _on_right(_event=None):
            _step(1)
            return "break"

        dlg.bind_all("<Left>", _on_left)
        dlg.bind_all("<Right>", _on_right)

        def _release_keys(_event=None):
            try:
                dlg.unbind_all("<Left>")
                dlg.unbind_all("<Right>")
            except tk.TclError:
                pass

        dlg.bind("<Destroy>", _release_keys)
        canvas.bind("<Configure>", _show_page)
        dlg.after(50, _show_page)
        dlg.after(80, canvas.focus_set)
