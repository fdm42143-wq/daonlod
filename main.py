import os
import telebot
import yt_dlp
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# قراءة المتغيرات من بيئة العمل (Railway Variables)
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# إعداد قاعدة بيانات Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": username}).execute()
        except Exception as e:
            print(f"فشل حفظ المستخدم: {e}")
            
    welcome_msg = (
        "مرحباً بك في بوت التحميل الذكي 🌐\n\n"
        "• أرسل **رابط فيديو** (يوتيوب، إنستغرام، تيك توك) وسأقوم بتحميله لك مباشرة.\n"
        "• أو أرسل **اسم أغنية أو شعر** للبحث عنها."
    )
    bot.reply_to(message, welcome_msg)

# معالجة الروابط والتحميل المباشر باستخدام yt-dlp
@bot.message_handler(func=lambda message: message.text and message.text.strip().startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ جاري استخراج ومعالجة الملف، تريث قليلاً...")

    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloaded_video.%(ext)s',
        'max_filesize': 50 * 1024 * 1024, # الحد الأقصى 50 ميجابايت لتناسب تيليجرام
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        caption_text = (
            f"✅ تم التحميل بنجاح!\n\n"
            f"---\n"
            f"🤖 Bot: {BOT_USERNAME}\n"
            f"💻 Dev: {DEV_USERNAME}"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 فتح الرابط الأصلي", url=url))

        # إرسال الملف (فيديو أو صوت) للمستخدم
        with open(filename, 'rb') as f:
            if filename.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                bot.send_video(message.chat.id, f, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
            elif filename.endswith(('.mp3', '.m4a', '.wav', '.opus')):
                bot.send_audio(message.chat.id, f, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
            else:
                bot.send_document(message.chat.id, f, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
                
        # حذف الملف من السيرفر بعد الإرسال لتوفير المساحة
        if os.path.exists(filename):
            os.remove(filename)
            
        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ عذراً، فشل التحميل. إما أن الرابط غير مدعوم، أو أن حجم الملف كبير جداً، أو أن الرابط خاص."
            )
        except:
            pass

# معالجة النصوص العادية (للبحث)
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http"))
def handle_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 جاري البحث عن: ({query}) ...")
    
    try:
        search_api = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
        
        caption_text = (
            f"🔍 نتائج البحث لـ: *{query}*\n\n"
            f"اضغط على الزر أدناه لمشاهدة النتائج مباشرة على يوتيوب:\n\n"
            f"---\n"
            f"🤖 Bot: {BOT_USERNAME}\n"
            f"💻 Dev: {DEV_USERNAME}"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📺 اضغط هنا لعرض نتائج البحث", url=search_api))
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=caption_text,
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text="❌ حدث خطأ أثناء عملية البحث."
        )

if __name__ == "__main__":
    print("البوت يعمل الآن بأحدث أدوات التحميل المحلية...")
    bot.infinity_polling()
