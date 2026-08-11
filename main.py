import os
import re
import shutil
import tempfile
import subprocess
import threading
import uuid
import urllib.request
import asyncio
import base64
from pathlib import Path

import telebot
from telebot import types
from yt_dlp import YoutubeDL
from supabase import create_client, Client

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.stories import GetStoriesByIDRequest
    TELETHON_AVAILABLE = True
except Exception:
    TELETHON_AVAILABLE = False


# =========================================================
# ENV
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=12)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase: متصل ✅")
    except Exception as exc:
        print(f"Supabase connection error: {exc}")


# =========================================================
# SETTINGS
# =========================================================

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608

MAX_UPLOAD_MB = 45
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# صورة ميسي التي رفعتها في GitHub
FIXED_THUMB_URL = (
    "https://raw.githubusercontent.com/fdm42143-wq/"
    "daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"
)

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PENDING = {}
PENDING_LOCK = threading.Lock()
THUMB_CACHE = None
THUMB_LOCK = threading.Lock()

DOWNLOAD_SEMAPHORE = threading.Semaphore(4)

TG_API_ID = os.getenv("TG_API_ID")
TG_API_HASH = os.getenv("TG_API_HASH")
TG_SESSION = os.getenv("TG_SESSION")
YOUTUBE_COOKIES_B64 = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
COOKIE_FILE = None

def prepare_youtube_cookies():
    """Create a temporary cookies.txt from Railway env if provided."""
    global COOKIE_FILE
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        return COOKIE_FILE
    try:
        if YOUTUBE_COOKIES_B64:
            path = os.path.join(tempfile.gettempdir(), "youtube_cookies.txt")
            raw = base64.b64decode(YOUTUBE_COOKIES_B64).decode("utf-8")
            Path(path).write_text(raw, encoding="utf-8")
            COOKIE_FILE = path
            return path
        if YOUTUBE_COOKIES_FILE and os.path.exists(YOUTUBE_COOKIES_FILE):
            COOKIE_FILE = YOUTUBE_COOKIES_FILE
            return COOKIE_FILE
    except Exception as exc:
        print(f"YouTube cookies error: {exc}")
    return None


# =========================================================
# HELPERS
# =========================================================

def is_url(text):
    return bool(re.match(r"^https?://", (text or "").strip(), re.I))


def clean_text(value):
    value = str(value or "")
    return value.replace("\\", "").replace("*", "").replace("_", "").replace("`", "")


def safe_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", str(name or "download"))
    return (name.strip() or "download")[:100]


def format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except Exception:
        return "0:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_views(views):
    try:
        views = int(views or 0)
    except Exception:
        return "0"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M".replace(".0M", "M")
    if views >= 1_000:
        return f"{views / 1_000:.1f}K".replace(".0K", "K")
    return str(views)


def file_size_mb(path):
    try:
        return os.path.getsize(path) / 1024 / 1024
    except Exception:
        return 0.0


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr[-6000:])
        raise RuntimeError("FFmpeg command failed")
    return result


def get_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0


def get_thumb_path(temp_dir):
    global THUMB_CACHE
    with THUMB_LOCK:
        if THUMB_CACHE and os.path.exists(THUMB_CACHE):
            # Copy because Telegram multipart upload consumes a fresh file object.
            target = os.path.join(temp_dir, "cover.jpg")
            shutil.copyfile(THUMB_CACHE, target)
            return target

        target = os.path.join(temp_dir, "cover.jpg")
        try:
            urllib.request.urlretrieve(FIXED_THUMB_URL, target)
        except Exception as exc:
            print(f"Thumbnail download error: {exc}")
            return None

        # Telegram audio thumbnails must be JPEG and under 200 KB / max 320x320.
        if ffmpeg_exists():
            normalized = os.path.join(temp_dir, "cover_normalized.jpg")
            try:
                run_cmd([
                    "ffmpeg", "-y", "-i", target,
                    "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
                    "-q:v", "3", normalized,
                ])
                if os.path.exists(normalized):
                    os.replace(normalized, target)
            except Exception as exc:
                print(f"Thumbnail normalization error: {exc}")

        if os.path.getsize(target) > 190 * 1024:
            # Try a smaller JPEG.
            smaller = os.path.join(temp_dir, "cover_small.jpg")
            if ffmpeg_exists():
                try:
                    run_cmd([
                        "ffmpeg", "-y", "-i", target,
                        "-vf", "scale=240:-2",
                        "-q:v", "6", smaller,
                    ])
                    if os.path.exists(smaller):
                        os.replace(smaller, target)
                except Exception:
                    pass

        cache_path = os.path.join(tempfile.gettempdir(), "awe5bot_cover.jpg")
        try:
            shutil.copyfile(target, cache_path)
            THUMB_CACHE = cache_path
        except Exception:
            pass
        return target


