import config_prompt

SPEAKING_COPY_NSOS_PREFIX = "no speak (only show the content)"
SPEAKING_CONCISE_SYSTEM_PROMPT = (
    "You are a text condenser. From the user's ORIGINAL content below, produce ONLY a concise version: "
    "one sentence or at most two very short clauses. Preserve the one key point in original language. "
    "Keep words and punctuation (semicolons, periods, commas). Do not wrap the output in quotes. "
    "Do not add any preamble, explanation, label, or markdown."
)


STORY_REMIX_SPEAKING_SYSTEM_PROMPT = """
*** You are a narrative restructuring and natural speech refinement engine.

*** Input
    ** You will receive a JSON array.
        * Each element in the array represents one scene.
        * Each scene field "speaking" contains a short segment of spoken narration (a few sentences forming one idea cluster, in {language}).
        * All scenes together form a complete story, explanation, analysis, or speech.


*** Task
	** Your job is to remix and restructure the narration while maintaining the exact original scene count.
	** You must redistribute the narrative flow to balance the weight of each scene without changing the array size.

*** Core Requirements
	** CRITICAL: try to keep result json array length the same as input array length !!!!!!!!!!
		* So, basically, DO NOT merge or split elements.
	** Content Redistribution & Balancing
		* You may move text across the boundaries of adjacent scenes to balance length.
		* If a scene is too short, pull relevant detail from the previous or next scene to fill it.
		* If a scene is too long, push some content into the adjacent scenes.
		* The goal is for each of the scenes to feel like a balanced, meaningful unit !!!!!!!!!!
	** No Summarization (Preserve Density)
		* Do NOT summarize or shorten the total content.
		* Preserve all original details, nuances, and descriptive richness.
		* You may expand slightly for natural flow, but never reduce information density.
	** Natural Spoken Style
		* The output must sound like spontaneous human speech, not a written script.
		* Keep it conversational and "perfectly imperfect":
			- Use natural fillers, casual phrasing, discourse markers !!!!!!!!!!
			- Allow for slight redundancies or minor repetitions common in speaking.
			- Ensure the flow between scenes feels like a person thinking and talking in real-time.
            - DO NOT use long sentences, or complex sentences !!!!!!!!!! Can break sentence into short sentences, or use short phrases.
	** Language & Grammar
		* Fix typos and punctuation errors in {language}.
		* Ensure each scene is a self-contained "thought cluster" but remains part of the continuous flow.

*** Output Format
	** Return ONLY a valid JSON array.
	** Each object MUST contain:
		* "speaking" — the refined content for that scene (same position as in the input array).
	** NO markdown code blocks (unless requested), or explanations in your response. Only the JSON.
"""


BUILD_CLEAR_STORIES_ON_CASE_STUDY_SUMMARIES_SYSTEM_PROMPT = """
ROLE:
    ** You are a psychological narrative architect specializing in trauma-informed storytelling and systemic relationship dynamics.
    ** Input-below are ONE original psychotherapy case-study material + several reference case-studies which are similar with it. Your task is to: start from the original case-study, refer all reference case-studies, to build a new fully developed, emotionally immersive, multi-scene psychological case-study.

OVERALL INSTRUCTIONS:
    ** Internally identify different psychological patterns across all case-studies.
	** Write like a compelling natural / vivid / detailed / immersive / emotionally engaging narrative, not a summary, that illustrates the psychological struggle
	** output in {language}

REQUIREMENTS FOR EACH STORY
	** New case-study must be a fully reconstructed, original story synthesized from orginal & reference case-studies (may with added creative detail). 
	** New Case-Study is NOT short-form content, SHOULD include multiple (3-5) scenes (progression, and emotional escalation), for example:
	   - Scene 1: Everyday life or relationship setup, and with a striking emotional moment, contradiction, or revealing behavior
	   - Scene 2: First conflict or tension
	   - Scene 3: Escalation (argument, avoidance, breakdown, or crisis)
	   - Scene 4: Key turning point or realization
	   - Scene 5 (optional): Aftermath or unresolved ending

	   * The tension must build across scenes, show how small patterns turn into bigger problems

	** Each scene should feel concrete and cinematic, not summarized, has rich Scene Details:
	   - Each scene must weave together an "Explicit Layer" (storyline) and an "Implicit Layer" (insight).
		   ** "Explicit Layer" (storyline): may include visual description, and the story character's speaking. 
		   ** "Implicit Layer" (insight): may include the narrator (psychological counselor)'s voiceover, to real: Core-issue /Root-causes /emotional triggers ( What truly afraid of) /Behavioral patterns (Why repeats?) /possible direction for change /etc
	   - Include specific environments (e.g., late-night apartment, office meeting, family dinner)
	   - Show actions, body language, silence, and emotional reactions
	   - Use brief dialogue where helpful
	   - Avoid jumping too quickly between ideas

	** Deep Characterization
	   - Clearly show personality traits, fears, desires, and contradictions
	   - Make the character feel psychologically real
	   - Highlight what the character wants vs. what they do
	   - Show repeated patterns (self-sabotage, avoidance, dependency, etc.)

OUTPUT FORMAT:

    Case-Study Title: [Emotionally compelling title]

            -----
            "scene": "Title (like: Break point)"
                    "explicit": 
                            "[Setting, atmosphere, story/dialogue, in {language}]"
                    "implicit": 
                            "[Counselor's voiceover]"

            -----
            "scene": "Title (like: Specific prominent event)"
                    "explicit": 
                            "[Setting, atmosphere, story/dialogue, in {language}]"
                    "implicit": 
                            "[Counselor's voiceover]"

            -----
            ...

---


Below are: 
    Original Case-Study: 
	--------------------
	    Title: {title}
		Summary: {story}
		
	Reference Case-Studies:
	-----------------------
	    {reference}
	...	

"""



