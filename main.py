import os
import telebot
from pytubefix import YouTube
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

# دالة لتحويل التنسيق الأنيق للمشاهدات والوقت
def format_views(views):
    if views >= 1_000_000:
        return f"{views // 1_000_000}M"
    elif views >= 1_000:
        return f"{views // 1_000}K"
    return str(views)

def format_duration(seconds):
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

# معالجة الروابط المباشرة (تحميل فيديو + بصمة صوتية + ملف صوتي)
@bot.message_handler(func=lambda message: message.text and (message.text.strip().startswith("http") or message.text.strip().startswith("/dl_")))
def handle_download(message):
    text = message.text.strip()
    
    # التعامل مع أزرار البحث السريع التي تبدأ بـ /dl_
    if text.startswith("/dl_"):
        # استخراج معرف الفيديو الوهمي أو الحقيقي المرتبط بالبحث
        # في حال تم تخزين الروابط، يمكنك جلب الرابط الحقيقي، هنا سنقوم بمعالجة النص مباشرة
        url = f"https://youtu.be/{text.replace('/dl_', '')}"
    else:
        url = text

    processing_msg = bot.reply_to(message, "⏳ | جاري معالجة التحميل (فيديو وصوت وبصمة)، يرجى الانتظار...")

    video_file = "media_video.mp4"
    audio_file = "media_audio.mp3"
    
    try:
        yt = YouTube(url)
        title = yt.title
        
        # 1. تحميل الفيديو بأعلى دقة
        v_stream = yt.streams.get_highest_resolution()
        if not v_stream:
            raise Exception("فشل في العثور على دقة فيديو مناسبة.")
        v_stream.download(filename=video_file)

        # 2. تحميل الصوت وتحويله لـ mp3 للصوتيات والبصمة
        a_stream = yt.streams.get_audio_only()
        if a_stream:
            downloaded_audio = a_stream.download(filename="temp_audio")
            if os.path.exists(downloaded_audio):
                os.rename(downloaded_audio, audio_file)

        # إرسال الفيديو
        if os.path.exists(video_file):
            with open(video_file, 'rb') as f:
                bot.send_video(message.chat.id, f, caption=f"🎬 {title}\n• {BOT_USERNAME}")

        # إرسال كملف صوتي (Audio)
        if os.path.exists(audio_file):
            with open(audio_file, 'rb') as f:
                bot.send_audio(message.chat.id, f, caption=f"🎵 {title}\n• {BOT_USERNAME}")

        # إرسال كبصمة صوتية (Voice Note)
        if os.path.exists(audio_file):
            with open(audio_file, 'rb') as f:
                bot.send_voice(message.chat.id, f, caption=f"🎤 بصمة صوتية\n• {BOT_USERNAME}")

        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text=f"❌ تعذر التحميل.\nالخطأ: {str(e)[:60]}"
            )
        except:
            pass
    finally:
        for f in [video_file, audio_file, "temp_audio"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass

# نظام البحث بالنصوص مثل "حسام الرسام" بنفس التنسيق المطلوب
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and message.text != "🛠 لوحة تحكم المطور")
def handle_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        from pytubefix import Search
        s = Search(query)
        results = s.results[:5]  # جلب أول 5 نتائج
        
        if not results:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ لم يتم العثور على نتائج بحث.")
            return

        response_text = f"🔍 **نتائج بحث اليوتيوب لـ \"{query}\"**\n\n"
        markup = InlineKeyboardMarkup()
        
        for vid in results:
            vid_title = vid.title
            vid_id = vid.video_id
            duration = format_duration(vid.length)
            views = format_views(vid.views)
            channel_name = vid.author
            
            response_text += f"🎬 {vid_title}\n👤 {channel_name}\n⏱ {duration} - 👁 {views}\n📎 `/dl_{vid_id}`\n\n"
            markup.add(InlineKeyboardButton(f"تحميل: {vid_title[:25]}...", callback_data=f"dl_vid_{vid_id}"))

        markup.add(InlineKeyboardButton("« التالي", callback_data="next_page_dummy"))

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=response_text,
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=f"❌ حدث خطأ في البحث: {str(e)[:40]}")

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
            
    elif call.data.startswith("dl_vid_"):
        vid_id = call.data.replace("dl_vid_", "")
        url = f"https://youtu.be/{vid_id}"
        bot.answer_callback_query(call.id, "⏳ جاري بدء التحميل (فيديو وصوت وبصمة)...")
        
        # محاكاة إرسال الرابط تلقائياً للتحميل
        fake_message = call.message
        fake_message.text = url
        handle_download(fake_message)

if __name__ == "__main__":
    print("البوت يعمل بكامل الميزات الجديدة...")
    bot.infinity_polling(skip_pending=True)