def remember_item(value):
    token = uuid.uuid4().hex[:16]
    with PENDING_LOCK:
        PENDING[token] = value
        if len(PENDING) > 3000:
            for key in list(PENDING.keys())[:500]:
                PENDING.pop(key, None)
    return token


def get_item(token):
    with PENDING_LOCK:
        return PENDING.get(token)


def answer_callback(call, text=None, alert=False):
    try:
        bot.answer_callback_query(call.id, text=text, show_alert=alert)
    except Exception:
        pass


# =========================================================
# SUPABASE
# =========================================================

def save_user(user):
    if not supabase or not user:
        return
    try:
        supabase.table("users").upsert(
            {
                "user_id": int(user.id),
                "username": user.username or "No Username",
            },
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        print(f"save_user error: {exc}")


def users_count():
    if not supabase:
        return 0
    try:
        result = supabase.table("users").select("user_id", count="exact").execute()
        return int(result.count or len(result.data or []))
    except Exception:
        return 0


# =========================================================
# YT-DLP
# =========================================================

def ytdlp_base():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": COMMON_HEADERS,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "socket_timeout": 45,
        "concurrent_fragment_downloads": 8,
        "geo_bypass": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }
    cookie_file = prepare_youtube_cookies()
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts


def search_youtube(query, limit=5):
    opts = ytdlp_base()
    opts.update({
        "extract_flat": True,
        "default_search": f"ytsearch{limit}",
    })
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    return [x for x in (info.get("entries") or []) if x]


def extract_url_info(url):
    opts = ytdlp_base()
    opts["noplaylist"] = True
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def download_with_ytdlp(url, mode, temp_dir):
    output = os.path.join(temp_dir, "%(title).90s.%(ext)s")
    opts = ytdlp_base()
    opts["outtmpl"] = output

    if mode == "audio":
        # Avoid downloading a video when only audio is requested.
        opts.update({
            "format": "bestaudio[ext=m4a]/bestaudio/best",
        })
    else:
        # Prefer a single-file MP4 first to reduce merge time.
        opts.update({
            "format": (
                "best[ext=mp4][filesize<45M]/"
                "best[filesize<45M]/"
                "bestvideo[height<=1080]+bestaudio/best"
            ),
            "merge_output_format": "mp4",
        })

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [
        os.path.join(temp_dir, name)
        for name in os.listdir(temp_dir)
        if os.path.isfile(os.path.join(temp_dir, name))
        and not name.endswith(".part")
    ]
    media = max(files, key=os.path.getsize) if files else None
    if not media:
        raise RuntimeError("لم يتم إنشاء الملف")
    return media, info


# =========================================================
# MEDIA CONVERSION
# =========================================================

def make_mp3(source, temp_dir, title):
    if source.lower().endswith(".mp3"):
        return source
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg غير موجود")

    target = os.path.join(temp_dir, safe_filename(title) + ".mp3")
    run_cmd([
        "ffmpeg", "-y", "-i", source,
        "-vn", "-c:a", "libmp3lame", "-b:a", "128k",
        target,
    ])

    if os.path.getsize(target) > MAX_UPLOAD_BYTES:
        smaller = os.path.join(temp_dir, safe_filename(title) + "_64k.mp3")
        run_cmd([
            "ffmpeg", "-y", "-i", source,
            "-vn", "-c:a", "libmp3lame", "-b:a", "64k",
            smaller,
        ])
        os.replace(smaller, target)
    return target


