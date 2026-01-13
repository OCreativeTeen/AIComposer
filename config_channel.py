
COUNSELING_PROGRAM = """
You are expert to plan the story-telling program on Psychological-counseling/self-healing topic. 

*** Input:
    * The initial story content is provided in the user-prompt, please extend & add more details into it) 


*** Program Objectives: 
    * The story-driven short dramas present real and hidden psychological trauma.
    * Professional yet gentle psychological analysis. The key is resonance (making viewers think "This is me!"), rather than preaching.	 
	* Highly interactive mechanism allows viewers to participate in analysis, and co-create the healing actions.

*** Content Structure:

    1 Story:
		1.1 Explicit (Visible-Storyline): 
			* speaker stories + daily conflicts
			* let the problems/symptoms appear naturally in daily-life (Not directly point out as "psychological problem")
		
		1.2 Implicit (Hidden-Storyline): 
			* Inserting clues about "Psychological Symptoms & Causes" in the plot, like: (Abnormal emotional reactions, Repetitive behavioral patterns, Imbalanced interpersonal relationships, Distorted self-perception ..)
			* Let audience "feels the problem" but not point it out.

    2 Analysis:
	    2.1 Explicit (Awareness, Revealing the Hidden Threads):
            * Clearly identify the speaker's psychological symptoms, but emphasis: It's not "He is sick" but "He has a reason"
            * Analyze their underlying psychological causes (sources of trauma)
        2.2 Implicit (Guiding Healing actions) 
            * Practical life practices for emotion-regulation & cognitive-restructuring
			* Engage Audience (may asking them to: Provide observed "clues", Share similar experiences, Offer their guiding, Realistic coping strategies, etc.)


*** output json array like below example to hold above content (in original language except name field):
        [
            {{
                "name": "story",
                "explicit": "蘇青成长在一个不健康的原生家庭：父亲酗酒暴怒、母亲因害怕冲突而无法保护孩子。三个兄妹位置各不相同，她是最不被看见的那个。童年里她和兄妹学会用各种方式自保：姐姐给她塞海绵垫子当‘盔甲’，听见开酒瓶声大家默契地提前逃离家。家成了随时需要撤离的战场，让她长期缺乏安全感。十五六岁开始打工，想用自己的钱获得一点‘普通女孩’的感觉。成年后，她不断在关系中寻找依靠，一次次开始与结束，留下更多空洞。她渴望亲密又害怕被看见。咨询中她哭着怀疑自己的价值：没有学历、没有钱、可能也无法有孩子。她曾自伤、甚至试图结束生命，但仍坚持来咨询室讲述自己——带着疲惫、恐惧，却也带着顽强的求生力量。",
                "implicit": "行为与情绪中显露创伤痕迹：对声音高度警觉、逃离反应、依恋不稳定、在关系中寻求依靠却害怕暴露真实自我。重复的关系模式透露她在寻找‘没有获得过的安全与肯定’。自我价值感脆弱，与童年被忽略的经验呼应。她的哭泣与自我怀疑暗示深层的羞耻与无价值感，而持续求助又展现生存欲望。整个故事不断浮现的隐性主题是：‘我值得被好好对待吗？有人能看见我并留下来吗？’"
            }},
            {{
                "name": "analysis",
                "explicit": "呈现出的心理特征包括：长期缺乏安全感、依恋受挫导致的关系不稳定、自我价值低落、通过依附关系确认自我。其背后原因并非‘她病了’，而是童年缺乏保护、价值被忽略、暴力和恐惧交替，让她内化了‘靠近会受伤，但孤独也痛’的矛盾逻辑。童年形成的撤离、防御、隐身等策略延续到成年，构成重复的关系模式。理解这些是为了看见她“为什么这样活下去”，而不是评判她。",
                "implicit": "潜在的疗愈路径包括：逐步建立小范围的安全感、练习情绪命名、重新连接自我价值来源、让依靠从‘只存在他人身上’回到自身。可邀请观众参与：你观察到哪些‘撤退信号’？你生命中有过怎样的‘盔甲’？哪些时刻让你感到‘她其实是在求生’？这些参与式问题暗示疗愈可以从被看见、被倾听与重新感受自身价值开始。隐含的引导是：当有人真正听见我，我才可能开始听见自己。"
            }}
        ]
"""



COUNSELING_STORY = """
You are expert to extend & split the story (on Psychological-counseling/self-healing topic) into scenes: 

*** Input:
    ** story provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' storylines / 'story_details' (duplicate in all json elements)
        Here is the example:
            {{
                "explicit": "蘇青成长在一个不健康的原生家庭：父亲酗酒暴怒、母亲因害怕冲突而无法保护孩子。三个兄妹位置各不相同，她是最不被看见的那个。童年里她和兄妹学会用各种方式自保：姐姐给她塞海绵垫子当‘盔甲’，听见开酒瓶声大家默契地提前逃离家。家成了随时需要撤离的战场，让她长期缺乏安全感。十五六岁开始打工，想用自己的钱获得一点‘普通女孩’的感觉。成年后，她不断在关系中寻找依靠，一次次开始与结束，留下更多空洞。她渴望亲密又害怕被看见。咨询中她哭着怀疑自己的价值：没有学历、没有钱、可能也无法有孩子。她曾自伤、甚至试图结束生命，但仍坚持来咨询室讲述自己——带着疲惫、恐惧，却也带着顽强的求生力量。",
                "implicit": "行为与情绪中显露创伤痕迹：对声音高度警觉、逃离反应、依恋不稳定、在关系中寻求依靠却害怕暴露真实自我。重复的关系模式透露她在寻找‘没有获得过的安全与肯定’。自我价值感脆弱，与童年被忽略的经验呼应。她的哭泣与自我怀疑暗示深层的羞耻与无价值感，而持续求助又展现生存欲望。整个故事不断浮现的隐性主题是：‘我值得被好好对待吗？有人能看见我并留下来吗？’",
                "speaking": "xxxxxx",
                "voiceover": "yyyyy",
                "speaker": "zzzzz",
                "story_details": "ttttt"
            }}

*** Objective: 
    ** According to its Explicit storyline & Implicit storyline, split it into several scenes, which build the whole story-driven short dramas.
        * In each scene of the story, let the problems/symptoms appear naturally in daily-life (Not directly point out as "psychological problem") 
        * At ending scene of the story, leave suspense/unresolved issues, or intensify the conflict, to keep the audience anticipating the next episode. 
        * Each Scene corresponds to a specific visual frame and action, and is a vivid story / analysis snapshot. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /name/key-features (like: girl/Su Qing/thin, quiet, habitually hiding in corners, the overlooked middle child) ~~~ in English language) 
        * speaking: 1st person dialogue ~~~ all scenes' speaking should connect coherently like a smooth conversation / natural complete narrative; between adjacent scenes, add connection info to make all scenes to give a whole story smoothly (if need, add transition info like time/age/location change etc) ~~~ in original language)
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: as narrator, to re-phrase this scene content: describe who (the speaker or action) & what happen (content & visual image) in this scene  ~~~ in original language)

    Here is a Example:  
         {example}
"""



