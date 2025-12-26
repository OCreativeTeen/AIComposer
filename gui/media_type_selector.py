import tkinter as tk
from tkinter import ttk
import os
from utility.ffmpeg_processor import FfmpegProcessor


class MediaTypeSelector:
    """对话框：选择要编辑的媒体类型和音频处理选项"""
    
    def __init__(self, parent, av_path, has_audio, current_scene=None):
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
        if has_audio:
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
