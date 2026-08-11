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

        if len(PENDING) > 2000:
            keys = list(PENDING.keys())[:500]

            for key in keys:
                PENDING.pop(key, None)

    return token


def get_item(user_id, token):
    with PENDING_LOCK:
        return PENDING.get(
            (int(user_id), token)
        )


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
    except Exception as e:
        print("Callback error:", e)


# =========================================================
# SUPABASE
# =========================================================

def save_user(user):
    if not supabase:
        return False

    try:
        supabase.table("users").upsert(
            {
                "user_id": int(user.id),
                "username": user.username or "No Username"
            },
            on_conflict="user_id"
        ).execute()

        return True

    except Exception as e:
        print("save_user error:", e)
        return False


def get_users_count():
    if not supabase:
        return 0

    try:
        result = (
            supabase
            .table("users")
            .select(
                "user_id",
                count="exact"
            )
            .execute()
        )

        if result.count is not None:
            return int(result.count)

        return len(result.data or [])

    except Exception as e:
        print("get_users_count error:", e)
        return 0


# =========================================================
# FFMPEG
# =========================================================

def run_command(command):
    print(
        "RUN:",
        " ".join(map(str, command))
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr[-5000:])
        raise RuntimeError(
            "FFmpeg failed"
        )

    return result


def get_media_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        return float(
            result.stdout.strip()
        )

    except Exception:
        return 0


def compress_video(
    input_path,
    output_path
):
    if not ffmpeg_exists():
        raise RuntimeError(
            "FFmpeg غير موجود"
        )

    duration = get_media_duration(
        input_path
    )

    if duration <= 0:
        duration = 60

    target_bytes = (
        MAX_UPLOAD_BYTES
        - (2 * 1024 * 1024)
    )

    audio_bitrate = 64_000

    total_bitrate = (
        target_bytes * 8
    ) / duration

    video_bitrate = max(
        int(
            total_bitrate
            - audio_bitrate
        ),
        120_000
    )

    video_k = max(
        int(video_bitrate / 1000),
        120
    )

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

    if not os.path.exists(output_path):
        raise RuntimeError(
            "فشل ضغط الفيديو"
        )

    if (
        os.path.getsize(output_path)
        > MAX_UPLOAD_BYTES
    ):
        smaller_path = (
            output_path
            + ".small.mp4"
        )

        smaller_k = max(
            int(video_k * 0.60),
            90
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
            if (
                os.path.getsize(
                    smaller_path
                )
                <= MAX_UPLOAD_BYTES
            ):
                os.replace(
                    smaller_path,
                    output_path
                )
            else:
                os.remove(smaller_path)

    if (
        os.path.getsize(output_path)
        > MAX_UPLOAD_BYTES
    ):
        raise RuntimeError(
            f"الفيديو أكبر من "
            f"{MAX_UPLOAD_MB}MB"
        )

    return output_path


def convert_audio(
    input_path,
    output_path
):
    if not ffmpeg_exists():
        raise RuntimeError(
            "FFmpeg غير موجود"
        )

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

    if (
        os.path.getsize(output_path)
        > MAX_UPLOAD_BYTES
    ):
        smaller = (
            output_path
            + ".small.mp3"
        )

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

    if (
        os.path.getsize(output_path)
        > MAX_UPLOAD_BYTES
    ):
        raise RuntimeError(
            f"الصوت أكبر من "
            f"{MAX_UPLOAD_MB}MB"
        )

    return output_path


# =========================================================
# YT-DLP + DENO
# =========================================================

def ytdlp_base_options():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "http_headers": COMMON_HEADERS,

        "retries": 3,
        "fragment_retries": 3,

        "socket_timeout": 60,

        "geo_bypass": True,

        "ignoreerrors": False,

        # مهم خصوصاً مع YouTube
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "web",
                    "android"
                ]
            }
        }
    }

    # تشغيل Deno تلقائياً إذا كان مثبتاً
    deno = shutil.which("deno")

    if deno:
        opts["js_runtimes"] = {
            "deno": {
                "path": deno
            }
        }

        print(
            "YouTube Deno: فعال ✅",
            deno
        )

    else:
        print(
            "YouTube Deno: غير موجود ⚠️"
        )

    return opts


def extract_info(
    url,
    download=False,
    audio=False
):
    opts = ytdlp_base_options()

    if download:
        if audio:
            opts["format"] = (
                "bestaudio/best"
            )
        else:
            opts.update({
                "format": (
                    "bestvideo[ext=mp4]"
                    "[filesize<45M]+"
                    "bestaudio[ext=m4a]"
                    "[filesize<15M]/"
                    "best[ext=mp4]"
                    "[filesize<45M]/"
                    "best"
                ),
                "merge_output_format": "mp4"
            })

    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(
            url,
            download=download
        )


