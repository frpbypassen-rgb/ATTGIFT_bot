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
import requests 
import io
import openpyxl 

# ========= CONFIG =========
API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"

# ضع هنا معرفات (IDs) كل المدراء مفصولة بفاصلة
ADMIN_IDS = [1262656649] 

MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

# رابط جوجل شيت لتسجيل الفواتير والأرباح
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzPrw8oANq8Aek6O6URoTU0kDVjb1ZtoVdYkhpqAqM6Nuws4ZmcPRC9JtoNZvWoMzUb/exec"

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]
transactions = db["transactions"]
counters = db["counters"]

MENU_BUTTONS = [
    "🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", 
    "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل", 
    "💰 ضبط الرصيد", "🧾 سجل الفواتير", "📦 إدارة المخزون", "🏪 العودة للمتجر"
]

temp_admin_data = {}

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
    kb.add("📦 إدارة المخزون", "🧾 سجل الفواتير") 
    kb.add("🏪 العودة للمتجر") 
    return kb

# ========= HELPER FUNCTIONS =========
def check_user_access(uid):
    u = users.find_one({"_id": uid})
    if not u or not u.get("phone"):
        bot.send_message(uid, "⚠️ النظام مغلق. يجب عليك مشاركة رقم هاتف حسابك أولاً.", reply_markup=contact_menu())
        return None
    if u.get("status") != "active":
        bot.send_message(uid, "❌ حساب مجمد. برجاء التواصل مع الدعم الفني.")
        return None
    return u

def find_customer(text):
    text = text.strip()
    if text.isdigit():
        u = users.find_one({"_id": int(text)})
        if u: return u
    clean_phone = text.replace("+", "").replace(" ", "").lstrip("0")
    if clean_phone:
        u = users.find_one({"phone": {"$regex": f"{clean_phone}$"}}) 
        if u: return u
    return None