def make_voice(source, temp_dir, title):
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg غير موجود")
    target = os.path.join(temp_dir, safe_filename(title) + ".ogg")
    run_cmd([
        "ffmpeg", "-y", "-i", source,
        "-vn", "-ac", "1", "-ar", "48000",
        "-c:a", "libopus", "-b:a", "48k",
        target,
    ])
    return target


def compress_video(source, temp_dir, title):
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg غير موجود")

    duration = get_duration(source) or 60
    target_bytes = MAX_UPLOAD_BYTES - 2 * 1024 * 1024
    total_kbps = max(int((target_bytes * 8 / duration) / 1000), 180)
    video_kbps = max(total_kbps - 64, 100)

    target = os.path.join(temp_dir, safe_filename(title) + "_small.mp4")
    run_cmd([
        "ffmpeg", "-y", "-i", source,
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", f"{video_kbps}k",
        "-maxrate", f"{video_kbps}k",
        "-bufsize", f"{video_kbps * 2}k",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        target,
    ])

    if os.path.getsize(target) > MAX_UPLOAD_BYTES:
        smaller = os.path.join(temp_dir, safe_filename(title) + "_tiny.mp4")
        tiny_k = max(int(video_kbps * 0.60), 90)
        run_cmd([
            "ffmpeg", "-y", "-i", source,
            "-vf", "scale='min(854,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{tiny_k}k",
            "-maxrate", f"{tiny_k}k",
            "-bufsize", f"{tiny_k * 2}k",
            "-c:a", "aac", "-b:a", "48k",
            "-movflags", "+faststart",
            smaller,
        ])
        os.replace(smaller, target)

    if os.path.getsize(target) > MAX_UPLOAD_BYTES:
        raise RuntimeError(f"الفيديو أكبر من {MAX_UPLOAD_MB}MB")
    return target


def ensure_mp4(source, temp_dir, title):
    if source.lower().endswith(".mp4"):
        return source
    target = os.path.join(temp_dir, safe_filename(title) + ".mp4")
    run_cmd([
        "ffmpeg", "-y", "-i", source,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-movflags", "+faststart",
        target,
    ])
    return target


# =========================================================
# SEND MEDIA
# =========================================================

def send_audio_and_voice(chat_id, mp3_path, source_for_voice, info, reply_to=None):
    title = str(info.get("title") or "Audio")[:64]
    performer = BOT_USERNAME
    duration = int(info.get("duration") or get_duration(mp3_path) or 0)
    caption = BOT_USERNAME

    thumb = get_thumb_path(os.path.dirname(mp3_path))

    with open(mp3_path, "rb") as audio_file:
        kwargs = {
            "caption": caption,
            "title": title,
            "performer": performer,
            "duration": duration,
            "timeout": 180,
        }
        if thumb and os.path.exists(thumb):
            kwargs["thumbnail"] = types.InputFile(thumb)
        if reply_to:
            kwargs["reply_to_message_id"] = reply_to
        bot.send_audio(chat_id, audio_file, **kwargs)

    # البصمة المطلوبة: نفس الصوت كـ Voice OGG/Opus.
    voice_path = make_voice(source_for_voice, os.path.dirname(mp3_path), title)
    with open(voice_path, "rb") as voice_file:
        bot.send_voice(
            chat_id,
            voice_file,
            caption=BOT_USERNAME,
            duration=duration,
            timeout=180,
        )


