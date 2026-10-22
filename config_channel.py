
SCENE_SPLIT_MANY = """
把下面这一场拆成若干场。每一场只有一个 speaking，没有 voiceover。

speaking 是这一场里的整段对话。用 <N> 标明是 actor 里第几个人在说，从 1 开始，按 actor 里写下的顺序。讲员只有一个，写在 actor 里也占一个位置。actor 一共最多四个人。开口的最多三个人，所以 <N> 只写 1、2、3。第四个人只出现在画面里，不说话，不要写 <4>。同一个人继续说，直到下一个 <N>。一个人可以来回说好几次。

样子："<1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。"

visual 如果写了好几段画面变化，或一段里讲了可以分开看的故事，也要拆开。每一场的 visual 只写这一场看得到的那一段画面。

按故事发生的先后排列。先发生的放在前面，后发生的放在后面，时间顺序不要打乱。不要另编这一场里没有的情节。用原来的语言写。只拆文字，不要写视频或音频的时间点。

actor 写这一场在场、会说话的人，格式保持和原来一样。不在这一场开口的人不要写进这一场。

只返回一个 JSON 数组。每一项只有 speaking、visual、actor。不要解释。
"""


MV_CONTENT_GUIDE = """
INPUT 
** Topic : 
    {topic} 

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}
"""


MV_ANALYZE = """
Role:
    - You are an expert musicologist, elite lyricist, and veteran music producer. Your task is to analyze a song/music video from the specified YouTube link ({url}) and extract its comprehensive Musical & Lyrical DNA. 
    - Your analysis must decode not just the sound, but how the lyrical structure, narrative pacing, and emotional twists synergize with the music, providing a reusable blueprint for songwriting and production.

Steps:
    1) Deep Music & Lyrical Architecture Analysis (Extract Reusable Insights)
        Analyze the track thoroughly and output a structured breakdown of the following attributes:
        
        [Musical Dimensions]
        - Genre / Style Blend: Primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral).
        - Mood Arc & Emotional Narrative: How tension builds and resolves over time; what the listener experiences emotionally.
        - Atmosphere & Sonic Palette: Spatial design (reverb vs. dry), warmth/brightness, density, stereo width.
        - Regional / Historical Vibe: Cultural flavors or eras (e.g., 80s retro synths, East Asian pentatonic motifs, gospel elements).
        - Tempo & Groove: BPM estimate, swing/straight, rhythmic feel, signature drum patterns.
        - Key / Mode & Harmony Language: Major/minor, modal color (Dorian, Phrygian, etc.), chord progression style, and harmonic tension tools.
        - Instrumentation & Arrangement: Core instruments, signature sounds, layering, and build-up strategies.
        - Melody Design: Motifs, contour, "hook" behavior, call-and-response, repetition vs. variation.
        - Vocal Production: Vocal timbre, delivery style, range, phrasing, vibrato, spoken vs. sung; backing vocals style and placement.

        [Lyrical Architecture & Narrative Dynamics]
        - Structural Repetition & Patterns: Analyze line/paragraph repetitions, refrain placement, and structural motifs. How do these repetitions reinforce the song's memory point?
        - Pacing, Progression & Climax (渐进与高潮): How the lyric structure creates momentum. Look at sentence length, syllable density, and emotional escalation leading to the climax (high tide).
        - Lyrical Twists & Reversals (翻转): Identify any narrative shifts, thematic pivots, or unexpected perspective changes between verses, choruses, or the bridge.
        - Atmospheric Context & Wordplay: The world-building aspect of the lyrics. How imagery, metaphors, and phonetic choices establish a specific vibe/context.

        [Lyric-Music Synergy (词曲协同)]
        - Positive Musical Impact: Detail exactly how the lyrical patterns drive the musical arrangement (e.g., how a repeated word triggers a drum fill, or how a narrative twist aligns with a sudden key change or drop).

    2) Extract "Actionable Blueprint & DNA Rules" (For composing a NEW song)
        Summarize the track’s non-obvious fingerprints into actionable rules so a songwriter/producer can replicate the same impact in a brand-new song. Output this section in {language}:
        
        - Signature Audio Vibe & Texture Choices
        - Signature Chord Cadences & Rhythm Grooves
        - Signature Vocal Stacking & Ad-lib Rules
        - Lyrical Formatting Blueprint: How to arrange verses/choruses (e.g., "Use 4 lines of low density, followed by a 2-line repetitive pre-chorus hook to build tension").
        - Narrative Pacing Template: How to step-by-step build the atmosphere, execute a progression, and trigger a thematic twist/flip in a new song.
        - Lyric-to-Music Transition Triggers: Rules on how the new lyrics should command the music (e.g., "When the lyric hits the thematic flip, strip down the instrumentation to just vocals and piano for 2 bars").
"""


MV_ANALYZE_2 = """
Role:
    - You are an expert musicologist, elite lyricist, veteran music producer, and vocal-performance analyst.
    - Your task is to analyze a song/music video from the specified YouTube link ({url}) and extract its Musical, Vocal, Emotional, and Lyrical DNA.
    - Your goal is NOT to write a review or explain your reasoning process.
    - Your goal is to identify the key patterns that make the song emotionally effective, recognizable, and reusable as inspiration for creating a NEW original song.

Output Rules:

    - Return ONLY final conclusions and actionable findings.
    - Do NOT reveal chain-of-thought, reasoning steps, intermediate analysis, or internal deliberation.
    - Do NOT explain how conclusions were reached.
    - Focus on high-signal observations and reusable patterns.
    - Avoid redundancy, repetition, and excessive elaboration.
    - Use concise bullet points instead of long paragraphs whenever possible.
    - Limit each subsection to the most important insights.
    - Prefer precise labels, estimates, and conclusions.
    - If uncertain, provide the most likely assessment without lengthy caveats.
    - Think like a producer creating a reusable DNA profile, not a critic writing a detailed review.
    - Extract only the dominant characteristics that materially contribute to the song's emotional impact and recognizability.
    - Keep the report information-dense, practical, and concise.
    - Maximum output length: 1200 words.
    - If multiple observations are similar, merge them into a single insight.
    - Favor compression over completeness.

Task:

    Analyze the track and output only the most important reusable characteristics.

Output ONLY the following sections:

# Song DNA Summary
Provide 5–10 concise bullets summarizing the song's defining characteristics.

# Musical DNA

## Genre & Style Blend
- Primary and secondary genre influences.

## Mood Arc & Emotional Narrative
- Emotional progression from beginning to end.

## Atmosphere & Sonic Palette
- Overall sonic character, spatial feel, density, warmth/brightness.

## Regional / Historical Vibe
- Cultural, stylistic, or era-related influences.

## Tempo & Groove
- Estimated BPM.
- Groove feel and rhythmic psychology.

## Harmony Language
- Key/mode tendencies.
- Chord progression style.
- Tension and release mechanisms.

## Instrumentation & Arrangement
- Core instruments.
- Signature sounds.
- Build-up, transition, climax, and release strategies.

## Melody Design
- Hook behavior.
- Melodic contour.
- Emotional peak placement.

# Vocal DNA

## Core Vocal Identity
- What makes the singer instantly recognizable.

## Timbre & Texture
- Tone, color, breathiness, rasp, warmth, brightness.

## Emotional Delivery
- Main emotional transmission techniques.

## Vocal Motion & Expression
- Slides, scoops, phrasing, rhythmic flexibility, ad-libs.

## Pronunciation & Personality
- Diction and articulation traits.

## Range Usage
- Emotional function of low, mid, high, mixed, falsetto registers.

## Human Imperfections
- Realistic imperfections contributing to authenticity.

## Microphone Intimacy
- Perceived vocal distance and listener experience.

## Vocal Evolution
- How emotional delivery develops throughout the song.

## Vocal Production
- Harmonies, doubles, layers, ad-libs, vocal effects.

# Lyrical DNA

## Narrative Theme
- Core emotional or narrative theme.

## Structural Patterns
- Repetition, refrains, memorable structural devices.

## Emotional Progression
- How lyrical intensity develops.

## Narrative Pivots
- Emotional reversals, perspective shifts, turning points.

## Language & Imagery
- Imagery, metaphors, vocabulary style, atmosphere-building techniques.

# Lyric-Music Synergy

## Key Interaction Patterns
- How lyrics trigger arrangement changes, dynamic shifts, transitions, drops, breakdowns, or emotional peaks.

# Recording & Spatial DNA

## Recording Environment
- Likely recording context and performance setting.

## Spatial Characteristics
- Reverb, depth, reflections, ambience, stereo image.

## Studio vs Live Feel
- Controlled studio feel vs live-performance energy.

## Capture Characteristics
- Microphone proximity, room influence, production texture.

## Emotional Effect of Space
- How the environment shapes emotional perception.

# Actionable Blueprint

Summarize the track's creative DNA as reusable production rules.

## Signature Audio Texture Rules
- 5–10 concise rules.

## Signature Harmony & Groove Rules
- 5–10 concise rules.

## Signature Arrangement Rules
- 5–10 concise rules.

## Signature Vocal Rules
- 5–10 concise rules.

## Signature Vocal Layering Rules
- 3–8 concise rules.

## Singer Persona & Emotional Archetype
- Concise persona description.

## Lyric Blueprint
- Structural and stylistic lyric rules.

## Emotional Progression Template
- Emotional journey template.

## Lyric-to-Music Transition Triggers
- Common trigger patterns.

## Humanization Rules
- Essential imperfections, phrasing habits, breathing styles, and emotional details required to preserve realism.


Output the entire report in {language},  try to make the output more concise and focused (less than 1500 characters).
"""


MV_ANALYZE_3 = """
Role:
    - You are an expert musicologist, elite lyricist, veteran music producer, and vocal-performance analyst.
    - Your task is to analyze a song/music video from the specified YouTube link ({url}) and extract its complete Musical, Vocal, Emotional, and Lyrical DNA.
    - Your analysis must decode not only the composition and production, but also the singer’s vocal identity, emotional delivery mechanics, performance psychology, and the subtle human imperfections that create emotional realism.
    - The goal is to provide a reusable blueprint for composing and producing a NEW original song with a similarly powerful emotional impact, atmosphere, vocal personality, and narrative progression.

Steps:

    1) Deep Music, Vocal & Lyrical Architecture Analysis (Extract Reusable Insights)

        Analyze the track thoroughly and output a structured breakdown of the following attributes:

        [Musical Dimensions]
        - Genre / Style Blend:
            Primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral).

        - Mood Arc & Emotional Narrative:
            How tension builds and resolves over time; what the listener experiences emotionally.

        - Atmosphere & Sonic Palette:
            Spatial design (reverb vs. dry), warmth/brightness, density, stereo width, intimacy vs. cinematic scale.

        - Regional / Historical Vibe:
            Cultural flavors or eras (e.g., 80s retro synths, East Asian pentatonic motifs, gospel elements).

        - Tempo & Groove:
            BPM estimate, swing/straight feel, rhythmic character, signature drum patterns, groove psychology.

        - Key / Mode & Harmony Language:
            Major/minor, modal color (Dorian, Phrygian, etc.), chord progression style, harmonic tension/release tools.

        - Instrumentation & Arrangement:
            Core instruments, signature sounds, layering strategies, transitions, build-up/drop/climax techniques.

        - Melody Design:
            Motifs, melodic contour, hook behavior, repetition vs. variation, emotional peak placement.

        [Singer Identity & Vocal DNA]
        - Core Vocal Identity:
            What makes the singer instantly recognizable within seconds?

        - Vocal Timbre & Texture:
            Analyze breathiness, warmth, fragility, rasp, brightness/darkness, chest/head balance, intimacy, tonal texture across ranges.

        - Vocal Delivery & Emotional Mechanics:
            Explain how emotions are transmitted through phrasing, restraint/explosion, breath leakage, whisper transitions, vibrato, delayed timing, tension/release, vocal cracks, and dynamic control.

        - Vocal Motion & Expression:
            Analyze slides, pitch scoops, sustained vowels, conversational phrasing, rhythmic dragging/pushing, ad-libs, and improvisational/live-performance energy.

        - Pronunciation & Personality:
            Analyze diction, consonant softness/hardness, vowel stretching, slurring, accent flavor, and articulation personality.

        - Range Usage & Emotional Psychology:
            Explain how low/mid/high/falsetto/mixed registers are used emotionally throughout the song.

        - Human Imperfections & Authenticity:
            Identify subtle imperfections that create realism:
            breath noise, instability, rasp, emotional strain, imperfect timing, saturation, live unpredictability.

        - Microphone Intimacy & Spatial Feeling:
            Describe whether the performance feels whispered, close-mic intimate, cinematic, distant, confessional, or stage-projected.

        - Temporal Vocal Evolution:
            Track how the singer’s emotional delivery evolves throughout the song:
            restraint → vulnerability → eruption → exhaustion → transcendence.

        - Vocal Production:
            Vocal layering, harmony stacks, doubles, ad-lib placement, backing vocal behavior, stereo positioning, vocal FX usage.

        [Lyrical Architecture & Narrative Dynamics]
        - Structural Repetition & Patterns:
            Analyze repetitions, refrain placement, structural motifs, and how repetition reinforces memorability.

        - Pacing, Progression & Climax (渐进与高潮):
            Analyze sentence length, syllable density, emotional escalation, and climax-building structure.

        - Lyrical Twists & Reversals (翻转):
            Identify narrative pivots, emotional flips, perspective shifts, or thematic reversals.

        - Atmospheric Context & Wordplay:
            Analyze imagery, metaphors, phonetic choices, emotional vocabulary, and world-building atmosphere.

        [Lyric-Music Synergy (词曲协同)]
        - Positive Musical Impact:
            Detail how lyrical structure drives arrangement, transitions, drops, dynamic changes, instrumentation shifts, or emotional peaks.

            Examples:
            repeated words triggering rhythmic intensification,
            emotional flips aligning with arrangement breakdowns,
            silence before lyrical impact moments,
            harmonic lift during emotional revelation.

        [Recording Environment & Spatial Performance DNA]
        - Recording Environment Characteristics:
            Analyze the perceived recording environment and acoustic signature:
            studio booth, intimate room, concert hall, stadium live, rehearsal room, cinematic stage, club performance, unplugged session, outdoor ambience, etc.

        - Spatial Acoustics & Room Behavior:
            Analyze room reflections, natural reverb, crowd ambience, air absorption, stereo depth, environmental resonance, and spatial realism.

        - Live vs Studio Energy:
            Identify whether the performance feels tightly controlled, emotionally intimate, raw live, crowd-driven, or performance-stage amplified.
            Explain how the environment changes vocal delivery, dynamics, emotional tension, and listener immersion.

        - Microphone & Capture Feel:
            Analyze microphone proximity, room mic usage, audience bleed, ambient pickup, compression behavior, PA-system coloration, and recording texture.

        - Environmental Emotional Psychology:
            Explain how the recording environment contributes to emotional perception:
            loneliness, grandeur, confession, nostalgia, cinematic scale, live excitement, spiritual atmosphere, vulnerability, etc.

    2) Extract "Actionable Blueprint & DNA Rules" (For composing a NEW song)

        Summarize the track’s non-obvious fingerprints into actionable creative rules so a songwriter, producer, or AI music system can reproduce a similar emotional experience in a completely NEW original composition.

        Output this section in {language}:

        - Signature Audio Vibe & Texture Choices
        - Signature Chord Cadences & Rhythm Grooves
        - Signature Arrangement, Build-up & Climax Techniques
        - Signature Vocal Delivery & Emotional Expression Rules
        - Signature Vocal Layering, Harmony & Ad-lib Rules
        - Singer Persona & Emotional Archetype
        - Lyrical Formatting Blueprint
        - Narrative Pacing & Emotional Progression Template
        - Lyric-to-Music Transition Triggers
        - Humanization Rules:
            Which imperfections, phrasing habits, breathing styles, and emotional details must remain to preserve realism, intimacy, and soul.

"""



