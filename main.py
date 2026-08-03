import os
import re
import logging
import tempfile
import uuid

import httpx
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
    """Резервный способ для TikTok: сторонний сервис tikwm.com,
    который сам обходит блокировки на своей стороне."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://www.tikwm.com/api/",
                data={"url": url},
            )
            data = resp.json()
            video_url = data.get("data", {}).get("play")
            if not video_url:
                return None

            filepath = os.path.join(out_dir, f"{uuid.uuid4()}.mp4")
            async with client.stream("GET", video_url) as video_resp:
                with open(filepath, "wb") as f:
                    async for chunk in video_resp.aiter_bytes():
                        f.write(chunk)
            return filepath
    except Exception as e:
        logger.error(f"Ошибка резервного скачивания через tikwm: {e}")
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

    # Куки из браузера — помогают обойти блокировку IP для TikTok.
    # Укажи путь к файлу cookies.txt (формат Netscape), экспортированному
    # расширением вроде "Get cookies.txt LOCALLY".
    cookies_file = os.environ.get("COOKIES_FILE")
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file

    # Прокси — альтернатива/дополнение к кукам, если хостинг бота
    # находится на IP датацентра, заблокированном TikTok.
    proxy_url = os.environ.get("PROXY_URL")
    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    # Переключение между внутренними API TikTok (web / mobile app API).
    # Иногда один способ заблокирован, а другой ещё работает.
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
        logger.error(f"Ошибка скачивания {url}: {e}")

    # Если это TikTok и основной способ не сработал — пробуем резервный.
    if "tiktok" in url.lower():
        logger.info("Пробую резервный способ скачивания через tikwm.com")
        return await download_via_tikwm(url, out_dir)

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
