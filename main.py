import telebot
from telebot import types
from pymongo import MongoClient
import datetime
import os
import certifi
import random
import string
from flask import Flask
from threading import Thread

# --- 1. إعداد السيرفر (حل مشكلة توقف Render) ---
app = Flask('')
@app.route('/')
def home(): return "<h1>Al-Ahram System is Online</h1>"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. الإعدادات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- 3. الدوال المساعدة ---
def is_account_safe(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        bot.send_message(uid, f"⚠️ **{user.get('freeze_reason', 'تم تجميد حسابك بموجب سياسة الاستخدام')}**")
        return False
    return True

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- 4. أوامر المستخدم ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام\nيرجى الضغط على الزر لتسجيل حسابك:", reply_markup=markup)
    else:
        bot.send_message(uid, "أهلاً بك في القائمة الرئيسية", reply_markup=get_main_keyboard())

@bot.message_handler(content_types=['contact'])
def on_register(message):
    if message.contact:
        users_col.update_one({"_id": message.chat.id}, {"$set": {
            "phone": message.contact.phone_number,
            "balance": 0,
            "status": "active",
            "failed_attempts": 0,
            "join_date": datetime.datetime.now()
        }}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم تفعيل حسابك بنجاح!", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support_info(message):
    bot.send_message(message.chat.id, "📞 **الدعم الفني المباشر:**\n\nللتواصل: @AlAhram_Support\nنحن هنا لمساعدتك دائماً.")

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    if not is_account_safe(message.chat.id): return
    u = users_col.find_one({"_id": message.chat.id})
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    
    # جلب تقارير الإنفاق
    purchases = list(logs_col.find({"uid": u['_id'], "type": "buy"}))
    spent_today = sum(p['price'] for p in purchases if p['date'] >= today_start)
    spent_month = sum(p['price'] for p in purchases if p['date'] >= month_start)

    text = (f"👤 **بيانات حسابك:**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📱 الهاتف: `{u['phone']}`\n"
            f"💰 الرصيد: {u.get('balance', 0)} د.ل\n"
            f"📅 انضممت في: {u['join_date'].strftime('%Y-%m-%d')}\n\n"
            f"📊 **تقارير الإنفاق:**\n"
            f"▫️ صرف اليوم: {spent_today} د.ل\n"
            f"▫️ صرف الشهر: {spent_month} د.ل")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 5. الشراء والشحن والحماية ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    if not is_account_safe(message.chat.id): return
    items = list(stock_col.find({"sold": False}))
    if not items:
        return bot.send_message(message.chat.id, "⚠️ لا توجد بضاعة متوفرة حالياً.")
    
    markup = types.InlineKeyboardMarkup()
    names_added = set()
    for item in items:
        if item['name'] not in names_added:
            markup.add(types.InlineKeyboardButton(f"{item['name']} - {item['price']} د.ل", callback_data=f"buy_{item['name']}"))
            names_added.add(item['name'])
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def on_buy_click(call):
    name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": name, "sold": False})

    if user['balance'] < item['price']:
        bot.answer_callback_query(call.id, "❌ رصيدك لا يكفي!", show_alert=True)
    else:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": True, "buyer": uid, "date": datetime.datetime.now()}})
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        logs_col.insert_one({"uid": uid, "type": "buy", "price": item['price'], "date": datetime.datetime.now()})
        bot.send_message(uid, f"✅ تم الشراء!\nمنتجك: {name}\nالكود: `{item['code']}`", parse_mode="Markdown")
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge_init(message):
    if not is_account_safe(message.chat.id): return
    msg = bot.send_message(message.chat.id, "🔢 أرسل كود الكرت الآن:")
    bot.register_next_step_handler(msg, validate_card)

def validate_card(message):
    uid = message.chat.id
    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}, "$set": {"failed_attempts": 0}})
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "by": uid}})
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل بنجاح!")
    else:
        fails = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": fails}})
        if fails >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك بسبب المحاولة في تخريب النظام"}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب المحاولة في تخريب النظام.")
        else:
            bot.send_message(uid, f"❌ كود خاطئ! تبقى لك {3 - fails} محاولات.")

# --- 6. لوحة الإدارة الكاملة ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ إضافة بضاعة", callback_data="adm_add"),
        types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen"),
        types.InlineKeyboardButton("👥 إدارة المشتركين", callback_data="adm_users")
    )
    bot.send_message(ADMIN_ID, "🛠 لوحة إدارة الأهرام:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_actions(call):
    if call.data == "adm_users":
        users = list(users_col.find())
        text = "👥 **قائمة المشتركين:**\n"
        markup = types.InlineKeyboardMarkup()
        for u in users:
            status = "✅" if u.get('status') == 'active' else "❄️"
            text += f"{status} {u['phone']} | {u.get('balance', 0)} د.ل\n"
            markup.add(types.InlineKeyboardButton(f"إدارة {u['phone']}", callback_data=f"edit_{u['_id']}"))
        bot.send_message(ADMIN_ID, text, reply_markup=markup)
    
    elif call.data == "adm_gen":
        msg = bot.send_message(ADMIN_ID, "أرسل (الفئة:العدد) مثال: 20:10")
        bot.register_next_step_handler(msg, do_gen_cards)

    elif call.data == "adm_add":
        msg = bot.send_message(ADMIN_ID, "أرسل (الاسم:السعر:الكود) مثال: Snapchat:15:XXXX-XXXX")
        bot.register_next_step_handler(msg, do_add_stock)

def do_gen_cards(message):
    try:
        val, count = map(int, message.text.split(":"))
        for _ in range(count):
            code = "AHR-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            cards_col.insert_one({"code": code, "val": val, "used": False})
        bot.send_message(ADMIN_ID, f"✅ تم توليد {count} كرت فئة {val}")
    except: bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق")

def do_add_stock(message):
    try:
        name, price, code = message.text.split(":")
        stock_col.insert_one({"name": name, "price": int(price), "code": code, "sold": False})
        bot.send_message(ADMIN_ID, f"✅ تم إضافة منتج {name}")
    except: bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def user_edit_menu(call):
    uid = int(call.data.split("_")[1])
    u = users_col.find_one({"_id": uid})
    markup = types.InlineKeyboardMarkup()
    if u.get('status') == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد", callback_data=f"frz_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل", callback_data=f"thw_{uid}"))
    bot.send_message(ADMIN_ID, f"التحكم في: {u['phone']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("frz_") or call.data.startswith("thw_"))
def toggle_user(call):
    action, uid = call.data.split("_")
    new_status = "frozen" if action == "frz" else "active"
    users_col.update_one({"_id": int(uid)}, {"$set": {"status": new_status, "failed_attempts": 0}})
    bot.answer_callback_query(call.id, f"تم التغيير إلى {new_status}")
    bot.send_message(int(uid), "🔔 تم تحديث حالة حسابك من قبل الإدارة.")

# --- 7. تشغيل البوت النهائي ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.remove_webhook()
    print("🚀 System is fully operational...")
    bot.infinity_polling(skip_pending=True)
