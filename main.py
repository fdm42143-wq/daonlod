import os
import re
import shutil
import tempfile
import subprocess
import threading
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
        supabase = create_client(
            SUPABASE_URL,
            SUPABASE_KEY
        )
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

FIXED_THUMB_URL = (
    "https://raw.githubusercontent.com/fdm42143-wq/"
    "daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"
)

# نترك هامش حتى لا يصل الملف إلى حد Telegram
MAX_UPLOAD_MB = 45
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# =========================================================
# BASIC HELPERS
# =========================================================

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.add(
        types.KeyboardButton("🛠 لوحة تحكم المطور")
    )

    return markup


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
            return result.count

    except Exception as e:
        print(f"get_users_count error: {e}")

    return 0


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

        print(
            f"تم تسجيل المستخدم: "
            f"{user_id} | @{username}"
        )

        return True

    except Exception as e:
        print(f"خطأ تسجيل المستخدم: {e}")
        return False


def format_views(views):
    if not views:
        return "0"

    try:
        views = int(views)
    except:
        return "0"

    if views >= 1_000_000:
        return f"{views // 1_000_000}M"

    if views >= 1_000:
        return f"{views // 1_000}K"

    return str(views)


def format_duration(seconds):
    if not seconds:
        return "0:00"

    try:
        seconds = int(seconds)
    except:
        return "0:00"

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


def safe_filename(name):
    if not name:
        return "download"

    name = re.sub(
        r'[\\/*?:"<>|]',
        "_",
        str(name)
    )

    name = name.strip()

    if not name:
        name = "download"

    return name[:80]


def file_size_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except:
        return 0


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


# =========================================================
# TELEGRAM SAFE CALLBACK
# =========================================================

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
        print("FFmpeg error:")
        print(result.stderr[-5000:])

        raise RuntimeError(
            "FFmpeg failed"
        )

    return result


def get_media_duration(path):
    try:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        return float(result.stdout.strip())

    except Exception:
        return 0


def compress_video(input_path, output_path):
    """
    يحاول إنتاج MP4 أقل من 45MB.
    """

    if not ffmpeg_exists():
        raise RuntimeError(
            "FFmpeg غير موجود على السيرفر"
        )

    duration = get_media_duration(input_path)

    if duration <= 0:
        duration = 60

    target_bytes = (
        MAX_UPLOAD_BYTES
        - (2 * 1024 * 1024)
    )

    # صوت 64kbps
    audio_bitrate = 64_000

    total_bitrate = (
        target_bytes * 8 / duration
    )

    video_bitrate = (
        total_bitrate - audio_bitrate
    )

    # لا ننزل الفيديو إلى جودة سيئة جداً
    video_bitrate = max(
        int(video_bitrate),
        120_000
    )

    video_k = max(
        int(video_bitrate / 1000),
        120
    )

    # المحاولة الأولى
    run_command([
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vf",
        "scale='min(1280,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        f"{video_k}k",
        "-maxrate",
        f"{video_k}k",
        "-bufsize",
        f"{video_k * 2}k",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-movflags",
        "+faststart",
        output_path
    ])

    # إذا بقي أكبر من الحد، محاولة ثانية أصغر
    if os.path.exists(output_path):
        if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:

            smaller_path = (
                output_path + ".small.mp4"
            )

            smaller_k = max(
                int(video_k * 0.65),
                100
            )

            run_command([
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-vf",
                "scale='min(854,iw)':-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-b:v",
                f"{smaller_k}k",
                "-maxrate",
                f"{smaller_k}k",
                "-bufsize",
                f"{smaller_k * 2}k",
                "-c:a",
                "aac",
                "-b:a",
                "48k",
                "-movflags",
                "+faststart",
                smaller_path
            ])

            if os.path.exists(smaller_path):

                if os.path.getsize(smaller_path) <= MAX_UPLOAD_BYTES:
                    os.replace(
                        smaller_path,
                        output_path
                    )

                else:
                    os.remove(smaller_path)

    if not os.path.exists(output_path):
        raise RuntimeError(
            "لم يتم إنشاء الفيديو المضغوط"
        )

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            "الفيديو لا يزال أكبر من الحد المسموح"
        )

    return output_path


def convert_audio(input_path, output_path):
    """
    تحويل الصوت إلى MP3 بحجم مناسب.
    """

    run_command([
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "96k",
        output_path
    ])

    if not os.path.exists(output_path):
        raise RuntimeError(
            "فشل تحويل الصوت"
        )

    # إذا بقي كبير، ننزله إلى 64k
    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:

        smaller = output_path + ".small.mp3"

        run_command([
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            smaller
        ])

        if os.path.exists(smaller):
            os.replace(
                smaller,
                output_path
            )

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            "الملف الصوتي أكبر من الحد المسموح"
        )

    return output_path


