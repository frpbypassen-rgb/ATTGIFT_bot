import telebot
from telebot import types
from pymongo import MongoClient, ReturnDocument
from bson import ObjectId
import datetime
import certifi
import random
import string
import os
from flask import Flask
import threading
import time
import requests # لإرسال البيانات لجوجل شيت

# ========= CONFIG =========
API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"
ADMIN_ID = 1262656649
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

# رابط جوجل شيت لتسجيل الفواتير والأرباح الذي قمت بإنشائه
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzPrw8oANq8Aek6O6URoTU0kDVjb1ZtoVdYkhpqAqM6Nuws4ZmcPRC9JtoNZvWoMzUb/exec"

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]
transactions = db["transactions"]
counters = db["counters"] # لحفظ تسلسل الفواتير

MENU_BUTTONS = ["🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل", "💰 ضبط الرصيد", "🏪 العودة للمتجر"]

# ========= MENUS =========
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن")
    kb.add("👤 حسابي")
    return kb

def contact_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("إرسال رقم الهاتف 📱", request_contact=True))
    return kb

def admin_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👥 المستخدمين", "⚙️ إدارة عميل")
    kb.add("🎫 توليد", "💳 شحن يدوي")
    kb.add("💰 ضبط الرصيد", "➕ منتج")
    kb.add("🏪 العودة للمتجر") # زر العودة للمتجر
    return kb

# ========= HELPER FUNCTIONS =========
def check_user_access(uid):
    u = users.find_one({"_id": uid})
    if not u or not u.get("phone"):
        bot.send_message(uid, "⚠️ النظام مغلق. يجب عليك مشاركة رقم هاتف حسابك أولاً.", reply_markup=contact_menu())
        return None
    if u.get("status") != "active":
        bot.send_message(uid, "❌ حسابك مجمد قيد المراجعة. برجاء التواصل مع الدعم الفني.")
        return None
    return u

def find_customer(text):
    """دالة بحث ذكية جداً برقم الهاتف أو الـ ID"""
    text = text.strip()
    # 1. البحث بالـ ID المباشر
    if text.isdigit():
        u = users.find_one({"_id": int(text)})
        if u: return u
    # 2. البحث برقم الهاتف (تنظيف الرقم من الفراغات والبلس والأصفار)
    clean_phone = text.replace("+", "").replace(" ", "").lstrip("0")
    if clean_phone:
        u = users.find_one({"phone": {"$regex": f"{clean_phone}$"}}) 
        if u: return u
    return None

def get_next_order_id():
    """الحصول على رقم فاتورة متسلسل"""
    doc = counters.find_one_and_update(
        {"_id": "order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

# ========= START & CONTACT HANDLER =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({
            "_id": uid, "balance": 0, "status": "frozen", "phone": None, "join": datetime.datetime.now()
        })
        u = {"phone": None, "status": "frozen"}

    if not u.get("phone"):
        bot.send_message(uid, "👋 مرحباً بك في المتجر!\n\nلإكمال التسجيل، يرجى مشاركة رقم هاتفك.", reply_markup=contact_menu())
    else:
        bot.send_message(uid, "👋 مرحباً بك في المتجر", reply_markup=menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(msg):
    uid = msg.chat.id
    if msg.contact.user_id != uid:
        return bot.send_message(uid, "❌ الرجاء إرسال رقم هاتفك الخاص.", reply_markup=contact_menu())
    
    phone = msg.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone}})
    u = users.find_one({"_id": uid})
    if u.get("status") == "frozen":
        bot.send_message(uid, f"✅ تم التسجيل بالرقم: {phone}\n\n⚠️ حسابك الآن (مجمد). برجاء التواصل مع الدعم الفني لتفعيل الحساب.", reply_markup=menu())
    else:
        bot.send_message(uid, f"✅ حسابك نشط وجاهز.", reply_markup=menu())

