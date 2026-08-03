import os
import re
import telebot
import requests

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Регулярное выражение для поиска TikTok, Instagram Reels и YouTube Shorts
URL_PATTERN = re.compile(
    r'(https?://\S*(?:tiktok\.com|instagram\.com/reel|youtube\.com/shorts)\S*)', 
    re.IGNORECASE
)

print("Бот со всеядной поддержкой API запущен!")

@bot.message_handler(func=lambda message: message.text and URL_PATTERN.search(message.text))
def handle_all_videos(message):
    match = URL_PATTERN.search(message.text)
    url = match.group(1)
    
    # Включаем статус отправки видео в чате
    bot.send_chat_action(message.chat.id, 'upload_video')
    
    try:
        # Используем альтернативное продвинутое API (парсит TT, Reels, Shorts)
        # Оно мгновенно возвращает прямую ссылку на готовый MP4-файл
        api_url = f"https://v02.ru{url}" 
        response = requests.get(api_url, timeout=12).json()
        
        if response.get("status") == "success" and "video_url" in response:
            video_url = response["video_url"]
            title = response.get("title", "Video")
            
            # Отправляем видео в чат методом стриминга по URL
            bot.send_video(
                chat_id=message.chat.id, 
                video=video_url, 
                reply_to_message_id=message.message_id,
                caption=f"🎬 {title[:50]}..." if title else None
            )
        else:
            # Попробуем резервный популярный шлюз, если первый промолчал
            fallback_url = f"https://lewisandclark.tech{url}"
            fallback_resp = requests.get(fallback_url, timeout=12).json()
            
            if fallback_resp.get("success") and "url" in fallback_resp:
                bot.send_video(
                    chat_id=message.chat.id, 
                    video=fallback_resp["url"], 
                    reply_to_message_id=message.message_id
                )
            else:
                print(f"Парсеры не смогли забрать видео по ссылке: {url}")
                
    except Exception as e:
        print(f"Ошибка во время запроса к API: {e}")

if __name__ == '__main__':
    bot.infinity_polling()
