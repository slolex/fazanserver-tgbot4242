import os
import re
import logging
import tempfile
import uuid

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, ContextTypes, filters

import yt_dlp

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН")

# Ограничение на размер файла, который бот может отправить (Telegram Bot API: 50 МБ)
MAX_FILE_SIZE_MB = 50

URL_PATTERN = re.compile(
    r"(https?://)?"
    r"(www\.)?"
    r"("
    r"(vm|vt|www)\.tiktok\.com|tiktok\.com|"
    r"(www\.)?instagram\.com/reel[s]?|"
    r"(www\.)?youtube\.com/shorts|"
    r"youtu\.be"
    r")"
    r"[^\s]*",
    re.IGNORECASE,
)


def extract_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if match:
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return url
    return None


async def download_video(url: str, out_dir: str) -> str | None:
    """Скачивает видео по ссылке через yt-dlp, возвращает путь к файлу или None."""
    out_template = os.path.join(out_dir, f"{uuid.uuid4()}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        "format": "mp4/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if os.path.exists(filepath):
                return filepath
    except Exception as e:
        logger.error(f"Ошибка скачивания {url}: {e}")
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return

    url = extract_url(message.text)
    if not url:
        return

    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)

    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = await download_video(url, tmp_dir)

        if not filepath:
            await message.reply_text(
                "Не получилось скачать видео 😕 "
                "Либо оно слишком большое (>50 МБ), либо ссылка недоступна."
            )
            return

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            await message.reply_text(
                f"Видео весит {file_size_mb:.1f} МБ — это больше лимита в "
                f"{MAX_FILE_SIZE_MB} МБ, которое разрешено обычным ботам Telegram."
            )
            return

        try:
            with open(filepath, "rb") as video_file:
                await message.reply_video(
                    video=video_file,
                    supports_streaming=True,
                )
        except Exception as e:
            logger.error(f"Ошибка отправки видео: {e}")
            await message.reply_text("Скачал, но не смог отправить видео в чат.")


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "ВСТАВЬ_СЮДА_ТОКЕН":
        raise RuntimeError(
            "Не задан токен бота. Установи переменную окружения BOT_TOKEN "
            "или впиши токен прямо в bot.py."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