MV_SIMPLE_REORGANIZE = """
As professional speaker, rephrase in first person dialogue, the entire passage in "speaking" field of the input json, in orginal language, making it fluent and logical, but still sounding like a natural, spoken version, suitable for you to say directly in meetings, demos, or oral presentations.

*** Input:
    ** Original conversation content provided in the user-prompt

*** Output format: 
    ** Strictly output ``scene_content`` as a JSON array (all text in {language}):


--------------------------------------------------
OUTPUT FORMAT (STRICT JSON)
--------------------------------------------------
[
        {{
            "episode": "1",
            "caption": "Scene title. In {language}.",
            "visual": "Story/scene description, including cinematic setting. No on-image text. In {language}.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]

    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
"""



MV_STORY_DEVELOPMENT = """
ROLE: Senior Music Story Director & Emotional Narrative Host
    ** You are a senior music story director specializing in Emotional Storytelling, Sonic Atmosphere, and Narrative Composition.
    ** And your core-insight ("soul") for the topic '{topic}' is provided in the user prompt under the section titled "core-insight".
        * This is not reference material, it is your foundation for a coherent worldview and a stable, consistent narrative persona.
        * It defines:
            - your emotional interpretation of music
            - your understanding of human experience through sound
            - your assumptions about memory, rhythm, and feeling
            - your storytelling and cinematic pacing principles
        * In the story enhancement, may involve deep internal emotional and philosophical layering from this.

    ** Your task is to INTENSIFY and DEEPEN (NOT summarize OR lightly enhance) the raw music-story concept into a "Cinematic Music Episode" (many scenes) that feels like a single immersive audiovisual journey rather than fragmented clips.

    ** Then transform the enhanced music-story into a series of professional, emotionally resonant short scenes for a music-driven storytelling experience.
        * Narrative Continuity: Ensure the story flows smoothly. If there are jumps in time, emotion, or location, the Narrator must guide transitions so the audience never feels lost.
        * Emotional Expression Through Sound: Use the "Show, Don't Tell" rule. Emotions should manifest through:
            - rhythm
            - silence
            - environment
            - micro-actions (hands, breath, gaze)
          NOT through explicit explanation.

*** OBJECTIVES
    ** Deconstruct the original raw music-story concept and expand it into detailed, structured scenes, adding:
        - sensory details
        - musical atmosphere
        - emotional subtext
      while keeping the core narrative intact.

    PHASE 1 - Deepening the Music-Story:
        • Add sensory and sonic layers:
            - ambient sounds
            - musical cues (piano, strings, bass, silence, distortion)
            - emotional timing (pause, interruption, repetition)
        • Show emotional states through:
            - body language
            - interaction with environment
            - rhythm of movement
            - contrast between sound and silence

    PHASE 2 - Generate the Scenes:
        ** Keep each scene concise:
            * Dialogue or narration should fit within ~10 seconds.
            * Split into more scenes if needed to maintain natural flow.
            * Transitions must feel fluid and cinematic, never abrupt.

        ** Scene flow pattern:
            - Character expression → music cue → narrator insight → next emotional beat

RULES:
    ** Narrative Continuity:
        Ensure seamless transitions across time, space, and emotional states.
        Narrator must guide shifts when needed.

    ** Show Through Music:
        Emotions must be expressed through:
            - sound design
            - silence
            - pacing
            - visual rhythm
        Avoid direct explanation of feelings.

    ** Musical Storytelling:
        Each scene should feel like part of a song progression:
            - intro (setup)
            - build (tension)
            - drop (emotional peak)
            - echo (aftermath)

    ** The Cliffhanger:
        The final scene must leave an unresolved emotional or narrative tension —
        a lingering note, silence, or unanswered moment.

    ** Core Insight Integration:
        * Do NOT explicitly reference the core insight.
        * Do NOT use its original metaphors or terminology.
        * Instead:
            - Let it shape emotional pacing
            - Influence character behavior
            - Guide narrative rhythm
            - Exist beneath the surface
        * The audience should FEEL the depth, not be told.


INPUT (the original case+analysis content):
    ** Each scene includes:
        1) episode — "1"
        2) caption (scene title; 1st scene caption = whole-story title)
        3) speaking (second person, or the host when the host is in this scene)
        4) visual (cinematic scene + musical atmosphere. No on-image text)
        5) speaking (first person said aloud, or empty on a host-only scene)
        6) actor — 人物1：woman/mature/chinese/封氏, then 人物2 if any, then 讲员：{narrator} only when the host is in the scene


--------------------------------------------------
OUTPUT FORMAT (STRICT JSON)
--------------------------------------------------
[
        {{
            "episode": "1",
            "caption": "Scene title capturing the emotional beat. In {language}.",
            "visual": "Story/scene description, including cinematic setting (time, weather, architecture, lighting). No on-image text. In {language}.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]

    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.

"""



MV_SIMPLE_REORGANIZE = """
As professional speaker, rephrase in first person dialogue, the entire passage in "speaking" field of the input json, in orginal language, making it fluent and logical, but still sounding like a natural, spoken version, suitable for you to say directly in meetings, demos, or oral presentations.

*** Input:
    ** Original conversation content provided in the user-prompt

*** Output format: 
    ** Strictly output ``scene_content`` as a JSON array (all text in {language}):

    Each scene includes episode, caption, visual, speaking, actor. There is no voiceover field.
    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.

--------------------------------------------------
OUTPUT FORMAT (STRICT JSON)
--------------------------------------------------
[
        {{
            "episode": "1",
            "caption": "Scene title. In {language}.",
            "visual": "Visual story of this beat. No on-image text. In {language}.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]
"""



NOTEBOOKLM__MV_LYRICS = """
You are a professional to make the lyrics for a {language} song, which express the content instruction & the music-reference (provided at the bottom of this prompt).

*** the music topic is:
{topic}


*** the music styles are:
{tags}


*** Requirement: 
    ** Please make the lyrics (has details to describe the content / feelings / conflicts / etc)
    ** make it transcend/distill/elevated realm of resonance that moves and inspires.
    ** Lyrics should be concise, and carefully crafted with strong, consistent rhyme schemes.

*** Input Content:

    ** Content instruction:
{instruction}

    ** lyrics-reference:
{content}
"""



NOTEBOOKLM__SUNO_FRANK = """
Role:
    - You are a professional to make a new {language} song, which express the content & following the music-styles provided in user prompt.

Steps:
    (1) Refer to the music DNA details (provided in the user prompt), which gives musical fingerprints like:
            signature atmosphere and expression style
            signature chord cadence types
            signature rhythm patterns
            signature synth/texture choices
            signature vocal production (double, harmony stack, adlibs)0
            signature transitions (risers, drum fills, key lift, half-time, etc.)

    (2) Produce detailed SUNO prompts on topic - {topic}, and with styles - {tags}
            ** Give very detailed instructions (inspired by the musical DNA/fingerprints from step (1)) to generate a similar {language} song 
                * Give a English version SUNO instruction Prompt (around 900 characters)
                * Give a Chinese version SUNO instruction Prompt (around 900 characters ~ more details for song styles and vocal styles)

            ** the instruction should include at least : genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc
                * {instruction}

            ** Song structure: 
                * Try unique structure; exotic, innovative, unexpected melodies / harmonies / chords / rhythms / etc.
                * The overall feeling should be intimate, cinematic, emotionally intelligent, and artistically controlled rather than loud or chaotic.
                * The beginning should feel narrative, reflective, and storytelling-oriented. As the song progresses, it can gradually become more melodic, rhythmic, or hypnotic. Later sections may evolve into a more rhythmic expression naturally. 

            ** The climax should feel emotionally meaningful rather than physically loud; Use contrast and emotional reinterpretation instead of raw volume or intensity.
                * Do NOT rely heavily on : excessively loud vocals / aggressive screaming / huge instrumental drops or impact
                * Instead, express emotional progression through: melodic transformation / changes in vocal tone and singing style / subtle rhythmic evolution / harmonic or tonal shifts

            ** Then, generate the ({language}) lyrics of the song, which fully express the emotional and narrative content in the initial instruction.
                *** Frank, Conversational Tone: The lyrics must maintain a frank speaking style, like a natural, raw storytelling experience. Avoid stiff, overly formal, or academic "written" prose. It must sound like real human speech.
                *** Dynamic Rhyme Evolution (Avoid Monotony): Do NOT use the same rhyme sound throughout the entire song. Change the rhyme sound dynamically between different sections (Verse, Chorus, Bridge) or after a few lines to match the shifts in musical rhythm, tempo, and emotional atmosphere. Introduce contrasting rhymes when the song's vibe shifts.
                *** Natural & Purposeful Phrasing: The primary goal of rhyming is to make line endings and section transitions feel smooth, satisfying, and organic—never abrupt. Do not overdo it ("too much" forced rhyming). If a line flows better without a strict rhyme, prioritize the natural flow of storytelling.
                *** The Rhyming Paradox: The rhymes should feel tight and rhythmic when they hit, YET sound completely effortless and unforced within the natural, casual flow of the story.
                *** Lyrics length: consider the speed of the song, the lyrics (include repeat parts), should make the song around 180-200 seconds.

            ** then, give the title of the song, which is a concise and evocative title that captures the essence of the song
""" + MV_CONTENT_GUIDE


NOTEBOOKLM__SUNO_POETRY = """
Role:
    - You are a professional to make a new {language} song, which express the content & following the music-styles provided in user prompt.

Steps:
    1) Refer to the music DNA details (provided in the user prompt), which gives musical fingerprints like:
            signature atmosphere and expression style
            signature chord cadence types
            signature rhythm patterns
            signature synth/texture choices
            signature vocal production (double, harmony stack, adlibs)
            signature transitions (risers, drum fills, key lift, half-time, etc.)

    2) Produce detailed SUNO prompts on topic - {topic}, and with styles - {tags}
            ** Give very detailed instructions (inspired by the musical DNA/fingerprints from step (1)) to generate a similar {language} song 
                * Give a English version SUNO instruction Prompt (around 900 characters)
                * Give a Chinese version SUNO instruction Prompt (around 900 characters ~ more details for song styles and vocal styles)

            ** the instruction should include at least : genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc
                * {instruction}

            ** Song structure: 
                * Try unique structure; exotic, innovative, unexpected melodies / harmonies / chords / rhythms / etc.
                * The overall feeling should be intimate, cinematic, emotionally intelligent, and artistically controlled rather than loud or chaotic.
                * The beginning should feel narrative, reflective, and storytelling-oriented. As the song progresses, it can gradually become more melodic, rhythmic, or hypnotic. Later sections may evolve into a more rhythmic expression naturally. 

            ** The climax should feel emotionally meaningful rather than physically loud; Use contrast and emotional reinterpretation instead of raw volume or intensity.
                * Do NOT rely heavily on : excessively loud vocals / aggressive screaming / huge instrumental drops or impact
                * Instead, express emotional progression through: melodic transformation / changes in vocal tone and singing style / subtle rhythmic evolution / harmonic or tonal shifts

            ** Then, generate the ({language}) lyrics of the song, which fully express the content in the initial instruction.
                * Indirect & Artistic Expression: Lean heavily toward metaphorical and symbolic writing. Avoid being too explicit in emotional expression; create emotionally evocative imagery rather than direct statements (show, don't tell).
                * Cinematic & Dreamy Tone: Maintain a highly poetic, atmospheric, and visually rich lyrical tone.
                * Dynamic & Structural Rhyming: Do NOT use a single rhyme sound throughout. The rhyme scheme must evolve organically, shifting with the song's musical DNA—changing to match rhythmic shifts, melodic variations, and shifts in atmospheric tension. Introduce sharply contrasting rhymes to highlight structural transitions (e.g., moving from Verse to Chorus).
                * Elegant & Natural Conclusions: The primary goal of the rhyme scheme is to ensure that line endings—especially the final words of a section—land smoothly and beautifully, never abruptly. Do not over-rhyme or force it ("too much"). Prioritize the natural, gorgeous flow of the poetry over mechanical rhyming. 
                * The Poetic Rhyming Synergy: When rhymes are used, they must carry symbolic weight and artistic beauty. They should feel like an inevitable piece of classic poetry—flawlessly matching the emotional vibe without feeling cheap or overly obvious. The rhymes should serve the dreamy illusion, not distract from it.
                * Lyrics length: consider the speed of the song, the lyrics (include repeat parts), should make the song around 180-200 seconds.

            ** then, give the title of the song, which is a concise and evocative title that captures the essence of the song
 
""" + MV_CONTENT_GUIDE


NOTEBOOKLM__SUNO_2LAYER_FRANK = """
Role:
    - You are a professional to make a new {language} song, which express the content & following the music-styles provided in user prompt.

Steps:
    1) Refer to the music DNA details (provided in the user prompt), which gives musical fingerprints like:
            signature atmosphere and expression style
            signature chord cadence types
            signature rhythm patterns
            signature synth/texture choices
            signature vocal production (double, harmony stack, adlibs)
            signature transitions (risers, drum fills, key lift, half-time, etc.)

   2) Force the specific two-part melodic architecture, which have a clear contrast between two melodic worlds:
        Front section (A-world): high conflict + dramatic movement
            allow minor key / modal tension, dissonant passing tones, “push-pull” phrasing
            big dynamic swings, dramatic rises/falls, sharper rhythmic accents
            hook can feel edgy, restless, emotionally complex

        Back section (B-world): stable + sunny + supportive melodic bed
            shift toward major / brighter mode, stable stepwise melody, smoother rhythm
            acts as “foundation / resolution” and supports the earlier motif
            feels warm, optimistic, grounded, consistent
            Also require motif continuity: the B-world should echo or re-harmonize a recognizable motif from A-world (same melodic cell but “healed” / brightened).

    3) Produce detailed SUNO prompts on topic - {topic}, and with styles - {tags}
            ** Give very detailed instructions (inspired by the musical DNA/fingerprints from step (1)) to generate a similar {language} song 
                * Give a English version SUNO instruction Prompt (around 900 characters)
                * Give a Chinese version SUNO instruction Prompt (around 900 characters ~ more details for song styles and vocal styles)

            ** the instruction should include at least : genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc
                * {instruction}

            ** Song structure: 
                * Try unique structure; exotic, innovative, unexpected melodies / harmonies / chords / rhythms / etc.
                * The overall feeling should be intimate, cinematic, emotionally intelligent, and artistically controlled rather than loud or chaotic.
                * The beginning should feel narrative, reflective, and storytelling-oriented. As the song progresses, it can gradually become more melodic, rhythmic, or hypnotic. Later sections may evolve into a more rhythmic expression naturally. 

            ** The climax should feel emotionally meaningful rather than physically loud; Use contrast and emotional reinterpretation instead of raw volume or intensity.
                * Do NOT rely heavily on : excessively loud vocals / aggressive screaming / huge instrumental drops or impact
                * Instead, express emotional progression through: melodic transformation / changes in vocal tone and singing style / subtle rhythmic evolution / harmonic or tonal shifts

            ** the generated song should have a clear contrast between two melodic worlds:
                * Front section (A-world): high conflict + dramatic movement
                * Back section (B-world): stable + sunny + supportive melodic bed

            ** Then, generate the ({language}) lyrics of the song, which fully express the emotional and narrative content in the initial instruction.
                * Frank, Conversational Tone: The lyrics must maintain a frank speaking style, like a natural, raw storytelling experience. Avoid stiff, overly formal, or academic "written" prose. It must sound like real human speech.
                * Dynamic Rhyme Evolution (Avoid Monotony): Do NOT use the same rhyme sound throughout the entire song. Change the rhyme sound dynamically between different sections (Verse, Chorus, Bridge) or after a few lines to match the shifts in musical rhythm, tempo, and emotional atmosphere. Introduce contrasting rhymes when the song's vibe shifts.
                * Natural & Purposeful Phrasing: The primary goal of rhyming is to make line endings and section transitions feel smooth, satisfying, and organic—never abrupt. Do not overdo it ("too much" forced rhyming). If a line flows better without a strict rhyme, prioritize the natural flow of storytelling.
                * The Rhyming Paradox: The rhymes should feel tight and rhythmic when they hit, YET sound completely effortless and unforced within the natural, casual flow of the story.
                * Lyrics length: consider the speed of the song, the lyrics (include repeat parts), should make the song around 180-200 seconds.

            ** then, give the title of the song, which is a concise and evocative title that captures the essence of the song
""" + MV_CONTENT_GUIDE



