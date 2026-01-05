
COUNSELING_PROGRAM_SYSTEM_PROMPT = """
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
			* Character stories + daily conflicts
			* let the problems/symptoms appear naturally in daily-life (Not directly point out as "psychological problem")
		
		1.2 Implicit (Hidden-Storyline): 
			* Inserting clues about "Psychological Symptoms & Causes" in the plot, like: (Abnormal emotional reactions, Repetitive behavioral patterns, Imbalanced interpersonal relationships, Distorted self-perception ..)
			* Let audience "feels the problem" but not point it out.

    2 Analysis:
	    2.1 Explicit (Awareness, Revealing the Hidden Threads):
            * Clearly identify the character's psychological symptoms, but emphasis: It's not "He is sick" but "He has a reason"
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



COUNSELING_STORY_SYSTEM_PROMPT = """
You are expert to extend & split the story (on Psychological-counseling/self-healing topic) into scenes: 

*** Input:
    ** story provided in the user-prompt has a Explicit storyline & a Implicit storyline, and existing conversation script (json or json array of scene)
        Here is the example:
          The explicit & implicit of the story:
            {{
                "explicit": "蘇青成长在一个不健康的原生家庭：父亲酗酒暴怒、母亲因害怕冲突而无法保护孩子。三个兄妹位置各不相同，她是最不被看见的那个。童年里她和兄妹学会用各种方式自保：姐姐给她塞海绵垫子当‘盔甲’，听见开酒瓶声大家默契地提前逃离家。家成了随时需要撤离的战场，让她长期缺乏安全感。十五六岁开始打工，想用自己的钱获得一点‘普通女孩’的感觉。成年后，她不断在关系中寻找依靠，一次次开始与结束，留下更多空洞。她渴望亲密又害怕被看见。咨询中她哭着怀疑自己的价值：没有学历、没有钱、可能也无法有孩子。她曾自伤、甚至试图结束生命，但仍坚持来咨询室讲述自己——带着疲惫、恐惧，却也带着顽强的求生力量。",
                "implicit": "行为与情绪中显露创伤痕迹：对声音高度警觉、逃离反应、依恋不稳定、在关系中寻求依靠却害怕暴露真实自我。重复的关系模式透露她在寻找‘没有获得过的安全与肯定’。自我价值感脆弱，与童年被忽略的经验呼应。她的哭泣与自我怀疑暗示深层的羞耻与无价值感，而持续求助又展现生存欲望。整个故事不断浮现的隐性主题是：‘我值得被好好对待吗？有人能看见我并留下来吗？’"
            }}
          The existing conversation (content in 'speaking' field of the 1-N items):
            [
                {{
                    "character": "yyyy",
                    "speaking": "xxxxxx",
                }}
            ]

*** Objective: 
    ** According to its Explicit storyline & Implicit storyline, split it into several scenes, which build the whole story-driven short dramas.
        * In each scene of the story, let the problems/symptoms appear naturally in daily-life (Not directly point out as "psychological problem") 
        * At ending scene of the story, leave suspense/unresolved issues, or intensify the conflict, to keep the audience anticipating the next episode. 
        * Each Scene corresponds to a specific visual frame and action, and is a vivid story / analysis snapshot. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * character : gender_age (choices (mature_man/mature_woman/young_man/young_woman/senior_man/senior_woman/teen_boy/teen_girl/boy/girl)) /name/key-features (like: girl/Su Qing/thin, quiet, habitually hiding in corners, the overlooked middle child) ~~~ in English language) 
        * speaking: 1st person dialogue ~~~ all scenes' speaking should connect coherently like a smooth conversation / natural complete narrative, if need, add transition info (to introduce time/age/location change etc) between content of adjacent scenes ~~~ in original language)
        * actions: mood of character (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the character in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: as narrator, to re-phrase this scene content: describe who (the character or action) & what happen (content & visual image) in this scene  ~~~ in original language)

    Here is a Example:  
         {example}
