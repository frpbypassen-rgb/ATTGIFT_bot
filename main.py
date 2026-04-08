import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
import datetime
import certifi
from flask import Flask, request
import os
import time

# ========= CONFIG =========
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

# ✅ رابط Render (مضاف)
RENDER_URL = "https://attgift-bot.onrender.com"

bot = telebot.TeleBot(API_TOKEN)

# ========= DATABASE =========
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']

users_col = db['users']
stock_col = db['stock']

# ========= FLASK =========
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running ✅"

@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

# ========= MENU =========
def menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("🛒 شراء كود", "👤 حسابي")
    return m

# ========= START =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id

    if not users_col.find_one({"_id": uid}):
        users_col.insert_one({
            "_id": uid,
            "balance": 0,
            "join_date": datetime.datetime.now()
        })

    bot.send_message(uid, "أهلاً بك 👋", reply_markup=menu())

# ========= ACCOUNT =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users_col.find_one({"_id": msg.chat.id})
    bot.send_message(msg.chat.id, f"💰 رصيدك: {u.get('balance',0)}")

# ========= SHOP =========
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

# ========= BUY SAFE =========
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

    users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})

    bot.send_message(uid, f"✅ تم الشراء\n🎫 الكود:\n{item['code']}")
    bot.answer_callback_query(call.id, "تم الشراء")

# ========= WEBHOOK =========
def set_webhook():
    bot.remove_webhook()
    time.sleep(2)

    webhook_url = f"{RENDER_URL}/{API_TOKEN}"
    print("Webhook:", webhook_url)

    bot.set_webhook(url=webhook_url)

# ========= RUN =========
if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))  # مهم لـ Render
    app.run(host="0.0.0.0", port=port)
