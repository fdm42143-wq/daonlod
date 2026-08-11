import os
import glob
import html
import subprocess
import requests
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
# إعدادات البيئة
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)

supabase: Client = None
supabase_status = False

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        supabase_status = True
        print("✅ تم الاتصال بقاعدة Supabase")
    except Exception as e:
        print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        supabase = None
        supabase_status = False


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
# أدوات مساعدة
# =========================================================

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup


def get_users_count():
    """
    جلب عدد المستخدمين بشكل آمن.
    """
    if not supabase:
        return 0

    try:
        res = (
            supabase
            .table("users")
            .select("user_id", count="exact")
            .execute()
        )

        if res.count is not None:
            return int(res.count)

    except Exception as e:
        print(f"❌ خطأ أثناء جلب عدد المستخدمين: {e}")

    return 0


def format_views(views):
    if not views:
        return "0"

    try:
        views = int(views)
    except:
        return "0"

    if views >= 1_000_000:
        return f"{views // 1_000_000}M"

    elif views >= 1_000:
        return f"{views // 1_000}K"

    return str(views)


def format_duration(seconds):
    if not seconds:
        return "0:00"

    try:
        seconds = int(seconds)
    except:
        return "0:00"

    m, s = divmod(seconds, 60)

    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"

    return f"{m}:{s:02d}"


def safe_text(text):
    """
    حماية النصوص من مشاكل Markdown.
    """
    if not text:
        return ""

    return html.escape(str(text))


def find_downloaded_file(video_id, directory="."):
    """
    يبحث عن الملف الذي أنشأه yt-dlp فعليًا.
    هذا يحل مشكلة اختلاف الامتداد.
    """

    patterns = [
        os.path.join(directory, f"{video_id}.*"),
        os.path.join(directory, f"{video_id}*.*")
    ]

    files = []

    for pattern in patterns:
        files.extend(glob.glob(pattern))

    # إزالة التكرار
    files = list(dict.fromkeys(files))

    # استبعاد الملفات المؤقتة
    files = [
        f for f in files
        if os.path.isfile(f)
        and not f.endswith(".part")
        and not f.endswith(".ytdl")
        and not f.endswith(".temp")
    ]

    if not files:
        return None

    # اختيار أحدث ملف
    files.sort(key=os.path.getmtime, reverse=True)

    return files[0]


def remove_file(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            print(f"⚠️ تعذر حذف الملف {path}: {e}")


def check_ffmpeg():
    """
    التأكد من وجود FFmpeg.
    مطلوب لتحويل الصوت إلى OGG/Opus للبصمة.
    """

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
# START
# =========================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):

    user_id = message.from_user.id
    username = message.from_user.username or "No Username"

    # تسجيل المستخدم
    if supabase:

        try:
            supabase.table("users").upsert(
                {
                    "user_id": user_id,
                    "username": username
                }
            ).execute()

        except Exception as e:
            print(f"❌ خطأ أثناء تسجيل المستخدم: {e}")

    welcome_msg = (
        "- اهلا بك عزيزي المستخدم\n\n"
        "- لكشف التاك المخفي يرجى ارسال رابط الحساب على الانستكرام او اليوزر \n\n"
        "- يمكنك من خلالي التحميل من جميع المواقع .\n"
        "**{ اليك المواقع المدعومه }** ،\n"
        "يوتيوب ، انستكرام ، فيسبوك ، تيك توك ، لايكي ، كواي ، "
        "ساوندكلاود ، بينترست ، سنابشات ، سبوتيفاي ، ثريدز .\n\n"
        "- للتحميل من اي موقع .\n"
        "ارسل - رابط الفيديو - او يوزر الحساب او كلمه ."
    )

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "🤖 البوت",
            url=f"https://t.me/{BOT_USERNAME.replace('@', '')}"
        ),
        InlineKeyboardButton(
            "💻 المطور",
            url=f"https://t.me/{DEV_USERNAME.replace('@', '')}"
        )
    )

    if user_id == DEV_ADMIN_ID:

        bot.send_message(
            message.chat.id,
            "أهلاً بك يا مطور البوت، تم تفعيل لوحة التحكم بنجاح.",
            reply_markup=get_admin_keyboard()
        )

    bot.reply_to(
        message,
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=markup
    )