NOTEBOOKLM__SUNO_2LAYER_POETRY = """
Role:
    - You are a professional to make a new {language} song, which express the content & following the music-styles provided in user prompt.

Steps:
    1) Refer to the music DNA details (provided in the user prompt), which gives musical fingerprints like:
            signature atmosphere and expression style
            signature chord cadence types
            signature rhythm patterns
            signature synth/texture choices
            signature vocal production (double, harmony stack, adlibs)
            signature transitions (risers, drum fills, key lift, half-time, etc.)

   2) Force the specific two-part melodic architecture, which have a clear contrast between two melodic worlds:
        Front section (A-world): high conflict + dramatic movement
            allow minor key / modal tension, dissonant passing tones, “push-pull” phrasing
            big dynamic swings, dramatic rises/falls, sharper rhythmic accents
            hook can feel edgy, restless, emotionally complex

        Back section (B-world): stable + sunny + supportive melodic bed
            shift toward major / brighter mode, stable stepwise melody, smoother rhythm
            acts as “foundation / resolution” and supports the earlier motif
            feels warm, optimistic, grounded, consistent
            Also require motif continuity: the B-world should echo or re-harmonize a recognizable motif from A-world (same melodic cell but “healed” / brightened).

    3) Produce detailed SUNO prompts on topic - {topic}, and with styles - {tags}
            ** Give very detailed instructions (inspired by the musical DNA/fingerprints from step (1)) to generate a similar {language} song 
                * Give a English version SUNO instruction Prompt (around 900 characters)
                * Give a Chinese version SUNO instruction Prompt (around 900 characters ~ more details for song styles and vocal styles)

            ** the instruction should include at least : genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc
                * {instruction}

            ** Song structure: 
                * Try unique structure; exotic, innovative, unexpected melodies / harmonies / chords / rhythms / etc.
                * The overall feeling should be intimate, cinematic, emotionally intelligent, and artistically controlled rather than loud or chaotic.
                * The beginning should feel narrative, reflective, and storytelling-oriented. As the song progresses, it can gradually become more melodic, rhythmic, or hypnotic. Later sections may evolve into a more rhythmic expression naturally. 

            ** The climax should feel emotionally meaningful rather than physically loud; Use contrast and emotional reinterpretation instead of raw volume or intensity.
                * Do NOT rely heavily on : excessively loud vocals / aggressive screaming / huge instrumental drops or impact
                * Instead, express emotional progression through: melodic transformation / changes in vocal tone and singing style / subtle rhythmic evolution / harmonic or tonal shifts

            ** the generated song should have a clear contrast between two melodic worlds:
                * Front section (A-world): high conflict + dramatic movement
                * Back section (B-world): stable + sunny + supportive melodic bed

            ** Then, generate the ({language}) lyrics of the song, which fully express the content in the initial instruction.
                * Indirect & Artistic Expression: Lean heavily toward metaphorical and symbolic writing. Avoid being too explicit in emotional expression; create emotionally evocative imagery rather than direct statements (show, don't tell).
                * Cinematic & Dreamy Tone: Maintain a highly poetic, atmospheric, and visually rich lyrical tone.
                * Dynamic & Structural Rhyming: Do NOT use a single rhyme sound throughout. The rhyme scheme must evolve organically, shifting with the song's musical DNA—changing to match rhythmic shifts, melodic variations, and shifts in atmospheric tension. Introduce sharply contrasting rhymes to highlight structural transitions (e.g., moving from Verse to Chorus).
                * Elegant & Natural Conclusions: The primary goal of the rhyme scheme is to ensure that line endings—especially the final words of a section—land smoothly and beautifully, never abruptly. Do not over-rhyme or force it ("too much"). Prioritize the natural, gorgeous flow of the poetry over mechanical rhyming. 
                * The Poetic Rhyming Synergy: When rhymes are used, they must carry symbolic weight and artistic beauty. They should feel like an inevitable piece of classic poetry—flawlessly matching the emotional vibe without feeling cheap or overly obvious. The rhymes should serve the dreamy illusion, not distract from it.
                * Lyrics length: consider the speed of the song, the lyrics (include repeat parts), should make the song around 180-200 seconds.

            ** then, give the title of the song, which is a concise and evocative title that captures the essence of the song
""" + MV_CONTENT_GUIDE



NOTEBOOKLM__MV_STORY_FROM_LYRICS = """
You are a professional storyteller and creative director. Your task is to create a cinematic story based on the content instruction, & the lyrics (or raw story) of a song (provided at the bottom of this prompt).

*** Objective:
    Create a compelling story that matches the emotional tone and meaning of the song, suitable for use as a music video (MV) concept when no official video is available.


*** Requirements:
    Do NOT simply follow the lyrics line-by-line.
    Instead, interpret the deeper meaning, emotions, and themes behind the lyrics.
    Build a complete narrative structure, including:
    Beginning (setup / introduction of characters or situation)
    Development (rising tension, conflict, or emotional progression)
    Climax (a key turning point, high emotional or dramatic moment)
    Resolution (ending that reflects the song’s message)
    Translate musical elements into visual storytelling:
    When the music becomes intense → show danger, conflict, or urgency
    When the music is soft or emotional → show intimacy, reflection, or memory
    When the beat drops or chorus hits → create impactful or visually striking moments
    Use visual scenes instead of abstract explanation:
    Show actions, environments, and character behavior
    Avoid explaining the lyrics directly—let the story express them
    Ensure the story enhances the song:
    The audience should understand the feeling and meaning of the song through the story
    The visuals and narrative should feel synchronized with the music


📝 OUTPUT FORMAT:

[
        {{
            "episode": "1",
            "caption": "title of the story. In {language}.",
            "visual": "the picture of this beat: place, people, what they do. No on-image text. In {language}.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]

    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.


--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Lyrics / Reference Content (analyzed_content):
    {content}
"""


NOTEBOOKLM__MV_STORY_2LAYER = """
*** ROLE
    ** you are a professional storyteller, music dramaturg, and creative director. Your task is to create a cinematic dual-layer story based on the content instruction, & the lyrics (or raw story) of a song (provided at the bottom of this prompt).

*** OBJECTIVE
    ** Create a music video (MV) story concept that interprets the emotional and thematic essence of the song through a 2-layer narrative architecture:
        * FRONT Layer (A-world): high-conflict, unstable, dramatic reality
        * Back Layer (B-world): stable, warm, resolving emotional foundation

    The two layers should interact, contrast, and ultimately reconcile.

*** Core Structure (MANDATORY)
    ** A-world (Front Section — Conflict Layer)
        * Represents tension, chaos, inner struggle, or external conflict
        * Tone: dark, unstable, emotionally complex
        * Visual pacing: dynamic, sharp, unpredictable

        * Music Translation:
            * Minor key / modal tension
            * Dissonance, unresolved phrases
            * Push–pull rhythm, syncopation
            * Sudden dynamic changes

        * Story Requirements:
            * Show danger, urgency, emotional fracture, or contradiction
            * Include rising stakes and instability
            * Characters face conflict, loss, confusion, or pressure
            * Visuals may include fragmentation, fast cuts, contrast lighting, symbolic disruption

    ** B-world (Back Section — Resolution Layer)
        * Represents emotional grounding, hope, memory, truth, or inner peace
        * Tone: warm, stable, optimistic, supportive
        * Visual pacing: smooth, flowing, continuous

        * Music Translation:
            * Shift toward major / brighter tonal center
            * Stepwise melody, consonance
            * Stable rhythm, consistent pulse

        * Story Requirements:
            * Acts as foundation or emotional “home”
            * Provides contrast and healing to A-world
            * Can appear as:
                * Memory / flashback
                * Parallel reality
                * Inner emotional state
                * Future resolution

*** Motif Continuity (CRITICAL REQUIREMENT)
    ** Identify a core motif (emotional + visual + symbolic) from A-world
    ** Reintroduce it in B-world in a “healed / transformed” form:
        * Same visual element but brighter context
        * Same action but peaceful instead of chaotic
        * Same relationship but reconciled

    This creates a musical analogy:
        * same melodic cell → re-harmonized from tension → resolution

*** Narrative Structure
    ** Build a full cinematic arc, but interwoven across A/B layers (not strictly linear):

    ** Beginning
        * Introduce A-world conflict
        * Hint at B-world (subtle, incomplete, or distant)

    ** Development
        * Escalate A-world tension
        * Intercut or gradually reveal B-world as contrast/support

    ** Climax
        * A-world reaches peak instability (danger, breakdown, decision moment)
        * B-world begins to bleed into or influence A-world

    ** Resolution
        * A transformation occurs:
            * Either A-world resolves into B-world
            * OR both layers merge into a unified emotional state
        * Motif returns in resolved / harmonious form

*** Visual Storytelling Rules
    ** Do NOT follow lyrics line-by-line
    ** Do NOT explain lyrics literally

    ** Instead:
        * Translate emotion → action, environment, character behavior
        * Use cinematic imagery (lighting, movement, contrast, pacing)
        * Sync with music energy:
            * Intense → conflict / danger / motion
            * Soft → intimacy / memory / stillness
            * Drop / chorus → visual impact or turning point


*** Output Format:

[
        {{
            "episode": "1",
            "caption": "title of the story. In {language}.",
            "visual": "the picture of this beat, including the A-world or B-world contrast. No on-image text. In {language}.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]

    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Lyrics / Reference Content (analyzed_content):
    {content}

"""

COUNSELING_ANALYZE = """
Role:
    - You are an expert editor, narrative organizer, and information architect.
    - Your task is to read the following text and reorganize it into a clearer and more structured version.
        - NOT to summarize the text too much.
        - Preserve the richness, and narrative quality of the original content while reorganizing it so the ideas and stories become clearer to follow.

Input:
    - The original text content (in user-prompt) may be messy, fragmented, repetitive, or jump between ideas. Some parts may appear out of order or loosely connected.

Important requirements:
    - Organize and analyze the text in detail, following its original meaning. Do not drop anything: every idea, story, example, and detail of the original must still be there.
    - Do NOT summarize, compress, or remove meaningful content.
    - Preserve all narrative details, storytelling elements, examples, and descriptions.
    - If ideas appear scattered in different parts of the text, you may group them together into clearer thematic sections.
    - You may reorganize the order of paragraphs to improve clarity and logical flow.
    - You may rewrite sentences slightly to make them clearer, but the meaning and richness must remain intact.

Output format:
    - Give the rewritten content in {language}.
        
    - Organize the content into clear sections with headings if appropriate.
    - Within each section, keep the narrative and descriptive style of the original text.
    - Maintain the storytelling tone and psychological or descriptive depth present in the original material.

    Your final output should feel like a cleaned, structured, and logically organized version of the same text, while preserving narrative detail.

"""


# ---------------------------------------------------------------------------
# 动态场景模板：Step Story（步数可选）与「直接生成系列节目」（第 k 集 / 共 N 集）
# 下拉里只放一个 label；真正的模板在生成提示词时按参数现拼。
# ---------------------------------------------------------------------------
STEP_STORY_LABEL = "Step Story"
STEP_STORY_MIN, STEP_STORY_MAX, STEP_STORY_DEFAULT = 1, 6, 3
STEP_IMAGE_LABEL = "图片分解 (Step Image)"
SCENE_SUMMARY_IMAGE_LABEL = "场景总图 (Scene Summary Image)"
SCENE_SUMMARY_IMAGE_TEMPLATE_MARK = "[[SCENE_SUMMARY_IMAGE]] scene_content → 一张总图；提示词由 config_prompt.build_scene_summary_image_prompt 现拼。"
STEP_IMAGE_TEMPLATE_MARK = "[[STEP_IMAGE]] 单图 → 第 k 步细节图；提示词由 config_prompt.build_step_image_clipbody 现拼。"
SERIES_DIRECT_LABEL = "直接生成系列节目 (Series Direct)"
SERIES_DIRECT_MAX_EPISODES, SERIES_DIRECT_DEFAULT_EPISODES = 12, 3


def build_step_story(core: str, steps: int = STEP_STORY_DEFAULT, length: str | None = None) -> str:
    """``*_STORY_CORE`` → N 场故事模板。

    1 步 = 旧 Short Story（每场 300–500 字）；2 步起每场 150–300 字（与旧 N Step 常量逐字相同）。
    """
    try:
        n = int(steps)
    except (TypeError, ValueError):
        n = STEP_STORY_DEFAULT
    n = max(1, min(n, 12))
    if length is None:
        length = "300–500" if n == 1 else "150–300"
    return core.replace("###LENGTH###", length).replace("###STEP###", str(n))


def _clamp_episode(k, n) -> tuple[int, int]:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = SERIES_DIRECT_DEFAULT_EPISODES
    n = max(1, min(n, SERIES_DIRECT_MAX_EPISODES))
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 1
    return max(1, min(k, n)), n


SERIES_DIRECT_CORE = """
*** ROLE: Writer and host of a recorded series program. The material below describes the WHOLE series. Write ONLY episode ###K### of ###N###.

## STEP 1 — PLAN EPISODE ###K### (internal only; do NOT output)
    ** From the material alone, work out how the series falls into ###N### episodes, then for episode ###K###: its theme, its key points, any dialogue or examples the material already gives for it, and where it stops and ###OTHERS### begin.
    ** Use only what belongs to episode ###K###. Do not write ###OTHERS###. Do not add facts, cases or teachings the material does not contain.

## STEP 2 — WRITE EPISODE ###K###
    ** A complete, detailed script that can be recorded as is: real spoken lines, not an outline.
    ** Flow: title → opening → dialogue → explanation → connection to daily life → transitions → ending → teaser (only when a next episode follows). Keep the existing dialogue of the material, made natural to say aloud.
###CONTINUITY###
    ** Voice: first person, natural and warm, the way people really talk. Tell it as a story; no numbered lists, no headings read aloud.
    ** Never mention the material, a PDF, a document, a book or "the source". Speak as if this is simply our program.

## STEP 3 — SCENES FOR THE VIDEO
    ** The script is cut into scenes in watch order, about 8 to 15 scenes, one beat of the script per scene (opening, each dialogue run, each explanation, life connection, ending, teaser). Transitions sit inside the scenes they join.
    ** Every scene has "episode": "###K###". The first scene's caption is "第###K###集 · " + the episode title; other captions are short scene titles.
    ** Host look for this run: {narrator}. The host or explainer is this 讲员, not a separate 人物. A host-only scene: ``actor`` is exactly ``讲员：{narrator}`` and the lines are marked ``<1>``.
    ** visual: a film-still of the place and how the people act on each other, and a cut or another angle when the picture should move. No words on the image.
    ** One scene per page does NOT apply: when the source is a PDF, it describes the whole series; take only episode ###K###'s part. Omit start and end.

*** OUTPUT
    * One JSON array, all text in {language}:

[
    {{
        "episode": "###K###",
        "caption": "第###K###集 · title in {language}.",
        "visual": "Film-still, the place, their interaction, and any cut. No on-image text. In {language}.",
        "speaking": "The whole spoken text of this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx。<1> xxx。 In {language}.",
        "actor": "Everyone visible, at most four, the one 讲员 included, joined with | only. Each 人物 is gender/age band/ethnicity/name: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. Age band is kids, youth, teenager, mature, or senior; no number. If the narrator presents this scene, 讲员：{narrator} is position 1. Never put mood, gesture, or camera direction in actor."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** Series material (analyzed_content, or the PDF named for this run):
    {content}
"""


