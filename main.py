import os
import telebot
import yt_dlp
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"خطأ في الاتصال بقاعدة البيانات: {e}")

BOT_USERNAME = "@awe5Bot"
DEV_USERNAME = "@toe7e"
DEV_ADMIN_ID = 5126968608  # آيدي المطور الخاص بك

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
       
    bot.reply_to(message, welcome_msg, parse_mode="Markdown", reply_markup=markup)

# --- لوحة تحكم المطور ---
@bot.message_handler(commands=['admin', 'control'])
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

# معالجة الروابط والتحميل (فيديو، صوت، بصمة)
@bot.message_handler(func=lambda message: message.text and message.text.strip().startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ | يرجى الانتظار، جاري معالجة التحميل...")

    # خيارات تجاوز حماية البوتات في يوتيوب
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'media_file.%(ext)s',
        'noplaylist': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        caption_text = f"• {BOT_USERNAME}."
        
        # خيارات الأزرار: فيديو، ملف صوتي، بصمة صوتية
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🎬 فيديو", callback_data=f"send_vid:{url}"),
            InlineKeyboardButton("🎵 صوتي", callback_data=f"send_aud:{url}"),
            InlineKeyboardButton("🎙 بصمة", callback_data=f"send_voice:{url}")
        )

        with open(filename, 'rb') as f:
            if filename.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                bot.send_video(message.chat.id, f, caption=caption_text, reply_markup=markup)
            else:
                bot.send_audio(message.chat.id, f, caption=caption_text, reply_markup=markup)
                
        if os.path.exists(filename):
            os.remove(filename)
            
        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text=f"❌ عذراً، حظر يوتيوب المؤقت مفعل على السيرفر.\nيرجى تحديث مكتبة yt-dlp أو تجربة رابط آخر."
            )
        except:
            pass

# معالجة البحث بالنصوص
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http"))
def handle_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        ydl_opts = {
            'extract_flat': True,
            'default_search': 'ytsearch5',
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
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
            
            if duration_sec:
                mins = duration_sec // 60
                secs = duration_sec % 60
                duration_str = f"{mins}:{secs:02d}"
            else:
                duration_str = "غير معروف"
            
            response_text += f"🎬 {title}\n📎 https://youtu.be/{vid_id}\n⏱ {duration_str}\n\n"
            markup.add(InlineKeyboardButton(f"نتيجة {index}: {title[:30]}...", url=f"https://youtu.be/{vid_id}"))

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
            text="❌ حدث خطأ في محرك البحث بسبب قيود المنصة، جرب إرسال رابط مباشر."
        )

# معالجة الأزرار وتحويل الصيغ (فيديو، صوت، بصمة)
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
            
    elif call.data.startswith("send_aud:") or call.data.startswith("send_voice:") or call.data.startswith("send_vid:"):
        action, url = call.data.split(":", 1)
        bot.answer_callback_query(call.id, "⏳ جاري تحضير الملف المطلوب...")
        
        try:
            if action == "send_aud":
                ydl_opts = {'format': 'bestaudio', 'outtmpl': 'audio.%(ext)s'}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    fname = ydl.prepare_filename(info)
                with open(fname, 'rb') as af:
                    bot.send_audio(call.message.chat.id, af, caption=f"• {BOT_USERNAME}")
                os.remove(fname)
                
            elif action == "send_voice":
                ydl_opts = {'format': 'bestaudio', 'outtmpl': 'voice.%(ext)s', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'ogg'}]}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    fname = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.ogg'
                with open(fname, 'rb') as vf:
                    bot.send_voice(call.message.chat.id, vf)
                os.remove(fname)
                
            elif action == "send_vid":
                ydl_opts = {'format': 'best', 'outtmpl': 'video.%(ext)s'}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    fname = ydl.prepare_filename(info)
                with open(fname, 'rb') as vf:
                    bot.send_video(call.message.chat.id, vf, caption=f"• {BOT_USERNAME}")
                os.remove(fname)
        except Exception as ex:
            bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء التحويل: {str(ex)[:60]}")

if __name__ == "__main__":
    print("البوت يعمل بكفاءة تامة...")
    bot.infinity_polling()
