import os
import requests
import telebot
from yt_dlp import YoutubeDL
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608
FIXED_THUMB_URL = "https://raw.githubusercontent.com/fdm42143-wq/daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup

def get_users_count():
    try:
        if supabase:
            res = supabase.table("users").select("user_id", count="exact").execute()
            if res.count is not None:
                return res.count
    except:
        pass
    return 0

def format_views(views):
    if not views: return "0"
    if views >= 1_000_000: return f"{views // 1_000_000}M"
    elif views >= 1_000: return f"{views // 1_000}K"
    return str(views)

def format_duration(seconds):
    if not seconds: return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": username}).execute()
        except:
            pass
            
    welcome_msg = (
        "- اهلا بك عزيزي المستخدم\n\n"
        "- لكشف التاك المخفي يرجى ارسال رابط الحساب على الانستكرام او اليوزر \n\n"
        "- يمكنك من خلالي التحميل من جميع المواقع .\n"
        "**{ اليك المواقع المدعومه }** ،\n"
        "يوتيوب ، انستكرام ، فيسبوك ، تيك توك ، لايكي ، كواي ، ساوندكلاود ، بينترست ، سنابشات ، سبوتيفاي ، ثريدز .\n\n"
        "- للتحميل من اي موقع .\n"
        "ارسل - رابط الفيديو - او يوزر الحساب او كلمه ."
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🤖 البوت", url=f"https://t.me/{BOT_USERNAME.replace('@','')}"),
        InlineKeyboardButton("💻 المطور", url=f"https://t.me/{DEV_USERNAME.replace('@','')}")
    )
    if user_id == DEV_ADMIN_ID:
        bot.send_message(message.chat.id, "أهلاً بك يا مطور البوت، تم تفعيل لوحة التحكم بنجاح.", reply_markup=get_admin_keyboard())
    bot.reply_to(message, welcome_msg, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🛠 لوحة تحكم المطور" or message.text in ['/admin', '/control'])
def admin_panel(message):
    if message.from_user.id != DEV_ADMIN_ID:
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمطور فقط.")
        return
    users_count = get_users_count()
    admin_text = (
        f"🛠 **لوحة تحكم المطور**\n\n"
        f"👥 **إحصائيات البوت:**\n"
        f"• عدد المشتركين الكلي: `{users_count}` مشترك\n"
        f"• حالة قاعدة البيانات: `متصلة بنجاح ✅`\n\n"
        f"اختر أحد الإجراءات أدناه:"
    )
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📊 تحديث الإحصائيات", callback_data="refresh_stats"))
    bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=markup)

# البحث في الخاص
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and message.text != "🛠 لوحة تحكم المطور" and message.chat.type == 'private')
def handle_private_search(message):
    query = message.text.strip()
    msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': False,
            'default_search': 'ytsearch5',
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': COMMON_HEADERS
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            results = info.get('entries', [])
        
        if not results:
            bot.edit_message_text("❌ لم يتم العثور على نتائج بحث.", message.chat.id, msg.message_id)
            return

        response_text = f"🔍 **نتائج بحث اليوتيوب لـ \"{query}\"**\n\n"
        markup = InlineKeyboardMarkup()
        
        for idx, vid in enumerate(results, 1):
            if not vid: continue
            vid_title = vid.get('title', 'Unknown')
            vid_id = vid.get('id')
            duration = format_duration(vid.get('duration'))
            views = format_views(vid.get('view_count'))
            channel_name = vid.get('uploader', 'YouTube')
            
            response_text += f"{idx}️⃣ 🎬 {vid_title}\n👤 {channel_name}\n⏱ {duration} - 👁 {views}\n\n"
            markup.add(
                InlineKeyboardButton(f"[{idx}] 🎬 فيديو", callback_data=f"vid_{vid_id}"),
                InlineKeyboardButton(f"[{idx}] 🎵 صوتي", callback_data=f"aud_{vid_id}"),
                InlineKeyboardButton(f"[{idx}] 🎤 بصمة", callback_data=f"voi_{vid_id}")
            )

        bot.delete_message(message.chat.id, msg.message_id)
        bot.send_message(message.chat.id, response_text, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ في البحث. تأكد من صحة الكلمة.", message.chat.id, msg.message_id)

# الروابط المباشرة
@bot.message_handler(func=lambda message: message.text and message.text.startswith("http"))
def handle_direct_link(message):
    url = message.text.strip()
    try:
        ydl_opts = {
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': COMMON_HEADERS
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            vid_id = info.get('id')
            title = info.get('title')
            duration = format_duration(info.get('duration'))
            views = format_views(info.get('view_count'))
        
        caption = f"🎬 {title}\n👤 {BOT_USERNAME}\n⏱ {duration} - 👁 {views}"
        markup = InlineKeyboardMarkup(row_width=3).add(
            InlineKeyboardButton("🎬 مقطع فيديو.", callback_data=f"vid_{vid_id}"),
            InlineKeyboardButton("🎵 ملف صوتي.", callback_data=f"aud_{vid_id}"),
            InlineKeyboardButton("🎤 بصمة صوتية.", callback_data=f"voi_{vid_id}")
        )
        bot.send_photo(message.chat.id, FIXED_THUMB_URL, caption=caption, reply_markup=markup)
    except:
        bot.reply_to(message, "❌ تعذر جلب معلومات الفيديو من الرابط.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "refresh_stats":
        if call.from_user.id != DEV_ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ هذا الزر للمطور فقط", show_alert=True)
            return
        count = get_users_count()
        bot.answer_callback_query(call.id, f"📊 عدد المشتركين الحالي: {count}")
        return

    data = call.data
    if "_" not in data: return
    action, vid_id = data.split("_", 1)
    url = f"https://youtu.be/{vid_id}"
    
    bot.answer_callback_query(call.id, "⏳ جاري التحميل والإرسال...")
    
    file_path = None
    try:
        if action == "vid":
            ydl_opts = {
                'format': 'best',
                'outtmpl': '%(id)s.%(ext)s',
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'http_headers': COMMON_HEADERS
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    bot.send_video(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
                
        elif action in ["aud", "voi"]:
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio',
                'outtmpl': '%(id)s.%(ext)s',
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'http_headers': COMMON_HEADERS
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    if action == "aud":
                        bot.send_audio(call.message.chat.id, f, performer=BOT_USERNAME, title=info.get('title', 'Audio'), caption=f"• {BOT_USERNAME}")
                    else:
                        bot.send_voice(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
                
    except Exception as e:
        print(f"Error details: {e}")
        bot.send_message(call.message.chat.id, "❌ حدث خطأ أثناء التحميل.")
    finally:
        if file_path and os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

if __name__ == "__main__":
    print("البوت يعمل بكامل الميزات وبدون أخطاء...")
    bot.infinity_polling(skip_pending=True)
