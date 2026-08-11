import os
import requests
import telebot
from pytubefix import YouTube, Search
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)

# ... (إعداد Supabase كما هو في كودك الأصلي) ...
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

# دالة مساعدة لإنشاء كائن YouTube محدث
def create_yt_obj(url):
    # إضافة client='WEB' يحل 90% من مشاكل فشل التحميل
    return YouTube(url, client='WEB')

# ... (دوال get_admin_keyboard, format_views, format_duration تبقى كما هي) ...

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    # ... (كود الـ refresh_stats و more_ يبقى كما هو) ...
    if call.data == "refresh_stats": 
        # (نفس كودك السابق)
        pass 
    elif call.data.startswith("more_"):
        # (نفس كودك السابق)
        pass

    data = call.data
    parts = data.split("_", 1)
    if len(parts) != 2: return
        
    action, vid_id = parts[0], parts[1]
    url = f"https://youtu.be/{vid_id}"
    
    bot.answer_callback_query(call.id, "⏳ جاري المعالجة...")
    
    try:
        yt = create_yt_obj(url)
        safe_title = "".join([c for c in yt.title if c.isalnum() or c.isspace()]).strip() or "media"
        
        if action == "vid":
            stream = yt.streams.get_highest_resolution()
            filename = f"{safe_title}.mp4"
            stream.download(filename=filename)
            with open(filename, 'rb') as f:
                bot.send_video(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
            os.remove(filename)
                
        elif action == "aud":
            # استخدام streams.get_audio_only() مع ضمان التحميل
            stream = yt.streams.filter(only_audio=True).first()
            temp_file = stream.download(filename="temp_a")
            filename = f"{safe_title}.mp3"
            os.rename(temp_file, filename)
            with open(filename, 'rb') as f:
                bot.send_audio(call.message.chat.id, f, performer=BOT_USERNAME, title=yt.title)
            os.remove(filename)
                
        elif action == "voi":
            stream = yt.streams.filter(only_audio=True).first()
            temp_file = stream.download(filename="temp_v")
            filename = f"{safe_title}.ogg"
            os.rename(temp_file, filename)
            with open(filename, 'rb') as f:
                bot.send_voice(call.message.chat.id, f)
            os.remove(filename)
                
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء التحميل، يرجى المحاولة مرة أخرى.")

# تأكد من إضافة bot.remove_webhook() في النهاية
if __name__ == "__main__":
    print("البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
