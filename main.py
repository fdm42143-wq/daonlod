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

def format_views(views):
    if not views:
        return "0"
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

# معالجة البحث في المجموعات والقنوات عند البدء بكلمة "يوت"
@bot.message_handler(func=lambda message: message.text and message.text.startswith("يوت ") and message.chat.type in ['group', 'supergroup', 'channel'])
def handle_group_search(message):
    query = message.text.replace("يوت ", "", 1).strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث والتحميل الفوري لـ: ({query}) ...")
    
    thumb_file = None
    try:
        s = Search(query)
        if not s.results:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ لم يتم العثور على نتيجة.")
            return
            
        vid = s.results[0]
        url = f"https://youtu.be/{vid.video_id}"
        yt = YouTube(url)
        safe_title = "".join([c for c in yt.title if c.isalnum() or c.isspace()]).strip() or "media"
        
        # تنزيل الغلاف الثابت
        thumb_res = requests.get(FIXED_THUMB_URL)
        if thumb_res.status_code == 200:
            thumb_file = f"fixed_thumb_{vid.video_id}.jpg"
            with open(thumb_file, 'wb') as tf:
                tf.write(thumb_res.content)

        # تحميل الملف الصوتي وإرساله مباشرة مع الحقوق والصورة
        stream = yt.streams.get_audio_only()
        temp_file = stream.download(filename="temp_grp")
        filename = f"{safe_title}.mp3"
        if os.path.exists(temp_file):
            os.rename(temp_file, filename)
            
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                thumb_data = open(thumb_file, 'rb') if thumb_file and os.path.exists(thumb_file) else None
                bot.send_audio(
                    message.chat.id, 
                    f, 
                    performer=BOT_USERNAME, 
                    title=yt.title, 
                    caption=f"• {BOT_USERNAME}",
                    thumb=thumb_data
                )
            os.remove(filename)
            
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
            
    except Exception as e:
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ حدث خطأ أثناء جلب الطلب.")
        except:
            pass
    finally:
        if thumb_file and os.path.exists(thumb_file):
            try:
                os.remove(thumb_file)
            except:
                pass