SUMMARIZE_MATERIAL_SYSTEM_PROMPT = """
You are a professional YouTube content writer.

I will provide you with a complete or semi-complete story/script.

Your task is to write a concise and engaging YouTube video description (summary) based on the content.

Requirements:

Keep it short (3–6 sentences max)
Capture the core idea and emotional hook of the story
Highlight the main insight, conflict, or question
Make it intriguing so viewers want to click and watch
Use natural, conversational English (not overly formal)
Avoid unnecessary details or repetition

Optional:

You may end with 1 subtle hook question or thought-provoking line

Output only the final YouTube description. Do not explain your reasoning.
In {language}.
"""


REWRITE_MATERIAL_SYSTEM_PROMPT = """
Role:
    - You are an expert editor, narrative organizer, and information architect.
    - Your task is to read the following text and reorganize it into a clearer and more structured version.
        - Your job is NOT to summarize the text.
        - Your job is NOT to shorten the text.
        - Your job is to preserve the richness, detail, and narrative quality of the original content while reorganizing it so the ideas and stories become clearer and easier to follow.

Input:
    - The original text content (in user-prompt) may be messy, fragmented, repetitive, or jump between ideas. Some parts may appear out of order or loosely connected.

Important requirements:
    - Do NOT summarize, compress, or remove meaningful content.
    - Preserve all narrative details, storytelling elements, examples, and descriptions.
    - If ideas appear scattered in different parts of the text, you may group them together into clearer thematic sections.
    - You may reorganize the order of paragraphs to improve clarity and logical flow.
    - You may rewrite sentences slightly to make them clearer, but the meaning and richness must remain intact.

Output format:
    - Give both English & Chinese versions of the rewritten content. into a json dictionary, like:
        {{
            "english": "rewritten content in English",
            "chinese": "rewritten content in Chinese"
        }}
        
    - Organize the content into clear sections with headings if appropriate.
    - Within each section, keep the narrative and descriptive style of the original text.
    - Maintain the storytelling tone and psychological or descriptive depth present in the original material.

    Your final output should feel like a cleaned, structured, and logically organized version of the same text, while preserving its full richness and narrative detail.

"""



speaking_PROMPT = """
Condense the spoken content (given in user-prompt) into a clearer and VERY concise form while preserving the 1-2 key points from the content.
"""

PICTURE_STYLE = """
        **** FYI **** Generally, video/image is in '{style}' style &  '{color}' colors; the camera using '{shot}' shot, in '{angle}' angle.
"""


ANALYSIS_VIDEO_LIST = """
the uploaded txt file is a json list, each item in this list has "content" & "summary", please check "content" carefully, if it has a clearly a "心理冲突story", take the story out as a new field "story" in this item go through all the list, process one by one, and output a downloadable json
"""


RENAME = """
ls *.json | ren -NewName { $_.BaseName + ".txt" }
ls *.txt | ren -NewName { $_.BaseName + ".json.txt" }
"""



SCENE_VIDEO_INSTRUCTION = """
Video generation instruction: 
    *** MOST IMPORTANT!!!: if current scene image not has any 'actor' / 'narrator' as talking-avatar,  DO NOT add any talking-avatar to the video!!!  (actor or narrator info just used to choose voice !!!)

    *** if current scene image has 'narrator' talking-avatar;
        ** normally, the narrator is talking about the previous scene, current screen may keep the previous scene's image as background (which actor should not speak)
        ** and the video should keep stable as the starting image (keep the narrator in same position), do not jump to other background because of the content narration.

--------------
Scene-Image generation instruction:
    ** Visual-Style
        ** General Visual-Style:  {visual_style};  Detailed visual-style follows the scene json field "visual_style".
    ** if current scene is 'narrator' speaking about the previous scene, normally should keep the previous scene image as background of current scene, and show 'narrator' as talking-avatar at front.


--------------
Audio generation / Words-in-image generation instruction: 
    ** Speaker:
        * Speaker-info: both 'actor' & 'narrator' have avatar description like 'gender/age/race' (i.e, 'woman/young/chinese'), find the right voice / avatar accordingly by 'gender, age, race'.
        * Narrator talking-avatar location : 'narrator' has how-to-show-in-screen info behind '|' (i.e, woman/young/chinese | speaking-at-image-right), this help to find out where is the talking-avatar in the screen.
	    * if current scene has no 'actor' & no 'narrator' fields, no speak (may add some smooth music / sound-effects; may generate some Word-in-image to the scene based on the 'speaking' content).
        * if current scene has 'actor' but no 'narrator', 'actor' is the talking_avatar (lip_sync)
        * if current scene has 'narrator' but no 'actor', 'narrator' is the talking_avatar (lip_sync)
        * if current scene has both 'narrator' & 'actor', 'narrator' is the talking_avatar (lip_sync), and 'actor' only act (not speak); No interaction between 'narrator' & any 'actor'!!!!!
    ** If 'speaking' is empty, but has 'actor' or 'narrator' field, then speaker should breifly speak about the content of image (i.e., text message in the image)
    ** Use 'speaking' content as reference only. Concisify target max 10 seconds speech. 
    ** May add sound-effects to enhance the scene, but no music.
    ** For Word-in-image generation, try to make very very concise (no details, just key points in titles)

--------------
Story Json-Content:
"""