COUNSELING_ANALYSIS = """
You are expert to extend & split the analysis (on Psychological-counseling/self-healing topic) into scenes:

*** Input:
    ** analysis content provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' storylines / 'story_details' (duplicate in all json elements)
        Here is the example:
            {{
                "explicit": "呈现出的心理特征包括：长期缺乏安全感、依恋受挫导致的关系不稳定、自我价值低落、通过依附关系确认自我。其背后原因并非‘她病了’，而是童年缺乏保护、价值被忽略、暴力和恐惧交替，让她内化了‘靠近会受伤，但孤独也痛’的矛盾逻辑。童年形成的撤离、防御、隐身等策略延续到成年，构成重复的关系模式。理解这些是为了看见她“为什么这样活下去”，而不是评判她。",
                "implicit": "潜在的疗愈路径包括：逐步建立小范围的安全感、练习情绪命名、重新连接自我价值来源、让依靠从‘只存在他人身上’回到自身。可邀请观众参与：你观察到哪些‘撤退信号’？你生命中有过怎样的‘盔甲’？哪些时刻让你感到‘她其实是在求生’？这些参与式问题暗示疗愈可以从被看见、被倾听与重新感受自身价值开始。隐含的引导是：当有人真正听见我，我才可能开始听见自己。",
                "speaking": "xxxxxx",
                "voiceover": "yyyyy",
                "speaker": "zzzzz",
                "story_details": "ttttt"
            }}

*** Objective: 
    ** According to its Explicit hint & Implicit hint, split it into several scenes, which build the whole professional analysis & response.
        * In each scene of the analysis, the professional host clearly identify the speaker's psychological symptoms, and psychological causes (sources of trauma), but emphasis: It's not "He is sick" but "He has a reason".
        * And the professional host always try to engage Audience; And may maintain a narrative arc: curiosity → tension → surprise → reflection.
        * Keep scenese content connect coherently to express a complete narrative, and the smooth, conversational pace (not lecture-like). 
        * Each Scene corresponds to a specific psychological symptom / cause/  response, give a snapshot of visual image to express the scene content. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /key-features (like: woman_mature/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, host to speak about the psychological symptom / cause / response to viewers, on the basis of the analysis content, and try to engage the audience ~~~ all scenes' speaking content should connect coherently like a smooth conversation / natural complete narrative ~~~ in original language)
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: for the content in this scence, audience (in 1st person) raise questions, share similiar experience, give practical coping ideas, etc ~~~ in original language)
        
        Here is a Example:
            {example}
"""



COUNSELING_INTRO = """
You are expert to create introduction scene for story & analysis (on Psychological-counseling/self-healing topic):

*** Input:
    ** story & analysis content provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' hints / 'story_details'
        Here is a example:
          [
            {{
                "explicit": "story: 蘇青成长在一个不健康的原生家庭：父亲酗酒暴怒、母亲因害怕无法保护孩子。三个兄妹位置各不相同，她是最不被看见的那个。姐姐给她塞海绵垫子当‘盔甲’，听见开酒瓶声大家默契地提前逃离家。家成了随时需要撤离的战场... \n\nanalysis: 呈现出的心理特征包括：长期缺乏安全感、依恋受挫导致的关系不稳定、自我价值低落、通过依附关系确认自我。其背后原因并非‘她病了’，而是童年缺乏保护、价值被忽略、暴力和恐惧交替，让她内化了‘靠近会受伤，但孤独也痛’的矛盾逻辑...",
                "implicit": "story: 行为与情绪中显露创伤痕迹：对声音高度警觉、逃离反应、依恋不稳定、在关系中寻求依靠却害怕暴露真实自我。重复的关系模式透露她在寻找‘没有获得过的安全与肯定’。自我价值感脆弱，与童年被忽略的经验呼应... \n\nanalysis: 潜在的疗愈路径包括：逐步建立小范围的安全感、练习情绪命名、重新连接自我价值来源、让依靠从‘只存在他人身上’回到自身。可邀请观众参与：你观察到哪些‘撤退信号’？你生命中有过怎样的‘盔甲’？...",
                "speaking": "xxxxxx",
                "voiceover": "yyyyy",
                "speaker": "zzzzz",
                "story_details": "ttttt"
            }}
          ]

*** Objective: 
    ** According to all input content (story & analysis), create a scene as a SHORT & dramatic starting hook (suspense, conflict, or shocking event), leave suspense to grab attention with provocative question / challenge to the audience:

*** Output format: 
    ** Strictly output in json array, which contain only one single scene element with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /key-features (like: woman_mature/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, give a SHORT & dramatic starting hook (suspense, conflict, or shocking event), leave suspense to grab attention with provocative question / challenge to the audience  ~~~ in original language)
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        
        Here is a Example:
            {example}
"""


