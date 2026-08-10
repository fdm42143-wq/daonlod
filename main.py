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

# إعداد اتصال قاعدة بيانات Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_USERNAME_CLEAN = "toe7e" # يوزر المطور بدون علامة الـ @

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    
    # حفظ المستخدم في قاعدة بيانات Supabase
    if supabase:
        try:
            supabase.table("users").upsert({"user_id": user_id, "username": username}).execute()
        except Exception as e:
            print(f"فشل حفظ المستخدم: {e}")
            
    welcome_msg = (
        "• اهلا بك عزيزي المستخدم\n\n"
        "• لكشف التاك المخفي يرجى ارسال رابط الحساب على الانستكرام او اليوزر\n\n"
        "• يمكنك من خلالي التحميل من جميع المواقع .\n"
        "**{ اليك المواقع المدعومه }** ،\n"
        "يوتيوب ، انستكرام ، فيسبوك ، تيك توك ، لايكي ، كواي ، ساوندكلاود ، بينترست ، سنابشات ، سبوتيفاي ، ثريدز .\n\n"
        "• للتحميل من اي موقع .\n"
        "ارسل - رابط الفيديو - او يوزر الحساب او كلمه ."
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🤖 البوت", url=f"https://t.me/{BOT_USERNAME.replace('@','')}"),
        InlineKeyboardButton("💻 المطور", url=f"https://t.me/{DEV_USERNAME_CLEAN}")
    )
       
    bot.reply_to(message, welcome_msg, parse_mode="Markdown", reply_markup=markup)

# --- لوحة تحكم المطور ---
@bot.message_handler(commands=['admin', 'control'])
def admin_panel(message):
    username = message.from_user.username
    
    # التحقق مما إذا كان المرسل هو المطور حصراً
    if not username or username.lower() != DEV_USERNAME_CLEAN.lower():
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمطور فقط.")
        return

    users_count = 0
    if supabase:
        try:
            # جلب عدد المستخدمين من قاعدة البيانات
            response = supabase.table("users").select("user_id", count="exact").execute()
            if response.count is not None:
                users_count = response.count
        except Exception as e:
            print(f"خطأ في جلب عدد المستخدمين: {e}")

    admin_text = (
        f"🛠 **لوحة تحكم المطور**\n\n"
        f"👥 **إحصائيات البوت:**\n"
        f"• عدد المشتركين الكلي: `{users_count}` مشترك\n"
        f"• حالة قاعدة البيانات: `متصلة بنجاح ✅`\n\n"
        f"اختر أحد الإجراءات أدناه:"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 تحديث الإحصائيات", callback_data="refresh_stats"))
    markup.add(InlineKeyboardButton("📢 إرسال اذاعة للكل", callback_data="broadcast_msg"))

    bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=markup)

# معالجة الروابط والتحميل المباشر
@bot.message_handler(func=lambda message: message.text and message.text.strip().startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ | يرجى الانتظار، يتم قياس حجم التحميل...")

    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloaded_media.%(ext)s',
        'max_filesize': 50 * 1024 * 1024,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        caption_text = f"• {BOT_USERNAME}."
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("تحميل كملف صوتي.", callback_data="audio_dl"))
        markup.add(InlineKeyboardButton("تحميل باعلى دقه HD.", url=url))

        with open(filename, 'rb') as f:
            if filename.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                bot.send_video(message.chat.id, f, caption=caption_text, reply_markup=markup)
            elif filename.endswith(('.mp3', '.m4a', '.wav', '.opus')):
                bot.send_audio(message.chat.id, f, caption=caption_text, reply_markup=markup)
            else:
                bot.send_document(message.chat.id, f, caption=caption_text, reply_markup=markup)
                
        if os.path.exists(filename):
            os.remove(filename)
            
        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ عذراً، فشل التحميل. يرجى التأكد من أن الرابط عام وغير مخفي أو كبير الحجم."
            )
        except:
            pass

# معالجة النصوص العادية والبحث
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http"))
def handle_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        ydl_opts = {
            'extract_flat': True,
            'default_search': 'ytsearch5',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            
        entries = results.get('entries', [])
        
        if not entries:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ لم يتم العثور على نتائج مطابقة.")
            return

        response_text = f"🔍 ¦ نتائج البحث لـ \"{query}\"\n\n"
        markup = InlineKeyboardMarkup()
        
        for index, entry in enumerate(entries, start=1):
            title = entry.get('title', 'فيديو بدون عنوان')
            vid_id = entry.get('id', '')
            duration_sec = entry.get('duration', 0)
            
            mins = duration_sec // 60
            secs = duration_sec % 60
            duration_str = f"{mins}:{secs:02d}" if duration_sec else "مباشر/غير معروف"
            
            response_text += f"🎬 {title}\n📎 https://youtu.be/{vid_id}\n⏱ {duration_str}\n\n"
            markup.add(InlineKeyboardButton(f"نتيجة {index}: {title[:30]}...", url=f"https://youtu.be/{vid_id}"))

        markup.add(InlineKeyboardButton("« التالي", callback_data="next_page"))

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=response_text,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text="❌ حدث خطأ أثناء عملية البحث، حاول مرة أخرى."
        )

# معالجة الضغط على الأزرار الشفافة لوحة التحكم
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "refresh_stats":
        if call.from_user.username and call.from_user.username.lower() == DEV_USERNAME_CLEAN.lower():
            users_count = 0
            if supabase:
                try:
                    res = supabase.table("users").select("user_id", count="exact").execute()
                    if res.count is not None:
                        users_count = res.count
                except:
                    pass
            bot.answer_callback_query(call.id, f"📊 عدد المشتركين الحالي: {users_count}")
        else:
            bot.answer_callback_query(call.id, "❌ هذا الزر للمطور فقط", show_alert=True)
            
    elif call.data == "broadcast_msg":
        if call.from_user.username and call.from_user.username.lower() == DEV_USERNAME_CLEAN.lower():
            bot.answer_callback_query(call.id, "أرسل الرسالة التي تريد إذاعتها للمشتركين (قريباً)", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ هذا الزر للمطور فقط", show_alert=True)

if __name__ == "__main__":
    print("البوت يعمل مع لوحة تحكم المطور بكفاءة...")
    bot.infinity_polling()
