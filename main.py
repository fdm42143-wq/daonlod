import os
import glob
import shutil
import subprocess
import tempfile

import telebot
from yt_dlp import YoutubeDL
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from supabase import create_client, Client


# =========================================================
# ENV
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")


# =========================================================
# BOT
# =========================================================

# threaded=True مهم حتى لا تتعطل Callback Queries
# أثناء تحميل ملف كبير.
bot = telebot.TeleBot(
    TOKEN,
    threaded=True,
    num_threads=8
)


# =========================================================
# SUPABASE
# =========================================================

supabase: Client = None
supabase_status = False

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(
            SUPABASE_URL,
            SUPABASE_KEY
        )

        supabase_status = True
        print("🗄 Supabase: متصلة ✅")

    except Exception as e:
        print(f"❌ خطأ في الاتصال بـ Supabase: {e}")
        supabase = None
        supabase_status = False
else:
    print("⚠️ متغيرات Supabase غير موجودة")


# =========================================================
# معلومات البوت
# =========================================================

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608

FIXED_THUMB_URL = (
    "https://raw.githubusercontent.com/fdm42143-wq/"
    "daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"
)


COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# =========================================================
# إعدادات الملفات
# =========================================================

# Telegram Bot API يرفض الملفات الكبيرة.
# نستخدم هامش أمان بدل الوصول إلى الحد بالضبط.

TELEGRAM_SAFE_SIZE = 48 * 1024 * 1024

# أقل حجم/حد نستخدمه في الضغط
VIDEO_MAX_HEIGHT = 720

# جودة ضغط الفيديو
VIDEO_CRF = 28

# صوت الفيديو المضغوط
VIDEO_AUDIO_BITRATE = "96k"

# الصوت
AUDIO_BITRATE = "128k"

# البصمة
VOICE_BITRATE = "64k"


# =========================================================
# أدوات
# =========================================================

def get_admin_keyboard():

    markup = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.add(
        KeyboardButton("🛠 لوحة تحكم المطور")
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
            return int(result.count)

    except Exception as e:

        print(
            f"❌ خطأ في جلب عدد المستخدمين: {e}"
        )

    return 0


def save_user(user_id, username):

    if not supabase:
        return False

    try:

        result = (
            supabase
            .table("users")
            .upsert(
                {
                    "user_id": int(user_id),
                    "username": username
                },
                on_conflict="user_id"
            )
            .execute()
        )

        print(
            f"✅ تم تسجيل المستخدم: "
            f"{user_id} | @{username}"
        )

        return True

    except Exception as e:

        print(
            f"❌ فشل تسجيل المستخدم: "
            f"{e}"
        )

        return False


def format_views(views):

    if not views:
        return "0"

    try:
        views = int(views)
    except Exception:
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
    except Exception:
        return "0:00"

    hours, remainder = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        remainder,
        60
    )

    if hours:

        return (
            f"{hours}:"
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )

    return (
        f"{minutes}:"
        f"{seconds:02d}"
    )


def file_size(path):

    try:
        return os.path.getsize(path)

    except Exception:
        return 0


def is_file_too_large(path):

    return file_size(path) > TELEGRAM_SAFE_SIZE


def find_file(directory, prefix):

    files = glob.glob(
        os.path.join(
            directory,
            prefix + ".*"
        )
    )

    files = [
        f for f in files
        if os.path.isfile(f)
        and not f.endswith(".part")
        and not f.endswith(".ytdl")
    ]

    if not files:
        return None

    files.sort(
        key=os.path.getmtime,
        reverse=True
    )

    return files[0]


def remove_file(path):

    if not path:
        return

    try:

        if os.path.exists(path):
            os.remove(path)

    except Exception as e:

        print(
            f"⚠️ تعذر حذف الملف: "
            f"{path} | {e}"
        )


def check_ffmpeg():

    try:

        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )

        return result.returncode == 0

    except Exception:
        return False


# =========================================================
# FFmpeg - ضغط الفيديو
# =========================================================

def compress_video(
    input_file,
    output_file,
    duration
):

    print(
        "🎬 الفيديو أكبر من الحد، "
        "جاري ضغطه..."
    )

    if not check_ffmpeg():

        raise Exception(
            "FF