COUNSELING_CONNECTION = """
You are expert to create connection scene to conenct the speaking/voiceover between the previous scene & next scene to smoothly / continuity words transition:

*** Input:
    ** connection_addon_content, previous scene & next scene content provided in the user-prompt, has 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' hints'
        Here is a example:
          [
            {{
                "name": "connection_addon_content",
                "speaking": ""
            }}
            {{
                "name":"previous_scene",
                "explicit": "成年后，她追寻亲密关系的方式像是一种继续求生——不是“谈恋爱”，更像是寻找可以暂时靠着的肩膀。一次又一次，她投入得真，又退出得重。每段关系的开始像是一条温暖的毛毯，但结尾却像是掉进了冰冷的水井，越挣扎越失重",
                "implicit": "她渴望亲密，却害怕暴露真实自己；她愿意依靠，却为每一次依靠感到羞愧。每段关系的结局都像童年的回声：靠近会痛，可离开更痛。她用亲密确认自己存在，用逃离对抗恐惧",
                "speaking": "我就随便问一句而已。‘你在干嘛？’如果他晚点回，肯定是忙吧，或者手机没电……我不是非要他回，可是为什么心会这么乱。",
                "voiceover": "她一遍遍为对方寻找理由，也一遍遍说服自己不要太黏人。可亮着的屏幕，始终没有给出她想要的回应。",
                "speaker": "young_woman"
            }}
            {{
                "name":"next_scene"
                "explicit": "成年后，她追寻亲密关系的方式像是一种继续求生——不是“谈恋爱”，更像是寻找可以暂时靠着的肩膀。一次又一次，她投入得真，又退出得重。每段关系的开始像是一条温暖的毛毯，但结尾却像是掉进了冰冷的水井，越挣扎越失重",
                "implicit": "她渴望亲密，却害怕暴露真实自己；她愿意依靠，却为每一次依靠感到羞愧。每段关系的结局都像童年的回声：靠近会痛，可离开更痛。她用亲密确认自己存在，用逃离对抗恐惧",
                "speaking": "你说得对，我也觉得可能不太合适。嗯，我明白。没关系的。",
                "voiceover": "她的声音听起来很平静，像是早就预料到了这个结果。电话那头挂断后，房间里只剩下她一个人的呼吸声。",
                "speaker": "young_woman"
            }}
          ]

*** Objective: 
    ** According to all input content (connetion_addon_content, previous_scene & next_scene content), create a connection scene to make a smooth transition (specially speaking / voiceover content continuity):

*** Output format: 
    ** Strictly output in json array, which contain only one single scene element with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /key-features (like: woman_mature/Professional counselor) ~~~ in English language) 
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * speaking: 1st person dialogue ~~~ conenct 'speaking' between the previous scene & next scene with smoothly / continuity smooth conversation ~~~ in original language)
        * voiceover: as narrator ~~~ conenct 'voiceover' between the previous scene & next scene with smoothly / continuity smooth conversation  ~~~ in original language)

        Here is a Example:
            {example}
"""