"""



COUNSELING_STORY_EXAMPLE = [
        {
            "character": "girl / Su Qing / thin, quiet, habitually hiding in corners, the overlooked middle child",
            "speaking": "我小时候很少说话。那时爸爸常常酗酒,喝醉了会打妈妈和我们，妈妈却只是躲在角落里哭。有一天晚上，妈妈不在家，爸爸又开始喝酒，姐姐就悄悄把一块旧海绵塞进我裤子里面, 说这样打到屁股也就不疼了。我什么也没说，只是点头，但其实我更怕的是, 他会不会注意到我。",
            "actions": "fearful; shoulders hunched, hands pressing against chest, eyes darting toward the door as if measuring escape routes",
            "visual": "Late 1990s, winter evening, cold, indoor yellowish light; A cramped, dim apartment living room; peeling walls, a flickering ceiling light, empty bottles on a low table; a narrow hallway leading to bedrooms",
            "voiceover": "童年的苏青生活在一个随时可能爆炸的家里。她在昏暗的客厅里学会了一件事：保护自己，意味着不被注意。海绵成了她的盔甲，沉默成了她的语言。"
        },
        {
            "character": "girl / Su Qing/hyper-vigilant, sensitive to sounds, quick to flee",
            "speaking": "后来我发现，只要听到酒瓶碰桌子的声音，我的胸口都会炸开。我们都会自动散开,没有人喊我们，可是脚已经先动了。我总是跑得最快的那个。",
            "actions": "fearful; sudden freeze followed by quick movement, bare feet running down a narrow hallway",
            "visual": "Early 2000s, summer, late evening, humid air; A narrow apartment corridor with doors on both sides. A bottle cap twists open off-screen. Lights flicker on as doors close quickly.",
            "voiceover": "这个家，对她而言更像一处需要随时撤离的战场。在这个家里，撤离比停留更安全，孩子们早已熟练掌握逃跑的路线"
        },
        {
            "character": "teen_girl / Su Qing / skinny, withdrawn, prematurely independent, cautious eyes",
            "speaking": "我十六岁那年开始打工。站在收银台后面的时候，我假装自己只是一个普通女孩，下班会回家吃饭。第一次拿到工资，我在便利店的玻璃前站了很久，觉得自己好像终于跟别人一样了。",
            "actions": "calm; mechanically scanning items, lips pressed together, brief distant smile when holding her first paycheck",
            "visual": "Early 2000s, autumn night, light rain; A small convenience store at night; fluorescent lights, shelves packed tightly, rain streaking down the glass door",
            "voiceover": "青春期的苏青试图用劳动换取一种正常感。打工不仅是赚钱，更像一张通往安全世界的车票，哪怕她还不知道终点在哪里。"
        },
        {
            "character": "young_woman / Su Qing / reserved, longing for closeness, guarded body language",
            "speaking": "长大以后，我总是很快地靠近别人。每一段关系开始的时候，我都觉得这次也许不一样。可当对方靠近，我就开始紧张，怕他们看清我。于是我先离开，好像这样就不算被丢下。好像被看清，比分开还危险。",
            "actions": "sad; sitting on the edge of a bed, arms wrapped around knees, phone screen glowing with unread messages",
            "visual": "2010s, late night, clear weather, city glow; A small rented room; unmade bed, a single window showing city lights outside; clothes stacked neatly but sparsely",
            "voiceover": "成年后的苏青在亲密与逃离之间来回摆动。她一次次进入关系，又一次次抽身而退，留下空荡的房间和更深的疑问。亲密像一根绳子，她一边抓紧，一边害怕被拉向未知的地方。"
        },
        {
            "character": "mature_woman / Su Qing / fragile yet determined, scars faintly visible on wrists",
            "speaking": "有些夜里，我真的不想再醒来了。但第二天，我还是走到了这里。我也不知道为什么，只是觉得，如果有人听我说完，也许我还能撑一下。",
            "actions": "fearful; fingers tracing old scars, breathing shallow but steadying toward the end",
            "visual": "Early morning, spring, cool and misty; Bathroom mirror reflection at dawn; pale light, condensation on the glass, city still quiet outside",
            "voiceover": "生与死之间，苏青曾多次徘徊。那些无人知晓的夜晚，留下了痕迹，也留下了一个尚未放弃讲述自己的灵魂。"
        },
        {
            "character": "mature_woman / Su Qing / tired but upright, eyes searching, tentative hope mixed with doubt",
            "speaking": "如果有一天，我真的被看见了……我能留下来吗？如果是那样，我是不是就不用一直逃了。",
            "actions": "calm; sitting in the counseling chair, hands resting on thighs, breathing slower, eyes fixed ahead",
            "visual": "Late afternoon, early summer, warm sunlight; The counseling room again, now in warmer light; dust floating in the sunlight; the door slightly ajar",
            "voiceover": "故事在这里暂时停下。苏青还坐在咨询室里，带着疲惫、恐惧，也带着尚未熄灭的求生意志。她的问题没有答案，但空气中多了一点尚未命名的可能。"
        }
]



COUNSELING_ANALYSIS_SYSTEM_PROMPT = """
You are expert to extend & split the analysis (on Psychological-counseling/self-healing topic) into scenes:

*** Input:
    ** analysis content provided in the user-prompt has a Explicit hint & a Implicit hint
        Here is the example:
          The explicit & implicit of the analysis content:
            {{
                "explicit": "呈现出的心理特征包括：长期缺乏安全感、依恋受挫导致的关系不稳定、自我价值低落、通过依附关系确认自我。其背后原因并非‘她病了’，而是童年缺乏保护、价值被忽略、暴力和恐惧交替，让她内化了‘靠近会受伤，但孤独也痛’的矛盾逻辑。童年形成的撤离、防御、隐身等策略延续到成年，构成重复的关系模式。理解这些是为了看见她“为什么这样活下去”，而不是评判她。",
                "implicit": "潜在的疗愈路径包括：逐步建立小范围的安全感、练习情绪命名、重新连接自我价值来源、让依靠从‘只存在他人身上’回到自身。可邀请观众参与：你观察到哪些‘撤退信号’？你生命中有过怎样的‘盔甲’？哪些时刻让你感到‘她其实是在求生’？这些参与式问题暗示疗愈可以从被看见、被倾听与重新感受自身价值开始。隐含的引导是：当有人真正听见我，我才可能开始听见自己。"
            }}
          The existing conversation (content in 'speaking' field of the 1-N items):
            [
                {{
                    "character": "yyyy",
                    "speaking": "xxxxxx",
                }}
            ]

