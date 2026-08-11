import os
import re
import asyncio
import tempfile
import logging
from pathlib import Path
from urllib.parse import urlparse

import telebot
from telebot import types
import yt_dlp

# Optional Telethon support for Telegram Stories.
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError

# =========================
# ENVIRONMENT CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Telegram API ID / HASH from my.telegram.org
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
TG_SESSION = os.getenv("TG_SESSION", "").strip()

# Public image URL used as the thumbnail/cover for downloaded audio.
# Put your GitHub raw image URL here.
COVER_URL = os.getenv(
    "COVER_URL",
    "https://raw.githubusercontent.com/fdm42143-wq/daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg",
).strip()

ARTIST = os.getenv("ARTIST", "@awe5Bot").strip()

# Optional Instagram cookies Netscape-format file.
# If supplied, yt-dlp can use it for accounts/content requiring login.
INSTAGRAM_COOKIES = os.getenv("INSTAGRAM_COOKIES", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("download-bot")

URL_RE = re.compile(r"https?://\S+", re.I)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "tg_ytdl_bot"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Limit concurrent yt-dlp jobs so Railway does not get overloaded.
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)

# =========================
# HELPERS
# =========================
def clean_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name or "media")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len] or "media"


def extract_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,!?]}>") if m else None


def is_youtube_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return "youtube.com" in host or "youtu.be" in host
    except Exception:
        return False


def is_instagram_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return "instagram.com" in host or "instagr.am" in host
    except Exception:
        return False


def is_telegram_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return "t.me" in host or "telegram.me" in host
    except Exception:
        return False


def make_ydl_opts_audio(out_dir: str):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    if INSTAGRAM_COOKIES:
        opts["cookiefile"] = INSTAGRAM_COOKIES
    return opts


