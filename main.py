import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
from flask import Flask, request
import datetime
import certifi
import os
import time
import random
import string

# ========= CONFIG =========
API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"
ADMIN_ID = 1262656649
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
RENDER_URL = "https://attgift-bot.onrender.com"

bot = telebot.TeleBot(API_TOKEN)

# ========= DATABASE =========
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]

# ========= FLASK =========
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running ✅"

@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

# ========= MENU =========
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن")
    kb.add("👤 حسابي")
    return kb

# ========= START =========
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.chat.id

    if not users.find_one({"_id": uid}):
        users.insert_one({
            "_id": uid,
            "balance": 0,
            "status": "active",
            "join_date": datetime.datetime.now()
        })

    bot.send_message(uid, "أهلاً بك 👋", reply_markup=menu())

# ========= ACCOUNT =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    bot.send_message(msg.chat.id, f"💰 رصيدك: {u.get('balance',0)}")

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    bot.send_message(msg.chat.id, "أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    code = msg.text.strip()
    uid = msg.chat.id

    card = cards.find_one_and_update(
        {"code": code, "used": False},
        {"$set": {"used": True}}
    )

    if not card:
        return bot.send_message(uid, "❌ كود غير صالح")

    users.update_one({"_id": uid}, {"$inc": {"balance": card["value"]}})
    bot.send_message(uid, f"✅ تم الشحن {card['value']}")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def categories(msg):
    cats = stock.distinct("category")

    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))

    bot.send_message(msg.chat.id, "اختر قسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def sub(call):
    cat = call.data.split("_",1)[1]

    subs = stock.distinct("subcategory", {"category": cat})

    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat}_{s}"))

    bot.edit_message_text("اختر فئة:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def products(call):
    _, cat, sub = call.data.split("_",2)

    items = list(stock.find({
        "category": cat,
        "subcategory": sub,
        "sold": False
    }))

    if not items:
        return bot.answer_callback_query(call.id, "لا يوجد")

    unique = {}
    for i in items:
        name = i["name"]
        if name not in unique:
            unique[name] = {
                "price": i["price"],
                "count": 1,
                "id": str(i["_id"])
            }
        else:
            unique[name]["count"] += 1

    for name, data in unique.items():
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            f"شراء {data['price']}",
            callback_data=f"buy_{data['id']}"
        ))

        bot.send_message(call.message.chat.id,
            f"{name}\n💰 {data['price']}\n📦 {data['count']}",
            reply_markup=kb
        )

# ========= BUY =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = users.find_one({"_id": uid})

    item = stock.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "❌ انتهى")

    if user["balance"] < item["price"]:
        stock.update_one({"_id": item["_id"]}, {"$set": {"sold": False}})
        return bot.answer_callback_query(call.id, "❌ الرصيد لا يكفي")

    users.update_one({"_id": uid}, {"$inc": {"balance": -item["price"]}})

    bot.send_message(uid, f"🎫 الكود:\n{item['code']}")

# ========= ADMIN =========
@bot.message_handler(commands=["admin"])
def admin(msg):
    if msg.chat.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "❌")

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 احصائيات", "🎫 توليد")
    kb.add("💳 شحن يدوي", "➕ منتج")

    bot.send_message(msg.chat.id, "لوحة الأدمن", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📊 احصائيات")
def stats(msg):
    if msg.chat.id != ADMIN_ID: return

    bot.send_message(msg.chat.id,
        f"👥 {users.count_documents({})}\n"
        f"📦 {stock.count_documents({})}"
    )

@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def gen(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "عدد:قيمة")
    bot.register_next_step_handler(msg, make_cards)

def make_cards(msg):
    try:
        count, val = map(int, msg.text.split(":"))
        arr = []

        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase+string.digits,k=12))
            arr.append({"code":code,"value":val,"used":False})

        cards.insert_many(arr)
        bot.send_message(msg.chat.id, "تم")

    except:
        bot.send_message(msg.chat.id, "خطأ")

@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "id:amount")
    bot.register_next_step_handler(msg, do)

def do(msg):
    try:
        uid, amt = msg.text.split(":")
        users.update_one({"_id": int(uid)}, {"$inc": {"balance": int(amt)}})
        bot.send_message(msg.chat.id, "تم")
    except:
        bot.send_message(msg.chat.id, "خطأ")

# ========= WEBHOOK =========
def set_webhook():
    bot.remove_webhook()
    time.sleep(2)
    bot.set_webhook(url=f"{RENDER_URL}/{API_TOKEN}")

# ========= RUN =========
if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