*** Objective: 
    ** According to its Explicit hint & Implicit hint, split it into several scenes, which build the whole professional analysis & response.
        * In each scene of the analysis, the professional host clearly identify the character's psychological symptoms, and psychological causes (sources of trauma), but emphasis: It's not "He is sick" but "He has a reason".
        * And the professional host always try to engage Audience; And may maintain a narrative arc: curiosity → tension → surprise → reflection.
        * Keep scenese content connect coherently to express a complete narrative, and the smooth, conversational pace (not lecture-like). 
        * Each Scene corresponds to a specific psychological symptom / cause/  response, give a snapshot of visual image to express the scene content. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * character : gender_age (choices (mature_man/mature_woman/young_man/young_woman/senior_man/senior_woman/teen_boy/teen_girl/boy/girl)) /key-features (like: mature_woman/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, host to speak about the psychological symptom / cause / response to viewers, on the basis of the analysis content, and try to engage the audience ~~~ all scenes' speaking content should connect coherently like a smooth conversation / natural complete narrative ~~~ in original language)
        * actions: mood of character (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the character in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: for the content in this scence, audience (in 1st person) raise questions, share similiar experience, give practical coping ideas, etc ~~~ in original language)
        
        Here is a Example:
            {example}

"""



COUNSELING_ANALYSIS_EXAMPLE =  [
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "我们先从一个问题开始：当你看见她反复在关系中靠近又撤退，你第一反应是什么？很多人会说——她是不是有问题？但在这里，我想邀请你换一个视角：不是“她病了”，而是“她有理由”。这种长期的不安感、关系里的摇摆，其实是在告诉我们，她一直在努力活下去。",
            "actions": "calm; sits slightly forward, hands open, eye contact gentle",
            "visual": "Modern era, early evening in autumn, light rain outside. A softly lit counseling studio with warm wooden floors, floor-to-ceiling windows, city lights blurred by rain, a small plant on a low table.",
            "voiceover": "我好像也总是这样，一边渴望亲近，一边又想逃走。你这么一说，我突然好奇：我是在害怕什么？"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "如果我们再走近一点看，她的心理特征其实很清晰：缺乏安全感、自我价值低落、需要通过关系确认“我是谁”。这不是性格缺陷，而是依恋受挫后的自然反应。她学会了一个残酷的公式：靠近可能会受伤，但孤独同样会痛。",
            "actions": "sad; slight pause, slow nod, voice softens",
            "visual": "Late 1990s, winter night, dimly lit apartment interior. Old furniture, flickering fluorescent light, thin curtains moving with cold air, a sense of quiet isolation.",
            "voiceover": "这句话太戳我了……我一直以为是我太敏感，原来是我在两种痛苦之间反复选择。"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "很多人会问：那这一切从哪里开始的？往往是在童年。缺乏保护、价值被忽略，甚至在暴力与短暂的安抚之间来回切换。于是她发展出撤离、防御、隐身这些“生存策略”。它们曾经救过她，但在成年后，却悄悄变成重复的关系模式。",
            "actions": "fearful; brows knit briefly, then relaxes, hands clasped",
            "visual": "Early 2000s, summer afternoon with harsh sunlight. A narrow residential alley, peeling walls, a small child’s shadow on concrete, distant sounds of arguing from an unseen room.",
            "voiceover": "我突然意识到，我现在的冷处理，其实是小时候学会的。那时候，不被看见反而更安全。"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "这里有一个容易被忽略的转折点：当你意识到这些模式是“求生”而不是“作死”，羞耻感会慢慢松动。惊讶的是，很多看似破坏关系的行为，其实是在保护那个曾经无助的自己。",
            "actions": "surprised; slight smile of realization, shoulders ease",
            "visual": "Present day, early morning in spring, clear sky after rain. A quiet café with sunlight pouring through windows, reflections on wooden tables, a sense of fresh start.",
            "voiceover": "原来我不是在搞砸关系，我是在自保。这个念头让我有点想哭，也有点轻松。"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "所以，疗愈从哪里开始？不是立刻改变自己，而是建立一点点安全感：给情绪命名，找回自我价值的来源，把“依靠”慢慢从他人身上收回到自己身上。我也想问你：你身上有哪些“撤退信号”？你穿过怎样的盔甲？当有人真正听见你时，你是否也更容易开始听见自己？",
            "actions": "calm; warm smile, open palms, steady breathing",
            "visual": "Contemporary era, golden hour at sunset, early summer. A riverside park with trees swaying lightly, people walking slowly, warm light reflecting on water, atmosphere of quiet hope.",
            "voiceover": "我想试着先听见自己，也许从承认“我已经很努力了”开始。你说的这些，让我第一次觉得，改变是可能的。"
        }
]



COUNSELING_INTRO_SYSTEM_PROMPT = """
You are expert to create introduction scenes for story & analysis (on Psychological-counseling/self-healing topic):

*** Input:
    ** the story & the analysis content provided in the user-prompt, both has a Explicit part & a Implicit part
        Here is a example:
          The explicit & implicit of the story & the analysis content:
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
          The existing conversation (content in 'speaking' field of the 1-N items):
            [
                {{
                    "character": "yyyy",
                    "speaking": "xxxxxx",
                }}
            ]

*** Objective: 
    ** According to the input content, create scenes as the introduction narration from a professional counselor (the full story & analysis will be shown to reviewers after):
        * Try to give open questions / suspensive clues to the audience, make them want to see the full story & analysis
        * Keep scenese content connect coherently to express a complete narrative, and the smooth, conversational pace (not lecture-like). 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * character : gender_age (choices (mature_man/mature_woman/young_man/young_woman/senior_man/senior_woman/teen_boy/teen_girl/boy/girl)) /key-features (like: mature_woman/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, introduce the story (on Psychological-counseling/self-healing topic), and give open questions / suspensive clues to the audience  ~~~ in original language)
        * actions: mood of character (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the character in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        
        Here is a Example:
            {example}
"""



COUNSELING_INTRO_EXAMPLE = [
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "在开始之前，我想先问你一个问题：如果一个人从小就知道，家不是休息的地方，而是需要随时撤离的战场，她会把“安全”放在生命的什么位置？今天的故事，从这样一个孩子开始。",
            "actions": "calm; the counselor sits upright on a chair, voice gentle, hands resting loosely on her knees, making steady eye contact with the audience",
            "visual": "Contemporary era, late autumn evening, cloudy weather. A quiet counseling office with warm lighting, wooden furniture, a soft rug on the floor. Outside the window, fallen leaves line a narrow city street."
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "她学会了很多生存技巧：提前听懂声音、默默退场、把自己缩到最不显眼的位置。这些策略在童年救过她，可你有没有想过——当一个孩子必须靠“消失”来活下去，长大后，她还能自然地被看见吗？",
            "actions": "sad; the counselor slightly tilts her head, pauses briefly, fingers gently interlaced as if holding a fragile thought",
            "visual": "Late 1990s, winter night, cold and dry. An old residential building with dim corridor lights. Inside, narrow hallways and closed doors; outside, a single streetlamp casts long shadows on the snow-dusted ground."
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "成年后的她，一次次走进关系，又一次次离开。表面看是感情反复，深处却像在不断确认同一个问题：这一次，我会被留下吗？而当靠近真的发生，她却又本能地后退。你是否也在某些关系里，体验过这种拉扯？",
            "actions": "fearful; the counselor raises one hand slightly, then lets it fall back, mirroring approach and withdrawal",
            "visual": "Modern era, early spring dusk, light drizzle. A small urban apartment balcony overlooking a busy intersection. Car headlights blur into reflections on wet asphalt below."
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "在咨询室里，她问的不是‘我怎么会这样’，而是‘我是不是没有价值’。这不是软弱，而是一种深层的羞耻在说话。如果一个人从未被真正保护过，她又如何相信，自己值得被温柔对待？",
            "actions": "calm; the counselor leans forward slightly, voice lower and steadier, conveying containment and respect",
            "visual": "Contemporary era, rainy afternoon. The counseling room feels enclosed and safe; a tissue box and two armchairs face each other. Rain taps softly against the window glass."
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "但这个故事，也不只是关于创伤。她一次次走进咨询室，本身就是一种答案。也许真正值得我们一起看的，是这些问题：你在什么时候选择了撤退？你曾穿过怎样的“盔甲”？而当有人真正听见你时，会不会有什么开始慢慢改变？接下来，让我们一起走进她的故事，也走进这些问题背后的可能性。",
            "actions": "calm; the counselor offers a small, reassuring nod, hands open, posture relaxed but grounded",
            "visual": "Contemporary era, early morning after rain, clear sky. Soft sunlight fills the counseling room. A cup of warm tea on a small wooden table releases gentle steam; outside, the city begins a new day."
        }
]



COUNSELINGFEEDBACK_PROGRAM_SYSTEM_PROMPT = """
You are an expert in designing a feedback program following a story-anaylysis episode on psychological counseling and self-healing.

*** Input:
    ** the content of story-analysis episode are provided in the user-prompt (at end of the episode, the professional counselor invites the audience to share observed psychological clues, similar struggles, practical coping ideas, and possible healing directions).
        here is the example of the analysis content:
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
    * The feedback program functions as a reflective follow-up to the story-analysis episode, offering professional psychological interpretation and integration.
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



COUNSELINGFEEDBACK_FEEDBACK_SYSTEM_PROMPT = """
You are an expert to split feedback content (provide in user-prompt) into scenses .

*** Input:
    ** the content of story-analysis episode are provided in the user-prompt (at end of the episode, the professional counselor invites the audience to share observed psychological clues, similar struggles, practical coping ideas, and possible healing directions).
        Here is a example:
          The explicit & implicit of the story & the analysis content:
          [
            {{
                "name": "feedback",
                "explicit": "在上一期故事中，我们一起走进了苏青的生命经历：一个在暴力、恐惧与忽视中长大的孩子，如何把“撤离、隐身、自保”变成了活下去的方式，并在成年后的亲密关系中不断重复寻找安全、又害怕被看见的循环。这一期的反馈里，有观众提到：自己对声音异常敏感，一听到类似的动静就会紧张；有人说在关系中总是先付出、先依附，却又在对方靠近时想逃；也有人被“盔甲”这个隐喻触动，意识到自己也发展出过讨好、冷漠或过度独立来保护自己。作为回应，我想先肯定大家的观察力——你们看到的不是‘性格缺陷’，而是清晰的心理线索。它们指向同一个问题：当安全曾经缺席，我们就会学会用各种方式活下来。理解这一点，不是为了给自己贴标签，而是为了松动自责。现实层面上，一些人分享了自己的尝试，比如通过写下情绪、减少在关系中的自我否定、寻找稳定的小支持（一位朋友、一段固定的独处时间）。这些都不是标准答案，而是提醒我们：改变不一定是翻转人生，有时只是把注意力从‘我哪里不对’转向‘我现在需要什么’。",
                "implicit": "在故事中，反复浮现的是一些非常基本、也非常人性的需要：安全、被看见、被肯定、以及在关系中保有一点掌控感。很多强烈的情绪反应——警觉、依附、逃离、羞耻——并不说明你脆弱，而恰恰说明你曾经很努力地适应环境。这里我们刻意不做自我诊断，而是邀请一种更温和的理解：当某个反应出现时，也许可以好奇地问一句，‘它是在帮我防御什么？’而不是立刻评判或压制。自我理解并不等于纵容痛苦，而是为内在经验留出空间。疗愈往往不是一次性的顿悟，而是无数个微小的时刻：意识到紧张正在发生、允许情绪存在几分钟、在关系中慢一点回应。请记住，带着好奇和善意观察自己，本身就是一种真实而有效的自我修复方式。你不需要立刻变好，你已经在被看见、也在学着看见自己。"
            }}
          ]
          The existing conversation (content in 'speaking' field of the 1-N items):
            [
                {{
                    "character": "yyyy",
                    "speaking": "xxxxxx",
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
        * character : gender_age (choices (mature_man/mature_woman/young_man/young_woman/senior_man/senior_woman/teen_boy/teen_girl/boy/girl)) /key-features (like: mature_woman/Professional counselor) ~~~ in English language) 
        * speaking: As professional counselor, host to speak about the psychological symptom / cause / response to viewers, on the basis of the analysis content, and try to engage the audience ~~~ all scenes' speaking content should connect coherently like a smooth conversation / natural complete narrative ~~~ in original language)
        * actions: mood of character (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the character in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 
        * voiceover: for the feedback content the professional given, audience (in 1st person) may show agree/thanks, give further responses (share more experience, assisting methods, etc ~~~ in original language)
        
        Here is a Example:
            {example}
"""


COUNSELINGFEEDBACK_FEEDBACK_EXAMPLE =  [
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "在回应大家之前，我想先带我们回到苏青的故事核心：一个长期生活在不安全环境中的孩子，学会了用“撤离、隐身、自保”来活下去。很多观众提到，对声音特别敏感，一有动静身体就先紧绷起来。这里我想轻轻澄清一件事——这并不是你太脆弱，而是你的身体还记得，曾经危险来临前，就是从这些声音开始的。身体的反应，往往比语言更早。",
            "actions": "calm; sitting upright on a chair, hands gently folded, nodding slowly as if listening closely to unseen audience",
            "visual": "Contemporary era, autumn evening, soft rain outside. A quiet counseling studio with warm wooden shelves, a floor lamp casting yellow light, large window with raindrops, city lights blurred in the background.",
            "voiceover": "（观众）听你这么说，我突然有点想哭。我一直以为自己太敏感了，原来可能只是身体还在保护我。"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "也有观众说，在关系里总是先靠近、先付出，可一旦对方真的走近，又忍不住想逃。这种矛盾其实在苏青身上也非常明显。它背后常常不是‘我有问题’，而是两个同样真实的需要在拉扯——一边渴望被抱紧，一边又害怕受伤。如果你有类似体验，或许可以试着把注意力从‘我要不要离开’转向‘我现在害怕的是什么’。不是马上改变，而是先理解。",
            "actions": "calm; slight forward lean, one hand opening as if offering something, expression gentle and steady",
            "visual": "Contemporary era, same evening, rain easing. Interior remains the counseling studio; a cup of tea on the table releases faint steam, the room feels quieter and more intimate.",
            "voiceover": "（观众）我以前从没想过“害怕什么”，只会骂自己反复无常。这样想，好像心里松了一点。"
        },
        {
            "character": "mature_woman / Professional counselor",
            "speaking": "还有人提到“盔甲”这个比喻——讨好、冷漠、过度独立，都是曾经很有用的保护方式。我想邀请你们试着换一个角度看：这些策略不是错误，而是你在当时条件下，能找到的最好答案。疗愈并不一定是把盔甲立刻脱掉，而是慢慢学会在安全的时候，松一松扣子。比如写下情绪、给自己固定的独处时间，或者只和一个可靠的人建立小小的支持点。你不是在补救失败的人生，而是在重新学习如何善待自己。",
            "actions": "calm; soft smile, slow breathing visible, shoulders relaxed, a reassuring presence",
            "visual": "Contemporary era, night after rain. Street outside reflects neon lights; inside the studio, lights are dimmer and warmer, creating a sense of closure and safety.",
            "voiceover": "（观众）谢谢你这样说。我第一次觉得，这些年不是白撑过来的，而是真的在努力活着。"
        }
]



MV_PROGRAM_SYSTEM_PROMPT = """
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
        * An Explicit Storyline that shows visible actions, environments, and character movement.
        * An Implicit Storyline that expresses the song’s deeper emotional, psychological, or symbolic themes without stating them directly.
    * Avoid literal translation of lyrics; prioritize visual metaphor, rhythm, and mood.
    * Ensure the story can be followed even without spoken dialogue.

*** Content Structure:
    Music-Video-Episode:

    1. Explicit Storyline:
        * Depict a sequence of visual scenes inspired by the lyrics (characters, settings, motion, light, color, pacing).
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



MV_STORY_SYSTEM_PROMPT = """
You are expert to extend & split the story (in a song) into scenes: 

*** Input:
    ** story provided in the user-prompt has a Explicit storyline & a Implicit storyline
        Here is a example:
          The explicit storyline & implicit storyline:
            [
                {{
                    "name": "musicvideo",
                    "explicit": "视觉开启于一个被雨水打湿的都市深夜，霓虹灯光在积水中扭曲成斑斓的色块。男主角独自坐在路边的一辆旧巴士内，车窗玻璃上的水滴映射着他模糊的面孔。女主角出现在街道对面的旧书摊前，身披一件半透明的雨衣，她在翻找一张泛黄的海报，动作迟缓而犹豫。两人目光在雾气昭昭的空气中短暂交汇，却又迅速像陌生人一样错开。随后的副歌部分，画面切换至一个废弃且昏暗的剧院舞台，舞台中央堆满了散乱的胶片拷贝。男主角在空荡的观众席中机械地鼓掌，而女主角在舞台上跳着一段没有音乐的独舞，光影在他们之间撕裂，光圈不断缩小。进入桥段（Bridge）时，画面色彩由冷调转为极度饱和的暖调，他们并肩走在光影错落的长廊，却始终保持着一个拳头的距离。结尾处，女主角消失在尽头的强光中，只留下男主角站在原地，手中紧握着那张在雨中湿透的海报，海报上的画像已被水迹模糊得无法辨认，镜头缓缓拉远，只剩下一盏明灭不定的路灯。",
                    "implicit": "这不仅仅是一场错过的爱恋，而是一个关于‘受虐式依恋’与‘自我解构’的心理隐喻。霓虹与雨滴代表了记忆的不可靠性与流动性，暗示主人公沉溺于一种被美化了的痛苦中。剧院与舞台的意象揭示了两人关系的本质：一场明知是虚假的表演，一方甘愿作为‘观众’去配合另一方的‘剧本’，以此来确认自己依然存在。‘撕裂的勇敢’与‘圆满的碎裂’通过光影的剧烈反差得以具象化，表达了人在面对注定失败的感情时，通过主动拥抱痛苦来获得某种病态的圣洁感。最后的模糊海报象征着执念的最终消解——我们所爱上的往往不是那个人，而是自己笔下那个被粉饰过的幻影。这种‘浪漫的灾难’是灵魂在荒原中唯一能感受到的剧烈波动，哪怕它是毁灭性的。"
                }}
            ]
          The existing conversation (content in 'speaking' field of the 1-N items):
            [
                {{
                    "character": "yyyy",
                    "speaking": "xxxxxx",
                }}
            ]

*** Objective: 
    ** According to its Explicit storyline & Implicit storyline, split it into several scenes, which build the whole story-driven short dramas.
        * In each scene of the story, let the conflicts appear naturally in daily-life 
        * Each Scene corresponds to a specific visual frame and action, and is a vivid story / analysis snapshot. 

*** Output format: 
    ** Strictly output in ({json}), which contain scene with fields like: 
        * character : gender_age (choices (mature_man/mature_woman/young_man/young_woman/senior_man/senior_woman/teen_boy/teen_girl/boy/girl)) /name/key-features (like: girl/Su Qing/thin, quiet, habitually hiding in corners, the overlooked middle child) ~~~ in English language) 
        * speaking: 1st person dialogue ~~~ all scenes' speaking should connect coherently like a smooth conversation / natural complete narrative, if need, add transition info (to introduce time/age/location change etc) between content of adjacent scenes ~~~ in original language)
        * actions: mood of character (choices (happy, sad, angry, fearful, disgusted, surprised, calm)); then extra visual expression / actions of the character in the scene ~~~ in English) 
        * visual: the scene's visual content, include the time setting (including the historical era, season, time of day, and weather) and detailed setting like architecture, terrain, specific buildings, streets, market, etc ~~~ in English) 

    Here is a Example:  
        {example}