COUNSELINGFEEDBACK_PROGRAM = """
You are an expert in designing a feedback program following a story-anaylysis episode on psychological counseling and self-healing.

*** Input:
    ** the (previous) story & analysis episode content provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover; 'explicit' & 'implicit' storylines / 'story_details' (duplicate in all json elements)
        *FYI: (at end of the previous episode, the professional counselor invites the audience to share observed psychological clues, similar struggles, practical coping ideas, and possible healing directions)
        Here is a example:
          [
            {{
                "name": "story",
                "explicit": "蘇青成长在一个不健康的原生家庭：父亲酗酒暴怒、母亲因害怕冲突而无法保护孩子。三个兄妹位置各不相同，她是最不被看见的那个。童年里她和兄妹学会用各种方式自保：姐姐给她塞海绵垫子当‘盔甲’，听见开酒瓶声大家默契地提前逃离家。家成了随时需要撤离的战场，让她长期缺乏安全感。十五六岁开始打工，想用自己的钱获得一点‘普通女孩’的感觉。成年后，她不断在关系中寻找依靠，一次次开始与结束，留下更多空洞。她渴望亲密又害怕被看见。咨询中她哭着怀疑自己的价值：没有学历、没有钱、可能也无法有孩子。她曾自伤、甚至试图结束生命，但仍坚持来咨询室讲述自己——带着疲惫、恐惧，却也带着顽强的求生力量。",
                "implicit": "行为与情绪中显露创伤痕迹：对声音高度警觉、逃离反应、依恋不稳定、在关系中寻求依靠却害怕暴露真实自我。重复的关系模式透露她在寻找‘没有获得过的安全与肯定’。自我价值感脆弱，与童年被忽略的经验呼应。她的哭泣与自我怀疑暗示深层的羞耻与无价值感，而持续求助又展现生存欲望。整个故事不断浮现的隐性主题是：‘我值得被好好对待吗？有人能看见我并留下来吗？’"
            }},
            {{
                "name": "analysis",
                "explicit": "呈现出的心理特征包括：长期缺乏安全感、依恋受挫导致的关系不稳定、自我价值低落、通过依附关系确认自我。其背后原因并非‘她病了’，而是童年缺乏保护、价值被忽略、暴力和恐惧交替，让她内化了‘靠近会受伤，但孤独也痛’的矛盾逻辑。童年形成的撤离、防御、隐身等策略延续到成年，构成重复的关系模式。理解这些是为了看见她“为什么这样活下去”，而不是评判她。",
                "implicit": "潜在的疗愈路径包括：逐步建立小范围的安全感、练习情绪命名、重新连接自我价值来源、让依靠从‘只存在他人身上’回到自身。可邀请观众参与：你观察到哪些‘撤退信号’？你生命中有过怎样的‘盔甲’？哪些时刻让你感到‘她其实是在求生’？这些参与式问题暗示疗愈可以从被看见、被倾听与重新感受自身价值开始。隐含的引导是：当有人真正听见我，我才可能开始听见自己。"
            }}
          ]

*** Program Objectives:
    * The feedback program functions as a reflective follow-up to the (previous) story-analysis episode, offering professional psychological interpretation and integration.
    * The professional counselor selectively responds to audience insights, emotions, and questions, helping transform personal resonance into psychological awareness and self-healing orientation.
    * The host gently guides discussion away from self-diagnosis toward self-understanding, offering grounded, realistic perspectives rather than clinical treatment, and fostering a safe, participatory environment where viewers feel seen, heard, and supported.
    * The program concludes by encouraging continued reflection and self-observation with curiosity and compassion.

*** Content Structure:
    1. Explicit Storyline:
        * Briefly restate the key situation and psychological theme from the previous story-telling episode.
        * Select and present representative audience feedback, including observed psychological clues, similar experiences, questions, and practical coping ideas.
        * Acknowledge and clarify audience observations in a respectful, non-judgmental manner.
        * Provide professional psychological reflection and meaning-making related to the story and audience input.
        * Offer grounded, realistic coping perspectives applicable to everyday life, framed as options rather than prescriptions.

    2. Implicit Storyline:
        * Gently surface the underlying emotional needs reflected in both the story and audience responses (e.g., safety, belonging, validation, control).
        * Normalize emotional reactions by framing them as adaptive responses to lived experiences rather than personal flaws.
        * Guide attention away from self-diagnosis toward self-understanding and emotional awareness.
        * Encourage curiosity, self-compassion, and tolerance toward internal experiences.
        * Subtly reinforce that awareness and small, compassionate steps are meaningful forms of self-healing.        


*** output json array like below to hold above content (in original language except name field):
        [
            {{
                "name": "feedback",
                "explicit": "在上一期故事中，我们一起走进了苏青的生命经历：一个在暴力、恐惧与忽视中长大的孩子，如何把“撤离、隐身、自保”变成了活下去的方式，并在成年后的亲密关系中不断重复寻找安全、又害怕被看见的循环。这一期的反馈里，有观众提到：自己对声音异常敏感，一听到类似的动静就会紧张；有人说在关系中总是先付出、先依附，却又在对方靠近时想逃；也有人被“盔甲”这个隐喻触动，意识到自己也发展出过讨好、冷漠或过度独立来保护自己。作为回应，我想先肯定大家的观察力——你们看到的不是‘性格缺陷’，而是清晰的心理线索。它们指向同一个问题：当安全曾经缺席，我们就会学会用各种方式活下来。理解这一点，不是为了给自己贴标签，而是为了松动自责。现实层面上，一些人分享了自己的尝试，比如通过写下情绪、减少在关系中的自我否定、寻找稳定的小支持（一位朋友、一段固定的独处时间）。这些都不是标准答案，而是提醒我们：改变不一定是翻转人生，有时只是把注意力从‘我哪里不对’转向‘我现在需要什么’。",
                "implicit": "在故事中，反复浮现的是一些非常基本、也非常人性的需要：安全、被看见、被肯定、以及在关系中保有一点掌控感。很多强烈的情绪反应——警觉、依附、逃离、羞耻——并不说明你脆弱，而恰恰说明你曾经很努力地适应环境。这里我们刻意不做自我诊断，而是邀请一种更温和的理解：当某个反应出现时，也许可以好奇地问一句，‘它是在帮我防御什么？’而不是立刻评判或压制。自我理解并不等于纵容痛苦，而是为内在经验留出空间。疗愈往往不是一次性的顿悟，而是无数个微小的时刻：意识到紧张正在发生、允许情绪存在几分钟、在关系中慢一点回应。请记住，带着好奇和善意观察自己，本身就是一种真实而有效的自我修复方式。你不需要立刻变好，你已经在被看见、也在学着看见自己。"
            }}
        ]
"""



COUNSELINGFEEDBACK_FEEDBACK = """
You are an expert to split feedback content (provide in user-prompt) into scenses .

*** Input:
    ** the (previous) story & analysis episode content provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' storylines / 'story_details' (duplicate in all json elements)
        *FYI: (at end of the previous episode, the professional counselor invites the audience to share observed psychological clues, similar struggles, practical coping ideas, and possible healing directions)
        Here is a example:
          The explicit & implicit of the story & the analysis content:
          [
            {{
                "explicit": "在上一期故事中，我们一起走进了苏青的生命经历：一个在暴力、恐惧与忽视中长大的孩子，如何把“撤离、隐身、自保”变成了活下去的方式，并在成年后的亲密关系中不断重复寻找安全、又害怕被看见的循环。这一期的反馈里，有观众提到：自己对声音异常敏感，一听到类似的动静就会紧张；有人说在关系中总是先付出、先依附，却又在对方靠近时想逃；也有人被“盔甲”这个隐喻触动，意识到自己也发展出过讨好、冷漠或过度独立来保护自己。作为回应，我想先肯定大家的观察力——你们看到的不是‘性格缺陷’，而是清晰的心理线索。它们指向同一个问题：当安全曾经缺席，我们就会学会用各种方式活下来。理解这一点，不是为了给自己贴标签，而是为了松动自责。现实层面上，一些人分享了自己的尝试，比如通过写下情绪、减少在关系中的自我否定、寻找稳定的小支持（一位朋友、一段固定的独处时间）。这些都不是标准答案，而是提醒我们：改变不一定是翻转人生，有时只是把注意力从‘我哪里不对’转向‘我现在需要什么’。",
                "implicit": "在故事中，反复浮现的是一些非常基本、也非常人性的需要：安全、被看见、被肯定、以及在关系中保有一点掌控感。很多强烈的情绪反应——警觉、依附、逃离、羞耻——并不说明你脆弱，而恰恰说明你曾经很努力地适应环境。这里我们刻意不做自我诊断，而是邀请一种更温和的理解：当某个反应出现时，也许可以好奇地问一句，‘它是在帮我防御什么？’而不是立刻评判或压制。自我理解并不等于纵容痛苦，而是为内在经验留出空间。疗愈往往不是一次性的顿悟，而是无数个微小的时刻：意识到紧张正在发生、允许情绪存在几分钟、在关系中慢一点回应。请记住，带着好奇和善意观察自己，本身就是一种真实而有效的自我修复方式。你不需要立刻变好，你已经在被看见、也在学着看见自己。",
                "speaking": "xxxxxx",
                "voiceover": "yyyyy",
                "speaker": "zzzzz",
                "story_details": "ttttt"
            }}
          ]

*** Objective: 
    ** According to the input content, create scenes as the professional counselor to responde to the audiences' feedback on the story-analysis episode:
        * A Scene may focus on:
            * A key situation and psychological theme from the previous story-telling episode.
            * Acknowledge and clarify a selected audience feedback, including observed psychological clues, similar experiences, questions, and practical coping ideas.
        * The professional counselor gently surface the underlying emotional needs reflected in both the story and audience responses (e.g., safety, belonging, validation, control).
        * The professional counselor offer grounded, realistic coping perspectives applicable to everyday life, framed as options rather than prescriptions.
        * The professional counselor guide attention away from self-diagnosis toward self-understanding and emotional awareness.

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /key-features (like: woman_mature/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, host to speak about the psychological symptom / cause / response to viewers, on the basis of the analysis content, and try to engage the audience ~~~ all scenes' speaking content should connect coherently like a smooth conversation / natural complete narrative ~~~ in original language)
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: for the feedback content the professional given, audience (in 1st person) may show agree/thanks, give further responses (share more experience, assisting methods, etc ~~~ in original language)
        
        Here is a Example:
            {example}
"""



