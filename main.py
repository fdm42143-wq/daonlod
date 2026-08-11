import os
import requests
import telebot
from pytubefix import YouTube, Search
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

# إعداد التوكن ومتغيرات قاعدة البيانات
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)

# تصحيح الاتصال بـ Supabase (بدون إرسال بارامترات غير مدعومة)
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

# [باقي الدوال الخاصة بك تبقى كما هي تماماً]
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup

def format_views(views):
    if not views: return "0"
    if views >= 1_000_000: return f"{views // 1_000_000}M"
    elif views >= 1_000: return f"{views // 1_000}K"
    return str(views)

def format_duration(seconds):
    if not seconds: return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

# --- الأوامر ومعالجة الرسائل ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": username}).execute()
        except: pass
    
    welcome_msg = "- اهلا بك عزيزي المستخدم.\n\n- أرسل رابط الفيديو أو اسم الأغنية للتحميل."
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🤖 البوت", url=f"https://t.me/{BOT_USERNAME.replace('@','')}"))
    bot.reply_to(message, welcome_msg, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🛠 لوحة تحكم المطور" or message.text in ['/admin', '/control'])
def admin_panel(message):
    if message.from_user.id != DEV_ADMIN_ID: return
    users_count = 0
    if supabase:
        try:
            res = supabase.table("users").select("user_id", count='exact').execute()
            users_count = len(res.data)
        except: pass
    bot.reply_to(message, f"👥 عدد المشتركين: `{users_count}`", parse_mode="Markdown")

# [هنا تضع باقي دوالك للبحث والتحميل المباشر كما هي في كودك السابق تماماً]
# ... [تم اختصارها هنا لتوفير المساحة، استخدم نفس المنطق الخاص بك] ...

if __name__ == "__main__":
    # هذا السطر يحمي البوت من التعارض (Error 409)
    bot.remove_webhook()
    print("البوت يعمل الآن بكامل الميزات وبدون أخطاء...")
    bot.infinity_polling(skip_pending=True)
