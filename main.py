import os
import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# قراءة المتغيرات من بيئة العمل (Railway Variables)
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# التحقق من المتغيرات الأساسية
if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# إعداد اتصال قاعدة بيانات Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

# روابط الـ APIs المستخرجة من الصور
INSTA_API = "https://dev-ooooo2oo.pantheonsite.io/insd.php?url="
YOUTUBE_API = "https://dev-ooooo2oo.pantheonsite.io/api/YouTube.php?url="
GENERAL_API = "https://dev-ooooo2oo.pantheonsite.io/app.php?url="

# معرفات البوت والمطور المطلوبة للوصف
BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    
    # حفظ المستخدم في Supabase إذا كانت مفعلة
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": username}).execute()
        except Exception as e:
            print(f"فشل حفظ المستخدم في قاعدة البيانات: {e}")
            
    welcome_msg = (
        "مرحباً بك في بوت التحميل الشامل 🌐\n\n"
        "أرسل لي رابطاً من:\n"
        "• إنستغرام (صور أو ريلز/فيديو)\n"
        "• يوتيوب\n"
        "• تيك توك أو منصات أخرى\n\n"
        "وسيتم جلب الرابط المباشر للتحميل مع زر البحث والرابط فوراً!"
    )
    bot.reply_to(message, welcome_msg)

@bot.message_handler(func=lambda message: message.text and message.text.startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ جاري معالجة الطلب وجلب الروابط...")
    
    target_api = GENERAL_API # الافتراضي للمنصات العامة مثل تيك توك
    
    if "instagram.com" in url:
        target_api = INSTA_API
    elif "youtube.com" in url or "youtu.be" in url:
        target_api = YOUTUBE_API

    try:
        # طلب البيانات من الـ الـ API
        response = requests.get(target_api + url, timeout=20)
        
        if response.status_code == 200:
            try:
                data = response.json()
                download_link = data.get("link") or data.get("url") or response.text
            except:
                download_link = response.text

            if download_link and "http" in download_link:
                # صياغة النص مع معلومات البوت والمطور
                caption_text = (
                    f"✅ تم تحميل الملف بنجاح!\n\n"
                    f"🔗 **رابط التحميل المباشر:**\n{download_link}\n\n"
                    f"--- \n"
                    f"🤖 Bot: {BOT_USERNAME}\n"
                    f"💻 Dev: {DEV_USERNAME}"
                )
                
                # إنشاء أزرار تفاعلية (زر لرابط التحميل المباشر وزر للبحث أو زيارة المصدر)
                markup = InlineKeyboardMarkup()
                btn_download = InlineKeyboardButton("📥 تحميل الملف مباشرة", url=download_link)
                btn_source = InlineKeyboardButton("🌐 فتح الرابط الأصلي", url=url)
                markup.add(btn_download)
                markup.add(btn_source)
                
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id,
                    text=caption_text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            else:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id,
                    text="❌ لم يتم العثور على رابط تحميل صالح في الاستجابة."
                )
        else:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ حدث خطأ من المصدر الخارجي (API)، حاول مرة أخرى لاحقاً."
            )
    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ حدث خطأ أثناء الاتصال: {str(e)}"
        )

if __name__ == "__main__":
    print("البوت يعمل الآن...")
    bot.infinity_polling()
