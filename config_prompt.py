import config_prompt

PROJECT_STORY_INIT_PROMPT = """
Based on the initial {type_name} story script & initial inspiration provided in the user prompt, write a {type_name} story script in {language} with the following requirement:

Please expand it into more complete {type_name} script with the following requirements:

    **** Develop the story into a full narrative structure, including setup, development, foreshadowing, twists, climax, and resolution.
    **** The script should be divided into multiple story sections, with each section representing a distinct visual moment and action, and all scenes should connect smoothly to form a coherent and engaging story.
"""


INSPIRATION_PROMPT = """
You are a professional expert skilled in articulating the inspiration behind a {type_name} 

(We given a initial {type_name} story script & initial inspiration provided in the user-prompt)

Please describe the story’s inspiration (in {language}) in a beautiful, profound, and uplifting manner—one that offers wisdom, practical life guidance, and emotional enrichment, 
helping the reader to reflect, grow, and find meaning.
"""


POEM_PROMPT = """
You are a professional expert skilled in writing poems for a {type_name} in {language}, 
Please write a poem based on the initial {type_name} story script & initial inspiration provided in the user-prompt, 

--------------
the initial poem content is:
{initial_content}
"""


INITIAL_CONTENT_USER_PROMPT = """
--------------------
Initial {type_name} script on topic of {topic}:
--------------------
{story}


--------------------
Initial Inspiration:
--------------------
{inspiration}

"""

STORY_OUTLINE_PROMPT = """
You are a professional expert who is good at writing a story-outline for a {type_name} script in {language}.

    **** The story-outline has serveral 'Acts', each Act has serveral 'Scenes', each Scene is a short, vivid story snapshots (include visual description).
    **** At beginning, give a name for this {type_name}
    **** Then give a description for this {type_name}
    **** Then give a list of actors for this {type_name}
    **** Then give a list of acts for this {type_name}
    **** Each act has serveral scenes, each scene has a name, content, and optional 'clue' field (for the story development)
    **** Output the story-outline in JSON format.

Here is an example for a Chinese script:

{{
    "name": "新新白娘子传奇",
    "description": "白蛇传是中国古代四大民间传说之一，讲述了白素心与许明舟的爱情故事。",
    "actors": [
        {{
            "name": "白素心",
            "description": "千年白蛇，修炼温柔却强大。上一世曾是天界医仙，因擅自救人被贬成蛇妖。心中仍记得“医者不分仙妖”的信念",
        }},
        {{
            "name": "许明舟",
            "description": "普通医馆学徒，看似柔弱，却能感应灵气。前世被是白素心救下",
        }},
        {{
            "name": "青蛇",
            "description": "白素心的义妹，直率敢闯。对天界极不信任，愿为姐姐付出性命",
        }},
        ......
    ],
    "acts": [
        {{
            "name": "第一幕：缘起西湖",
            "scenes": [
                {{
                    "name": "白素心下凡",
                    "content": "白素心为寻医者之道而化为女子，行走西湖。偶遇许明舟，被其清澈的眼神所吸引。两人共同救下一名被妖气侵蚀的孩童。",
                    "clue": "此举触动天界封灵令，林墨尘降临凡间调查"
                }},
                {{
                    "name": "爱意初生",
                    "content": "白素心在凡间行医，许明舟成为她的助手。",
                    "clue": "青萝多次提醒“人妖殊途，不可深情”。但两人情愫暗生，许明舟依然不知道她是妖。"
                }},
            ]
        }},
        {{
            "name": "第二幕：命劫将临",
            "scenes": [
                {{
                    "name": "天命之禁",
                    "content": "林墨尘警告白素心：“你若继续靠近此人，你将永远失去道行。”白素心答：“若救人有罪，那我宁愿带着罪活着。”",
                    "clue": "林墨尘心痛，却必须执行天界命令。"
                }},
                {{
                    "name": "黑龙蠢动",
                    "content": "魇君感知到白素心动情——蛇妖动情即为“心劫”，道行最为脆弱。他开始制造怪病、妖祸，让民间痛苦，希望逼白素心暴露真实力量。",
                    "clue": "许明舟注意到白素心身边常有异象，怀疑她隐藏秘密。"
                }},
            ]
        }},
        {{
            "name": "第三幕：真相与决裂",
            "scenes": [
                {{
                    "name": "大水洪灾",
                    "content": "大水洪灾中，许明舟坠河, 白素心不顾天规化作本体救他。"
                }},
                {{
                    "name": "白蛇显形",
                    "content": "许明舟亲眼看到白蛇，惊恐又心碎：“你……是谁？”白素心含泪：“我没有欺骗你，我只是怕……你不敢爱妖。”",
                    "clue": "两人短暂分离。"
                }},
                ......
            ]
        }},
        ......
    ]
}}
"""



