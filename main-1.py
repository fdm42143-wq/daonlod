import os
import re
import shutil
import tempfile
import subprocess
import threading
import uuid
from html import escape

import telebot
from telebot import types
from yt_dlp import YoutubeDL
from supabase import create_client, Client


# =========================================================
# ENV
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(
    TOKEN,
    threaded=True,
    num_threads=8
)

supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase: متصل بنجاح ✅")
    except Exception as e:
        print(f"Supabase connection error: {e}")
else:
    print("تحذير: SUPABASE_URL أو SUPABASE_KEY غير موجود")


# =========================================================
# SETTINGS
# =========================================================

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608

# Telegram Bot API cloud upload limit is 50 MB.
# Keep a safe margin.
MAX_UPLOAD_MB = 45
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

FIXED_THUMB_URL = (
    "https://raw.githubusercontent.com/fdm42143-wq/"
    "daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"
)

# Temporary callback storage.
# It lets callback_data stay very short.
PENDING = {}
PENDING_LOCK = threading.Lock()


# =========================================================
# BASIC HELPERS
# =========================================================

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup


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


def format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except Exception:
        return "0:00"

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def safe_filename(name):
    name = str(name or "download")
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip() or "download"
    return name[:80]


def file_size_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def is_url(text):
    return bool(
        re.match(
            r"^https?://",
            (text or "").strip(),
            re.IGNORECASE
        )
    )


def clean_markdown(text):
    text = str(text or "")
    return (
        text.replace("\\", "")
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .replace("[", "")
        .replace("]", "")
    )


def remember_item(user_id, value):
    token = uuid.uuid4().hex[:12]

    with PENDING_LOCK:
        PENDING[(user_id, token)] = value

        # Avoid unlimited memory growth.
        if len(PENDING) > 1000:
            for key in list(PENDING.keys())[:200]:
                PENDING.pop(key, None)

    return token


def get_item(user_id, token):
    with PENDING_LOCK:
        return PENDING.get((user_id, token))


def safe_answer_callback(call, text=None, show_alert=False):
    try:
        bot.answer_callback_query(
            call.id,
            text=text,
            show_alert=show_alert
        )
    except Exception as e:
        print(f"Callback answer ignored: {e}")


# =========================================================
# SUPABASE
# =========================================================

def save_user(user):
    if not supabase:
        print("Supabase غير متصل، لم يتم حفظ المستخدم")
        return False

    try:
        user_id = int(user.id)
        username = user.username or "No Username"

        supabase.table("users").upsert(
            {
                "user_id": user_id,
                "username": username
            },
            on_conflict="user_id"
        ).execute()

        print(f"تم تسجيل/تحديث المستخدم: {user_id} | @{username}")
        return True

    except Exception as e:
        print(f"خطأ تسجيل المستخدم: {e}")
        return False


def get_users_count():
    if not supabase:
        return 0

    try:
        result = (
            supabase
            .table("users")
            .select("user_id", count="exact")
            .execute()
        )

        if result.count is not None:
            return int(result.count)

        # Fallback in case count is unavailable.
        data = result.data or []
        return len(data)

    except Exception as e:
        print(f"get_users_count error: {e}")
        return 0


# =========================================================
# FFMPEG
# =========================================================

