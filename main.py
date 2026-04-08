import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
import datetime
import os
import certifi
import random
import string
from flask import Flask
from threading import Thread
import logging
import time

# --- Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Running ✅"

@app.route('/stats')
def stats():
    total_users = users_col.count_documents({})
    total_balance = sum(u.get('balance', 0) for u in users_col.find())
    return {"users": total_users, "balance": total_balance}

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)

# --- CONFIG ---
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

# --- HELPERS ---
def get_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("🛒 شراء كود", "💳 شحن")
    m.add("👤 حسابي")
    return m

# --- START + REF ---
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    ref = msg.text.split()[1] if len(msg.text.split()) > 1 else None

    user = users_col.find_one({"_id": uid})

    if not user:
        users_col.insert_one({
            "_id": uid,
            "balance": 0,
            "status": "active",
            "ref_by": int(ref) if ref else None,
            "join_date": datetime.datetime.now()
        })

        if ref:
            users_col.update_one({"_id": int(ref)}, {"$inc": {"balance": 1}})

        bot.send_message(uid, "تم التسجيل ✅", reply_markup=get_menu())
    else:
        bot.send_message(uid, "أهلاً بك", reply_markup=get_menu())

# --- CHARGE ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    bot.send_message(msg.chat.id, "أرسل الكود")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    uid = msg.chat.id
    code = msg.text.strip()

    card = cards_col.find_one_and_update(
        {"code": code, "used": False},
        {"$set": {"used": True, "by": uid, "at": datetime.datetime.now()}}
    )

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}})
        bot.send_message(uid, f"تم الشحن {card['val']} ✅")
    else:
        bot.send_message(uid, "كود خطأ ❌")

# --- SHOP ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(msg):
    items = list(stock_col.find({"sold": False}))

    for item in items:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("شراء", callback_data=f"buy_{item['_id']}"))

        bot.send_message(msg.chat.id,
            f"{item['name']}\n💰 {item['price']}",
            reply_markup=kb
        )

# --- BUY (FIXED RACE CONDITION) ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = users_col.find_one({"_id": uid})

    item = stock_col.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True, "buyer": uid, "date": datetime.datetime.now()}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "انتهى ❌")

    if user['balance'] < item['price']:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": False}})
        return bot.answer_callback_query(call.id, "رصيدك لا يكفي ❌")

    users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})

    logs_col.insert_one({
        "uid": uid,
        "type": "buy",
        "price": item['price'],
        "cost_price": item.get('cost_price', 0),
        "date": datetime.datetime.now()
    })

    bot.send_message(uid, f"الكود:\n{item['code']}")

# --- ACCOUNT ---
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def acc(msg):
    u = users_col.find_one({"_id": msg.chat.id})
    bot.send_message(msg.chat.id, f"رصيدك: {u.get('balance',0)}")

# --- ADMIN REPORT ---
@bot.message_handler(commands=['report'])
def report(msg):
    if msg.chat.id != ADMIN_ID:
        return

    pipeline = [
        {"$match": {"type": "buy"}},
        {"$group": {
            "_id": None,
            "sales": {"$sum": "$price"},
            "costs": {"$sum": "$cost_price"},
            "count": {"$sum": 1}
        }}
    ]

    data = list(logs_col.aggregate(pipeline))
    stats = data[0] if data else {"sales": 0, "costs": 0, "count": 0}

    profit = stats["sales"] - stats["costs"]

    bot.send_message(msg.chat.id,
        f"📊 عمليات: {stats['count']}\n"
        f"💰 مبيعات: {stats['sales']}\n"
        f"💵 ربح: {profit}"
    )

# --- RUN ---
def run_bot():
    while True:
        try:
            bot.infinity_polling()
        except:
            time.sleep(5)

if __name__ == "__main__":
    Thread(target=run_bot).start()
    run_flask()
