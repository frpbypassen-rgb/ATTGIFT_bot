import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
from flask import Flask
from threading import Thread

# --- إعدادات السيرفر للاستقرار على Render ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- إعدادات البوت وقاعدة البيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT&tlsAllowInvalidCertificates=true"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "218913731533" 

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI)
db = client['StoreDB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
sales_col = db['sales']

# --- القوائم الرئيسية ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد", "🏦 شحن مباشر")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- الأوامر الأساسية ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 مشاركة جهة الاتصال للتسجيل", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات\nيرجى تسجيل حسابك أولاً:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك: {user['balance']} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact:
        user_data = {"_id": message.chat.id, "phone": message.contact.phone_number, "balance": 0, "join_date": datetime.datetime.now().strftime("%Y-%m-%d")}
        users_col.update_one({"_id": message.chat.id}, {"$set": user_data}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم التسجيل بنجاح!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 مراسلة الدعم (واتساب)", url=f"https://wa.me/{SUPPORT_NUMBER}"))
    bot.send_message(message.chat.id, "يمكنك التواصل معنا مباشرة عبر الرابط التالي:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    user = users_col.find_one({"_id": message.chat.id})
    if user:
        text = f"👤 **معلومات الحساب:**\n📱 الرقم: `{user['phone']}`\n💰 الرصيد: {user['balance']} د.ل"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- نظام الشحن المباشر ---
@bot.message_handler(func=lambda m: m.text == "🏦 شحن مباشر")
def direct_charge_req(message):
    msg = bot.send_message(message.chat.id, "أرسل (رقم حسابك : المبلغ)\nمثال: 12345 : 50")
    bot.register_next_step_handler(msg, send_to_admin)

def send_to_admin(message):
    try:
        acc, amount = message.text.split(":")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تأكيد الإضافة", callback_data=f"confirm_{message.chat.id}_{amount.strip()}"))
        bot.send_message(ADMIN_ID, f"⚠️ طلب شحن جديد:\nالمستخدم: {message.chat.id}\nالحساب: {acc}\nالمبلغ: {amount} د.ل", reply_markup=markup)
        bot.send_message(message.chat.id, "✅ تم إرسال طلبك. سيتم شحن محفظتك فور التأكد.")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في التنسيق. استخدم (الحساب : المبلغ)")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
def confirm_charge(call):
    _, uid, amt = call.data.split("_")
    users_col.update_one({"_id": int(uid)}, {"$inc": {"balance": int(amt)}})
    bot.send_message(int(uid), f"✅ تم شحن محفظتك بـ {amt} د.ل بنجاح!")
    bot.edit_message_text(f"✅ تم تأكيد الشحن لـ {uid}", ADMIN_ID, call.message.message_id)

# --- لوحة الإدارة (إضافة بضاعة متعددة) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة متعددة", callback_data="add_multi"))
        bot.send_message(ADMIN_ID, "🛠 لوحة الإدارة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_multi")
def prompt_multi(call):
    msg = bot.send_message(ADMIN_ID, "أرسل البيانات هكذا:\n(الاسم : السعر : كود1, كود2, كود3)")
    bot.register_next_step_handler(msg, save_multi_stock)

def save_multi_stock(message):
    try:
        name, price, codes_raw = message.text.split(":")
        codes = [c.strip() for c in codes_raw.replace("\n", ",").split(",")]
        for c in codes:
            if c: stock_col.insert_one({"name": name.strip(), "price": int(price.strip()), "secret": c})
        bot.send_message(ADMIN_ID, f"✅ تم إضافة {len(codes)} كود لمنتج {name} بنجاح!")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

# --- نظام الشراء ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    products = stock_col.distinct("name")
    if not products: return bot.send_message(message.chat.id, "المخزن فارغ حالياً.")
    markup = types.InlineKeyboardMarkup()
    for p in products:
        item = stock_col.find_one({"name": p})
        markup.add(types.InlineKeyboardButton(f"{p} ({item['price']} د.ل)", callback_data=f"buy_{p}"))
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    p_name = call.data.split("_")[1]
    user = users_col.find_one({"_id": call.message.chat.id})
    item = stock_col.find_one({"name": p_name})
    if item and user['balance'] >= item['price']:
        users_col.update_one({"_id": user['_id']}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        bot.send_message(user['_id'], f"✅ تم الشراء!\nكودك: `{item['secret']}`", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ رصيد غير كافٍ أو نفذت الكمية", show_alert=True)

# --- تشغيل البوت ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