def run_command(command):
    print("Running:", " ".join(command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr[-5000:])
        raise RuntimeError("FFmpeg failed")

    return result


def get_media_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        return float(result.stdout.strip())
    except Exception:
        return 0


def compress_video(input_path, output_path):
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg غير موجود على السيرفر")

    duration = get_media_duration(input_path)
    if duration <= 0:
        duration = 60

    target_bytes = MAX_UPLOAD_BYTES - (2 * 1024 * 1024)
    audio_bitrate = 64_000

    total_bitrate = (target_bytes * 8) / duration
    video_bitrate = max(int(total_bitrate - audio_bitrate), 120_000)
    video_k = max(int(video_bitrate / 1000), 120)

    run_command([
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", f"{video_k}k",
        "-maxrate", f"{video_k}k",
        "-bufsize", f"{video_k * 2}k",
        "-c:a", "aac",
        "-b:a", "64k",
        "-movflags", "+faststart",
        output_path
    ])

    if not os.path.exists(output_path):
        raise RuntimeError("لم يتم إنشاء الفيديو المضغوط")

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        smaller_path = output_path + ".small.mp4"
        smaller_k = max(int(video_k * 0.60), 90)

        run_command([
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "scale='min(854,iw)':-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", f"{smaller_k}k",
            "-maxrate", f"{smaller_k}k",
            "-bufsize", f"{smaller_k * 2}k",
            "-c:a", "aac",
            "-b:a", "48k",
            "-movflags", "+faststart",
            smaller_path
        ])

        if os.path.exists(smaller_path):
            if os.path.getsize(smaller_path) <= MAX_UPLOAD_BYTES:
                os.replace(smaller_path, output_path)
            else:
                os.remove(smaller_path)

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"الفيديو أكبر من {MAX_UPLOAD_MB}MB حتى بعد الضغط"
        )

    return output_path


def convert_audio(input_path, output_path):
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg غير موجود على السيرفر")

    run_command([
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "96k",
        output_path
    ])

    if not os.path.exists(output_path):
        raise RuntimeError("فشل تحويل الصوت")

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        smaller = output_path + ".small.mp3"

        run_command([
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "64k",
            smaller
        ])

        if os.path.exists(smaller):
            os.replace(smaller, output_path)

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"الصوت أكبر من {MAX_UPLOAD_MB}MB"
        )

    return output_path


# =========================================================
# YT-DLP
# =========================================================

def extract_info(url_or_query, download=False, audio=False):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": COMMON_HEADERS,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "geo_bypass": True,
        "ignoreerrors": False,
    }

    if download:
        if audio:
            opts.update({
                "format": "bestaudio/best",
            })
        else:
            # Prefer formats below the Telegram limit.
            # If no such format exists, fall back to best.
            opts.update({
                "format": (
                    "bestvideo[filesize<45M]+bestaudio[filesize<15M]/"
                    "best[filesize<45M]/"
                    "best"
                ),
                "merge_output_format": "mp4",
            })

    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(
            url_or_query,
            download=download
        )


def search_youtube(query):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch5",
        "noplaylist": True,
        "http_headers": COMMON_HEADERS,
        "retries": 2,
        "socket_timeout": 30,
    }

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"ytsearch5:{query}",
            download=False
        )

    return [
        x for x in (info.get("entries") or [])
        if x
    ]


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    save_user(message.from_user)

    welcome_msg = (
        "اهلا بك عزيزي المستخدم 👋\n\n"
        "لكشف التاك المخفي يرجى ارسال رابط الحساب "
        "على الانستكرام او اليوزر.\n\n"
        "يمكنك من خلالي التحميل من جميع المواقع "
        "التي يدعمها yt-dlp.\n\n"
        "يوتيوب، انستكرام، فيسبوك، تيك توك، لايكي، "
        "كواي، ساوندكلاود، بينترست، سنابشات، "
        "سبوتيفاي، ثريدز وغيرها.\n\n"
        "للتحميل من اي موقع:\n"
        "ارسل رابط الفيديو أو اسم/كلمة للبحث."
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "🤖 البوت",
            url=f"https://t.me/{BOT_USERNAME.replace('@', '')}"
        ),
        types.InlineKeyboardButton(
            "💻 المطور",
            url=f"https://t.me/{DEV_USERNAME.replace('@', '')}"
        )
    )

    if message.from_user.id == DEV_ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "أهلاً بك يا مطور البوت، تم تفعيل لوحة التحكم بنجاح.",
            reply_markup=get_admin_keyboard()
        )

    bot.send_message(
        message.chat.id,
        welcome_msg,
        reply_markup=markup
    )


# =========================================================
# ADMIN
# =========================================================