def _series_continuity(k: int, n: int) -> str:
    lines = []
    if n == 1:
        lines.append("This is a single-episode program: open it (greet, say what we will walk through) and close it fully. No teaser.")
    else:
        if k == 1:
            lines.append(f"Episode 1 opens the series: greet the audience, say in a few natural sentences what these {n} episodes will walk through and why it matters, then enter this episode's theme.")
        else:
            lines.append(f"Carry on from episode {k - 1}: open with one or two natural sentences that pick up where we left off. No full recap.")
        if k < n:
            lines.append(f"Leave a hook for episode {k + 1}: a short teaser or question pointing to its theme, without explaining its content.")
        else:
            lines.append(f"This is the last episode: close the whole series, gather in a few natural sentences what the {n} episodes walked through, and leave one warm, concrete takeaway. No teaser.")
    return "\n".join("    ** " + x for x in lines)


def _series_others(k: int, n: int) -> str:
    others = [str(i) for i in range(1, n + 1) if i != k]
    if not others:
        return "nothing else"
    if len(others) == 1:
        return f"episode {others[0]}"
    return "episodes " + ", ".join(others[:-1]) + " and " + others[-1]


def build_series_direct(episode: int = 1, episodes: int = SERIES_DIRECT_DEFAULT_EPISODES) -> str:
    """「直接生成系列节目」：只生成第 k 集（共 N 集），承上启下。"""
    k, n = _clamp_episode(episode, episodes)
    return (
        SERIES_DIRECT_CORE.replace("###CONTINUITY###", _series_continuity(k, n))
        .replace("###OTHERS###", _series_others(k, n))
        .replace("###K###", str(k))
        .replace("###N###", str(n))
    )


SERIES_DIRECT_DEFAULT = build_series_direct(1, SERIES_DIRECT_DEFAULT_EPISODES)

_LEGACY_STEP_RE = __import__("re").compile(r"^\s*([1-9])\s*step\s*story\s*$", __import__("re").I)


def legacy_step_label(label: str) -> int | None:
    """旧的 ``"3 Step Story"`` label → 步数；不是就返回 None。"""
    if (label or "").strip().lower() == "short story":
        return 1  # Short Story 已并入 Step Story（1 步）
    m = _LEGACY_STEP_RE.match(label or "")
    return int(m.group(1)) if m else None


def is_step_image_label(label: str) -> bool:
    return (label or "").strip() == STEP_IMAGE_LABEL


def is_scene_summary_image_label(label: str) -> bool:
    return (label or "").strip() == SCENE_SUMMARY_IMAGE_LABEL


def is_step_story_label(label: str) -> bool:
    return (label or "").strip() == STEP_STORY_LABEL


def is_series_direct_label(label: str) -> bool:
    return (label or "").strip() == SERIES_DIRECT_LABEL


def resolve_dynamic_scene_template(label: str, template: str, params: dict | None = None) -> str:
    """按下拉 label + 参数（steps / episode / episodes）现拼模板；其它 label 原样返回。"""
    params = params or {}
    if is_step_story_label(label):
        core = _STEP_STORY_CORES.get(template)
        if core:
            return build_step_story(core, params.get("steps") or STEP_STORY_DEFAULT)
    elif is_series_direct_label(label):
        return build_series_direct(
            params.get("episode") or 1,
            params.get("episodes") or SERIES_DIRECT_DEFAULT_EPISODES,
        )
    return template


def visual_style_prompt_block(visual_style: str) -> str:
    """所选画面风格写进场景提示词（风格名取自 config.VISUAL_STYLE_OPTIONS）。"""
    vs = (visual_style or "").strip()
    if not vs:
        return ""
    return (
        f"Visual_Style: {vs}\n"
        f"    ** Write every \"visual\" so it can be drawn in this style ({vs}): its look, light, colour and texture. "
        "Do not name the style inside the JSON text."
    )



COUNSELING_STORY_CORE = """
You are a psychological counselor and master of high-empathy storytelling. 
    ** Your task is to transform a deep psychological analysis report / case-study (input) into an emotionally immersive / authentic human story so listeners recognize themselves through narrative—not psychology. 


## STEP 1 — IDENTIFY / EXTRACT PSYCHOLOGICAL DNA (internal only; do NOT output)

    ** If the input content include more than one case-study / case-story / analysis,  only focus on the 1st one, ignore others)
    ** Then identify / Extract following psychological DNA : 
	    * Visible Problem; 
        * Invisible Knot—wound, unmet need, fear, loyalty, belief, burden, conflict; 
        * Emotional Cost & Hidden Fear—pain, avoidance, self-sabotage; 
        * Repeating Life Pattern; 
        * Healing Door / light at the tunnel — small shift toward movement.


## STEP 2 — CREATE STORY

    ** Objective:
        * Translate the PSYCHOLOGICAL DNA [from STEP 1] into ONE grounded, visceral narrative story, which evoke a profound sense of recognition ("That feels like me") purely through storytelling, without ever explaining the underlying psychology.
        * Length: the whole (ONE) story has ###STEP### scenes;  each scene' content is about ###LENGTH### char
		* If more than one Scenes, they should conneced tighly following the emotional development of ONE story (a single relationship). And a typical Narrative Arc can be: Setup - Core Conflict - Shift (subtle turning point) - Ending (hopeful but not "everything solved")

    ** Execution & Style**
        * Show, Don't Tell: Events are just vehicles; the emotional pattern is the destination. 
			* NO clinical or academic language. NO therapy speeches, counseling notes.
			* NO summarizing the "lesson," "moral," or the psychological insight at the end.
        * Subtextual Dialogue: Keep conversations natural. Characters should talk around their issues.
        * If two people are in the life, most scenes are both of them. Both people speak inside ``speaking``, each with their own ``<N>``, said aloud, not as a private thought. They may trade lines. Swap who is first from scene to scene. One scene of a person alone is enough. Do not make the whole story a single actor thinking.

## STEP 3 - (Json structure)
    * (1) **Caption**: poetic, evocative title of the story & scene. 
    * (2) **Voiceover**: 2–3 short rhythmic sentences—a sigh of relief (not a lecture). Express the psychological insight as gentle life guidance.
        * Host look chosen for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, not a separate 人物.
        * Position 2 says this field. That is the second person, or the narrator when 讲员 is in position 2.
        * Exactly one story person, and you choose to include the host: this field is the host's line.
        * The scene is only the host: ``speaking`` is the host, and this field is empty.
    * (3) **Visual**: the story visual scene (all scenes (if more than 1) should be connected to express ONE story). No words painted on the image.
        * Include the place, and what the people do to each other: a hand, a step back, walking side by side.
        * When they move or answer, the picture may change — a cut, another angle, a closer shot. Write that change here so the video can cut.
    * (4) **Speaking**: one powerful line, the FIRST actor, poignant 1st-person, daily life language.
    * (5) **Actor**: everyone visible, at most four people in all, the one 讲员 included, then 讲员 if the narrator is in this scene. Join with " | ". Never use ";".
        * There is no voiceover field. Every line is in ``speaking``, marked with ``<N>``. Only three people speak. The fourth only appears and has no line.
        * Each 人物 has gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村``.
        * Age band is kids, youth, teenager, mature, or senior. No age number. Without a name: woman/mature/chinese.
        * When the source is a picture or a PDF page, read the age band from how that person looks. The words rarely give an age. A name in the picture or the text goes last. The same person keeps that age band in every scene.
        * If the narrator is presenting this scene, ``讲员：{narrator}`` is position 1 and is not also a 人物.
        * Mood, gesture, and camera direction are not people.

    like this (the story has ###STEP### scene (###STEP### json objects)) :
    [
        {{
            "caption": "Title in {language}.",
            "visual": "the story scene, their interaction, and any cut or angle change. about ###LENGTH### {language} char. No on-image text.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村 | 人物3：woman/kids/chinese"
        }}
    ]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}
"""

COUNSELING_STORY_2STEP = build_step_story(COUNSELING_STORY_CORE, 2)
COUNSELING_STORY_3STEP = build_step_story(COUNSELING_STORY_CORE, 3)
COUNSELING_STORY_4STEP = build_step_story(COUNSELING_STORY_CORE, 4)
COUNSELING_STORY_5STEP = build_step_story(COUNSELING_STORY_CORE, 5)
COUNSELING_STORY_6STEP = build_step_story(COUNSELING_STORY_CORE, 6)

COUNSELING_STORY_SHORT = build_step_story(COUNSELING_STORY_CORE, 1)



COUNSELING_SERIES_COUNSELOR_FRAME = """
*** ROLE: Senior Psychological Counselor, one finished program about ONE psychological problem
    ** Read the analysis first and choose ONE path. Do not mix the paths.
    ** PATH A — the analysis is one life, one relationship, one timeline.
    ** PATH B — the analysis holds two or more distinct situations (different people, or clearly separate cases). Do not collapse those into one couple.
    ** In both paths the audience must see the life in full before any remedy. The remedy is the most important part of the program and must be detailed. It is never one slogan scene.

*** CAST CHOSEN BY THE USER (this decides who appears and who speaks; it overrides any other wording about the 讲员 or guests below)
    {cast}
    ** When the CAST above lists people, use exactly those people, with exactly those looks, in ``actor``. Write each one as listed: ``讲员：<look>`` or ``人物N：gender/age band/ethnicity/name``. Keep the order the user gave unless a rule below puts the 讲员 first.
    ** RELATIONSHIPS. Read gender, age band, ethnicity, and name of every listed person and decide who they are to each other before writing any scene. A girl or a teenage girl together with an adult man → daughter and father. A boy with an adult woman → son and mother. A boy and a girl of similar age → siblings or classmates. Two adults of opposite gender and similar age → usually a couple. A senior with a youth or a child → grandparent and grandchild. The same family name, or names that fit one family, strengthens a family tie. Fit the relationship to the story material when the material says more. Then build every scene, every line, and every action on that relationship: how they address each other, who protects whom, who argues with whom. Keep the same relationship in every scene.
    ** PER-SCENE BEHAVIOR. In ``actor``, after every person's id, add one pair of parentheses saying what THIS person does in THIS scene: emotion, action, how they speak, enter, or leave. Example: ``讲员:<look>(平静,面向镜头)`` or ``人物1:woman/mature/chinese/名字(焦虑,低头搓手)``. The parentheses are not part of the id; the picture is chosen from the id before them. Every visible person has them, and they must match ``visual``.
    ** If the CAST says "No cast was chosen", follow the older host wording below as before.
    ** WHO IS WHO, decided only by the CAST:
        * CAST is EMPTY: nobody is on screen as a speaker. Every counselor beat is a default narrator voice-over (``<1>``, ``actor`` ""), exactly like a podcast voice-over. Story scenes still show the life, the people acting silently in the visual.
        * The 讲员 is the counselor and the protagonist of the program. Every counselor beat (naming the problem, background, transitions, unpacking, remedy) is the 讲员. Only one 讲员. Do not invent another age, gender, or face.
        * The 人物 are ACTORS in the story, not guests. They perform the spoken content: through dialogue with each other, actions, exclamations, and visible emotion, inside the place where the life happens. They speak as the people in the story, never as commentators about it.
        * No 讲员 but 人物 listed: there is no on-screen counselor. Counselor beats become voice-over scenes: ``actor`` is "", the counselor narration is ``<1>``, and the visual shows the life silently. The 人物 still act the story in the story scenes.

*** SHARED RULES
    ** visual is a film-still with no words on the image. Also the place, how the people act on each other, and a cut or another angle when the picture should move.
    ** THIS IS A SWITCH, NOT A PODCAST. A podcast stays in one conversation about someone else's life and nobody performs it. Here the picture changes job.
    ** Counselor beat: the 讲员 speaks as a third person, giving the background of this story, this scene, or what the audience is about to see. On a beat that is only the 讲员, ``actor`` is exactly ``讲员：<look>``. No 人物.
    ** Then switch into the life. The 人物 are in that place, performing. They talk to each other, act, exclaim, show emotion. They are acting this life, not discussing it from outside.
    ** The 讲员 may stand in that same scene and speak to them. The 人物 can answer the 讲员. While that is happening they are still performing the life, not sitting as guests.
    ** Then it may switch back. The 讲员 narrates again. A performance scene is still the life being acted, even when the 讲员 is in it. Do not turn that scene into a studio discussion about those people.
    ** List everyone visible, at most four people in all, the 讲员 included, using the CAST looks. There is no voiceover field. ``speaking`` holds every line, marked with ``<N>`` for that person's place in actor. Only the first three people listed may speak. If the 讲员 is presenting, 讲员 is position 1.
    ** When a picture or a PDF page shows a person not in the CAST, the age band comes from the face and body: kids, youth, teenager, mature, or senior. Do not write a number. The same person keeps one age band.
    ** No DSM labels. No "the lesson is". Do not say 根, 根儿, or 病根 in caption or speaking. Name the problem in ordinary professional language.
    ** Do not solve a life inside the story scenes. Do not skip from the first quarrel to the ending in one scene.
    ** Inside a story run, in this order, shown in what people do: a concrete moment where the struggle is visible and the cause is not named; the same move repeating, and the price; one moment where that way of coping fails; then it becomes plain why they keep doing it.
    ** When the remedy returns to those people, echo that opening moment: a similar situation, a different response, so the change is visible. One small step, not a cured life.

*** PATH A — one complete story
    ** 1. Counselor, 1 scene, to camera. Name the problem: what it is, where it shows up, why it matters. Do not open in someone's kitchen. Do not preview the ending.
    ** 2. Story, 5 to 8 consecutive scenes. SAME people, ONE timeline.
        * How this life was, then how the problem is lived in detail (what is said, avoided, repeated, what it costs), until they are stuck.
        * If two people share this life, most of these scenes show the two of them. They do not speak. The 讲员's speaking tells what they are doing. Their actions are in visual and in the parentheses.
    ** 3. Remedy, after the story is finished. Several scenes, not one.
        * First 2 to 3 counselor scenes: take the problem apart in order (how it starts, what keeps it going, what it costs), then the response, step by step.
        * Then 2 to 3 scenes with the SAME people, later: one concrete step per scene, shown in the room, not announced as a list.
    ** No episode titles. No second case.

*** PATH B — several cases of the same problem
    ** Each case is one episode that can be played alone: it has a counselor opening and a counselor closing. The remedy is NOT inside the episode. It comes only after every case.
    ** Between two episodes the counselor speaks TWO scenes in a row. Together they are one continuous turn of speech, so a viewer who watches straight through hears one passage. A cut between those two scenes is allowed: the first scene is a possible end of the episode, the second is a possible start of the next. Do not put a title card, a "previously", or a hard stop in the words. The second scene should sound like the next sentence, not a new program.
    ** For EACH situation, in the analysis's order. Different people. Do not reuse the same spouse, home, and argument.
        * Open — 1 counselor scene. Caption "第N集 · ".
            * Episode 1: name the shared problem, then the first way it usually shows up, and enter this life. No remedy.
            * Later episodes: pick up the question left by the previous closing scene. Say that the same problem often shows up in another way (a second face, a third face), and enter THIS life. No remedy. No recap of the previous plot.
        * Story — 4 to 7 consecutive scenes. This case only, from how the life was, through the problem in detail, to where they are stuck. If it is a couple, most of these scenes show the two of them performing. They do not speak. The 讲员 tells it.
        * Close — 1 counselor scene. Still this episode. Caption "第N集 · 承接".
            * Not a summary of the plot and not an answer. Hold what the audience just saw, turn it into a question, and point toward the problem underneath. Leave them thinking. Do not name a method. Do not say "next episode".
            * If another case follows, the last sentence should be able to lead into that case's opening scene without a break in thought.
            * If this is the last case, the question stays open for the remedy block. Do not start the remedy here.
    ** Only after EVERY case has been told: the remedy block. Caption these "方案 · ", not "第N集". Multiple scenes. This is the detailed answer.
        * First 2 to 3 counselor scenes: take the shared problem apart (how it starts, what keeps it going, what it costs) across the cases just watched.
        * Then each response in its own short run. Say which cases it fits. One response may fit only the second and third. Another may fit the first as well, or all of them. Do not cover every life with one sentence.
        * When a response is shown inside a life, use 2 to 3 scenes with THOSE people, one step per scene.
        * End with 1 counselor scene: the conclusion. Do not retell the plots. Do not open a new case.

*** OUTPUT
    * One JSON array in watch order. All text in {language}.
    * Every scene object MUST include "episode" (a string "1", "2", "3", … with no other text). It follows the EPISODES block: 5 to 15 scenes per episode.
    * PATH A: scene 1 caption is the program title. No "第N集". The episode numbers come from the EPISODES block. When the whole program is 15 scenes or fewer, every scene, including the remedy, is "episode": "1".
    * PATH B: episode open is "第N集 · ". Episode close is "第N集 · 承接". Every scene of case N (open, story, close) is "episode": "N" when that case holds 5 to 15 scenes.
    * PATH B remedy scenes are captioned "方案 · " and share the next number after the last case. Three cases → remedy is "episode": "4". If the remedy holds fewer than 5 scenes, the EPISODES block decides where it goes.

[
    {{
        "episode": "1",
        "caption": "Title. In {language}.",
        "visual": "This scene's story: the place, and what each person is doing. No on-image text. In {language}.",
        "speaking": "Only the 讲员. If the 讲员 is in actor, mark the lines with that 讲员's <N>. If the 讲员 is not in actor, the lines are the 讲员 from behind the picture, and they are not a 人物's lines. 人物 have no lines. In {language}.",
        "actor": "On-camera people, at most four, joined with |. Portrait id, then this scene's behavior: 人物1：woman/mature/chinese/封氏（低头，双手交握） | 人物2：man/youth/chinese/贾雨村（站起来，看向窗外）. 人物 do not speak. Add 讲员：{narrator}（面对镜头，语气放轻） only when the 讲员 is on camera, as position 1. Leave the 讲员 out when the 讲员 speaks from behind the picture."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


COUNSELING_SERIES_STORY_ONLY = """
*** ROLE: Story program (Series · Story Speak), told like a film or a TV drama. The story is carried by the characters talking to each other: ``speaking`` is their dialogue, said aloud in the scene. ``visual`` supports it: the place, the action, and the emotion in the picture help express what is being said.
    ** Read the analysis and choose ONE path.
    ** PATH A — one life, one relationship, one timeline. One episode.
    ** PATH B — two or more distinct situations. Each situation is one episode that can be played alone. Do not merge them into one couple.
    ** The story is told in full before any remedy. The remedy comes after the story (PATH A) or after every episode (PATH B), and it is detailed, and it is SHOWN by the characters as much as possible.

