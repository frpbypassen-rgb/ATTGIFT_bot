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
RENDER_URL = "https://attgift-bot.onrender.com"

bot = telebot.TeleBot(API_TOKEN)

# ========= DB =========
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']

users_col = db['users']
stock_col = db['stock']
cards_col = db['cards']

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
    m.add("🛒 شراء كود", "💳 شحن رصيد")
    m.add("👤 حسابي")
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
    bot.send_message(msg.chat.id,
        f"💰 رصيدك: {u.get('balance',0)}"
    )

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge(msg):
    bot.send_message(msg.chat.id, "🔢 أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    uid = msg.chat.id
    code = msg.text.strip()

    card = cards_col.find_one_and_update(
        {"code": code, "used": False},
        {"$set": {"used": True, "by": uid, "date": datetime.datetime.now()}}
    )

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['value']}})
        bot.send_message(uid, f"✅ تم شحن {card['value']} د.ل")
    else:
        bot.send_message(uid, "❌ كود غير صحيح")

# ========= CATEGORIES =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def categories(msg):
    cats = stock_col.distinct("category")

    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))

    bot.send_message(msg.chat.id, "📂 اختر القسم:", reply_markup=kb)

# ========= SUB =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def subcategories(call):
    cat = call.data.split("_",1)[1]

    subs = stock_col.distinct("subcategory", {"category": cat})

    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat}_{s}"))

    bot.edit_message_text("📁 اختر الفئة:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb
    )

# ========= PRODUCTS =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def products(call):
    _, cat, sub = call.data.split("_",2)

    items = list(stock_col.find({
        "category": cat,
        "subcategory": sub,
        "sold": False
    }))

    if not items:
        return bot.answer_callback_query(call.id, "❌ لا يوجد")

    unique = {}

    for i in items:
        name = i['name']
        if name not in unique:
            unique[name] = {
                "price": i['price'],
                "count": 1,
                "id": str(i['_id'])
            }
        else:
            unique[name]['count'] += 1

    for name, data in unique.items():
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            f"شراء {data['price']} د.ل",
            callback_data=f"buy_{data['id']}"
        ))

        bot.send_message(call.message.chat.id,
            f"📦 {name}\n💰 السعر: {data['price']}\n📊 المتوفر: {data['count']}",
            reply_markup=kb
        )

# ========= BUY =========
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
        return bot.answer_callback_query(call.id, "❌ انتهى")

    if user['balance'] < item['price']:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": False}})
        return bot.answer_callback_query(call.id, "❌ رصيدك لا يكفي")

    users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})

    bot.send_message(uid, f"✅ تم الشراء\n🎫 الكود:\n{item['code']}")

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "❌ غير مصرح")

    users = users_col.count_documents({})
    stock = stock_col.count_documents({})
    sold = stock_col.count_documents({"sold": True})

    bot.send_message(msg.chat.id,
        f"👑 لوحة الأدمن\n\n"
        f"👥 المستخدمين: {users}\n"
        f"📦 المنتجات: {stock}\n"
        f"✅ المباعة: {sold}"
    )

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