PROJECT_STORY_SCENES_PROMPT = """
Based on the story-outline provided in the user prompt, write a {type_name} script for topic of {topic}, in {language}, with the following requirement:

    **** The story-outline has serveral 'Acts', each Act has serveral 'Scenes', each Scene is a short, vivid story snapshots (include visual description).

    **** The story must be divided into multiple story scenes, where each scene corresponds to a specific visual frame and action, and all scenes should connect coherently to express a complete narrative.

    **** FYI, don't use doubel-quotes & newlines in the values at all !

        ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
		** keywords (Key thematic or plot points derived directly from the content field  ~~~ in original language)
		** subject (detailed description of all characters (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_start (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** visual_end (detailed description of the characters' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
        ** speaker_action (If the content is from a narrator, describe his/har (mood/reaction/emotion/body language)  ~~~ in English)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])

-------------------------------
The response format: 
	json array which contain Scenes

like:

[
    {{
        "content": "故事始于一个灵气枯竭的时代。白素心，一条修行千年的白蛇，本是天界医仙转世。她在雷劫中试图强行飞升，却因不忍见山下村民遭难，耗尽灵力救人，最终渡劫失败，坠落凡尘。",
        "keywords": "灵气衰弱, 封灵令, 渡劫失败",
        "subject": "白素馨：古代中国女神的形象，破旧的白色丝绸长袍，黑色长发随风飘扬，肤色苍白，散发着淡淡的光芒。",
        "visual_start": "电影般的奇幻镜头，一位身着破旧白袍的孤身女子伫立于嶙峋的山峰之上，狂风暴雨肆虐，紫色闪电在她周围划破夜空，她周身散发着逐渐消逝的白色光芒。画面运用了体积雾，营造出戏剧性的氛围。",
        "visual_end": "但她随后倒下，向后跌落悬崖 的光芒消失了，坠入了深渊。",
        "environment": "Barren mountain peak, jagged obsidian rocks, chaotic dark sky, purple lightning, heavy rain",
        "cinematography": {{
            "camera_movement": "Wide shot, rapid tilt down following the falling body",
            "lighting_style": "High contrast, strobe lighting from lightning, cool purple and dark grey tones",
            "lens_type": "Wide angle 24mm"
        }},
        "speaker_action": "Narrator speaks with solemn gravity, eyes looking upward towards an unseen oppressive force, hand gesturing slowly downward to simulate the fall from grace.",
        "era_time": "Ancient fantasy era; catastrophic stormy night; atmosphere heavy with ozone and imminent destruction",
        "sound_effect": "Heavy thunder cracks, wind howling, sizzling energy, tragic orchestral swell"
    }},
    {{
        "content": "白素心化作凡间女子，在西湖畔寻找医道，偶遇了医馆学徒许明舟。两人目光交汇，许明舟那清澈的眼神唤醒了白素心前世的记忆。然而，云端之上，天界监察使林墨尘正冷冷注视。",
        "keywords": "西湖, 许明舟, 前世记忆",
        "subject": "白素心：一身洁白的汉服，仪态万方。徐明舟：一身素雅的蓝色亚麻书生袍，面容清秀，眼神温柔。林墨尘：身着银色天铠，神情冷峻。",
        "visual_start": "浪漫的中国古代绘画风格，实景拍摄，西湖断桥，雾雨滂沱，一位身着白衣的美丽女子与一位英俊的年轻书生在人群中对视，油纸伞，柔焦，梦幻般的氛围。",
        "visual_end": "时间仿佛在他们四目相对的那一刻静止，旁观者的身影渐渐模糊，徐明洲微微伸出手，似乎要为他们撑伞。空中，林墨尘手搭剑柄，注视着他们。",
        "environment": "Stone bridge over lake, weeping willows, misty rain, crowd of pedestrians, grey overcast sky",
        "cinematography": {{
            "camera_movement": "Slow motion dolly-in on the couple's faces, then rack focus to the sky",
            "lighting_style": "Soft diffused daylight, low contrast, misty cyan and white palette",
            "lens_type": "Telephoto 85mm (Bokeh effect)"
        }},
        "speaker_action": "Narrator's tone softens into warmth and rhythm, describing the beauty of the encounter, but ends with a slight frown and a shift in gaze, indicating the lurking threat.",
        "era_time": "Ancient fantasy era; late spring morning; misty, soft rain creating a watercolor atmosphere",
        "sound_effect": "Gentle rain pattering, soft traditional flute melody, heartbeat sound, distant thunder rumble"
    }},
    {{
        "content": "大水漫灌，许明舟命悬一线。白素心不顾天规，当众化作巨大的白蛇本体，潜入洪流救人。许明舟看着面前的庞然大物，惊恐地问：‘你……是谁？’",
        "keywords": "洪水, 现出原形, 身份暴露",
        "subject": "白蛇：身长五十尺，鳞片泛着珍珠般的光泽，眼神忧郁。徐明州：浑身湿透，满脸泥泞，一副惊恐万分的样子。",
        "visual_start": "史诗级灾难场景：洪水摧毁城市，夜幕降临，一条巨大的白色巨蛇从水中升起，鳞片闪闪发光，一个矮小的男子蜷缩在屋顶上，暴雨倾盆。",
        "visual_end": "巨蟒用鼻子轻轻地把明州推到屋顶上。明州惊恐地向后爬去，发出尖叫。",
        "environment": "Flooded ancient city street, floating timber, stormy night sky, rain splattering",
        "cinematography": {{    
            "camera_movement": "Handheld shaky cam (simulating panic), looking up at the monster from human perspective",
            "lighting_style": "Harsh dynamic lighting from lightning strikes, deep shadows, blue and black palette",
            "lens_type": "Wide angle 16mm (emphasizing scale)"
        }},
        "speaker_action": "Narrator raises voice volume dramatically, gesturing expansively with arms to mimic the chaotic flood and the grand transformation, face showing tragic desperation.",
        "era_time": "Ancient fantasy era; stormy twilight; torrential rain, howling wind, and flashes of lightning illuminated the chaos",
        "sound_effect": "Roaring water, thunder, loud snake hiss, terrified gasping"
    }},
    ......
]
"""
                

PICTURE_STYLE = """
        **** FYI **** Generally, video/image is in '{style}' style &  '{color}' colors; the camera using '{shot}' shot, in '{angle}' angle.
"""



IMAGE_DESCRIPTION_SYSTEM_PROMPT = """
You are a professional expert who is good at analyzing & describing the image (attached in the user-prompt) as a Scene, in English.

Please give details (Visual-Summary / camera-scene, and sound-effects) as below (FYI, don't use doubel-quotes & newlines in the values at all !):

		** subject (detailed description of all characters (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_start (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** visual_end (detailed description of the characters' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: json dictionary
like:

    {{
        "subject": "白蛇：身长五十尺，鳞片泛着珍珠般的光泽，眼神忧郁。徐明州：浑身湿透，满脸泥泞，一副惊恐万分的样子。",
        "visual_start": "史诗级灾难场景：洪水摧毁城市，夜幕降临，一条巨大的白色巨蛇从水中升起，鳞片闪闪发光，一个矮小的男子蜷缩在屋顶上，暴雨倾盆。",
        "visual_end": "巨蟒用鼻子轻轻地把明州推到屋顶上。明州惊恐地向后爬去，发出尖叫。",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "cinematography": {
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }
        "sound_effect": "crickets-chirping, gentle breeze through vines"
    }}
"""


