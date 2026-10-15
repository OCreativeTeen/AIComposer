"""PlayerMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import time
import pygame
from PIL import Image, ImageTk
import cv2
from utility.file_util import get_file_path
from gui.workflow.wf_common import STANDARD_FPS


class PlayerMixin:
    def _cleanup_video_before_switch(self):
        """切换场景前清理视频资源"""
        # 停止视频播放
        if self.video_playing:
            self.stop_video_playback()
        
        # 清理视频捕获对象
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        
        # 取消定时器
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
        
        # 停止音频
        self.stop_audio_playback()
        
        # 重置播放状态
        self.video_playing = False
        self.video_play_button.config(text="▶")
        
        # 更新视频进度显示
        self.update_video_progress_display()
        
        # 清空画布
        self.video_canvas.delete("all")
        
        # 重置视频相关变量
        self.video_start_time = None
        self.video_pause_time = None
        
        # 清理图片引用，防止内存泄漏
        if hasattr(self, 'current_video_frame'):
            self.current_video_frame = None

    def load_video_first_frame(self):
        self._cleanup_video_before_switch()

        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            
        video_path = get_file_path(current_scene, "clip")
        if not video_path:
            return

        if not video_path:
            self.clear_video_preview()
            return
            
        try:
            self.video_canvas.delete("all")
            
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                cap.release()
                self.clear_video_preview()
                return
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                pil_image = Image.fromarray(frame_rgb)
                
                canvas_width = self.video_canvas.winfo_width()
                canvas_height = self.video_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:  # 确保画布已经初始化
                    pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
                else:
                    pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
                
                # 转换为Tkinter可用的格式
                self.current_video_frame = ImageTk.PhotoImage(pil_image)
                
                # 在画布中央显示图像
                self.video_canvas.delete("all")
                canvas_width = self.video_canvas.winfo_width() or 640
                canvas_height = self.video_canvas.winfo_height() or 360
                x = canvas_width // 2
                y = canvas_height // 2
                
                # 确保图像对象存在后再创建画布图像
                if self.current_video_frame:
                    try:
                        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                    except tk.TclError as e:
                        # 如果图像对象无效，重新创建
                        print(f"⚠️ 图像对象无效，重新创建: {e}")
                        self.current_video_frame = ImageTk.PhotoImage(pil_image)
                        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                
                self.video_canvas.create_text(x, y + pil_image.height//2 + 20, 
                                            text="点击 '▶ 播放' 开始播放视频", 
                                            fill="white", font=("Arial", 12))
            else:
                self.clear_video_preview()
                self.log_to_output(self.video_output, f"❌ 无法读取视频第一帧")
                
        except Exception as e:
            self.clear_video_preview()
            self.log_to_output(self.video_output, f"❌ 加载视频预览失败: {str(e)}")

    def clear_video_preview(self):
        """清空视频预览"""
        # 先清理图片引用，防止内存泄漏
        if hasattr(self, 'current_video_frame'):
            self.current_video_frame = None
        
        # 清空画布
        self.video_canvas.delete("all")
        
        # 显示提示文本
        canvas_width = self.video_canvas.winfo_width() or 640
        canvas_height = self.video_canvas.winfo_height() or 360
        x = canvas_width // 2
        y = canvas_height // 2
        
        self.video_canvas.create_text(x, y, text="选择场景后会显示视频预览", fill="white",
                                    font=("Arial", 12), justify=tk.CENTER, tags="no_video_hint")

    def toggle_video_playback(self):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        video_path = None
        if current_scene:
            video_path = get_file_path(current_scene, "clip")
            
        if not video_path:
            self.log_to_output(self.video_output, "❌ 没有可播放的视频文件")
            return
            
        if self.video_playing:
            self.pause_video()
        else:
            # 如果是从暂停状态恢复，需要特殊处理
            if self.video_cap is not None:
                self.video_playing = True
                self.video_play_button.config(text="⏸")
                # 重新设置开始时间，考虑之前暂停的时间
                self.video_start_time = time.time()
                self._park_preview_audio(self.video_pause_time or 0, paused=False)
                print(f"▶️ 恢复播放，已播放时间: {self.video_pause_time or 0:.2f}秒")
                self.play_next_frame()
            else:
                self.play_video()

    def play_video(self):
        """播放视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        video_path = None
        if current_scene:
            video_path = get_file_path(current_scene, "clip")
            
        if not video_path:
            return

        if self.video_cap is None:
            self.video_cap = cv2.VideoCapture(video_path)
            
        if not self.video_cap.isOpened():
            self.log_to_output(self.video_output, "❌ 无法打开视频文件")
            return
            
        self.video_playing = True
        self.video_play_button.config(text="⏸")
        
        # 记录播放开始时间，重置暂停时间
        self.video_start_time = time.time()
        self.video_pause_time = None  # 重置暂停时间
        
        # 开始播放音频（如果有）
        self.start_audio_playback()
        
        self.play_next_frame()

    def start_audio_playback(self):
        clip = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), "clip_audio")
        if not clip:
            return
        pygame.mixer.music.load(clip)
        pygame.mixer.music.play()

    def pause_audio_playback(self):
        pygame.mixer.music.pause()

    def resume_audio_playback(self):
        pygame.mixer.music.unpause()

    def stop_audio_playback(self):
        pygame.mixer.music.stop()

    def pause_video(self):
        """暂停视频"""
        self.video_playing = False
        self.video_play_button.config(text="▶")
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
        
        # 记录暂停时已播放的时间
        if self.video_start_time:
            elapsed = time.time() - self.video_start_time
            self.video_pause_time = (self.video_pause_time or 0) + elapsed
            
        # 暂停音频
        self.pause_audio_playback()
        print(f"⏸️ 视频暂停，总播放时间: {self.video_pause_time or 0:.2f}秒")

    def _demo_cleanup_playback(self):
        """停止当前视频/音频，不刷新 GUI（全文演示衔接用）"""
        self.video_playing = False
        self.video_play_button.config(text="▶")
        if self.video_after_id:
            try:
                self.root.after_cancel(self.video_after_id)
            except Exception:
                pass
            self.video_after_id = None
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None
        self.stop_audio_playback()
        self.video_start_time = None
        self.video_pause_time = None

    def stop_video_playback(self, cancel_demo=True):
        """停止视频播放"""
        if cancel_demo:
            self._demo_playthrough_active = False
            if getattr(self, "_demo_playthrough_after_id", None):
                try:
                    self.root.after_cancel(self._demo_playthrough_after_id)
                except Exception:
                    pass
                self._demo_playthrough_after_id = None
        self.video_playing = False
        self.video_play_button.config(text="▶")
        
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
            
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
            
        # 停止音频
        self.stop_audio_playback()
            
        # 重置时间相关变量
        self.video_start_time = None
        self.video_pause_time = None
        self._preview_playhead = 0.0
            
        self.refresh_gui_scenes()

    def play_next_frame(self):
        """播放下一帧"""
        if not self.video_playing or not self.video_cap:
            return
        
        # 首先检查音频是否还在播放
        audio_is_playing = pygame.mixer.music.get_busy()
        if not audio_is_playing:
            if getattr(self, "_demo_playthrough_active", False):
                elapsed = 0.0
                if self.video_start_time:
                    elapsed = (time.time() - self.video_start_time) + (self.video_pause_time or 0)
                if elapsed < 0.2:
                    self.video_after_id = self.root.after(50, self.play_next_frame)
                    return
                self.log_to_output(self.video_output, "✅ 音频播放完毕，继续下一场景")
                self._demo_after_clip_finished()
                return
            self.stop_video_playback()
            self.log_to_output(self.video_output, "✅ 音频播放完毕，视频同步停止")
            return
            
        # 计算应该播放的帧位置以保持与音频同步
        
        if self.video_start_time:
            # 计算实际经过的时间
            elapsed_time = time.time() - self.video_start_time
            current_time = elapsed_time + (self.video_pause_time or 0)
            
            # 计算应该在第几帧 (正常1倍速播放)
            target_frame = int(current_time * STANDARD_FPS)
            current_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # 如果视频帧落后于音频进度，跳帧追赶
            if target_frame > current_frame + 2:  # 允许2帧的容错
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        
        ret, frame = self.video_cap.read()
        
        if ret:
            # 转换颜色格式
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整图像大小
            canvas_width = self.video_canvas.winfo_width()
            canvas_height = self.video_canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
            else:
                pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
            
            # 更新画布
            self.current_video_frame = ImageTk.PhotoImage(pil_image)
            self.video_canvas.delete("all")
            
            canvas_width = canvas_width or 640
            canvas_height = canvas_height or 360
            x = canvas_width // 2
            y = canvas_height // 2
            
            # 确保图像对象存在后再创建画布图像
            if self.current_video_frame:
                try:
                    self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                except tk.TclError as e:
                    # 如果图像对象无效，重新创建
                    print(f"⚠️ 图像对象无效，重新创建: {e}")
                    self.current_video_frame = ImageTk.PhotoImage(pil_image)
                    self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
            
            current_time, _total_time = self.get_current_video_time()
            self._preview_playhead = current_time
            self._draw_progress_bar()
            
            # 计算下一帧的延迟时间（毫秒）- 正常1倍播放速度
            delay = int(1000 / STANDARD_FPS)  # 正常播放速度
            self.video_after_id = self.root.after(delay, self.play_next_frame)

        else:
            # 视频文件读取完毕，但仍需等待音频播放完成
            if audio_is_playing:
                # 重新开始视频循环播放以配合音频
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.video_after_id = self.root.after(33, self.play_next_frame)
                print("🔄 视频循环播放以等待音频完成")
            else:
                if getattr(self, "_demo_playthrough_active", False):
                    self.log_to_output(self.video_output, "✅ 视频播放完毕，继续下一场景")
                    self._demo_after_clip_finished()
                    return
                self.stop_video_playback()
                self.log_to_output(self.video_output, "✅ 视频播放完毕")

    def cleanup_track_video_captures(self):
        if hasattr(self, 'secondary_track_cap') and self.secondary_track_cap:
            try:
                self.secondary_track_cap.release()
            except:
                pass
            self.secondary_track_cap = None
        
        # 重置旁白轨道的播放状态
        if hasattr(self, 'secondary_track_playing'):
            self.secondary_track_playing = False
        if hasattr(self, 'secondary_track_after_id') and self.secondary_track_after_id:
            try:
                self.root.after_cancel(self.secondary_track_after_id)
            except:
                pass
            self.secondary_track_after_id = None
        
        # 清理 PIP 左右轨道
        if hasattr(self, 'pip_left_cap') and self.pip_left_cap:
            try:
                self.pip_left_cap.release()
            except:
                pass
            self.pip_left_cap = None
            
        if hasattr(self, 'pip_right_cap') and self.pip_right_cap:
            try:
                self.pip_right_cap.release()
            except:
                pass
            self.pip_right_cap = None
        
        # 重置 PIP 的播放状态
        if hasattr(self, 'pip_lr_playing'):
            self.pip_lr_playing = False
        if hasattr(self, 'pip_lr_after_id') and self.pip_lr_after_id:
            try:
                self.root.after_cancel(self.pip_lr_after_id)
            except:
                pass
            self.pip_lr_after_id = None

    def get_current_video_time(self):
        """Get current video playback time in sec"""
        if self.video_cap is None:
            return 0.0, 0.0
        current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
        current_time = current_frame / STANDARD_FPS

        total_time = self.workflow.find_clip_duration(self.workflow.get_scene_by_index(self.current_scene_index))
        
        if current_time > total_time:
            current_time = total_time

        return current_time, total_time

    def start_demo_playthrough(self):
        """从第一场景起依次导航并播放主轨 clip，串成整条故事预览。"""
        if not self.workflow or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有场景", parent=self.root)
            return
        if self._demo_playthrough_active:
            messagebox.showinfo("提示", "全文演示已在进行中", parent=self.root)
            return
        if self.video_playing:
            self.stop_video_playback(cancel_demo=False)
        if hasattr(self, "_save_timer") and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self._demo_playthrough_active = True
        if self._demo_playthrough_after_id:
            try:
                self.root.after_cancel(self._demo_playthrough_after_id)
            except Exception:
                pass
            self._demo_playthrough_after_id = None
        self.update_current_scene()
        self.current_scene_index = 0
        self.refresh_gui_scenes()
        self.log_to_output(self.video_output, "▶ 全文演示：从场景 1 开始")
        self.root.after(400, self._demo_start_play_scene)

    def _demo_video_duration_sec(self, path: str) -> float:
        cap = cv2.VideoCapture(path)
        try:
            if not cap.isOpened():
                return 3.0
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps <= 0:
                return 3.0
            return max(0.5, float(n) / float(fps))
        finally:
            cap.release()

    def _demo_start_play_scene(self):
        if not self._demo_playthrough_active:
            return
        if not self.workflow or not self.workflow.scenes:
            self._demo_playthrough_active = False
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip = get_file_path(scene, "clip") if scene else None
        clip_audio = get_file_path(scene, "clip_audio") if scene else None
        if not clip:
            self.log_to_output(self.video_output, f"场景 {self.current_scene_index + 1} 无 clip，跳过")
            self._demo_after_clip_finished()
            return
        if not clip_audio:
            d = self._demo_video_duration_sec(clip)
            self.log_to_output(
                self.video_output,
                f"场景 {self.current_scene_index + 1} 无 clip_audio，按视频时长 {d:.1f}s 后切下一场景",
            )
            self.load_all_images_preview()
            ms = max(100, int(d * 1000) + 200)
            self._demo_playthrough_after_id = self.root.after(ms, self._demo_after_clip_finished)
            return
        self.play_video()

    def _demo_after_clip_finished(self):
        if not self._demo_playthrough_active:
            return
        self._demo_playthrough_after_id = None
        self._demo_cleanup_playback()
        n = len(self.workflow.scenes)
        if n == 0:
            self._demo_playthrough_active = False
            return
        next_i = self.current_scene_index + 1
        if next_i >= n:
            self._demo_playthrough_active = False
            self.log_to_output(self.video_output, "✅ 全文演示结束（已播完所有场景）")
            self.refresh_gui_scenes()
            return
        self.current_scene_index = next_i
        self.refresh_gui_scenes()
        self.root.after(300, self._demo_start_play_scene)