def get_next_order_id():
    doc = counters.find_one_and_update(
        {"_id": "order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

def generate_excel_file(items_data, index):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Codes"
    ws.append(["الكود", "الرقم التسلسلي"])
    for data in items_data:
        ws.append([data['code'], data['serial']])
    
    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = f"Codes_Part_{index+1}.xlsx"
    return file_stream

def generate_products_template():
    """توليد قالب إكسيل فارغ جاهز لملء المنتجات"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products_Template"
    headers = ["القسم", "الفئة", "الاسم", "السعر", "التكلفة", "الكود", "الرقم التسلسلي"]
    ws.append(headers)
    
    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = "Template_Products.xlsx"
    return file_stream

# ========= START & CONTACT HANDLER =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({
            "_id": uid, "balance": 0.0, "status": "frozen", "phone": None, "failed_attempts": 0, "join": datetime.datetime.now()
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
    text = f"👤 **بيانات حسابك**\n\n🆔 ID: `{msg.chat.id}`\n📱 الهاتف: `{u.get('phone')}`\n💰 رصيدك: **{u.get('balance', 0.0)}**\nحالة الحساب: {status_text}"
    
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
            report_text += f"▪️ {t['date']} | فاتورة #{order_id} | {t['item_name']} (x{t.get('quantity', 1)}) | السعر: {t['price']}\n"
            
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
    uid = msg.chat.id
    u = users.find_one({"_id": uid})
    
    if not u or u.get("status") != "active":
        return bot.send_message(uid, "❌ حسابك مجمد. لا يمكنك الشحن.")

    code = msg.text.strip()
    card = cards.find_one_and_update({"code": code, "used": False}, {"$set": {"used": True}})
    
    if not card:
        failed_attempts = u.get("failed_attempts", 0) + 1
        if failed_attempts >= 5:
            users.update_one({"_id": uid}, {"$set": {"status": "frozen", "failed_attempts": 0}})
            return bot.send_message(uid, "🚫 تم إيقاف الحساب بسبب التلاعب بالنظام.")
        else:
            users.update_one({"_id": uid}, {"$set": {"failed_attempts": failed_attempts}})
            attempts_left = 5 - failed_attempts
            return bot.send_message(uid, f"❌ كود غير صالح. (متبقي لك {attempts_left} محاولات قبل تجميد الحساب)")

    users.update_one({"_id": uid}, {"$inc": {"balance": float(card["value"])}, "$set": {"failed_attempts": 0}})
    transactions.insert_one({"uid": uid, "type": "شحن كارت", "amount": float(card["value"]), "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
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
    available_count = len(items)
    
    if available_count < 10:
        return bot.answer_callback_query(call.id, "❌ الكمية المتوفرة أقل من الحد الأدنى للشراء (10 أكواد).", show_alert=True)
        
    item = items[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 طلب شراء", callback_data=f"buy_{item['_id']}"))
    bot.send_message(call.message.chat.id, f"📦 المنتج: {item['name']}\n💰 السعر: {item['price']}\n📊 المتوفر: {available_count}\n⚠️ أقل كمية للطلب: 10 ومضاعفاتها", reply_markup=kb)

# ========= BUY (BULK WITH MINIMUM 10) =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy_quantity_prompt(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = check_user_access(uid)
    if not user: return bot.answer_callback_query(call.id, "❌ حسابك غير مؤهل.", show_alert=True)

    item_preview = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item_preview: return bot.answer_callback_query(call.id, "❌ نفذت الكمية أو تم بيعها.", show_alert=True)
    
    product_name = item_preview['name']
    available = stock.count_documents({"name": product_name, "sold": False})
    
    if available < 10:
        return bot.answer_callback_query(call.id, "❌ الكمية المتبقية أقل من 10.", show_alert=True)

    msg = bot.send_message(uid, f"📦 المنتج: {product_name}\n📊 المتوفر: {available}\n\n👉 أرسل **الكمية المطلوبة** (يجب أن تكون 10 أو مضاعفاتها كـ 20، 30...):")
    bot.register_next_step_handler(msg, process_purchase, user, item_preview, available)
    bot.answer_callback_query(call.id)

def process_purchase(msg, user, item_ref, available):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم إلغاء الشراء.")
    uid = msg.chat.id
    
    try:
        qty = int(msg.text.strip())
        if qty < 10 or qty % 10 != 0:
            return bot.send_message(uid, "❌ الكمية يجب أن تكون 10 أو مضاعفاتها (10, 20, 30...). تم الإلغاء.")
    except ValueError:
        return bot.send_message(uid, "❌ الرجاء إدخال رقم صحيح. تم الإلغاء.")

    if qty > available:
        return bot.send_message(uid, f"❌ الكمية المطلوبة غير متوفرة. أقصى كمية: {available}")

    name = item_ref['name']
    price = float(item_ref['price'])
    cost = float(item_ref.get('cost', 0.0))
    total_price = qty * price
    total_cost = qty * cost
    profit = total_price - total_cost

    user_fresh = users.find_one({"_id": uid})
    if float(user_fresh.get("balance", 0.0)) < total_price: 
        return bot.send_message(uid, f"❌ رصيدك غير كافي.\nالمطلوب: {total_price}\nرصيدك: {user_fresh.get('balance', 0)}")

    available_docs = list(stock.find({"name": name, "sold": False}).limit(qty))
    if len(available_docs) < qty:
        return bot.send_message(uid, "❌ حدث خطأ، الكمية نفذت فجأة. يرجى المحاولة مرة أخرى.")

    doc_ids = [d['_id'] for d in available_docs]
    res = stock.update_many({"_id": {"$in": doc_ids}, "sold": False}, {"$set": {"sold": True}})
    
    if res.modified_count != qty:
        stock.update_many({"_id": {"$in": doc_ids}}, {"$set": {"sold": False}})
        return bot.send_message(uid, "❌ حدث تضارب أثناء الشراء، الرجاء المحاولة مرة أخرى.")

    users.update_one({"_id": uid}, {"$inc": {"balance": -total_price}})
    order_id = get_next_order_id()
    dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    transactions.insert_one({
        "order_id": order_id, "uid": uid, "phone": user_fresh.get('phone'), "type": "شراء", 
        "item_name": name, "quantity": qty, "price": total_price, "cost": total_cost, "profit": profit, "date": dt_now
    })

    if SHEET_WEBHOOK_URL and SHEET_WEBHOOK_URL.startswith("http"):
        try:
            requests.post(SHEET_WEBHOOK_URL, json={
                "order_id": order_id, "date": dt_now, "phone": user_fresh.get('phone'),
                "item_name": f"{name} (x{qty})", "price": total_price, "cost": total_cost, "profit": profit
            }, timeout=3)
        except Exception as e:
            print("Sheet Error:", e)

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n💰 إجمالي المخصوم: {total_price}\n\nجاري تجهيز الأكواد وإرسالها في ملفات إكسيل...", parse_mode="Markdown")

    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, f"🛒 شراء جديد بالجملة | فاتورة #{order_id}\n👤 العميل: `{uid}`\n📱 الهاتف: {user_fresh.get('phone')}\n📦 المنتج: {name} (الكمية: {qty})\n💰 المدفوع: {total_price}\n💵 المربح: {profit}", parse_mode="Markdown")
        except: pass

    purchased_items_data = [{'code': d['code'], 'serial': d.get('serial', 'بدون_تسلسلي')} for d in available_docs]
    chunks = [purchased_items_data[i:i + 10] for i in range(0, len(purchased_items_data), 10)]
    
    for i, chunk in enumerate(chunks):
        file_stream = generate_excel_file(chunk, i)
        bot.send_document(uid, document=file_stream, caption=f"📁 الأكواد (الدفعة {i+1} من {len(chunks)})")
        
        for admin_id in ADMIN_IDS:
            try:
                file_stream.seek(0)
                bot.send_document(admin_id, document=file_stream, caption=f"📁 نسخة للإدارة | فاتورة #{order_id} | الدفعة {i+1}")
            except: pass

    remaining_stock = stock.count_documents({"name": name, "sold": False})
    if remaining_stock <= 30:
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"⚠️ **تنبيه نقص مخزون** ⚠️\n\nالمنتج: `{name}`\nالكمية المتبقية: **{remaining_stock}** كود فقط!\nيرجى إعادة تعبئة المخزون قريباً لتجنب نفاذ الكمية.", parse_mode="Markdown")
            except: pass

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.chat.id not in ADMIN_IDS: return
    bot.send_message(msg.chat.id, "👑 لوحة تحكم الإدارة", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def back_to_store(msg):
    if msg.chat.id not in ADMIN_IDS: return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل", reply_markup=menu())

# ===== MANAGE STOCK =====
@bot.message_handler(func=lambda m: m.text == "📦 إدارة المخزون")
def manage_stock_cmd(msg):
    if msg.chat.id not in ADMIN_IDS: return
    
    names = stock.distinct("name", {"sold": False})
    if not names: 
        return bot.send_message(msg.chat.id, "❌ المخزن فارغ حالياً أو تم بيع كل المنتجات.")
    
    text = "📦 **المنتجات المتوفرة في المخزن:**\n\n"
    for n in names:
        count = stock.count_documents({"name": n, "sold": False})
        text += f"▪️ `{n}` (الكمية: {count})\n"
        
    text += "\n👉 أرسل **اسم المنتج** (انسخه من القائمة بالأعلى) لإدارته:"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, show_stock_item_panel)

def show_stock_item_panel(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    name = msg.text.strip()
    
    count = stock.count_documents({"name": name, "sold": False})
    item = stock.find_one({"name": name, "sold": False})
    
    if not item:
        return bot.send_message(msg.chat.id, "❌ المنتج غير موجود أو نفذت كميته. تأكد من نسخ الاسم بشكل صحيح.")
        
    text = f"📦 المنتج: `{name}`\n💰 السعر الحالي: {item['price']}\n📉 التكلفة: {item.get('cost', 0)}\n📊 الكمية المتوفرة: {count}"
    
    if msg.chat.id not in temp_admin_data: temp_admin_data[msg.chat.id] = {}
    temp_admin_data[msg.chat.id]["mng_item_name"] = name
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💰 تعديل السعر", callback_data="stk_price"))
    kb.add(types.InlineKeyboardButton("➖ حذف كمية من الأكواد", callback_data="stk_delqty"))
    kb.add(types.InlineKeyboardButton("❌ حذف المنتج بالكامل", callback_data="stk_delall"))
    
    bot.send_message(msg.chat.id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("stk_"))
def stk_action(call):
    action = call.data.split("_")[1]
    data = temp_admin_data.get(call.message.chat.id)
    
    if not data or "mng_item_name" not in data:
        return bot.answer_callback_query(call.id, "❌ انتهت الجلسة، الرجاء إعادة طلب المخزون.", show_alert=True)
        
    name = data["mng_item_name"]
    
    if action == "price":
        msg = bot.send_message(call.message.chat.id, f"أرسل السعر الجديد للمنتج `{name}`:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, update_stock_price, name)
        bot.answer_callback_query(call.id)
        
    elif action == "delqty":
        msg = bot.send_message(call.message.chat.id, f"أرسل عدد الأكواد المراد حذفها من المنتج `{name}`:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, delete_stock_qty, name)
        bot.answer_callback_query(call.id)
        
    elif action == "delall":
        res = stock.delete_many({"name": name, "sold": False})
        bot.answer_callback_query(call.id, f"✅ تم حذف {res.deleted_count} كود.")
        bot.edit_message_text(f"✅ تم حذف المنتج `{name}` بالكامل ({res.deleted_count} كود) من المخزن.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        if call.message.chat.id in temp_admin_data and "mng_item_name" in temp_admin_data[call.message.chat.id]:
            del temp_admin_data[call.message.chat.id]["mng_item_name"]

def update_stock_price(msg, name):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        new_price = float(msg.text.strip())
        res = stock.update_many({"name": name, "sold": False}, {"$set": {"price": new_price}})
        bot.send_message(msg.chat.id, f"✅ تم تحديث سعر `{name}` ليصبح {new_price} لـ {res.modified_count} كود.", parse_mode="Markdown")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ، يرجى إرسال أرقام فقط.")

def delete_stock_qty(msg, name):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        qty_to_delete = int(msg.text.strip())
        docs_to_delete = list(stock.find({"name": name, "sold": False}).limit(qty_to_delete))
        
        if not docs_to_delete:
            return bot.send_message(msg.chat.id, "❌ لا توجد أكواد متاحة للحذف.")
        
        doc_ids = [d['_id'] for d in docs_to_delete]
        res = stock.delete_many({"_id": {"$in": doc_ids}})
        bot.send_message(msg.chat.id, f"✅ تم حذف {res.deleted_count} كود من منتج `{name}` بنجاح.", parse_mode="Markdown")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ، يرجى إرسال رقم صحيح.")

# ===== INVOICE LOG =====
@bot.message_handler(func=lambda m: m.text == "🧾 سجل الفواتير")
def invoices_log(msg):
    if msg.chat.id not in ADMIN_IDS: return
    history = list(transactions.find({"type": "شراء", "order_id": {"$exists": True}}).sort("_id", -1).limit(40))
    if not history: return bot.send_message(msg.chat.id, "لا توجد فواتير مبيعات حتى الآن.")
    
    text = "🧾 **سجل آخر 40 فاتورة:**\n\n"
    for t in history:
        phone_display = t.get('phone', 'بدون')
        qty = t.get('quantity', 1)
        text += f"▪️ #{t['order_id']} | 📱 `{phone_display}` | 🛒 {t['item_name']} (x{qty}) | 💰 {t['price']}\n"
        
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users_list(msg):
    if msg.chat.id not in ADMIN_IDS: return
    text = "👥 قائمة آخر المستخدمين:\n\n"
    for u in users.find().sort("join", -1).limit(30):
        stat = "✅" if u.get('status') == 'active' else "❄️"
        text += f"📱 `{u.get('phone', 'بدون رقم')}` | الرصيد: {u.get('balance',0)} | {stat}\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== MANAGE CUSTOMER =====
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def manage_customer_cmd(msg):
    if msg.chat.id not in ADMIN_IDS: return
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
        users.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
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

# ===== ADD PRODUCT (TEMPLATE & MANUAL) =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add_product(msg):
    if msg.chat.id not in ADMIN_IDS: return
    
    text = "اختر طريقة إضافة المنتجات:\n\n"
    text += "📁 **الطريقة الأولى (موصى بها): القالب الشامل**\n"
    text += "قم بتحميل القالب المرفق، املأه بالمنتجات والأكواد (يمكنك إضافة أقسام ومنتجات مختلفة في نفس الملف دفعة واحدة)، ثم أعد رفعه هنا.\n\n"
    text += "✍️ **الطريقة الثانية: الإضافة اليدوية لمنتج واحد**\n"
    text += "أرسل بيانات المنتج بالتنسيق التالي:\n`القسم:الفئة:الاسم:السعر:التكلفة`"
    
    try:
        template = generate_products_template()
        bot.send_document(msg.chat.id, template, caption=text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, handle_add_product_choice)
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ: {e}")

def handle_add_product_choice(msg):
    if msg.text and msg.text in MENU_BUTTONS: 
        return bot.send_message(msg.chat.id, "تم الإلغاء.")
        
    if msg.document:
        if not msg.document.file_name.endswith('.xlsx'):
            return bot.send_message(msg.chat.id, "❌ يرجى رفع ملف بصيغة .xlsx فقط.")
        
        bot.send_message(msg.chat.id, "⏳ جاري قراءة القالب واستيراد المنتجات...")
        try:
            file_info = bot.get_file(msg.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_stream = io.BytesIO(downloaded_file)
            
            wb = openpyxl.load_workbook(file_stream)
            ws = wb.active
            
            docs = []
            errors = 0
            
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0: continue # تخطي صف العناوين
                if not any(row): continue # تخطي الصفوف الفارغة بالكامل
                
                try:
                    cat = str(row[0]).strip() if row[0] else ""
                    sub = str(row[1]).strip() if row[1] else ""
                    name = str(row[2]).strip() if row[2] else ""
                    price = float(row[3]) if row[3] is not None else 0.0
                    cost = float(row[4]) if row[4] is not None else 0.0
                    code_val = str(row[5]).strip() if row[5] else ""
                    serial_val = str(row[6]).strip() if len(row) > 6 and row[6] else "بدون_تسلسلي"
                    
                    if not all([cat, sub, name, code_val]):
                        errors += 1
                        continue
                        
                    docs.append({
                        "category": cat, "subcategory": sub, "name": name,
                        "price": price, "cost": cost, 
                        "code": code_val, "serial": serial_val, "sold": False
                    })
                except Exception as e:
                    errors += 1
                    continue
            
            if docs:
                stock.insert_many(docs)
                msg_res = f"✅ تم استيراد وإضافة {len(docs)} كود للمتجر بنجاح!"
                if errors > 0: 
                    msg_res += f"\n⚠️ تم تخطي {errors} صف لوجود بيانات ناقصة أو غير صحيحة (تأكد من كتابة السعر والتكلفة كأرقام)."
                bot.send_message(msg.chat.id, msg_res)
            else:
                bot.send_message(msg.chat.id, "❌ لم يتم استيراد أي بيانات. تأكد من تعبئة القالب بشكل صحيح.")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء معالجة الملف:\n{e}")
            
    elif msg.text and ":" in msg.text:
        save_product_info(msg)
    else:
        bot.send_message(msg.chat.id, "❌ إدخال غير صالح. قم بطلب `➕ منتج` مرة أخرى.")

def save_product_info(msg):
    try:
        cat, sub, name, price, cost = msg.text.split(":")
        if msg.chat.id not in temp_admin_data: temp_admin_data[msg.chat.id] = {}
        temp_admin_data[msg.chat.id]["new_product"] = {
            "cat": cat.strip(), "sub": sub.strip(), "name": name.strip(),
            "price": float(price.strip()), "cost": float(cost.strip())
        }
        
        bot.send_message(
            msg.chat.id, 
            "✅ تم حفظ بيانات المنتج.\n\nالآن أرسل الأكواد كـ **رسالة نصية** (الكود:التسلسلي في كل سطر)."
        )
        bot.register_next_step_handler(msg, process_product_codes_manual)
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ في التنسيق. تأكد من وجود 5 عناصر مفصولة بـ (:)\n{e}")

def process_product_codes_manual(msg):
    if msg.text and msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    
    data = temp_admin_data.get(msg.chat.id, {}).get("new_product")
    if not data: return bot.send_message(msg.chat.id, "❌ حدث خطأ، يرجى إعادة المحاولة من زر (➕ منتج).")

    codes = []
    if msg.text:
        for line in msg.text.split("\n"):
            if line.strip():
                parts = line.split(":")
                code_val = parts[0].strip()
                serial_val = parts[1].strip() if len(parts) > 1 else "بدون_تسلسلي"
                codes.append({"code": code_val, "serial": serial_val})
        
    if not codes:
        return bot.send_message(msg.chat.id, "❌ لم يتم العثور على أكواد.")

    docs = []
    for c in codes:
        docs.append({
            "category": data['cat'], "subcategory": data['sub'], "name": data['name'],
            "price": data['price'], "cost": data['cost'], 
            "code": c['code'], "serial": c['serial'], "sold": False
        })
        
    stock.insert_many(docs)
    bot.send_message(msg.chat.id, f"✅ تم إضافة {len(docs)} كود بنجاح للمنتج [{data['name']}].")
    if msg.chat.id in temp_admin_data and "new_product" in temp_admin_data[msg.chat.id]:
        del temp_admin_data[msg.chat.id]["new_product"]

# ===== SET BALANCE =====
@bot.message_handler(func=lambda m: m.text == "💰 ضبط الرصيد")
def set_balance_cmd(msg):
    if msg.chat.id not in ADMIN_IDS: return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:الرصيد_الجديد)\nمثال: 0940719000:500.5")
    bot.register_next_step_handler(msg, do_set_balance)

def do_set_balance(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        phone_str, val_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            new_bal = float(val_str.strip())
            users.update_one({"_id": u["_id"]}, {"$set": {"balance": new_bal}})
            transactions.insert_one({
                "uid": u["_id"], "type": "ضبط رصيد", "amount": new_bal, 
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            bot.send_message(msg.chat.id, f"✅ تم ضبط رصيد العميل {u.get('phone')} ليصبح {new_bal}")
            bot.send_message(u["_id"], f"⚙️ تم تحديث رصيدك من قبل الإدارة ليصبح: {new_bal}")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== DIRECT CHARGE =====
@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if msg.chat.id not in ADMIN_IDS: return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:قيمة_الإضافة)\nمثال: 0940719000:50.75")
    bot.register_next_step_handler(msg, do_charge)

def do_charge(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        phone_str, amt_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            amt = float(amt_str.strip())
            users.update_one({"_id": u["_id"]}, {"$inc": {"balance": amt}})
            transactions.insert_one({
                "uid": u["_id"], "type": "شحن إضافي", "amount": amt, 
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            bot.send_message(msg.chat.id, f"✅ تم إضافة {amt} لرصيد العميل {u.get('phone')}")
            bot.send_message(u["_id"], f"🎁 تم إضافة {amt} لرصيدك من قِبل الإدارة")
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== GENERATE CARDS =====
@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def gen_cards(msg):
    if msg.chat.id not in ADMIN_IDS: return
    bot.send_message(msg.chat.id, "أرسل (العدد:القيمة)\nمثال: 10:15.5")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        count_str, val_str = msg.text.split(":")
        count = int(count_str)
        val = float(val_str)
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
    print("🚀 FULL ADMIN BOT STARTED")
    bot.infinity_polling()
