import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
from PIL import Image, ImageTk
from utility.file_util import get_file_path
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor
import config

# 尝试导入拖放支持
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    print("警告: tkinterdnd2 不可用，拖放功能将被禁用")

# Video playback imports
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Audio playback imports
try:
    import pygame
    PYGAME_AVAILABLE = True
    pygame.mixer.init()
except ImportError:
    PYGAME_AVAILABLE = False


class MediaTypeSelector:
    """对话框：选择要编辑的媒体类型和音频处理选项"""
    
    def __init__(self, parent, av_path=None, current_scene=None):
        self.result = None
        self.replace_audio = "trim"
        self.av_path = av_path
        self.current_scene = current_scene
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("选择媒体类型")
        self.dialog.geometry("450x520")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 标题
        ttk.Label(self.dialog, text="请选择要编辑的媒体类型:", 
                 font=('Arial', 10, 'bold')).pack(pady=20)
        
        # 选项框架
        options_frame = ttk.Frame(self.dialog)
        options_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 三个选项
        ttk.Button(options_frame, text="场景媒体 (clip_video/audio/image)", 
                  command=lambda: self.select("clip")).pack(fill=tk.X, pady=5)

        ttk.Button(options_frame, text="第一轨道 (one/one_audio/one_image)", 
                  command=lambda: self.select("one")).pack(fill=tk.X, pady=5)

        ttk.Button(options_frame, text="第二轨道 (second/second_audio/second_image)", 
                  command=lambda: self.select("second")).pack(fill=tk.X, pady=5)
        
        ttk.Button(options_frame, text="背景轨道 (zero/zero_audio/zero_image)", 
                  command=lambda: self.select("zero")).pack(fill=tk.X, pady=5)

        # 音频处理选项（仅当视频有音频时显示）
        if self._check_video_has_audio():
            separator = ttk.Separator(options_frame, orient='horizontal')
            separator.pack(fill=tk.X, pady=15)
            
            audio_frame = ttk.LabelFrame(options_frame, text="音频处理选项", padding=10)
            audio_frame.pack(fill=tk.X, pady=10)
            
            self.audio_option_var = tk.StringVar(value="replace")

            ttk.Radiobutton(audio_frame, 
                          text="用场景现有音频替换视频音频", 
                          variable=self.audio_option_var, 
                          value="replace").pack(anchor=tk.W, pady=5)

            ttk.Radiobutton(audio_frame, 
                          text="保留视频自带音频并剪到现有长度", 
                          variable=self.audio_option_var, 
                          value="trim").pack(anchor=tk.W, pady=5)

            ttk.Radiobutton(audio_frame, 
                          text="保留视频自带的音频", 
                          variable=self.audio_option_var, 
                          value="keep").pack(anchor=tk.W, pady=5)

            # 说明文字
            info_label = ttk.Label(audio_frame, 
                                  text="💡 替换选项：将使用场景中对应的音频文件\n(clip_audio/second_audio/zero_audio)", 
                                  foreground="gray", 
                                  font=('Arial', 8))
            info_label.pack(anchor=tk.W, pady=(5, 0))
        else:
            self.audio_option_var = tk.StringVar(value="keep")
        
        # 取消按钮
        ttk.Button(options_frame, text="取消", 
                  command=self.cancel).pack(fill=tk.X, pady=20)
    
    def _check_video_has_audio(self):
        """检查视频是否包含音频流"""
        if not self.av_path or not os.path.exists(self.av_path):
            return False
        
        # 检查是否为视频文件
        if not self.av_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
            return False
        
        try:
            # 使用 ffmpeg 检查音频流
            from utility.ffmpeg_processor import FfmpegProcessor
            # 创建临时处理器检查音频
            temp_processor = FfmpegProcessor("temp", "zh")
            has_audio = temp_processor.has_audio_stream(self.av_path)
            return has_audio
        except:
            return False
    
    def select(self, media_type):
        self.result = media_type
        # 检查用户是否选择了替换音频
        self.replace_audio = self.audio_option_var.get()
        self.dialog.destroy()
    
    def cancel(self):
        self.result = None
        self.replace_audio = "trim"
        self.dialog.destroy()
    
    def show(self):
        self.dialog.wait_window()
        return self.replace_audio, self.result