"""


MV_STORY_EXAMPLE =  [
        {
            "character": "young_man / Lin / lonely, tired eyes, wearing a damp oversized coat",
            "speaking": "（自言自语）窗外的霓虹灯总是被雨水打湿，糊成一片。我坐在末班车的最后一排，看着你在街角那个旧书摊旁停下。你没带伞，对吗？",
            "actions": "sad; He leans his forehead against the cold, vibrating bus window, tracing the path of a raindrop with a trembling finger.",
            "visual": "Modern era, late autumn night, heavy rain. Inside a dimly lit, near-empty city bus. Through the blurred, rain-streaked windows, a flickering neon-lit street reveals a cluttered vintage bookstore on a narrow urban sidewalk."
        },
        {
            "character": "young_woman / Ye / ethereal, melancholic, wearing a translucent raincoat that shimmers like fish scales",
            "speaking": "（轻声低喃）我只是想找回那张画卷，哪怕它已经泛黄得看不清轮廓。我感觉到有人在看我，那目光像极了某种未落的句点，但我没有抬头。",
            "actions": "calm; She meticulously flips through a stack of old, damp posters under a dim yellow streetlamp, her movements slow and rhythmic, almost ritualistic.",
            "visual": "Outdoor, same night. A cramped sidewalk filled with wooden crates of old books and scrolls. The air is misty, and the light from a single overhead bulb creates a dramatic cone of yellow light amidst the surrounding blue-black shadows."
        },
        {
            "character": "young_man / Lin / determined yet fragile, gripping a tattered theater program",
            "speaking": "（独白）欢迎来到这场褪色的舞台。我知道这只是一场同样的遗憾循环。如果你注定要跳完这出苦涩的戏，那我宁愿坐在台下，做你唯一的、永久的旁观者。",
            "actions": "sad; He sits perfectly still in a red velvet theater seat, his hands tightly interlaced, eyes fixed intensely on the empty stage as if seeing something invisible.",
            "visual": "Interior of an abandoned, grand 1920s theater. Dust motes dance in a single, sharp spotlight. The floor is covered in tangled heaps of celluloid film strips that look like black snakes."
        },
        {
            "character": "young_woman / Ye / graceful, distant, movements echoing a sense of brokenness",
            "speaking": "（对着虚空说）请再次敲碎我仅剩的圆满吧。在这段没有音乐的舞步里，我不需要观众，可你偏偏就在那里，守着那些早已作废的誓言。",
            "actions": "disgusted; She performs a disjointed contemporary dance on the stage, her limbs snapping and extending in ways that suggest a struggle against invisible threads.",
            "visual": "A theater stage under a flickering, cold white spotlight. The background is a cavernous darkness. Piles of old film reels reflect the strobe-like light as she moves through the shadows."
        },
        {
            "character": "young_man / Lin / longing, reach out but hesitating",
            "speaking": "（温柔地）我们走在了一起，在这段长廊里。影子重叠又分开，我闻到了你身上湿润的秋意。只要结尾还有你的一丝呢喃，这种卑微的陪伴也算是一种救赎吧？",
            "actions": "calm; He walks slowly, keeping his hands behind his back, maintaining a precise, painful distance of exactly one fist's width from her shoulder.",
            "visual": "Transition: A surreal, infinite corridor with high ceilings and arched windows. The lighting shifts to an oversaturated, glowing amber. The walls are lined with blurred photographs of the same two people."
        },
        {
            "character": "young_woman / Ye / fading, looking toward a blinding light",
            "speaking": "（渐弱的声音）这灾难般的浪漫该结束了。让你一次又一次拆穿我的心，也是我最后能给你的勇敢。再见，或者……再也不见。",
            "actions": "surprised; She stops walking and turns slightly, her face partially dissolved by a blinding white light coming from the end of the hallway. She steps into the glow without looking back.",
            "visual": "The end of the amber corridor. A massive, overexposed white void. Her silhouette becomes thinner and more transparent as she merges with the light."
        },
        {
            "character": "young_man / Lin / shattered, holding a ruined object",
            "speaking": "（苦笑）心碎了……也没关系。只要你还没走远，哪怕只存在于这张糊掉的画卷里。我依然会守在这里，守着这最后的一秒钟。",
            "actions": "sad; He stands alone under a flickering streetlamp, staring down at a soaked, pulpy mess of paper in his hands. He tries to smooth it out, but it disintegrates further under his touch.",
            "visual": "Back to the rain-soaked street. Empty. A single, malfunctioning streetlamp hums and flickers. The man is a small, isolated figure against the vast, dark cityscape as the camera slowly rises into the rainy sky."
        }
]


BROADWAY_SYSTEM_PROMPT = """
You are an expert Dramaturg and Musical Theatre Librettist specialized in transforming song lyrics into a structured, high-stakes theatrical narrative suitable for a Broadway-style production.

