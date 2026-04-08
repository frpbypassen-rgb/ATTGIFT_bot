import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
import datetime
import certifi
import random
import string
import os
from flask import Flask
import threading

# ========= CONFIG =========
API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"
ADMIN_ID = 1262656649
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

bot = telebot.TeleBot(API_TOKEN)

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]

# ========= MENU =========
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن")
    kb.add("👤 حسابي")
    return kb

# ========= START =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id

    if not users.find_one({"_id": uid}):
        users.insert_one({
            "_id": uid,
            "balance": 0,
            "status": "active",
            "join": datetime.datetime.now()
        })

    bot.send_message(uid, "👋 مرحباً بك", reply_markup=menu())

# ========= ACCOUNT =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    if u:
        bot.send_message(msg.chat.id, f"🆔 ID: {msg.chat.id}\n💰 رصيدك: {u.get('balance',0)}")
    else:
        bot.send_message(msg.chat.id, "❌ حسابك غير موجود، أرسل /start")

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    bot.send_message(msg.chat.id, "أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    # إلغاء إذا ضغط المستخدم على زر من القائمة
    if msg.text in ["🛒 شراء", "💳 شحن", "👤 حسابي"]:
        return bot.send_message(msg.chat.id, "تم إلغاء عملية الشحن.")

    code = msg.text.strip()
    uid = msg.chat.id

    card = cards.find_one_and_update(
        {"code": code, "used": False},
        {"$set": {"used": True}}
    )

    if not card:
        return bot.send_message(uid, "❌ كود غير صالح أو مستخدم مسبقاً")

    users.update_one({"_id": uid}, {"$inc": {"balance": card["value"]}})
    bot.send_message(uid, f"✅ تم شحن {card['value']} بنجاح")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    cats = stock.distinct("category")

    if not cats:
        return bot.send_message(msg.chat.id, "❌ لا توجد منتجات حالياً")

    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))

    bot.send_message(msg.chat.id, "اختر قسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cat(call):
    cat_name = call.data.split("_",1)[1]

    subs = stock.distinct("subcategory", {"category": cat_name})

    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat_name}_{s}"))

    bot.edit_message_text("اختر فئة:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def sub(call):
    _, cat_name, sub_name = call.data.split("_",2)

    items = list(stock.find({
        "category": cat_name,
        "subcategory": sub_name,
        "sold": False
    }))

    if not items:
        return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    item = items[0]

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("شراء", callback_data=f"buy_{item['_id']}"))

    bot.send_message(call.message.chat.id,
        f"📦 المنتج: {item['name']}\n💰 السعر: {item['price']}\n📊 الكمية المتوفرة: {len(items)}",
        reply_markup=kb)

# ========= BUY =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = users.find_one({"_id": uid})

    # 1. فحص المنتج قبل حظره للتأكد من السعر
    item_preview = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item_preview:
        return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    # 2. التحقق من الرصيد أولاً
    if user.get("balance", 0) < item_preview["price"]:
        return bot.answer_callback_query(call.id, "❌ الرصيد غير كافي")

    # 3. حجز المنتج
    item = stock.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    # 4. خصم الرصيد
    users.update_one({"_id": uid}, {"$inc": {"balance": -item["price"]}})

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n\n🎫 الكود الخاص بك:\n`{item['code']}`", parse_mode="Markdown")

    # إشعار الأدمن
    bot.send_message(ADMIN_ID,
        f"🛒 عملية شراء جديدة\n👤 المشتري: {uid}\n📦 المنتج: {item['name']}\n💰 السعر: {item['price']}")

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "❌ غير مصرح لك")

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👥 المستخدمين", "🎫 توليد")
    kb.add("➕ منتج", "💳 شحن يدوي")

    bot.send_message(msg.chat.id, "👑 مرحباً بك في لوحة تحكم الأدمن", reply_markup=kb)

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users_list(msg):
    if msg.chat.id != ADMIN_ID: return

    text = "👥 قائمة آخر المستخدمين:\n\n"
    for u in users.find().limit(30):
        text += f"ID: `{u['_id']}` | الرصيد: {u.get('balance',0)}\n"

    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== ADD PRODUCT =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add_product(msg):
    if msg.chat.id != ADMIN_ID: return

    bot.send_message(msg.chat.id,
        "أرسل البيانات بالصيغة التالية:\n\nالقسم:الفئة:الاسم:السعر\nكود1\nكود2\nكود3")

    bot.register_next_step_handler(msg, save_product)

def save_product(msg):
    if msg.text in ["👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي"]:
        return bot.send_message(msg.chat.id, "تم الإلغاء.")

    try:
        lines = msg.text.split("\n")
        cat, sub, name, price = lines[0].split(":")
        price = int(price)

        docs = []
        for c in lines[1:]:
            if c.strip() == "": continue
            docs.append({
                "category": cat.strip(),
                "subcategory": sub.strip(),
                "name": name.strip(),
                "price": price,
                "code": c.strip(),
                "sold": False
            })

        if docs:
            stock.insert_many(docs)
            bot.send_message(msg.chat.id, f"✅ تم إضافة {len(docs)} كود بنجاح للمنتج {name}")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم إرسال أي أكواد.")

    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ في التنسيق:\n{e}")

# ===== GENERATE CARDS =====
@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def gen_cards(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (العدد:القيمة)\nمثال: 10:50")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    if msg.text in ["👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي"]:
        return bot.send_message(msg.chat.id, "تم الإلغاء.")

    try:
        count, val = map(int, msg.text.split(":"))
        arr = []
        codes_text = f"✅ تم توليد {count} كروت بقيمة {val}:\n\n"

        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase+string.digits, k=12))
            arr.append({"code":code, "value":val, "used":False})
            codes_text += f"`{code}`\n"

        cards.insert_many(arr)
        bot.send_message(msg.chat.id, codes_text, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ في الإدخال. تأكد من الصيغة (العدد:القيمة)")

# ===== DIRECT CHARGE =====
@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (ID_المستخدم:القيمة)")
    bot.register_next_step_handler(msg, do_charge)

def do_charge(msg):
    if msg.text in ["👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي"]:
        return bot.send_message(msg.chat.id, "تم الإلغاء.")

    try:
        uid, amt = map(int, msg.text.split(":"))
        result = users.update_one({"_id": uid}, {"$inc": {"balance": amt}})
        if result.matched_count > 0:
            bot.send_message(msg.chat.id, "✅ تم الشحن اليدوي بنجاح")
            bot.send_message(uid, f"🎁 تم شحن رصيدك بمبلغ {amt} من قِبل الإدارة")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على المستخدم")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال")

# ========= DUMMY WEB SERVER FOR RENDER =========
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ========= RUN =========
if __name__ == "__main__":
    # 1. تشغيل سيرفر الويب الوهمي لـ Render في مسار منفصل
    threading.Thread(target=run_web_server).start()
    
    # 2. إزالة أي Webhook عالق (حل مشكلة الخطأ 409)
    bot.remove_webhook()
    
    # 3. تشغيل البوت
    print("🚀 BOT STARTED")
    bot.infinity_polling()
