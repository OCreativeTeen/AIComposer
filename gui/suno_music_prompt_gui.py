import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import uuid
from datetime import datetime
import config
import config_prompt
from project_manager import PROJECT_CONFIG, save_project_config
from utility.llm_api import LLMApi






class SunoMusicPromptGUI:
    """SUNO音乐提示词生成工具 - UI组件"""
    def __init__(self, parent_window):
        """
        初始化SUNO音乐提示词GUI组件
        
        Args:
            parent_window: 父窗口（Tk 或 Toplevel）
        """
        # 创建子窗口
        self.root = tk.Toplevel(parent_window)
        self.root.title("SUNO音乐提示词生成工具")
        self.root.geometry("2000x1000")
        self.root.transient(parent_window)
        
        # Initialize variables
        self.tasks = {}
        
        # 直接从 project_manager 获取项目配置
        self.current_project_config = PROJECT_CONFIG if PROJECT_CONFIG else {}
        self.current_language = self.current_project_config.get('language', 'zh')
        
        self.setup_ui()
        
        self.llm_api = LLMApi()

        # Bind window close event to save config
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Setup the main UI"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create music prompts content directly (no tabs)
        self.create_music_prompts_content(main_frame)
        
        # Status bar
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        # Load initial config values
        self.root.after(300, self.load_initial_config_values)
    
    def load_initial_config_values(self):
        """Load initial config values for music prompts tab"""
        try:
            if not self.current_project_config:
                return
            
            # Load SUNO music prompts configuration
            if hasattr(self, 'suno_language'):
                self.suno_language.set(self.current_project_config.get('suno_language', config_prompt.SUNO_LANGUAGE[0]))
            if hasattr(self, 'suno_expression'):
                self.suno_expression.set(self.current_project_config.get('suno_expression', list(config_prompt.SUNO_CONTENT.keys())[0]))
            if hasattr(self, 'suno_atmosphere'):
                self.suno_atmosphere.set(self.current_project_config.get('music_atmosphere', config_prompt.SUNO_ATMOSPHERE[0]))
            
            # Load structure
            if hasattr(self, 'suno_structure_category'):
                structure_category = self.current_project_config.get('music_structure_category', self.suno_structure_categories[0] if hasattr(self, 'suno_structure_categories') else '')
                self.suno_structure_category.set(structure_category)
                self.on_structure_category_change()
                if hasattr(self, 'suno_structure'):
                    structure = self.current_project_config.get('music_structure_comparison', '')
                    if structure and structure in self.suno_structure['values']:
                        self.suno_structure.set(structure)
            
            # Load melody
            if hasattr(self, 'suno_melody_category'):
                melody_category = self.current_project_config.get('music_melody_category', self.suno_melody_categories[0] if hasattr(self, 'suno_melody_categories') else '')
                self.suno_melody_category.set(melody_category)
                self.on_melody_category_change()
                if hasattr(self, 'suno_leading_melody'):
                    melody = self.current_project_config.get('music_leading_melody', '')
                    if melody and melody in self.suno_leading_melody['values']:
                        self.suno_leading_melody.set(melody)
            
            # Load instruments
            if hasattr(self, 'suno_instruments_category'):
                instruments_category = self.current_project_config.get('music_instruments_category', self.suno_instruments_categories[0] if hasattr(self, 'suno_instruments_categories') else '')
                self.suno_instruments_category.set(instruments_category)
                self.on_instruments_category_change()
                if hasattr(self, 'suno_instruments'):
                    instrument = self.current_project_config.get('music_leading_instruments', '')
                    if instrument and instrument in self.suno_instruments['values']:
                        self.suno_instruments.set(instrument)
            
            # Load rhythm
            if hasattr(self, 'suno_rhythm_category'):
                category = self.current_project_config.get('music_rhythm_groove_category', self.suno_rhythm_categories[0] if hasattr(self, 'suno_rhythm_categories') else '')
                self.suno_rhythm_category.set(category)
                self.on_rhythm_category_change()
                if hasattr(self, 'suno_rhythm'):
                    style = self.current_project_config.get('music_rhythm_groove_style', '')
                    if style and style in self.suno_rhythm['values']:
                        self.suno_rhythm.set(style)
            
            # Load content
            if hasattr(self, 'music_content'):
                self.music_content.delete(1.0, tk.END)
                self.music_content.insert(1.0, self.current_project_config.get('music_json_content', ''))
            
            if hasattr(self, 'music_prompt'):
                self.music_prompt.delete(1.0, tk.END)
                self.music_prompt.insert(1.0, self.current_project_config.get('music_prompt_content', ''))
            
            if hasattr(self, 'music_lyrics'):
                self.music_lyrics.delete(1.0, tk.END)
                self.music_lyrics.insert(1.0, self.current_project_config.get('music_lyrics_content', ''))
                
        except Exception as e:
            print(f"❌ Failed to load initial config values: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def save_project_config(self):
        """保存项目配置（仅音乐提示词相关）"""
        try:
            # 从全局 PROJECT_CONFIG 获取配置
            if not PROJECT_CONFIG:
                return
            
            config_data = PROJECT_CONFIG.copy()
            
            # 保存SUNO音乐提示词配置
            if hasattr(self, 'suno_language'):
                config_data['suno_language'] = self.suno_language.get() or config_data.get('suno_language', config_prompt.SUNO_LANGUAGE[0])
            if hasattr(self, 'suno_expression'):
                config_data['suno_expression'] = self.suno_expression.get() or config_data.get('suno_expression', list(config_prompt.SUNO_CONTENT.keys())[0])
            if hasattr(self, 'suno_atmosphere'):
                config_data['music_atmosphere'] = self.suno_atmosphere.get() or config_data.get('music_atmosphere', config_prompt.SUNO_ATMOSPHERE[0])
            if hasattr(self, 'suno_structure_category'):
                config_data['music_structure_category'] = self.suno_structure_category.get() or config_data.get('music_structure_category', self.suno_structure_categories[0] if hasattr(self, 'suno_structure_categories') else '')
            if hasattr(self, 'suno_structure'):
                config_data['music_structure_comparison'] = self.suno_structure.get() or config_data.get('music_structure_comparison', '')
            if hasattr(self, 'suno_melody_category'):
                config_data['music_melody_category'] = self.suno_melody_category.get() or config_data.get('music_melody_category', self.suno_melody_categories[0] if hasattr(self, 'suno_melody_categories') else '')
            if hasattr(self, 'suno_leading_melody'):
                config_data['music_leading_melody'] = self.suno_leading_melody.get() or config_data.get('music_leading_melody', '')
            if hasattr(self, 'suno_instruments_category'):
                config_data['music_instruments_category'] = self.suno_instruments_category.get() or config_data.get('music_instruments_category', self.suno_instruments_categories[0] if hasattr(self, 'suno_instruments_categories') else '')
            if hasattr(self, 'suno_instruments'):
                config_data['music_leading_instruments'] = self.suno_instruments.get() or config_data.get('music_leading_instruments', '')
            if hasattr(self, 'suno_rhythm_category'):
                config_data['music_rhythm_groove_category'] = self.suno_rhythm_category.get() or config_data.get('music_rhythm_groove_category', self.suno_rhythm_categories[0] if hasattr(self, 'suno_rhythm_categories') else '')
            if hasattr(self, 'suno_rhythm'):
                config_data['music_rhythm_groove_style'] = self.suno_rhythm.get() or config_data.get('music_rhythm_groove_style', '')
            
            if hasattr(self, 'music_content'):
                config_data['music_json_content'] = self.music_content.get(1.0, tk.END).strip() or config_data.get('music_json_content', '')
            if hasattr(self, 'music_prompt'):
                config_data['music_prompt_content'] = self.music_prompt.get(1.0, tk.END).strip() or config_data.get('music_prompt_content', '')
            if hasattr(self, 'music_lyrics'):
                config_data['music_lyrics_content'] = self.music_lyrics.get(1.0, tk.END).strip() or config_data.get('music_lyrics_content', '')
            
            # 更新全局配置
            import project_manager
            project_manager.PROJECT_CONFIG.update(config_data)
            
            # 保存到文件
            pid = config_data.get('pid')
            if pid:
                save_project_config()
                self.current_project_config = config_data
                print(f"✅ 项目配置已保存: {pid}")
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")
    
    def on_closing(self):
        """窗口关闭时的处理"""
        self.save_project_config()
        self.root.destroy()
    
    def on_project_config_change(self, event=None):
        """项目配置改变时的处理"""
        # 自动保存配置
        self.root.after(100, self.save_project_config)
    
    def log_to_output(self, output_widget, message):
        """Add message to output text area"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        output_widget.see(tk.END)
    
    def get_pid(self):
        """Get current project ID"""
        return self.current_project_config.get('pid', '') if self.current_project_config else ''
    
    def get_language(self):
        """Get current language"""
        return self.current_language
    
    def get_channel(self):
        """Get current channel"""
        return self.current_project_config.get('channel', '') if self.current_project_config else ''
        
    def create_music_prompts_content(self, parent):
        """Create music prompts generation content"""
        # Music Prompts Configuration Section
        music_frame = ttk.LabelFrame(parent, text="SUNO音乐提示词配置", padding="10")
        music_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Container frame for text area and input fields
        inputs_container = ttk.Frame(music_frame)
        inputs_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Text area for music_style on the left
        text_area_frame = ttk.LabelFrame(inputs_container, text="音乐风格", padding="5")
        text_area_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        
        # Scrollbar for text area (pack first to ensure it's on the right)
        text_scrollbar = ttk.Scrollbar(text_area_frame, orient=tk.VERTICAL)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.music_style = tk.Text(text_area_frame, width=80, height=10, wrap=tk.WORD,
                                   yscrollcommand=text_scrollbar.set)
        self.music_style.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure scrollbar command
        text_scrollbar.config(command=self.music_style.yview)
        
        # Input fields frame - organized in rows
        inputs_frame = ttk.Frame(inputs_container)
        inputs_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Row 1: Target and Topic
        row1_frame = ttk.Frame(inputs_frame)
        row1_frame.pack(fill=tk.X, pady=2)
        
        # Target input
        ttk.Label(row1_frame, text="语言:").pack(side=tk.LEFT)
        self.suno_language = ttk.Combobox(row1_frame, values=config_prompt.SUNO_LANGUAGE, state="normal", width=30)
        self.suno_language.set(config_prompt.SUNO_LANGUAGE[0])
        self.suno_language.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_language.bind('<FocusOut>', self.on_project_config_change)
        self.suno_language.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Overall Atmosphere input
        ttk.Label(row1_frame, text="内容:").pack(side=tk.LEFT)
        self.suno_expression = ttk.Combobox(row1_frame, values=list(config_prompt.SUNO_CONTENT.keys()), state="normal", width=30)
        self.suno_expression.set(list(config_prompt.SUNO_CONTENT.keys())[0])
        self.suno_expression.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_expression.bind('<FocusOut>', self.on_project_config_change)
        self.suno_expression.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Overall Atmosphere input
        ttk.Label(row1_frame, text="氛围:").pack(side=tk.LEFT)
        self.suno_atmosphere = ttk.Combobox(row1_frame, values=config_prompt.SUNO_ATMOSPHERE, state="normal", width=30)
        self.suno_atmosphere.set(config_prompt.SUNO_ATMOSPHERE[0])
        self.suno_atmosphere.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_atmosphere.bind('<FocusOut>', self.on_project_config_change)
        self.suno_atmosphere.bind('<<ComboboxSelected>>', self.on_project_config_change)

        
        # Row 2: Structure - 2-level selection
        row2_frame = ttk.Frame(inputs_frame)
        row2_frame.pack(fill=tk.X, pady=2)

        # Structure Category input
        ttk.Label(row2_frame, text="结构:").pack(side=tk.LEFT)
        self.suno_structure_categories = [list(structure.keys())[0] for structure in config_prompt.SUNO_STRUCTURE]
        self.suno_structure_category = ttk.Combobox(row2_frame, values=self.suno_structure_categories, state="normal", width=30)
        self.suno_structure_category.set(self.suno_structure_categories[0])
        self.suno_structure_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_structure_category.bind('<<ComboboxSelected>>', self.on_structure_category_change)
        self.suno_structure_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Structure input (dependent on category)
        ttk.Label(row2_frame, text="结构-").pack(side=tk.LEFT)
        self.suno_structure = ttk.Combobox(row2_frame, values=[], state="normal", width=30)
        self.suno_structure.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_structure.bind('<FocusOut>', self.on_project_config_change)
        self.suno_structure.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Melody Category input
        ttk.Label(row2_frame, text="旋律:").pack(side=tk.LEFT)
        self.suno_melody_categories = [list(melody.keys())[0] for melody in config_prompt.SUNO_MELODY]
        self.suno_melody_category = ttk.Combobox(row2_frame, values=self.suno_melody_categories, state="normal", width=30)
        self.suno_melody_category.set(self.suno_melody_categories[0])
        self.suno_melody_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_melody_category.bind('<<ComboboxSelected>>', self.on_melody_category_change)
        self.suno_melody_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Melody input (dependent on category)
        ttk.Label(row2_frame, text="旋律-").pack(side=tk.LEFT)
        self.suno_leading_melody = ttk.Combobox(row2_frame, values=[], state="normal", width=30)
        self.suno_leading_melody.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_leading_melody.bind('<FocusOut>', self.on_project_config_change)
        self.suno_leading_melody.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Row 3:
        row3_frame = ttk.Frame(inputs_frame)
        row3_frame.pack(fill=tk.X, pady=2)

        # Leading Instruments input - 2-level selection
        ttk.Label(row3_frame, text="乐器:").pack(side=tk.LEFT)
        self.suno_instruments_categories = [list(instrument.keys())[0] for instrument in config_prompt.SUNO_INSTRUMENTS]
        self.suno_instruments_category = ttk.Combobox(row3_frame, values=self.suno_instruments_categories, state="normal", width=30)
        self.suno_instruments_category.set(self.suno_instruments_categories[0])
        self.suno_instruments_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_instruments_category.bind('<<ComboboxSelected>>', self.on_instruments_category_change)
        self.suno_instruments_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Instruments input (dependent on category)
        ttk.Label(row3_frame, text="乐器-").pack(side=tk.LEFT)
        self.suno_instruments = ttk.Combobox(row3_frame, values=[], state="normal", width=30)
        self.suno_instruments.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_instruments.bind('<FocusOut>', self.on_project_config_change)
        self.suno_instruments.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # Rhythm Groove Category input
        ttk.Label(row3_frame, text="律动:").pack(side=tk.LEFT)
        self.suno_rhythm_categories = [list(groove.keys())[0] for groove in config_prompt.SUNO_RHYTHM_GROOVE]
        self.suno_rhythm_category = ttk.Combobox(row3_frame, values=self.suno_rhythm_categories, state="normal", width=30)
        self.suno_rhythm_category.set(self.suno_rhythm_categories[0])
        self.suno_rhythm_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_rhythm_category.bind('<<ComboboxSelected>>', self.on_rhythm_category_change)
        self.suno_rhythm_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Rhythm Groove Style input (dependent on category)
        ttk.Label(row3_frame, text="律动-").pack(side=tk.LEFT)
        self.suno_rhythm = ttk.Combobox(row3_frame, values=[], state="normal", width=30)
        self.suno_rhythm.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_rhythm.bind('<FocusOut>', self.on_project_config_change)
        self.suno_rhythm.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # Button frame - placed below comboboxes in inputs_frame
        button_frame = ttk.Frame(inputs_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(button_frame, text="生SUNO提示 2222", 
                  command=lambda: self.generate_music_prompt(False)).pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="生SUNO歌词 1111", 
                  command=self.concise_music_lyrics).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(button_frame, text="保存音乐风格", 
                  command=self.save_music_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清空内容", 
                  command=self.clear_music_prompts).pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Refine", 
                  command=self.refine_music_prompt).pack(side=tk.LEFT, padx=(0, 5))


        
        # Initialize the style comboboxes with the first category's values
        self.on_structure_category_change()
        self.on_melody_category_change()
        self.on_instruments_category_change()
        self.on_rhythm_category_change()
        
        # Content areas frame - side by side layout
        content_areas_frame = ttk.Frame(music_frame)
        content_areas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        content_areas_frame.grid_columnconfigure(0, weight=1)  # left_frame weight
        content_areas_frame.grid_columnconfigure(1, weight=1)  # prompt_frame weight
        content_areas_frame.grid_columnconfigure(2, weight=2)  # lyrics_frame weight (wider, 2x)
        
        # Left side - Original content area
        left_frame = ttk.LabelFrame(content_areas_frame, text="音乐内容构建/提示", padding="5")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        
        # Content explanation - Combobox and button in same row
        content_info_frame = ttk.Frame(left_frame)
        content_info_frame.pack(fill=tk.X, pady=(0, 5))
        
        content_info_var = tk.StringVar()
        content_info = ttk.Combobox(content_info_frame, textvariable=content_info_var, 
                                    font=('TkDefaultFont', 9), state="readonly", width=50)
        
        # Set options from config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT
        enhance_options = [f"选项 {i+1}: {example[:50]}..." if len(example) > 50 
                                                else f"示例 {i+1}: {example}" 
                                                for i, example in enumerate(config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT)]
        content_info['values'] = enhance_options
        content_info.set("选择内容增强提示词...")
        content_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Insert button - append selected content to self.music_content, placed right after combobox
        def insert_to_music_content():
            selected_index = content_info.current()
            if selected_index >= 0 and selected_index < len(config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT):
                selected_content = config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT[selected_index] + "\n>>>>\n"
                # Append to music_content
                cursor_pos = self.music_content.index(tk.INSERT)
                self.music_content.insert(cursor_pos, selected_content)
            
        copy_btn = ttk.Button(content_info_frame, text="插入", command=insert_to_music_content)
        copy_btn.pack(side=tk.LEFT, padx=(0, 0))


        # Example selection frame
        example_frame = ttk.Frame(left_frame)
        example_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(example_frame, text="示例内容:", font=('TkDefaultFont', 9)).pack(side=tk.LEFT, padx=(0, 5))
        
        # Example selection combobox
        self.music_example_var = tk.StringVar()
        self.music_example_combobox = ttk.Combobox(example_frame, textvariable=self.music_example_var, 
                                                  state="normal", width=50)
        
        # Set example options from config
        example_options = ["选择示例内容..."] + [f"示例 {i+1}: {example[:50]}..." if len(example) > 50 
                                                else f"示例 {i+1}: {example}" 
                                                for i, example in enumerate(config_prompt.SUNO_CONTENT_EXAMPLES)]
        self.music_example_combobox['values'] = example_options
        self.music_example_combobox.set("选择示例内容...")
        self.music_example_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.music_example_combobox.bind('<<ComboboxSelected>>', self.on_music_example_selected)
        
        # Insert button - placed right after combobox
        ttk.Button(example_frame, text="插入", 
                  command=self.insert_selected_music_example).pack(side=tk.LEFT, padx=(0, 0))
        

        self.music_content = scrolledtext.ScrolledText(left_frame, height=12, wrap=tk.WORD)
        self.music_content.pack(fill=tk.BOTH, expand=True)
        self.music_content.bind('<FocusOut>', self.on_project_config_change)
        
        # Music prompt - directly child of content_areas_frame
        prompt_frame = ttk.LabelFrame(content_areas_frame, text="SUNO-AI 提示词", padding="5")
        prompt_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 2))
        prompt_frame.grid_rowconfigure(1, weight=1)
        
        self.music_prompt = scrolledtext.ScrolledText(prompt_frame, height=12, wrap=tk.WORD)
        self.music_prompt.grid(row=1, column=0, sticky="nsew")
        self.music_prompt.bind('<FocusOut>', self.on_project_config_change)

        # Music lyrics - directly child of content_areas_frame
        lyrics_frame = ttk.LabelFrame(content_areas_frame, text="歌词", padding="5")
        lyrics_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 0))
        lyrics_frame.grid_rowconfigure(1, weight=1)
        
        self.music_lyrics = scrolledtext.ScrolledText(lyrics_frame, height=12, wrap=tk.WORD)
        self.music_lyrics.grid(row=1, column=0, sticky="nsew")
        self.music_lyrics.bind('<FocusOut>', self.on_project_config_change)
        
        # Output area
        output_frame = ttk.LabelFrame(parent, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.music_output = scrolledtext.ScrolledText(output_frame, height=10)
        self.music_output.pack(fill=tk.BOTH, expand=True)
    
    def on_structure_category_change(self, event=None):
        """Handle structure category selection change"""
        if hasattr(self, 'suno_structure_category') and hasattr(self, 'suno_structure'):
            selected_category = self.suno_structure_category.get()
            # Find the corresponding structure object in SUNO_STRUCTURE
            for structure in config_prompt.SUNO_STRUCTURE:
                if selected_category in structure:
                    structures = structure[selected_category]
                    self.suno_structure['values'] = structures
                    if structures:
                        self.suno_structure.set(structures[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_melody_category_change(self, event=None):
        """Handle melody category selection change"""
        if hasattr(self, 'suno_melody_category') and hasattr(self, 'suno_leading_melody'):
            selected_category = self.suno_melody_category.get()
            # Find the corresponding melody object in SUNO_MELODY
            for melody in config_prompt.SUNO_MELODY:
                if selected_category in melody:
                    melodies = melody[selected_category]
                    self.suno_leading_melody['values'] = melodies
                    if melodies:
                        self.suno_leading_melody.set(melodies[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_instruments_category_change(self, event=None):
        """Handle instruments category selection change"""
        if hasattr(self, 'suno_instruments_category') and hasattr(self, 'suno_instruments'):
            selected_category = self.suno_instruments_category.get()
            # Find the corresponding instrument object in SUNO_INSTRUMENTS
            for instrument in config_prompt.SUNO_INSTRUMENTS:
                if selected_category in instrument:
                    instruments = instrument[selected_category]
                    self.suno_instruments['values'] = instruments
                    if instruments:
                        self.suno_instruments.set(instruments[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_rhythm_category_change(self, event=None):
        """Handle rhythm groove category selection change"""
        if hasattr(self, 'suno_rhythm_category') and hasattr(self, 'suno_rhythm'):
            selected_category = self.suno_rhythm_category.get()
            # Find the corresponding groove object in SUNO_RHYTHM_GROOVE
            for groove in config_prompt.SUNO_RHYTHM_GROOVE:
                if selected_category in groove:
                    styles = groove[selected_category]
                    self.suno_rhythm['values'] = styles
                    if styles:
                        self.suno_rhythm.set(styles[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_music_example_selected(self, event=None):
        """Handle music example selection change"""
        # No need to do anything on selection, user will click insert button
        pass
    
    def insert_selected_music_example(self):
        """Insert selected music example into the music content text area"""
        if not hasattr(self, 'music_example_combobox') or not hasattr(self, 'music_content'):
            return
            
        selected = self.music_example_combobox.get()
        if selected == "选择示例内容..." or not selected:
            return
        
        try:
            # Extract the example index from the selection
            if selected.startswith("示例 "):
                example_num = int(selected.split(":")[0].replace("示例 ", "")) - 1
                if 0 <= example_num < len(config_prompt.SUNO_CONTENT_EXAMPLES):
                    example_content = config_prompt.SUNO_CONTENT_EXAMPLES[example_num]
                    
                    # Get current cursor position
                    cursor_pos = self.music_content.index(tk.INSERT)
                    
                    # Insert the example content at cursor position
                    self.music_content.insert(cursor_pos, example_content)
                    
                    # Reset combobox selection
                    self.music_example_combobox.set("选择示例内容...")
                    
                    # Trigger config save
                    self.on_project_config_change()
                    
                    self.log_to_output(self.music_output, f"📝 已插入示例内容: 示例 {example_num + 1}")
        except (ValueError, IndexError) as e:
            self.log_to_output(self.music_output, f"❌ 插入示例内容时出错: {str(e)}")
    

    def generate_music_prompt(self, is_lyrics=False):
        try:
            # Generate music prompts using workflow
            system_prompt = self.music_content.get(1.0, tk.END).strip()
            user_prompt = self.music_prompt.get(1.0, tk.END).strip()
            
            music_prompt = self.llm_api.generate_text(system_prompt, user_prompt)

            if music_prompt:
                # 使用默认参数捕获变量值，避免闭包问题
                self.root.after(0, lambda mp=music_prompt: self.music_prompt.delete(1.0, tk.END))
                self.root.after(0, lambda mp=music_prompt: self.music_prompt.insert(1.0, mp))
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "生成音乐提示词失败：未获得有效响应"))
                return

            self.status_var.set("就绪")
            
            # Auto-save the configuration
            self.root.after(100, self.save_project_config)
            # Show success message in main thread
            self.root.after(0, lambda: messagebox.showinfo("成功", f"SUNO音乐提示词生成完成！"))
            
        except Exception as e:
            error_msg = str(e)
            self.log_to_output(self.music_output, f"❌ SUNO音乐提示词生成失败: {error_msg}")
            self.status_var.set("发生错误")
            # Show error message in main thread
            self.root.after(0, lambda: messagebox.showerror("错误", f"SUNO音乐提示词生成失败: {error_msg}"))
    

    def save_music_style(self):
        language = self.suno_language.get() 
        expression = self.suno_expression.get()
        # Get new parameters
        atmosphere = self.suno_atmosphere.get()
        structure = self.suno_structure.get()
        leading_melody = self.suno_leading_melody.get()
        instruments = self.suno_instruments.get()
        rhythm_groove = self.suno_rhythm.get()
        
        # Confirm generation
        instruments_category = self.suno_instruments_category.get()
        confirm_msg = f"确定要生成SUNO音乐提示词吗？\n\n音乐类型: {language}"
        if instruments_category and instruments:
            confirm_msg += f"\n乐器类别: {instruments_category}\n具体乐器: {instruments}"
        elif instruments:
            confirm_msg += f"\n乐器: {instruments}"
        if not messagebox.askyesno("确认生成", confirm_msg):
            return

        """Save music prompts configuration"""
        suno_style_prompt = config_prompt.SUNO_STYLE_PROMPT.format(
            target=language,
            atmosphere=atmosphere,
            expression=expression+" ("+config_prompt.SUNO_CONTENT[expression]+")",
            structure=structure,
            melody=leading_melody,
            instruments=instruments,
            rhythm=rhythm_groove
        )
        self.root.after(0, lambda: self.music_style.delete(1.0, tk.END))
        self.root.after(0, lambda: self.music_style.insert(1.0, suno_style_prompt))
    


    def refine_music_prompt(self):
        """Refine and reorganize the music prompt content using LLM"""
        current_content = self.music_prompt.get(1.0, tk.END).strip()
        if not current_content:
            messagebox.showwarning("警告", "提示词内容为空，无法优化")
            return
        
        def run_refine():
            try:
                self.status_var.set("优化提示词中...")
                self.log_to_output(self.music_output, "🔄 开始优化提示词...")
                
                system_prompt = """You are a professional music prompt organizer. Your task is to make the music prompt more concise (try to keep it less than 1000 characters) and impactful while preserving the core meaning and emotional essence. 
Remove redundant words and phrases, but keep all important information and maintain the music prompt flow. 
Output the concise version of the music prompt."""

                refined_content = self.llm_api.generate_text(system_prompt, current_content)
                
                if refined_content:
                    # 使用默认参数捕获变量值，避免闭包问题
                    refined_text = refined_content.strip()
                    self.root.after(0, lambda: self.music_prompt.delete(1.0, tk.END))
                    self.root.after(0, lambda rt=refined_text: self.music_prompt.insert(1.0, rt))
                    self.root.after(0, lambda: self.on_project_config_change())
                    self.status_var.set("就绪")
                    self.log_to_output(self.music_output, "✅ 提示词优化完成")
                    self.root.after(0, lambda: messagebox.showinfo("成功", "提示词优化完成！"))
                else:
                    self.status_var.set("发生错误")
                    self.log_to_output(self.music_output, "❌ 提示词优化失败：未获得有效响应")
                    self.root.after(0, lambda: messagebox.showerror("错误", "提示词优化失败：未获得有效响应"))
                    
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.music_output, f"❌ 提示词优化失败: {error_msg}")
                self.status_var.set("发生错误")
                self.root.after(0, lambda: messagebox.showerror("错误", f"提示词优化失败: {error_msg}"))
        
        thread = threading.Thread(target=run_refine)
        thread.daemon = True
        thread.start()
    
    
    def concise_music_lyrics(self):
        """Make the music lyrics content more concise using LLM"""
        current_lyrics = self.music_lyrics.get(1.0, tk.END).strip()
        if not current_lyrics:
            messagebox.showwarning("警告", "歌词起始内容为空，无法进行生成")
            return
        
        try:
            language = self.suno_language.get()
            music_styles = self.music_style.get(1.0, tk.END).strip()
            music_prompt = self.music_prompt.get(1.0, tk.END).strip()
            if music_prompt:
                music_styles = music_styles + "\n\n***\n" + music_prompt

            system_prompt = config_prompt.SUNO_LYRICS_SYSTEM_PROMPT.format(suno_lang=language, music_styles=music_styles)
            lyrics_prompt = self.llm_api.generate_text(system_prompt, current_lyrics)
            
            if lyrics_prompt:
                lyrics_text = lyrics_prompt.strip()
                self.root.after(0, lambda: self.music_lyrics.delete(1.0, tk.END))
                self.root.after(0, lambda lt=lyrics_text: self.music_lyrics.insert(1.0, lt))
                self.root.after(0, lambda: self.on_project_config_change())
                self.status_var.set("就绪")
                self.log_to_output(self.music_output, "✅ 歌词精简完成")
                self.root.after(0, lambda: messagebox.showinfo("成功", "歌词精简完成！"))
            else:
                self.status_var.set("发生错误")
                self.log_to_output(self.music_output, "❌ 歌词精简失败：未获得有效响应")
                self.root.after(0, lambda: messagebox.showerror("错误", "歌词精简失败：未获得有效响应"))
                
        except Exception as e:
            error_msg = str(e)
            self.log_to_output(self.music_output, f"❌ 歌词精简失败: {error_msg}")
            self.status_var.set("发生错误")
            self.root.after(0, lambda: messagebox.showerror("错误", f"歌词精简失败: {error_msg}"))



    def clear_music_prompts(self):
        """Clear music prompts configuration"""
        self.suno_language.set(config_prompt.SUNO_LANGUAGE[0])
        self.suno_expression.set(list(config_prompt.SUNO_CONTENT.keys())[0])
        self.suno_atmosphere.set(config_prompt.SUNO_ATMOSPHERE[0])
        
        # Reset structure to first category and first structure
        if hasattr(self, 'suno_structure_category'):
            self.suno_structure_category.set(self.suno_structure_categories[0])
            self.on_structure_category_change()
        
        # Reset melody to first category and first melody
        if hasattr(self, 'suno_melody_category'):
            self.suno_melody_category.set(self.suno_melody_categories[0])
            self.on_melody_category_change()
        
        # Reset instruments to first category and first instrument
        if hasattr(self, 'suno_instruments_category'):
            self.suno_instruments_category.set(self.suno_instruments_categories[0])
            self.on_instruments_category_change()
        
        # Reset rhythm to first category and first rhythm
        if hasattr(self, 'suno_rhythm_category'):
            self.suno_rhythm_category.set(self.suno_rhythm_categories[0])
            self.on_rhythm_category_change()
        
        self.music_content.delete(1.0, tk.END)
        self.music_prompt.delete(1.0, tk.END)
        self.music_lyrics.delete(1.0, tk.END)
        self.on_project_config_change()
        self.log_to_output(self.music_output, f"🗑️ SUNO音乐提示词配置已清空")