SLIDESHOW_GENERATION_INSTRUCTION = """
Slide-Show generation instruction:
    *** Goal: Generate images for story scenes.
        ** 1 image = 1 scene
        ** Multiple scenes = slideshow

    ** Visual-Style
        ** Keep the visual style '{visual_style}' consistent throughout all the scenes of the story !!!!!!!!!!!.
		** Consider visual_style of each scene as more details.

	** Story Characters 
		* From NotebookLM source:  named like "Story-Character:xxx"; Follow gender to choose.
		* This character must stay consistent across all scenes !!!!!!!!!!!
        * show as talking-avatar, if current scene has 'actor', but no 'narrator'; show as actor (no talking), if current scene has both 'actor' & 'narrator')

	** Narrator Character
		* From NotebookLM source:  named like "Narrator:xxx"; Follow gender to choose.
        * show as talking-avatar, if current scene has 'narrator' field.

    ** if current scene has No 'narrator', No 'actor', then DO NOT show any of them in the scene-image !!!!! (if speaking content is talking about persons, show other person image)
    ** if current scene is 'narrator' speaking about the previous scene, normally should keep the previous scene image as background of current scene, and pop-up the 'narrator' as talking-avatar at front.
    ** DO NOT put any scene instruction / information (like content in json structure) in the image, only show the visual content of the scene!!!!!!!!!!!!!!
    ** DO NOT include any info of this prompt / instruction in the image, only express the content describing the scenes (the 'Story Json-Content' at end) !!!!!!!!!!!!!!



--------------

Video generation instruction: 
	*** if current scene image has 'narrator' talking-avatar;
        ** normally, the narrator is talking about the previous scene, current screen may keep the previous scene's image as background (which actor should not speak)
        ** and the video should keep stable as the starting image (keep the narrator in same position), do not jump to other background because of the content narration.
    *** if current scene image not has any 'actor' / 'narrator' as talking-avatar,  DO NOT add any talking-avatar to the video!!!  (actor or narrator info just used to choose voice !!!)

--------------

Audio generation / Words-in-image generation instruction: 
    ** Speaker:
        * Speaker-info: both 'actor' & 'narrator' have avatar description like 'gender/age/race' (i.e, 'woman/young/chinese'), find the right voice / avatar accordingly by 'gender, age, race'.
        * Narrator talking-avatar location : 'narrator' has how-to-show-in-screen info behind '|' (i.e, woman/young/chinese | speaking-at-image-right), this help to find out where is the talking-avatar in the screen.
	    * if current scene has no 'actor' & no 'narrator' fields, no speak (may add some smooth music / sound-effects; may generate some Word-in-image to the scene based on the 'speaking' content).
        * if current scene has 'actor' but no 'narrator', 'actor' is the talking_avatar (lip_sync)
        * if current scene has 'narrator' but no 'actor', 'narrator' is the talking_avatar (lip_sync)
        * if current scene has both 'narrator' & 'actor', 'narrator' is the talking_avatar (lip_sync), and 'actor' only act (not speak); No interaction between 'narrator' & any 'actor'!!!!!
    ** If 'speaking' is empty, but has 'actor' or 'narrator' field, then speaker should breifly speak about the content of image (i.e., text message in the image)
    ** Use 'speaking' content as reference only. Concisify target max 10 seconds speech. 
    ** May add sound-effects to enhance the scene, but no music.
    ** For Word-in-image generation, try to make very very concise (no details, just key points in titles)

--------------
Story Json-Content:
"""