# =========================================================
# YOUTUBE SEARCH
# =========================================================

def search_youtube(query):
    opts = ytdlp_base_options()

    opts.update({
        "extract_flat": True,
        "default_search": "ytsearch5",
        "noplaylist": True
    })

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"ytsearch5:{query}",
            download=False
        )

    return [
        item
        for item in (
            info.get("entries") or []
        )
        if item
    ]


# =========================================================
# START
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def send_welcome(message):
    save_user(
        message.from_user
    )

    text = (
        "أهلاً بك 👋\n\n"
        "أرسل رابط فيديو أو اسم للبحث "
        "والتحميل من المواقع المدعومة."
    )

    markup = types.InlineKeyboardMarkup()

    markup.row(
        types.InlineKeyboardButton(
            "🤖 البوت",
            url=(
                "https://t.me/"
                + BOT_USERNAME.replace("@", "")
            )
        ),
        types.InlineKeyboardButton(
            "👨‍💻 المطور",
            url=(
                "https://t.me/"
                + DEV_USERNAME.replace("@", "")
            )
        )
    )

    if (
        message.from_user.id
        == DEV_ADMIN_ID
    ):
        bot.send_message(
            message.chat.id,
            "🛠 تم تفعيل لوحة المطور.",
            reply_markup=get_admin_keyboard()
        )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=markup
    )


# =========================================================
# ADMIN
# =========================================================

def send_admin_stats(
    chat_id,
    message_id=None
):
    count = get_users_count()

    db_status = (
        "متصلة ✅"
        if supabase
        else "غير متصلة ❌"
    )

    text = (
        "🛠 لوحة تحكم المطور\n\n"
        f"👥 المستخدمون: {count}\n"
        f"🗄 قاعدة البيانات: {db_status}\n"
        f"🎬 FFmpeg: "
        f"{'موجود ✅' if ffmpeg_exists() else 'غير موجود ❌'}\n"
        f"🟨 Deno: "
        f"{'موجود ✅' if deno_exists() else 'غير موجود ❌'}"
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🔄 تحديث",
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
        message.text
        in [
            "🛠 لوحة تحكم المطور",
            "/admin",
            "/control"
        ]
)
def admin_panel(message):
    if (
        message.from_user.id
        != DEV_ADMIN_ID
    ):
        bot.reply_to(
            message,
            "❌ هذا الأمر للمطور فقط."
        )
        return

    send_admin_stats(
        message.chat.id
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "refresh_stats"
)
def refresh_stats(call):
    if (
        call.from_user.id
        != DEV_ADMIN_ID
    ):
        safe_answer_callback(
            call,
            "غير مسموح ❌",
            True
        )
        return

    safe_answer_callback(
        call,
        "تم التحديث ✅"
    )

    send_admin_stats(
        call.message.chat.id,
        call.message.message_id
    )


# =========================================================
# SEARCH RESULTS
# =========================================================

def send_search_results(
    message,
    query
):
    status = bot.send_message(
        message.chat.id,
        f"🔍 جاري البحث عن:\n{query}"
    )

    try:
        results = search_youtube(
            query
        )

        if not results:
            bot.edit_message_text(
                "❌ لم يتم العثور على نتائج.",
                message.chat.id,
                status.message_id
            )
            return

        text = (
            f"🔍 نتائج البحث:\n\n"
        )

        markup = types.InlineKeyboardMarkup(
            row_width=2
        )

        number = 0

        for vid in results:
            vid_id = vid.get("id")

            if not vid_id:
                continue

            number += 1

            title = clean_text(
                vid.get(
                    "title",
                    "بدون عنوان"
                )
            )

            uploader = clean_text(
                vid.get(
                    "uploader",
                    "YouTube"
                )
            )

            duration = format_duration(
                vid.get("duration")
            )

            views = format_views(
                vid.get("view_count")
            )

            text += (
                f"{number}️⃣ {title}\n"
                f"👤 {uploader}\n"
                f"⏱ {duration} "
                f"| 👁 {views}\n\n"
            )

            token = remember_item(
                message.from_user.id,
                {
                    "type": "youtube",
                    "url": (
                        "https://www.youtube.com/"
                        f"watch?v={vid_id}"
                    ),
                    "title": title
                }
            )

            markup.row(
                types.InlineKeyboardButton(
                    f"🎬 فيديو {number}",
                    callback_data=(
                        f"vid_{token}"
                    )
                ),
                types.InlineKeyboardButton(
                    f"🎵 صوت {number}",
                    callback_data=(
                        f"aud_{token}"
                    )
                )
            )

        if number == 0:
            bot.edit_message_text(
                "❌ لم يتم العثور على نتائج.",
                message.chat.id,
                status.message_id
            )
            return

        bot.edit_message_text(
            text,
            message.chat.id,
            status.message_id,
            reply_markup=markup
        )

    except Exception as e:
        print(
            "SEARCH ERROR:",
            repr(e)
        )

        try:
            bot.edit_message_text(
                "❌ تعذر البحث حالياً.\n"
                "حاول مرة أخرى.",
                message.chat.id,
                status.message_id
            )
        except Exception:
            pass


