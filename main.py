import telebot
from telebot import types
from pymongo import MongoClient
import datetime
import os
import certifi
from flask import Flask
from threading import Thread

# 1. إعداد السيرفر ليرضي منصة Render فوراً
app = Flask('')
@app.route('/')
def home(): return "<h1>Al-Ahram Bot is Running Successfully</h1>"

def run_flask():
    # Render يتطلب الربط بالبورت المخصص له
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# 2. إعدادات الوصول
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

# 3. نظام الحماية والتجميد
def is_safe(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        bot.send_message(uid, f"❄️ **{user.get('freeze_reason', 'الحساب مجمد')}**")
        return False
    return True

# 4. الأزرار الرئيسية
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب", request_contact=True))
        bot.send_message(uid, "مرحباً بك في شركة الأهرام.\nيرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك: {user.get('balance', 0)} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_reg(message):
    if message.contact:
        users_col.update_one({"_id": message.chat.id}, {"$set": {
            "phone": message.contact.phone_number,
            "balance": 0,
            "status": "active",
            "failed_attempts": 0,
            "join_date": datetime.datetime.now()
        }}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم تفعيل حسابك!", reply_markup=main_menu())

# 5. تفعيل "حسابي" مع التقارير
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    if not is_safe(message.chat.id): return
    u = users_col.find_one({"_id": message.chat.id})
    
    # حساب تقارير العمليات
    today = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    month = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0)
    
    today_spent = sum(l['price'] for l in logs_col.find({"uid": u['_id'], "type": "buy", "date": {"$gte": today}}))
    month_spent = sum(l['price'] for l in logs_col.find({"uid": u['_id'], "type": "buy", "date": {"$gte": month}}))

    text = (f"👤 **بيانات الحساب:**\n"
            f"📱 الرقم: `{u['phone']}`\n"
            f"💰 الرصيد: {u['balance']} د.ل\n"
            f"📅 الانضمام: {u['join_date'].strftime('%Y-%m-%d')}\n\n"
            f"📊 **تقارير الصرف:**\n"
            f"▫️ صرف اليوم: {today_spent} د.ل\n"
            f"▫️ صرف الشهر: {month_spent} د.ل")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# 6. تفعيل "شراء كود"
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    if not is_safe(message.chat.id): return
    items = list(stock_col.find({"sold": False}))
    if not items:
        return bot.send_message(message.chat.id, "⚠️ لا توجد منتجات حالياً.")
    
    markup = types.InlineKeyboardMarkup()
    for item in items:
        markup.add(types.InlineKeyboardButton(f"{item['name']} - {item['price']} د.ل", callback_data=f"buy_{item['_id']}"))
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    item_id = call.data.split("_")[1]
    # منطق الشراء والخصم هنا...
    bot.answer_callback_query(call.id, "جاري المعالجة...")

# 7. نظام الحماية (3 محاولات خاطئة)
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge_init(message):
    if not is_safe(message.chat.id): return
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن:")
    bot.register_next_step_handler(msg, validate_charge)

def validate_charge(message):
    uid = message.chat.id
    code = message.text.strip()
    card = cards_col.find_one({"code": code, "used": False})
    user = users_col.find_one({"_id": uid})

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}, "$set": {"failed_attempts": 0}})
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "by": uid}})
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل")
    else:
        new_fails = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": new_fails}})
        if new_fails >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك بسبب المحاولة في تخريب النظام"}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب المحاولة في تخريب النظام.")
        else:
            bot.send_message(uid, f"❌ كود خاطئ! تبقى لك {3 - new_fails} محاولات.")

# 8. الدعم الفني
@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    bot.send_message(message.chat.id, "🛠 الدعم الفني لشركة الأهرام:\n@AlAhram_Support\nمتاحون على مدار الساعة.")

# --- التشغيل السليم ---
if __name__ == "__main__":
    # تشغيل Flask أولاً في خلفية منفصلة لإرضاء Render
    server_thread = Thread(target=run_flask)
    server_thread.start()
    
    # تنظيف الجلسات وحل مشكلة 409
    bot.remove_webhook()
    print("🚀 Bot is starting...")
    bot.infinity_polling(skip_pending=True)