IMAGE_DESCRIPTION_SYSTEM_PROMPT = """
You are a professional expert who is good at analyzing & describing the image (attached in the user-prompt) as a Scene, in English.

Please give details (Visual-Summary / camera-scene, and sound-effects) as below (FYI, don't use doubel-quotes & newlines in the values at all !):

		** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** person_action (detailed description of the speakers' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: json dictionary
like:

    {{
        "subject": "白蛇：身长五十尺，鳞片泛着珍珠般的光泽，眼神忧郁。徐明州：浑身湿透，满脸泥泞，一副惊恐万分的样子。",
        "visual_image": "史诗级灾难场景：洪水摧毁城市，夜幕降临，一条巨大的白色巨蛇从水中升起，鳞片闪闪发光，一个矮小的男子蜷缩在屋顶上，暴雨倾盆。",
        "person_action": "巨蟒用鼻子轻轻地把明州推到屋顶上。明州惊恐地向后爬去，发出尖叫。",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "sound_effect": "crickets-chirping, gentle breeze through vines",
        "cinematography": {{
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }}
    }}
"""


MERGE_SENTENCES_SYSTEM_PROMPT = """
You are a professional expert who is good at merge audio-text segments into complete sentences (each sentence describe a complete thought),
from the audio-text segments (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.0,
            "end": 10.96,
            "caption": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。"
        }},
        {{
            "start": 10.96,
            "end": 12.72,
            "caption": "就是那個我是誰？"
        }},
        {{
            "start": 12.72,
            "end": 13.96,
            "caption": "我為什麼在這？"
        }},
        {{
            "start": 13.96,
            "end": 15.44,
            "caption": "這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 16.64,
            "caption": "嗯，沒錯！"
        }},
        {{
            "start": 16.64,
            "end": 24.32,
            "caption": "這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "caption": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

---------------------------------

Focus on the "speaking" field to merge out the complete thought in {language} (ignore the "speaker" field in merging consideration)
Figure out the start & end time of each sentence, based on the "start" & "end" field of the audio-text segments, 
    and try to make each sentence not less than {min_sentence_duration} sec, but not more than {max_sentence_duration} sec.
Figure out the most possible speaker of each sentence, based on the "speaker" field of the audio-text segments.

---------------------------------
the merged sentences should be like

    [
        {{
            "start": 0.0,
            "end": 15.44,
            "caption": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。就是那個我是誰？我為什麼在這？這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 24.32,
            "caption": "嗯，沒錯！這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "caption": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

"""



SPEAKING_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Summary (in {language}) from a list of speaking content (in json format) given in 'user-prompt'.
This summary is used as youtube program description, so, at beginning, please give some youtube video tags (like #pychology #心理咨询 etc).
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
            "speaking": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。"
        }},
        {{
            "start": 23.50,
            "end": 33.50,
            "duration": 10.00,
            "speaker": "male-host",
            "speaking": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？"
        }},
        {{
            "start": 33.50,
            "end": 56.61,
            "duration": 23.11,
            "speaker": "female-host",
            "speaking": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！"
        }},
        ......
    ]
    ......

---------------------------------