def convert_voice(input_path, output_path):
    """
    تحويل الصوت إلى OGG/Opus للبصمة.
    """

    run_command([
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "48k",
        output_path
    ])

    if not os.path.exists(output_path):
        raise RuntimeError(
            "فشل تحويل البصمة"
        )

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:

        smaller = output_path + ".small.ogg"

        run_command([
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            smaller
        ])

        if os.path.exists(smaller):
            os.replace(
                smaller,
                output_path
            )

    if os.path.getsize(output_path) > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            "البصمة أكبر من الحد المسموح"
        )

    return output_path


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):

    save_user(message.from_user)

    user_id = message.from_user.id

    welcome_msg = (
        "- اهلا بك عزيزي المستخدم\n\n"
        "- لكشف التاك المخفي يرجى ارسال رابط الحساب "
        "على الانستكرام او اليوزر\n\n"
        "- يمكنك من خلالي التحميل من جميع المواقع.\n"
        "**{ اليك المواقع المدعومه }** ،\n"
        "يوتيوب ، انستكرام ، فيسبوك ، تيك توك ، "
        "لايكي ، كواي ، ساوندكلاود ، بينترست ، "
        "سنابشات ، سبوتيفاي ، ثريدز .\n\n"
        "- للتحميل من اي موقع .\n"
        "ارسل - رابط الفيديو - او يوزر الحساب او كلمه ."
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🤖 البوت",
            url=f"https://t.me/"
                f"{BOT_USERNAME.replace('@', '')}"
        ),
        types.InlineKeyboardButton(
            "💻 المطور",
            url=f"https://t.me/"
                f"{DEV_USERNAME.replace('@', '')}"
        )
    )

    if user_id == DEV_ADMIN_ID:

        bot.send_message(
            message.chat.id,
            "أهلاً بك يا مطور البوت، "
            "تم تفعيل لوحة التحكم بنجاح.",
            reply_markup=get_admin_keyboard()
        )

    bot.send_message(
        message.chat.id,
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=markup
    )


# =========================================================
# ADMIN PANEL
# =========================================================

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

    users_count = get_users_count()

    db_status = (
        "متصلة بنجاح ✅"
        if supabase
        else "غير متصلة ❌"
    )

    admin_text = (
        "🛠 **لوحة تحكم المطور**\n\n"
        "👥 **إحصائيات البوت:**\n"
        f"• عدد المشتركين الكلي: "
        f"`{users_count}` مشترك\n"
        f"• حالة قاعدة البيانات: `{db_status}`\n\n"
        "اختر أحد الإجراءات أدناه:"
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "📊 تحديث الإحصائيات",
            callback_data="refresh_stats"
        )
    )

    bot.send_message(
        message.chat.id,
        admin_text,
        parse_mode="Markdown",
        reply_markup=markup
    )


# =========================================================
# PRIVATE SEARCH
# =========================================================

@bot.message_handler(
    func=lambda message:
    message.text
    and not message.text.startswith("http")
    and message.text != "🛠 لوحة تحكم المطور"
    and message.chat.type == "private"
)
def handle_private_search(message):

    save_user(message.from_user)

    query = message.text.strip()

    msg = bot.reply_to(
        message,
        f"🔍 | جاري البحث عن: ({query}) ..."
    )

    try:

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "default_search": "ytsearch5",
            "noplaylist": True,
            "http_headers": COMMON_HEADERS
        }

        with YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                f"ytsearch5:{query}",
                download=False
            )

            results = info.get(
                "entries",
                []
            )

        if not results:

            bot.edit_message_text(
                "❌ لم يتم العثور على نتائج بحث.",
                message.chat.id,
                msg.message_id
            )

            return

        response_text = (
            f"🔍 **نتائج بحث اليوتيوب لـ "
            f"\"{query}\"**\n\n"
        )

        markup = types.InlineKeyboardMarkup(
            row_width=3
        )

        for idx, vid in enumerate(
            results,
            1
        ):

            if not vid:
                continue

            vid_title = vid.get(
                "title",
                "Unknown"
            )

            vid_id = vid.get("id")

            if not vid_id:
                continue

            duration = format_duration(
                vid.get("duration")
            )

            views = format_views(
                vid.get("view_count")
            )

            channel_name = vid.get(
                "uploader",
                "YouTube"
            )

            # نحمي Markdown من بعض الأحرف
            vid_title = vid_title.replace(
                "*",
                ""
            ).replace(
                "_",
                ""
            ).replace(
                "`",
                ""
            )

            response_text += (
                f"{idx}️⃣ 🎬 {vid_title}\n"
                f"👤 {channel_name}\n"
                f"⏱ {duration} - 👁 {views}\n\n"
            )

            markup.add(

                types.InlineKeyboardButton(
                    f"[{idx}] 🎬 فيديو",
                    callback_data=f"vid_{
