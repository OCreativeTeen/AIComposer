import tkinter as tk
from tkinter import ttk, messagebox
import os
import subprocess
import tempfile
import threading
import time
from PIL import Image, ImageTk

import cv2
CV2_AVAILABLE = True

# Audio playback imports
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("警告: pygame 不可用，音频播放功能将被禁用")


class VideoReviewDialog:
    """Dialog for reviewing and configuring video replacement"""
    
    def __init__(self, parent, source_video_path, current_scene_duration, 
                       initial_start_time, initial_end_time, scenes_length):
        self.parent = parent
        self.source_video_path = source_video_path
        self.current_scene_duration = current_scene_duration
        self.result = None  # Will store the result when dialog is closed
        self.scenes_length = scenes_length
        
        self.video_duration = parent.workflow.ffmpeg_processor.get_duration(source_video_path)
        self.source_has_audio = parent.workflow.ffmpeg_processor.has_audio_stream(source_video_path)
        
        # Set initial times - use provided values or defaults
        if initial_start_time is not None and initial_end_time is not None:
            self.start_time = max(0.0, initial_start_time)
            self.end_time = min(self.video_duration, initial_end_time)
        else:
            self.start_time = 0.0
            self.end_time = self.video_duration
            
        self.track_mode = 2  # Default to mode 2
        
        self.create_dialog()
        
    def create_dialog(self):
        """Create the review dialog window"""
        self.dialog = tk.Toplevel(self.parent.root)
        self.dialog.title("视频替换预览")
        self.dialog.geometry("800x850")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent.root)
        self.dialog.grab_set()
        
        # Main container
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Video info section
        info_frame = ttk.LabelFrame(main_frame, text="视频信息", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Video info row 1: 源视频 + 音频状态
        info_row1 = ttk.Frame(info_frame)
        info_row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(info_row1, text=f"源视频时长: {self.video_duration:.2f}秒").pack(side=tk.LEFT)

        ttk.Separator(info_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        ttk.Label(info_row1, text=f"目标时长: {self.current_scene_duration:.2f}秒").pack(side=tk.LEFT)

        ttk.Separator(info_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        audio_status = "有音频" if self.source_has_audio else "无音频"
        audio_color = "green" if self.source_has_audio else "red"
        audio_label = ttk.Label(info_row1, text=f"音频状态: {audio_status}", foreground=audio_color)
        audio_label.pack(side=tk.LEFT)

        ttk.Separator(info_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)

        ttk.Label(info_row1, text=f"源视频: {os.path.basename(self.source_video_path)}").pack(side=tk.LEFT)

        # Video preview section (placeholder for now)
        preview_frame = ttk.LabelFrame(main_frame, text="REPLACE视频预览", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Simple video preview using canvas
        self.preview_canvas = tk.Canvas(preview_frame, bg='black', height=300)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Video controls
        control_frame = ttk.Frame(preview_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.play_button = ttk.Button(control_frame, text="▶ 播放", command=self.toggle_playback)
        self.play_button.pack(side=tk.LEFT, padx=15)
        
        self.stop_button = ttk.Button(control_frame, text="⏹ 停止", command=self.stop_playback)
        self.stop_button.pack(side=tk.LEFT, padx=15)

        ttk.Button(control_frame, text="跳转到开始", command=self.jump_to_start).pack(side=tk.LEFT, padx=15)
        ttk.Button(control_frame, text="播放选定范围", command=self.play_selected_range).pack(side=tk.LEFT, padx=15)

        # behind "播放选定范围", add label to show  'play time / video duration'
        self.play_time_label = ttk.Label(control_frame, text="0.00 / 0.00", foreground="blue")
        self.play_time_label.pack(side=tk.LEFT, padx=15)
     
        # Time selection section
        time_frame = ttk.LabelFrame(main_frame, text="时间段选择", padding=10)
        time_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Time selection row: 开始时间 + 结束时间
        time_row = ttk.Frame(time_frame)
        time_row.pack(fill=tk.X, pady=2)
        
        ttk.Label(time_row, text="开始时间 (秒):").pack(side=tk.LEFT, padx=(0, 5))
        self.start_time_var = tk.DoubleVar(value=self.start_time)
        start_spinbox = ttk.Spinbox(time_row, from_=0, to=self.video_duration, 
                                   textvariable=self.start_time_var, increment=0.1, width=8)
        start_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(time_row, text="设为当前", command=self.set_start_to_current).pack(side=tk.LEFT, padx=(0, 10))
        
        # 分隔符
        ttk.Separator(time_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # 结束时间组
        ttk.Label(time_row, text="结束时间 (秒):").pack(side=tk.LEFT, padx=(5, 5))
        self.end_time_var = tk.DoubleVar(value=self.end_time)
        end_spinbox = ttk.Spinbox(time_row, from_=0, to=self.video_duration, 
                                 textvariable=self.end_time_var, increment=0.1, width=8)
        end_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(time_row, text="设为当前", command=self.set_end_to_current).pack(side=tk.LEFT)
        
        # 分隔符
        ttk.Separator(time_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # 时长显示组
        ttk.Label(time_row, text="选择的时长:").pack(side=tk.LEFT, padx=(5, 5))
        self.selected_duration_label = ttk.Label(time_row, text="", foreground="blue")
        self.selected_duration_label.pack(side=tk.LEFT)
        
        # Initialize play time display with video duration
        self.update_play_time_display()
        
        # Bind changes to update duration display
        self.start_time_var.trace('w', self.update_duration_display)
        self.end_time_var.trace('w', self.update_duration_display)
        self.update_duration_display()
        
        # Mode selection section
        mode_frame = ttk.LabelFrame(main_frame, text="处理模式", padding=10)
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create a horizontal container for all three sections
        sections_container = ttk.Frame(main_frame)
        sections_container.pack(fill=tk.X, pady=(0, 10))

        self.mode_var = tk.IntVar(value=self.track_mode)
                
        # Mode selection frame
        mode_frame = ttk.LabelFrame(sections_container, text="轨道模式选择", padding=10)
        mode_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        mode_row1 = ttk.Frame(mode_frame)
        mode_row1.pack(fill=tk.X, pady=10)

        ttk.Radiobutton(mode_row1, text="速度匹配", variable=self.mode_var, value=1).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_row1, text="剪切匹配", variable=self.mode_var, value=2).pack(side=tk.LEFT, padx=10)

        self.second_track_radio = ttk.Radiobutton(mode_row1, text="第二轨道", variable=self.mode_var, value=3)
        self.second_track_radio.pack(side=tk.LEFT, padx=10)

        # 如果主轨道被锁定，禁用主轨道选项
        if self.scenes_length==0:
            self.second_track_radio.config(state=tk.DISABLED)

        # Audio transcription frame
        transcribe_frame = ttk.LabelFrame(sections_container, text="音频转录选择", padding=10)
        transcribe_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Transcription mode selection
        transcribe_label = ttk.Label(transcribe_frame, text="转录模式:")
        transcribe_label.pack(pady=(0, 5))
        
        self.transcribe_audio_var = tk.StringVar(value="NONE")
        transcribe_options = ["NONE", "Single-scene", "Multiple-scenes"]
        transcribe_combobox = ttk.Combobox(
            transcribe_frame,
            textvariable=self.transcribe_audio_var,
            values=transcribe_options,
            state="readonly"
        )
        transcribe_combobox.pack(pady=5, fill=tk.X, padx=10)

        # Add note about transcription
        transcribe_note = ttk.Label(
            transcribe_frame, 
            text="NONE: 不转录\nSingle-scene: 单个场景\nMultiple-scenes: 多个场景",
            foreground="gray",
            font=("TkDefaultFont", 8)
        )
        transcribe_note.pack(pady=(5, 5))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="确认替换", command=self.confirm_replacement).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT)
        
        # Initialize video playback state
        self.video_playing = False
        self.video_cap = None
        self.video_after_id = None
        self.current_playback_time = 0.0
        
        # Initialize audio playback state
        self.audio_playing = False
        self.audio_file_path = None
        self.audio_start_time = 0.0
        self.audio_thread = None
        self.pygame_initialized = False
        self._audio_is_paused = False  # Track if audio is currently paused
        
        # Initialize pygame mixer if available
        if self.source_has_audio:
            self.init_pygame_mixer()
            self.extract_audio_for_playback()
        
    def update_duration_display(self, *args):
        """Update the selected duration display"""
        try:
            start = self.start_time_var.get()
            end = self.end_time_var.get()
            if end > start:
                duration = end - start
                self.selected_duration_label.config(text=f"{duration:.2f}秒")
            else:
                self.selected_duration_label.config(text="无效时间段")
        except:
            self.selected_duration_label.config(text="--")
    
    def update_play_time_display(self):
        """Update the play time display (current time / total duration)"""
        try:
            current_time = self.current_playback_time
            total_duration = self.video_duration
            
            # Format time display
            current_str = f"{current_time:.2f}"
            total_str = f"{total_duration:.2f}"
            
            # Update the label
            self.play_time_label.config(text=f"{current_str} / {total_str}")
            
        except Exception as e:
            # Fallback display
            self.play_time_label.config(text="0.00 / 0.00")
    
    def set_start_to_current(self):
        """Set start time to current playback position"""
        self.start_time_var.set(self.current_playback_time)
        # Update audio playback range if needed
        self.update_audio_playback_range()
        # Update play time display
        self.update_play_time_display()
    
    def set_end_to_current(self):
        """Set end time to current playback position"""
        self.end_time_var.set(self.current_playback_time)
        # Update audio playback range if needed
        self.update_audio_playback_range()
        # Update play time display
        self.update_play_time_display()
    
    def toggle_playback(self):
        """Toggle video and audio playback"""
        if not self.video_playing:
            self.start_playback()
        else:
            self.pause_playback()
    
    def start_playback(self):
        """Start video and audio playback"""
        try:
            if self.video_cap is None:
                self.video_cap = cv2.VideoCapture(self.source_video_path)
            
            self.video_playing = True
            self.play_button.config(text="⏸ 暂停")
            
            # Start audio playback if available and in selected range
            if self.source_has_audio and self.pygame_initialized and self.audio_file_path:
                if self.is_in_selected_time_range(self.current_playback_time):
                    # Check if audio was paused, then resume; otherwise start fresh
                    if self._audio_is_paused:
                        self.resume_audio_playback()
                    elif not self.audio_playing:
                        self.start_audio_playback()
                else:
                    print(f"⚠️ 当前位置不在选定范围内，不播放音频")
            
            self.update_video_frame()
        except Exception as e:
            messagebox.showerror("错误", f"无法播放视频: {str(e)}")
    
    def pause_playback(self):
        """Pause video and audio playback"""
        self.video_playing = False
        self.play_button.config(text="▶ 播放")
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
        
        # Pause audio
        if self.audio_playing and self.pygame_initialized:
            self.pause_audio_playback()
    
    def stop_playback(self):
        """Stop video and audio playback"""
        self.video_playing = False
        self.play_button.config(text="▶ 播放")
        self.current_playback_time = 0.0
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
        if self.video_cap:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        # Stop audio and reset state
        if self.pygame_initialized:
            self.stop_audio_playback()
        
        # Jump to start of selected range
        self.jump_to_start()
        
        # Update play time display
        self.update_play_time_display()
    
    def update_video_frame(self):
        """Update video frame in preview"""
        if not self.video_playing or not self.video_cap:
            return
        
        try:
            ret, frame = self.video_cap.read()
            if ret:
                # Get current time
                fps = self.video_cap.get(cv2.CAP_PROP_FPS)
                current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                self.current_playback_time = current_frame / fps if fps > 0 else 0
                
                # Update play time display
                self.update_play_time_display()
                
                # Check if we're still in the selected time range
                if not self.is_in_selected_time_range(self.current_playback_time):
                    try:
                        end_time = self.end_time_var.get()
                        if self.current_playback_time >= end_time:
                            # Reached end of selected range
                            self.stop_playback()
                            return
                    except:
                        pass
                
                # Convert frame to display in canvas
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width = frame.shape[:2]
                
                # Resize frame to fit canvas
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                if canvas_width > 1 and canvas_height > 1:
                    aspect_ratio = width / height
                    if canvas_width / canvas_height > aspect_ratio:
                        new_height = canvas_height
                        new_width = int(canvas_height * aspect_ratio)
                    else:
                        new_width = canvas_width
                        new_height = int(canvas_width / aspect_ratio)
                    
                    frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to PhotoImage and display
                    image = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image)
                    
                    self.preview_canvas.delete("all")
                    self.preview_canvas.create_image(canvas_width//2, canvas_height//2, 
                                                   image=photo, anchor=tk.CENTER)
                    self.preview_canvas.image = photo  # Keep a reference
                
                # Check audio status (no sync restart)
                if self.source_has_audio and self.audio_playing:
                    self.sync_audio_to_video()
                
                # Schedule next frame
                if fps > 0:
                    delay = int(1000 / fps)
                else:
                    delay = 33  # ~30 FPS fallback
                self.video_after_id = self.dialog.after(delay, self.update_video_frame)
            else:
                # End of video or end of selected range
                self.stop_playback()
        except Exception as e:
            print(f"Video playback error: {e}")
            self.stop_playback()
    
    def confirm_replacement(self):
        """Confirm the video replacement with selected parameters"""
        try:
            start_time = self.start_time_var.get()
            end_time = self.end_time_var.get()
            
            if end_time <= start_time:
                messagebox.showerror("错误", "结束时间必须大于开始时间")
                return
            
            if start_time < 0 or end_time > self.video_duration:
                messagebox.showerror("错误", "时间选择超出视频范围")
                return
            
            self.result = {
                'confirmed': True,
                'start_time': start_time,
                'end_time': end_time,
                'track_mode': self.mode_var.get(),
                'transcribe_audio': self.transcribe_audio_var.get()
            }
            
            self.close_dialog()
            
        except Exception as e:
            messagebox.showerror("错误", f"参数验证失败: {str(e)}")
    
    def cancel(self):
        """Cancel the operation"""
        self.result = {'confirmed': False}
        self.close_dialog()
    
    def close_dialog(self):
        """Close the dialog and cleanup"""
        # Stop video playback
        self.video_playing = False
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
        if self.video_cap:
            self.video_cap.release()
        
        # Stop audio immediately and reset all states
        self.audio_playing = False
        self._audio_is_paused = False
        if self.pygame_initialized and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
                print(f"✓ 音频播放已停止")
            except:
                pass
        
        # Cleanup audio resources
        self.cleanup_audio()
        
        # Close dialog
        self.dialog.destroy()
    
    def init_pygame_mixer(self):
        """Initialize pygame mixer for audio playback"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            self.pygame_initialized = True
            print("✓ Pygame mixer 初始化成功")
        except Exception as e:
            print(f"⚠️ Pygame mixer 初始化失败: {e}")
            self.pygame_initialized = False
    
    def extract_audio_for_playback(self):
        """Extract audio from source video for playback"""
        if not self.source_has_audio or not self.pygame_initialized:
            return
        
        try:
            # Create temporary audio file
            temp_dir = tempfile.gettempdir()
            self.audio_file_path = os.path.join(temp_dir, f"video_preview_audio_{os.getpid()}.wav")
            
            # Extract audio using ffmpeg
            cmd = [
                "ffmpeg", "-y", "-i", self.source_video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                self.audio_file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(self.audio_file_path):
                print(f"✓ 音频提取成功: {self.audio_file_path}")
            else:
                print(f"⚠️ 音频提取失败: {result.stderr}")
                self.audio_file_path = None
                
        except Exception as e:
            print(f"⚠️ 音频提取异常: {e}")
            self.audio_file_path = None
    
    def cleanup_audio(self):
        """Cleanup audio resources"""
        try:
            # Stop audio playback
            if self.pygame_initialized and pygame.mixer.get_init():
                pygame.mixer.music.stop()
            
            # Remove temporary audio file
            if self.audio_file_path and os.path.exists(self.audio_file_path):
                os.remove(self.audio_file_path)
                print(f"✓ 临时音频文件已删除: {self.audio_file_path}")
                
        except Exception as e:
            print(f"⚠️ 音频清理异常: {e}")
    
    def start_audio_playback(self):
        """Start audio playback synchronized with video"""
        if not self.audio_file_path or not os.path.exists(self.audio_file_path):
            return
        
        # Prevent multiple simultaneous audio starts
        if self.audio_playing:
            return
        
        try:
            # Stop any existing audio first
            pygame.mixer.music.stop()
            
            # Load and play audio from current position
            pygame.mixer.music.load(self.audio_file_path)
            
            # Calculate position in the audio file based on current video time
            start_pos = self.current_playback_time
            
            pygame.mixer.music.play()
            self.audio_playing = True
            self.audio_start_time = time.time() - start_pos  # Adjust for current position
            
            print(f"✓ 音频播放开始，从 {start_pos:.2f}秒开始")
            
        except Exception as e:
            print(f"⚠️ 音频播放失败: {e}")
            self.audio_playing = False
    
    def pause_audio_playback(self):
        """Pause audio playback"""
        try:
            if self.audio_playing and self.pygame_initialized:
                pygame.mixer.music.pause()
                # Don't set audio_playing to False, just mark as paused
                self._audio_is_paused = True
                print(f"⏸ 音频播放暂停")
        except Exception as e:
            print(f"⚠️ 音频暂停失败: {e}")
    
    def resume_audio_playback(self):
        """Resume audio playback"""
        try:
            if self._audio_is_paused and self.pygame_initialized:
                pygame.mixer.music.unpause()
                self._audio_is_paused = False
                print(f"▶ 音频播放恢复")
        except Exception as e:
            print(f"⚠️ 音频恢复失败: {e}")
    
    def stop_audio_playback(self):
        """Stop audio playback"""
        try:
            if self.pygame_initialized:
                pygame.mixer.music.stop()
                self.audio_playing = False
                self.audio_start_time = 0.0
                self._audio_is_paused = False
                print(f"⏹ 音频播放停止")
        except Exception as e:
            print(f"⚠️ 音频停止失败: {e}")
    
    def sync_audio_to_video(self):
        """Check audio playback status (no longer restarts audio)"""
        if not self.audio_playing or not self.pygame_initialized:
            return
        
        try:
            # Only check if audio is still playing, don't restart
            if not pygame.mixer.music.get_busy():
                self.audio_playing = False
                print(f"ℹ️ 音频播放已结束")
                return
            
            # Optional: Log sync status occasionally without restarting
            current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES) if self.video_cap else 0
            if int(current_frame) % 90 == 0 and self.audio_start_time > 0:  # Every 3 seconds
                audio_position = time.time() - self.audio_start_time
                video_position = self.current_playback_time
                time_diff = abs(audio_position - video_position)
                if time_diff > 1.0:
                    print(f"ℹ️ 音视频偏差: {time_diff:.2f}s (不重启)")
                    
        except Exception as e:
            print(f"⚠️ 音频状态检查异常: {e}")
    
    def update_audio_playback_range(self):
        """Update audio playback range based on time selection"""
        if not self.source_has_audio or not self.pygame_initialized:
            return
        
        try:
            start_time = self.start_time_var.get()
            end_time = self.end_time_var.get()
            
            # If playing and current time is outside selected range, stop
            if self.audio_playing or self._audio_is_paused:
                if self.current_playback_time < start_time or self.current_playback_time > end_time:
                    self.stop_audio_playback()
                    print(f"⚠️ 播放位置超出选定范围，停止音频")
            
        except Exception as e:
            print(f"⚠️ 更新音频播放范围异常: {e}")
    
    def is_in_selected_time_range(self, current_time):
        """Check if current time is within selected range"""
        try:
            start_time = self.start_time_var.get()
            end_time = self.end_time_var.get()
            return start_time <= current_time <= end_time
        except:
            return True  # Default to allowing playback if values can't be read
    
    def jump_to_start(self):
        """Jump to the start of selected time range"""
        try:
            start_time = self.start_time_var.get()
            if self.video_cap:
                fps = self.video_cap.get(cv2.CAP_PROP_FPS)
                start_frame = int(start_time * fps) if fps > 0 else 0
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                self.current_playback_time = start_time
                
                # Stop current audio and reset state
                if self.audio_playing or self._audio_is_paused:
                    self.stop_audio_playback()
                
                print(f"✓ 跳转到开始位置: {start_time:.2f}秒")
                
                # Update play time display
                self.update_play_time_display()
                
        except Exception as e:
            print(f"⚠️ 跳转失败: {e}")
    
    def play_selected_range(self):
        """Play only the selected time range"""
        try:
            # Jump to start first
            self.jump_to_start()
            
            # Start playback
            if not self.video_playing:
                self.start_playback()
            
            print(f"▶ 开始播放选定范围")
            
        except Exception as e:
            print(f"⚠️ 播放选定范围失败: {e}")