def send_admin_stats(chat_id, message_id=None):
    count = get_users_count()
    db_status = "متصلة بنجاح ✅" if supabase else "غير متصلة ❌"

    text = (
        "🛠 لوحة تحكم المطور\n\n"
        "📊 إحصائيات البوت:\n"
        f"👥 عدد المشتركين الكلي: {count}\n"
        f"🗄 حالة قاعدة البيانات: {db_status}\n"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "🔄 تحديث الإحصائيات",
            callback_data="refresh_stats"
        )
    )

    if message_id:
        try:
            bot.edit_message_text(
                text,
                chat_id,
                message_id,
                reply_markup=markup
            )
            return
        except Exception:
            pass

    bot.send_message(
        chat_id,
        text,
        reply_markup=markup
    )


@bot.message_handler(
    func=lambda message:
    message.text == "🛠 لوحة تحكم المطور"
    or message.text in ["/admin", "/control"]
)
def admin_panel(message):
    if message.from_user.id != DEV_ADMIN_ID:
        bot.reply_to(
            message,
            "❌ عذراً، هذا الأمر مخصص للمطور فقط."
        )
        return

    send_admin_stats(message.chat.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "refresh_stats"
)
def refresh_stats(call):
    if call.from_user.id != DEV_ADMIN_ID:
        safe_answer_callback(
            call,
            "غير مسموح ❌",
            True
        )
        return

    safe_answer_callback(call, "تم تحديث الإحصائيات ✅")
    send_admin_stats(
        call.message.chat.id,
        call.message.message_id
    )


# =========================================================
# SEARCH
# =========================================================

def send_search_results(message, query):
    status = bot.reply_to(
        message,
        f"🔍 جاري البحث عن: {query}"
    )

    try:
        results = search_youtube(query)

        if not results:
            bot.edit_message_text(
                "❌ لم يتم العثور على نتائج.",
                message.chat.id,
                status.message_id
            )
            return

        text = f"🔍 نتائج البحث عن: {query}\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)

        for idx, vid in enumerate(results, 1):
            vid_id = vid.get("id")
            if not vid_id:
                continue

            title = clean_markdown(
                vid.get("title", "بدون عنوان")
            )
            uploader = clean_markdown(
                vid.get("uploader", "YouTube")
            )

            duration = format_duration(
                vid.get("duration")
            )
            views = format_views(
                vid.get("view_count")
            )

            text += (
                f"{idx}️⃣ 🎬 {title}\n"
                f"👤 {uploader}\n"
                f"⏱ {duration} | 👁 {views}\n\n"
            )

            token = remember_item(
                message.from_user.id,
                {
                    "type": "youtube",
                    "url": (
                        f"https://www.youtube.com/watch?v={vid_id}"
                    ),
                    "title": title,
                }
            )

            markup.add(
                types.InlineKeyboardButton(
                    f"[{idx}] 🎬 فيديو",
                    callback_data=f"vid_{token}"
                ),
                types.InlineKeyboardButton(
                    f"[{idx}] 🎵 صوت",
                    callback_data=f"aud_{token}"
                )
            )

        bot.edit_message_text(
            text,
            message.chat.id,
            status.message_id,
            reply_markup=markup
        )

    except Exception as e:
        print(f"Search error: {e}")

        try:
            bot.edit_message_text(
                "❌ حدث خطأ أثناء البحث. حاول مرة أخرى.",
                message.chat.id,
                status.message_id
            )
        except Exception:
            pass


# =========================================================
# DIRECT URL
# =========================================================

