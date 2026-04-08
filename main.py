import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
from flask import Flask
from threading import Thread

# --- 1. سيرفر الاستقرار ---
app = Flask('')
@app.route('/')
def home(): return "Bot Status: Online"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- 2. البيانات والربط ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT&tlsAllowInvalidCertificates=true"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "+2189XXXXXXXX" # ضع رقمك هنا

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI)
db = client['StoreDB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
sales_col = db['sales'] # مجموعة جديدة لحفظ المبيعات

# --- 3. القوائم ---
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
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات\nيرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {user['balance']} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if message.contact:
        phone = message.contact.phone_number
        user_data = {"_id": uid, "phone": phone, "balance": 0, "join_date": datetime.datetime.now().strftime("%Y-%m-%d")}
        users_col.update_one({"_id": uid}, {"$set": user_data}, upsert=True)
        bot.send_message(uid, "✅ تم تفعيل حسابك بنجاح!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    user = users_col.find_one({"_id": message.chat.id})
    if user:
        text = (f"👤 **معلومات حسابك:**\n\n"
                f"📱 الرقم: `{user['phone']}`\n"
                f"💰 الرصيد: {user['balance']} د.ل\n"
                f"📅 تاريخ الانضمام: {user['join_date']}")
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 مراسلة الدعم", url=f"https://wa.me/{SUPPORT_NUMBER}"))
    bot.send_message(message.chat.id, "يمكنك التواصل معنا عبر الواتساب مباشرة:", reply_markup=markup)

# --- 5. الشحن والشراء ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def recharge(message):
    msg = bot.send_message(message.chat.id, "📩 قم بإرسال كود الشحن هنا:")
    bot.register_next_step_handler(msg, do_recharge)

def do_recharge(message):
    code = message.text.strip()
    card = cards_col.find_one_and_delete({"code": code})
    if card:
        users_col.update_one({"_id": message.chat.id}, {"$inc": {"balance": card['value']}})
        bot.send_message(message.chat.id, f"✅ تم شحن {card['value']} د.ل بنجاح!")
    else:
        bot.send_message(message.chat.id, "❌ كود الشحن غير صحيح أو مستخدم.")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    products = stock_col.distinct("name")
    if not products: return bot.send_message(message.chat.id, "المخزن فارغ حالياً.")
    markup = types.InlineKeyboardMarkup()
    for p in products:
        item = stock_col.find_one({"name": p})
        markup.add(types.InlineKeyboardButton(f"{p} - {item['price']} د.ل", callback_data=f"buy_{p}"))
    bot.send_message(message.chat.id, "اختر المنتج الذي تريده:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name})
    
    if item and user['balance'] >= item['price']:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        # تسجيل العملية
        sales_col.insert_one({"user_id": uid, "phone": user['phone'], "item": p_name, "price": item['price'], "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
        bot.send_message(uid, f"✅ تم الشراء بنجاح!\nكودك هو: `{item['secret']}`", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ أو نفذت الكمية", show_alert=True)

# --- 6. لوحة الإدارة المتطورة ---
@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة", callback_data="add_stock"),
               types.InlineKeyboardButton("🎫 توليد كروت", callback_data="gen_menu"))
    markup.add(types.InlineKeyboardButton("📊 إحصائيات المستخدمين", callback_data="view_stats"))
    markup.add(types.InlineKeyboardButton("🧾 سجل المبيعات", callback_data="view_sales"))
    bot.send_message(ADMIN_ID, "🛠 لوحة التحكم الاحترافية:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["gen_menu", "view_stats", "view_sales", "add_stock"])
def admin_actions(call):
    if call.data == "gen_menu":
        markup = types.InlineKeyboardMarkup()
        for v in [5, 10, 20, 50]: markup.add(types.InlineKeyboardButton(f"فئة {v} دينار", callback_data=f"gv_{v}"))
        bot.edit_message_text("اختر الفئة التي تريد توليدها:", ADMIN_ID, call.message.message_id, reply_markup=markup)
    
    elif call.data == "view_stats":
        users = users_col.find()
        text = f"📊 **إحصائيات المشتركين:**\n\n"
        for u in users:
            text += f"📱 `{u['phone']}` | 💰 {u['balance']} د.ل\n"
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        
    elif call.data == "view_sales":
        sales = sales_col.find().limit(20) # آخر 20 عملية
        text = "🧾 **آخر عمليات الشراء:**\n\n"
        for s in sales:
            text += f"👤 {s['phone']} اشترى {s['item']} بـ {s['price']}د.ل\n📅 {s['date']}\n---\n"
        bot.send_message(ADMIN_ID, text)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gv_"))
def finalize_gen(call):
    val = int(call.data.split("_")[1])
    code = "GIFT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    cards_col.insert_one({"code": code, "value": val})
    bot.send_message(ADMIN_ID, f"🎫 تم توليد كرت فئة {val} دينار:\n`{code}`", parse_mode="Markdown")

# --- 7. تشغيل ---
if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    bot.infinity_polling()