# =========================================================
# لوحة تحكم المطور
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

    if supabase_status:
        db_status = "متصلة بنجاح ✅"
    else:
        db_status = "غير متصلة ❌"

    admin_text = (
        "🛠 <b>لوحة تحكم المطور</b>\n\n"
        "👥 <b>إحصائيات البوت:</b>\n"
        f"• عدد المشتركين الكلي: <code>{users_count}</code> مشترك\n"
        f"• حالة قاعدة البيانات: <code>{db_status}</code>\n\n"
        "اختر أحد الإجراءات أدناه:"
    )

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "📊 تحديث الإحصائيات",
            callback_data="refresh_stats"
        )
    )

    bot.reply_to(
        message,
        admin_text,
        parse_mode="HTML",
        reply_markup=markup
    )


# =========================================================
# البحث في الخاص
# =========================================================

@bot.message_handler(
    func=lambda message:
    message.text
    and not message.text.startswith("http")
    and message.text != "🛠 لوحة تحكم المطور"
    and message.chat.type == "private"
)
def handle_private_search(message):

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

            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "android",
                        "web"
                    ]
                }
            },

            "http_headers": COMMON_HEADERS
        }

        with YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                f"ytsearch5:{query}",
                download=False
            )

            results = info.get("entries", [])

        if not results:

            bot.edit_message_text(
                "❌ لم يتم العثور على نتائج بحث.",
                message.chat.id,
                msg.message_id
            )

            return

        response_text = (
            f"🔍 <b>نتائج بحث اليوتيوب لـ "
            f"\"{safe_text(query)}\"</b>\n\n"
        )

        markup = InlineKeyboardMarkup()

        number = 0

        for vid in results:

            if not vid:
                continue

            vid_id = vid.get("id")

            if not vid_id:
                continue

            number += 1

            vid_title = safe_text(
                vid.get("title", "Unknown")
            )

            duration = format_duration(
                vid.get("duration")
            )

            views = format_views(
                vid.get("view_count")
            )

            channel_name = safe_text(
                vid.get("uploader", "YouTube")
            )

            response_text += (
                f"{number}️⃣ 🎬 {vid_title}\n"
                f"👤 {channel_name}\n"
                f"⏱ {duration} - 👁 {views}\n\n"
            )

            markup.add(
                InlineKeyboardButton(
                    f"[{number}] 🎬 فيديو",
                    callback_data=f"vid_{vid_id}"
                ),
                InlineKeyboardButton(
                    f"[{number}] 🎵 صوتي",
                    callback_data=f"aud_{vid_id}"
                ),
                InlineKeyboardButton(
                    f"[{number}] 🎤 بصمة",
                    callback_data=f"voi_{vid_id}"
                )
            )

            if number >= 5:
                break

        try:
            bot.delete_message(
                message.chat.id,
                msg.message_id
            )
        except:
            pass

        bot.send_message(
            message.chat.id,
            response_text,
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:

        print(f"❌ Search Error: {e}")

        try:

            bot.edit_message_text(
                "❌ حدث خطأ في البحث. تأكد من صحة الكلمة.",
                message.chat.id,
                msg.message_id
            )

        except:

            bot.send_message(
                message.chat.id,
                "❌ حدث خطأ في البحث. تأكد من صحة الكلمة."
            )


# =========================================================
# الروابط المباشرة
# =========================================================

@bot.message_handler(
    func=lambda message:
    message.text
    and message.text.startswith("http")
)
def handle_direct_link(message):

    url = message.text.strip()

    try:

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,

            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "android",
                        "web"
                    ]
                }
            },

            "http_headers": COMMON_HEADERS
        }

        with YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        vid_id = info.get("id")
        title = info.get("title", "Video")
        duration = format_duration(info.get("duration"))
        views = format_views(info.get("view_count"))

        caption = (
            f"🎬 {title}\n"
            f"👤 {BOT_USERNAME}\n"
            f"⏱ {duration} - 👁 {views}"
        )

        markup = InlineKeyboardMarkup(row_width=3)

        markup.add(
            InlineKeyboardButton(
                "🎬 مقطع فيديو.",
                callback_data=f"vid_{vid_id}"
            ),
            InlineKeyboardButton(
                "🎵 ملف صوتي.",
                callback_data=f"aud_{vid_id}"
            ),
            InlineKeyboardButton(
                "🎤 بصمة صوتية.",
                callback_data=f"voi_{vid_id}"
            )
        )

        bot.send_photo(
            message.chat.id,
            FIXED_THUMB_URL,
            caption=caption,
            reply_markup=markup
        )

    except Exception as e:

        print(f"❌ Direct Link Error: {e}")

        bot.reply_to(
            message,
            "❌ تعذر جلب معلومات الفيديو من الرابط."
        )


