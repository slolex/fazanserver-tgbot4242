import os
import re
import telebot
import requests
import traceback

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Регулярное выражение для поиска TikTok, Instagram Reels и YouTube Shorts
URL_PATTERN = re.compile(
    r'(https?://\S*(?:tiktok\.com|instagram\.com/reel|youtube\.com/shorts)\S*)', 
    re.IGNORECASE
)

print("=== БОТ ЗАПУЩЕН И ГОТОВ ВЫВОДИТЬ ПОДРОБНЫЕ ЛОГИ ===")

@bot.message_handler(func=lambda message: message.text and URL_PATTERN.search(message.text))
def handle_all_videos(message):
    match = URL_PATTERN.search(message.text)
    url = match.group(1)
    
    print(f"\n[LOG]: Обнаружена ссылка в чате {message.chat.id}: {url}")
    
    # Включаем статус отправки видео в чате
    bot.send_chat_action(message.chat.id, 'upload_video')
    print("[LOG]: Отправлен статус 'upload_video' в Telegram...")
    
    try:
        # Запрос к первому API
        api_url = f"https://v02.ru{url}" 
        print(f"[LOG]: Отправляю запрос к первому API: {api_url}")
        
        response = requests.get(api_url, timeout=12).json()
        print(f"[LOG]: Ответ от первого API: {response}")
        
        if response.get("status") == "success" and "video_url" in response:
            video_url = response["video_url"]
            title = response.get("title", "Video")
            print(f"[LOG]: Прямая ссылка на MP4 получена: {video_url}")
            print(f"[LOG]: Пытаюсь отправить видео в Telegram...")
            
            # Отправка в Telegram
            bot.send_video(
                chat_id=message.chat.id, 
                video=video_url, 
                reply_to_message_id=message.message_id,
                caption=f"🎬 {title[:50]}..." if title else None
            )
            print("[LOG]: !!! ВИДЕО УСПЕШНО ОТПРАВЛЕНО В ЧАТ !!!")
            
        else:
            print("[LOG]: Первое API не выдало ссылку. Пробую резервное API...")
            fallback_url = f"https://lewisandclark.tech{url}"
            print(f"[LOG]: Отправляю запрос к резервному API: {fallback_url}")
            
            fallback_resp = requests.get(fallback_url, timeout=12).json()
            print(f"[LOG]: Ответ от резервного API: {fallback_resp}")
            
            if fallback_resp.get("success") and "url" in fallback_resp:
                video_url = fallback_resp["url"]
                print(f"[LOG]: Резервная ссылка на MP4 получена: {video_url}")
                print(f"[LOG]: Пытаюсь отправить видео в Telegram...")
                
                bot.send_video(
                    chat_id=message.chat.id, 
                    video=video_url, 
                    reply_to_message_id=message.message_id
                )
                print("[LOG]: !!! ВИДЕО УСПЕШНО ОТПРАВЛЕНО ЧЕРЕЗ РЕЗЕРВНЫЙ ПУТЬ !!!")
            else:
                print(f"[LOG]: ОБА АПИ ОТКАЗАЛИСЬ ОБРАБАТЫВАТЬ ССЫЛКУ: {url}")
                
    except Exception as e:
        print(f"[ERROR]: Произошла критическая ошибка в коде бота!")
        print(f"[ERROR]: Описание ошибки: {e}")
        print("[ERROR]: Полный след ошибки (traceback):")
        print(traceback.format_exc())

if __name__ == '__main__':
    bot.infinity_polling()
