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

    ydl_opts = {
        'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / best',
        'outtmpl': filename,
        'merge_output_format': 'mp4',
        'max_filesize': 48 * 1024 * 1024,
        'quiet': True,
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