# ========= ACCOUNT & REPORTS =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    if not u or not u.get("phone"): return bot.send_message(msg.chat.id, "⚠️ أرسل رقم هاتفك أولاً.", reply_markup=contact_menu())

    status_text = "نشط ✅" if u.get("status") == "active" else "مجمد ❄️"
    text = f"👤 **بيانات حسابك**\n\n🆔 ID: `{msg.chat.id}`\n📱 الهاتف: `{u.get('phone')}`\n💰 رصيدك: **{u.get('balance',0)}**\nحالة الحساب: {status_text}"
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🛒 سجل المشتريات", callback_data="client_purchases"),
        types.InlineKeyboardButton("🧾 كشف حساب تفصيلي", callback_data="client_statement")
    )
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["client_purchases", "client_statement"])
def client_reports(call):
    uid = call.message.chat.id
    u = check_user_access(uid)
    if not u: return bot.answer_callback_query(call.id, "حسابك مجمد.", show_alert=True)

    if call.data == "client_purchases":
        history = list(transactions.find({"uid": uid, "type": "شراء"}).sort("_id", -1).limit(10))
        if not history: return bot.answer_callback_query(call.id, "لا توجد مشتريات.", show_alert=True)
        report_text = "🛒 **آخر 10 مشتريات:**\n\n"
        for t in history:
            order_id = t.get('order_id', 'N/A')
            report_text += f"▪️ {t['date']} | فاتورة #{order_id} | {t['item_name']} | السعر: {t['price']}\n"
            
    elif call.data == "client_statement":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(20))
        if not history: return bot.answer_callback_query(call.id, "لا توجد عمليات.", show_alert=True)
        report_text = "🧾 **كشف حساب (آخر 20):**\n\n"
        for t in history:
            if t["type"] == "شراء":
                report_text += f"🔴 خصم | {t['date']} | شراء {t['item_name']} | -{t['price']}\n"
            else:
                report_text += f"🟢 إضافة | {t['date']} | {t['type']} | +{t['amount']}\n"
                
    bot.send_message(uid, report_text, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# ========= CHARGE =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def charge(msg):
    if not check_user_access(msg.chat.id): return
    bot.send_message(msg.chat.id, "أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    code = msg.text.strip()
    uid = msg.chat.id
    card = cards.find_one_and_update({"code": code, "used": False}, {"$set": {"used": True}})
    if not card: return bot.send_message(uid, "❌ كود غير صالح")

    users.update_one({"_id": uid}, {"$inc": {"balance": card["value"]}})
    transactions.insert_one({"uid": uid, "type": "شحن كارت", "amount": card["value"], "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(uid, f"✅ تم شحن رصيدك بقيمة {card['value']} بنجاح")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    if not check_user_access(msg.chat.id): return
    cats = stock.distinct("category")
    if not cats: return bot.send_message(msg.chat.id, "❌ لا توجد منتجات حالياً")
    kb = types.InlineKeyboardMarkup()
    for c in cats: kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))
    bot.send_message(msg.chat.id, "اختر قسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cat(call):
    cat_name = call.data.split("_",1)[1]
    subs = stock.distinct("subcategory", {"category": cat_name})
    kb = types.InlineKeyboardMarkup()
    for s in subs: kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat_name}_{s}"))
    bot.edit_message_text("اختر فئة:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def sub(call):
    _, cat_name, sub_name = call.data.split("_",2)
    items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))
    if not items: return bot.answer_callback_query(call.id, "❌ نفذت الكمية")
    item = items[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("شراء", callback_data=f"buy_{item['_id']}"))
    bot.send_message(call.message.chat.id, f"📦 المنتج: {item['name']}\n💰 السعر: {item['price']}\n📊 الكمية: {len(items)}", reply_markup=kb)

# ========= BUY =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = check_user_access(uid)
    if not user: return bot.answer_callback_query(call.id, "❌ حسابك غير مؤهل.", show_alert=True)

    item_preview = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item_preview: return bot.answer_callback_query(call.id, "❌ نفذت الكمية")
    if user.get("balance", 0) < item_preview["price"]: return bot.answer_callback_query(call.id, "❌ الرصيد غير كافي")

    item = stock.find_one_and_update({"_id": ObjectId(pid), "sold": False}, {"$set": {"sold": True}})
    if not item: return bot.answer_callback_query(call.id, "❌ نفذت الكمية")

    users.update_one({"_id": uid}, {"$inc": {"balance": -item["price"]}})

    # حسابات الفاتورة والربح
    order_id = get_next_order_id()
    cost_price = item.get("cost", 0)
    profit = item["price"] - cost_price
    dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    transactions.insert_one({
        "order_id": order_id, "uid": uid, "type": "شراء", "item_name": item['name'],
        "price": item["price"], "cost": cost_price, "profit": profit, "date": dt_now
    })

    # الإرسال لجوجل شيت
    if SHEET_WEBHOOK_URL and SHEET_WEBHOOK_URL.startswith("http"):
        try:
            requests.post(SHEET_WEBHOOK_URL, json={
                "order_id": order_id, "date": dt_now, "phone": user.get('phone'),
                "item_name": item['name'], "price": item["price"], "cost": cost_price, "profit": profit
            }, timeout=3)
        except Exception as e:
            print("Sheet Error:", e)

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n\n🎫 الكود الخاص بك:\n`{item['code']}`", parse_mode="Markdown")
    bot.send_message(ADMIN_ID, f"🛒 شراء جديد | فاتورة #{order_id}\n👤 العميل: `{uid}`\n📱 الهاتف: {user.get('phone')}\n📦 المنتج: {item['name']}\n💰 السعر: {item['price']}\n💵 المربح: {profit}", parse_mode="Markdown")

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "👑 لوحة تحكم الإدارة", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def back_to_store(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل", reply_markup=menu())

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users_list(msg):
    if msg.chat.id != ADMIN_ID: return
    text = "👥 قائمة آخر المستخدمين:\n\n"
    for u in users.find().sort("join", -1).limit(30):
        stat = "✅" if u.get('status') == 'active' else "❄️"
        text += f"📱 `{u.get('phone', 'بدون رقم')}` | الرصيد: {u.get('balance',0)} | {stat}\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== MANAGE CUSTOMER =====
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def manage_customer_cmd(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل رقم هاتف العميل (أو الـ ID):")
    bot.register_next_step_handler(msg, show_customer_panel)

def show_customer_panel(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
        
    uid = u["_id"]
    stat_ar = "نشط" if u.get("status") == "active" else "مجمد"
    info = f"👤 بيانات العميل:\nID: `{uid}`\nالهاتف: `{u.get('phone')}`\nالرصيد: {u.get('balance',0)}\nالحالة: {stat_ar}"
    
    kb = types.InlineKeyboardMarkup()
    if u.get("status") == "active": kb.add(types.InlineKeyboardButton("❄️ تجميد", callback_data=f"freeze_{uid}"))
    else: kb.add(types.InlineKeyboardButton("✅ تفعيل", callback_data=f"activate_{uid}"))
    kb.add(types.InlineKeyboardButton("📊 تقرير العمليات", callback_data=f"report_{uid}"))
    bot.send_message(msg.chat.id, info, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith(("freeze_", "activate_", "report_")))
def admin_customer_actions(call):
    action, uid = call.data.split("_")
    uid = int(uid)
    if action == "freeze":
        users.update_one({"_id": uid}, {"$set": {"status": "frozen"}})
        bot.answer_callback_query(call.id, "✅ تم التجميد")
        bot.edit_message_text(call.message.text.replace("نشط", "مجمد"), call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "⚠️ تم تجميد حسابك.")
    elif action == "activate":
        users.update_one({"_id": uid}, {"$set": {"status": "active"}})
        bot.answer_callback_query(call.id, "✅ تم التفعيل")
        bot.edit_message_text(call.message.text.replace("مجمد", "نشط"), call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "✅ تم تفعيل حسابك، يمكنك الاستمتاع بالمتجر.", reply_markup=menu())
    elif action == "report":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(15))
        if not history: return bot.answer_callback_query(call.id, "لا يوجد عمليات.", show_alert=True)
        report_text = f"📊 آخر عمليات العميل `{uid}`:\n\n"
        for t in history:
            if t["type"] == "شراء": report_text += f"▪️ {t['date']} | 🛒 {t['item_name']} | بـ {t['price']}\n"
            else: report_text += f"▪️ {t['date']} | 💳 {t['type']} | بـ {t['amount']}\n"
        bot.send_message(call.message.chat.id, report_text, parse_mode="Markdown")

# ===== ADD PRODUCT (WITH COST) =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add_product(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "القسم:الفئة:الاسم:السعر:التكلفة\nكود1\nكود2")
    bot.register_next_step_handler(msg, save_product)

def save_product(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        lines = msg.text.split("\n")
        cat, sub, name, price, cost = lines[0].split(":")
        price = int(price.strip())
        cost = int(cost.strip())
        docs = []
        for c in lines[1:]:
            if c.strip() == "": continue
            docs.append({
                "category": cat.strip(), "subcategory": sub.strip(), "name": name.strip(),
                "price": price, "cost": cost, "code": c.strip(), "sold": False
            })
        if docs:
            stock.insert_many(docs)
            bot.send_message(msg.chat.id, f"✅ تم إضافة {len(docs)} كود.\nالسعر: {price} | التكلفة: {cost} | الربح المتوقع: {price-cost}")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ، تأكد من وجود 5 عناصر (قسم:فئة:اسم:سعر:تكلفة)\n{e}")

# ===== SET BALANCE =====
@bot.message_handler(func=lambda m: m.text == "💰 ضبط الرصيد")
def set_balance_cmd(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:الرصيد_الجديد)\nمثال: 0940719000:500")
    bot.register_next_step_handler(msg, do_set_balance)

def do_set_balance(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        phone_str, val_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            new_bal = int(val_str.strip())
            users.update_one({"_id": u["_id"]}, {"$set": {"balance": new_bal}})
            transactions.insert_one({"uid": u["_id"], "type": "ضبط رصيد", "amount": new_bal, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            bot.send_message(msg.chat.id, f"✅ تم ضبط رصيد العميل {u.get('phone')} ليصبح {new_bal}")
            bot.send_message(u["_id"], f"⚙️ تم تحديث رصيدك من قبل الإدارة ليصبح: {new_bal}")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== DIRECT CHARGE (ADD BALANCE) =====
@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:قيمة_الإضافة)\nمثال: 0940719000:50")
    bot.register_next_step_handler(msg, do_charge)

def do_charge(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        phone_str, amt_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            amt = int(amt_str.strip())
            users.update_one({"_id": u["_id"]}, {"$inc": {"balance": amt}})
            transactions.insert_one({"uid": u["_id"], "type": "شحن إضافي", "amount": amt, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            bot.send_message(msg.chat.id, f"✅ تم إضافة {amt} لرصيد العميل {u.get('phone')}")
            bot.send_message(u["_id"], f"🎁 تم إضافة {amt} لرصيدك من قِبل الإدارة")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

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

# ========= DUMMY WEB SERVER FOR RENDER =========
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running perfectly!"
def run_web_server(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ========= RUN =========
if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.remove_webhook()
    print("⏳ Waiting for old instance to shut down...")
    time.sleep(5)
    print("🚀 PRO BOT STARTED")
    bot.infinity_polling()
