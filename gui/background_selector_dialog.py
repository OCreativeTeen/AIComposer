import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import pygame
from PIL import Image, ImageTk
from pathlib import Path
import config


class BackgroundSelectorDialog:
    """Dialog for selecting background image and music"""
    
    def __init__(self, parent, magic_workflow, new_clip_image):
        self.parent = parent
        self.workflow = magic_workflow
        self.result = None  # Will store the result when dialog is closed
        # Initialize pygame mixer for audio playback
        try:
            pygame.mixer.init()
            self.pygame_available = True
        except Exception as e:
            print(f"⚠️ pygame初始化失败: {e}")
            self.pygame_available = False
        
        # Current selections
        self.selected_background_images = []  # 修改为列表支持多选
        if new_clip_image:
            self.selected_background_images.append(new_clip_image)

        self.selected_background_music = None
        
        # Audio playback state
        self.current_music = None
        self.is_playing = False
        
        self.create_dialog()
        
        
    def create_dialog(self):
        """Create the dialog window"""
        self.dialog = tk.Toplevel(self.parent.root)
        self.dialog.title("选择背景图片和音乐")
        self.dialog.geometry("1000x700")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent.root)
        self.dialog.grab_set()
        
        # Main container
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create paned window for left and right sections
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Background Image
        left_frame = ttk.LabelFrame(paned_window, text="背景图片", padding=10)
        paned_window.add(left_frame, weight=1)
        
        self.create_image_section(left_frame)
        
        # Right panel - Background Music
        right_frame = ttk.LabelFrame(paned_window, text="背景音乐", padding=10)
        paned_window.add(right_frame, weight=1)
        
        self.create_music_section(right_frame)
        
        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="确定", command=self.confirm_selection).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=self.cancel_selection).pack(side=tk.RIGHT)
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel_selection)
        
    def create_image_section(self, parent):
        """Create the image selection section"""
        # Controls frame
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(controls_frame, text="浏览文件", command=self.browse_image_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(controls_frame, text="清空选择", command=self.clear_image_selection).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(controls_frame, text="刷新", command=self.refresh_image_list).pack(side=tk.LEFT)
        
        # Status label
        self.image_status_label = ttk.Label(controls_frame, text="正在加载...", foreground="blue")
        self.image_status_label.pack(side=tk.RIGHT)
        
        # Image preview
        self.image_canvas = tk.Canvas(parent, bg='gray', height=200)
        self.image_canvas.pack(fill=tk.X, pady=(0, 10))
        
        # Image selection frame with scrollbar
        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview for image list
        tree_frame = ttk.Frame(selection_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.image_tree = ttk.Treeview(tree_frame, columns=('path',), show='tree', selectmode='extended')  # 支持多选
        self.image_tree.heading('#0', text='图片文件 (支持多选)')
        self.image_tree.column('#0', width=300)
        self.image_tree.column('path', width=0, stretch=False)  # Hidden column for full path
        
        # Scrollbars for image tree
        img_v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.image_tree.yview)
        img_h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.image_tree.xview)
        self.image_tree.configure(yscrollcommand=img_v_scrollbar.set, xscrollcommand=img_h_scrollbar.set)
        
        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        img_v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        img_h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind selection event
        self.image_tree.bind('<<TreeviewSelect>>', self.on_image_select)
        
    def create_music_section(self, parent):
        """Create the music selection section"""
        # Controls frame
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(controls_frame, text="浏览文件", command=self.browse_music_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(controls_frame, text="刷新", command=self.refresh_music_list).pack(side=tk.LEFT)
        
        # Status label
        self.music_status_label = ttk.Label(controls_frame, text="正在加载...", foreground="blue")
        self.music_status_label.pack(side=tk.RIGHT)
        
        # Music player controls
        player_frame = ttk.Frame(parent)
        player_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.play_button = ttk.Button(player_frame, text="▶ 播放", command=self.toggle_music_playback)
        self.play_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(player_frame, text="⏹ 停止", command=self.stop_music_playback)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # Volume control
        ttk.Label(player_frame, text="音量:").pack(side=tk.LEFT, padx=(20, 5))
        self.volume_var = tk.DoubleVar(value=0.7)
        volume_scale = ttk.Scale(player_frame, from_=0.0, to=1.0, variable=self.volume_var, orient=tk.HORIZONTAL, length=100)
        volume_scale.pack(side=tk.LEFT, padx=(0, 10))
        self.volume_var.trace('w', self.on_volume_change)
        
        # Music info display
        info_frame = ttk.LabelFrame(parent, text="音乐信息", padding=5)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.music_info_text = tk.Text(info_frame, height=4, wrap=tk.WORD, state=tk.DISABLED)
        info_scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=self.music_info_text.yview)
        self.music_info_text.configure(yscrollcommand=info_scrollbar.set)
        
        self.music_info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Music selection frame with scrollbar
        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview for music list
        tree_frame = ttk.Frame(selection_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.music_tree = ttk.Treeview(tree_frame, columns=('path',), show='tree')
        self.music_tree.heading('#0', text='音乐文件')
        self.music_tree.column('#0', width=300)
        self.music_tree.column('path', width=0, stretch=False)  # Hidden column for full path
        
        # Scrollbars for music tree
        music_v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.music_tree.yview)
        music_h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.music_tree.xview)
        self.music_tree.configure(yscrollcommand=music_v_scrollbar.set, xscrollcommand=music_h_scrollbar.set)
        
        self.music_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        music_v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        music_h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind selection event
        self.music_tree.bind('<<TreeviewSelect>>', self.on_music_select)
        
    
    def _update_status_error(self, error_msg):
        """Update status with error message"""
        self.image_status_label.config(text=f"加载失败: {error_msg}", foreground="red")
        self.music_status_label.config(text=f"加载失败: {error_msg}", foreground="red")
        
    def load_image_files(self, default_path=None):
        """Load background image files"""
        try:
            self.image_tree.delete(*self.image_tree.get_children())
            
            # Get background image path
            base_path = config.get_background_image_path()
            channel_path = os.path.join(base_path, self.workflow.channel)
            
            image_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']
            
            # Scan for image files
            found_files = []
            if os.path.exists(channel_path):
                for root, dirs, files in os.walk(channel_path):
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in image_extensions):
                            full_path = os.path.join(root, file)
                            found_files.append(full_path)
            
            # Sort files
            found_files.sort()
            
            # Add to tree
            for file_path in found_files:
                filename = os.path.basename(file_path)
                item_id = self.image_tree.insert('', 'end', text=filename, values=(file_path,))
                
                # Select default if matches
                if default_path and file_path == default_path:
                    self.image_tree.selection_set(item_id)
                    self.image_tree.focus(item_id)
            
            self.image_status_label.config(text=f"找到 {len(found_files)} 个图片文件", foreground="green")
            
        except Exception as e:
            print(f"❌ 加载图片文件失败: {e}")
            self.image_status_label.config(text=f"加载失败: {str(e)}", foreground="red")
            
    def load_music_files(self, default_path=None):
        """Load background music files"""
        try:
            self.music_tree.delete(*self.music_tree.get_children())
            
            # Get background music path
            base_path = config.get_background_music_path()
            channel_path = os.path.join(base_path, self.workflow.channel)
            
            music_extensions = ['.mp3', '.wav', '.ogg', '.m4a']
            
            # Scan for music files
            found_files = []
            if os.path.exists(channel_path):
                for root, dirs, files in os.walk(channel_path):
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in music_extensions):
                            full_path = os.path.join(root, file)
                            found_files.append(full_path)
            
            # Sort files
            found_files.sort()
            
            # Add to tree
            for file_path in found_files:
                filename = os.path.basename(file_path)
                item_id = self.music_tree.insert('', 'end', text=filename, values=(file_path,))
                
                # Select default if matches
                if default_path and file_path == default_path:
                    self.music_tree.selection_set(item_id)
                    self.music_tree.focus(item_id)
            
            self.music_status_label.config(text=f"找到 {len(found_files)} 个音乐文件", foreground="green")
            
        except Exception as e:
            print(f"❌ 加载音乐文件失败: {e}")
            self.music_status_label.config(text=f"加载失败: {str(e)}", foreground="red")
    
    def on_image_select(self, event):
        """Handle image selection (支持多选)"""
        selection = self.image_tree.selection()
        if selection:
            # 获取所有选中的图片路径
            for item_id in selection:
                file_path = self.image_tree.item(item_id, 'values')[0]
                self.selected_background_images.append(file_path)
            
            # 预览第一个选中的图片
            if self.selected_background_images:
                self.preview_image(self.selected_background_images[0])
                
            # 更新状态显示
            count = len(self.selected_background_images)
            self.image_status_label.config(text=f"已选择 {count} 个图片文件", foreground="blue")
    
    def on_music_select(self, event):
        """Handle music selection"""
        selection = self.music_tree.selection()
        if selection:
            item_id = selection[0]
            file_path = self.music_tree.item(item_id, 'values')[0]
            self.selected_background_music = file_path
            self.update_music_info(file_path)
    
    def preview_image(self, image_path):
        """Preview selected image"""
        try:
            if not os.path.exists(image_path):
                return
                
            # Load and resize image for preview
            image = Image.open(image_path)
            
            # Calculate size to fit canvas
            canvas_width = self.image_canvas.winfo_width() or 300
            canvas_height = self.image_canvas.winfo_height() or 200
            
            # Resize image maintaining aspect ratio
            image.thumbnail((canvas_width - 20, canvas_height - 20), Image.Resampling.LANCZOS)
            
            # Create PhotoImage and display
            self.preview_photo = ImageTk.PhotoImage(image)
            
            self.image_canvas.delete("all")
            self.image_canvas.create_image(canvas_width//2, canvas_height//2, 
                                         image=self.preview_photo, anchor=tk.CENTER)
            
            # Show image info with selection count
            selected_count = len(self.selected_background_images)
            count_text = f"[{selected_count} 张已选择] " if selected_count > 1 else ""
            self.image_canvas.create_text(10, canvas_height-10, 
                                        text=f"{count_text}{os.path.basename(image_path)} ({image.width}x{image.height})",
                                        anchor=tk.SW, fill="white")
            
        except Exception as e:
            print(f"❌ 图片预览失败: {e}")
            self.image_canvas.delete("all")
            self.image_canvas.create_text(self.image_canvas.winfo_width()//2, 
                                        self.image_canvas.winfo_height()//2,
                                        text="预览失败", anchor=tk.CENTER, fill="red")
    
    def update_music_info(self, music_path):
        """Update music information display"""
        try:
            if not os.path.exists(music_path):
                return
                
            # Get file info
            file_size = os.path.getsize(music_path)
            file_size_mb = file_size / (1024 * 1024)
            
            # Try to get duration if possible
            duration_text = "未知"
            try:
                if hasattr(self.workflow, 'ffmpeg_audio_processor'):
                    duration = self.workflow.ffmpeg_audio_processor.get_duration(music_path)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    duration_text = f"{minutes}:{seconds:02d}"
            except:
                pass
            
            info_text = f"""文件: {os.path.basename(music_path)}
路径: {music_path}
大小: {file_size_mb:.2f} MB
时长: {duration_text}"""
            
            self.music_info_text.config(state=tk.NORMAL)
            self.music_info_text.delete(1.0, tk.END)
            self.music_info_text.insert(1.0, info_text)
            self.music_info_text.config(state=tk.DISABLED)
            
        except Exception as e:
            print(f"❌ 音乐信息更新失败: {e}")
    
    def toggle_music_playback(self):
        """Toggle music playback"""
        if not self.pygame_available:
            messagebox.showwarning("警告", "音频播放功能不可用，请安装pygame")
            return
            
        if self.is_playing:
            self.pause_music()
        else:
            self.play_music()
    
    def play_music(self):
        """Play selected music"""
        if not self.selected_background_music or not os.path.exists(self.selected_background_music):
            messagebox.showwarning("警告", "请先选择音乐文件")
            return
            
        try:
            pygame.mixer.music.load(self.selected_background_music)
            pygame.mixer.music.set_volume(self.volume_var.get())
            pygame.mixer.music.play()
            
            self.is_playing = True
            self.play_button.config(text="⏸ 暂停")
            
        except Exception as e:
            messagebox.showerror("错误", f"播放音乐失败: {str(e)}")
    
    def pause_music(self):
        """Pause music playback"""
        try:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_button.config(text="▶ 播放")
        except:
            pass
    
    def stop_music_playback(self):
        """Stop music playback"""
        try:
            pygame.mixer.music.stop()
            self.is_playing = False
            self.play_button.config(text="▶ 播放")
        except:
            pass
    
    def on_volume_change(self, *args):
        """Handle volume change"""
        if self.pygame_available:
            try:
                pygame.mixer.music.set_volume(self.volume_var.get())
            except:
                pass
    
    
    def _select_in_tree(self, tree, file_path):
        """Select item in tree by file path"""
        for item_id in tree.get_children():
            if tree.item(item_id, 'values')[0] == file_path:
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
                break
    
    def browse_image_file(self):
        """Browse for image files (支持多选)"""
        filetypes = [
            ("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp"),
            ("PNG文件", "*.png"),
            ("JPEG文件", "*.jpg *.jpeg"),
            ("所有文件", "*.*")
        ]
        
        initial_dir = config.get_background_image_path()
        filenames = filedialog.askopenfilenames(  # 改为 askopenfilenames 支持多选
            title="选择背景图片 (支持多选)",
            initialdir=initial_dir,
            filetypes=filetypes
        )
        
        if filenames:
            self.selected_background_images = list(filenames)  # 转换为列表
            self.preview_image(filenames[0])  # 预览第一个图片
            # Add all files to tree if not already there
            for filename in filenames:
                self._add_custom_file_to_tree(self.image_tree, filename)
    
    def browse_music_file(self):
        """Browse for music file"""
        filetypes = [
            ("音频文件", "*.mp3 *.wav *.ogg *.m4a"),
            ("MP3文件", "*.mp3"),
            ("WAV文件", "*.wav"),
            ("所有文件", "*.*")
        ]
        
        initial_dir = config.get_background_music_path()
        filename = filedialog.askopenfilename(
            title="选择背景音乐",
            initialdir=initial_dir,
            filetypes=filetypes
        )
        
        if filename:
            self.selected_background_music = filename
            self.update_music_info(filename)
            # Add to tree if not already there
            self._add_custom_file_to_tree(self.music_tree, filename)
    
    def _add_custom_file_to_tree(self, tree, file_path):
        """Add custom file to tree if not already present"""
        # Check if file already in tree
        for item_id in tree.get_children():
            if tree.item(item_id, 'values')[0] == file_path:
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
                return
        
        # Add new item
        filename = f"[自定义] {os.path.basename(file_path)}"
        item_id = tree.insert('', 0, text=filename, values=(file_path,))
        tree.selection_set(item_id)
        tree.focus(item_id)
        tree.see(item_id)
    
    def clear_image_selection(self):
        """Clear image selection"""
        self.selected_background_images = []
        self.image_tree.selection_remove(*self.image_tree.selection())
        self.image_canvas.delete("all")
        self.image_status_label.config(text="已清空选择", foreground="orange")
    
    def refresh_image_list(self):
        """Refresh image file list"""
        self.load_image_files()
    
    def refresh_music_list(self):
        """Refresh music file list"""
        self.load_music_files()
    
    def confirm_selection(self):
        """Confirm selection and close dialog"""
        if not self.selected_background_images:  # 检查列表是否为空
            messagebox.showwarning("警告", "请选择背景图片")
            return
            
        if not self.selected_background_music:
            messagebox.showwarning("警告", "请选择背景音乐")
            return
        
        # Validate file existence for all selected images
        for image_path in self.selected_background_images:
            if not os.path.exists(image_path):
                messagebox.showerror("错误", f"选择的背景图片文件不存在: {os.path.basename(image_path)}")
                return
            
        if not os.path.exists(self.selected_background_music):
            messagebox.showerror("错误", "选择的背景音乐文件不存在")
            return
        
        self.result = {
            'confirmed': True,
            'background_images': self.selected_background_images,  # 返回图片列表
            'background_music': self.selected_background_music
        }
        
        self.close_dialog()
    
    def cancel_selection(self):
        """Cancel selection and close dialog"""
        self.result = {'confirmed': False}
        self.close_dialog()
    
    def close_dialog(self):
        """Close dialog and cleanup"""
        # Stop music playback
        self.stop_music_playback()
        
        # Close dialog
        self.dialog.destroy()