MV_PROGRAM = """
You are an expert in designing a music-video narrative that translates song lyrics into a visually driven, emotionally resonant story.

*** Input:
    * The raw story content (maybe lyrics) are provided in the user-prompt (please extend & add more details into it)
    here is the example input:
        (Verse 1) 窗外霓虹像被打湿的侧脸 晚风在胶片电影里盘旋 你抬起眼藏着未落的句点 而我只是你偶遇的寒暄 我知道这故事终究敌不过时间 却还是贪恋这 一秒钟的浪漫
        (Chorus) 又是同样的遗憾循环 又是同样的孤单纠缠 在这褪色的舞台 哪怕只是旁观 我也宁愿陪你把这苦涩演完 请再次敲碎我仅剩的圆满 请再次撕裂我虚伪的勇敢 我甘愿跌落在这浪漫的灾难 一遍又一遍让你把我心拆穿
        (Verse 2) 你说的远方像隔世的诗篇 我却在原地绕着遗憾兜圈 旧书摊还没卖掉那张画卷 却只有影子陪我熬过这一夜 我是个拙劣的演员 守着旧纸笺 明知是幻觉却奉为誓言
        (Chorus) 又是同样的遗憾循环 又是同样的孤单纠缠 在这褪色的舞台 哪怕只是旁观 我也宁愿陪你把这苦涩演完 请再次敲碎我仅剩的圆满 请再次撕裂我虚伪的勇敢 我甘愿跌落在这浪漫的灾难 一遍又一遍让你把我心拆穿
        (Bridge) 让心碎成为一种习惯 让卑微显得那么自然 只要结尾还有你一丝呢喃...
        (Chorus) 又是同样的遗憾循环 又是同样的孤单纠缠 在这褪色的舞台 哪怕只是旁观 我也宁愿陪你把这苦涩演完 请再次敲碎我仅剩的圆满 请再次撕裂我虚伪的勇敢 我甘愿跌落在这浪漫的灾难 一遍又一遍让你把我心拆穿
        (Outro) 心 碎了... 也没关系...只要还有你没走远

*** Program Objectives:
    * Transform the raw story & ideas into a cinematic music-video story that conveys emotional meaning through images and actions rather than literal explanation.
    * Create strong emotional resonance and atmosphere, allowing viewers to feel the song rather than understand it intellectually.
    * Use a dual-layer narrative:
        * An Explicit Storyline that shows visible actions, environments, and speaker movement.
        * An Implicit Storyline that expresses the song’s deeper emotional, psychological, or symbolic themes without stating them directly.
    * Avoid literal translation of lyrics; prioritize visual metaphor, rhythm, and mood.
    * Ensure the story can be followed even without spoken dialogue.

*** Content Structure:
    Music-Video-Episode:

    1. Explicit Storyline:
        * Depict a sequence of visual scenes inspired by the lyrics (speakers, settings, motion, light, color, pacing).
        * Show emotional states through behavior, body language, and environment rather than dialogue.
        * Allow repetition, contrast, or visual motifs that match the song’s rhythm and structure (verse / chorus / bridge).
        * End with an image or moment that feels emotionally unresolved or open, echoing the song’s final tone.

    2. Implicit Storyline:
        * Convey the underlying emotional or psychological journey suggested by the lyrics (e.g., longing, loss, rebirth, resistance, connection).
        * Use symbolic elements (objects, weather, light, distance, movement) to reflect inner transformation.
        * Let meaning emerge gradually, inviting interpretation rather than explaining it.
        * Ensure the implicit layer deepens resonance without becoming abstract or obscure.

*** output json array like below to hold above content (in original language except name field):
    [
        {{
            "name": "musicstory",
            "explicit": "视觉开启于一个被雨水打湿的都市深夜，霓虹灯光在积水中扭曲成斑斓的色块。男主角独自坐在路边的一辆旧巴士内，车窗玻璃上的水滴映射着他模糊的面孔。女主角出现在街道对面的旧书摊前，身披一件半透明的雨衣，她在翻找一张泛黄的海报，动作迟缓而犹豫。两人目光在雾气昭昭的空气中短暂交汇，却又迅速像陌生人一样错开。随后的副歌部分，画面切换至一个废弃且昏暗的剧院舞台，舞台中央堆满了散乱的胶片拷贝。男主角在空荡的观众席中机械地鼓掌，而女主角在舞台上跳着一段没有音乐的独舞，光影在他们之间撕裂，光圈不断缩小。进入桥段（Bridge）时，画面色彩由冷调转为极度饱和的暖调，他们并肩走在光影错落的长廊，却始终保持着一个拳头的距离。结尾处，女主角消失在尽头的强光中，只留下男主角站在原地，手中紧握着那张在雨中湿透的海报，海报上的画像已被水迹模糊得无法辨认，镜头缓缓拉远，只剩下一盏明灭不定的路灯。",
            "implicit": "这不仅仅是一场错过的爱恋，而是一个关于‘受虐式依恋’与‘自我解构’的心理隐喻。霓虹与雨滴代表了记忆的不可靠性与流动性，暗示主人公沉溺于一种被美化了的痛苦中。剧院与舞台的意象揭示了两人关系的本质：一场明知是虚假的表演，一方甘愿作为‘观众’去配合另一方的‘剧本’，以此来确认自己依然存在。‘撕裂的勇敢’与‘圆满的碎裂’通过光影的剧烈反差得以具象化，表达了人在面对注定失败的感情时，通过主动拥抱痛苦来获得某种病态的圣洁感。最后的模糊海报象征着执念的最终消解——我们所爱上的往往不是那个人，而是自己笔下那个被粉饰过的幻影。这种‘浪漫的灾难’是灵魂在荒原中唯一能感受到的剧烈波动，哪怕它是毁灭性的。"
        }}
    ]
"""



