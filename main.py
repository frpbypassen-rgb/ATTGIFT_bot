import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
import certifi
from flask import Flask
from threading import Thread

# --- إعدادات السيرفر (Render Port Binding) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- إعدادات البوت والبيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)
# استخدام certifi لتجنب أخطاء SSL Handshake على Render
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- وظائف الحماية والتحقق ---
def check_status(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'مخالفة الشروط')
        bot.send_message(uid, f"⚠️ حسابك مجمد حالياً!\n📌 السبب: {reason}\n📞 تواصل مع الدعم للفك.")
        return False
    return True

def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- أوامر المستخدم ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات\nيرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        if not check_status(uid): return
        bot.send_message(uid, "أهلاً بك في القائمة الرئيسية", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact:
        user_data = {
            "_id": message.chat.id, 
            "phone": message.contact.phone_number, 
            "balance": 0, 
            "status": "active",
            "join_date": datetime.datetime.now()
        }
        users_col.update_one({"_id": message.chat.id}, {"$set": user_data}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم تفعيل حسابك!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    uid = message.chat.id
    if not check_status(uid): return
    user = users_col.find_one({"_id": uid})
    
    # حساب الإحصائيات المالية
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    today_spent = sum(log['amt'] for log in logs_col.find({"uid": uid, "type": "purchase", "date": {"$gte": today_start}}))
    month_spent = sum(log['amt'] for log in logs_col.find({"uid": uid, "type": "purchase", "date": {"$gte": month_start}}))
    
    text = (f"👤 **تفاصيل حسابك:**\n\n"
            f"📱 الرقم: `{user['phone']}`\n"
            f"💰 الرصيد الحالي: {user['balance']} د.ل\n"
            f"📅 انضممت في: {user['join_date'].strftime('%Y-%m-%d')}\n\n"
            f"📊 **إحصائيات الإنفاق:**\n"
            f"▫️ صرف اليوم: {abs(today_spent)} د.ل\n"
            f"▫️ صرف الشهر: {abs(month_spent)} د.ل")
    bot.send_message(uid, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge_request(message):
    if not check_status(message.chat.id): return
    msg = bot.send_message(message.chat.id, "أرسل كود الكرت المكون من 12 رمزاً:")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(message):
    code = message.text.strip()
    card = cards_col.find_one({"code": code, "used": False})
    if card:
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True}})
        users_col.update_one({"_id": message.chat.id}, {"$inc": {"balance": card['val']}})
        logs_col.insert_one({"uid": message.chat.id, "type": "charge", "amt": card['val'], "date": datetime.datetime.now()})
        bot.send_message(message.chat.id, f"✅ تم شحن {card['val']} د.ل بنجاح!")
    else:
        bot.send_message(message.chat.id, "❌ الكود خاطئ أو تم استخدامه مسبقاً.")

# --- لوحة الإدارة (ADMIN) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ إضافة بضاعة", callback_data="adm_add_stock"),
        types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen_cards"),
        types.InlineKeyboardButton("👥 إدارة المشتركين", callback_data="adm_list_users"),
        types.InlineKeyboardButton("💰 شحن رصيد لعميل", callback_data="adm_charge_user")
    )
    bot.send_message(ADMIN_ID, "🛠 لوحة إدارة الأهرام:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_list_users")
def list_users(call):
    users = users_col.find().limit(15)
    text = "👥 **قائمة المشتركين وأرصدتهم:**\n\n"
    markup = types.InlineKeyboardMarkup()
    for u in users:
        icon = "✅" if u.get('status') == 'active' else "❄️"
        text += f"{icon} `{u['phone']}` -> {u['balance']} د.ل\n"
        markup.add(types.InlineKeyboardButton(f"إدارة {u['phone']}", callback_data=f"manage_{u['_id']}"))
    bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_"))
def manage_user_options(call):
    uid = int(call.data.split("_")[1])
    user = users_col.find_one({"_id": uid})
    markup = types.InlineKeyboardMarkup()
    if user.get('status') == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"freeze_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ إلغاء التجميد", callback_data=f"unfreeze_{uid}"))
    bot.send_message(ADMIN_ID, f"إدارة حساب: {user['phone']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freeze_"))
def freeze_step1(call):
    uid = call.data.split("_")[1]
    msg = bot.send_message(ADMIN_ID, "أرسل سبب التجميد ليظهر للمستخدم:")
    bot.register_next_step_handler(msg, lambda m: execute_freeze(m, uid))

def execute_freeze(message, uid):
    users_col.update_one({"_id": int(uid)}, {"$set": {"status": "frozen", "freeze_reason": message.text}})
    bot.send_message(ADMIN_ID, "✅ تم التجميد بنجاح.")
    bot.send_message(int(uid), f"⚠️ تم تجميد حسابك.\nالسبب: {message.text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("unfreeze_"))
def execute_unfreeze(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active", "freeze_reason": ""}})
    bot.send_message(ADMIN_ID, "✅ تم إلغاء التجميد.")
    bot.send_message(uid, "✅ تم تفعيل حسابك مجدداً.")

@bot.callback_query_handler(func=lambda call: call.data == "adm_charge_user")
def admin_charge_prompt(call):
    msg = bot.send_message(ADMIN_ID, "أرسل (رقم الهاتف : القيمة)\nمثال: 0910000000 : 50")
    bot.register_next_step_handler(msg, process_admin_charge)

def process_admin_charge(message):
    try:
        phone, val = message.text.split(":")
        user = users_col.find_one({"phone": phone.strip()})
        if user:
            users_col.update_one({"_id": user['_id']}, {"$inc": {"balance": int(val.strip())}})
            bot.send_message(ADMIN_ID, f"✅ تم شحن {val} د.ل للرقم {phone}")
            bot.send_message(user['_id'], f"✅ تم إضافة {val} د.ل لرصيدك من قبل الإدارة.")
        else:
            bot.send_message(ADMIN_ID, "❌ الرقم غير مسجل في البوت.")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

# --- توليد كروت وفئات ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_gen_cards")
def gen_cards_prompt(call):
    msg = bot.send_message(ADMIN_ID, "أرسل (الفئة : العدد)\nمثال: 20 : 10")
    bot.register_next_step_handler(msg, process_card_gen)

def process_card_gen(message):
    try:
        f_val, count = map(int, message.text.split(":"))
        generated = []
        for _ in range(count):
            code = "AHRAM-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            cards_col.insert_one({"code": code, "val": f_val, "used": False})
            generated.append(f"`{code}`")
        bot.send_message(ADMIN_ID, f"✅ تم توليد {count} كرت فئة {f_val}:\n\n" + "\n".join(generated), parse_mode="Markdown")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

# --- تشغيل البوت مع حل مشكلة التعارض ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.delete_webhook() # تنظيف أي Webhook سابق لتجنب خطأ 409
    bot.infinity_polling(skip_pending=True)