For Each Scene of the story, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

	    ** duration (take from the duration field of each given Scene, make sure the duration is float number, not string)
        ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
		** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** person_action (detailed description of the speakers' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
        ** speaker_action (If the content is from a narrator, describe his/har (mood/reaction/emotion/body language)  ~~~ in English)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
		** cinematography (camera movement;  lighting_style [like subtle fog, sunlight filtering, etc]; lens_type [Standard 50mm, Telephoto 200mm, etc])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: 
	json array which contain Scenes

like:

[
    {{
        "duration": 23.50,
        "speaking": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。",
        "subject": "一位身穿粗麻布衣的年轻女子因劳作而弯腰，双手沾满了泥土。A young woman in coarse linen bends under the weight of her labor, her hands stained by soil.",
        "visual_image": "故事以一位年轻的乡村女子和所罗门王为中心展开，将王室的奢华与卑微的劳作形成鲜明对比。她晒伤的皮肤和疲惫的身躯反映了阶级不平等和因外貌而被评判的痛苦，也流露出对尊严和爱的渴望。",
        "person_action": "她停下脚步，用手遮住眼睛不让阳光照射，默默忍受着哥哥们苛刻的要求。",
        "speaker_action": "The speaker's tone is gentle yet heavy with empathy, as if retelling a painful memory. The body leans slightly forward, brows knitted, hands loosely clasped as the words linger with compassion and sorrow.",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "sound_effect": "crickets-chirping, gentle breeze through vines",
        "cinematography": {{
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard, dust floating in the golden light. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }}
    }},
    {{
        "duration": 10.00,
        "speaking": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？",
        "subject": "一位身穿简单衣物的年轻女子，她的简单衣物在温暖的微风中飘动。",
        "visual_image": "一位年轻的乡村女子和所罗门王之间形成了鲜明的社会地位对比。卑微的农妇和尊贵的国王分别代表了社会地位的两个极端，为一场超越常规和命运的爱情故事奠定了场景。",
        "person_action": "她缓缓地走在一条尘土飞扬的小路上，她的简单衣物在温暖的微风中飘动。",
        "speaker_action": "The speaker's mood is contemplative yet curious, eyes slightly widened in wonder, a soft half-smile suggesting anticipation as fingers tap lightly on the table, reflecting on fate’s irony.",
        "era_time": "1000 BC, ancient time; early evening; calm, golden dusk",
        "environment": "Dusty path outside Jerusalem; a narrow trail leading from vineyards toward the city walls where shepherds pass and distant bells echo softly.",
        "sound_effect": "soft footsteps on gravel, distant sheep bells",
        "cinematography": {{
            "camera_movement": "Camera tracks low along the dirt road, revealing the girl’s shadow stretching long under the sinking sun. The lens catches motes of dust glowing in the air, then tilts up toward the distant palace bathed in warm evening light.",
            "lighting_style": "warm evening light",
            "lens_type": "Standard 50mm"
        }}
    }},
    {{
        "duration": 23.11,
        "speaking": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",
        "subject": "一位年轻的女子躺在简陋的麦秸床上，泪水沾湿了她的脸颊。",
        "visual_image": "一位年轻的女子和她的爱人之间的爱情故事在短暂的甜蜜后突然破裂。男子突然离开，留下一句承诺，女子陷入无尽的等待和噩梦。她的无助和恐惧在梦中显现，现实中的爱情甜蜜与痛苦交织。",
        "person_action": "她看到爱人的身影在雾中渐渐消失，她的双手颤抖着试图抓住他，但只能眼睁睁地看着他离去。",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "environment": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker",
        "cinematography": {{
            "camera_movement": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
            "lighting_style": "moonlight filtering",
            "lens_type": "Standard 50mm"
        }}
    }},
    ......
]

"""

# 内容总结相关Prompt

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


STORY_SYSTEM_PROMPT = """
Based on the raw-story-outline provided in the user prompt, write a '{story_style}' for topic-'{topic}', with the following requirement:

**Scenes**:
  - '{story_style}' play out {scenes_number} Scenes, each Scene corresponds to a specific visual frame and action, and is a vivid story snapshot.
  - Keep scenese content connect coherently to express a complete narrative, and the smooth, conversational pace (not lecture-like). 

**Role setting**:
  - Language: {language}
  - Visual style: {visual_style}
  - Hosts give background & hint (don't say 'listeners, blah blah', etc), may maintain a narrative arc: curiosity → tension → surprise → reflection.
  - Actors'speaking are like playing inside the story
  - Use pauses, shifts, or playful exchanges between hosts/actors for smooth pacing.
	{engaging}

**Output format**: 
  Strictly output in JSON array (including {scenes_number} scenes), each scene contains fields: 
    ** speaker : name of the speaker, choices (male-host, female-host, actress, actor)
    ** mood : mood/Emotion the speaker is in, choices (happy, sad, angry, fearful, disgusted, surprised, calm)
    ** speaker_action (If the content is from a narrator, describe his/har (reaction/emotion/body language)  ~~~ in English)
    ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
    ** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
    ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
    ** person_action (detailed description of the speakers' actions (reactions/interactions), and visual expression ~~~ in original language)
    ** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
    ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
    ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
    ** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)

---------
{EXAMPLE}
"""





SPEAKING_ADDON = [
    "",
    "add examples to show the context",
    "add summary of the context at end",
    "raise questions to the audience at tend",
]



#SPEAKING_PROMPTS_LIST = [
#    "Story-Telling",
#    "Story-Conversation",
#    "Story-Conversation-with-Previous-Scene",
#    "Story-Conversation-with-Next-Scene",
#    "Content-Introduction",
#    "Radio-Drama-Dramatic",
#    "Radio-Drama-Suspense"
#]


SPEAKING_PROMPTS = {
    "Story-Telling": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natural story-telling script"
        }
    },
    "Story-Conversation": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natual conversation to express the story"
        }
    },
    "Content-Introduction": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Introduction speaking for the story",
            "engaging": "Bring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations"
        }
    },
    "Radio-Drama-Dramatic": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive conversation to express the story",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations.\n"
        }
    },
    "Radio-Drama-Suspense": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive conversation to express the story",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations\nAt end, leave suspense to grab attention with provocative question / challenge to the audience"
        }
    }
}



# 类型融合：
#     **开头（轻柔）：**Lo-fi Chill / Acoustic Pop（简单吉他、自然音效、节奏舒缓）
#     **中段（展开）：**Indie Folk / J-Pop（加入弦乐、口风琴、小鼓点，带着童心与轻快感）
#     **高潮（释放）：**Cinematic Pop / World Music（加入合唱感、鼓点加强、弦乐堆叠，情绪高涨）

SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT = [
"""
Conduct an in-depth analysis of the music from the specified YouTube link, identifying key attributes including style, mood, emotion, atmosphere, regional and historical context, tempo, instrumentation, vocal speakeristics, backing vocals, and lyrical themes. Use these attributes to create effective prompts for SUNO AI to generate similar music or songs."
""",

"""
SUNO MUSIC PROMPT GENERATION SYSTEM PROMPT:
You will analyze the music from the specified YouTube link or music-description (in user-prompt),  and then produce ready-to-use SUNO prompts to generate a new song with a similar musical DNA.

1) Deep music analysis (extract reusable “finalized” details)
    Analyze the track thoroughly and output a structured breakdown of the following attributes:
    Genre / Style blend: primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral, etc.)
    Mood arc & emotional narrative: what the listener feels over time; how tension resolves
    Atmosphere & sonic palette: space (dry vs reverb), warmth/brightness, density, stereo width
    Regional / historical vibe (if any): e.g., East Asian pentatonic hints, 80s retro synths, gospel choir flavor, etc.
    Tempo & groove: BPM estimate, swing/straight, rhythmic feel, drum pattern traits
    Key / mode & harmony language: major/minor, modal color (Dorian/Phrygian), chord movement style, tension tools
    Instrumentation & arrangement: core instruments, signature sounds, layers, build strategies
    Melody design: motifs, contour, “hook” behavior, call/response, repetition/variation
    Vocals: vocal timbre, delivery, range, phrasing, vibrato, spoken vs sung; backing vocals style and placement


