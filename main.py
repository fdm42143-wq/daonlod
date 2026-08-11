import os
import requests
import telebot
from pytubefix import YouTube, Search
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client

# إعداد التوكن ومتغيرات قاعدة البيانات
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN في منصة Railway")

bot = telebot.TeleBot(TOKEN, threaded=False)

# تصحيح الاتصال بـ Supabase (بدون بارامتر proxy المسبب للخطأ)
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608
FIXED_THUMB_URL = "https://raw.githubusercontent.com/fdm42143-wq/daonlod/main/7bcc85a8907b306cede0cfd79d5af741.jpg"

# --- الدوال المساعدة ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup

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
    user_id = message.from_user.id
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": message.from_user.username or "No"}).execute()
        except: pass
            
    welcome_msg = "- اهلا بك عزيزي المستخدم. أرسل رابط الفيديو أو اسم الأغنية للتحميل."
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💻 المطور", url=f"https://t.me/{DEV_USERNAME.replace('@','')}"))
    
    bot.reply_to(message, welcome_msg, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🛠 لوحة تحكم المطور")
def admin_panel(message):
    if message.from_user.id != DEV_ADMIN_ID: return
    users_count = 0
    if supabase:
        try:
            res = supabase.table("users").select("user_id", count='exact').execute()
            users_count = len(res.data)
        except: pass
    bot.reply_to(message, f"👥 عدد المشتركين: {users_count}")

# معالجة الروابط
@bot.message_handler(func=lambda message: message.text and message.text.startswith("http"))
def handle_direct_link(message):
    try:
        yt = YouTube(message.text.strip())
        caption = f"🎬 {yt.title}\n⏱ {format_duration(yt.length)}"
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("🎬 فيديو", callback_data=f"vid_{yt.video_id}"),
            InlineKeyboardButton("🎵 صوتي", callback_data=f"aud_{yt.video_id}")
        )
        bot.send_photo(message.chat.id, FIXED_THUMB_URL, caption=caption, reply_markup=markup)
    except:
        bot.reply_to(message, "❌ تعذر جلب معلومات الرابط.")

# معالجة الكلمات للبحث
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http"))
def handle_search(message):
    try:
        results = Search(message.text).results[:3]
        if not results: return bot.reply_to(message, "❌ لا توجد نتائج.")
        
        for vid in results:
            markup = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🎬 فيديو", callback_data=f"vid_{vid.video_id}"),
                InlineKeyboardButton("🎵 صوتي", callback_data=f"aud_{vid.video_id}")
            )
            bot.send_message(message.chat.id, f"🎬 {vid.title}", reply_markup=markup)
    except: pass

# معالجة التحميل (Callback)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, vid_id = call.data.split("_")
    bot.answer_callback_query(call.id, "⏳ جاري التحميل...")
    try:
        yt = YouTube(f"https://youtu.be/{vid_id}")
        if action == "vid":
            path = yt.streams.get_highest_resolution().download()
            with open(path, 'rb') as f: bot.send_video(call.message.chat.id, f)
            os.remove(path)
        else:
            path = yt.streams.get_audio_only().download()
            with open(path, 'rb') as f: bot.send_audio(call.message.chat.id, f)
            os.remove(path)
    except:
        bot.send_message(call.message.chat.id, "❌ خطأ أثناء التحميل.")

if __name__ == "__main__":
    # ضروري جداً لمسح أي Webhook قديم يسبب تضارب
    bot.remove_webhook()
    print("البوت يعمل الآن...")
    bot.infinity_polling(skip_pending=True)