def send_video_and_voice(chat_id, video_path, info, reply_to=None):
    title = str(info.get("title") or "Video")[:64]
    duration = int(info.get("duration") or get_duration(video_path) or 0)
    caption = BOT_USERNAME

    with open(video_path, "rb") as video_file:
        bot.send_video(
            chat_id,
            video_file,
            caption=caption,
            duration=duration or None,
            supports_streaming=True,
            timeout=240,
            reply_to_message_id=reply_to,
        )

    # البصمة من صوت الفيديو.
    voice_path = make_voice(video_path, os.path.dirname(video_path), title)
    with open(voice_path, "rb") as voice_file:
        bot.send_voice(
            chat_id,
            voice_file,
            caption=BOT_USERNAME,
            duration=duration or None,
            timeout=180,
        )


# =========================================================
# DOWNLOAD WORKER
# =========================================================

def perform_download(chat_id, url, mode, status_message_id=None, reply_to=None):
    temp_dir = tempfile.mkdtemp(prefix="awe5bot_")
    try:
        with DOWNLOAD_SEMAPHORE:
            media, info = download_with_ytdlp(url, mode, temp_dir)

            title = str(info.get("title") or "download")

            if mode == "audio":
                mp3 = make_mp3(media, temp_dir, title)
                if os.path.getsize(mp3) > MAX_UPLOAD_BYTES:
                    raise RuntimeError("الصوت أكبر من الحد المسموح")
                send_audio_and_voice(chat_id, mp3, media, info, reply_to)
            else:
                video = media
                if not video.lower().endswith(".mp4"):
                    video = ensure_mp4(video, temp_dir, title)
                if os.path.getsize(video) > MAX_UPLOAD_BYTES:
                    video = compress_video(video, temp_dir, title)
                send_video_and_voice(chat_id, video, info, reply_to)

        if status_message_id:
            try:
                bot.delete_message(chat_id, status_message_id)
            except Exception:
                pass

    except Exception as exc:
        print(f"DOWNLOAD ERROR [{mode}] {url}: {exc}")
        if status_message_id:
            try:
                bot.edit_message_text(
                    "❌ فشل التحميل.\n\n"
                    "إذا ظهر خطأ YouTube (Sign in / not a bot)، أضف YOUTUBE_COOKIES_B64 في Railway.\n"
                    "أما الروابط العامة الأخرى فجرّبها مرة ثانية.",
                    chat_id,
                    status_message_id,
                )
            except Exception:
                bot.send_message(chat_id, "❌ فشل التحميل.")
        else:
            bot.send_message(chat_id, "❌ فشل التحميل.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def start_download(chat_id, url, mode, reply_to=None):
    try:
        status = bot.send_message(chat_id, "⏳ جاري التحميل بسرعة... ⚡")
        status_id = status.message_id
    except Exception:
        status_id = None

    threading.Thread(
        target=perform_download,
        args=(chat_id, url, mode, status_id, reply_to),
        daemon=True,
    ).start()


# =========================================================
# SEARCH RESULTS
# =========================================================

def search_and_show(chat_id, query, reply_to=None):
    try:
        results = search_youtube(query, 5)
        if not results:
            bot.send_message(chat_id, "❌ لم يتم العثور على نتائج.")
            return

        text = f"🔍 نتائج يوتيوب: {query}\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)

        for idx, item in enumerate(results, 1):
            vid_id = item.get("id")
            if not vid_id:
                continue
            title = clean_text(item.get("title") or "بدون عنوان")
            uploader = clean_text(item.get("uploader") or "YouTube")
            text += (
                f"{idx}️⃣ {title}\n"
                f"👤 {uploader} | ⏱ {format_duration(item.get('duration'))}\n\n"
            )
            token = remember_item({
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": title,
            })
            markup.add(
                types.InlineKeyboardButton(
                    f"{idx} 🎵 صوت",
                    callback_data=f"aud_{token}",
                ),
                types.InlineKeyboardButton(
                    f"{idx} 🎬 فيديو",
                    callback_data=f"vid_{token}",
                ),
            )

        bot.send_message(
            chat_id,
            text[:4000],
            reply_markup=markup,
            reply_to_message_id=reply_to,
        )
    except Exception as exc:
        print(f"SEARCH ERROR: {exc}")
        bot.send_message(chat_id, "❌ حدث خطأ أثناء البحث.")


# =========================================================
# YOUTUBE SEARCH COMMAND - PRIVATE / GROUP / CHANNEL
# =========================================================

def extract_command_query(message):
    text = getattr(message, "text", "") or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def handle_youtube_search_command(message):
    query = extract_command_query(message)
    if not query:
        bot.reply_to(message, "اكتب هكذا:\n/يوت اسم الأغنية أو الفنان")
        return
    try:
        bot.send_chat_action(message.chat.id, "typing")
    except Exception:
        pass
    threading.Thread(
        target=search_and_show,
        args=(message.chat.id, query, getattr(message, "message_id", None)),
        daemon=True,
    ).start()


@bot.message_handler(commands=["يوت", "yt", "youtube"])
def youtube_command(message):
    save_user(getattr(message, "from_user", None))
    handle_youtube_search_command(message)


@bot.channel_post_handler(commands=["يوت", "yt", "youtube"])
def youtube_channel_command(message):
    handle_youtube_search_command(message)


# =========================================================
# TELEGRAM STORIES (optional MTProto user session)
# =========================================================

def telegram_story_parts(url):
    match = re.search(r"https?://t\.me/([^/?#]+)/s/(\d+)", url, re.I)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


def download_telegram_story(url, temp_dir):
    if not TELETHON_AVAILABLE:
        raise RuntimeError("Telethon غير مثبت")
    if not (TG_API_ID and TG_API_HASH and TG_SESSION):
        raise RuntimeError("TG_API_ID/TG_API_HASH/TG_SESSION غير موجودة")

    username, story_id = telegram_story_parts(url)
    if not username:
        raise RuntimeError("رابط ستوري تيليجرام غير صالح")

    async def runner():
        client = TelegramClient(
            StringSession(TG_SESSION),
            int(TG_API_ID),
            TG_API_HASH,
        )
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("جلسة Telegram غير مسجلة الدخول")

        try:
            peer = await client.get_entity(username)
            result = await client(GetStoriesByIDRequest(
                peer=peer,
                id=[story_id],
            ))
            stories = getattr(result, "stories", None) or []
            if not stories:
                raise RuntimeError("الستوري غير موجود أو غير متاح لهذا الحساب")

            story = stories[0]
            path = await client.download_media(
                story.media,
                file=os.path.join(temp_dir, "telegram_story"),
            )
            if not path:
                raise RuntimeError("تعذر تنزيل ميديا الستوري")
            return path
        finally:
            await client.disconnect()

    return asyncio.run(runner())


def process_telegram_story(chat_id, url, reply_to=None):
    temp_dir = tempfile.mkdtemp(prefix="tg_story_")
    try:
        path = download_telegram_story(url, temp_dir)
        ext = Path(path).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            with open(path, "rb") as photo:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption=BOT_USERNAME,
                    reply_to_message_id=reply_to,
                )
        else:
            info = {"title": "Telegram Story", "duration": get_duration(path)}
            if os.path.getsize(path) > MAX_UPLOAD_BYTES:
                path = compress_video(path, temp_dir, "Telegram Story")
            if not path.lower().endswith(".mp4"):
                path = ensure_mp4(path, temp_dir, "Telegram Story")
            send_video_and_voice(chat_id, path, info, reply_to)
    except Exception as exc:
        print(f"Telegram story error: {exc}")
        bot.send_message(
            chat_id,
            "❌ لم أستطع تنزيل ستوري تيليجرام.\n\n"
            "يحتاج هذا الجزء إلى MTProto بحساب مستخدم معتمد "
            "و TG_API_ID + TG_API_HASH + TG_SESSION، وليس BOT_TOKEN فقط."
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# =========================================================
# URL DOWNLOADS - PRIVATE/GROUP
# =========================================================

@bot.message_handler(
    func=lambda m: bool(m.text and is_url(m.text) and not m.text.startswith("/"))
)
def direct_url_handler(message):
    save_user(getattr(message, "from_user", None))
    url = message.text.strip()

    if is_instagram_story(url):
        start_download(message.chat.id, url, "video", getattr(message, "message_id", None))
        return

    if is_telegram_story(url):
        status = bot.reply_to(message, "⏳ جاري تنزيل ستوري تيليجرام...")
        def story_worker():
            try:
                bot.delete_message(message.chat.id, status.message_id)
            except Exception:
                pass
            process_telegram_story(message.chat.id, url, message.message_id)
        threading.Thread(target=story_worker, daemon=True).start()
        return

    # لا نفحص الرابط قبل اختيار النوع حتى لا يفشل YouTube بسبب الحماية.
    token = remember_item({"url": url, "title": "الرابط"})
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎵 ملف صوتي", callback_data=f"aud_{token}"),
        types.InlineKeyboardButton("🎬 مقطع فيديو", callback_data=f"vid_{token}"),
    )
    bot.reply_to(
        message,
        "🔗 تم استلام الرابط\n\nاختر نوع التحميل:",
        reply_markup=markup,
    )

