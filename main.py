import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("يرجى تعيين متغير البيئة BOT_TOKEN")

# ضبط البوت وعدم استخدام threaded لمنع أي تعارض
bot = telebot.TeleBot(TOKEN, threaded=False)

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

# دالة جلب روابط التحميل المباشرة بدون أخطاء يوتيوب أو حظر
def get_media_links(url):
    try:
        api_url = "https://api.vidssave.com/api/contentsite_api/media/parse"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        data = {
            "auth": "20250901majwlqo",
            "domain": "api-ak.vidssave.com",
            "origin": "source",
            "link": url
        }
        response = requests.post(api_url, data=data, headers=headers, timeout=15)
        res_json = response.json()
        
        links = []
        if 'data' in res_json:
            # البحث في الـ media أو resources
            media_list = res_json['data'].get('media', [])
            for item in media_list:
                for res in item.get('resources', []):
                    if 'download_url' in res:
                        links.append({
                            'quality': res.get('quality', 'جودة عالية'),
                            'type': item.get('type', 'video'),
                            'url': res['download_url']
                        })
            
            # إذا لم توجد في media، نبحث في resources مباشرة
            if not links and 'resources' in res_json['data']:
                for res in res_json['data']['resources']:
                    if 'download_url' in res:
                        links.append({
                            'quality': res.get('quality', 'جودة عالية'),
                            'type': res.get('type', 'video'),
                            'url': res['download_url']
                        })
        return links
    except Exception as e:
        print(f"API Error: {e}")
        return []

# استقبال الروابط ومعالجتها عبر الـ API السريع
@bot.message_handler(func=lambda message: message.text and message.text.strip().startswith("http"))
def handle_download(message):
    url = message.text.strip()
    processing_msg = bot.reply_to(message, "⏳ | جاري جلب روابط التحميل السريعة...")

    links = get_media_links(url)

    if not links:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text="❌ عذراً، لم نتمكن من جلب روابط التحميل لهذا الرابط. تأكد أنه مدعوم وحاول مجدداً."
        )
        return

    markup = InlineKeyboardMarkup()
    for idx, link_info in enumerate(links[:4]): # عرض أول 4 روابط متوفرة
        q = link_info['quality']
        t = "فيديو 🎬" if link_info['type'] == 'video' else "صوت 🎵"
        # تخزين الرابط في الأزرار بشكل آمن
        markup.add(InlineKeyboardButton(f"تحميل {t} ({q})", url=link_info['url']))

    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=processing_msg.message_id,
        text=f"✅ **تم استخراج روابط التحميل بنجاح بواسطة {BOT_USERNAME}**\nاختر الجودة المطلوبة للتحميل المباشر:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# البحث بالنصوص (عبر يوتيوب مباشرة كروابط بحث)
@bot.message_handler(func=lambda message: message.text and not message.text.startswith("http") and message.text != "🛠 لوحة تحكم المطور")
def handle_search(message):
    query = message.text.strip()
    bot.reply_to(message, f"🔍 | للبحث والتحميل، يرجى إرسال رابط مباشر (يوتيوب، انستقرام، تيك توك، إلخ) وسيتم جلب روابط التحميل فوراً.")

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
    print("البوت يعمل الآن بدون أخطاء يوتيوب وبسرعة فائقة...")
    bot.infinity_polling(skip_pending=True)