# =========================================================
# DIRECT URL
# =========================================================

def send_url_options(
    message,
    url
):
    status = bot.send_message(
        message.chat.id,
        "🔎 جاري فحص الرابط..."
    )

    try:
        info = extract_info(
            url,
            download=False
        )

        if not info:
            raise RuntimeError(
                "No information"
            )

        title = clean_text(
            info.get(
                "title",
                "الملف"
            )
        )

        uploader = clean_text(
            info.get("uploader")
            or info.get("channel")
            or "غير معروف"
        )

        duration = format_duration(
            info.get("duration")
        )

        token = remember_item(
            message.from_user.id,
            {
                "type": "url",
                "url": url,
                "title": title
            }
        )

        text = (
            f"🎬 {title}\n"
            f"👤 {uploader}\n"
            f"⏱ {duration}\n\n"
            "اختر نوع التحميل:"
        )

        markup = types.InlineKeyboardMarkup()

        markup.row(
            types.InlineKeyboardButton(
                "🎬 فيديو",
                callback_data=(
                    f"vid_{token}"
                )
            ),
            types.InlineKeyboardButton(
                "🎵 صوت MP3",
                callback_data=(
                    f"aud_{token}"
                )
            )
        )

        bot.edit_message_text(
            text,
            message.chat.id,
            status.message_id,
            reply_markup=markup
        )

    except Exception as e:
        print(
            "URL INFO ERROR:",
            repr(e)
        )

        try:
            bot.edit_message_text(
                "❌ تعذر قراءة هذا الرابط.\n\n"
                "تأكد أن الرابط صحيح "
                "وأن الموقع يسمح بالتحميل.",
                message.chat.id,
                status.message_id
            )
        except Exception:
            pass


# =========================================================
# TEXT HANDLER
# =========================================================

@bot.message_handler(
    func=lambda message:
        message.text
        and not message.text.startswith("/")
        and message.text
        != "🛠 لوحة تحكم المطور"
        and message.chat.type == "private"
)
def handle_text(message):
    save_user(
        message.from_user
    )

    text = message.text.strip()

    if not text:
        return

    if is_url(text):
        threading.Thread(
            target=send_url_options,
            args=(
                message,
                text
            ),
            daemon=True
        ).start()

    else:
        threading.Thread(
            target=send_search_results,
            args=(
                message,
                text
            ),
            daemon=True
        ).start()


# =========================================================
# DOWNLOAD
# =========================================================

def download_media(
    url,
    mode
):
    temp_dir = tempfile.mkdtemp(
        prefix="telegram_dl_"
    )

    try:

        output_template = os.path.join(
            temp_dir,
            "%(title).80s.%(ext)s"
        )

        opts = ytdlp_base_options()

        opts["outtmpl"] = (
            output_template
        )

        if mode == "audio":

            opts.update({
                "format":
                    "bestaudio/best"
            })

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    url,
                    download=True
                )

            files = [
                os.path.join(
                    temp_dir,
                    x
                )
                for x in os.listdir(
                    temp_dir
                )
                if os.path.isfile(
                    os.path.join(
                        temp_dir,
                        x
                    )
                )
            ]

            if not files:
                raise RuntimeError(
                    "لم يتم تنزيل الصوت"
                )

            media = max(
                files,
                key=os.path.getsize
            )

            title = info.get(
                "title",
                "audio"
            )

            mp3_path = os.path.join(
                temp_dir,
                safe_filename(title)
                + ".mp3"
            )

            convert_audio(
                media,
                mp3_path
            )

            return (
                temp_dir,
                mp3_path,
                "audio",
                info
            )

        # VIDEO

        opts.update({
            "format": (
                "bestvideo[ext=mp4]"
                "[filesize<45M]+"
                "bestaudio[ext=m4a]"
                "[filesize<15M]/"
                "best[ext=mp4]"
                "[filesize<45M]/"
                "best"
            ),
            "merge_output_format":
                "mp4"
        })

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

        files = [
            os.path.join(
                temp_dir,
                x
            )
            for x in os.listdir(
                temp_dir
            )
            if os.path.isfile(
                os.path.join(
                    temp_dir,
                    x
                )
            )
        ]

        if not files:
            raise RuntimeError(
                "لم يتم تنزيل الفيديو"
            )

        media = max(
            files,
            key=os.path.getsize
        )

        title = info.get(
            "title",
            "video"
        )

        final_path = media

        # إذا أكبر من الحد
        if (
            os.path.getsize(
                final_path
            )
            > MAX_UPLOAD_BYTES
        ):

            compressed = os.path.join(
                temp_dir,
                safe_filename(title)
                + "_compressed.mp4"
            )

            compress_video(
                final_path,
                compressed
            )

            final_path = compressed

        # تحويل إلى MP4
        if not final_path.lower().endswith(
            ".mp4"
        ):

            converted = os.path.join(
                temp_dir,
                safe_filename(title)
                + ".mp4"
            )

            run_command([
                "ffmpeg",
                "-y",
                "-i",
                final_path,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                converted
            ])

            final_path = converted

        if (
            os.path.getsize(
                final_path
            )
            > MAX_UPLOAD_BYTES
        ):
            compressed = os.path.join(
                temp_dir,
                safe_filename(title)
                + "_compressed.mp4"
            )

            compress_video(
                final_path,
                compressed
            )

            final_path = compressed

        if (
            os.path.getsize(
                final_path
            )
            > MAX_UPLOAD_BYTES
        ):
            raise RuntimeError(
                f"الفيديو أكبر من "
                f"{MAX_UPLOAD_MB}MB"
            )

        return (
            temp_dir,
            final_path,
            "video",
            info
        )

    except Exception:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise


