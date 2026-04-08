import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
from flask import Flask, request
import datetime, certifi, os, time, random, string

# ========= CONFIG =========
API_TOKEN = "PUT_TOKEN_HERE"
ADMIN_ID = 1262656649
MONGO_URI = "PUT_MONGO_HERE"
RENDER_URL = "https://your-app.onrender.com"

bot = telebot.TeleBot(API_TOKEN)

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["botdb"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]

# ========= FLASK =========
app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

# ========= START =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id

    if not users.find_one({"_id": uid}):
        users.insert_one({"_id": uid, "balance": 0, "status": "active"})

    bot.send_message(uid, "👋 مرحباً", reply_markup=main_menu())

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن")
    kb.add("👤 حسابي")
    return kb

# ========= ACCOUNT =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    bot.send_message(msg.chat.id, f"💰 رصيدك: {u.get('balance',0)}\n🆔 {msg.chat.id}")

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    bot.send_message(msg.chat.id, "أرسل الكود:")
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
    bot.send_message(uid, f"✅ تم شحن {card['value']}")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    cats = stock.distinct("category")

    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))

    bot.send_message(msg.chat.id, "اختر قسم", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cat(call):
    cat = call.data.split("_",1)[1]
    subs = stock.distinct("subcategory", {"category": cat})

    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat}_{s}"))

    bot.edit_message_text("اختر فئة", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def sub(call):
    _, cat, sub = call.data.split("_",2)

    items = list(stock.find({"category": cat, "subcategory": sub, "sold": False}))

    if not items:
        return bot.answer_callback_query(call.id, "لا يوجد")

    item = items[0]

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("شراء", callback_data=f"buy_{item['_id']}"))

    bot.send_message(call.message.chat.id,
        f"{item['name']}\n💰 {item['price']}\n📦 {len(items)}",
        reply_markup=kb)

# ========= BUY =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    item = stock.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "❌ انتهى")

    user = users.find_one({"_id": uid})

    if user["balance"] < item["price"]:
        stock.update_one({"_id": item["_id"]}, {"$set": {"sold": False}})
        return bot.answer_callback_query(call.id, "❌ رصيدك غير كافي")

    users.update_one({"_id": uid}, {"$inc": {"balance": -item["price"]}})

    # إشعار الأدمن
    bot.send_message(ADMIN_ID,
        f"🛒 شراء جديد\n👤 {uid}\n📦 {item['name']}\n💰 {item['price']}")

    bot.send_message(uid, f"🎫 الكود:\n{item['code']}")

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id != ADMIN_ID:
        return

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👥 المستخدمين", "🎫 كروت")
    kb.add("➕ منتج", "💳 شحن")

    bot.send_message(msg.chat.id, "👑 لوحة التحكم", reply_markup=kb)

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def all_users(msg):
    if msg.chat.id != ADMIN_ID: return

    text = "👥 المستخدمين:\n\n"
    for u in users.find().limit(20):
        text += f"{u['_id']} | {u.get('balance',0)}\n"

    bot.send_message(msg.chat.id, text)

# ===== ADD PRODUCT =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "cat:sub:name:price\ncode1\ncode2")
    bot.register_next_step_handler(msg, save)

def save(msg):
    try:
        lines = msg.text.split("\n")
        cat, sub, name, price = lines[0].split(":")
        price = int(price)

        docs = []
        for c in lines[1:]:
            docs.append({
                "category": cat,
                "subcategory": sub,
                "name": name,
                "price": price,
                "code": c,
                "sold": False
            })

        stock.insert_many(docs)
        bot.send_message(msg.chat.id, f"✅ تم إضافة {len(docs)} كود")

    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ\n{e}")

# ===== CARDS =====
@bot.message_handler(func=lambda m: m.text == "🎫 كروت")
def gen(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "عدد:قيمة")
    bot.register_next_step_handler(msg, make)

def make(msg):
    try:
        count, val = map(int, msg.text.split(":"))
        arr = []

        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase+string.digits,k=12))
            arr.append({"code":code,"value":val,"used":False})

        cards.insert_many(arr)
        bot.send_message(msg.chat.id, "✅ تم")

    except:
        bot.send_message(msg.chat.id, "❌ خطأ")

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