*** CAST CHOSEN BY THE USER (this decides who appears and who speaks; it overrides any other wording about the 讲员 or guests below)
    {cast}
    ** When the CAST above lists people, use exactly those people, with exactly those looks, in ``actor``. Write each one as listed: ``讲员：<look>`` or ``人物N：gender/age band/ethnicity/name``. Keep the order the user gave unless a rule below puts the 讲员 first.
    ** RELATIONSHIPS. Read gender, age band, ethnicity, and name of every listed person and decide who they are to each other before writing any scene. A girl or a teenage girl together with an adult man → daughter and father. A boy with an adult woman → son and mother. A boy and a girl of similar age → siblings or classmates. Two adults of opposite gender and similar age → usually a couple. A senior with a youth or a child → grandparent and grandchild. The same family name, or names that fit one family, strengthens a family tie. Fit the relationship to the story material when the material says more. Then build every scene, every line, and every action on that relationship: how they address each other, who protects whom, who argues with whom. Keep the same relationship in every scene.
    ** PER-SCENE BEHAVIOR. In ``actor``, after every person's id, add one pair of parentheses saying what THIS person does in THIS scene: emotion, action, how they speak, enter, or leave. Example: ``讲员:<look>(平静,面向镜头)`` or ``人物1:woman/mature/chinese/名字(焦虑,低头搓手)``. The parentheses are not part of the id; the picture is chosen from the id before them. Every visible person has them, and they must match ``visual``.
    ** If the CAST says "No cast was chosen", follow the older host wording below as before.
    ** WHO DOES WHAT, decided only by the CAST:
        * The 人物 carry the story. Each story scene is a dramatized moment: they speak the scene's content to each other as dialogue, said aloud, not a summary, while they act, move, and react in the place where it happens, like a scene in a film or TV drama. What they do and how they look must fit and strengthen what they are saying.
        * The 讲员, when listed, is the narrator only: a short introduction and background at the start, brief transitions between parts or episodes, and a brief closing. 2 to 4 sentences each. The 讲员 never takes over a story scene and never explains what the audience can already see. A narrator-only scene has ``actor`` exactly ``讲员：<look>`` and the lines marked ``<1>``.
        * Wherever the PATH sections below say "the host's lines", that is this 讲员, kept brief. Remedy explanations are kept short and the steps are shown by the 人物 acting them out.
        * No 讲员 in the CAST: the whole program is purely acted. No narrator, no voice-over. The opening, transitions, closing, and remedy are carried by the 人物 themselves (a line of dialogue, a gesture, a changed action), and by the caption.
        * CAST is EMPTY: invent the story people from the material (still pure drama, no narrator), giving each a look ``gender/age band/ethnicity/name``.
    ** List everyone visible, at most four people in all, the 讲员 included, using the CAST looks. There is no voiceover field. ``speaking`` holds every line, marked with ``<N>`` for that person's place in actor. Only the first three listed may speak. Never write <4>.
    ** When a picture or a PDF page shows a person not in the CAST, the age band comes from the face and body: kids, youth, teenager, mature, or senior. Do not write a number. The same person keeps one age band.

*** PATH A — one story. When the whole program is 15 scenes or fewer it is one episode, every scene "episode": "1". A longer one follows the EPISODES block.
    ** Start — 1 scene. Caption is the program title. The host's lines in speaking names the problem and enters this life. No remedy.
    ** Story — 5 to 8 consecutive scenes. Same people. From how the life was, through the problem in detail, to where they are stuck.
    ** End — 1 scene. The host's lines in speaking holds what we saw and leaves a question. No method yet.
    ** Remedy — several scenes, still in the same episode while it holds 15 scenes or fewer.
        * 2 to 3 scenes with the host's lines in speaking: take the problem apart, then the response, step by step.
        * Then 2 to 3 scenes with the same people: one concrete step per scene, shown, not announced.

*** PATH B — one episode per situation. Different people. Do not reuse the same spouse, home, and argument.
    ** An episode is: start, full story, end. A cut between one episode's end scene and the next episode's start scene is allowed. The host's two lines in speaking are one continuous passage: the end does not say "next episode"; the start sounds like the next sentence.
    ** Start — 1 scene. Caption "第N集 · ". "episode": "N".
        * Episode 1: host names the shared problem, then the first way it shows up.
        * Later episodes: host picks up the question from the previous end, says this problem often has another face, and enters THIS life. No remedy. No plot recap.
    ** Story — 4 to 7 consecutive scenes. This case only, until they are stuck. "episode": "N".
    ** End — 1 scene. Caption "第N集 · 承接". "episode": "N".
        * The host's lines in speaking: not a plot summary and not an answer. A question that points under the problem. No method. No "next time".
        * If another case follows, the last line can lead into the next start. If this is the last case, the question stays open for the remedy.
    ** Only after every case: remedy. Caption "方案 · ". "episode" is the next number after the last case (three cases → "4"), unless the EPISODES block says otherwise.
        * 2 to 3 scenes, the host's lines in speaking: unpack the shared problem across the lives just shown.
        * Then each response in its own short run. Say which episodes it fits. One may fit only some; another may fit all.
        * When a response is shown in a life, 2 to 3 scenes with those people, one step per scene. The host's lines in speaking may be one short line, not a speech.
        * Last scene: the host's lines in speaking, the conclusion. Do not retell the plots.

*** RULES
    ** visual: this scene's own story. The place, how these people relate, and what each person is doing. No on-image words. A cut or another angle when the picture should move. The actor parentheses say the same performance again, one person at a time. No DSM labels. Do not say 根, 根儿, or 病根.
    ** Inside a story run, in this order, shown in what people do: a concrete moment where the struggle is visible and the cause is not named; the same move repeating, and the price; one moment where that way of coping fails; then it becomes plain why they keep doing it. Do not fix it there.
    ** When the remedy returns to those people, echo that opening moment: a similar situation, a different response. One small step, not a cured life.

*** OUTPUT
    * One JSON array in watch order. All text in {language}.
    * Every scene includes "episode": "1", "2", "3", … and nothing else in that field. It follows the EPISODES block: 5 to 15 scenes per episode.

