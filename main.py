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

# --- 1. إعداد السيرفر لضمان استقرار Render ---
app = Flask('')
@app.route('/')
def home(): 
    return "<h1>Al-Ahram Bot is Live</h1>"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. الإعدادات والاتصال بقاعدة البيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)

try:
    # استخدام certifi لحل مشاكل الـ SSL في ليبيا وسيرفرات Render
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['AlAhram_DB']
    users_col = db['users']
    cards_col = db['topup_cards']
    stock_col = db['stock']
    logs_col = db['logs']
    print("✅ Connected to MongoDB")
except Exception as e:
    print(f"❌ DB Error: {e}")

# --- 3. الوظائف المساعدة ---
def is_safe(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        bot.send_message(uid, f"⚠️ **{user.get('freeze_reason', 'الحساب مجمد')}**")
        return False
    return True

def main_menu():
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
        markup.add(types.KeyboardButton("📱 تفعيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام\nيرجى تسجيل حسابك أولاً:", reply_markup=markup)
    else:
        bot.send_message(uid, f"مرحباً بك مجدداً!\nرصيدك الحالي: {user.get('balance', 0)} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def register(message):
    if message.contact:
        new_user = {
            "_id": message.chat.id,
            "phone": message.contact.phone_number,
            "balance": 0,
            "status": "active",
            "failed_attempts": 0,
            "join_date": datetime.datetime.now()
        }
        users_col.update_one({"_id": message.chat.id}, {"$set": new_user}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم التسجيل بنجاح!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def tech_support(message):
    bot.send_message(message.chat.id, "📞 **الدعم الفني المباشر:**\n\nللتواصل مع الإدارة: @AlAhram_Support\nمتاحون لخدمتكم 24/7.")

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account_info(message):
    if not is_safe(message.chat.id): return
    user = users_col.find_one({"_id": message.chat.id})
    
    # حساب الإحصائيات
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    
    purchases = list(logs_col.find({"uid": message.chat.id, "type": "buy"}))
    spent_today = sum(p['price'] for p in purchases if p['date'] >= today_start)
    spent_month = sum(p['price'] for p in purchases if p['date'] >= month_start)

    msg = (f"👤 **معلومات حسابك:**\n"
           f"━━━━━━━━━━━━━━━\n"
           f"📱 الرقم: `{user['phone']}`\n"
           f"💰 الرصيد: {user['balance']} د.ل\n"
           f"📊 **الإنفاق:**\n"
           f"▫️ اليوم: {spent_today} د.ل\n"
           f"▫️ الشهر: {spent_month} د.ل")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- 5. نظام الشراء والحماية ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop_menu(message):
    if not is_safe(message.chat.id): return
    products = list(stock_col.find({"sold": False}))
    if not products:
        bot.send_message(message.chat.id, "⚠️ عذراً، لا توجد أكواد متوفرة حالياً.")
        return
    
    markup = types.InlineKeyboardMarkup()
    seen_names = set()
    for p in products:
        if p['name'] not in seen_names:
            markup.add(types.InlineKeyboardButton(f"{p['name']} ({p['price']} د.ل)", callback_data=f"buy_{p['name']}"))
            seen_names.add(p['name'])
    bot.send_message(message.chat.id, "اختر المنتج الذي ترغب بشرائه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    product = stock_col.find_one({"name": p_name, "sold": False})
    
    if user['balance'] < product['price']:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ!", show_alert=True)
        return

    stock_col.update_one({"_id": product['_id']}, {"$set": {"sold": True, "sold_to": uid, "date": datetime.datetime.now()}})
    users_col.update_one({"_id": uid}, {"$inc": {"balance": -product['price']}})
    logs_col.insert_one({"uid": uid, "type": "buy", "price": product['price'], "date": datetime.datetime.now()})
    
    bot.send_message(uid, f"✅ تم الشراء!\nمنتج: {p_name}\nالكود: `{product['code']}`", parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def start_charge(message):
    if not is_safe(message.chat.id): return
    msg = bot.send_message(message.chat.id, "🔢 يرجى إرسال كود الكرت للشحن:")
    bot.register_next_step_handler(msg, process_charge)

def process_charge(message):
    uid = message.chat.id
    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}, "$set": {"failed_attempts": 0}})
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "user": uid}})
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل بنجاح!")
    else:
        new_fails = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": new_fails}})
        if new_fails >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك بسبب المحاولة في تخريب النظام"}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب المحاولة في تخريب النظام.")
        else:
            bot.send_message(uid, f"❌ الكود خاطئ! تبقى لك {3 - new_fails} محاولات قبل التجميد.")

# --- 6. لوحة الإدارة ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👥 إدارة المشتركين", callback_data="adm_list"))
    markup.add(types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen"))
    bot.send_message(ADMIN_ID, "🛠 لوحة إدارة الأهرام:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_list")
def list_users(call):
    users = list(users_col.find())
    text = "👥 **المشتركين:**\n"
    markup = types.InlineKeyboardMarkup()
    for u in users:
        icon = "✅" if u.get('status') == 'active' else "❄️"
        text += f"{icon} {u['phone']} | {u['balance']} د.ل\n"
        markup.add(types.InlineKeyboardButton(f"التحكم: {u['phone']}", callback_data=f"ctrl_{u['_id']}"))
    bot.send_message(ADMIN_ID, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ctrl_"))
def ctrl_user(call):
    uid = int(call.data.split("_")[1])
    user = users_col.find_one({"_id": uid})
    markup = types.InlineKeyboardMarkup()
    if user['status'] == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد", callback_data=f"frez_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل", callback_data=f"unfz_{uid}"))
    bot.send_message(ADMIN_ID, f"إدارة: {user['phone']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("unfz_"))
def unfreeze(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
    bot.answer_callback_query(call.id, "✅ تم التفعيل")
    bot.send_message(uid, "✅ تم إلغاء تجميد حسابك.")

# --- تشغيل البوت ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.remove_webhook()
    print("🚀 البوت يعمل الآن...")
    bot.infinity_polling(skip_pending=True)
