import os
import re
import telebot
import yt_dlp

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

URL_PATTERN = re.compile(
    r'(https?://\S*(?:tiktok\.com|instagram\.com/reel|youtube\.com/shorts)\S*)', 
    re.IGNORECASE
)

print("Бот запущен на платном тарифе Bothost!")

@bot.message_handler(func=lambda message: message.text and URL_PATTERN.search(message.text))
def download_and_send_video(message):
    match = URL_PATTERN.search(message.text)
    url = match.group(1)

    bot.send_chat_action(message.chat.id, 'upload_video')
    filename = f"video_{message.message_id}.mp4"

    # Продвинутые настройки маскировки для обхода блокировок TikTok/Reels
    ydl_opts = {
        'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / best',
        'outtmpl': filename,
        'merge_output_format': 'mp4',
        'max_filesize': 48 * 1024 * 1024,
        'quiet': True,
        # --- БЛОК ОБХОДА БЛОКИРОВОК (Имитация браузера) ---
        'extractor_args': {
            'tiktok': {
                'app_info': '1234567890123456789/trill/34.0.1/340001/1180', # Имитируем оригинальное приложение TikTok
            },
            'instagram': {
                'app_id': 'web',
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        # --------------------------------------------------
    }


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        with open(filename, 'rb') as video:
            bot.reply_to(message, video)
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == '__main__':
    bot.infinity_polling()

