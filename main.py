import os
import re
import logging
import tempfile
import uuid

import httpx
import imageio_ffmpeg
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


async def download_via_tikwm(url: str, out_dir: str) -> str | None:
    """Основной способ для TikTok: сторонний сервис tikwm.com.

    ВАЖНО: без параметра hd=1 API tikwm часто вообще не отдаёт поле
    hdplay, и раньше бот брал "play" — это SD-версия без вотермарки,
    заметно хуже по битрейту. С hd=1 приходит hdplay — HD без
    вотермарки, это и есть то же качество, что видно в приложении TikTok.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://www.tikwm.com/api/",
                data={"url": url, "hd": 1},
            )
            data = resp.json().get("data", {})

            # Порядок приоритета: HD без вотермарки -> обычное без вотермарки
            video_url = data.get("hdplay") or data.get("play")
            if not video_url:
                return None

            filepath = os.path.join(out_dir, f"{uuid.uuid4()}.mp4")
            async with client.stream("GET", video_url) as video_resp:
                with open(filepath, "wb") as f:
                    async for chunk in video_resp.aiter_bytes():
                        f.write(chunk)
            return filepath
    except Exception as e:
        logger.error(f"Ошибка скачивания через tikwm: {e}")
        return None


async def download_via_ytdlp(url: str, out_dir: str) -> str | None:
    """Скачивает видео по ссылке через yt-dlp, возвращает путь к файлу или None.

    Используется как основной способ для YouTube Shorts и Instagram Reels,
    и как резервный для TikTok (если tikwm недоступен).
    """
    out_template = os.path.join(out_dir, f"{uuid.uuid4()}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        # bestvideo+bestaudio реально имеет смысл для YouTube (там видео
        # и аудио отдаются отдельными адаптивными потоками). TikTok и
        # Instagram обычно отдают уже готовый смешанный файл, так что
        # для них эта строка просто fallback'ится на "best".
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
    }

    # Куки из браузера критично важны для Instagram — без них Instagram
    # часто отдаёт урезанное качество "для гостя". Экспортируй cookies.txt
    # (формат Netscape) из залогиненного в Instagram браузера.
    cookies_file = os.environ.get("COOKIES_FILE")
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file

    proxy_url = os.environ.get("PROXY_URL")
    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    tiktok_api = os.environ.get("TIKTOK_API_HINT")  # "api" или "webpage"
    if tiktok_api:
        ydl_opts["extractor_args"] = {"tiktok": {"api_hostname": [tiktok_api]}}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if os.path.exists(filepath):
                return filepath
    except Exception as e:
        logger.error(f"Ошибка скачивания через yt-dlp {url}: {e}")

    return None


async def download_video(url: str, out_dir: str) -> str | None:
    """Выбирает способ скачивания в зависимости от площадки."""

    if "tiktok" in url.lower():
        # Для TikTok tikwm с hd=1 обычно даёт лучше результат и быстрее,
        # чем yt-dlp (у которого TikTok-экстрактор нестабилен и часто
        # получает урезанную версию). yt-dlp — запасной вариант.
        filepath = await download_via_tikwm(url, out_dir)
        if filepath:
            return filepath
        logger.info("tikwm не сработал, пробую yt-dlp для TikTok")
        return await download_via_ytdlp(url, out_dir)

    # YouTube Shorts и Instagram Reels — через yt-dlp
    return await download_via_ytdlp(url, out_dir)


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
            send_as_document = os.environ.get("SEND_AS_DOCUMENT", "false").lower() == "true"
            with open(filepath, "rb") as video_file:
                if send_as_document:
                    await message.reply_document(document=video_file)
                else:
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
