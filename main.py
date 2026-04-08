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
transactions = db["transactions"] # مجموعة جديدة لتسجيل التقارير

# كلمات لإلغاء أي عملية إدخال إذا ضغط المستخدم على أزرار القوائم
MENU_BUTTONS = ["🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل"]

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
            "status": "active", # active أو frozen
            "phone": None,      # رقم الهاتف اختياري
            "join": datetime.datetime.now()
        })

    bot.send_message(uid, "👋 مرحباً بك في المتجر", reply_markup=menu())

# ========= ACCOUNT (اختياري رقم الهاتف) =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    if u:
        phone = u.get("phone") if u.get("phone") else "غير محدد"
        status_text = "نشط ✅" if u.get("status") == "active" else "مجمد ❄️"
        
        text = f"🆔 ID: `{msg.chat.id}`\n📱 الهاتف: {phone}\n💰 رصيدك: {u.get('balance',0)}\nحالة الحساب: {status_text}"
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📱 إضافة/تعديل رقم الهاتف", callback_data="set_phone"))
        
        bot.send_message(msg.chat.id, text, reply_markup=kb, parse_mode="Markdown")
    else:
        bot.send_message(msg.chat.id, "❌ حسابك غير موجود، أرسل /start")

@bot.callback_query_handler(func=lambda c: c.data == "set_phone")
def set_phone(call):
    msg = bot.send_message(call.message.chat.id, "أرسل رقم هاتفك الآن:")
    bot.register_next_step_handler(msg, save_phone)

