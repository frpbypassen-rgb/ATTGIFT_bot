import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
from flask import Flask
from threading import Thread

# --- 1. إعداد السيرفر الوهمي لإرضاء Render ---
app = Flask('')

@app.route('/')
def home():
    return "البوت يعمل بنجاح!"

def run_flask():
    # سيقوم Render بتوفير البورت تلقائياً عبر متغيرات البيئة
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. الإعدادات والربط ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
# الرابط المعدل مع خيار تجاوز شهادة SSL لضمان الاتصال
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT&tlsAllowInvalidCertificates=true"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI)
db = client['StoreDB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']

# --- 3. لوحات المفاتيح ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد", "👤 حسابي", "📢 الدعم الفني")
    return markup

# --- 4. أوامر المستخدم ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "مرحباً بك في متجر ATTGIFT! يرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك: {user['balance']} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if message.contact:
        user_data = {"_id": uid, "phone": message.contact.phone_number, "balance": 0, "date": str(datetime.datetime.now())}
        users_col.update_one({"_id": uid}, {"$set": user_data}, upsert=True)
        bot.send_message(uid, "✅ تم التسجيل سحابياً بنجاح!", reply_markup=main_menu())

# --- 5. نظام الشحن والشراء ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def recharge(message):
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن:")
    bot.register_next_step_handler(msg, do_recharge)

def do_recharge(message):
    code = message.text.strip()
    card = cards_col.find_one_and_delete({"code": code})
    if card:
        users_col.update_one({"_id": message.chat.id}, {"$inc": {"balance": card['value']}})
        bot.send_message(message.chat.id, f"✅ تم شحن {card['value']} د.ل")
    else:
        bot.send_message(message.chat.id, "❌ كود خاطئ.")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    products = stock_col.distinct("name")
    if not products: return bot.send_message(message.chat.id, "المخزن فارغ.")
    markup = types.InlineKeyboardMarkup()
    for p in products:
        item = stock_col.find_one({"name": p})
        markup.add(types.InlineKeyboardButton(f"{p} ({item['price']} د.ل)", callback_data=f"buy_{p}"))
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name})
    if item and user['balance'] >= item['price']:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        bot.send_message(uid, f"✅ تم الشراء!\nكودك: `{item['secret']}`", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ رصيد غير كافٍ", show_alert=True)

# --- 6. لوحة الإدارة ---
@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة", callback_data="add_stock"))
    markup.add(types.InlineKeyboardButton("🎫 توليد كرت شحن", callback_data="gen_topup"))
    bot.send_message(ADMIN_ID, "🛠 لوحة الإدارة السحابية:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["add_stock", "gen_topup"])
def admin_actions(call):
    if call.data == "gen_topup":
        code = "GIFT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        cards_col.insert_one({"code": code, "value": 10})
        bot.send_message(ADMIN_ID, f"🎫 كود جديد (10 د.ل):\n`{code}`", parse_mode="Markdown")
    elif call.data == "add_stock":
        msg = bot.send_message(ADMIN_ID, "أرسل (الاسم : السعر : الكود)")
        bot.register_next_step_handler(msg, save_stock)

def save_stock(message):
    try:
        n, p, s = [i.strip() for i in message.text.split(":")]
        stock_col.insert_one({"name": n, "price": int(p), "secret": s})
        bot.send_message(ADMIN_ID, "✅ تمت الإضافة")
    except: bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق")

# --- 7. تشغيل كل شيء معاً ---
if __name__ == "__main__":
    # تشغيل Flask في خيط (Thread) منفصل
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    print("--- البوت الآن متصل بقاعدة بيانات MongoDB وهو يعمل ---")
    bot.infinity_polling()