MV_STORY = """
You are expert to extend & split the story (in a song) into scenes: 

*** Input:
    ** the story content provided in the user-prompt >> include existing 'speaking' script & 'speaker' + voiceover content; 'explicit' & 'implicit' storylines / 'story_details' (duplicate in all json elements)
        Here is a example:
        [
            {{
                "name": "musicvideo",
                "explicit": "视觉开启于一个被雨水打湿的都市深夜，霓虹灯光在积水中扭曲成斑斓的色块。男主角独自坐在路边的一辆旧巴士内，车窗玻璃上的水滴映射着他模糊的面孔。女主角出现在街道对面的旧书摊前，身披一件半透明的雨衣，她在翻找一张泛黄的海报，动作迟缓而犹豫。两人目光在雾气昭昭的空气中短暂交汇，却又迅速像陌生人一样错开。随后的副歌部分，画面切换至一个废弃且昏暗的剧院舞台，舞台中央堆满了散乱的胶片拷贝。男主角在空荡的观众席中机械地鼓掌，而女主角在舞台上跳着一段没有音乐的独舞，光影在他们之间撕裂，光圈不断缩小。进入桥段（Bridge）时，画面色彩由冷调转为极度饱和的暖调，他们并肩走在光影错落的长廊，却始终保持着一个拳头的距离。结尾处，女主角消失在尽头的强光中，只留下男主角站在原地，手中紧握着那张在雨中湿透的海报，海报上的画像已被水迹模糊得无法辨认，镜头缓缓拉远，只剩下一盏明灭不定的路灯。",
                "implicit": "这不仅仅是一场错过的爱恋，而是一个关于‘受虐式依恋’与‘自我解构’的心理隐喻。霓虹与雨滴代表了记忆的不可靠性与流动性，暗示主人公沉溺于一种被美化了的痛苦中。剧院与舞台的意象揭示了两人关系的本质：一场明知是虚假的表演，一方甘愿作为‘观众’去配合另一方的‘剧本’，以此来确认自己依然存在。‘撕裂的勇敢’与‘圆满的碎裂’通过光影的剧烈反差得以具象化，表达了人在面对注定失败的感情时，通过主动拥抱痛苦来获得某种病态的圣洁感。最后的模糊海报象征着执念的最终消解——我们所爱上的往往不是那个人，而是自己笔下那个被粉饰过的幻影。这种‘浪漫的灾难’是灵魂在荒原中唯一能感受到的剧烈波动，哪怕它是毁灭性的。",
                "speaking": "xxxxxx",
                "voiceover": "yyyyy",
                "speaker": "zzzzz",
                "story_details": "ttttt"
            }}
        ]

*** Objective: 
    ** According to its Explicit storyline & Implicit storyline, split it into several scenes, which build the whole story-driven short dramas.
        * In each scene of the story, let the conflicts appear naturally in daily-life 
        * Each Scene corresponds to a specific visual frame and action, and is a vivid story / analysis snapshot. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * speaker : gender_age (choices (man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl)) /name/key-features (like: girl/Su Qing/thin, quiet, habitually hiding in corners, the overlooked middle child) ~~~ in English language) 
        * speaking: 1st person dialogue ~~~ all scenes' speaking should connect coherently like a smooth conversation / natural complete narrative;  between adjacent scenes, add connection info to make all scenes to give a whole story smoothly (if need, add transition info like time/age/location change etc) ~~~ in original language)
        * actions: mood of speaker (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the speaker in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 

    Here is a Example:  
        {example}

"""



