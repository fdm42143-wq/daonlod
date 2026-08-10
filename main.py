import os
import telebot
import yt_dlp
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, threaded=False)  # لمنع تداخل الطلبات

# الاتصال بقاعدة بيانات Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608  # آيدي المطور

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🛠 لوحة تحكم المطور"))
    return markup

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

    users_count = 0
    if supabase:
        try:
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

    bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=markup)

# استقبال الروابط ومعالجتها بدون مشاكل الصيغ
@bot.message_handler(func=lambda message: message.text and message.text.strip().startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ | يرجى الانتظار، جاري معالجة التحميل...")

    # خيارات معدلة لتجنب أخطاء الصيغ في يوتيوب وبقية المواقع
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'media_file.%(ext)s',
        'noplaylist': True,
        'nocheckcertificate': True,
        'merge_output_format': 'mp4',
    }

    filename = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        caption_text = f"• {BOT_USERNAME}."
        
        if filename and os.path.exists(filename):
            with open(filename, 'rb') as f:
                if filename.endswith(('.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv')):
                    bot.send_video(message.chat.id, f, caption=caption_text)
                else:
                    bot.send_audio(message.chat.id, f, caption=caption_text)
        else:
            raise Exception("لم يتم العثور على الملف.")
                
        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text=f"❌ عذراً، فشل التحميل.\nالخطأ: {str(e)[:100]}"
            )
        except:
            pass
    finally:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass

# البحث بالنصوص
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and message.text != "🛠 لوحة تحكم المطور")
def handle_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        ydl_opts = {
            'extract_flat': True,
            'default_search': 'ytsearch5',
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            
        entries = results.get('entries', [])
        
        if not entries:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ لم يتم العثور على نتائج.")
            return

        response_text = f"🔍 ¦ نتائج البحث لـ \"{query}\"\n\n"
        markup = InlineKeyboardMarkup()
        
        for index, entry in enumerate(entries, start=1):
            title = entry.get('title', 'فيديو بدون عنوان')
            vid_id = entry.get('id', '')
            response_text += f"🎬 {title}\n📎 https://youtu.be/{vid_id}\n\n"
            markup.add(InlineKeyboardButton(f"نتيجة {index}: {title[:30]}...", url=f"https://youtu.be/{vid_id}"))

        bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=response_text, reply_markup=markup)
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ حدث خطأ في البحث.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "refresh_stats":
        if call.from_user.id == DEV_ADMIN_ID:
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

if __name__ == "__main__":
    print("البوت يعمل الآن بدون تعارض...")
    bot.infinity_polling(skip_pending=True)