class EnhancedMediaEditor:
    """增强的媒体编辑器，支持视频/音频/图片的拖放编辑"""
    
    def __init__(self, parent, scene, media_type="clip"):
        self.parent = parent
        self.scene = scene
        self.media_type = media_type  # "clip", "second", "zero"
        self.workflow = parent.workflow
        
        video_width = self.workflow.ffmpeg_processor.width
        video_height = self.workflow.ffmpeg_processor.height
        
        # 媒体字段名映射
        if media_type == "clip":
            self.video_field = "clip_video"
            self.audio_field = "clip_audio"
            self.image_field = "clip_image"
        elif media_type == "second":
            self.video_field = "second"
            self.audio_field = "second_audio"
            self.image_field = "second_image"
        elif media_type == "zero":
            self.video_field = "zero"
            self.audio_field = "zero_audio"
            self.image_field = "zero_image"
        
        # 当前媒体路径
        self.current_video = get_file_path(scene, self.video_field)
        self.current_audio = get_file_path(scene, self.audio_field)
        self.current_image = get_file_path(scene, self.image_field)
        
        # 新媒体路径（拖放后的）
        self.new_video = None
        self.new_audio = None
        self.new_image = None
        
        
        # 播放状态
        self.video_playing = False
        self.audio_playing = False
        self.video_cap = None
        self.video_after_id = None
        
        self.result = None
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框UI"""
        self.dialog = tk.Toplevel(self.parent.root if hasattr(self.parent, 'root') else self.parent)
        self.dialog.title(f"媒体编辑器 - {self.media_type}")
        self.dialog.geometry("1400x800")
        
        # 主容器
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 标题
        title = f"编辑 {self.media_type} 媒体 (拖放文件到对应区域)"
        ttk.Label(main_frame, text=title, font=('Arial', 12, 'bold')).pack(pady=10)
        
        # 三栏布局
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左栏：视频
        self.create_video_column(content_frame)
        
        # 中栏：图片
        self.create_image_column(content_frame)
        
        # 右栏：音频
        self.create_audio_column(content_frame)
        
        # 底部按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="确定", command=self.confirm).pack(side=tk.RIGHT, padx=5)
        
        # 加载默认媒体
        self.load_default_media()
    
    def create_video_column(self, parent):
        """创建视频栏"""
        video_frame = ttk.LabelFrame(parent, text="视频区域", padding=10)
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 视频显示区
        self.video_canvas = tk.Canvas(video_frame, width=400, height=400, bg='black')
        self.video_canvas.pack(fill=tk.BOTH, expand=True)
        
        if DND_AVAILABLE:
            self.video_canvas.drop_target_register(DND_FILES)
            self.video_canvas.dnd_bind('<<Drop>>', self.on_video_drop)
        
        # 视频控制
        video_control = ttk.Frame(video_frame)
        video_control.pack(fill=tk.X, pady=5)
        
        self.video_play_btn = ttk.Button(video_control, text="播放", command=self.toggle_video_playback)
        self.video_play_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(video_control, text="清除", command=self.clear_video).pack(side=tk.LEFT, padx=2)
        
        self.video_info_label = ttk.Label(video_frame, text="无视频")
        self.video_info_label.pack()
    
    def create_image_column(self, parent):
        """创建图片栏"""
        image_frame = ttk.LabelFrame(parent, text="图片区域", padding=10)
        image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 图片显示区
        self.image_canvas = tk.Canvas(image_frame, width=400, height=400, bg='gray')
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        
        if DND_AVAILABLE:
            self.image_canvas.drop_target_register(DND_FILES)
            self.image_canvas.dnd_bind('<<Drop>>', self.on_image_drop)
        
        # 动画选择
        anim_frame = ttk.Frame(image_frame)
        anim_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(anim_frame, text="动画效果:").pack(side=tk.LEFT, padx=5)
        
        self.animation_var = tk.IntVar(value=1)
        animations = [(1, "静止"), (2, "向左"), (3, "向右"), (4, "动画")]
        
        for value, text in animations:
            ttk.Radiobutton(anim_frame, text=text, variable=self.animation_var, 
                           value=value).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(image_frame, text="清除", command=self.clear_image).pack(pady=2)
        
        self.image_info_label = ttk.Label(image_frame, text="无图片")
        self.image_info_label.pack()
    
    def create_audio_column(self, parent):
        """创建音频栏"""
        audio_frame = ttk.LabelFrame(parent, text="音频区域", padding=10)
        audio_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 音频显示区（波形可视化占位符）
        self.audio_canvas = tk.Canvas(audio_frame, width=400, height=400, bg='lightblue')
        self.audio_canvas.pack(fill=tk.BOTH, expand=True)
        
        if DND_AVAILABLE:
            self.audio_canvas.drop_target_register(DND_FILES)
            self.audio_canvas.dnd_bind('<<Drop>>', self.on_audio_drop)
        
        # 音频控制
        audio_control = ttk.Frame(audio_frame)
        audio_control.pack(fill=tk.X, pady=5)
        
        self.audio_play_btn = ttk.Button(audio_control, text="播放", command=self.toggle_audio_playback)
        self.audio_play_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(audio_control, text="清除", command=self.clear_audio).pack(side=tk.LEFT, padx=2)
        
        self.audio_info_label = ttk.Label(audio_frame, text="无音频")
        self.audio_info_label.pack()
    
    def load_default_media(self):
        """加载默认媒体"""
        # 加载视频
        if self.current_video and os.path.exists(self.current_video):
            self.display_video(self.current_video)
        
        # 加载图片
        if self.current_image and os.path.exists(self.current_image):
            self.display_image(self.current_image)
        else:
            # 使用默认图片
            default_image = os.path.join(config.get_background_image_path(), "default.png")
            if os.path.exists(default_image):
                self.current_image = default_image
                self.display_image(default_image)
        
        # 加载音频
        if self.current_audio and os.path.exists(self.current_audio):
            self.display_audio(self.current_audio)
        else:
            # 使用默认音频
            default_audio = os.path.join(config.get_background_music_path(), "default.mp3")
            if os.path.exists(default_audio):
                self.current_audio = default_audio
                self.display_audio(default_audio)
    
    def on_video_drop(self, event):
        """处理视频拖放"""
        file_path = event.data.strip('{}')
        if os.path.isfile(file_path):
            # 检查是否是视频文件
            if file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                self.new_video = file_path
                self.display_video(file_path)
                
                # 如果视频有音频，提取音频
                if self.workflow.ffmpeg_processor.has_audio_stream(file_path):
                    audio_path = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(file_path)
                    self.new_audio = audio_path
                    self.display_audio(audio_path)
                    messagebox.showinfo("提示", "已从视频中提取音频")
            else:
                messagebox.showwarning("警告", "请拖放视频文件")
    
    def on_image_drop(self, event):
        """处理图片拖放"""
        file_path = event.data.strip('{}')
        if os.path.isfile(file_path):
            # 检查是否是图片文件
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')):
                self.new_image = file_path
                self.display_image(file_path)
            else:
                messagebox.showwarning("警告", "请拖放图片文件")
    
    def on_audio_drop(self, event):
        """处理音频拖放"""
        file_path = event.data.strip('{}')
        if os.path.isfile(file_path):
            # 检查是否是音频文件
            if file_path.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg')):
                self.new_audio = file_path
                self.display_audio(file_path)
            else:
                messagebox.showwarning("警告", "请拖放音频文件")
    
    def display_video(self, video_path):
        """显示视频"""
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(video_path)
                ret, frame = cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                    img.thumbnail((400, 400))
                    photo = ImageTk.PhotoImage(img)
                    
                    self.video_canvas.delete("all")
                    self.video_canvas.create_image(200, 200, image=photo)
                    self.video_canvas.image = photo
                    
                    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
                    self.video_info_label.config(text=f"视频: {os.path.basename(video_path)} ({duration:.1f}s)")
                cap.release()
            except Exception as e:
                self.video_info_label.config(text=f"视频加载失败: {str(e)}")
        else:
            self.video_info_label.config(text=f"视频: {os.path.basename(video_path)}")
    
    def display_image(self, image_path):
        """显示图片"""
        try:
            img = Image.open(image_path)
            img.thumbnail((400, 400))
            photo = ImageTk.PhotoImage(img)
            
            self.image_canvas.delete("all")
            self.image_canvas.create_image(200, 200, image=photo)
            self.image_canvas.image = photo
            
            self.image_info_label.config(text=f"图片: {os.path.basename(image_path)}")
        except Exception as e:
            self.image_info_label.config(text=f"图片加载失败: {str(e)}")
    
    def display_audio(self, audio_path):
        """显示音频信息"""
        try:
            duration = self.workflow.ffmpeg_audio_processor.get_duration(audio_path)
            self.audio_info_label.config(text=f"音频: {os.path.basename(audio_path)} ({duration:.1f}s)")
            
            # 简单的音频可视化
            self.audio_canvas.delete("all")
            self.audio_canvas.create_text(200, 200, text="🔊", font=('Arial', 80), fill='white')
        except Exception as e:
            self.audio_info_label.config(text=f"音频加载失败: {str(e)}")
    
    def toggle_video_playback(self):
        """切换视频播放"""
        # TODO: 实现视频播放
        pass
    
    def toggle_audio_playback(self):
        """切换音频播放"""
        if PYGAME_AVAILABLE:
            audio_path = self.new_audio or self.current_audio
            if audio_path and os.path.exists(audio_path):
                if not self.audio_playing:
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.play()
                    self.audio_playing = True
                    self.audio_play_btn.config(text="停止")
                else:
                    pygame.mixer.music.stop()
                    self.audio_playing = False
                    self.audio_play_btn.config(text="播放")
    
    def clear_video(self):
        """清除视频"""
        self.new_video = None
        self.video_canvas.delete("all")
        self.video_info_label.config(text="无视频")
    
    def clear_image(self):
        """清除图片"""
        self.new_image = None
        self.image_canvas.delete("all")
        self.image_info_label.config(text="无图片")
    
    def clear_audio(self):
        """清除音频"""
        self.new_audio = None
        if PYGAME_AVAILABLE:
            pygame.mixer.music.stop()
        self.audio_playing = False
        self.audio_canvas.delete("all")
        self.audio_info_label.config(text="无音频")
    
    def confirm(self):
        """确认并保存更改"""
        try:
            # 获取最终的媒体路径
            final_image = self.new_image or self.current_image
            final_audio = self.new_audio or self.current_audio
            final_video = self.new_video or self.current_video
            
            # 处理各种情况
            if final_video:
                # 有视频
                if self.new_video:
                    # 新视频被拖入
                    if not self.workflow.ffmpeg_processor.has_audio_stream(final_video) and final_audio:
                        # 视频没有音频，添加音频
                        final_video = self.workflow.ffmpeg_processor.add_audio_to_video(final_video, final_audio)
                    
                    # 更新场景
                    old_v, new_v = refresh_scene_media(self.scene, self.video_field, ".mp4", final_video)
                    final_video = new_v
                
                # 如果音频被更新，替换视频中的音频
                if self.new_audio and not self.new_video:
                    final_video = self.workflow.ffmpeg_processor.add_audio_to_video(final_video, final_audio)
                    old_v, new_v = refresh_scene_media(self.scene, self.video_field, ".mp4", final_video)
                    final_video = new_v
                
                # 提取音频
                if self.workflow.ffmpeg_processor.has_audio_stream(final_video):
                    final_audio = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(final_video)
            
            else:
                # 没有视频，从图片和音频生成
                if final_image and final_audio:
                    final_video = self.workflow.ffmpeg_processor.image_audio_to_video( final_image, final_audio, self.animation_var.get() )
                    old_v, new_v = refresh_scene_media(self.scene, self.video_field, ".mp4", final_video)
                    final_video = new_v
            
            # 更新音频
            if final_audio:
                old_a, new_a = refresh_scene_media(self.scene, self.audio_field, ".wav", final_audio)
            
            # 更新图片
            if self.new_image:
                old_i, new_i = refresh_scene_media(self.scene, self.image_field, ".webp", final_image)
            
            self.workflow.save_scenes_to_json()
            self.result = "ok"
            self.cleanup()
            self.dialog.destroy()
            
            messagebox.showinfo("成功", "媒体已更新")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def cancel(self):
        """取消"""
        self.result = "cancel"
        self.cleanup()
        self.dialog.destroy()
    
    def cleanup(self):
        """清理资源"""
        if PYGAME_AVAILABLE:
            pygame.mixer.music.stop()
        if self.video_cap:
            self.video_cap.release()
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
    
    def show(self):
        """显示对话框"""
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        self.dialog.wait_window()
        return self.result


def show_enhanced_media_editor(parent, scene):
    """显示增强的媒体编辑器"""
    # 首先选择媒体类型
    selector = MediaTypeSelector(parent.root if hasattr(parent, 'root') else parent)
    media_type = selector.show()
    
    if media_type:
        # 打开编辑器
        editor = EnhancedMediaEditor(parent, scene, media_type)
        return editor.show()
    
    return None

