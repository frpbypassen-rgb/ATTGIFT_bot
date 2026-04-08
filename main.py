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
transactions = db["transactions"]

# كلمات لإلغاء أي عملية إدخال إذا ضغط المستخدم على أزرار القوائم
MENU_BUTTONS = ["🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل"]

# ========= MENUS =========
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن")
    kb.add("👤 حسابي")
    return kb

def contact_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    # request_contact=True تجبر تيليجرام على إرسال رقم هاتف الحساب
    kb.add(types.KeyboardButton("إرسال رقم الهاتف 📱", request_contact=True))
    return kb

# ========= HELPER FUNCTION =========
def check_user_access(uid):
    """دالة للتحقق من أن المستخدم مسجل، أرسل رقمه، وغير مجمد"""
    u = users.find_one({"_id": uid})
    if not u or not u.get("phone"):
        bot.send_message(uid, "⚠️ يجب عليك مشاركة رقم هاتف حسابك أولاً لتتمكن من استخدام المتجر.", reply_markup=contact_menu())
        return None
    if u.get("status") != "active":
        bot.send_message(uid, "❌ حسابك مجمد. تواصل مع الإدارة.")
        return None
    return u

# ========= START & CONTACT HANDLER =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({
            "_id": uid,
            "balance": 0,
            "status": "active",
            "phone": None,
            "join": datetime.datetime.now()
        })
        u = {"phone": None}

    if not u.get("phone"):
        bot.send_message(uid, "👋 مرحباً بك في المتجر!\n\nلإكمال التسجيل، يرجى الضغط على الزر بالأسفل لمشاركة رقم هاتفك المرتبط بتيليجرام.", reply_markup=contact_menu())
    else:
        bot.send_message(uid, "👋 مرحباً بك مجدداً في المتجر", reply_markup=menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(msg):
    uid = msg.chat.id
    
    # تحقق أمني: التأكد من أن جهة الاتصال المرسلة تخص نفس المستخدم، وليس رقم شخص آخر
    if msg.contact.user_id != uid:
        return bot.send_message(uid, "❌ الرجاء استخدام الزر بالأسفل لإرسال رقم هاتفك الخاص بحسابك، وليس جهة اتصال أخرى.", reply_markup=contact_menu())
    
    phone = msg.contact.phone_number
    # إضافة علامة + إذا لم تكن موجودة
    if not phone.startswith('+'):
        phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone}})
    bot.send_message(uid, f"✅ تم تفعيل حسابك بنجاح!\nرقمك المسجل: {phone}", reply_markup=menu())

# ========= ACCOUNT =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = check_user_access(msg.chat.id)
    if not u: return

    status_text = "نشط ✅" if u.get("status") == "active" else "مجمد ❄️"
    text = f"🆔 ID: `{msg.chat.id}`\n📱 الهاتف: {u.get('phone')}\n💰 رصيدك: {u.get('balance',0)}\nحالة الحساب: {status_text}"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    if not check_user_access(msg.chat.id): return
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
    if not check_user_access(msg.chat.id): return

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
    if not user.get("phone"):
        return bot.answer_callback_query(call.id, "❌ يرجى تسجيل رقم هاتفك أولاً.", show_alert=True)

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

    transactions.insert_one({
        "uid": uid,
        "type": "شراء",
        "item_name": item['name'],
        "price": item["price"],
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n\n🎫 الكود الخاص بك:\n`{item['code']}`", parse_mode="Markdown")
    bot.send_message(ADMIN_ID, f"🛒 شراء جديد\n👤 العميل: {uid}\n📱 الهاتف: {user.get('phone')}\n📦 المنتج: {item['name']}\n💰 السعر: {item['price']}")

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
        phone = u.get('phone', 'بدون رقم')
        text += f"`{u['_id']}` | 📱 {phone} | الرصيد: {u.get('balance',0)} | {stat}\n"

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
        
        phone = u.get("phone", "لم يكمل التسجيل")
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
    return "Bot is running perfectly with Mandatory Phone Verification!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ========= RUN =========
if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.remove_webhook()
    print("🚀 BOT STARTED")
    bot.infinity_polling()
