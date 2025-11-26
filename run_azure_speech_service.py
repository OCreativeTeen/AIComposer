from utility.azure_speech_service import AzureSpeechService
import os
import config


# Example usage
def main():
    # Configuration - REPLACE THESE WITH YOUR ACTUAL VALUES
    subscription_key = ""  # Replace with your actual key
    region = "eastus"  # Replace with your actual region
    
    # Check if placeholder values are still being used
    if subscription_key == "YOUR_AZURE_SPEECH_KEY":
        print("❌ Please replace YOUR_AZURE_SPEECH_KEY with your actual Azure Speech Service key")
        return
    
    if region == "your_region":
        print("❌ Please replace 'your_region' with your actual Azure region (e.g., 'eastus')")
        return
    
    # Initialize the service
    tts_service = AzureSpeechService("program", subscription_key, region)
    
    print("=== Testing Azure Speech Service Setup ===")
    
    speach_name = "strange_zh"
    speaches = [
        {
            "name": "strange_zh_m",
            "voice": "zh-CN-Yunfan:DragonHDLatestNeural",
            "mood": "cheerful",
            "content": "大家好，我是 佳伟, 欢迎来到我们的 聊斋新语 节目",
            "picture": "a Chinese men (45 years old) & women (30 years old) (dressing chinese traditionally), host of the podcast show called ('聊斋新话')； background showing Chinese architecture & culture"
        },
        {
            "name": "strange_zh_f",
            "voice": "zh-CN-XiaorouNeural",
            "mood": "cheerful",
            "content": "我是 莹莹, 让我们一起来说说新的聊斋故事吧？记得点赞关注哦！",
            "picture": "a Chinese men (45 years old) & women (30 years old) (dressing chinese traditionally), host of the podcast show called ('聊斋新话')； background showing Chinese architecture & culture"
        }
    ]

    speaches2 = [
        {
            "name": "spirit_zh_m",
            "voice": "zh-CN-Yunxiao:DragonHDFlashLatestNeural",
            "mood": "cheerful",
            "content": "大家好，我是 大勇, 欢迎来到我们的 Spirit Tales 节目",
            "picture": "a pair of chinese men & women (around 30 years old), host of the travel show called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "spirit_zh_f",
            "voice": "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural",
            "mood": "cheerful",
            "content": "我是 晓秋, 准备好，一起同行一段心意更新的道路了吗？记得点赞关注哦！",
            "picture": "a pair of chinese men & women (around 30 years old), host of the travel podcast (in studio) called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_zh_m",
            "voice": "zh-CN-Yunxiao:DragonHDFlashLatestNeural",
            "mood": "cheerful",
            "content": "大家好，我是 大鹏, 欢迎来到我们的 故事里的旅行 节目",
            "picture": "a pair of chinese men & women (around 30 years old), host of the travel show called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_zh_f",
            "voice": "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural",
            "mood": "cheerful",
            "content": "我是 晓涵, 准备好，跟我们一起探索世界的故事了吗？记得点赞关注哦！",
            "picture": "a pair of chinese men & women (around 30 years old), host of the travel podcast (in studio) called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_en_m",
            "voice": "en-US-Andrew3:DragonHDLatestNeural",  
            "mood": "cheerful",
            "content": "Welcome to WanderTales! I am Andrew",
            "picture": "a pair of Canadian men & women (around 30 years old), host of the travel show called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_en_f",
            "voice": "en-US-Emma2:DragonHDLatestNeural",
            "mood": "cheerful",
            "content": "I am Emma. Ready to explore the world with us? Don't forget to like and subscribe!",
            "picture": "a pair of Canadian men & women (around 30 years old), host of the travel podcast (in studio) called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_jp_m",
            "voice": "ja-JP-Masaru:DragonHDLatestNeural",
            "mood": "cheerful",
            "content": "こんにちは、しょうた です！WanderTalesへようこそ。", #**翔太（
            "picture": "a pair of Japanese men & women (around 30 years old, dressed in traditional Japanese kimono), host of the travel show called WanderTales ('Stories in Travel'); "
        },
        {
            "name": "travel_jp_f",
            "voice": "ja-JP-Nanami:DragonHDLatestNeural",
            "mood": "cheerful",
            "content": "みさき です！さあ、一緒に世界の物語を旅しましょう！チャンネル登録といいね、お願いします！",
            "picture": "a pair of Japanese men & women (around 30 years old, dressed in traditional Japanese kimono), host of the travel podcast (in studio) called WanderTales"
        }
    ]
    # Test basic functionality

    audio_path_list = []

    for speach in speaches:
        # Test SSML generation and validation
        ssml = tts_service.create_ssml(speach["content"], speach["voice"], speach["mood"])
        print(f"Generated SSML: {ssml}")
        
        if tts_service.validate_ssml(ssml):
            print("✓ SSML validation passed")
        else:
            print("✗ SSML validation failed")
            return
        
        output_file = os.path.abspath(f"{config.BASE_MEDIA_PATH}/program/{speach['name']}.mp3")
        tts_service.text_to_speech(ssml, output_file)
        audio_path_list.append(output_file)

    tts_service.ffmpeg_processor.concat_audios(f"{config.BASE_MEDIA_PATH}/program/{speach_name}.wav", audio_path_list)
    print(f"Output path: {speach_name}.aac")


if __name__ == "__main__":
    main()