def make_ydl_opts_video(out_dir: str):
    opts = {
        # Keep the result Telegram-friendly and avoid very large files.
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(out_dir, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
    }
    if INSTAGRAM_COOKIES:
        opts["cookiefile"] = INSTAGRAM_COOKIES
    return opts


def ytdlp_info(url: str, mode: str, out_dir: str):
    opts = make_ydl_opts_audio(out_dir) if mode == "audio" else make_ydl_opts_video(out_dir)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info


def find_downloaded_file(out_dir: str):
    files = [p for p in Path(out_dir).iterdir() if p.is_file()]
    if not files:
        return None
    # Prefer mp3/mp4.
    preferred = [p for p in files if p.suffix.lower() in {".mp3", ".mp4", ".m4a", ".webm", ".mkv"}]
    return max(preferred or files, key=lambda p: p.stat().st_mtime)


def download_media(url: str, mode: str):
    work = tempfile.mkdtemp(prefix="job_", dir=DOWNLOAD_DIR)
    try:
        info = ytdlp_info(url, mode, work)
        path = find_downloaded_file(work)
        if not path:
            raise RuntimeError("لم يتم العثور على الملف بعد التحميل")
        title = info.get("title") or path.stem
        duration = info.get("duration") or 0
        uploader = info.get("uploader") or info.get("channel") or ""
        thumbnail = info.get("thumbnail")
        return path, title, duration, uploader, thumbnail, work
    except Exception:
        # Keep work dir for a moment only; caller cleans it.
        raise


def format_size(n):
    try:
        n = float(n)
    except Exception:
        return "غير معروف"
    units = ["B", "KB", "MB", "GB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f} {units[i]}"


def status_text(title, size=None):
    extra = f"\n📦 الحجم: {format_size(size)}" if size else ""
    return (
        "✅ <b>تم التحميل بنجاح</b>\n\n"
        f"📌 <b>{telebot.util.escape(title)}</b>"
        f"{extra}\n\n"
        f"🤖 {telebot.util.escape(ARTIST)}"
    )


def send_audio_result(chat_id, path, title, duration=0):
    caption = status_text(title, path.stat().st_size)
    with open(path, "rb") as f:
        # Thumbnail is the fixed GitHub image when available.
        try:
            bot.send_audio(
                chat_id,
                f,
                caption=caption,
                title=title[:64],
                performer=ARTIST,
                duration=int(duration or 0),
                thumb=COVER_URL if COVER_URL.startswith("http") else None,
            )
        except Exception as e:
            log.warning("send_audio with thumb failed: %s", e)
            f.seek(0)
            bot.send_audio(
                chat_id,
                f,
                caption=caption,
                title=title[:64],
                performer=ARTIST,
                duration=int(duration or 0),
            )


def send_video_result(chat_id, path, title, duration=0, thumb_url=None):
    caption = status_text(title, path.stat().st_size)
    with open(path, "rb") as f:
        try:
            bot.send_video(
                chat_id,
                f,
                caption=caption,
                duration=int(duration or 0),
                supports_streaming=True,
            )
        except Exception as e:
            log.warning("send_video failed: %s", e)
            raise


async def process_youtube(chat_id, url, mode="audio", status_message_id=None):
    async with DOWNLOAD_SEMAPHORE:
        work = None
        try:
            if status_message_id:
                try:
                    bot.edit_message_text(
                        "⏳ <b>جاري التحميل...</b>\nقد يستغرق الأمر بعض الوقت حسب حجم الملف.",
                        chat_id,
                        status_message_id,
                    )
                except Exception:
                    pass

            path, title, duration, uploader, thumb, work = await asyncio.to_thread(
                download_media, url, mode
            )

            if mode == "audio":
                await asyncio.to_thread(send_audio_result, chat_id, path, title, duration)
            else:
                await asyncio.to_thread(send_video_result, chat_id, path, title, duration, thumb)

        except Exception as e:
            log.exception("download failed")
            msg = str(e)
            if len(msg) > 700:
                msg = msg[-700:]
            bot.send_message(
                chat_id,
                "❌ <b>فشل التحميل</b>\n\n"
                "تأكد من الرابط أو جرّب رابطًا آخر.\n"
                f"<code>{telebot.util.escape(msg)}</code>"
            )
        finally:
            if work:
                import shutil
                shutil.rmtree(work, ignore_errors=True)


# =========================
# TELEGRAM STORIES
# =========================
tg_client = None


async def init_telethon():
    global tg_client
    if not (API_ID and API_HASH and TG_SESSION):
        return None
    try:
        tg_client = TelegramClient(
            StringSession(TG_SESSION),
            API_ID,
            API_HASH,
            connection_retries=3,
            retry_delay=2,
        )
        await tg_client.connect()
        if not await tg_client.is_user_authorized():
            log.warning("TG_SESSION is not authorized")
            return None
        log.info("Telethon story session connected")
        return tg_client
    except Exception:
        log.exception("Telethon initialization failed")
        return None


async def download_telegram_story(url: str):
    """
    Supports public t.me story links when the account session has access.
    Story URLs commonly look like:
      https://t.me/<username>/s/<story_id>
      https://t.me/<username>/stories/<story_id>
    Telegram may restrict access depending on privacy and account.
    """
    if not tg_client:
        raise RuntimeError("ميزة قصص تيليجرام تحتاج TG_SESSION + API_ID + API_HASH")

    m = re.search(
        r"t\.me/([A-Za-z0-9_]+)/(?:s/|stories/)(\d+)",
        url,
        re.I,
    )
    if not m:
        raise RuntimeError("رابط ستوري تيليجرام غير معروف")

    username = m.group(1)
    story_id = int(m.group(2))

    try:
        from telethon import functions, types as tl_types
        entity = await tg_client.get_entity(username)
        result = await tg_client(functions.stories.GetStoriesByIDRequest(
            peer=entity,
            id=[story_id],
        ))
        if not result.stories:
            raise RuntimeError("الستوري غير متاح أو انتهت مدته")

        story = result.stories[0]
        media = getattr(story, "media", None)
        if not media:
            raise RuntimeError("الستوري لا يحتوي على ملف وسائط")

        out = Path(tempfile.mkdtemp(prefix="story_", dir=DOWNLOAD_DIR))
        downloaded = await tg_client.download_media(media, file=str(out / "story"))
        if not downloaded:
            raise RuntimeError("تعذر تنزيل الستوري")
        return Path(downloaded), story

    except RPCError as e:
        raise RuntimeError(f"Telegram API: {e}")


async def process_telegram_story(chat_id, url, status_message_id=None):
    try:
        if status_message_id:
            bot.edit_message_text("⏳ <b>جاري جلب ستوري تيليجرام...</b>", chat_id, status_message_id)
        path, story = await download_telegram_story(url)
        size = path.stat().st_size
        caption = (
            "✅ <b>تم تحميل الستوري</b>\n\n"
            f"📦 الحجم: {format_size(size)}\n\n"
            f"🤖 {telebot.util.escape(ARTIST)}"
        )
        with open(path, "rb") as f:
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                bot.send_photo(chat_id, f, caption=caption)
            else:
                bot.send_video(chat_id, f, caption=caption, supports_streaming=True)
        import shutil
        shutil.rmtree(path.parent, ignore_errors=True)
    except Exception as e:
        log.exception("telegram story failed")
        bot.send_message(chat_id, f"❌ <b>تعذر تحميل الستوري</b>\n{telebot.util.escape(str(e))}")


# =========================
# COMMANDS / MESSAGES
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 <b>أهلاً بك</b>\n\n"
        "🎵 أرسل اسم أغنية أو رابط YouTube لتحميل الصوت.\n"
        "🎬 أرسل رابط YouTube لتحميل الفيديو.\n"
        "📸 أرسل رابط Instagram العام لتحميل الوسائط إذا كان متاحًا.\n"
        "📱 أرسل رابط Telegram Story إذا كانت جلسة Telegram مفعلة.\n\n"
        "في المجموعات والقنوات يمكن استخدام:\n"
        "<code>/yt اسم الأغنية</code>\n"
        "<code>/yt رابط</code>\n\n"
        f"🤖 {telebot.util.escape(ARTIST)}",
    )


@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(
        message.chat.id,
        "📚 <b>الاستخدام</b>\n\n"
        "• <code>/yt اسم الأغنية</code> — يبحث في YouTube ويرسل الصوت.\n"
        "• <code>/yt رابط YouTube</code> — يرسل الصوت.\n"
        "• أرسل رابط YouTube مباشرة — صوت.\n"
        "• أرسل رابط Instagram — يحاول تنزيل الوسائط.\n"
        "• أرسل رابط Telegram Story — يتطلب جلسة مستخدم Telegram.\n\n"
        "🤖 " + telebot.util.escape(ARTIST),
    )


@bot.message_handler(commands=["yt", "youtube"])
def yt_command(message):
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2:
        bot.reply_to(message, "❗ اكتب اسم الأغنية أو رابط YouTube بعد الأمر.")
        return

    q = query[1].strip()
    status = bot.reply_to(message, "⏳ <b>جاري البحث والتحضير...</b>")

    if is_youtube_url(q):
        url = q
    else:
        # ytsearch1 is fast and returns one result.
        url = f"ytsearch1:{q}"

    # Run in a background thread so polling remains responsive.
    import threading
    threading.Thread(
        target=lambda: asyncio.run(process_youtube(
            message.chat.id, url, "audio", status.message_id
        )),
        daemon=True,
    ).start()


@bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith("/"))
def text_handler(message):
    text = message.text.strip()
    url = extract_url(text)

    # Direct URL handling
    if url:
        status = bot.reply_to(message, "⏳ <b>جاري التحضير...</b>")

        if is_telegram_url(url) and ("/s/" in url or "/stories/" in url):
            import threading
            threading.Thread(
                target=lambda: asyncio.run(
                    process_telegram_story(message.chat.id, url, status.message_id)
                ),
                daemon=True,
            ).start()
            return

        if is_instagram_url(url):
            # Instagram is handled by yt-dlp. Audio is not appropriate for a story/reel,
            # so use video mode.
            import threading
            threading.Thread(
                target=lambda: asyncio.run(
                    process_youtube(message.chat.id, url, "video", status.message_id)
                ),
                daemon=True,
            ).start()
            return

        if is_youtube_url(url):
            import threading
            threading.Thread(
                target=lambda: asyncio.run(
                    process_youtube(message.chat.id, url, "audio", status.message_id)
                ),
                daemon=True,
            ).start()
            return

        bot.edit_message_text("❌ الرابط غير مدعوم حاليًا.", message.chat.id, status.message_id)
        return

    # Plain text: search YouTube and return audio.
    status = bot.reply_to(message, "🔎 <b>جاري البحث في YouTube...</b>")
    query = f"ytsearch1:{text}"

    import threading
    threading.Thread(
        target=lambda: asyncio.run(
            process_youtube(message.chat.id, query, "audio", status.message_id)
        ),
        daemon=True,
    ).start()


# Optional explicit video command
@bot.message_handler(commands=["video"])
def video_command(message):
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2:
        bot.reply_to(message, "❗ أرسل رابط YouTube بعد /video")
        return
    url = query[1].strip()
    if not is_youtube_url(url):
        bot.reply_to(message, "❗ أمر /video يحتاج رابط YouTube.")
        return
    status = bot.reply_to(message, "⏳ <b>جاري تحميل الفيديو...</b>")
    import threading
    threading.Thread(
        target=lambda: asyncio.run(
            process_youtube(message.chat.id, url, "video", status.message_id)
        ),
        daemon=True,
    ).start()


# =========================
# STARTUP
# =========================
async def startup():
    await init_telethon()


def run():
    try:
        asyncio.run(startup())
    except Exception:
        log.exception("startup failed")

    log.info("Bot started")
    # Drop pending updates to avoid an old queue flooding the bot after deployment.
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True,
                allowed_updates=["message", "channel_post"],
            )
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("polling crashed; restarting in 5 seconds")
            import time
            time.sleep(5)


if __name__ == "__main__":
    run()