def send_url_options(message, url):
    status = bot.reply_to(
        message,
        "🔎 جاري فحص الرابط..."
    )

    try:
        info = extract_info(url, download=False)

        if not info:
            raise RuntimeError("لم يتم العثور على معلومات")

        title = clean_markdown(
            info.get("title", "الملف")
        )

        duration = format_duration(
            info.get("duration")
        )

        uploader = clean_markdown(
            info.get("uploader") or
            info.get("channel") or
            "غير معروف"
        )

        token = remember_item(
            message.from_user.id,
            {
                "type": "url",
                "url": url,
                "title": title,
            }
        )

        text = (
            f"🎬 {title}\n"
            f"👤 {uploader}\n"
            f"⏱ {duration}\n\n"
            "اختر نوع التحميل:"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "🎬 فيديو",
                callback_data=f"vid_{token}"
            ),
            types.InlineKeyboardButton(
                "🎵 صوت MP3",
                callback_data=f"aud_{token}"
            )
        )

        bot.edit_message_text(
            text,
            message.chat.id,
            status.message_id,
            reply_markup=markup
        )

    except Exception as e:
        print(f"URL info error: {e}")

        try:
            bot.edit_message_text(
                "❌ حدث خطأ أثناء التحميل أو قراءة الرابط.",
                message.chat.id,
                status.message_id
            )
        except Exception:
            pass


# =========================================================
# PRIVATE TEXT
# =========================================================

@bot.message_handler(
    func=lambda message:
    message.text
    and not message.text.startswith("/")
    and message.text != "🛠 لوحة تحكم المطور"
    and message.chat.type == "private"
)
def handle_text(message):
    save_user(message.from_user)

    text = message.text.strip()

    if not text:
        return

    if is_url(text):
        threading.Thread(
            target=send_url_options,
            args=(message, text),
            daemon=True
        ).start()
        return

    threading.Thread(
        target=send_search_results,
        args=(message, text),
        daemon=True
    ).start()


# =========================================================
# DOWNLOAD CORE
# =========================================================

def download_media(url, mode):
    temp_dir = tempfile.mkdtemp(prefix="telegram_dl_")

    try:
        if mode == "audio":
            output_template = os.path.join(
                temp_dir,
                "%(title).80s.%(ext)s"
            )

            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "http_headers": COMMON_HEADERS,
                "retries": 3,
                "fragment_retries": 3,
                "socket_timeout": 60,
                "format": "bestaudio/best",
                "outtmpl": output_template,
            }

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    url,
                    download=True
                )

            files = [
                os.path.join(temp_dir, x)
                for x in os.listdir(temp_dir)
            ]

            media = next(
                (
                    x for x in files
                    if os.path.isfile(x)
                ),
                None
            )

            if not media:
                raise RuntimeError(
                    "لم يتم العثور على الملف الصوتي"
                )

            title = info.get("title", "audio")
            mp3_path = os.path.join(
                temp_dir,
                safe_filename(title) + ".mp3"
            )

            convert_audio(media, mp3_path)

            return temp_dir, mp3_path, "audio", info

        output_template = os.path.join(
            temp_dir,
            "%(title).80s.%(ext)s"
        )

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "http_headers": COMMON_HEADERS,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 60,
            "format": (
                "bestvideo[filesize<45M]+"
                "bestaudio[filesize<15M]/"
                "best[filesize<45M]/best"
            ),
            "merge_output_format": "mp4",
            "outtmpl": output_template,
        }

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

        files = [
            os.path.join(temp_dir, x)
            for x in os.listdir(temp_dir)
            if os.path.isfile(os.path.join(temp_dir, x))
        ]

        if not files:
            raise RuntimeError(
                "لم يتم العثور على الملف بعد التحميل"
            )

        # Choose the largest media file.
        media = max(
            files,
            key=lambda x: os.path.getsize(x)
        )

        title = info.get("title", "video")
        final_path = media

        # Telegram safe size.
        if os.path.getsize(media) > MAX_UPLOAD_BYTES:
            compressed = os.path.join(
                temp_dir,
                safe_filename(title) + "_compressed.mp4"
            )

            compress_video(
                media,
                compressed
            )

            final_path = compressed

        # Ensure MP4 for send_video.
        if not final_path.lower().endswith(".mp4"):
            converted = os.path.join(
                temp_dir,
                safe_filename(title) + ".mp4"
            )

            run_command([
                "ffmpeg", "-y",
                "-i", final_path,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-c:a", "aac",
                "-movflags", "+faststart",
                converted
            ])

            final_path = converted

            if os.path.getsize(final_path) > MAX_UPLOAD_BYTES:
                compressed = os.path.join(
                    temp_dir,
                    safe_filename(title) + "_compressed.mp4"
                )
                compress_video(
                    final_path,
                    compressed
                )
                final_path = compressed

        if os.path.getsize(final_path) > MAX_UPLOAD_BYTES:
            raise RuntimeError(
                f"الفيديو أكبر من {MAX_UPLOAD_MB}MB"
            )

        return temp_dir, final_path, "video", info

    except Exception:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )
        raise