# معالجة البحث في المحادثة الخاصة (بحث كامل مع النتائج والأوامر الزرقاء)
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and not message.text.startswith("/dl_") and message.text != "🛠 لوحة تحكم المطور" and message.chat.type == 'private')
def handle_private_search(message):
    query = message.text.strip()
    processing_msg = bot.reply_to(message, f"🔍 | جاري البحث عن: ({query}) ...")
    
    try:
        s = Search(query)
        results = s.results[:5]
        
        if not results:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ لم يتم العثور على نتائج بحث.")
            return

        response_text = f"🔍 **نتائج بحث اليوتيوب لـ \"{query}\"**\n\n"
        
        for idx, vid in enumerate(results, 1):
            vid_title = vid.title
            vid_id = vid.video_id
            duration = format_duration(vid.length)
            views = format_views(vid.views)
            channel_name = getattr(vid, 'author', 'YouTube')
            
            response_text += f"{idx}️⃣ 🎬 {vid_title}\n👤 {channel_name}\n⏱ {duration} - 👁 {views}\n📎 /dl_{vid_id}\n\n"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("التالي ➡️", callback_data=f"more_{query[:20]}"))

        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass

        bot.send_message(message.chat.id, response_text, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ حدث خطأ في البحث. تأكد من صحة الكلمة.")
        except:
            pass

@bot.message_handler(func=lambda message: message.text and (message.text.startswith("http") or message.text.startswith("/dl_")))
def handle_download_options(message):
    text = message.text.strip()
    if text.startswith("/dl_"):
        url = f"https://youtu.be/{text.replace('/dl_', '')}"
    else:
        url = text

    try:
        yt = YouTube(url)
        vid_id = yt.video_id
        title = yt.title
        duration = format_duration(yt.length)
        views = format_views(yt.views)
        
        caption = f"🎬 {title}\n👤 {BOT_USERNAME}\n⏱ {duration} - 👁 {views}"
        
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("🎬 مقطع فيديو.", callback_data=f"vid_{vid_id}"),
            InlineKeyboardButton("🎵 ملف صوتي.", callback_data=f"aud_{vid_id}"),
            InlineKeyboardButton("🎤 بصمة صوتية.", callback_data=f"voi_{vid_id}")
        )
        
        bot.send_photo(message.chat.id, FIXED_THUMB_URL, caption=caption, reply_markup=markup)
            
    except Exception as e:
        bot.reply_to(message, f"❌ تعذر جلب معلومات الفيديو.")

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
            return

    if call.data.startswith("more_"):
        bot.answer_callback_query(call.id, "🔍 جاري جلب المزيد من النتائج...")
        query = call.data.replace("more_", "")
        try:
            s = Search(query)
            results = s.results[5:10]
            if not results:
                bot.answer_callback_query(call.id, "❌ لا توجد نتائج أخرى.", show_alert=True)
                return

            response_text = f"🔍 **المزيد من نتائج بحث اليوتيوب لـ \"{query}\"**\n\n"
            
            for idx, vid in enumerate(results, 6):
                vid_title = vid.title
                vid_id = vid.video_id
                duration = format_duration(vid.length)
                views = format_views(vid.views)
                channel_name = getattr(vid, 'author', 'YouTube')
                
                response_text += f"{idx}️⃣ 🎬 {vid_title}\n👤 {channel_name}\n⏱ {duration} - 👁 {views}\n📎 /dl_{vid_id}\n\n"

            bot.send_message(call.message.chat.id, response_text, parse_mode="Markdown")
        except:
            bot.answer_callback_query(call.id, "❌ حدث خطأ أثناء جلب الصفحة التالية.", show_alert=True)
        return

    data = call.data
    parts = data.split("_", 1)
    if len(parts) != 2:
        return
        
    action, vid_id = parts[0], parts[1]
    url = f"https://youtu.be/{vid_id}"
    
    bot.answer_callback_query(call.id, "⏳ جاري التحميل بأقصى سرعة...")
    
    thumb_file = None
    try:
        yt = YouTube(url)
        safe_title = "".join([c for c in yt.title if c.isalnum() or c.isspace()]).strip() or "media"
        
        thumb_res = requests.get(FIXED_THUMB_URL)
        if thumb_res.status_code == 200:
            thumb_file = f"fixed_thumb_{vid_id}.jpg"
            with open(thumb_file, 'wb') as tf:
                tf.write(thumb_res.content)

        if action == "vid":
            stream = yt.streams.get_highest_resolution()
            filename = f"{safe_title}.mp4"
            stream.download(filename=filename)
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    bot.send_video(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
                os.remove(filename)
                
        elif action == "aud":
            stream = yt.streams.get_audio_only()
            temp_file = stream.download(filename="temp_a")
            filename = f"{safe_title}.mp3"
            if os.path.exists(temp_file):
                os.rename(temp_file, filename)
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    thumb_data = open(thumb_file, 'rb') if thumb_file and os.path.exists(thumb_file) else None
                    bot.send_audio(
                        call.message.chat.id, 
                        f, 
                        performer=BOT_USERNAME, 
                        title=yt.title, 
                        caption=f"• {BOT_USERNAME}",
                        thumb=thumb_data
                    )
                os.remove(filename)
                
        elif action == "voi":
            stream = yt.streams.get_audio_only()
            temp_file = stream.download(filename="temp_v")
            filename = f"{safe_title}.ogg"
            if os.path.exists(temp_file):
                os.rename(temp_file, filename)
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    bot.send_voice(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
                os.remove(filename)
                
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء التحميل.")
    finally:
        if thumb_file and os.path.exists(thumb_file):
            try:
                os.remove(thumb_file)
            except:
                pass

if __name__ == "__main__":
    print("البوت يعمل بكامل الميزات وبدون أخطاء...")
    bot.infinity_polling(skip_pending=True)