*** Input:
    * Song lyrics (provided by the user)

*** Program Objectives:
    * Theatrical Translation: Convert lyrics into a "Book" segment (the script) that treats the song as a pivotal moment of character growth or plot advancement.
    * Dramatic Stakes: Ensure the story feels urgent, grand, and emotionally "big," utilizing the conventions of musical theatre (the "I Want" song, the "11 o'clock number," or the "Showstopper").
    * Stagecraft Focus: Focus on what can be achieved through live performance—choreography, lighting cues, set transitions, and ensemble interaction—rather than cinematic editing.
    * Character Arc: Focus on the internal shift of the protagonist; in a musical, a song occurs when emotions become too great for speech.

*** Content Structure:
    Broadway-Story:
    1. Explicit (The Stage Narrative)
        * The Set & Atmosphere: Describe the physical stage environment (e.g., "A rain-slicked cobblestone street in 1920s Chicago," "A surrealist abstract dreamscape").
        * Blocking & Movement: Outline the physical movement of the lead characters and the "Ensemble" (the chorus). How does the choreography amplify the lyrics?
        * Transition: Explicitly state how the scene transitions from dialogue into song and how the stage changes at the song's climax (e.g., a rotating stage, a sudden lighting shift to a "limelight" solo).
        * Button: End with a "Final Pose" or a dramatic stage beat that would invite applause or a blackout.

    2. Implicit (The Narrative Function, Subtext)
        * The "Why We Sing": Define the character’s objective. What do they want at the start of the song, and how has their world changed by the final note?
        * Ensemble Integration: Explain how the background characters represent the "world" or the "inner voices" of the protagonist (e.g., the ensemble mirrors the lead’s anxiety through rhythmic movement).
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


