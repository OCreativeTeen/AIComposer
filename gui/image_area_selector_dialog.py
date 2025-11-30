import tkinter as tk
from tkinter import ttk, messagebox
import os
import tempfile
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
class ImageAreaSelectorDialog:
    """对话框用于选择图像区域和设置垂直分割线"""
    
    def __init__(self, parent, source_image_path, video_width, video_height):
        self.parent = parent
        self.source_image_path = source_image_path
        self.video_width = int(video_width)
        self.video_height = int(video_height)
        
        # 结果变量
        self.result_image_path = None
        self.vertical_line_position = 0
        self.dialog_result = None
        self.target_field_choice = "clip_image"  # 默认保存到 clip_image
        
        # 画布和图像相关变量
        self.canvas = None
        self.original_image = None
        self.display_image = None
        self.canvas_width = 800
        self.canvas_height = 550
        self.scale_factor = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        
        # 选择框相关变量
        self.selection_rect = None
        self.selection_start_x = 0
        self.selection_start_y = 0
        self.selection_width = 0
        self.selection_height = 0
        self.dragging_selection = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # 垂直分割线相关变量
        self.vertical_line = None
        self.vertical_line_x = 0
        self.dragging_line = False
        
        self.create_dialog()
        self.load_image()
        
    def create_dialog(self):
        """创建对话框窗口"""
        self.dialog = tk.Toplevel(self.parent.root if hasattr(self.parent, 'root') else self.parent)
        self.dialog.title("选择图像区域")
        self.dialog.geometry("900x750")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent.root if hasattr(self.parent, 'root') else self.parent)
        self.dialog.grab_set()
        
        # 主容器
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 说明标签
        info_label = ttk.Label(main_frame, text=f"拖拽选择图像区域 (比例: {self.video_width}×{self.video_height})，移动垂直线设置分割位置")
        info_label.pack(pady=(0, 10))
        
        # 画布框架
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建画布和滚动条
        self.canvas = tk.Canvas(canvas_frame, bg='white', width=self.canvas_width, height=self.canvas_height)
        
        # 滚动条
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # 布局画布和滚动条
        self.canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        
        # 目标字段选择框架
        target_frame = ttk.LabelFrame(main_frame, text="保存到字段")
        target_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 目标字段选择变量
        self.target_field_var = tk.StringVar(value="clip_image")
        
        # 创建单选按钮
        target_options = [
            ("clip_image", "主景图片"),
            ("second_image", "次景图片"), 
            ("zero_image", "背景图片")
        ]
        
        for value, text in target_options:
            ttk.Radiobutton(
                target_frame, 
                text=text, 
                variable=self.target_field_var, 
                value=value
            ).pack(side=tk.LEFT, padx=10, pady=5)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 重置按钮
        ttk.Button(button_frame, text="重置选择", command=self.reset_selection).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="重置中线", command=self.reset_vertical_line).pack(side=tk.LEFT, padx=(0, 10))
        
        # 信息标签
        self.info_var = tk.StringVar()
        self.info_label = ttk.Label(button_frame, textvariable=self.info_var)
        self.info_label.pack(side=tk.LEFT, expand=True)
        
        # 确定和取消按钮
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="确定", command=self.confirm).pack(side=tk.RIGHT)
        
        # 设置对话框关闭事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        
    def load_image(self):
        """加载并显示图像"""
        try:
            self.original_image = Image.open(self.source_image_path)
            
            # 计算缩放比例以适应画布
            img_width, img_height = self.original_image.size
            scale_x = self.canvas_width / img_width
            scale_y = self.canvas_height / img_height
            self.scale_factor = min(scale_x, scale_y, 1.0)  # 不放大，只缩小
            
            # 计算显示尺寸和偏移
            display_width = int(img_width * self.scale_factor)
            display_height = int(img_height * self.scale_factor)
            self.image_offset_x = (self.canvas_width - display_width) // 2
            self.image_offset_y = (self.canvas_height - display_height) // 2
            
            # 创建显示图像
            self.display_image = self.original_image.resize((display_width, display_height), Image.Resampling.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(self.display_image)
            
            # 设置画布滚动区域
            self.canvas.configure(scrollregion=(0, 0, display_width + self.image_offset_x * 2, 
                                              display_height + self.image_offset_y * 2))
            
            # 在画布上显示图像
            self.canvas.create_image(self.image_offset_x, self.image_offset_y, 
                                   anchor=tk.NW, image=self.photo_image, tags="image")
            
            # 初始化选择区域（默认选择整个图像的中心区域）
            self.init_default_selection()
            
        except Exception as e:
            messagebox.showerror("错误", f"无法加载图像: {str(e)}")
            self.cancel()
    
    def init_default_selection(self):
        """初始化默认选择区域"""
        img_width, img_height = self.display_image.size
        
        # 根据视频比例计算默认选择区域
        video_aspect = self.video_width / self.video_height
        img_aspect = img_width / img_height
        if video_aspect > img_aspect:
            # 视频更宽，以图像宽度为准
            selection_width = img_width
            selection_height = int(selection_width / video_aspect)
        else:
            # 视频更高，以图像高度为准
            selection_height = img_height
            selection_width = int(selection_height * video_aspect)
        
        # 居中放置
        self.selection_start_x = self.image_offset_x + (img_width - selection_width) // 2
        self.selection_start_y = self.image_offset_y + (img_height - selection_height) // 2
        self.selection_width = selection_width
        self.selection_height = selection_height
        
        # 初始化垂直分割线位置（选择区域的中央）
        self.vertical_line_x = self.selection_start_x + self.selection_width // 2
        
        self.update_selection_display()
        self.update_info()
    
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """将画布坐标转换为图像坐标"""
        image_x = (canvas_x - self.image_offset_x) / self.scale_factor
        image_y = (canvas_y - self.image_offset_y) / self.scale_factor
        return image_x, image_y
    
    def image_to_canvas_coords(self, image_x, image_y):
        """将图像坐标转换为画布坐标"""
        canvas_x = image_x * self.scale_factor + self.image_offset_x
        canvas_y = image_y * self.scale_factor + self.image_offset_y
        return canvas_x, canvas_y
    
    def on_mouse_press(self, event):
        """鼠标按下事件"""
        x, y = event.x, event.y
        
        # 检查是否点击在垂直分割线附近
        if abs(x - self.vertical_line_x) < 10:
            self.dragging_line = True
            return
        
        # 检查是否点击在选择区域内
        if (self.selection_start_x <= x <= self.selection_start_x + self.selection_width and
            self.selection_start_y <= y <= self.selection_start_y + self.selection_height):
            self.dragging_selection = True
            self.drag_start_x = x - self.selection_start_x
            self.drag_start_y = y - self.selection_start_y
        else:
            # 开始新的选择
            self.selection_start_x = x
            self.selection_start_y = y
            self.selection_width = 0
            self.selection_height = 0
            self.dragging_selection = False
    
    def on_mouse_drag(self, event):
        """鼠标拖拽事件"""
        x, y = event.x, event.y
        
        if self.dragging_line:
            # 拖拽垂直分割线
            # 限制在选择区域内
            min_x = self.selection_start_x
            max_x = self.selection_start_x + self.selection_width
            self.vertical_line_x = max(min_x, min(max_x, x))
            self.update_vertical_line()
            self.update_info()
        elif self.dragging_selection:
            # 拖拽整个选择区域
            new_x = x - self.drag_start_x
            new_y = y - self.drag_start_y
            
            # 限制在图像范围内
            img_width, img_height = self.display_image.size
            max_x = self.image_offset_x + img_width - self.selection_width
            max_y = self.image_offset_y + img_height - self.selection_height
            
            self.selection_start_x = max(self.image_offset_x, min(max_x, new_x))
            self.selection_start_y = max(self.image_offset_y, min(max_y, new_y))
            
            # 更新垂直分割线位置（保持相对位置）
            relative_pos = (self.vertical_line_x - (self.selection_start_x - (new_x - self.selection_start_x))) / self.selection_width
            self.vertical_line_x = self.selection_start_x + int(self.selection_width * relative_pos)
            
            self.update_selection_display()
            self.update_info()
        else:
            # 创建新的选择区域
            video_aspect = self.video_width / self.video_height
            width = abs(x - self.selection_start_x)
            height = int(width / video_aspect)  # 保持视频比例
            
            # 调整起始点和尺寸
            if x < self.selection_start_x:
                self.selection_start_x = x
            if y < self.selection_start_y:
                self.selection_start_y = y
                
            # 限制在图像范围内
            img_width, img_height = self.display_image.size
            max_width = self.image_offset_x + img_width - self.selection_start_x
            max_height = self.image_offset_y + img_height - self.selection_start_y
            
            self.selection_width = min(width, max_width)
            self.selection_height = min(height, max_height, int(self.selection_width / video_aspect))
            
            # 重新调整宽度以保持比例
            self.selection_width = int(self.selection_height * video_aspect)
            
            # 更新垂直分割线位置
            self.vertical_line_x = self.selection_start_x + self.selection_width // 2
            
            self.update_selection_display()
            self.update_info()
    
    def on_mouse_release(self, event):
        """鼠标释放事件"""
        self.dragging_selection = False
        self.dragging_line = False
    
    def on_mouse_move(self, event):
        """鼠标移动事件（用于改变光标）"""
        x, y = event.x, event.y
        
        # 检查是否在垂直分割线附近
        if abs(x - self.vertical_line_x) < 10:
            self.canvas.configure(cursor="sb_h_double_arrow")
        elif (self.selection_start_x <= x <= self.selection_start_x + self.selection_width and
              self.selection_start_y <= y <= self.selection_start_y + self.selection_height):
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="crosshair")
    
    def update_selection_display(self):
        """更新选择区域显示"""
        # 删除旧的选择框
        self.canvas.delete("selection")
        
        if self.selection_width > 0 and self.selection_height > 0:
            # 绘制选择框
            self.selection_rect = self.canvas.create_rectangle(
                self.selection_start_x, self.selection_start_y,
                self.selection_start_x + self.selection_width,
                self.selection_start_y + self.selection_height,
                outline="red", width=2, tags="selection"
            )
            
            # 绘制选择区域外的半透明遮罩
            img_width, img_height = self.display_image.size
            
            # 上方遮罩
            if self.selection_start_y > self.image_offset_y:
                self.canvas.create_rectangle(
                    self.image_offset_x, self.image_offset_y,
                    self.image_offset_x + img_width, self.selection_start_y,
                    fill="black", stipple="gray50", tags="selection"
                )
            
            # 下方遮罩
            if self.selection_start_y + self.selection_height < self.image_offset_y + img_height:
                self.canvas.create_rectangle(
                    self.image_offset_x, self.selection_start_y + self.selection_height,
                    self.image_offset_x + img_width, self.image_offset_y + img_height,
                    fill="black", stipple="gray50", tags="selection"
                )
            
            # 左侧遮罩
            if self.selection_start_x > self.image_offset_x:
                self.canvas.create_rectangle(
                    self.image_offset_x, self.selection_start_y,
                    self.selection_start_x, self.selection_start_y + self.selection_height,
                    fill="black", stipple="gray50", tags="selection"
                )
            
            # 右侧遮罩
            if self.selection_start_x + self.selection_width < self.image_offset_x + img_width:
                self.canvas.create_rectangle(
                    self.selection_start_x + self.selection_width, self.selection_start_y,
                    self.image_offset_x + img_width, self.selection_start_y + self.selection_height,
                    fill="black", stipple="gray50", tags="selection"
                )
        
        self.update_vertical_line()
    
    def update_vertical_line(self):
        """更新垂直分割线显示"""
        # 删除旧的垂直线
        self.canvas.delete("vertical_line")
        
        if self.selection_width > 0 and self.selection_height > 0:
            # 绘制垂直分割线
            self.vertical_line = self.canvas.create_line(
                self.vertical_line_x, self.selection_start_y,
                self.vertical_line_x, self.selection_start_y + self.selection_height,
                fill="blue", width=3, tags="vertical_line"
            )
            
            # 添加拖拽手柄
            handle_y = self.selection_start_y + self.selection_height // 2
            self.canvas.create_oval(
                self.vertical_line_x - 5, handle_y - 5,
                self.vertical_line_x + 5, handle_y + 5,
                fill="blue", outline="white", width=2, tags="vertical_line"
            )
    
    def update_info(self):
        """更新信息显示"""
        if self.selection_width > 0 and self.selection_height > 0:
            # 计算原始图像坐标
            orig_x, orig_y = self.canvas_to_image_coords(self.selection_start_x, self.selection_start_y)
            orig_w = self.selection_width / self.scale_factor
            orig_h = self.selection_height / self.scale_factor
            
            # 计算垂直线在选择区域内的相对位置，然后转换为视频坐标
            relative_line_pos = (self.vertical_line_x - self.selection_start_x) / self.selection_width
            # 使用视频宽度计算，与确认时返回的值保持一致
            video_line_x = int(self.video_width * relative_line_pos)
            
            info_text = f"选择区域: {int(orig_w)}×{int(orig_h)} | 垂直线位置: {video_line_x} (在{self.video_width}px视频中)"
            self.info_var.set(info_text)
        else:
            self.info_var.set("请拖拽选择区域")
    

    def reset_vertical_line(self):
        """重置垂直线"""
        self.vertical_line_x = self.selection_start_x + self.selection_width // 2
        self.update_vertical_line()
        self.update_info()


    def reset_selection(self):
        """重置选择"""
        self.init_default_selection()

    
    def confirm(self):
        """确认选择"""
        if self.selection_width <= 0 or self.selection_height <= 0:
            messagebox.showwarning("警告", "请先选择一个区域")
            return
        
        try:
            # 计算原始图像坐标
            orig_x, orig_y = self.canvas_to_image_coords(self.selection_start_x, self.selection_start_y)
            orig_w = self.selection_width / self.scale_factor
            orig_h = self.selection_height / self.scale_factor
            
            # 裁剪图像
            crop_box = (int(orig_x), int(orig_y), int(orig_x + orig_w), int(orig_y + orig_h))
            cropped_image = self.original_image.crop(crop_box)
            
            # 调整到目标视频尺寸
            resized_image = cropped_image.resize((self.video_width, self.video_height), Image.Resampling.LANCZOS)
            
            # 保存为临时文件
            temp_dir = tempfile.gettempdir()
            temp_filename = f"selected_image_{os.getpid()}_{id(self)}.png"
            self.result_image_path = os.path.join(temp_dir, temp_filename)
            resized_image.save(self.result_image_path, "PNG")
            
            # 计算垂直线在选择区域内的相对位置，然后转换为最终图像坐标
            relative_line_pos = (self.vertical_line_x - self.selection_start_x) / self.selection_width
            self.vertical_line_position = int(self.video_width * 0.5) #relative_line_pos)
            
            # 保存用户选择的目标字段
            self.target_field_choice = self.target_field_var.get()
            
            self.dialog_result = "ok"
            self.dialog.destroy()
            
        except Exception as e:
            messagebox.showerror("错误", f"处理图像失败: {str(e)}")
    
    def cancel(self):
        """取消选择"""
        self.dialog_result = "cancel"
        self.dialog.destroy()
    
    def show(self):
        """显示对话框并返回结果"""
        # 等待对话框关闭
        self.dialog.wait_window()
        
        if self.dialog_result == "ok":
            return self.result_image_path, self.vertical_line_position, self.target_field_choice
        else:
            return None, None, None


def show_image_area_selector(parent, source_image_path, video_width, video_height):
    """显示图像区域选择对话框的便捷函数"""
    dialog = ImageAreaSelectorDialog(parent, source_image_path, video_width, video_height)
    return dialog.show()


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python image_area_selector_dialog.py <image_path>")
        sys.exit(1)
    
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    image_path = sys.argv[1]
    video_width = 1920
    video_height = 1080
    
    result_path, line_pos, target_field = show_image_area_selector(root, image_path, video_width, video_height)
    
    if result_path:
        print(f"Selected image saved to: {result_path}")
        print(f"Vertical line position: {line_pos}")
        print(f"Target field: {target_field}")
    else:
        print("User cancelled selection")
    
    root.destroy()