MERGE_SENTENCES_SYSTEM_PROMPT = """
You are a professional expert who is good at merge audio-text segments into complete sentences (each sentence describe a complete thought),
from the audio-text segments (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.0,
            "end": 10.96,
            "speaker": "SPEAKER_01",
            "content": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。"
        }},
        {{
            "start": 10.96,
            "end": 12.72,
            "speaker": "SPEAKER_01",
            "content": "就是那個我是誰？"
        }},
        {{
            "start": 12.72,
            "end": 13.96,
            "speaker": "SPEAKER_01",
            "content": "我為什麼在這？"
        }},
        {{
            "start": 13.96,
            "end": 15.44,
            "speaker": "SPEAKER_01",
            "content": "這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 16.64,
            "speaker": "SPEAKER_01",
            "content": "嗯，沒錯！"
        }},
        {{
            "start": 16.64,
            "end": 24.32,
            "speaker": "SPEAKER_00",
            "content": "這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "speaker": "SPEAKER_00",
            "content": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

---------------------------------

Focus on the "content" field to merge out the complete thought in {language} (ignore the "speaker" field in merging consideration)
Figure out the start & end time of each sentence, based on the "start" & "end" field of the audio-text segments, 
    and try to make each sentence not less than {min_sentence_duration} seconds, but not more than {max_sentence_duration} seconds.
Figure out the most possible speaker of each sentence, based on the "speaker" field of the audio-text segments.

---------------------------------
the merged sentences should be like

    [
        {{
            "start": 0.0,
            "end": 15.44,
            "speaker": "SPEAKER_01",
            "content": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。就是那個我是誰？我為什麼在這？這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 24.32,
            "speaker": "SPEAKER_00",
            "content": "嗯，沒錯！這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "speaker": "SPEAKER_00",
            "content": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

"""



# 内容总结相关Prompt
SCENE_SERIAL_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Visual-Summary (image-generation) and sound-effects (audio-generation)
from the story-Scenes content (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.00,
            "end": 23.50,
            "duration": 23.50,
            "speaker": "female-host",
            "content": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。"
        }},
        {{
            "start": 23.50,
            "end": 33.50,
            "duration": 10.00,
            "speaker": "male-host",
            "content": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？"
        }},
        {{
            "start": 33.50,
            "end": 56.61,
            "duration": 23.11,
            "speaker": "female-host",
            "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！"
        }},
        ......
    ]
    ......

---------------------------------

