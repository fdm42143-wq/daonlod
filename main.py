import os
import requests
import telebot
from pytubefix import YouTube, Search
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

# إعدادات المتغيرات
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)

# الاتصال بقاعدة البيانات
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Database connection error: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608
FIXED_THUMB_URL = "https://raw.githubusercontent.com/fdm42143-wq/daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"

# --- الدوال المساعدة ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup

def get_users_count():
    try:
        if supabase:
            return len(supabase.table("users").select("user_id").execute().data or [])
    except: return 0
    return 0

def format_views(views):
    if not views: return "0"
    if views >= 1_000_000: return f"{views // 1_000_000}M"
    if views >= 1_000: return f"{views // 1_000}K"
    return str(views)

def format_duration(seconds):
    if not seconds: return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

# --- الأوامر ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if supabase:
        try: supabase.table("users").upsert({"user_id": message.from_user.id, "username": message.from_user.username or "No"}).execute()
        except: pass
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🤖 البوت", url=f"https://t.me/{BOT_USERNAME.replace('@','')}"),
               InlineKeyboardButton("💻 المطور", url=f"https://t.me/{DEV_USERNAME.replace('@','')}"))
    
    text = "اهلا بك! أرسل رابطاً أو اسم أغنية للتحميل."
    if message.from_user.id == DEV_ADMIN_ID:
        bot.send_message(message.chat.id, "أهلاً بالمطور، تم تفعيل لوحة التحكم.", reply_markup=get_admin_keyboard())
    bot.reply_to(message, text, reply_markup=markup)

# --- معالجة البحث (المصححة) ---
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and message.text != "🛠 لوحة تحكم المطور" and message.chat.type == 'private')
def handle_private_search(message):
    query = message.text.strip()
    msg = bot.reply_to(message, "🔍 جاري البحث...")
    
    try:
        # إضافة معالجة ذكية للبحث لمنع انهيار الكود
        s = Search(query)
        results = s.results[:5]
        
        if not results:
            raise Exception("No results")

        response_text = f"🔍 نتائج بحث لـ \"{query}\":\n\n"
        markup = InlineKeyboardMarkup()
        
        for idx, vid in enumerate(results, 1):
            response_text += f"{idx}️⃣ 🎬 {vid.title[:40]}\n⏱ {format_duration(vid.length)}\n\n"
            markup.add(
                InlineKeyboardButton(f"[{idx}] فيديو", callback_data=f"vid_{vid.video_id}"),
                InlineKeyboardButton(f"[{idx}] صوت", callback_data=f"aud_{vid.video_id}")
            )
        
        bot.delete_message(message.chat.id, msg.message_id)
        bot.send_message(message.chat.id, response_text, reply_markup=markup)
        
    except Exception:
        bot.edit_message_text("❌ فشل البحث، حاول مرة أخرى أو استخدم رابط مباشر.", message.chat.id, msg.message_id)

# --- معالجة الروابط والتحميل ---
@bot.message_handler(func=lambda message: message.text and message.text.startswith("http"))
def handle_direct_link(message):
    try:
        yt = YouTube(message.text.strip())
        caption = f"🎬 {yt.title}\n👁 {format_views(yt.views)}"
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🎬 فيديو", callback_data=f"vid_{yt.video_id}"),
            InlineKeyboardButton("🎵 صوتي", callback_data=f"aud_{yt.video_id}")
        )
        bot.send_photo(message.chat.id, FIXED_THUMB_URL, caption=caption, reply_markup=markup)
    except:
        bot.reply_to(message, "❌ تعذر جلب معلومات الفيديو.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith(("vid_", "aud_")):
        bot.answer_callback_query(call.id, "⏳ جاري المعالجة...")
        action, vid_id = call.data.split("_")
        try:
            yt = YouTube(f"https://youtu.be/{vid_id}")
            if action == "vid":
                path = yt.streams.get_highest_resolution().download()
                with open(path, 'rb') as f: bot.send_video(call.message.chat.id, f)
            else:
                path = yt.streams.get_audio_only().download()
                with open(path, 'rb') as f: bot.send_audio(call.message.chat.id, f)
            os.remove(path)
        except:
            bot.send_message(call.message.chat.id, "❌ خطأ أثناء التحميل.")

if __name__ == "__main__":
    bot.remove_webhook() # لحل مشكلة 409
    print("البوت يعمل...")
    bot.infinity_polling(skip_pending=True)