# =========================================================
# Callback
# =========================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):

    # -----------------------------------------------------
    # تحديث الإحصائيات
    # -----------------------------------------------------

    if call.data == "refresh_stats":

        if call.from_user.id != DEV_ADMIN_ID:

            bot.answer_callback_query(
                call.id,
                "❌ هذا الزر للمطور فقط",
                show_alert=True
            )

            return

        count = get_users_count()

        db = "متصلة ✅" if supabase_status else "غير متصلة ❌"

        try:

            new_text = (
                "🛠 <b>لوحة تحكم المطور</b>\n\n"
                "👥 <b>إحصائيات البوت:</b>\n"
                f"• عدد المشتركين الكلي: "
                f"<code>{count}</code> مشترك\n"
                f"• حالة قاعدة البيانات: "
                f"<code>{db}</code>\n\n"
                "اختر أحد الإجراءات أدناه:"
            )

            markup = InlineKeyboardMarkup()

            markup.add(
                InlineKeyboardButton(
                    "📊 تحديث الإحصائيات",
                    callback_data="refresh_stats"
                )
            )

            bot.edit_message_text(
                new_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup
            )

            bot.answer_callback_query(
                call.id,
                f"📊 عدد المشتركين الحالي: {count}"
            )

        except Exception as e:

            print(f"❌ Admin refresh error: {e}")

            bot.answer_callback_query(
                call.id,
                f"📊 العدد الحالي: {count}"
            )

        return

    # -----------------------------------------------------
    # أزرار التحميل
    # -----------------------------------------------------

    data = call.data

    if "_" not in data:
        return

    action, vid_id = data.split("_", 1)

    if action not in ["vid", "aud", "voi"]:
        return

    if not vid_id:
        bot.answer_callback_query(
            call.id,
            "❌ معرف الفيديو غير صالح",
            show_alert=True
        )
        return

    url = f"https://youtu.be/{vid_id}"

    bot.answer_callback_query(
        call.id,
        "⏳ جاري التحميل والإرسال..."
    )

    file_path = None
    output_files = []

    try:

        # =================================================
        # VIDEO
        # =================================================

        if action == "vid":

            bot.send_chat_action(
                call.message.chat.id,
                "upload_video"
            )

            output_template = (
                os.path.abspath(
                    f"{vid_id}_video.%(ext)s"
                )
            )

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,

                # أفضل فيديو مع صوت
                "format": (
                    "best[ext=mp4]/"
                    "bestvideo+bestaudio/"
                    "best"
                ),

                "merge_output_format": "mp4",

                "outtmpl": output_template,

                "noplaylist": True,

                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "android",
                            "web"
                        ]
                    }
                },

                "http_headers": COMMON_HEADERS
            }

            with YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True
                )

            # البحث عن الملف الحقيقي
            file_path = find_downloaded_file(
                f"{vid_id}_video"
            )

            if not file_path:

                # fallback
                prepared = ydl.prepare_filename(info)

                if os.path.exists(prepared):
                    file_path = prepared

            if not file_path:

                raise Exception(
                    "لم يتم العثور على ملف الفيديو بعد التحميل"
                )

            output_files.append(file_path)

            title = info.get(
                "title",
                "Video"
            )

            with open(file_path, "rb") as f:

                bot.send_video(
                    call.message.chat.id,
                    f,
                    caption=f"• {BOT_USERNAME}",
                    supports_streaming=True
                )

        # =================================================
        # AUDIO
        # =================================================

        elif action == "aud":

            bot.send_chat_action(
                call.message.chat.id,
                "upload_audio"
            )

            output_template = (
                os.path.abspath(
                    f"{vid_id}_audio.%(ext)s"
                )
            )

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,

                # نأخذ أفضل صوت متوفر
                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": output_template,

                "noplaylist": True,

                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "android",
                            "web"
                        ]
                    }
                },

                "http_headers": COMMON_HEADERS
            }

            with YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True
                )

            # لا نعتمد على prepare_filename وحده
            file_path = find_downloaded_file(
                f"{vid_id}_audio"
            )

            if not file_path:

                prepared = ydl.prepare_filename(info)

                if os.path.exists(prepared):
                    file_path = prepared

            if not file_path:

                raise Exception(
                    "لم يتم العثور على ملف الصوت بعد التحميل"
                )

            output_files.append(file_path)

            title = info.get(
                "title",
                "Audio"
            )

            with open(file_path, "rb") as f:

                bot.send_audio(
                    call.message.chat.id,
                    f,
                    performer=BOT_USERNAME,
                    title=title,
                    caption=f"• {BOT_USERNAME}"
                )

        # =================================================
        # VOICE
        # =================================================

        elif action == "voi":

            bot.send_chat_action(
                call.message.chat.id,
                "upload_voice"
            )

            # التأكد من FFmpeg
            if not check_ffmpeg():

                raise Exception(
                    "FFmpeg غير مثبت. مطلوب لتحويل الصوت إلى OGG/Opus"
                )

            source_template = (
                os.path.abspath(
                    f"{vid_id}_voice_source.%(ext)s"
                )
            )

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,

                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": source_template,

                "noplaylist": True,

                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "android",
                            "web"
                        ]
                    }
                },

                "http_headers": COMMON_HEADERS
            }

            with YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True
                )

            source_file = find_downloaded_file(
                f"{vid_id}_voice_source"
            )

            if not source_file:

                raise Exception(
                    "لم يتم العثور على ملف الصوت الأصلي"
                )

            output_files.append(source_file)

            voice_file = os.path.abspath(
                f"{vid_id}_voice.ogg"
            )

            # تحويل إلى OGG/Opus
            ffmpeg_command = [
                "ffmpeg",
                "-y",
                "-i",
                source_file,

                "-vn",

                "-c:a",
                "libopus",

                "-b:a",
                "64k",

                "-application",
                "voip",

                voice_file
            ]

            process = subprocess.run(
                ffmpeg_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300
            )

            if process.returncode != 0:

                error = process.stderr.decode(
                    "utf-8",
                    errors="ignore"
                )

                raise Exception(
                    f"FFmpeg conversion failed: {error[-1000:]}"
                )

            if not os.path.exists(voice_file):

                raise Exception(
                    "فشل إنشاء ملف البصمة الصوتية"
                )

            output_files.append(voice_file)

            with open(voice_file, "rb") as f:

                bot.send_voice(
                    call.message.chat.id,
                    f,
                    caption=f"• {BOT_USERNAME}"
                )

    except Exception as e:

        print("=" * 60)
        print("❌ DOWNLOAD ERROR")
        print(f"Action: {action}")
        print(f"Video ID: {vid_id}")
        print(f"Error: {e}")
        print("=" * 60)

        error_text = "❌ حدث خطأ أثناء التحميل."

        # أخطاء FFmpeg
        if "FFmpeg" in str(e):

            error_text = (
                "❌ لا يمكن إنشاء البصمة الصوتية حالياً.\n"
                "تأكد من تثبيت FFmpeg على السيرفر."
            )

        bot.send_message(
            call.message.chat.id,
            error_text
        )

    finally:

        # تنظيف جميع الملفات
        for path in output_files:

            remove_file(path)

        # تنظيف الملفات المؤقتة الخاصة بالفيديو
        patterns = [
            f"{vid_id}_video.*",
            f"{vid_id}_audio.*",
            f"{vid_id}_voice_source.*",
            f"{vid_id}_voice.ogg"
        ]

        for pattern in patterns:

            for path in glob.glob(pattern):

                if os.path.isfile(path):
                    remove_file(path)


# =========================================================
# تشغيل البوت
# =========================================================

if __name__ == "__main__":

    print("==============================================")
    print("🤖 البوت يعمل...")
    print(f"👤 المطور: {DEV_USERNAME}")
    print(f"🗄 Supabase: {'متصلة ✅' if supabase_status else 'غير متصلة ❌'}")
    print(f"🎙 FFmpeg: {'موجود ✅' if check_ffmpeg() else 'غير موجود ❌'}")
    print("==============================================")

    bot.infinity_polling(
        skip_pending=True,
        timeout=60,
        long_polling_timeout=60
    )
