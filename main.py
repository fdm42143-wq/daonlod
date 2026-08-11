import os
import re
import shutil
import tempfile
import subprocess
import threading
import uuid

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
    raise ValueError("BOT_TOKEN غير موجود")

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
        print("Supabase: متصل ✅")
    except Exception as e:
        print("Supabase error:", e)


# =========================================================
# SETTINGS
# =========================================================

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608

MAX_UPLOAD_MB = 45
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PENDING = {}
PENDING_LOCK = threading.Lock()


# =========================================================
# BASIC
# =========================================================

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.add(
        types.KeyboardButton(
            "🛠 لوحة تحكم المطور"
        )
    )

    return markup


def format_views(views):
    try:
        views = int(views or 0)
    except Exception:
        return "0"

    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M".replace(
            ".0M",
            "M"
        )

    if views >= 1_000:
        return f"{views / 1_000:.1f}K".replace(
            ".0K",
            "K"
        )

    return str(views)


def format_duration(seconds):
    try:
        seconds = int(seconds or 0)
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


def safe_filename(name):
    name = str(name or "download")

    name = re.sub(
        r'[\\/*?:"<>|]',
        "_",
        name
    )

    name = name.strip() or "download"

    return name[:80]


def file_size_mb(path):
    try:
        return os.path.getsize(path) / (
            1024 * 1024
        )
    except Exception:
        return 0


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def deno_exists():
    return shutil.which("deno") is not None


def is_url(text):
    return bool(
        re.match(
            r"^https?://",
            (text or "").strip(),
            re.IGNORECASE
        )
    )


def clean_text(text):
    text = str(text or "")

    return (
        text
        .replace("\\", "")
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .replace("[", "")
        .replace("]", "")
    )


# =========================================================
# CALLBACK STORAGE
# =========================================================

def remember_item(user_id, value):
    token = uuid.uuid4().hex[:16]

    with PENDING_LOCK:
        PENDING[
            (int(user_id), token)
        ] = value

        # تنظيف الذاكرة إذا كبرت
        if len(PENDING) > 2000:
            keys = list(PENDING.keys())[:500]

            for key in keys:
                PENDING.pop(
                    key,
                    None
                )

    print(
        "PENDING SAVED:",
        user_id,
        token
    )

    return token


def get_item(user_id, token):
    with PENDING_LOCK:
        item = PENDING.get(
            (int(user_id), token)
        )

    print(
        "PENDING GET:",
        user_id,
        token,
        "FOUND" if item else "NOT FOUND"
    )

    return item


def safe_answer_callback(
    call,
    text=None,
    show_alert=False
):
    try:
        bot.answer_callback_query(
            call.id,
            text=text,
            show_alert=show_alert
        )

        return True

    except Exception as e:
        print(
            "Callback answer error:",
            repr(e)
        )

        return False


# =========================================================
# SUPABASE
# =========================================================

def save_user(user):
    if not supabase:
        return False

    try:
        supabase.table(
            "users"
        ).upsert(
            {
                "user_id": int(user.id),
                "username": (
                    user.username
                    or "No Username"
                )
            },
            on_conflict="user_id"
        ).execute()

        return True

    except Exception as e:
        print(
            "save_user error:",
            e
        )

        return False