def is_instagram_story(url):
    return bool(re.search(r"instagram\.com/stories/", url, re.I))


def is_telegram_story(url):
    return bool(re.search(r"t\.me/[^/?#]+/s/\d+", url, re.I))


# =========================================================
# PRIVATE SEARCH WITHOUT COMMAND
# =========================================================

@bot.message_handler(
    func=lambda m: bool(
        m.text
        and not m.text.startswith("/")
        and not is_url(m.text)
        and m.chat.type == "private"
        and m.text != "🛠 لوحة تحكم المطور"
    )
)
def private_search_handler(message):
    save_user(message.from_user)
    query = message.text.strip()
    if query:
        bot.send_chat_action(message.chat.id, "typing")
        threading.Thread(
            target=search_and_show,
            args=(message.chat.id, query, message.message_id),
            daemon=True,
        ).start()


# =========================================================
# CALLBACK DOWNLOAD
# =========================================================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("aud_") or c.data.startswith("vid_")
)
def callback_download(call):
    save_user(call.from_user)
    token = call.data[4:]
    item = get_item(token)
    if not item:
        answer_callback(call, "انتهت صلاحية الزر، ابحث من جديد.", True)
        return

    mode = "audio" if call.data.startswith("aud_") else "video"
    answer_callback(call, "تم استلام الطلب ⚡")
    start_download(
        call.message.chat.id,
        item["url"],
        mode,
        reply_to=None,
    )