def save_phone(msg):
    if msg.text in MENU_BUTTONS:
        return bot.send_message(msg.chat.id, "تم إلغاء إضافة الرقم.")
    
    users.update_one({"_id": msg.chat.id}, {"$set": {"phone": msg.text.strip()}})
    bot.send_message(msg.chat.id, "✅ تم حفظ رقم الهاتف بنجاح.")

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    u = users.find_one({"_id": msg.chat.id})
    if u.get("status") != "active": return bot.send_message(msg.chat.id, "❌ حسابك مجمد. تواصل مع الإدارة.")
        
    bot.send_message(msg.chat.id, "أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    if msg.text in MENU_BUTTONS:
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
    
    # تسجيل العملية في التقارير
    transactions.insert_one({
        "uid": uid,
        "type": "شحن كارت",
        "amount": card["value"],
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    bot.send_message(uid, f"✅ تم شحن {card['value']} بنجاح")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    u = users.find_one({"_id": msg.chat.id})
    if u.get("status") != "active": return bot.send_message(msg.chat.id, "❌ حسابك مجمد. تواصل مع الإدارة.")

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

    bot.edit_message_text("اختر فئة:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def sub(call):
    _, cat_name, sub_name = call.data.split("_",2)

    items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))

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
    if user.get("status") != "active":
        return bot.answer_callback_query(call.id, "❌ حسابك مجمد.", show_alert=True)

    item_preview = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item_preview:
        return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    if user.get("balance", 0) < item_preview["price"]:
        return bot.answer_callback_query(call.id, "❌ الرصيد غير كافي")

    item = stock.find_one_and_update(
        {"_id": ObjectId(pid), "sold": False},
        {"$set": {"sold": True}}
    )

    if not item:
        return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    users.update_one({"_id": uid}, {"$inc": {"balance": -item["price"]}})

    # تسجيل العملية في التقارير
    transactions.insert_one({
        "uid": uid,
        "type": "شراء",
        "item_name": item['name'],
        "price": item["price"],
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n\n🎫 الكود الخاص بك:\n`{item['code']}`", parse_mode="Markdown")
    bot.send_message(ADMIN_ID, f"🛒 شراء جديد\n👤 العميل: {uid}\n📦 المنتج: {item['name']}\n💰 السعر: {item['price']}")

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id != ADMIN_ID: return

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👥 المستخدمين", "⚙️ إدارة عميل")
    kb.add("🎫 توليد", "💳 شحن يدوي")
    kb.add("➕ منتج")

    bot.send_message(msg.chat.id, "👑 لوحة تحكم الإدارة", reply_markup=kb)

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users_list(msg):
    if msg.chat.id != ADMIN_ID: return

    text = "👥 قائمة آخر المستخدمين:\n\n"
    for u in users.find().sort("join", -1).limit(30):
        stat = "✅" if u.get('status') == 'active' else "❄️"
        text += f"`{u['_id']}` | الرصيد: {u.get('balance',0)} | {stat}\n"

    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== MANAGE CUSTOMER & REPORTS =====
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def manage_customer_cmd(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل ID العميل المراد إدارته:")
    bot.register_next_step_handler(msg, show_customer_panel)

def show_customer_panel(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    
    try:
        uid = int(msg.text.strip())
        u = users.find_one({"_id": uid})
        if not u:
            return bot.send_message(msg.chat.id, "❌ العميل غير موجود.")
        
        phone = u.get("phone", "غير محدد")
        stat_ar = "نشط" if u.get("status") == "active" else "مجمد"
        
        info = f"👤 بيانات العميل:\nID: `{uid}`\nالهاتف: {phone}\nالرصيد: {u.get('balance',0)}\nالحالة: {stat_ar}"
        
        kb = types.InlineKeyboardMarkup()
        if u.get("status") == "active":
            kb.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"freeze_{uid}"))
        else:
            kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"))
            
        kb.add(types.InlineKeyboardButton("📊 تقرير العمليات", callback_data=f"report_{uid}"))
        
        bot.send_message(msg.chat.id, info, reply_markup=kb, parse_mode="Markdown")
        
    except ValueError:
        bot.send_message(msg.chat.id, "❌ ID غير صحيح. يجب أن يكون أرقاماً فقط.")

@bot.callback_query_handler(func=lambda c: c.data.startswith(("freeze_", "activate_", "report_")))
def admin_customer_actions(call):
    action, uid = call.data.split("_")
    uid = int(uid)
    
    if action == "freeze":
        users.update_one({"_id": uid}, {"$set": {"status": "frozen"}})
        bot.answer_callback_query(call.id, "✅ تم تجميد الحساب")
        bot.edit_message_text(call.message.text.replace("نشط", "مجمد"), call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "⚠️ تم تجميد حسابك من قبل الإدارة.")
        
    elif action == "activate":
        users.update_one({"_id": uid}, {"$set": {"status": "active"}})
        bot.answer_callback_query(call.id, "✅ تم تفعيل الحساب")
        bot.edit_message_text(call.message.text.replace("مجمد", "نشط"), call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "✅ تم إعادة تفعيل حسابك، يمكنك الاستمتاع بخدماتنا الآن.")
        
    elif action == "report":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(15))
        if not history:
            return bot.answer_callback_query(call.id, "لا توجد عمليات مسجلة لهذا العميل.", show_alert=True)
            
        report_text = f"📊 آخر 15 عملية للعميل `{uid}`:\n\n"
        for t in history:
            if t["type"] == "شراء":
                report_text += f"▪️ {t['date']} | 🛒 شراء | {t['item_name']} | بـ {t['price']}\n"
            else:
                report_text += f"▪️ {t['date']} | 💳 {t['type']} | بقيمة {t['amount']}\n"
                
        bot.send_message(call.message.chat.id, report_text, parse_mode="Markdown")

# ===== ADD PRODUCT =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add_product(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "القسم:الفئة:الاسم:السعر\nكود1\nكود2")
    bot.register_next_step_handler(msg, save_product)

def save_product(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        lines = msg.text.split("\n")
        cat, sub, name, price = lines[0].split(":")
        price = int(price)
        docs = []
        for c in lines[1:]:
            if c.strip() == "": continue
            docs.append({"category": cat.strip(), "subcategory": sub.strip(), "name": name.strip(), "price": price, "code": c.strip(), "sold": False})
        if docs:
            stock.insert_many(docs)
            bot.send_message(msg.chat.id, f"✅ تم إضافة {len(docs)} كود بنجاح.")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ:\n{e}")

# ===== GENERATE CARDS =====
@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def gen_cards(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (العدد:القيمة)")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        count, val = map(int, msg.text.split(":"))
        arr = []
        txt = f"✅ تم توليد {count} كروت بقيمة {val}:\n\n"
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase+string.digits, k=12))
            arr.append({"code":code, "value":val, "used":False})
            txt += f"`{code}`\n"
        cards.insert_many(arr)
        bot.send_message(msg.chat.id, txt, parse_mode="Markdown")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== DIRECT CHARGE =====
@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (ID_المستخدم:القيمة)")
    bot.register_next_step_handler(msg, do_charge)

def do_charge(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        uid, amt = map(int, msg.text.split(":"))
        result = users.update_one({"_id": uid}, {"$inc": {"balance": amt}})
        if result.matched_count > 0:
            transactions.insert_one({
                "uid": uid,
                "type": "شحن يدوي (إدارة)",
                "amount": amt,
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            bot.send_message(msg.chat.id, "✅ تم الشحن اليدوي بنجاح")
            bot.send_message(uid, f"🎁 تم شحن رصيدك بمبلغ {amt} من قِبل الإدارة")
        else:
            bot.send_message(msg.chat.id, "❌ العميل غير موجود")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال")

# ========= DUMMY WEB SERVER FOR RENDER =========
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running with Advanced Admin Features!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ========= RUN =========
if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.remove_webhook()
    print("🚀 ADVANCED BOT STARTED")
    bot.infinity_polling()