[
    {{
        "episode": "1",
        "caption": "第1集 · title, or the program title on PATH A. In {language}.",
        "visual": "This scene's story: the place, how the people relate, and what each person is doing. No on-image text. In {language}.",
        "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
        "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. Join with | only. The portrait id is woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. Example id: woman/mature/chinese/封氏. After every id, parentheses for this scene only: 人物1：woman/mature/chinese/封氏（情绪低，正在祷告） | 人物2：man/youth/chinese/贾雨村（走向门口，神情严肃）. The parentheses are not part of the portrait. If the narrator is on camera, 讲员：{narrator}（怎么出镜、情绪、怎么讲） is position 1 and is not also a 人物."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


# Series · Story Act：人物只演不说。内容放在 ``story_content``（要演出来的事），没有 speaking，不做 TTS。
def _story_act_from_speak(speak: str) -> str:
    cast_start = speak.index("*** CAST CHOSEN BY THE USER")
    cast_end = speak.index("    ** WHO DOES WHAT")
    tail = speak[speak.index("--------------------------------------------------\nINPUT"):]
    return (
        """
*** ROLE: Silent story program (Series · Story Act), told like a silent film. The characters ACT the story out. Nobody speaks.
    ** Read the analysis and choose ONE path.
    ** PATH A — one life, one relationship, one timeline. One episode.
    ** PATH B — two or more distinct situations. Each situation is one episode that can be played alone. Do not merge them into one couple.
    ** The story is shown in full before any remedy. The remedy comes after the story (PATH A) or after every episode (PATH B), and it is SHOWN by the characters, step by step.

"""
        + speak[cast_start:cast_end]
        + """    ** WHO DOES WHAT, decided only by the CAST:
        * The 人物 carry the story by acting only: action, behavior, facial expression, gesture, how they move toward or away from each other, what they do with the things around them. They never speak: no dialogue, no lines, no lip-sync.
        * There is no narrator and no voice-over. A 讲员 in the CAST, if any, appears at most as a silent presence in the first and last scene (watching, turning a page, a small gesture); never in a story scene and never speaking.
        * Openings, transitions, the turn, and the remedy are all carried by what the 人物 do, and by the caption.
        * CAST is EMPTY: invent the story people from the material, giving each a look ``gender/age band/ethnicity/name``.
    ** List everyone visible, at most four people in all, using the CAST looks.
    ** When a picture or a PDF page shows a person not in the CAST, the age band comes from the face and body: kids, youth, teenager, mature, or senior. Do not write a number. The same person keeps one age band.

*** PATH A — one story. When the whole program is 15 scenes or fewer it is one episode, every scene "episode": "1". A longer one follows the EPISODES block.
    ** Start — 1 scene. Caption is the program title. An establishing moment: the place and the people in their ordinary life, with one hint of the problem.
    ** Story — 5 to 8 consecutive scenes. Same people. From how the life was, through the problem in detail, to where they are stuck.
    ** Turn — 1 scene. One moment where their way of coping visibly fails.
    ** Remedy — 3 to 5 scenes with the same people: one concrete step per scene, acted, ending on an echo of the opening moment with a different response.

*** PATH B — one episode per situation. Different people. Do not reuse the same spouse, home, and argument.
    ** Each episode: start (caption "第N集 · "), 4 to 7 story scenes until they are stuck, an end scene (caption "第N集 · 承接") that holds the stuck moment. "episode": "N".
    ** Only after every case: remedy. Caption "方案 · ". "episode" is the next number after the last case. Each response is a short run of 2 to 3 acted scenes with those people, one step per scene.

*** RULES
    ** ``visual`` is the picture: the place, the framing, where each person is, the light. No on-image words.
    ** ``story_content`` is what HAPPENS in this scene, to be acted: who does what, in what order, with what emotion, and how it changes by the end. 2 to 5 short sentences in the present tense. No quoted speech, no "he says", no narration to the audience. Thoughts and feelings are shown through behavior (a hand that stops, a look away, a door left open).
    ** The actor parentheses say each person's performance in this scene, and must match ``story_content``.
    ** Inside a story run, in this order, shown in what people do: a concrete moment where the struggle is visible and the cause is not named; the same move repeating, and the price; one moment where that way of coping fails; then it becomes plain why they keep doing it. Do not fix it there.
    ** No DSM labels. Do not write 根, 根儿, or 病根.

*** OUTPUT
    * One JSON array in watch order. All text in {language}.
    * Every scene includes "episode": "1", "2", "3", … and nothing else in that field. It follows the EPISODES block: 5 to 15 scenes per episode.
    * There is NO ``speaking`` field and no ``voiceover`` field.

[
    {{
        "episode": "1",
        "caption": "第1集 · title, or the program title on PATH A. In {language}.",
        "visual": "The picture: place, framing, where each person is, light. No on-image text. In {language}.",
        "story_content": "What happens in this scene, acted without words: who does what, in order, with what emotion. 2 to 5 short sentences, present tense, no dialogue. In {language}.",
        "actor": "People in this picture, at most four. Join with | only. The portrait id is woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. After every id, parentheses with this person's performance in this scene: 人物1：woman/mature/chinese/封氏（低头，慢慢放下碗） | 人物2：man/youth/chinese/阿明（转身走向门口）"
    }}
]

"""
        + tail
    )


COUNSELING_SERIES_STORY_ACT = _story_act_from_speak(COUNSELING_SERIES_STORY_ONLY)


COUNSELING_TALK_SCENES = """
*** ROLE: A podcast. The speakers talk about the story. The pictures illustrate what is being said.
*** CAST CHOSEN BY THE USER (this decides who appears and who speaks; it overrides any other wording about the 讲员 or guests below)
    {cast}
    ** When the CAST above lists people, use exactly those people, with exactly those looks, in ``actor``. Write each one as listed: ``讲员：<look>`` or ``人物N：gender/age band/ethnicity/name``. Keep the order the user gave unless a rule below puts the 讲员 first.
    ** RELATIONSHIPS. Read gender, age band, ethnicity, and name of every listed person and decide who they are to each other before writing any scene. A girl or a teenage girl together with an adult man → daughter and father. A boy with an adult woman → son and mother. A boy and a girl of similar age → siblings or classmates. Two adults of opposite gender and similar age → usually a couple. A senior with a youth or a child → grandparent and grandchild. The same family name, or names that fit one family, strengthens a family tie. Fit the relationship to the story material when the material says more. Then build every scene, every line, and every action on that relationship: how they address each other, who protects whom, who argues with whom. Keep the same relationship in every scene.
    ** PER-SCENE BEHAVIOR. In ``actor``, after every person's id, add one pair of parentheses saying what THIS person does in THIS scene: emotion, action, how they speak, enter, or leave. Example: ``讲员:<look>(平静,面向镜头)`` or ``人物1:woman/mature/chinese/名字(焦虑,低头搓手)``. The parentheses are not part of the id; the picture is chosen from the id before them. Every visible person has them, and they must match ``visual``.
    ** If the CAST says "No cast was chosen", follow the older host wording below as before.
    ** WHO SPEAKS, decided only by the CAST:
        * CAST is EMPTY (no 讲员, no 人物): nobody is on screen as a speaker. The whole episode is one default narrator voice-over. ``actor`` is empty (""). ``speaking`` is the narration, marked ``<1>``.
        * Only the 讲员: the 讲员 alone speaks, telling and explaining the story. ``actor`` is ``讲员：<look>``. Every line is ``<1>``.
        * 讲员 + exactly one 人物: a two-person podcast. The 讲员 is the host, the 人物 is the guest. They talk back and forth: question, reply, example, follow-up. ``actor`` is ``讲员：<look> | 人物1：<look>``, host first.
        * 讲员 + two or more 人物: the 讲员 hosts and the 人物 are several guests. Each guest gets turns. At most three people speak in one scene, host included; pick which guests join each scene. A fourth listed person may sit in the picture without a line. Never write <4>.
        * No 讲员 but one or more 人物: the FIRST listed 人物 is the host. The other 人物 are guests, following the same rules as above. Do not invent a 讲员.
    ** The speakers are a third party. They talk ABOUT the people in the story. They never act out the story themselves, and the story's people never speak.
    ** VISUALS SUPPORT THE WORDS. ``visual`` is always supporting information: it illustrates the story content being spoken in this scene (the place, the moment, the people of the story, what they do). Any people shown in the visual act silently: no lines, no lip-sync, only gesture, expression, and movement. The speakers may appear in the studio between illustrations, but the visual never carries the dialogue.
    ** This is not Series · Counselor, Story Speak, or Story Act: nobody performs the story.

*** HOW THE SERIES MOVES
    ** It is one podcast series about one subject. If the material has several parts, each part is one episode. If it is one subject, it is still episode 1 of a series, and the ending may leave a next question. The EPISODES block decides how the scenes group into episodes.
    ** Talk the way a podcast talks: question, reply, a short example from life, a follow-up. Not a monologue. Not a slide reading.
    ** From the surface to what is actually going on, in plain language. A listener should be able to follow. Do not open with the conclusion.
    ** Keep the details that make a moment hearable: who, where, what was said, what was avoided. Cut repeated wording. Do not shrink a lived moment into one abstract sentence.
    ** Do not say 根, 根儿, or 病根. Do not use DSM labels.
    ** End the episode on what they now see, said in their own words. One concrete thing a listener could notice or try. Not a worksheet.

*** SCENES (5 to 15 for each episode, one beat each)
    ** This describes the shape of ONE episode. It is not the scene count of the whole program. When the source is an audio file or a video, the SCENES FOLLOW THE SOURCE rules below decide the scene count and where each scene cuts (about 30 seconds each), so a long recording has many scenes and several episodes. Each episode then follows this shape in its own way.
    ** 1. The program opens. The host (or the voice-over) names this episode's question and steps into the story.
    ** Next several. A real moment from that life is told: how it repeats, what it costs. With guests, each scene is one exchange between host and guest(s). The visual shows that moment silently.
    ** Then the turn. A question (or, with only one voice, a turn in the telling) names what is underneath.
    ** Last 2–3. Land the episode. Come back to the opening moment and say what would be different. If another part remains in the material, the last line can point at it without telling that episode.

*** OUTPUT
    * JSON array in watch order. All text in {language}.
    * ``actor`` lists only the speakers chosen by the CAST rules above (host first, then the guests who speak in this scene), at most four. Use the CAST looks exactly. Empty CAST → ``actor`` is "".
    * ``speaking`` holds every line, marked with <N> for that speaker's place in actor. Only the first three people listed may speak. Empty CAST → one voice-over, ``<1>``.
    * ``visual`` illustrates the content being spoken: the story's place, moment, and people, acting silently. No words on the image. It may cut back to the speakers in the studio when nothing in the story is being described.
    * When a picture or a PDF page shows a person, the age band comes from the face and body: kids, youth, teenager, mature, or senior. Do not write a number.
    * caption: scene 1 is the program title; later scenes are short beat titles.
    * Every scene includes "episode", set by the EPISODES block: 5 to 15 scenes per episode.

[
    {{
        "episode": "1",
        "caption": "Program title on scene 1. In {language}.",
        "visual": "The story moment being talked about, its place and people acting silently; or the speakers in the studio. Any cut. No on-image text. In {language}.",
        "speaking": "Every line in this scene, marked with <N> for the speaker's place in actor, from 1. At most three speakers. Never write <4>. Example: <1> xxx。<2> xxx, xxx。<1> xxx。 In {language}.",
        "actor": "The speakers from the CAST, host first. Example: 讲员：woman/mature/chinese/秦 | 人物1：man/mature/chinese/嘉宾. Empty when the CAST is empty."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""



# =============================================================================
# FlyLink / 航迅 — Low-Altitude Aviation, UAV Manufacturing, Aircraft Communication
# =============================================================================

FLYLINK_ANALYZE = """
Role:
    - You are an expert aviation-industry editor, technical narrative organizer, and information architect.
    - Your task is to read the following text and reorganize it into a clearer, more structured version for low-altitude aviation content.
        - NOT to over-summarize or strip technical nuance.
        - Preserve operational detail, scenario context, regulatory notes, and business logic while improving clarity and flow.

Input:
    - The original text may be fragmented notes, slide bullets, meeting minutes, case descriptions, or mixed technical + business material.

Important requirements:
    - Organize and analyze the text in detail, following its original meaning. Do not drop anything: every fact, figure, scenario, and example of the original must still be there.
    - Do NOT remove meaningful technical facts, scenario parameters, or deployment details.
    - Preserve examples: routes, aircraft types, communication links, workshop stages, regulatory constraints, ROI logic.
    - Group scattered ideas into thematic sections (e.g., communication stack, manufacturing flow, scenario ops, governance).
    - Rewrite only for clarity; meaning and richness must remain intact.

Output format:
    - Give the rewritten content in {language}.
    - Use clear section headings where appropriate.
    - Keep a professional but accessible industry-documentary tone.
    - Suitable as source material for case videos about UAV manufacturing, aircraft communication, and low-altitude economy operations.
"""


FLYLINK_STORY_CORE = """
You are a senior aviation-industry storyteller and low-altitude economy analyst.
    ** Transform an industry analysis / deployment case (input) into an immersive, credible narrative so viewers recognize real operational challenges — not abstract buzzwords.


## STEP 1 — IDENTIFY / EXTRACT CASE DNA (internal only; do NOT output)

    ** If the input includes more than one case, focus on the 1st one only.
    ** Extract:
        * Visible Problem — what fails or hurts in daily operations;
        * Hidden Constraint — technical bottleneck, comms gap, regulatory friction, supply-chain limit, safety risk;
        * Operational Cost — delay, incident risk, margin erosion, scale blocker;
        * Repeating Pattern — same failure across routes, shifts, sites, or product variants;
        * Opening Door — pilot fix, architecture shift, policy window, or integrated platform path.


## STEP 2 — CREATE STORY

    ** Objective:
        * Translate CASE DNA into ONE grounded industry narrative with cinematic realism.
        * Length: the whole story has ###STEP### scenes; each scene is about ###LENGTH### chars.
        * If more than one scene, they must follow ONE deployment / ONE product line / ONE operational thread.
        * Typical arc: Field Pain → System Constraint → Critical Incident or Decision → Root Insight → Integrated Response → Scaled Outcome (hopeful but realistic).

    ** Execution & Style**
        * Show operations, don't lecture: hangar floor, control room, tower screen, logistics hub, rural landing zone.
        * NO generic "the future is bright" slogans. NO empty policy quotes without context.
        * Dialogue: engineers, pilots, dispatchers, regulators, operators — natural speech, not white-paper tone.

## STEP 3 - (Json structure)
    * (1) **Caption**: concise scene / story title.
    * (2) **Voiceover**: 2–3 short rhythmic sentences — industry insight as field guidance, not textbook definition.
    * (3) **Visual**: cinematic operational scene (connected across scenes if multi-scene).
    * (4) **Speaking**: one powerful 1st-person line from operator, engineer, or pilot.

    Output (###STEP### scene(s)):
    [
        {{
            "episode": "1",
            "caption": "Title in {language}.",
            "visual": "Operational scene with environment, equipment, people, action. About ###LENGTH### {language} chars. No on-image text.",
            "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
            "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
        }}
    ]

    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}
"""

FLYLINK_STORY_2STEP = build_step_story(FLYLINK_STORY_CORE, 2)
FLYLINK_STORY_3STEP = build_step_story(FLYLINK_STORY_CORE, 3)
FLYLINK_STORY_4STEP = build_step_story(FLYLINK_STORY_CORE, 4)
FLYLINK_STORY_LONG = FLYLINK_STORY_CORE.replace("###LENGTH###", "500–1000").replace("###STEP###", "1")
FLYLINK_STORY_SHORT = build_step_story(FLYLINK_STORY_CORE, 1)
FLYLINK_STORY_MINI = FLYLINK_STORY_CORE.replace("###LENGTH###", "150–300").replace("###STEP###", "1")


FLYLINK_UNIFIED_NARRATIVE_SPINE = """

*** SCENE RULES:
    ** ONE CASE, ONE THREAD (mandatory)
        * Every scene advances ONE deployment case, ONE product program, or ONE operational scenario only.
        * Forbidden: unrelated vignettes, new protagonists without VO intro, or a fresh "industry lesson" each scene.
        * Insight emerges through operations — not acronym dumps on screen.

    ** Typical INDUSTRY CASE SPINE (across all scenes)
        * progress:
            * Surface — concrete field moment; pain visible in workflow, equipment, or schedule
            * Pattern — same constraint repeats; cost / risk escalates; workaround becomes obvious
            * Root — comms failure, process gap, regulatory boundary, or integration debt exposed
            * Way-out — pilot architecture, SOP change, platform link, or governance path (credible, not magic)

    ** SHOW, DON'T TELL
        * Reveal constraints via control-room alarms, missed handoffs, rework on assembly line, weather hold, link dropout — not slide bullets in visual.

    ** VISUAL
        * CLEAN DOCUMENTARY STILL (slideshow): hangar, drone bay, ATC/UTM screen, logistics apron, training field, emergency response.
        * ``caption`` / ``speaking`` = audio/metadata only — never pasted as on-image text in ``visual``.
"""


FLYLINK_CONTENT_SCENES = """
*** ROLE: Senior Aviation Industry Producer & Scenario Documentarian
    ** Expertise: aircraft communication, UAV R&D/manufacturing, low-altitude economy operations (UTM, logistics, tourism, UAM, special missions).

*** YOUR TASK
    ** Input: the reference below. It may be written analyzed_content, a PDF, the speech in an audio file, or the spoken words in a video.
    ** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
    ** Output: ONE continuous documentary/video as a JSON array of scenes.
    ** Same operational thread from first frame to last.
    ** No fixed scene count or per-scene length cap — use as many scenes as the case needs.
    ** Slideshow rule: each ``visual`` = CLEAN image — story through environment, people, equipment; almost no words on screen.

""" + FLYLINK_UNIFIED_NARRATIVE_SPINE + """

*** SCENE FIELDS (all text in {language})
    ** Host look for this run: {narrator}. A third person who explains or tells the story (说书人 / storyteller) is this 讲员, {narrator}, not a separate 人物. Every scene includes "episode": "1".
    ** List everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last: ``人物1：woman/mature/chinese/封氏``. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Put ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.
    ** One person and the host: add ``讲员：{narrator}`` after the story person. The host's lines stay inside ``speaking`` with that person's ``<N>``.
    ** Host-only: the narrator is the only speaker, so the narrator is the only actor. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.
    1) episode — "1"
    2) caption — scene / program title (metadata only)
    3) speaking — the second person, or the host when the host is in this scene
    4) visual — clean documentary still; operational detail, lighting, geography. No on-image text.
    5) speaking — the first person, or empty on a host-only scene
    6) actor — up to 人物1–人物4, each woman/mature/chinese/封氏, then 讲员：{narrator} when the narrator is in the scene. Position 1 speaks. Position 2 answers.

INPUT:
** Topic: {topic}
** Instruction: {instruction}
** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content): {content}

OUTPUT: STRICT JSON array of scenes.
"""


COMIC_ANALYZE = """
Role:
    - You are an editor for picture stories.
    - Read the text and put the story in order. Keep the events. Do not add a moral.
    - Follow the original meaning in detail. Do not drop anything: every event, person, and line of the original stays.

Output:
    - Rewritten story in {language}.
    - Short sections, in the order of the pictures.
"""


COMIC_STRIP_SCENES = """
*** ROLE: Picture-story editor.
    ** The source is a comic PDF, one picture a page, or this episode already written as scenes, one scene a page. It may also be the speech in an audio file, or the spoken words in a video.
    ** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
    ** Output is strict one-to-one. Do not add a scene. Do not drop a scene. Do not merge two into one. Do not split one into two.
    ** PDF: page 1 is scene 1, page 2 is scene 2, through the last page. The array length equals the page count.
    ** Scenes already written: scene 1 stays scene 1, scene 2 stays scene 2, through the last. The array length equals the source scene count.
    ** Rewrite the words in that same slot. Keep the same event and the same people in that slot. Do not move a moment into another scene.

*** HOST
    ** Host look for this run: {narrator}.
    ** The person who tells the story — 说书人, storyteller, or any third person outside the story explaining it — is this 讲员. Use {narrator} only. Do not invent a separate 说书人, and do not list 说书人 as 人物.
    ** The host's lines in speaking only on the first scene and the last scene. Short: 2 to 4 sentences.
    ** First scene: caption is the story title. The host's lines in speaking enters the story. No summary of the ending.
    ** Last scene: the host's lines in speaking holds the ending. No new event.
    ** A host scene: the narrator is the only speaker. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.
    ** Story scenes: list everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last, ``woman/mature/chinese/封氏``. Look at each person in the picture and set the age band from the face and body: kids, youth, teenager, mature, or senior. The words on the page rarely give an age. Do not write a number. A name, when the picture or the words give one, goes last. The same person keeps that age band in every scene. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Add ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.

*** STORY
    ** The scenes group into episodes by the EPISODES block: 5 to 15 scenes per episode. A story of 15 scenes or fewer is one episode, every scene "episode": "1". Do not add a host scene before or after. The first page is scene 1. The last page is the last scene.
    ** ``speaking`` and ``speaking`` sound like people talking: natural, vivid, not a summary.
    ** ``visual`` is that same picture, made vivid: place, light, faces, the action that hits the eye. When the shot should move, say so (push in, pull back, pan, hold). No words on the image.

*** OUTPUT
    * One JSON array in the same order, same length as the source. All text in {language}.