# =========================================================
# DOWNLOAD WORKER
# =========================================================

def process_download(
    call,
    url,
    mode
):
    chat_id = (
        call.message.chat.id
    )

    status = bot.send_message(
        chat_id,
        "⏳ جاري التحميل..."
    )

    temp_dir = None

    try:

        (
            temp_dir,
            path,
            result_mode,
            info
        ) = download_media(
            url,
            mode
        )

        title = clean_text(
            info.get(
                "title",
                "الملف"
            )
        )

        size = file_size_mb(
            path
        )

        caption = (
            "✅ تم التحميل بنجاح\n\n"
            f"📌 {title}\n"
            f"📦 الحجم: {size:.1f} MB\n\n"
            f"🤖 {BOT_USERNAME}"
        )

        try:
            bot.delete_message(
                chat_id,
                status.message_id
            )
        except Exception:
            pass

        with open(
            path,
            "rb"
        ) as media:

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
                    supports_streaming=True
                )

    except Exception as e:

        print("=" * 60)
        print("DOWNLOAD ERROR")
        print(
            "URL:",
            url
        )
        print(
            "MODE:",
            mode
        )
        print(
            "ERROR:",
            repr(e)
        )
        print("=" * 60)

        error_text = (
            "❌ تعذر تحميل الملف.\n\n"
            "قد يكون السبب:\n"
            "• الموقع منع الطلب\n"
            "• الفيديو غير متاح\n"
            "• الملف أكبر من الحد المسموح\n"
            "• YouTube طلب تحققاً إضافياً\n\n"
            "حاول برابط آخر."
        )

        try:
            bot.edit_message_text(
                error_text,
                chat_id,
                status.message_id
            )
        except Exception:
            try:
                bot.send_message(
                    chat_id,
                    error_text
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
# CALLBACK BUTTONS
# =========================================================

@bot.callback_query_handler(
    func=lambda call:
        (
            call.data.startswith("vid_")
            or call.data.startswith("aud_")
        )
)
def download_callback(call):

    save_user(
        call.from_user
    )

    if call.data.startswith(
        "vid_"
    ):
        mode = "video"
        token = call.data[
            len("vid_"):
        ]

    else:
        mode = "audio"
        token = call.data[
            len("aud_"):
        ]

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

    url = item.get("url")

    if not url:
        safe_answer_callback(
            call,
            "الرابط غير صالح.",
            True
        )
        return

    # إغلاق حالة Loading للزر فوراً
    safe_answer_callback(
        call,
        "⏳ بدأ التحميل..."
    )

    # منع الضغط المتكرر على نفس الزر
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
    except Exception:
        pass

    threading.Thread(
        target=process_download,
        args=(
            call,
            url,
            mode
        ),
        daemon=True
    ).start()


# =========================================================
# POLLING
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("🚀 البوت يعمل...")
    print(
        f"🤖 Bot: {BOT_USERNAME}"
    )
    print(
        f"👨‍💻 Developer: {DEV_USERNAME}"
    )
    print(
        "🗄 Supabase:",
        "متصل ✅"
        if supabase
        else "غير متصل ❌"
    )
    print(
        "🎬 FFmpeg:",
        "موجود ✅"
        if ffmpeg_exists()
        else "غير موجود ❌"
    )
    print(
        "🟨 Deno:",
        "موجود ✅"
        if deno_exists()
        else "غير موجود ❌"
    )
    print("=" * 60)

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