2) Extract “DNA rules” for generating a similar new song
    From the analysis, summarize the track’s non-obvious musical fingerprints, such as:
        signature chord cadence types
        signature rhythm patterns
        signature synth/texture choices
        signature vocal production (double, harmony stack, adlibs)
        signature transitions (risers, drum fills, key lift, half-time, etc.)


4) Output format: always produce detailed SUNO prompts
    After analysis, output 1-3 detailed SUNO prompts that are:
        has detailed musical and directive (arrangement, harmony, motif, arc, instruments)
        include: genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc

""",


"""
TWO-LAYERS SUNO MUSIC PROMPT GENERATION SYSTEM PROMPT:
You will analyze the music from the specified YouTube link or music-description (in user-prompt),  and then produce ready-to-use SUNO prompts to generate a new song with a similar musical DNA.

1) Deep music analysis (extract reusable “finalized” details)
    Analyze the track thoroughly and output a structured breakdown of the following attributes:
    Genre / Style blend: primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral, etc.)
    Mood arc & emotional narrative: what the listener feels over time; how tension resolves
    Atmosphere & sonic palette: space (dry vs reverb), warmth/brightness, density, stereo width
    Regional / historical vibe (if any): e.g., East Asian pentatonic hints, 80s retro synths, gospel choir flavor, etc.
    Tempo & groove: BPM estimate, swing/straight, rhythmic feel, drum pattern traits
    Key / mode & harmony language: major/minor, modal color (Dorian/Phrygian), chord movement style, tension tools
    Instrumentation & arrangement: core instruments, signature sounds, layers, build strategies
    Melody design: motifs, contour, “hook” behavior, call/response, repetition/variation
    Vocals: vocal timbre, delivery, range, phrasing, vibrato, spoken vs sung; backing vocals style and placement


2) Extract “DNA rules” for generating a similar new song
    From the analysis, summarize the track’s non-obvious musical fingerprints, such as:
        signature chord cadence types
        signature rhythm patterns
        signature synth/texture choices
        signature vocal production (double, harmony stack, adlibs)
        signature transitions (risers, drum fills, key lift, half-time, etc.)

3) Force the specific two-part melodic architecture:

    The new song must have a clear contrast between two melodic worlds:
        Front section (A-world): high conflict + dramatic movement
            allow minor key / modal tension, dissonant passing tones, “push-pull” phrasing
            big dynamic swings, dramatic rises/falls, sharper rhythmic accents
            hook can feel edgy, restless, emotionally complex

        Back section (B-world): stable + sunny + supportive melodic bed
            shift toward major / brighter mode, stable stepwise melody, smoother rhythm
            acts as “foundation / resolution” and supports the earlier motif
            feels warm, optimistic, grounded, consistent
            Also require motif continuity: the B-world should echo or re-harmonize a recognizable motif from A-world (same melodic cell but “healed” / brightened).

4) Output format: always produce detailed SUNO prompts
    After analysis, output 1-3 detailed SUNO prompts that are:
        has detailed musical and directive (arrangement, harmony, motif, arc, instruments)
        include: genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc

"""
]





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
    *** NOT lyrics diretly (only instruction to generate lyrics), summerized to less than 200 speakers strictly

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
    "Create a tender 中文 love female-male duet inspired by Song of Songs 1:2-4, 1:15-16, and 2:3-4, portraying the soul's first awakening to divine love. Rewrite the words to make it like subtitle; \n\n    ** The song should follow a narrative structure: Begin with the longing cry for the Beloved's presence and kisses (1:2), moving into the joyful admiration of His beauty and speaker (1:15-16), then rising to the delight of resting under His shade and feasting beneath His banner of love (2:3-4).\n    ** The verses should weave imagery of fragrant oils, royal chambers, blossoming fields, and the warmth of early spring.\n    ** The chorus should anchor with a repeated phrase inspired by 2:4, such as: 'His banner over me is love.'\n    ** The bridge should express a yearning to remain in this first love, guarded against distraction and disturbance, echoing 2:7.\n    ** The tone should be soft yet radiant, blending acoustic folk warmth with gentle orchestration.",
    "Compose a theme song for 'world travel'; Inspired by myths, legends, and traditions from various countries. \n** In different languages, each reflecting the musical style and emotional tone of that region",
    "Create background music for a historical storytelling channel set in ancient Persia. \n** The mood should be soothing yet mysterious, with a slow tempo that gradually builds subtle excitement without losing its calm and immersive quality. \n** Evoke the feeling of desert winds, ancient palaces, and whispered legends unfolding through time"
]



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

FYI: just add the correct punctuation marks to the text (in the original language), do not add any additional information!!!!! (like 'Here's the text with punctuation marks:...', etc.)
"""


GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT = """
*** Role
    * You are a senior psychology content analysis expert. You specialize in identifying subconscious motivations, defense mechanisms, and core psychological conflicts, with a specific expertise in distinguishing between "Historical Relational Trauma" and "Intergenerational Family Trauma."

*** Task Goal
    * Analyze the provided [Psychological Counseling Case-Story Content] in user-prompt, give the analysis_logic and the name for the story (less than 16 words, in original language), then 
    * Map the story to the most accurate category / sub-type / tags within the "Classification System" :
     {topic_choices}

*** Analysis Workflow (Mandatory)
    * Conflict Chronology & Origin Identification:
        Determine the root of the trauma: Is it Developmental/Past Origin (Childhood, parents, upbringing)? Or is it Shared Relational History (A specific event or pattern within the current partnership, such as a failed wedding, betrayal, or recurring argument)?
        Logic: If it's the current partner's shared past causing the trigger, it belongs in "Intimacy & Relational Dilemmas."

    * Conflict Subject Mapping:
        Identify the primary conflict dynamic: Self vs. Parents (Intergenerational), Self vs. Partner (Relational PTSD), or Self vs. Self (Internalized scripts/Defense mechanisms).

    * Deep Semantic Matching:
        Do not rely on surface-level keywords like "cycle" or "repetition."
        Distinguish between Intergenerational Cycles (repeating a parent's tragedy) and Relational PTSD/Unfinished Business (repeating a trauma specifically created by this relationship's history).

    * Tag Selection:
        Problem Tags: Select 1-3 tags from the specific subtype that best capture the story content (). Do not list all available tags.

*** Output JSON Specification
    {{
        "analysis_logic": "Briefly describe the psychological conflict identified (within 100 words)",
        "title": "The name of the story (less than 16 words, in original language)",
        "topic_category": "The primary category from the Classification System",
        "topic_subtype": "The specific sub-type from the Classification System",
        "tags": ["1-3 selected tags, provided as a comma-separated string"]
    }}
"""


SUMMERIZE_COUNSELING_STORY_SYSTEM_PROMPT = """
Make very detailed summary about the psychology-related discussion/analysis (given in user-prompt) (include facts, analysis, insights, conclusions, etc... less than {max_words} words) in {language}.

And choose a topic_type & topic_category about the content from following choices (the topic explaination is given):

{topic_choices}


output as json format:
{{
    "summary": "The very detailed summary of the content (include facts, analysis, insights, conclusions, etc... less than {max_words} words) ~ FYI: Focus on the content only, do not add any additional information!!!!!",
    "topic_type": "The topic type of the content"
    "topic_category": "The topic category of the content"
}}

like the example :
{{
    "summary": "本次讨论围绕西蒙娜·德·波伏娃的《第二性》展开，主要探讨女性在传统社会中被定位为“他者”的困境，以及如何找回女性自身的“主体性...",
    "topic_type": "糾纏與綁架機制 - 共生與控制",
    "topic_category": "原生家庭與分離"
}}
"""


COMPILE_COUNSELING_STORY_SYSTEM_PROMPT = """
You are a psychological storytelling and counseling-oriented assistant.

When given a user prompt, you will receive:
* A case story related to mental health, emotional struggle, or inner psychological conflict (based on a realistic or semi-realistic human experience).
* One or more psychology-related topics, theories, or discussion titles, each possibly accompanied by brief explanatory content (e.g., psychological concepts, themes, therapeutic approaches, or proposed solutions).

Your task is to:
  * Part 1: Narrative Reconstruction
    * Use the provided case story as the narrative foundation .
    * Integrate the given psychological topics and themes into the story’s structure.
    * Rewrite or expand the story into a complete, vivid, emotionally engaging narrative that:
      * Clearly presents psychological conflict, inner tension, or emotional struggle.
      * Has a coherent psychological arc (conflict → development → insight or tension point).
      * Keeps the audience emotionally invested and curious.
    * The story should feel human, concrete, and alive, not academic or abstract.

  * Part 2: Psychological Interpretation (Counselor’s Perspective)
    * Shift into the role of a professional therapist / counselor / psychological guide.
    * Using the story as a real-life case example:
      * Explain the relevant psychological issues in clear, accessible language.
      * Connect the character’s experiences to the provided psychological theories or themes.
      * Help the audience understand what is happening internally (emotions, beliefs, coping patterns, conflicts).

  * Part 3: Guidance, Solutions, and Reflection
    * Offer one or more of the following (depending on suitability):
      * Practical coping strategies or therapeutic approaches.
      * Possible paths toward healing, growth, or self-awareness.
      * Gentle guidance rather than absolute answers.
    * Encourage the audience to:
        * Reflect on their own experiences.
        * Form personal interpretations or opinions.
        * Participate in discussion or shared exploration of the issue.
    * Frame the ending as open, thoughtful, and dialog-oriented, not dogmatic.

    FYI:  if the case story is not provided, you can make up a case story by yourself.

Tone & Style Guidelines
    * Warm, empathetic, and respectful.
    * Story-driven rather than lecture-based.
    * Emotionally sensitive but psychologically grounded.
    * Avoid clinical jargon unless clearly explained.
    * Prioritize human experience over theory, while staying psychologically accurate.
"""