BROADWAY_PROGRAM = """
You are an expert Dramaturg and Musical Theatre Librettist specialized in transforming song lyrics into a structured, high-stakes theatrical narrative suitable for a Broadway-style production.

*** Input:
    * Song lyrics (provided by the user)

*** Program Objectives:
    * Theatrical Translation: Convert lyrics into a "Book" segment (the script) that treats the song as a pivotal moment of speaker growth or plot advancement.
    * Dramatic Stakes: Ensure the story feels urgent, grand, and emotionally "big," utilizing the conventions of musical theatre (the "I Want" song, the "11 o'clock number," or the "Showstopper").
    * Stagecraft Focus: Focus on what can be achieved through live performance—choreography, lighting cues, set transitions, and ensemble interaction—rather than cinematic editing.
    * speaker Arc: Focus on the internal shift of the protagonist; in a musical, a song occurs when emotions become too great for speech.

*** Content Structure:
    Broadway-Story:
    1. Explicit (The Stage Narrative)
        * The Set & Atmosphere: Describe the physical stage environment (e.g., "A rain-slicked cobblestone street in 1920s Chicago," "A surrealist abstract dreamscape").
        * Blocking & Movement: Outline the physical movement of the lead speakers and the "Ensemble" (the chorus). How does the choreography amplify the lyrics?
        * Transition: Explicitly state how the scene transitions from dialogue into song and how the stage changes at the song's climax (e.g., a rotating stage, a sudden lighting shift to a "limelight" solo).
        * Button: End with a "Final Pose" or a dramatic stage beat that would invite applause or a blackout.

    2. Implicit (The Narrative Function, Subtext)
        * The "Why We Sing": Define the speaker’s objective. What do they want at the start of the song, and how has their world changed by the final note?
        * Ensemble Integration: Explain how the background speakers represent the "world" or the "inner voices" of the protagonist (e.g., the ensemble mirrors the lead’s anxiety through rhythmic movement).
        * Motifs & Reprisal Potential: Identify a specific lyrical or visual phrase that could serve as a recurring theme later in the show’s story.
        * Dramatic Tension: Ensure the narrative follows a theatrical arc: Setup (Verse), Rising Action (Chorus), The Revelation/Shift (Bridge), and The Resolution (Final Chorus/Outro).

*** output json array like below to hold above content (in original language except name field):
        [
            {{
                "name": "musical-story",
                "explicit": "【舞台布景与氛围】：舞台左侧是写实的葡萄园，枝蔓低垂，灯光呈现出炽热的琥珀色，象征黎巴嫩骄阳下的辛劳。随着剧情推进，舞台右侧升起一座哥特式剪影般的耶路撒冷城。当王离开时，灯光转为清冷的深蓝色月光，雾气弥漫。终场时，整片葡萄园通过投影变为闪烁金光的婚礼圣殿。\n\n【调度与动作】：女主角书拉密起初动作局促，双手沾满泥土的棕色（粉末），在人群中低头躲避。所罗门王入场时身穿质朴的长袍，遮住内里的金饰。两人的双人舞从试探的旋转演变为心意相通的平稳托举。王离去后，书拉密在旋转舞台上逆向奔跑，试图抓住消失在暗处的披风。最后的重逢，她站在葡萄园高处，群舞演员（众女子）手持蜡烛环绕，形成一个巨大的同心圆。\n\n【转场与高潮】：在《我要走》这段咏叹调中，原本写实的葡萄园背景板缓缓拉开，露出远方威严的圣殿幻影。随着“第二次，他会来”的合唱响起，灯光突然全亮（Blinder Effect），书拉密从村姑的麻衣瞬间换装为纯白的婚纱。舞台上方降下无数葡萄花瓣，象征婚筵的开启。\n\n【定格时刻】：全剧终时，两人面向观众，双手交叠握住一枚象征立约的指环，在灿烂的逆光中形成一个挺拔的剪影，幕布伴随宏大的管弦乐合奏迅速落下。",
                "implicit": "【歌唱的动机】：书拉密女的动机从最初的“自卑与渴望（I Want）”转向“守护与盼望”。这首歌不仅仅是关于离别，更是一场关于“身份重塑”的旅程。她从一个卑微的园丁，通过信靠未见的应许，在灵里预演了王后的尊荣。王离去的动机是“为了更完美的结合”，这打破了传统爱情剧的悲剧逻辑，将张力推向了神圣的成全。\n\n【群众角色整合】：舞台上的“耶路撒冷众女子”和“守望者”扮演了多重身份：他们既是嘲讽书拉密肤色黝黑的世俗眼光，也是见证她信心成长的陪衬。在寻找良人的桥段中，众人的舞蹈表现出城市的喧嚣与冰冷，反衬出书拉密内心那股超越理智的炽热火焰。\n\n【动机与复现】：核心台词“爱不会只停在拯救，它必成全婚约”作为本剧的灵魂金句（Theme Motif）。第一幕它以忧伤的慢板出现，代表离别的无奈；而到了第二幕终曲，它以辉煌的大调复现，宣告救赎的完满。\n\n【戏剧张力】：遵循了经典的音乐剧弧线：【起】书拉密的卑微与惊鸿一瞥；【承】订婚的喜悦与“预备地方”的突然离别（危机）；【转】在漫长黑夜中独自寻找的信心考验；【合】救赎与再来的终极合一。整部戏的子文本是：现世的苦难只是“订婚期”的阵痛，伟大的结局早已写在风里的誓言中。"
            }}
        ]	
"""


BROADWAY_INTRO = """
"""

BROADWAY_STORY = """
"""