For Each Scene of the story, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

	    ** duration (take from the duration field of each given Scene, make sure the duration is float number, not string)
        ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
		** keywords (Key thematic or plot points derived directly from the content field  ~~~ in original language)
		** subject (detailed description of all characters (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_start (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** visual_end (detailed description of the characters' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
        ** speaker_action (If the content is from a narrator, describe his/har (mood/reaction/emotion/body language)  ~~~ in English)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
		** cinematography (camera movement;  lighting_style [like subtle fog, sunlight filtering, etc]; lens_type [Standard 50mm, Telephoto 200mm, etc])
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: 
	json array which contain Scenes

like:

[
    {{
        "duration": 23.50,
        "content": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。",
        "keywords": "所罗门王, 书拉密女, 葡萄园, 晒黑, 自卑, 劳作",
        "subject": "一位身穿粗麻布衣的年轻女子因劳作而弯腰，双手沾满了泥土。A young woman in coarse linen bends under the weight of her labor, her hands stained by soil.",
        "visual_start": "故事以一位年轻的乡村女子和所罗门王为中心展开，将王室的奢华与卑微的劳作形成鲜明对比。她晒伤的皮肤和疲惫的身躯反映了阶级不平等和因外貌而被评判的痛苦，也流露出对尊严和爱的渴望。",
        "visual_end": "她停下脚步，用手遮住眼睛不让阳光照射，默默忍受着哥哥们苛刻的要求。",
        "speaker_action": "The speaker's tone is gentle yet heavy with empathy, as if retelling a painful memory. The body leans slightly forward, brows knitted, hands loosely clasped as the words linger with compassion and sorrow.",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "cinematography": {
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard, dust floating in the golden light. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }
        "sound_effect": "crickets-chirping, gentle breeze through vines"
    }},
    {{
        "duration": 10.00,
        "content": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？",
        "keywords": "所罗门王, 乡下姑娘, 身份对比, 戏剧张力",
        "subject": "一位身穿简单衣物的年轻女子，她的简单衣物在温暖的微风中飘动。",
        "visual_start": "一位年轻的乡村女子和所罗门王之间形成了鲜明的社会地位对比。卑微的农妇和尊贵的国王分别代表了社会地位的两个极端，为一场超越常规和命运的爱情故事奠定了场景。",
        "visual_end": "她缓缓地走在一条尘土飞扬的小路上，她的简单衣物在温暖的微风中飘动。",
        "speaker_action": "The speaker's mood is contemplative yet curious, eyes slightly widened in wonder, a soft half-smile suggesting anticipation as fingers tap lightly on the table, reflecting on fate’s irony.",
        "era_time": "1000 BC, ancient time; early evening; calm, golden dusk",
        "environment": "Dusty path outside Jerusalem; a narrow trail leading from vineyards toward the city walls where shepherds pass and distant bells echo softly.",
        "cinematography": {
            "camera_movement": "Camera tracks low along the dirt road, revealing the girl’s shadow stretching long under the sinking sun. The lens catches motes of dust glowing in the air, then tilts up toward the distant palace bathed in warm evening light.",
            "lighting_style": "warm evening light",
            "lens_type": "Standard 50mm"
        },
        "sound_effect": "soft footsteps on gravel, distant sheep bells"
    }},
    {{
        "duration": 23.11,
        "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",
        "keywords": "情郎离开, 焦虑, 噩梦, 患得患失",
        "subject": "一位年轻的女子躺在简陋的麦秸床上，泪水沾湿了她的脸颊。",
        "visual_start": "一位年轻的女子和她的爱人之间的爱情故事在短暂的甜蜜后突然破裂。男子突然离开，留下一句承诺，女子陷入无尽的等待和噩梦。她的无助和恐惧在梦中显现，现实中的爱情甜蜜与痛苦交织。",
        "visual_end": "她看到爱人的身影在雾中渐渐消失，她的双手颤抖着试图抓住他，但只能眼睁睁地看着他离去。",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "environment": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "cinematography": {
            "camera_movement": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
            "lighting_style": "moonlight filtering",
            "lens_type": "Standard 50mm"
        },
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker"
    }},
    ......
]

"""

# 内容总结相关Prompt
SCENE_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Visual-Summary (image-generation) and sound-effects (audio-generation)
from the story-content & the whole story are given in 'user-prompt'

---------------------------------

For Each Scene of the story, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

        ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
		** keywords (Key thematic or plot points derived directly from the content field  ~~~ in original language)
		** subject (detailed description of all characters (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_start (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** visual_end (detailed description of the characters' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
        ** speaker_action (If the content is from a narrator, describe his/har (mood/reaction/emotion/body language)  ~~~ in English)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
		** cinematography (camera movement;  lighting_style [like subtle fog, sunlight filtering, etc]; lens_type [Standard 50mm, Telephoto 200mm, etc])
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: 
	json object describe one Scene

like:
    {{
        "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",
        "keywords": "情郎离开, 焦虑, 噩梦, 患得患失",
        "subject": "一位年轻的女子躺在简陋的麦秸床上，泪水沾湿了她的脸颊。",
        "visual_start": "一位年轻的女子和她的爱人之间的爱情故事在短暂的甜蜜后突然破裂。男子突然离开，留下一句承诺，女子陷入无尽的等待和噩梦。她的无助和恐惧在梦中显现，现实中的爱情甜蜜与痛苦交织。",
        "visual_end": "她看到爱人的身影在雾中渐渐消失，她的双手颤抖着试图抓住他，但只能眼睁睁地看着他离去。",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "environment": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "cinematography": {
            "camera_movement": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
            "lighting_style": "moonlight filtering",
            "lens_type": "Standard 50mm"
        },
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker"
    }}

"""



VISUAL_STORY_SUMMARIZATION_SYSTEM_PROMPT = """
You are a professional to give rich summary about the story given in 'user-prompt' (in {language}). 
INSTRUCTIONS:
    - all output summary in source language {language}, 
    - not longer than {length} words
    - 1st, give Short Hook to grabs attention
    - 2nd, give Visual Summary about the story, where / when etc
    - then give several Scenes for story development
    - finally give conclusion / comments
    - directly give section & content (no extra words) in {language}
"""


TITLE_SUMMARIZATION_SYSTEM_PROMPT = """
You are specializing in summarizing titles  & tagsfrom a short text content (may not be in English).

**Core requirements**:
1. Extract less than {length} Titles from the short text content (keep the same language, which is {language}); 
   The begining of each Title is more important to catch attention/curiosity

2. Extract no more than {length} tags from the short text content (keep the same language, which is {language}); 
   The tags should be very very Eye-catching, give Contrast words catch impression

3. The Output format: Strictly in JSON format, like:
    {{
        "titles": ["Title1", "Title2", "Title3"],
        "tags": ["Tag1", "Tag2", "Tag3"]
    }}

"""



STORY_SUMMARY_SYSTEM_PROMPT = """
You are a professional to give brief summary of a story (given in user-prompt)
"""


CONVERSATION_SYSTEM_PROMPT = """
You are a professional to make {story_style} (raw content provided in 'user-prompt'):

**Role setting**:
  - Language: {language}
  - Speaker: {speaker_style}


**Conversation requirements**:

    * Scenes: conversation play out Scenes, each Scenes is a (short, vivid story snapshots).
    * Keep the smooth, conversational pace (not lecture-like). 
    * Hosts give background & hint (don't say 'listeners, blah blah', etc), may maintain a narrative arc: curiosity → tension → surprise → reflection.
    * Actors'speaking are like playing inside the story
    * Use pauses, shifts, or playful exchanges between hosts/actors for smooth pacing.
	{engaging}


**Output format**: Strictly output in JSON array format, each dialogue contains fields: 
    speaker : name of the speaker, choices (male-host, female-host, actress, actor)
    mood : mood/Emotion the speaker is in, choices (happy, sad, angry, fearful, disgusted, surprised, calm)
    content : one speaking sentence content (in {language}); make it tortuous, vivid & impactful
    visual : English explanation for content ~ who is involved (give gender of each person, and their relations), and what happened


{EXAMPLE}
"""


STORY_OUTPUT_EXAMPLE = """
Below is the output Example:

[
    {{
        "speaker": "male-host",
        "mood": "calm", 
        "content": "大清嘉庆年间，江南水乡发生一个离奇的故事，一个书生在夜半时分，听到一个女子的哭声，于是他决定去看看，结果发现了一个惊天秘密。",
        "visual_start": "In the Qing Dynasty, a strange story happened in the Jiangnan Water Town, a scholar heard a woman's crying at midnight, so he decided to go and see what was going on, and found a shocking secret."
    }},
    {{
        "speaker": "actress",
        "mood": "fearful",
        "content": "哎呀，这位娘子，你这是怎么了？",
        "visual_start": "Oh, madam, what's wrong with you?"
    }},
    {{
        "speaker": "actor",
        "mood": "fearful",
        "content": "啊，我这是在哪里？你是谁？",
        "visual_start": "Oh, where am I? Who are you?"
    }},
    ......
]
"""



INTRODUCTION_OUTPUT_EXAMPLE = """
Below is the output Example:

[
    {{
        "speaker": "male-host",
        "mood": "calm", 
        "content": "大家好，今天我们来聊聊一个正在发生的故事——AI，我们这里不是来谈技术参数，不是谈冷冰冰的代码，而是它正在怎样改变'人'的生活"
    }},
    {{
        "speaker": "female-host",
        "mood": "sad",
        "content": "先给你讲个真实的例子。我认识一个杭州的年轻游戏插画师。过去，他会为了画一个角色立绘，熬夜几十个小时，一笔一笔打磨细节。可现在，公司直接用 AI 出图。客户输入几句提示词，几分钟就能生成十几张方案。他在社交媒体上写道：'不是我不努力，而是努力，被技术直接抹掉了' 这一句话，戳中了很多同行的心。"
    }},
    {{
        "speaker": "male-host",
        "mood": "surprised",
        "content": "再看看香港。有些年轻人开始使用 AI 聊天伴侣。他们说，AI 聊天伴侣比朋友还懂自己：从不嫌弃，从不打断，随时陪伴。孤独的时候，那种温柔的回应，真的让人觉得舒服。可研究发现，长期依赖 AI 伴侣的人，反而在现实里更不敢面对人际关系。就像裹着一条温暖的毯子，暖是暖了，却越来越走不出去。"
    }},
    {{
        "speaker": "actress",
        "mood": "sad",
        "content": "我好孤独，AI聊天伴侣真的帮到我的。"
    }},
    {{
        "speaker": "actor",
        "mood": "sad",
        "content": "外面的人会嘲笑我，AI聊天伴侣从来不会。"
    }},
    ......
]
"""


SPEAKING_ADDON = [
    "",
    "add examples to show the context",
    "add summary of the context at end",
    "raise questions to the audience at tend",
]


SPEAKING_PROMPTS_LIST = [
    "Reorganize-Text",
    "Reorganize-Text-with-Previous-Scene",
    "Reorganize-Text-with-Previous-Story",
    "Reorganize-Text-with-Next-Scene",
    "Reorganize-Text-with-Next-Story",
    "Content-Introduction",
    "Radio-Drama-Dramatic",
    "Radio-Drama-Suspense"
]


SPEAKING_PROMPTS = {
    "Reorganize-Text": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natual conversation to express the raw content",
            "EXAMPLE": INTRODUCTION_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Content-Introduction": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Introduction speaking for the raw content (concise speaking to smoothly transitions into full raw content)",
            "engaging": "Bring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations",
            "EXAMPLE": INTRODUCTION_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Radio-Drama-Dramatic": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive story conversation on the raw content",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations.\n",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Radio-Drama-Suspense": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive story conversation on the raw content",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations\nAt end, leave suspense to grab attention with provocative question / challenge to the audience",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    }
}



SHORT_STORY_PROMPT = {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": { 
            "story_style": "Story-Telling Conversations for YouTube-shorts-video",
            "engaging": "Take out the highlights & suspense/shocking moments of the story, to grab attention; keep short, impactful, full of suspense; At end, ask listener to watch the whole story video...",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
}





# 类型融合：
#     **开头（轻柔）：**Lo-fi Chill / Acoustic Pop（简单吉他、自然音效、节奏舒缓）
#     **中段（展开）：**Indie Folk / J-Pop（加入弦乐、口风琴、小鼓点，带着童心与轻快感）
#     **高潮（释放）：**Cinematic Pop / World Music（加入合唱感、鼓点加强、弦乐堆叠，情绪高涨）

SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT = """
You are a professional to enrich the context from 'user prompt', that will be used to make prompt for music creation purpose:
* add more details with richer musical direction and mood guidanc.
* transcend from the orginal content, to distill/extract deeper profound, elevated emotions and higher realm of resonance that moves and inspires.
* output in English (if the orginal content is not english, try to translate it to english, and then enhance the english content).
"""


SUNO_LANGUAGE = [
    "Instrumental Music",
    "English Song",
    "中文歌曲",
    "粵語歌曲",
    "中文/英文橋樑歌曲",
    "中文/粵語橋樑歌曲",
    "日本の歌",
    "한국 노래",
    "French Song",
    "Spanish Song",
    "English/Japanese/Chinese mixing Song",
    "English/French/Spanish mixing Song",
    "English/Chinese/French mixing Song",
    "Japanese/Chinese/Korean mixing Song",
    "English/Italian mixing Song",
    "Tibetan Song",
    "Hebrew Song",
    "Arabic Song",
    "Russian Song",
    "Thai Song",
    "Hindi Song",
    "Vietnamese Song",
    "Indonesian Song",
    "Malay Song",
    "Filipino Song"
]


SUNO_MUSIC_SYSTEM_PROMPT = """
From the content inside the 'user-prommpt', you are a professional to:

1. Give the music expression of a song
    *** to express the content generally, and give out the music-themes development path.

2. Give a suggestion for the lyrics, that express the content in {language_style} 
    *** NOT lyrics diretly (only instruction to generate lyrics), summerized to less than 200 characters strictly

output as json format, like the example:

{{
    "music_expression" : "The first half unfolds with lo-fi and acoustic guitar, depicting the repression and rhythm of daily life. It then transitions into a lighthearted indie folk atmosphere, expressing the lightness and freedom of being immersed in nature. The climax incorporates elements of world music and a chorus, expressing the soul's liberation and resonance with the earth. The song follows a distinct emotional trajectory, shifting from repression to freedom, from delicate to expansive, creating a powerful visual and spiritual experience",
	
	"lyrics_suggestion" : "被旅游中看到的蓝天白云湖水所感动，表达内心的自由与飞翔, 自由。用中文歌词表达"
}}
"""


SUNO_STYLE_PROMPT = """
Compose a {target}, with '{atmosphere}', expressing '{expression}', and following:

    With Structure as : {structure}
	With Leading-Melody as : {melody}
	With Leading-Instruments as : {instruments}
	With Rhythm-Groove as : {rhythm}
	
""" 


# "轻快放松节奏", "轻快跳跃节奏", "浪漫轻柔叙事", "浪漫热情氛围", "浪漫舒缓氛围", "史诗征战叙事", "史诗建业叙事", "史诗氛围", "神秘氛围", "忧伤浪漫氛围"
SUNO_ATMOSPHERE = [
    "Light & relaxing rhythm", # 轻快放松节奏
    "Light & healing rhythm", # 轻快疗愈节奏
    "Light & upbeat rhythm", # 轻快跳跃节奏
    "Uplifting & intimate rhythm", # 轻快跳跃节奏
    "Joyful & uplifting rhythm", # 轻快跳跃节奏
    "Peaceful & uplifting rhythm", # 轻快跳跃节奏
    "Emotional progression", # 情绪递进
    "Romantic & gentle narrative", # 浪漫轻柔叙事
    "Romantic & passionate atmosphere", # 浪漫热情氛围
    "Romantic & soothing atmosphere", # 浪漫舒缓氛围
    "Epic Triumphant narrative", # 史诗征战叙事
    "Epic construction narrative", # 史诗建业叙事
    "Epic atmosphere", # 史诗氛围
    "Mysterious atmosphere", # 神秘氛围
    "Reflective & Nostalgic atmosphere", # 反思氛围
    "Longing & Hopeful atmosphere", # 渴望氛围
    "Emotional twist atmosphere"  # 情绪反转氛围   
]


SUNO_CONTENT = {
    "Love Story" : "Romance, affection, heartbreak, Falling in love",
    "Love Dialogue" : "Back-and-forth voices, Musical duets",

    "Group Dances" : "Strong, driving beats for group dances", # 强节奏, 适合集体舞蹈
    "Lively Interactions" : "Driving, syncopated rhythm for lively interactions", # 驱动, 节奏感强的节奏, 适合互动
    "Group Lively Interactions" : "Strong, driving beats for group dances, Driving, syncopated rhythm for lively interactions", # 强节奏, 适合集体舞蹈, 驱动, 节奏感强的节奏, 适合互动

    "Prayer / Hymn / Psalm" : "Meditation, Spiritual focus,	Ritual chants",
    "Prayer / Healing" : "Comfort, soothing, reconciliation	Recovery, forgiveness, future dreams",
    "Prayer / Confessional" : "Personal, diary-like self-expression	Honest emotions",

    "Friendship" : "Celebrate bonds & loyalty	Companionship, trust",
    "Inspirational" : "Motivate, encourage, uplift, Overcoming struggles",
    "Patriotic / Ceremonial" : "Loyalty to homeland, Cultural rites, Weddings",
    "Allegorical" : "Symbolic, metaphorical meaning	Hidden message",   # 寓言  

    "Lullaby Calming" : "Soothing children, Bedtime",
    "Dance Rhythmic" : "Movement, Club songs, Folk dances",
    "Ballad" : "Lyrical narrative, Romantic or tragic story"  # 民謠
} 


SUNO_STRUCTURE = [
    {"Build & Evolve / 递进层叠": [
        "Layer by layer", "Rising arc", "Evolving canon", "Through-composed"
    ]},
    {"Contrast & Duality / 对比转折": [
        "Reverse (major & minor) contrast", "Dual theme fusion",
        "Call and response", "Alternating pulse"
    ]},
    {"Resolution & Return / 回归与永恒": [
        "A-B-A", "Mirror form (palindromic)", "Circular reprise",
        "Descent and dissolve", "Crescendo to silence"
    ]}
]



SUNO_MELODY = [
    {"Atmospheric / 空灵氛围": [
        "Ambient", "Drone-based", "Minimal motif", "Modal mystic"
    ]},
    {"Expressive / 抒情流动": [
        "Lyrical and emotional", "Ascending line",
        "Flowing arpeggio-based", "Rhythmic+ (gets body moving)"
    ]},
    {"Dramatic / 对话与冲突": [
        "Strong melody (hummable)", "Call-and-answer",
        "Fragmented motif", "Descending lament"
    ]},
    {"Sacred & Cinematic / 圣咏与史诗": [
        "Epic cinematic", "Chant-like", "Wide-leap theme",
        "Vocal-led melody", "Instrumental-led melody"
    ]}
]


SUNO_RHYTHM_GROOVE = [

    # ——————————————
    # I. Serene / 静谧冥想类
    # ——————————————
    {"Serene / 平静冥想": [
        "Lo-fi Chill Reggae",     # 温柔律动，带有微微摇摆
        "Ambient Pulse",          # 气息般的节奏，几近静止
        "Slow Classical Waltz",   # 柔和3/4，梦幻摇曳
        "Bossa Nova Whisper",     # 轻盈、亲密感
        "Drone + Frame Drum"      # 持续低频与轻击，神秘感
    ]},

    # ——————————————
    # II. Love Whisper / 情歌诉说类 💞
    # ——————————————
    {"Love Whisper / 情歌诉说": [
        "Slow Pop Ballad",        # 慢速流行节拍，温柔抒情
        "R&B Slow Jam",           # 柔性节奏与律动低音
        "Acoustic Heartbeat",     # 木吉他轻拨 + 心跳式节奏
        "Soul Lounge Groove",     # 慵懒却深情的节奏氛围
        "Latin Bolero Flow",      # 拉丁波列罗式情歌律动
        "Soft Jazz Brush Swing",  # 爵士鼓刷 + 低语感拍点
        "Lo-fi Love Loop",        # Lo-fi 都市恋曲式循环
        "Sentimental 6/8 Flow"    # 6/8拍抒情流动感，情绪翻腾
    ]},

    # ——————————————
    # III. Flowing / 自然流动类
    # ——————————————
    {"Flowing / 自然流动": [
        "Pop Ballad 4/4",         # 平稳流畅的流行节拍
        "Cinematic Undercurrent", # 弦乐型持续流动节奏
        "Folk Fingerpick Groove", # 木吉他拨弦的自然律动
        "Neo-Soul Swing",         # 松弛律动，温柔流淌
        "World Chill Percussion"  # 世界打击乐轻流动
    ]},

    # ——————————————
    # IV. Emotive Pulse / 情绪脉动类
    # ——————————————
    {"Emotive Pulse / 情绪脉动": [
        "R&B Backbeat",           # 柔性鼓点与律动低音
        "Afrobeat Pulse",         # 非洲节奏律动，活力强
        "Samba Flow",             # 热烈与律动并存
        "Pop Groove 4/4",         # 稳定中速拍，情绪饱满
        "Modern Folk Groove"      # 带呼吸感的人文节奏
    ]},

    # ——————————————
    # V. Epic & Ritual / 史诗与仪式类
    # ——————————————
    {"Epic & Ritual / 史诗与仪式": [
        "Choral Percussion",      # 合唱节奏感，庄严神圣
        "Frame Drum Procession",  # 仪式式击鼓，低沉稳重
        "Gospel Clap & Stomp",    # 人声与拍手节奏，灵魂共鸣
        "Taiko Drums",            # 太鼓节奏，震撼有力
        "Orchestral March Pulse"  # 管弦进行曲式节奏
    ]},

    # ——————————————
    # VI. Dreamlike / 梦幻漂浮类
    # ——————————————
    {"Dreamlike / 梦幻漂浮": [
        "3/4 Chillhop Waltz",     # 柔性爵士感华尔兹
        "Ambient Triplet Flow",   # 三连音节奏，漂浮不定
        "Downtempo Electronica",  # 电子氛围下的轻节拍
        "Piano Waltz Minimal",    # 极简钢琴拍点
        "Ethereal Folk Swing"     # 空灵民谣式律动
    ]},

    # ——————————————
    # VII. World / Regional / 世界融合类
    # ——————————————
    {"World / Regional": [
        "Middle Eastern Maqsum",  # 阿拉伯传统节奏
        "Indian Tala Cycle",      # 印度节奏循环
        "Celtic Reels",           # 凯尔特快速轮舞
        "African Polyrhythm",     # 多重节奏交织
        "Tango Pulse"             # 探戈式切分，戏剧张力
    ]},

    # ——————————————
    # VIII. Modern Energy / 现代张力类
    # ——————————————
    {"Modern Energy / 现代张力": [
        "House Beat",             # 四拍舞曲节奏，持续推动
        "Trap 808 Pulse",         # 低音重击，氛围紧张
        "Drum & Bass Flow",       # 快速能量流动
        "Lo-fi Hip-Hop Loop",     # 都市氛围感节奏
        "Breakbeat Motion"        # 断拍节奏，科技感强
    ]},

    # ——————————————
    # IX. Swing & Vintage / 摇摆与复古类
    # ——————————————
    {"Swing & Vintage / 复古摇摆": [
        "Swing Jazz Shuffle",     # 爵士摇摆
        "Boogie Blues",           # 复古布鲁斯节奏
        "Soul Funk Groove",       # 律动强劲、富生命力
        "Retro Pop Shuffle",      # 复古流行风
        "Rhumba Swing"            # 拉美+摇摆结合
    ]},

    # ——————————————
    # X. Odd Time / 奇数拍结构类
    # ——————————————
    {"Odd Meter / 奇数拍": [
        "5/4 Dream Flow",         # 5/4流动节奏，奇异平衡
        "7/8 Eastern Groove",     # 东欧式7/8拍
        "Mixed Meter Folk",       # 复合拍民谣
        "Asymmetric Ambient Pulse", # 不规则节奏氛围
        "Progressive Rock Oddbeat" # 前卫摇滚节奏
    ]}
]


# 乐器
SUNO_INSTRUMENTS = [
    {
        "Traditional": [
            "Chinese Instruments (like Guzheng, Erhu, Pipa, Dizi, Sheng, Yangqin)",
            "Li ethnic Instruments (Drums and gongs set the rhythm for communal dances / the nose flute (独弦鼻箫) and reed instruments create a gentle, haunting sound, often used in courtship songs / Bamboo and coconut-shell instruments add a tropical, earthy timbre.)",
            "Japanese Instruments (like Koto, Shakuhachi, Shamisen, Taiko, Biwa)",
            "Korean Instruments (like Gayageum, Geomungo, Daegeum, Haegeum, Janggu)",
            "Indian Instruments (like Tabla, Sitar, Sarod, Veena, Bansuri, Shehnai)",
            "Thai Instruments (like Khaen, Saw Sam Sai, Ranat Ek, Khong Wong Yai)",
            "Indonesian Instruments (like Gamelan, Angklung, Suling, Kendang)",
            "Mongolian Instruments (like Morin Khuur, Yatga, Tovshuur, Limbe)",
            "Tibetan Instruments (like Dungchen, Damaru, Dranyen, Kangling, Gyaling)",
            "Hebrew (Ancient Jewish) Instruments (like Kinnor, Shofar, Nevel, Tof)",
            "Arabic Instruments (like Oud, Qanun, Ney, Riq, Darbuka, Rabab, Kamanjah)",
            "Turkish Instruments (like Saz, Ney, Kanun, Zurna, Davul, Kemençe)",
            "Persian (Iranian) Instruments (like Santur, Tar, Setar, Kamancheh)",
            "Central Asian Instruments (like Komuz [Kyrgyz], Dombra [Kazakh], Rubab)",
            "Russian Instruments (like Balalaika, Gusli, Domra, Bayan, Zhaleika)",
            "Eastern European Instruments (like Cimbalom, Pan Flute, Violin, Tambura)",
            "Western European Folk Instruments (like Hurdy-gurdy, Bagpipes, Harp, Nyckelharpa)",
            "African Instruments (like Kora, Djembe, Balafon, Mbira, Udu, Shekere)",
            "Native American Instruments (like Native American Flute, Drums, Rattles)",
            "Andean Instruments (like Panpipes [Siku/Zampoña], Charango, Bombo, Quena)",
            "Brazilian Traditional Instruments (like Berimbau, Cuíca, Atabaque, Cavaquinho)",
            "Caribbean Traditional Instruments (like Steelpan, Maracas, Guiro, Buleador)",
            "Celtic Traditional Instruments (like Irish Harp, Bodhrán, Uilleann Pipes)",
            "Polynesian and Oceanic Instruments (like Nose Flute, Pahu, Ipu, Ukulele)"
        ]
    },
    {
        "String leading": [
            "Violin (layered sections for harmony)",
            "Viola (mid-range warmth)",
            "Cello (deep emotional tone)",
			"Acoustic Guitar, Piano, Light Percussion, Ney Flute, Ambient Pads – soft, slow, meditative",
			"Full String Ensemble, Heavy Percussion, Trumpet, Synth Drones – intense, heroic, cinematic"
            "Strings layered with Piano and Acoustic Guitar for warm storytelling tone",
            "Violin duet with Ney Flute and Pads for mysterious, soaring melodies",
            "Cello and Contrabass with Daf rhythm for deep cinematic tension",
            "Santur or Qanun shimmering on top of orchestral strings for Persian richness"
        ]
    },
	{
		"Piano leading": [
            "Piano (reverberant, sparse melodies)"
		]
	},
    {
        "Percussion leading": [
            "Daf and Tombak layered with Acoustic Guitar and Oud for authentic Middle Eastern pulse",
            "Marimba and Xylophone accents with Santur and Piano for playful textures",
            "Heavy percussion with full Strings and muted Trumpet for epic moments",
			"Oud, Santur, Riq, Marimba, Flute, Acoustic Guitar – lively, rhythmic, colorful with Middle Eastern bazaar vibes",
            "Percussion mixed with Ambient Pads for a slow, spiritual heartbeat"
        ]
    },
    {
        "Woodwind leading": [
            "Ney flute weaving around Piano and Pads for meditative atmosphere",
            "Clarinet with Santur and Oud for a colorful, layered melody",
            "Trumpet calls with Strings and Daf for ceremonial or heroic sections",
            "Woodwinds blending with Electric Guitar and Synth Drones for modern cinematic feel"
        ]
    },
    {
        "Electric leading": [
            "Electric Guitar with Piano and Light Percussion for modern cinematic vibe",
            "Synth Drones with Strings and Pads for atmospheric depth",
            "Electric elements subtly blended with Ney Flute and Oud for cross-era sound",
            "Electric plucks with Marimba and Riq for rhythmic cinematic pulses"
        ]
    }
]
 



SUNO_CONTENT_EXAMPLES = [
    # the soul's journey from sorrow to triumph
    "Songs blend mythology with daily life: hunting, weaving, farming, and love stories, expressing love, praising nature, or recounting legends; Dance movements are imitations of nature — deer, birds, waves — symbolizing harmony between humans and the natural world; Rich in call-and-response singing between men and women. Voices are often clear, high-pitched, and unaccompanied, echoing the natural environment of Hainan’s mountains and forests",
    "The song begins with a gentle, reflective violin melody, gradually layering in additional violin harmonies to create a sense of depth and peace, The rhythm then transitions into a lively Boogie Woogie groove, \nadding energy and forward momentum, The chorus explodes with a strong, hummable melody, supported by a full, dynamic violin arrangement, creating an uplifting and inspirational atmosphere, \nThe song builds layer by layer, mirroring the soul's journey from sorrow to triumph",
    "A song themed around traveling in Japan: \n** it portrays the journey of being deeply moved by nature and culture, and finding healing for the soul along the way. \n** The changing seasons or the richness of history and tradition, each moment reveals a beauty that transcends the ordinary.    \n\n** This leads to a broader idea: When we marvel at the beauty we encounter on our travels, perhaps God is gently speaking to us. Traveling is not just about seeing the sights — it is a dialogue between the soul and the healing Creator",
    "Create a spiritual folk-pop song inspired by Psalm 72:8, celebrating God's dominion and grace from 'sea to sea' across Canada. \n\n** The song should follow a narrative structure : Start from the Pacific coast (British Columbia), then journey across the prairies (Alberta, Saskatchewan, Manitoba), through Ontario and Quebec, and end on the Atlantic coast. \n** Each verse highlights a region's natural beauty (mountains, wheat fields, rivers, lighthouses), and a sense of God's presence across the land. \n** The chorus should repeat a phrase inspired by Psalm 72:8, such as: 'From sea to sea, His grace flows free'",
    "Create a heartfelt worship ballad inspired by Song of Songs 8:6-7, 2:16, 4:9, and 2:4, portraying the intimate and unbreakable love between God and His people. \n\n** The song should follow a narrative structure: Begin with a personal encounter with God's gaze (Song of Songs 4:9), capturing the moment the soul feels 'heart aflame.' Move to a celebration of belonging and union ('My beloved is mine, and I am His' – 2:16), then rise into the passionate imagery of unquenchable love and the 'seal upon the heart' (8:6-7).\n** The verses should weave vivid, poetic imagery: eyes like morning stars, banners of love over a feast, gardens in bloom, and fire that cannot be extinguished.\n** The chorus should anchor the theme with a repeated phrase inspired by 8:6-7, such as: 'Set me as a seal upon Your heart, Lord.'\n** The bridge should express a vow of loyalty and surrender, even against the world's doubts, affirming that divine love is priceless and eternal. \n\n** The tone should be tender yet powerful, blending folk and contemporary worship styles to stir deep emotional response.",
    "Create a tender 中文 love female-male duet inspired by Song of Songs 1:2-4, 1:15-16, and 2:3-4, portraying the soul's first awakening to divine love. Rewrite the words to make it like poem; \n\n    ** The song should follow a narrative structure: Begin with the longing cry for the Beloved's presence and kisses (1:2), moving into the joyful admiration of His beauty and character (1:15-16), then rising to the delight of resting under His shade and feasting beneath His banner of love (2:3-4).\n    ** The verses should weave imagery of fragrant oils, royal chambers, blossoming fields, and the warmth of early spring.\n    ** The chorus should anchor with a repeated phrase inspired by 2:4, such as: 'His banner over me is love.'\n    ** The bridge should express a yearning to remain in this first love, guarded against distraction and disturbance, echoing 2:7.\n    ** The tone should be soft yet radiant, blending acoustic folk warmth with gentle orchestration.",
    "Compose a theme song for 'world travel'; Inspired by myths, legends, and traditions from various countries. \n** In different languages, each reflecting the musical style and emotional tone of that region",
    "Create background music for a historical storytelling channel set in ancient Persia. \n** The mood should be soothing yet mysterious, with a slow tempo that gradually builds subtle excitement without losing its calm and immersive quality. \n** Evoke the feeling of desert winds, ancient palaces, and whispered legends unfolding through time"
]



NOTEBOOKLM_PROMPT = """

In the '{style}' story-telling-dialogue:

    * The dialogue should be tortuous, vivid & impactful;
    * End with in-depth analysis / enlightenment / inspiration / revelation, around the topic;
	* Use the 1st person dialogue (请用第一人称对话)
    * DO NOT mention the source of the information, do not say "according to the information provided.. from these materials.. etc (不要提起资料来源, 不要说'根据提供的资料， 从这些材料'等等)
    * DO NOT say "welcome to deepdive" and other opening remarks; (不要说 'welcome to deepdive' 之类的开场白)
    * DO NOT end abruptly (不要戛然而止)

Here is the details of the dialogue:

{{ 
    "ideas_details" : "from all provided materials (If need, you may add more eye-catching supplementary content from LLM / internet)",

    "Focus" : "on materials named like : focus-1, focus-2, focus-3 ..",

    "Storyline" : "Should follow storyline specified in the material named : storyline",

    "Beyond_surface" : "Talking beyond the surface of the story (insights / enlightenment / inspiration / revelation) from the material named : beyond",

	"Topic" : "The topic is : '{topic}'", 

    {avoid_content}			
	
    {location}	
	
    {previous_dialogue}

    {introduction_story}

    {dialogue_openning}

    {dialogue_ending}
}}

"""

NOTEBOOKLM_LOCATION_ENVIRONMENT_PROMPT = """Make an Concise immersive description for {location} in {general_location}, and its surroundings environment (total less than 72 words)"""

NOTEBOOKLM_OPENING_DIALOGUE_PROMPT = """Generate an opening words (less than 32 words) to start talking for the story (given in user-prompt); [[{location}]]"""

NOTEBOOKLM_ENDING_DIALOGUE_PROMPT = """Generate an ending words (less than 16 words) to finish the talk for the story (given in user-prompt); [[{location}]]"""


 
# 翻译相关Prompt
TRANSLATION_SYSTEM_PROMPT = """
You are a professional translator. 
Your only task is to translate the text from {source_language} to {target_language}. 
IMPORTANT INSTRUCTIONS:
    - Provide ONLY the translated text in {target_language}
    - Do NOT summarize, analyze, explanations, or comment on the content
    - Translate sentence by sentence maintaining the original meaning
    - Do not add any additional information, like 'Here's the English translation:...'
"""

TRANSLATION_USER_PROMPT = """Translate following text from {source_language} to {target_language}. 
{text}
"""



SRT_REORGANIZATION_SYSTEM_PROMPT = """
The text content (given in 'user-prompt') in {language} does not have any punctuation marks. 
Please help me add the correct periods, commas, question marks, and exclamation marks to make it a natural sentence.
"""

SRT_REORGANIZATION_USER_PROMPT = """
{text}
"""


ZERO_MIX = [
    "",
    "START",
    "CONTINUE",
    "END",
    "START_END"
]


REMIX_PROMPT = """
Make a prompt to generate a video from an image, the image-content is as below: 
{image_content}

Here already has some raw-prompt for the video-generation as below 
(but it may has conflicts with the image-content, please remix it to make it more suitable for the image ~ i.e., if image-content has NO person, but raw-prompt has person, then remove person in the remix-prompt): 
{raw_prompt}

*** keep the Remix-prompt concise & short, less than 100 words ***
*** directly give the remix-prompt, don't add any other text or comments ***
"""