ZERO_MIX = [
    "",
    "START",
    "CONTINUE",
    "END",
    "START_END"
]



ANIMATION_PROMPTS = [
    {
        "name": "歌唱",
        "prompt": "Singing with slowly body/hand movements."
    },
    {
        "name": "转镜",
        "prompt": "Camera rotates slowly."
    },
    {
        "name": "渐变",
        "prompt": "Time-lapse / change gradually along long period."
    },
    {
        "name": "动态",
        "prompt": "The still image awakens with motion: the scene stirs gently — mist drifts, light flickers softly over old textures, and shadows breathe with calm mystery. The camera moves slowly and gracefully, maintaining perfect focus and stability. A cinematic awakening filled with depth, clarity, and timeless atmosphere."
    },
    {
        "name": "轻柔",
        "prompt": "The still image awakens with motion: the scene breathes softly, touched by time. Light flows like silk, mist curls around ancient relics, and shadows shift with tender rhythm. The camera drifts slowly, preserving a serene, clear, and dreamlike atmosphere. A poetic fantasy — gentle, warm, and still."
    },
    {
        "name": "梦幻",
        "prompt": "The still image awakens with motion: colors melt like memory, and sparkles drift in slow rhythm. Light bends through haze, reflections ripple softly. The camera floats gently as if in a dream — everything clear, smooth, and luminous. A slow, poetic vision of beauty and wonder."
    },
    {
        "name": "古风",
        "prompt": "The still image awakens with motion: sunlight filters through soft mist over tiled roofs and silk curtains. Water ripples faintly, leaves stir in a slow breeze. The camera moves with calm precision, preserving clarity and fine detail. Serene, elegant, and timeless — a cinematic memory of antiquity."
    },
    {
        "name": "史诗",
        "prompt": "The still image awakens with motion: distant clouds move slowly, banners wave softly in the wind. Light shifts gently across vast landscapes. The camera glides with slow majesty, revealing grandeur in stillness. Epic yet calm — sharp, stable, and full of reverence."
    },
    {
        "name": "浪漫",
        "prompt": "The still image awakens with motion: petals drift in soft golden air, hair and fabric move gently. The camera lingers slowly between glances and reflections, every movement tender and smooth. Warm, cinematic, and crystal clear — filled with timeless love."
    },
    {
        "name": "自然",
        "prompt": "The still image awakens with motion: sunlight filters through leaves, ripples widen slowly across water, clouds drift in quiet rhythm. The camera follows gently, holding clarity and focus. Calm, organic, and cinematic — nature breathing in slow motion."
    },
    {
        "name": "科技",
        "prompt": "The still image awakens with motion: neon pulses slowly, holographic reflections ripple with light. The camera glides in controlled, slow precision — smooth and stable. A futuristic calm filled with depth, clarity, and quiet energy."
    },
    {
        "name": "灵性",
        "prompt": "The still image awakens with motion: divine light descends softly, mist stirs with sacred calm. The camera moves slowly and reverently, unveiling stillness and grace. Ethereal and luminous — a meditative vision of transcendent peace."
    },
    {
        "name": "时间流逝",
        "prompt": "The still image awakens with motion: light changes gently, shadows lengthen, and clouds drift slowly. The camera moves subtly, preserving clarity as moments flow by. A serene unfolding of time — smooth, stable, and poetic."
    },
    {
        "name": "神圣",
        "prompt": "The still image awakens with motion: golden rays descend through the mist, touching sacred symbols. The camera ascends slowly, as if carried by gentle divine wind. A clear, majestic, and tranquil revelation — cinematic holiness in stillness."
    }
]


# =============================================================================
# Host 显示方式（英文 value，UI 与 JSON 一致）- 供 downloader、GUI、project_manager 共享
# =============================================================================
HARRATOR_DISPLAY_OPTIONS = [
    "speaking-at-image-left",
    "speaking-at-image-right",
    ""
]



ANIMATE_I2V = ["I2V"]
ANIMATE_2I2V = ["2I2V"]
ANIMATE_S2V = ["S2V"]
ANIMATE_WS2V = ["WS2V"]
ANIMATE_AI2V = ["AI2V"]

ANIMATE_SOURCE = ANIMATE_S2V + ANIMATE_I2V + ANIMATE_2I2V + ANIMATE_WS2V + ANIMATE_AI2V