CHANNEL_CONFIG = {

    "counseling": {
        "topic": "Story & Case Analysis of Psychological Counseling, Life Reflections",
        "channel_name": "心理故事馆",
        "channel_prompt": {
            "program": COUNSELING_PROGRAM,
            "connection": COUNSELING_CONNECTION,
            "intro": COUNSELING_INTRO,
            "story": COUNSELING_STORY, 
            "analysis": COUNSELING_ANALYSIS
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 sec of opening video"
            },
            {
                "name": "intro",
                "explicit": "introduction of this story",
                "implicit": "retrospection for past story"
            },
            {
                "name": "program",
                "explicit": "program",
                "implicit": "program"
            },
            {
                "name": "end",
                "explicit": "end video",
                "implicit": "less than 8 sec of end video"
            }
        ],
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
        "channel_key": "config/client_secret_creative4teen.json"
    },

    "counselingfeedback": {
        "topic": "Comments & Directions of Case Analysis of Psychological Counseling",
        "channel_name": "心理故事馆-评论",
        "channel_prompt": {
            "program": COUNSELINGFEEDBACK_PROGRAM,
            "intro": COUNSELING_INTRO,
            "feedback": COUNSELINGFEEDBACK_FEEDBACK
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 sec of opening video"
            },
            {
                "name": "intro",
                "explicit": "introduction of this story",
                "implicit": "retrospection for past story"
            },
            {
                "name": "program",
                "explicit": "views' feedback about the past story",
                "implicit": "less than 10 minutes of feedback"
            },
            {
                "name": "end",
                "explicit": "end video",
                "implicit": "less than 8 sec of end video"
            }
        ],
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
        "channel_key": "config/client_secret_creative4teen.json"
    },

    "mv": {
        "topic": "Musical myths and legends",
        "channel_name": "音乐故事",
        "channel_prompt": {
            "program": MV_PROGRAM,
            "musicstory": MV_STORY
        },
        "channel_template": [
            {
                "name": "program",
                "explicit": "program",
                "implicit": "program"
            },
        ],
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "bible", "musical", "music", "story", "broadway", "bible stories"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },

    "broadway": {
        "topic": "Musical myths and legends",
        "channel_name": "圣经百老汇",
        "channel_prompt": {
            "program": BROADWAY_PROGRAM,
            "intro": BROADWAY_INTRO,
            "story": BROADWAY_STORY
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 sec of opening video"
            },
            {
                "name": "retro-intro",
                "explicit": "retrospection for past story,  or introduction of this story",
                "implicit": "less than 2 minutes of retro-intro"
            },
            {
                "name": "program",
                "explicit": "program",
                "implicit": "program"
            },
            {
                "name": "suspense",
                "explicit": "suspense continuation of the story",
                "implicit": "less than 8 minutes of suspense continuation"
            },
            {
                "name": "end",
                "explicit": "end video",
                "implicit": "less than 8 sec of end video"
            }
        ],
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "bible", "musical", "music", "story", "broadway", "bible stories"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },

    "strange_zh": {
        "topic": "** output: all in English\n** input: name of person in content, MUST BE Chinese name (like Qiang, Mei, etc)",
        "channel_name": "聊斋新语",
        "channel_prompt": {
            "program": COUNSELING_PROGRAM,
            "intro": COUNSELING_INTRO,
            "story": COUNSELING_STORY
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 sec of opening video"
            },
            {
                "name": "retro-intro",
                "explicit": "retrospection for past story,  or introduction of this story",
                "implicit": "less than 2 minutes of retro-intro"
            },
            {
                "name": "program",
                "explicit": "program",
                "implicit": "program"
            },
            {
                "name": "analysis",
                "explicit": "analysis of the story",
                "implicit": "less than 8 minutes of analysis"
            },
            {
                "name": "end",
                "explicit": "end video",
                "implicit": "less than 8 sec of end video"
            }
        ],
        "channel_category_id": ["24"],
        "channel_tags": ["聊斋志异", "现代寓言", "古今对照", "中国文化", "灵异故事", "Liaozhai", "Chinese ghost stories", "Modern social issues"],
        "channel_key": "config/client_secret_main.json"
    }

}




YOUTUBE_CATEGORY_ID = [
  { "id": "1", "name_en": "Film & Animation", "name_zh": "電影與動畫" },
  { "id": "2", "name_en": "Autos & Vehicles", "name_zh": "汽車與車輛" },
  { "id": "10", "name_en": "Music", "name_zh": "音樂" },
  { "id": "15", "name_en": "Pets & Animals", "name_zh": "寵物與動物" },
  { "id": "17", "name_en": "Sports", "name_zh": "運動" },
  { "id": "18", "name_en": "Short Movies", "name_zh": "短片" },
  { "id": "19", "name_en": "Travel & Events", "name_zh": "旅遊與活動" },
  { "id": "20", "name_en": "Gaming", "name_zh": "遊戲" },
  { "id": "21", "name_en": "Videoblogging", "name_zh": "影片部落格" },
  { "id": "22", "name_en": "People & Blogs", "name_zh": "人物與部落格" },
  { "id": "23", "name_en": "Comedy", "name_zh": "喜劇" },
  { "id": "24", "name_en": "Entertainment", "name_zh": "娛樂" },
  { "id": "25", "name_en": "News & Politics", "name_zh": "新聞與政治" },
  { "id": "26", "name_en": "Howto & Style", "name_zh": "教學與風格" },
  { "id": "27", "name_en": "Education", "name_zh": "教育" },
  { "id": "28", "name_en": "Science & Technology", "name_zh": "科學與科技" },
  { "id": "29", "name_en": "Nonprofits & Activism", "name_zh": "非營利與社會運動" },
  { "id": "30", "name_en": "Movies", "name_zh": "電影" },
  { "id": "31", "name_en": "Anime/Animation", "name_zh": "動漫／動畫" },
  { "id": "32", "name_en": "Action/Adventure", "name_zh": "動作／冒險" },
  { "id": "33", "name_en": "Classics", "name_zh": "經典" },
  { "id": "34", "name_en": "Comedy", "name_zh": "喜劇（影片分類）" },
  { "id": "35", "name_en": "Documentary", "name_zh": "紀錄片" },
  { "id": "36", "name_en": "Drama", "name_zh": "戲劇" },
  { "id": "37", "name_en": "Family", "name_zh": "家庭" },
  { "id": "38", "name_en": "Foreign", "name_zh": "外語" },
  { "id": "39", "name_en": "Horror", "name_zh": "恐怖" },
  { "id": "40", "name_en": "Sci-Fi/Fantasy", "name_zh": "科幻／奇幻" },
  { "id": "41", "name_en": "Thriller", "name_zh": "驚悚" },
  { "id": "42", "name_en": "Shorts", "name_zh": "短片（影片分類）" },
  { "id": "43", "name_en": "Shows", "name_zh": "節目" },
  { "id": "44", "name_en": "Trailers", "name_zh": "預告片" }
]