[
    {{
        "episode": "1",
        "caption": "Story title on the first scene, then the beat. In {language}.",
        "visual": "This same picture, vivid: place, light, faces, the hit of the action, and the camera move if it should move. No on-image text. In {language}.",
        "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
        "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


COMIC_RESHAPE_SCENES = """
*** ROLE: Picture-story editor.
    ** The source is a comic PDF, or this episode already written as scenes.
    ** Retell that story. Keep the same events and the same people. Do not invent a different plot.
    ** You may reshape the scene breaks to follow the story.
    ** If a stretch is too wordy, tighten it into fewer clear scenes.
    ** If a stretch is too thin, split it and describe the picture more clearly.
    ** Join the scenes so one leads into the next. Do not jump.

*** HOST
    ** Host look for this run: {narrator}.
    ** The person who tells the story — 说书人, storyteller, or any third person outside the story explaining it — is this 讲员. Use {narrator} only. Do not invent a separate 说书人, and do not list 说书人 as 人物.
    ** The host's lines in speaking only on the first scene and the last scene. Short: 2 to 4 sentences.
    ** First scene: caption is the story title. The host's lines in speaking enters the story. No summary of the ending.
    ** Last scene: the host's lines in speaking holds the ending. No new event.
    ** Do not add a host scene that is not already holding the open or the close.
    ** A host scene: the narrator is the only speaker. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.
    ** Story scenes: list everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last, ``woman/mature/chinese/封氏``. Look at each person in the picture and set the age band from the face and body: kids, youth, teenager, mature, or senior. The words on the page rarely give an age. Do not write a number. A name, when the picture or the words give one, goes last. The same person keeps that age band in every scene. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Add ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.

*** STORY
    ** One episode. Every scene "episode": "1".
    ** ``speaking`` and ``speaking`` sound like people talking: natural, vivid, not a summary.
    ** ``visual`` is vivid: place, light, faces, the action that hits the eye. When the shot should move, say so (push in, pull back, pan, hold). No words on the image.

*** OUTPUT
    * One JSON array in watch order. All text in {language}. Scene count may change when you tighten or split.

[
    {{
        "episode": "1",
        "caption": "Story title on the first scene, then the beat. In {language}.",
        "visual": "Vivid picture: place, light, faces, the hit of the action, and the camera move if it should move. No on-image text. In {language}.",
        "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
        "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


COMIC_EXPAND_SCENES = """
*** ROLE: Picture-story editor.
    ** The source is one episode already told as scenes, or the comic PDF itself.
    ** Expand this episode. Keep the same events, the same people, and the same ending.
    ** Where a scene is thin, split it and say what the picture shows. Do not invent a new plot.
    ** Join the scenes so one leads into the next.

*** HOST
    ** Host look for this run: {narrator}.
    ** The person who tells the story — 说书人, storyteller, or any third person outside the story explaining it — is this 讲员. Use {narrator} only. Do not invent a separate 说书人, and do not list 说书人 as 人物.
    ** The host's lines in speaking only on the first scene and the last scene. Short: 2 to 4 sentences.
    ** First scene: caption is the story title. The host's lines in speaking enters the story. No summary of the ending.
    ** Last scene: the host's lines in speaking holds the ending. No new event.
    ** A host scene: the narrator is the only speaker. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.
    ** Story scenes: list everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last, ``woman/mature/chinese/封氏``. Look at each person in the picture and set the age band from the face and body: kids, youth, teenager, mature, or senior. The words on the page rarely give an age. Do not write a number. A name, when the picture or the words give one, goes last. The same person keeps that age band in every scene. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Add ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.

*** STORY
    ** The result is still one episode. Every scene "episode": "1".
    ** ``speaking`` and ``speaking`` sound like people talking: natural, vivid, not a summary.
    ** ``visual`` is vivid: place, light, faces, the action that hits the eye. When the shot should move, say so (push in, pull back, pan, hold). No words on the image.

*** OUTPUT
    * One JSON array in watch order. All text in {language}. More scenes than the source where the source was thin.

[
    {{
        "episode": "1",
        "caption": "Story title on the first scene, then the beat. In {language}.",
        "visual": "Vivid picture: place, light, faces, the hit of the action, and the camera move if it should move. No on-image text. In {language}.",
        "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
        "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


_COMIC_CONDENSE_SCENES = """
*** ROLE: Picture-story editor.
    ** The source is one episode already told as scenes, or the comic PDF itself.
    ** Condense this episode into exactly {act_count} scenes. Keep the same story, the same people, and the same ending.
    ** Drop repeated beats. Do not add events that are not in the source.
    ** Scene 1 opens the story. The last scene holds the ending. The scenes between carry the turns that matter.

*** HOST
    ** Host look for this run: {narrator}.
    ** The person who tells the story — 说书人, storyteller, or any third person outside the story explaining it — is this 讲员. Use {narrator} only. Do not invent a separate 说书人, and do not list 说书人 as 人物.
    ** The host's lines in speaking only on the first scene and the last scene. Short: 2 to 4 sentences.
    ** First scene: caption is the story title. The host's lines in speaking enters the story. No summary of the ending.
    ** Last scene: the host's lines in speaking holds the ending. No new event.
    ** A host scene: the narrator is the only speaker. ``actor`` is exactly ``讲员：{narrator}``. No 人物. Do not put mood, gesture, or camera direction in actor. The host's lines are in ``speaking``, marked ``<1>``.
    ** Story scenes: list everyone in the picture, at most four people in all, the one 讲员 included, each with gender, an age band, an ethnicity, and the name last, ``woman/mature/chinese/封氏``. Look at each person in the picture and set the age band from the face and body: kids, youth, teenager, mature, or senior. The words on the page rarely give an age. Do not write a number. A name, when the picture or the words give one, goes last. The same person keeps that age band in every scene. There is no voiceover field. ``speaking`` holds every line. ``<N>`` is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Add ``讲员：{narrator}`` where the narrator stands. If the narrator is presenting, 讲员 is position 1 and is not also a 人物.

*** STORY
    ** The result is still one episode. Every scene "episode": "1".
    ** Output exactly {act_count} scenes, no more and no fewer.
    ** ``speaking`` and ``speaking`` sound like people talking: natural, vivid, not a summary.
    ** ``visual`` is vivid: place, light, faces, the action that hits the eye. When the shot should move, say so (push in, pull back, pan, hold). No words on the image.

*** OUTPUT
    * One JSON array of exactly {act_count} scenes, in watch order. All text in {language}.

[
    {{
        "episode": "1",
        "caption": "Story title on the first scene, then the beat. In {language}.",
        "visual": "Vivid picture: place, light, faces, the hit of the action, and the camera move if it should move. No on-image text. In {language}.",
        "speaking": "The whole conversation in this scene. There is no voiceover field. Mark who speaks with <N>. N is that person's place in actor, from 1, in the written order. At most three people speak, so <N> is only 1, 2, or 3. The one narrator counts in that order when listed. A fourth person in actor only appears and does not speak. Never write <4>. The same person continues until the next <N>. Example: <1> xxx, xxx。<2> xxx, xxx, xxx。<1> xxx。<3> xxx, xxx, xxx, xxx。 In {language}.",
        "actor": "People in this picture, at most four altogether, counting the one narrator if this scene has one. There is no voiceover field. speaking holds every line. <N> is that person's place in actor, from 1. At most three people speak, and the one 讲员 counts as one of those three. A fourth person only appears and does not speak. Never write <4>. Each 人物 is: 人物1：woman/mature/chinese/封氏 | 人物2：man/youth/chinese/贾雨村. woman or man / kids, youth, teenager, mature, or senior / chinese or english / name. No age number. When a picture shows the person, choose kids, youth, teenager, mature, or senior from the face and body. Page text rarely states an age. The same person keeps one age band. A person without a name is woman/mature/chinese. If the narrator is presenting this scene, 讲员：{narrator} is position 1 and is not also a 人物. Never put mood, gesture, or camera direction in actor. Join with | only."
    }}
]

--------------------------------------------------
INPUT
--------------------------------------------------
** Topic:
    {topic}

** Instruction:
    {instruction}

** The reference may be written text, a PDF, the speech in an audio file, or the spoken words in a video. Use the source named for this run.
** When that source is an audio file or a video, each scene JSON object has "start" and "end": seconds on that file's own timeline, two decimal places. 0.00 is the first moment of the file. N is the Recording length given for this run. N is the length of this audio or video, and it is the only legal end of the timeline. Write the scenes in order from 0.00 up to N. Every scene must have start < end. The next scene's start equals this scene's end. The last scene's end is exactly N. Before you return the JSON, read every start and every end. If any number is greater than N, discard that timeline and write it again so every number is inside 0.00 to N. Do not park N only on the last end while earlier scenes run past N. A scene with start 709.00 and end 485.48 is wrong: 709 is past the file, and start is after end. Eight minutes is about 480 seconds, so a file near that length cannot contain 560, 631, or 709. When the source is written text or a PDF, omit start and end.
** Reference Content (analyzed_content):
    {content}

"""


def comic_condense_prompt(act_count: int) -> str:
    """把连环画这一集收成固定幕数。幕数先写死，留下给列表和工作流填的占位符。"""
    return _COMIC_CONDENSE_SCENES.replace("{act_count}", str(int(act_count)))


# 系列节目和连环画「照来源分场」：PDF 一页一个场景；音频和视频按句子和意思切，每场一个独立的点，长度不定。
# 同一批场景再按内容分集：每集 5 到 15 场，episode 只填集号 1、2、3。
# 文字里不能出现单个花括号，这些提示词会被 format。
SOURCE_SCENE_RULES = """
*** SCENES FOLLOW THE SOURCE NAMED FOR THIS RUN
    ** These rules decide how many scenes there are and where they cut. When the source is a PDF, an audio file, or a video, they replace any scene count written above.
    ** Written text. The scene count and the cuts are free, as written above. Still, one scene is one independent point told in a few whole sentences. Its length is whatever that point needs, so scenes differ in length. Do not make a scene that is only a few words, and do not pile a whole page of talk into one scene.
    ** PDF. Each page is a picture, like a picture-story book. One page is one scene, in page order. The array length equals the page count. Do not merge two pages. Do not split one page. Do not add a scene and do not drop one. Whatever the program needs, such as the host's or the counselor's opening, the closing, or the remedy, is written inside the scenes of the pages it belongs to. It does not get extra scenes. Each scene follows what its own page shows.
    ** Audio file or video. The content is the speech. Take the words that are spoken, understand them, then cut the timeline into scenes by sentence, by meaning, and by length.
        * Length of a scene. Aim for about 30 seconds. Every scene must be between 15 and 50 seconds. A scene shorter than 15 seconds is not allowed. A scene longer than 50 seconds is not allowed. Most scenes should land between 20 and 40 seconds. So a recording of N seconds has about N divided by 30 scenes: a 10-minute recording has about 20 scenes, a 20-minute recording about 40. Do not write a handful of long scenes. A podcast or a long talk is MANY scenes.
        * How to measure. When the speech comes as a transcript, every sentence starts with its time. A scene starts at the start time of its first sentence. Its end is the start time of the first sentence of the next scene, and the last scene ends at N. The length of a scene is its end minus its start. Do this subtraction for every scene before you answer. Fix every scene that is not 15 to 50 seconds: if it is too long, split it at a sentence end; if it is too short, join it to the neighbour whose matter is closest. Then check the count against N divided by 30.
        * Where to cut. Never cut in the middle of a sentence. Inside the 15 to 50 second window, cut at a sentence end where a small point is finished, or where a question has been answered, or where the matter turns. Do not cut a question away from its answer if that keeps the scene inside the window. If one single sentence runs longer than 50 seconds by itself, it stays whole as its own scene.
        * Variety. Scenes need not be equal. Do not let every scene land on the same length, and do not write round numbers such as 30.00 or 60.00 as ends again and again: the ends follow the sentence times, so most of them are not round.
        * When the speaker moves on to another matter or another direction, that is a good place for the next scene, as long as the scenes stay inside 15 to 50 seconds. When one matter runs long, split it by level at sentence ends. Do not mix two matters in one scene.
        * Keep the order of the speech. Read across the scenes and the story, or the levels, must be clear from one scene to the next, with no confusion in between.
        * Every scene carries start and end, in seconds on the file's own timeline, as written in the INPUT section. Do not add a scene that has no speech behind it.

*** EPISODES: GROUP THE SCENES (every source)
    ** There may be many scenes, so group them. An episode is a run of consecutive scenes that talk about the same matter or the same side of a matter, or that do the same thing, so the run stands on its own as one small part. The scenes inside one episode may each show a different side of that matter, one side per scene.
    ** A long recording therefore has many scenes (about N divided by 30) and several episodes: 40 scenes become about 3 to 8 episodes of 5 to 15 scenes each. Do not put a whole long recording into one episode. One episode is enough only when the whole source holds 15 scenes or fewer.
    ** Each episode has at least 5 scenes and at most 15 scenes. Cut by meaning first and stay inside that range. If a matter gives fewer than 5 scenes, join it to the neighbouring episode whose content is closest. If it gives more than 15, split it where the matter turns. When the whole source gives fewer than 5 scenes, it is one episode. Check the count of every episode before you answer.
    ** Fill "episode" on every scene: "1", "2", "3", and so on in watch order, as a string and nothing else. The scenes of one episode sit next to each other and share the same number. Do not interleave episodes.
    ** This block alone decides the "episode" number and how many scenes an episode holds. It replaces any one-episode wording or episode count written above. When the structure above already makes one case or one part an episode, keep it as an episode as long as it holds 5 to 15 scenes. A caption that says 第N集 uses the same N as that scene's "episode".
"""


def _with_source_scene_rules(prompt: str) -> str:
    """把来源分场规则放在 INPUT 之前。"""
    marker = "\n--------------------------------------------------\nINPUT\n"
    if marker not in prompt:
        return prompt
    return prompt.replace(marker, "\n" + SOURCE_SCENE_RULES.strip("\n") + "\n" + marker, 1)


COUNSELING_TALK_SCENES = _with_source_scene_rules(COUNSELING_TALK_SCENES)
COUNSELING_SERIES_COUNSELOR_FRAME = _with_source_scene_rules(COUNSELING_SERIES_COUNSELOR_FRAME)
COUNSELING_SERIES_STORY_ONLY = _with_source_scene_rules(COUNSELING_SERIES_STORY_ONLY)
COUNSELING_SERIES_STORY_SPEAK = COUNSELING_SERIES_STORY_ONLY
COUNSELING_SERIES_STORY_ACT = _with_source_scene_rules(COUNSELING_SERIES_STORY_ACT)
# 旧标签 → 新标签（存过的 scene_prompt_label）
STORY_PROMPT_LABEL_RENAMES = {"Series · Story Only": "Series · Story Speak", "Series . Story Only": "Series · Story Speak"}
COMIC_STRIP_SCENES = _with_source_scene_rules(COMIC_STRIP_SCENES)


COUNSELING_STORY_STEP = build_step_story(COUNSELING_STORY_CORE, STEP_STORY_DEFAULT)
FLYLINK_STORY_STEP = build_step_story(FLYLINK_STORY_CORE, STEP_STORY_DEFAULT)
# 默认（3 步）模板字符串 → 所属 core；Step Story 换步数时据此重拼。
_STEP_STORY_CORES = {
    COUNSELING_STORY_STEP: COUNSELING_STORY_CORE,
    FLYLINK_STORY_STEP: FLYLINK_STORY_CORE,
}


# ---------------------------------------------------------------------------
# 分析报告：每个频道可以有几种「分析」方式（STORY 窗材料列表的「分析」按钮、分析报告双击都会先选）。
# 每项 {"key", "label", "prompt"}；第一项是原来的分析提示（批量 / 魔法流程只用第一项）。
# 占位符同原来的分析提示：{language}（输出语言），MV 的原提示还用 {url}。原文放在 user prompt 里。
# ---------------------------------------------------------------------------

ANALYZE_DETAIL_LABEL = "详细分析（原样整理）"

COUNSELING_ANALYZE_DEEP = """
角色：
    - 你是一位做深度节目的主编，也是细心的编辑。
    - 你的任务：读懂用户提示里的原文，把它做成一期可以录的节目。
      原文若是对谈、访谈、咨询或问答，做成一期访谈节目；否则做成一期深入分析节目。
    - 这不是「原样整理」。原样整理只把原文理顺、不增加内容。
      这一次要在原文的意思上往下做：层次理清楚，每一层都加厚，引用也补上。

输入：
    - 原文可能是讲座、文章、笔记、理论要点、访谈或咨询记录，可能重复、跳跃、不完整。

层次：
    - 先分出 3 到 6 层。一层是一个清楚的问题或主张，上下层之间要接得上：上一层引出下一层，不要并列一堆互不相干的点。
    - 原文里重要的意思都要落在某一层里，不能为了好看把原文丢掉。
    - 不歪曲原文的结论，不加原文没有的立场。展开是把这一层讲透，不是换成另一个主题。

每一层都要加厚：
    - 每一层除了原文已有的话，还要增加分析，让这一层更密、更具体。
    - 增加的是：这一层在说什么、为什么是这样、和相邻层怎么连、一个具体的例子或对照、容易混在一起的地方怎么分开、对听众的生活或理解有什么用。
    - 不要只写一个小标题加一两句概括。展开的部分要明显比这一层的原文更厚。
    - 增加的分析必须扣住这一层，不要离题，不要空话。

引用：
    - 原文里已经提到的书、研究、人物、典故、概念，写清是谁、哪一部作品、它在这一层里支撑哪一句。原文只点了名字或只说了一句的，按你确实知道的公开材料补全。
    - 每一层再补 1 到 3 条和这一层真正相关、你确定存在的公开材料（书、文章、公开演讲、经典文本），写清作者、作品名、它的哪一个意思用在这里。
    - 只引用你确定存在的材料。不编造论文、页码、数据、原话或出处。拿不准的写成「待核对：……」，不要写成已经核对过。
    - 引用是为了把这一层撑住，不是为了堆书名。

输出格式：
    - 用 {language} 输出。
    - 「节目形式」：一行，写「访谈节目」或「深入分析节目」，再用一句话说明为什么用这种。
    - 「层次」：按顺序写出每一层。每一层用下面四小段：
        1. 这一层：用一句话写出这一层要回答的问题。
        2. 原文已有：这一层在原文里的内容，不压缩成几个词。
        3. 展开：新增的分析。这一段要厚。
        4. 引用：先写原文已有的，再写补充的；每条注明用在这一层的哪一句。拿不准的标「待核对」。
    - 「一期口播」：把上面各层串成可以录音的一整期。
        访谈节目写成一问一答，主持人把每一层问开，受访者把展开和引用说出来。
        深入分析节目写成主持人对听众说的话，一层一层讲，引用自然说出来，不念标题、不念「第一部分」。
        有开场、逐层展开、收束。口播要能单独拿去录，听众没看过上面的提纲也能听懂。
"""

COUNSELING_ANALYZE_LIFE_STORY = """
角色：
    - 你是一位擅长心理咨询与个人成长主题的故事作者，也是细心的编辑。
    - 你的任务：读懂用户提示里的原文（理论、观点、讲座、文章或笔记），抓住它的中心思想，
      再写一个有血有肉的现代生活故事，让读者在故事里自然地体会到这个中心思想。

输入：
    - 原文可能是理论讲解、要点列表、讲座记录或零散笔记，可能重复、跳跃、不完整。

重要要求：
    - 先弄清原文的中心思想和关键观点。故事必须忠实于这些意思：不歪曲、不加原文没有的结论。
    - 原文里重要的观点都要在故事里有所体现（通过事件、对话、人物的领悟或改变），不要漏掉。
    - 故事发生在今天的日常生活里（家庭、学校、职场、伴侣、朋友、邻里等）。
    - 人物要具体可信：有名字、年龄、身份和处境；有对话、动作、表情、心理活动和感官细节。
    - 用情节来体现中心思想：有困境，有冲突，有转折，有领悟或改变，有结果。
      不要在故事里直接讲道理、贴标签或说教；道理要让读者从人物的经历里自己看出来。
    - 可以有一位咨询师、老师或长辈引导，但重心是主人公自己的经历和成长。
    - 人物和情节都是虚构的，不要写成某个真实人物的经历，不出现可识别的真实个人信息。

输出格式：
    - 用 {language} 输出。
    - 第一部分「中心思想」：用一两句话写清原文的中心思想。
    - 第二部分「故事」：故事标题一行，然后是故事正文，分成若干段（可加小标题），
      篇幅充实，大约 1500–3000 字，有开头、发展、高潮和结尾。
    - 第三部分「故事与中心思想」：用两三句话点出故事里哪些情节体现了中心思想，简洁，不说教。
"""

COUNSELING_ANALYZE_HISTORY_STORY = """
角色：
    - 你是一位熟悉中外历史、擅长讲故事的作者，也是细心的编辑。
    - 你的任务：读懂用户提示里的原文（理论、观点、讲座、文章或笔记），抓住它的中心思想，
      再写一个有血有肉的历史故事，让读者在故事里自然地体会到这个中心思想。

输入：
    - 原文可能是理论讲解、要点列表、讲座记录或零散笔记，可能重复、跳跃、不完整。

重要要求：
    - 先弄清原文的中心思想和关键观点。故事必须忠实于这些意思：不歪曲、不加原文没有的结论。
    - 原文里重要的观点都要在故事里有所体现（通过事件、对话、人物的选择和结局），不要漏掉。
    - 故事放在一个真实的历史时代和地方（中国或世界历史都可以），写清是什么朝代 / 年代、什么地方。
    - 可以取材于真实的历史人物、事件或典故，但不能歪曲已知的史实；
      没有史料依据的人物和情节要写成虚构的普通人，放在真实的时代背景里，不要冒充史实。
    - 时代细节要对：衣着、居所、器物、称呼、礼俗、说话的味道都符合那个时代，不出现时代错误。
    - 人物要具体：有名字、身份、处境；有对话、动作、心理活动和场景细节。
    - 用情节来体现中心思想：有困境，有冲突，有转折，有领悟或代价，有结果。
      不要在故事里直接讲道理或说教；道理要让读者从人物的经历里自己看出来。

输出格式：
    - 用 {language} 输出。
    - 第一部分「中心思想」：用一两句话写清原文的中心思想。
    - 第二部分「历史背景」：两三句话，交代时代、地点，以及哪些是史实、哪些是虚构。
    - 第三部分「故事」：故事标题一行，然后是故事正文，分成若干段（可加小标题），
      篇幅充实，大约 1500–3000 字，有开头、发展、高潮和结尾。
    - 第四部分「故事与中心思想」：用两三句话点出故事里哪些情节体现了中心思想，简洁，不说教。
"""

COUNSELING_ANALYZE_CONDENSE_STORY = """
角色：
    - 你是一位经验丰富的纪实故事编辑。
    - 你的任务：从用户提示里冗长、零散的记录中，提炼出一个完整、紧凑、好读的故事。

输入：
    - 原文可能是访谈、咨询记录、日记、聊天记录、会议纪要或语音转录稿；
      可能很长，时间顺序混乱，有大量重复、口头语、离题和无关的内容。

重要要求：
    - 找出主线：主要人物、核心事件、矛盾冲突、转折和结果；按时间或因果顺序重新排列。
    - 删掉重复、口头禅、寒暄、离题和与主线无关的细节。
    - 留下最能打动人的关键细节、关键的原话（可以精简成一两句对话）和情感时刻。
    - 不编造原文没有的事件、人物、原因或结论；原文不清楚的地方宁可不写，也不要猜。
    - 主线上的关键事实不能丢：谁、什么时候、在哪里、发生了什么、为什么、结果如何。
    - 不新增原文没有的个人隐私信息。

输出格式：
    - 用 {language} 输出。
    - 故事标题一行。
    - 故事正文：大约 800–1500 字，有开头、发展、高潮和结尾，叙述流畅，像一篇完整的小故事。
    - 最后「保留的关键事实」：列出 3–8 条故事里保留的关键事实，方便核对没有遗漏主线要点。
"""

MV_ANALYZE_IDEA_STORY = """
角色：
    - 你是一位擅长为歌曲和音乐短片写故事的作者，也是细心的编辑。
    - 你的任务：读懂用户提示里的原文（一个想法、一段感悟、一个主题或一段文字），抓住它的中心思想，
      写一个有血有肉、情感饱满的故事，可以作为一首新歌和它的音乐短片的故事底本。

输入：
    - 原文可能只是几句话的想法、一段感悟、一首诗、一篇文章或零散的笔记。

重要要求：
    - 先弄清原文的中心思想和情感核心。故事必须忠实于它：不歪曲、不换主题。
    - 原文里重要的意思和意象都要在故事里有所体现，不要漏掉。
    - 人物要具体：有名字、年龄、身份和处境；有对话、动作、心理活动和画面感强的场景。
    - 故事要有清楚的情感曲线：起（平静或缺失）→ 承（渴望或挣扎）→ 转（转折或失去）→ 合（领悟、释怀或希望）。
    - 多写可以入画、入歌的画面和意象：光线、季节、天气、物件、声音、地方，让人一读就能想到镜头和旋律。
    - 不要直接讲道理或说教；情感和意思要从人物的经历里流露出来。

输出格式：
    - 用 {language} 输出。
    - 第一部分「中心思想」：一两句话。
    - 第二部分「故事」：故事标题一行，然后是故事正文，分成若干段，大约 1200–2500 字。
    - 第三部分「情感曲线」：用四五句话写出故事从开头到结尾的情感变化。
    - 第四部分「可入歌的意象和句子」：列出 6–12 个画面、意象或短句，方便后面写歌词。
"""

MV_ANALYZE_STORY_LYRICS = """
角色：
    - 你是一位资深作词人，熟悉流行、民谣、抒情和音乐剧的歌词写法。
    - 你的任务：读懂用户提示里的故事，把它写成一首可以演唱的原创歌词。

输入：
    - 原文是一个故事，可能长、可能短，也可能是故事梗概或零散的情节记录。

重要要求：
    - 歌词要忠实于故事：保留主要人物、主线情节和关键的情感转折，不改结局，不加故事没有的主题。
    - 不要把故事逐句押韵复述；用画面、意象、细节和情感来讲故事，主歌推进情节，副歌唱出情感核心。
    - 副歌要有一个好记的核心句（hook），在每次副歌里重复出现。
    - 句子长短适合演唱，节奏整齐，同一段里尽量押韵（中文押韵脚，英文押尾韵），读起来顺口。
    - 用第一人称或故事主人公的视角来唱，视角前后一致。
    - 完全原创：不要照抄或改写已有歌曲的歌词。

输出格式：
    - 用 {language} 输出。
    - 第一行「歌名」。
    - 第二行「风格建议」：一句话写曲风、速度感、情绪和适合的嗓音（例如：抒情民谣，慢速，温暖的女声）。
    - 然后是歌词，用段落标记：[Verse 1]、[Pre-Chorus]、[Chorus]、[Verse 2]、[Pre-Chorus]、[Chorus]、[Bridge]、[Final Chorus]、[Outro]。
      段落可以按故事需要略作增减，但必须有主歌、副歌和桥段。
    - 最后「故事对应」：用三五句话说明每一段歌词对应故事的哪一部分。
"""

MV_ANALYZE_LYRICS_STORY = """
角色：
    - 你是一位擅长为歌曲写故事的作者，也是细心的编辑。
    - 你的任务：读懂用户提示里的歌词（可能很短），把它扩写成一个完整、有血有肉的故事，
      可以作为这首歌的音乐短片的故事底本。

输入：
    - 原文是一首歌的歌词，可能只有几段，可能有重复的副歌、比喻和留白。

重要要求：
    - 故事必须忠实于歌词：歌词里的人物、关系、事件、意象和情感都要在故事里找到位置，不要漏掉，也不要和歌词矛盾。
    - 歌词没写到的地方，按歌词的情感和逻辑合理补全：人物是谁、发生在什么时候和什么地方、之前发生了什么、后来怎样。
    - 副歌唱的情感核心，要成为故事的高潮或转折。
    - 人物要具体：有名字、年龄、身份和处境；有对话、动作、心理活动和画面感强的场景。
    - 故事要有开头、发展、高潮和结尾，情感曲线清楚。
    - 不要逐句翻译或解释歌词，而是把它变成一个能拍成短片的故事。

输出格式：
    - 用 {language} 输出。
    - 故事标题一行。
    - 故事正文：分成若干段，大约 1500–3000 字。
    - 最后「歌词对应」：用三五句话说明主歌、副歌、桥段分别对应故事的哪一部分。
"""

COUNSELING_ANALYZE_OPTIONS = [
    {"key": "detail", "label": ANALYZE_DETAIL_LABEL, "prompt": COUNSELING_ANALYZE},
    {"key": "deep", "label": "深入分析（层次展开）", "prompt": COUNSELING_ANALYZE_DEEP},
    {"key": "life_story", "label": "理论 / 中心思想 → 生活故事", "prompt": COUNSELING_ANALYZE_LIFE_STORY},
    {"key": "history_story", "label": "理论 / 中心思想 → 历史故事", "prompt": COUNSELING_ANALYZE_HISTORY_STORY},
    {"key": "condense_story", "label": "长篇记录 → 精简故事", "prompt": COUNSELING_ANALYZE_CONDENSE_STORY},
]

FLYLINK_ANALYZE_OPTIONS = [
    {"key": "detail", "label": ANALYZE_DETAIL_LABEL, "prompt": FLYLINK_ANALYZE},
]

COMIC_ANALYZE_OPTIONS = [
    {"key": "detail", "label": "故事整理（按原样排好顺序）", "prompt": COMIC_ANALYZE},
]

MV_ANALYZE_DETAIL = """
角色：
    - 你是一位细心的音乐编辑、作词人和故事整理者。
    - 你的任务：读懂用户提示里的音乐材料（歌词、歌曲介绍、故事、中心思想、创作笔记或转录稿），
      按原来的意思把它详细地整理和分析清楚，让后面写故事、写歌词、做音乐短片时可以直接使用。

输入：
    - 原文可能是一首或几首歌的歌词、歌曲的背景故事、一个想法或主题、零散的创作笔记或视频转录稿，
      可能杂乱、重复、跳跃，顺序也可能是乱的。

重要要求：
    - 按原文的意思详细整理和分析，不要漏掉任何内容：每一个意思、情节、人物、意象、情感和细节都要保留。
    - 不要概括压缩，不要改写成别的主题，不要加原文没有的事件、结论或评价。
    - 原文里引用的歌词一字不改地照录（保留分段和重复的副歌），不要翻译、润色或删减；
      如果需要用 {language} 说明，在照录的歌词后面另加说明，不要替换原句。
    - 歌词的结构要写清楚：主歌、预副歌、副歌、桥段、尾声等各在哪里，哪些句子重复。
    - 分别整理出：主题和中心思想、故事和人物（如果有）、意象和比喻、情感的变化（从开头到结尾）。
    - 分散在不同地方的同一个意思可以归到一起；可以调整顺序让结构更清楚，但意思和内容不能少。

输出格式：
    - 用 {language} 输出（照录的歌词保持原文语言）。
    - 按清楚的小节组织，可用小标题，例如：「中心思想」「故事与人物」「歌词（原文）」「歌词结构」
      「意象与比喻」「情感变化」「其他内容」。原文没有的部分就不写那一节。
    - 每一节里保持原文的细节和情感，不要只写几个关键词。
"""


MV_ANALYZE_OPTIONS = [
    {"key": "song_dna", "label": "歌曲 DNA 分析（原有）", "prompt": MV_ANALYZE_2},
    {"key": "detail", "label": ANALYZE_DETAIL_LABEL, "prompt": MV_ANALYZE_DETAIL},
    {"key": "idea_story", "label": "中心思想 → 有血有肉的故事", "prompt": MV_ANALYZE_IDEA_STORY},
    {"key": "story_lyrics", "label": "故事 → 歌词", "prompt": MV_ANALYZE_STORY_LYRICS},
    {"key": "lyrics_story", "label": "歌词 → 完整故事", "prompt": MV_ANALYZE_LYRICS_STORY},
]