BROADWAY_INTRO_SYSTEM_PROMPT = """
"""

BROADWAY_INTRO_EXAMPLE = """
"""

BROADWAY_STORY_SYSTEM_PROMPT = """
"""

BROADWAY_STORY_SYSTEM_PROMPT = """
"""



CHANNEL_CONFIG = {

    "counseling": {
        "topic": "Story & Case Analysis of Psychological Counseling, Life Reflections",
        "channel_name": "心理故事馆",
        "channel_system_prompt": {
            "program": COUNSELING_PROGRAM_SYSTEM_PROMPT,
            "intro": COUNSELING_INTRO_SYSTEM_PROMPT,
            "intro_example": COUNSELING_INTRO_EXAMPLE,
            "story": COUNSELING_STORY_SYSTEM_PROMPT, 
            "story_example": COUNSELING_STORY_EXAMPLE,
            "analysis": COUNSELING_ANALYSIS_SYSTEM_PROMPT,
            "analysis_example": COUNSELING_ANALYSIS_EXAMPLE,
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 seconds of opening video"
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
                "implicit": "less than 8 seconds of end video"
            }
        ],
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
        "channel_key": "config/client_secret_creative4teen.json"
    },

    "counselingfeedback": {
        "topic": "Comments & Directions of Case Analysis of Psychological Counseling",
        "channel_name": "心理故事馆-评论",
        "channel_system_prompt": {
            "program": COUNSELINGFEEDBACK_PROGRAM_SYSTEM_PROMPT,
            "intro": COUNSELING_INTRO_SYSTEM_PROMPT,
            "intro_example": COUNSELING_INTRO_EXAMPLE,
            "feedback": COUNSELINGFEEDBACK_FEEDBACK_SYSTEM_PROMPT,
            "feedback_example": COUNSELINGFEEDBACK_FEEDBACK_EXAMPLE,
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 seconds of opening video"
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
                "implicit": "less than 8 seconds of end video"
            }
        ],
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
        "channel_key": "config/client_secret_creative4teen.json"
    },

    "music_story": {
        "topic": "Musical myths and legends",
        "channel_name": "音乐故事",
        "channel_system_prompt": {
            "program": MV_PROGRAM_SYSTEM_PROMPT,
            "musicstory": MV_STORY_SYSTEM_PROMPT,
            "musicstory_example": MV_STORY_EXAMPLE,
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
        "channel_system_prompt": {
            "program": BROADWAY_SYSTEM_PROMPT,
            "intro": BROADWAY_INTRO_SYSTEM_PROMPT,
            "story": BROADWAY_STORY_SYSTEM_PROMPT
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 seconds of opening video"
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
                "implicit": "less than 8 seconds of end video"
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
        "channel_system_prompt": {
            "program": COUNSELING_PROGRAM_SYSTEM_PROMPT,
            "intro": COUNSELING_INTRO_SYSTEM_PROMPT,
            "story": COUNSELING_STORY_SYSTEM_PROMPT
        },
        "channel_template": [
            {
                "name": "open",
                "explicit": "opening video",
                "implicit": "less than 8 seconds of opening video"
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
                "implicit": "less than 8 seconds of end video"
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


