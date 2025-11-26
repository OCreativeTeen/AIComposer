import tkinter as tk
from tkinter import ttk
import os


class PictureInPictureDialog:
    """Dialog for configuring picture-in-picture settings"""
    
    def __init__(self, parent, background_video_path, overlay_video_path, overlay_left_path, overlay_right_path):
        self.parent = parent
        self.background_video_path = background_video_path
        self.overlay_video_path = overlay_video_path
        self.result = None  # Will store the result when dialog is closed
        
        # Default settings
        if overlay_left_path or overlay_right_path:
            self.ratio = 0.7
            if overlay_left_path:
                self.position = "left"
            if overlay_right_path:
                self.position = "right"
            if overlay_left_path and overlay_right_path:
                self.position = "center"
            self.transition_duration = 0.0
        else:
            self.ratio = 0.5
            self.position = "right"
            self.transition_duration = 1.2

        self.shape = ""  # none/empty, circle, oval
        self.audio_volume = 0
        
        self.create_dialog()
        
    def create_dialog(self):
        """Create the dialog window"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("画中画设置")
        self.dialog.geometry("400x520")
        self.dialog.resizable(False, False)
        self.dialog.grab_set()  # Make dialog modal
        
        # Center the dialog
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Video info section
        info_frame = ttk.LabelFrame(main_frame, text="视频信息", padding=5)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(info_frame, text=f"背景视频: {os.path.basename(self.background_video_path)}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"叠加视频: {os.path.basename(self.overlay_video_path)}").pack(anchor=tk.W)
        
        # Settings section
        settings_frame = ttk.LabelFrame(main_frame, text="画中画设置", padding=5)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Ratio setting
        ratio_frame = ttk.Frame(settings_frame)
        ratio_frame.pack(fill=tk.X, pady=2)
        ttk.Label(ratio_frame, text="尺寸比例:").pack(side=tk.LEFT)
        self.ratio_var = tk.DoubleVar(value=self.ratio)
        ratio_scale = ttk.Scale(ratio_frame, from_=0.333, to=0.8, variable=self.ratio_var, orient=tk.HORIZONTAL)
        ratio_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        self.ratio_label = ttk.Label(ratio_frame, text=f"{self.ratio:.2f}")
        self.ratio_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Update ratio label when scale changes
        def update_ratio_label(*args):
            self.ratio_label.config(text=f"{self.ratio_var.get():.2f}")
        self.ratio_var.trace('w', update_ratio_label)
        
        # Position setting
        position_frame = ttk.Frame(settings_frame)
        position_frame.pack(fill=tk.X, pady=5)
        ttk.Label(position_frame, text="位置:").pack(side=tk.LEFT)
        
        self.position_var = tk.StringVar(value=self.position)
        positions = [("右", "right"), ("左", "left"), ("中心", "center"), ("满屏", "full"), ("影音", "av")]
        for i, (text, value) in enumerate(positions):
            ttk.Radiobutton(position_frame, text=text, variable=self.position_var, 
                          value=value).pack(side=tk.LEFT, padx=(10, 0))
        
        self.shape_var = tk.StringVar(value="")

        # Shape setting
        #shape_frame = ttk.Frame(settings_frame)
        #shape_frame.pack(fill=tk.X, pady=5)
        #ttk.Label(shape_frame, text="形状:").pack(side=tk.LEFT)
        #self.shape_var = tk.StringVar(value=self.shape)
        #shapes = [("矩形", ""), ("圆形", "circle"), ("椭圆", "oval")]
        #for i, (text, value) in enumerate(shapes):
        #    ttk.Radiobutton(shape_frame, text=text, variable=self.shape_var, 
        #                  value=value).pack(side=tk.LEFT, padx=(10, 0))
        
        # Transition duration setting
        transition_frame = ttk.Frame(settings_frame)
        transition_frame.pack(fill=tk.X, pady=2)
        ttk.Label(transition_frame, text="过渡时长(秒):").pack(side=tk.LEFT)
        self.transition_var = tk.DoubleVar(value=self.transition_duration)
        transition_scale = ttk.Scale(transition_frame, from_=0.0, to=3.0, variable=self.transition_var, orient=tk.HORIZONTAL)
        transition_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        self.transition_label = ttk.Label(transition_frame, text=f"{self.transition_duration:.1f}")
        self.transition_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Update transition label when scale changes
        def update_transition_label(*args):
            self.transition_label.config(text=f"{self.transition_var.get():.1f}")
        self.transition_var.trace('w', update_transition_label)
        
        # Audio volume setting
        volume_frame = ttk.Frame(settings_frame)
        volume_frame.pack(fill=tk.X, pady=2)
        ttk.Label(volume_frame, text="音频音量:").pack(side=tk.LEFT)
        self.volume_var = tk.DoubleVar(value=self.audio_volume)
        volume_scale = ttk.Scale(volume_frame, from_=-0.9, to=0.9, variable=self.volume_var, orient=tk.HORIZONTAL)
        volume_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        self.volume_label = ttk.Label(volume_frame, text=f"{self.audio_volume:.2f}")
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Update volume label when scale changes
        def update_volume_label(*args):
            self.volume_label.config(text=f"{self.volume_var.get():.2f}")
        self.volume_var.trace('w', update_volume_label)
        
        # Delay time setting (for left/right overlays)
        delay_frame = ttk.Frame(settings_frame)
        delay_frame.pack(fill=tk.X, pady=2)
        ttk.Label(delay_frame, text="延迟时间(秒):").pack(side=tk.LEFT)
        self.delay_var = tk.DoubleVar(value=0.0)
        delay_scale = ttk.Scale(delay_frame, from_=0.0, to=10.0, variable=self.delay_var, orient=tk.HORIZONTAL)
        delay_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        self.delay_label = ttk.Label(delay_frame, text="0.0")
        self.delay_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Update delay label when scale changes
        def update_delay_label(*args):
            self.delay_label.config(text=f"{self.delay_var.get():.1f}")
        self.delay_var.trace('w', update_delay_label)
        
        # Preview section
        preview_frame = ttk.LabelFrame(main_frame, text="预览", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        preview_canvas = tk.Canvas(preview_frame, bg='black', height=120)
        preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Create preview visualization
        def update_preview(*args):
            preview_canvas.delete("all")
            canvas_width = preview_canvas.winfo_width() or 300
            canvas_height = preview_canvas.winfo_height() or 120
            
            if canvas_width <= 1:  # Not rendered yet
                self.dialog.after(100, update_preview)
                return
                
            # Draw background (main video)
            bg_rect = preview_canvas.create_rectangle(5, 5, canvas_width-5, canvas_height-5, 
                                                    fill='#333333', outline='white')
            preview_canvas.create_text(canvas_width//2, canvas_height//2, text="主视频", fill='white')
            
            # Draw overlay (picture-in-picture)
            ratio = self.ratio_var.get()
            overlay_width = int((canvas_width - 10) * ratio)
            overlay_height = int((canvas_height - 10) * ratio)
            
            position = self.position_var.get()
            if position == "right":
                x1 = canvas_width - overlay_width - 15
                y1 = canvas_height - overlay_height - 15
            elif position == "left":
                x1 = 15
                y1 = canvas_height - overlay_height - 15
            elif position == "center":
                x1 = (canvas_width - overlay_width) // 2
                y1 = (canvas_height - overlay_height) // 2
            
            x2 = x1 + overlay_width
            y2 = y1 + overlay_height
            
            shape = self.shape_var.get()
            if shape == "circle":
                # Draw circle
                preview_canvas.create_oval(x1, y1, x2, y2, fill='#666666', outline='yellow', width=2)
                preview_canvas.create_text((x1+x2)//2, (y1+y2)//2, text="画中画", fill='white', font=('Arial', 8))
            elif shape == "oval":
                # Draw oval (same as circle for this preview)
                preview_canvas.create_oval(x1, y1, x2, y2, fill='#666666', outline='orange', width=2)
                preview_canvas.create_text((x1+x2)//2, (y1+y2)//2, text="画中画", fill='white', font=('Arial', 8))
            else:
                # Draw rectangle
                preview_canvas.create_rectangle(x1, y1, x2, y2, fill='#666666', outline='cyan', width=2)
                preview_canvas.create_text((x1+x2)//2, (y1+y2)//2, text="画中画", fill='white', font=('Arial', 8))
        
        # Bind all variables to update preview
        self.ratio_var.trace('w', update_preview)
        self.position_var.trace('w', update_preview)
        self.shape_var.trace('w', update_preview)
        
        # Initial preview after dialog is shown
        self.dialog.after(200, update_preview)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="确定", command=self.apply).pack(side=tk.RIGHT)
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        
    def apply(self):
        """Apply settings and close dialog"""
        self.result = {
            'ratio': self.ratio_var.get(),
            'position': self.position_var.get(),
            'shape': self.shape_var.get(),
            'transition_duration': self.transition_var.get(),
            'audio_volume': self.volume_var.get(),
            'delay_time': self.delay_var.get()
        }
        self.dialog.destroy()
        
    def cancel(self):
        """Cancel and close dialog"""
        self.result = None
        self.dialog.destroy()