# =========================================================
# ADMIN
# =========================================================

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup


@bot.message_handler(commands=["admin", "control"])
def admin_command(message):
    if message.from_user.id != DEV_ADMIN_ID:
        bot.reply_to(message, "❌ للمطور فقط.")
        return
    bot.send_message(
        message.chat.id,
        f"🛠 لوحة المطور\n\n👥 المستخدمون: {users_count()}\n"
        f"🗄 Supabase: {'متصل ✅' if supabase else 'غير متصل ❌'}",
        reply_markup=admin_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "🛠 لوحة تحكم المطور")
def admin_button(message):
    if message.from_user.id != DEV_ADMIN_ID:
        return
    admin_command(message)


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    save_user(message.from_user)
    text = (
        "أهلاً بك 👋\n\n"
        "🎵 ابحث عن أي أغنية بإرسال اسمها.\n"
        "👥 داخل الكروب استخدم: /يوت اسم الأغنية\n"
        "📢 داخل القناة استخدم: /يوت اسم الأغنية\n"
        "🔗 أرسل رابط فيديو/صوت للتحميل.\n"
        "📸 روابط Instagram Stories العامة مدعومة إذا كان المحتوى متاحاً بدون تسجيل دخول.\n\n"
        f"🤖 {BOT_USERNAME}"
    )
    bot.send_message(message.chat.id, text)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 awe5Bot downloader is running")
    print(f"🤖 {BOT_USERNAME}")
    print(f"🗄 Supabase: {'ON' if supabase else 'OFF'}")
    print(f"🎬 FFmpeg: {'ON' if ffmpeg_exists() else 'OFF'}")
    print("=" * 60)

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30,
    )
