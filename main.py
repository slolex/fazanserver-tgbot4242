import os
import re
import telebot
import requests

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Регулярное выражение для отлова только ссылок на TikTok
TIKTOK_PATTERN = re.compile(r'(https?://\S*tiktok\.com\S*)', re.IGNORECASE)

print("Бот переключен на API TikWM и успешно запущен!")

@bot.message_handler(func=lambda message: message.text and TIKTOK_PATTERN.search(message.text))
def download_tiktok(message):
    match = TIKTOK_PATTERN.search(message.text)
    url = match.group(1)
    
    # Показываем статус загрузки в чате
    bot.send_chat_action(message.chat.id, 'upload_video')
    
    try:
        # Отправляем запрос к бесплатному API парсера
        api_url = f"https://tikwm.com{url}"
        response = requests.get(api_url, timeout=10).json()
        
        # Проверяем, успешный ли ответ от сервера
        if response.get("code") == 0:
            video_url = response["data"]["play"] # Ссылка на видео без водяного знака
            title = response["data"].get("title", "TikTok Video")
            
            # Отправляем видео напрямую по ссылке (Telegram сам его скачает и отобразит как плеер)
            bot.send_video(
                chat_id=message.chat.id, 
                video=video_url, 
                reply_to_message_id=message.message_id,
                caption=f"🎬 {title[:50]}..."
            )
        else:
            print(f"Ошибка API: {response.get('msg')}")
            
    except Exception as e:
        print(f"Ошибка при обработке: {e}")

if __name__ == '__main__':
    bot.infinity_polling()
