import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
import datetime
import certifi
from flask import Flask, request
import time

# ================= CONFIG =================
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)

# ================= DATABASE =================
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']

users_col = db['users']
stock_col = db['stock']
orders_col = db['orders']

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running ✅"

@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

# ================= HELPERS =================
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("🛒 شراء كود", "👤 حسابي")
    return m

def notify_admin(text):
    try:
        bot.send_message(ADMIN_ID, text)
    except:
        pass

def create_order(uid, item):
    orders_col.insert_one({
        "uid": uid,
        "item": item['name'],
        "price": item['price'],
        "code": item['code'],
        "date": datetime.datetime.now()
    })

# ================= START =================
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    user = users_col.find_one({"_id": uid})

    if not user:
        users_col.insert_one({
            "_id": uid,
            "balance": 0,
            "points": 0,
            "join_date": datetime.datetime.now()
        })

    bot.send_message(uid, "أهلاً بك 👋", reply_markup=main_menu())

# ================= ACCOUNT =================
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users_col.find_one({"_id": msg.chat.id})
    bot.send_message(msg.chat.id,
        f"💰 رصيدك: {u.get('balance',0)}\n🎯 نقاطك: {u.get('points',0)}"
    )

# ================= SHOP =================
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(msg):
    items = list(stock_col.find({"sold": False}))

    if not items:
        return bot.send_message(msg.chat.id, "⚠️ لا يوجد منتجات حالياً")

    for item in items:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            f"شراء {item['price']} د.ل",
            callback_data=f"buy_{item['_id']}"
        ))

        bot.send_message(
            msg.chat.id,
            f"📦 {item['name']}\n💰 السعر: {item['price']}",
            reply_markup=kb
        )

# ================= BUY (SAFE) =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = users_col.find_one({"_id": uid})

    item = stock_col.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True, "buyer": uid}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "❌ المنتج انتهى")

    if user['balance'] < item['price']:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": False}})
        return bot.answer_callback_query(call.id, "❌ رصيدك لا يكفي")

    # خصم الرصيد
    users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})

    # نقاط
    points = int(item['price'] / 10)
    users_col.update_one({"_id": uid}, {"$inc": {"points": points}})

    # طلب
    create_order(uid, item)

    # إشعار أدمن
    notify_admin(f"🛒 طلب جديد\n👤 {uid}\n📦 {item['name']}\n💰 {item['price']}")

    bot.send_message(uid, f"✅ تم الشراء\n🎫 الكود:\n{item['code']}")
    bot.answer_callback_query(call.id, "تم الشراء")

# ================= SMART REPLY =================
@bot.message_handler(func=lambda m: True)
def smart(msg):
    text = msg.text.lower()

    if "مرحبا" in text:
        bot.reply_to(msg, "أهلاً بك 👋")
    elif "دعم" in text:
        bot.reply_to(msg, "📞 تواصل مع الدعم من القائمة")

# ================= WEBHOOK SET =================
def set_webhook():
    bot.remove_webhook()
    time.sleep(2)

    url = "https://attgift-bot.onrender.com" + API_TOKEN
    bot.set_webhook(url=url)

# ================= RUN =================
if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=10000)
