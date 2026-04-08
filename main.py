import telebot
from telebot import types
from pymongo import MongoClient
import datetime
import os
import certifi
from flask import Flask
from threading import Thread

# --- Flask Keep Alive ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running ✅"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- ENV (أمان) ---
API_TOKEN = os.environ.get("API_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SUPPORT_NUMBER = "+218913731533"

bot = telebot.TeleBot(API_TOKEN)

# --- Mongo ---
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']

users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- Anti Spam ---
last_action = {}

def is_spam(uid):
    now = datetime.datetime.now()
    if uid in last_action:
        diff = (now - last_action[uid]).seconds
        if diff < 2:
            return True
    last_action[uid] = now
    return False

# --- Security ---
def is_account_active(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'تم تجميد حسابك')
        bot.send_message(uid, f"⚠️ {reason}\n📞 {SUPPORT_NUMBER}")
        return False
    return True

# --- Menu ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- Start ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id

    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل", request_contact=True))
        bot.send_message(uid, "📌 سجل رقمك للمتابعة", reply_markup=markup)
    else:
        bot.send_message(uid, f"💰 رصيدك: {user.get('balance',0)} د.ل", reply_markup=main_menu())

# --- Register ---
@bot.message_handler(content_types=['contact'])
def register(message):
    uid = message.chat.id

    users_col.update_one(
        {"_id": uid},
        {"$set": {
            "phone": message.contact.phone_number,
            "balance": 0,
            "status": "active",
            "failed_attempts": 0,
            "join_date": datetime.datetime.now()
        }},
        upsert=True
    )

    bot.send_message(uid, "✅ تم التسجيل", reply_markup=main_menu())

# --- Support ---
@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    bot.send_message(message.chat.id, f"📞 {SUPPORT_NUMBER}")

# --- Account ---
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(message):
    uid = message.chat.id
    if not is_account_active(uid): return

    u = users_col.find_one({"_id": uid})
    bot.send_message(uid, f"📱 {u['phone']}\n💰 {u['balance']} د.ل")

# --- Charge ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge(message):
    if not is_account_active(message.chat.id): return

    msg = bot.send_message(message.chat.id, "🔑 أرسل الكود:")
    bot.register_next_step_handler(msg, process_card)

def process_card(message):
    uid = message.chat.id

    if is_spam(uid): return

    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        users_col.update_one({"_id": uid}, {
            "$inc": {"balance": card['val']},
            "$set": {"failed_attempts": 0}
        })

        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True}})

        logs_col.insert_one({
            "uid": uid,
            "type": "charge",
            "amount": card['val'],
            "date": datetime.datetime.now()
        })

        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل")

    else:
        fails = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": fails}})

        if fails >= 3:
            users_col.update_one({"_id": uid}, {
                "$set": {"status": "frozen"}
            })
            bot.send_message(uid, "❌ تم تجميد حسابك")
        else:
            bot.send_message(uid, f"❌ خطأ ({3-fails} محاولات متبقية)")

# --- Shop ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    if not is_account_active(message.chat.id): return

    items = list(stock_col.find({"sold": False}))
    if not items:
        return bot.send_message(message.chat.id, "❌ لا يوجد")

    markup = types.InlineKeyboardMarkup()

    names = set()
    for i in items:
        if i['name'] not in names:
            markup.add(types.InlineKeyboardButton(
                f"{i['name']} - {i['price']} د.ل",
                callback_data=f"buy_{i['name']}"
            ))
            names.add(i['name'])

    bot.send_message(message.chat.id, "اختر:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    name = call.data.split("_")[1]

    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": name, "sold": False})

    if not item:
        return bot.answer_callback_query(call.id, "❌ غير متوفر", show_alert=True)

    if user['balance'] < item['price']:
        return bot.answer_callback_query(call.id, "❌ رصيدك غير كافي", show_alert=True)

    stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": True}})
    users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})

    logs_col.insert_one({
        "uid": uid,
        "type": "buy",
        "amount": item['price'],
        "date": datetime.datetime.now()
    })

    bot.send_message(uid, f"✅ تم الشراء\n🔑 `{item['code']}`", parse_mode="Markdown")

# --- Admin ---
@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id != ADMIN_ID: return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👥 المستخدمين", callback_data="users"))

    bot.send_message(ADMIN_ID, "لوحة التحكم", reply_markup=markup)

# --- Run ---
if __name__ == "__main__":
    Thread(target=run_flask).start()

    bot.remove_webhook()
    print("Bot Running 🔥")

    while True:
        try:
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            print("ERROR:", e)