# =========================================================
# DOWNLOAD WORKER
# =========================================================

def process_download(call, url, mode):
    chat_id = call.message.chat.id

    status = bot.send_message(
        chat_id,
        "⏳ جاري التحميل...\n"
        "قد يستغرق الأمر بعض الوقت حسب حجم الملف."
    )

    temp_dir = None

    try:
        temp_dir, path, result_mode, info = download_media(
            url,
            mode
        )

        size = file_size_mb(path)
        title = info.get(
            "title",
            "الملف"
        )

        caption = (
            f"✅ تم التحميل بنجاح\n\n"
            f"📌 {clean_markdown(title)}\n"
            f"📦 الحجم: {size:.1f} MB\n\n"
            f"🤖 {BOT_USERNAME}"
        )

        # Delete status before sending if possible.
        try:
            bot.delete_message(
                chat_id,
                status.message_id
            )
        except Exception:
            pass

        with open(path, "rb") as media:
            if result_mode == "audio":
                bot.send_audio(
                    chat_id,
                    media,
                    caption=caption,
                    title=title[:64]
                )
            else:
                bot.send_video(
                    chat_id,
                    media,
                    caption=caption,
                    supports_streaming=True,
                    width=0,
                    height=0
                )

    except Exception as e:
        print("=" * 60)
        print("DOWNLOAD ERROR")
        print(f"URL: {url}")
        print(f"Mode: {mode}")
        print(f"Error: {e}")
        print("=" * 60)

        try:
            bot.edit_message_text(
                "❌ حدث خطأ أثناء التحميل.\n\n"
                "قد يكون السبب أن الموقع منع التحميل "
                "أو أن الملف أكبر من الحد المسموح في Telegram.",
                chat_id,
                status.message_id
            )
        except Exception:
            try:
                bot.send_message(
                    chat_id,
                    "❌ حدث خطأ أثناء التحميل."
                )
            except Exception:
                pass

    finally:
        if temp_dir:
            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )


# =========================================================
# CALLBACKS
# =========================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("vid_")
    or call.data.startswith("aud_")
)
def download_callback(call):
    save_user(call.from_user)

    mode = (
        "video"
        if call.data.startswith("vid_")
        else "audio"
    )

    token = call.data[4:]
    item = get_item(
        call.from_user.id,
        token
    )

    if not item:
        safe_answer_callback(
            call,
            "انتهت صلاحية الزر، أرسل الرابط مرة أخرى.",
            True
        )
        return

    safe_answer_callback(
        call,
        "تم استلام الطلب ✅"
    )

    url = item.get("url")

    threading.Thread(
        target=process_download,
        args=(call, url, mode),
        daemon=True
    ).start()


# =========================================================
# ERROR HANDLING
# =========================================================

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 البوت يعمل...")
    print(f"👨‍💻 المطور: {DEV_USERNAME}")
    print(
        "🗄 Supabase:",
        "متصل ✅" if supabase else "غير متصل ❌"
    )
    print(
        "🎬 FFmpeg:",
        "موجود ✅" if ffmpeg_exists() else "غير موجود ❌"
    )
    print("=" * 50)

    # Important:
    # infinity_polling itself is the main loop.
    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
