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
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

# ========= CONFIG =========
API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"

# المدير الأساسي
ADMIN_IDS = [1262656649] 

MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

# رابط جوجل شيت لتسجيل الفواتير
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzPrw8oANq8Aek6O6URoTU0kDVjb1ZtoVdYkhpqAqM6Nuws4ZmcPRC9JtoNZvWoMzUb/exec"

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]
transactions = db["transactions"]
counters = db["counters"]
admins_db = db["admins"]

MENU_BUTTONS = [
    "🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", 
    "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل", 
    "💰 ضبط الرصيد", "🧾 سجل الفواتير", "📦 إدارة المخزون", "📊 تقارير إكسيل", "💵 أسعار المستويات", "🏪 العودة للمتجر"
]

temp_admin_data = {}

# ========= HELPER FUNCTIONS =========
def is_admin(uid):
    if uid in ADMIN_IDS: return True
    if admins_db.find_one({"_id": uid}): return True
    return False

def get_all_admins():
    all_admins = list(ADMIN_IDS)
    for a in admins_db.find():
        if a["_id"] not in all_admins:
            all_admins.append(a["_id"])
    return all_admins

def check_user_access(uid):
    u = users.find_one({"_id": uid})
    if not u:
        bot.send_message(uid, "⚠️ النظام مغلق. أرسل /start للتسجيل أولاً.")
        return None
    if not u.get("name"):
        m = bot.send_message(uid, "يرجى كتابة اسمك الكريم أولاً للاستمرار:")
        bot.register_next_step_handler(m, process_name)
        return None
    if not u.get("phone"):
        bot.send_message(uid, "⚠️ يجب عليك مشاركة رقم هاتف حسابك أولاً.", reply_markup=contact_menu())
        return None
    if u.get("status") == "blocked":
        bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        return None
    if u.get("status") != "active":
        bot.send_message(uid, "❌ حسابك قيد المراجعة. برجاء الانتظار حتى تفعيل الإدارة.")
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
        {"_id": "order_id"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

def is_valid_val(val):
    if not val: return False
    if str(val).strip().lower() in ["", "none", "null", "بدون"]: return False
    return True

def generate_customer_excel_file(items_data, order_id, dt_now, product_name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Invoice_{order_id}"
    
    title_fill = PatternFill(start_color="002060", end_color="002060", fill_type="solid") 
    info_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid") 
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid") 
    
    title_font = Font(color="FFFFFF", bold=True, size=16)
    info_font = Font(bold=True, size=12)
    header_font = Font(color="FFFFFF", bold=True, size=13)
    center_aligned = Alignment(horizontal="center", vertical="center")
    
    has_serial = any(is_valid_val(d.get('serial')) for d in items_data)
    has_pin = any(is_valid_val(d.get('pin')) for d in items_data)
    has_opcode = any(is_valid_val(d.get('op_code')) for d in items_data)
    
    headers = ["م", "اسم المنتج", "كود الشحن"]
    if has_serial: headers.append("الرقم التسلسلي")
    if has_pin: headers.append("الرقم السري (PIN)")
    if has_opcode: headers.append("اوبريشن كود")
    
    total_cols = len(headers)
    last_col_letter = get_column_letter(total_cols)
    
    ws.merge_cells(f'A1:{last_col_letter}1')
    ws['A1'] = "شركة الأهرام للإتصالات والتقنية"
    ws['A1'].font = title_font
    ws['A1'].fill = title_fill
    ws['A1'].alignment = center_aligned
    ws.row_dimensions[1].height = 30
    
    ws.merge_cells(f'A2:{last_col_letter}2')
    ws['A2'] = f"رقم الفاتورة: #{order_id}   |   التاريخ: {dt_now}"
    ws['A2'].font = info_font
    ws['A2'].fill = info_fill
    ws['A2'].alignment = center_aligned
    ws.row_dimensions[2].height = 25
    
    ws.append([])
    ws.append(headers)
    
    for col_num in range(1, total_cols + 1):
        cell = ws.cell(row=4, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_aligned
    ws.row_dimensions[4].height = 20
        
    for idx, data in enumerate(items_data, 1):
        row = [idx, product_name, data['code']]
        if has_serial: row.append(data.get('serial', ''))
        if has_pin: row.append(data.get('pin', ''))
        if has_opcode: row.append(data.get('op_code', ''))
            
        ws.append(row)
        for col_num in range(1, total_cols + 1):
            ws.cell(row=ws.max_row, column=col_num).alignment = center_aligned
            
    for col in ws.columns:
        max_length = 0
        column_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        adjusted_width = (max_length + 4)
        if adjusted_width < 15: adjusted_width = 15
        if column_letter == 'A': adjusted_width = 8
        ws.column_dimensions[column_letter].width = adjusted_width
        
    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = f"Invoice_{order_id}.xlsx"
    return file_stream

def generate_products_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products_Template"
    ws.append(["القسم", "الفئة", "الاسم", "السعر 1", "السعر 2", "السعر 3", "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"])
    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = "Template_Products.xlsx"
    return file_stream

def generate_simple_excel(data_list, title):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Codes_Report"
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    headers = ["القسم", "الفئة", "الاسم", "السعر 1", "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"]
    ws.append(headers)
    
    for col_num in range(1, 9):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        
    for d in data_list:
        p1 = d.get('price_1', d.get('price', 0))
        ws.append([
            d.get('category', ''), d.get('subcategory', ''), d.get('name', ''), 
            p1, d.get('code', ''), d.get('serial', ''), d.get('pin', ''), d.get('op_code', '')
        ])
        
    for col in ws.columns:
        max_length = 0
        column_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length: max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column_letter].width = max_length + 4

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = f"{title}.xlsx"
    return file_stream

def generate_admin_report_excel(report_type, history_data, summary_data=None):
    wb = openpyxl.Workbook()
    ws1 = wb.active
    if report_type == "all":
        ws1.title = "سجل العمليات"
        ws1.append(["رقم الفاتورة", "التاريخ", "الاسم", "الهاتف", "نوع العملية", "البيان", "الكمية", "المبلغ"])
        for t in history_data:
            ws1.append([
                t.get("order_id", "-"), t.get("date", ""), t.get("user_name", "غير_مسجل"), t.get("phone", "بدون"),
                t.get("type", ""), t.get("item_name", "-"), t.get("quantity", "-"),
                t.get("price", t.get("amount", 0))
            ])
        if summary_data:
            ws2 = wb.create_sheet(title="ملخص مشتريات العملاء")
            ws2.append(["الاسم", "رقم الهاتف", "إجمالي المشتريات"])
            for phone, totals in summary_data.items():
                ws2.append([totals["name"], phone, totals["spent"]])
        file_name = "Comprehensive_Report.xlsx"
    elif report_type == "single":
        ws1.title = "تقرير العميل"
        ws1.append(["رقم الفاتورة", "التاريخ", "نوع العملية", "البيان", "الكمية", "المبلغ"])
        total_spent = 0
        for t in history_data:
            price_or_amount = t.get("price", t.get("amount", 0))
            ws1.append([
                t.get("order_id", "-"), t.get("date", ""), t.get("type", ""), 
                t.get("item_name", "-"), t.get("quantity", "-"), price_or_amount
            ])
            if t.get("type") == "شراء":
                total_spent += price_or_amount
        ws1.append([]) 
        ws1.append(["", "", "", "", "إجمالي المشتريات:", total_spent])
        file_name = "Customer_Report.xlsx"

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = file_name
    return file_stream

def filter_and_insert_codes(chat_id, extracted_data, product_info=None):
    if not extracted_data:
        return bot.send_message(chat_id, "❌ لم يتم العثور على بيانات صالحة للاستيراد.")
        
    bot.send_message(chat_id, "🔍 جاري فحص الأكواد للتأكد من عدم وجود تكرار...")
    
    codes_to_check = [str(d['code']).strip() for d in extracted_data]
    existing_docs = stock.find({"code": {"$in": codes_to_check}})
    existing_set = set([str(doc['code']).strip() for doc in existing_docs])
    
    valid_docs = []
    duplicate_docs = []
    seen_in_this_batch = set()
    
    for d in extracted_data:
        if product_info: d.update(product_info)
        c = str(d['code']).strip()
        if c in existing_set or c in seen_in_this_batch:
            duplicate_docs.append(d)
        else:
            seen_in_this_batch.add(c)
            d["sold"] = False
            valid_docs.append(d)
            
    bot.send_message(chat_id, f"📊 **نتيجة الإضافة النهائية:**\n\n✅ الأكواد المقبولة: {len(valid_docs)}\n❌ الأكواد المكررة: {len(duplicate_docs)}")
            
    if valid_docs:
        stock.insert_many(valid_docs)
        f1 = generate_simple_excel(valid_docs, "Accepted_Codes")
        bot.send_document(chat_id, f1, caption="📁 الأكواد المقبولة (التي تم إضافتها للمتجر).")
        
    if duplicate_docs:
        f2 = generate_simple_excel(duplicate_docs, "Rejected_Duplicate_Codes")
        bot.send_document(chat_id, f2, caption="⚠️ الأكواد المكررة (تم رفضها ومسحها لمنع التكرار).")

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
    kb.add("📊 تقارير إكسيل", "💵 أسعار المستويات") 
    kb.add("🏪 العودة للمتجر")
    return kb

# ========= HIDDEN COMMANDS =========
@bot.message_handler(commands=['FRP', 'frp'])
def frp_cmd(msg):
    if msg.chat.id not in ADMIN_IDS: return bot.send_message(msg.chat.id, "❌ هذه الصلاحية للمدير الأساسي فقط.")
    bot.send_message(msg.chat.id, "⚠️ **تحذير خطير جداً** ⚠️\n\nأنت على وشك عمل فورمات كامل للمتجر.\nللتأكيد، أرسل:\n`تأكيد الحذف النهائي`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_frp)

def process_frp(msg):
    if msg.text == "تأكيد الحذف النهائي":
        users.delete_many({})
        stock.delete_many({})
        cards.delete_many({})
        transactions.delete_many({})
        counters.delete_many({})
        admins_db.delete_many({})
        bot.send_message(msg.chat.id, "✅ تم عمل فورمات للمتجر بنجاح.")
    else: bot.send_message(msg.chat.id, "❌ تم إلغاء الفورمات.")

@bot.message_handler(commands=['ADD', 'add'])
def add_admin_cmd(msg):
    if msg.chat.id not in ADMIN_IDS: return bot.send_message(msg.chat.id, "❌ هذه الصلاحية للمدير الأساسي فقط.")
    bot.send_message(msg.chat.id, "أرسل الـ ID الخاص بالشخص المراد تعيينه كأدمن إضافي:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    try:
        new_admin_id = int(msg.text.strip())
        admins_db.update_one({"_id": new_admin_id}, {"$set": {"added_by": msg.chat.id, "date": datetime.datetime.now()}}, upsert=True)
        bot.send_message(msg.chat.id, f"✅ تم إضافة الأدمن `{new_admin_id}` بنجاح.", parse_mode="Markdown")
        bot.send_message(new_admin_id, "🎉 تمت ترقيتك لتصبح مشرفاً في المتجر!\nأرسل /admin لفتح لوحة التحكم.")
    except: bot.send_message(msg.chat.id, "❌ خطأ، يرجى إرسال أرقام فقط (ID).")

@bot.message_handler(commands=['Block', 'block'])
def block_user_cmd(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "أرسل رقم هاتف العميل المراد حظره:")
    bot.register_next_step_handler(msg, process_block_user)

def process_block_user(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    users.update_one({"_id": u["_id"]}, {"$set": {"status": "blocked"}})
    bot.send_message(msg.chat.id, f"✅ تم حظر العميل {u.get('phone')} بنجاح.")
    try: bot.send_message(u["_id"], "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
    except: pass

# ========= START & CONTACT & NAME HANDLER =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({"_id": uid, "name": None, "phone": None, "balance": 0.0, "status": "frozen", "tier": 1, "failed_attempts": 0, "join": datetime.datetime.now()})
        u = {"name": None, "phone": None, "status": "frozen", "tier": 1}

    if not u.get("name"):
        m = bot.send_message(uid, "👋 مرحباً بك في المتجر!\n\nللبدء، يرجى كتابة **اسمك** (أو اسم محلك):", parse_mode="Markdown")
        bot.register_next_step_handler(m, process_name)
    elif not u.get("phone"):
        bot.send_message(uid, f"أهلاً بك يا {u.get('name')}! يرجى مشاركة رقم هاتفك لاستكمال التسجيل بالضغط على الزر أدناه.", reply_markup=contact_menu())
    else:
        if u.get("status") == "blocked": bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        elif u.get("status") == "frozen": bot.send_message(uid, "حسابك الآن (قيد المراجعة). يرجى الانتظار حتى تقوم الإدارة بتفعيل حسابك.")
        else: bot.send_message(uid, "👋 مرحباً بك في المتجر", reply_markup=menu())

def process_name(msg):
    if msg.text and msg.text.startswith('/'): 
        m = bot.send_message(msg.chat.id, "يرجى كتابة اسم صحيح دون رموز:")
        bot.register_next_step_handler(m, process_name)
        return
    name = msg.text.strip()
    users.update_one({"_id": msg.chat.id}, {"$set": {"name": name}})
    bot.send_message(msg.chat.id, f"تشرفنا بك يا {name}!\nالآن يرجى مشاركة رقم هاتفك بالضغط على الزر أدناه 📱", reply_markup=contact_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(msg):
    uid = msg.chat.id
    if msg.contact.user_id != uid:
        return bot.send_message(uid, "❌ الرجاء إرسال رقم هاتفك الخاص المرتبط بتيليجرام.", reply_markup=contact_menu())
    
    phone = msg.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone, "tier": 1}}) 
    u = users.find_one({"_id": uid})
    name = u.get("name", "غير مسجل")
    
    if u.get("status") == "frozen":
        bot.send_message(uid, f"✅ تم التسجيل بنجاح يا {name}.\n\n⚠️ حسابك الآن (قيد المراجعة). يرجى الانتظار حتى تقوم الإدارة بتفعيل حسابك.", reply_markup=types.ReplyKeyboardRemove())
        
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"),
               types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}"))
        for admin_id in get_all_admins():
            try: bot.send_message(admin_id, f"🆕 **تسجيل مستخدم جديد! (قيد المراجعة)**\n\n🆔 ID: `{uid}`\n📛 الاسم: {name}\n📱 الهاتف: `{phone}`\n\nيرجى مراجعة الحساب وتحديد حالته:", reply_markup=kb, parse_mode="Markdown")
            except: pass
    else:
        bot.send_message(uid, f"✅ حسابك نشط وجاهز.", reply_markup=menu())

# ========= ACCOUNT & REPORTS =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    if not u or not u.get("name"): return bot.send_message(msg.chat.id, "⚠️ أرسل /start لتسجيل اسمك أولاً.")
    if not u.get("phone"): return bot.send_message(msg.chat.id, "⚠️ أرسل رقم هاتفك أولاً.", reply_markup=contact_menu())
    if u.get("status") == "blocked": return bot.send_message(msg.chat.id, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")

    status_text = "نشط ✅" if u.get("status") == "active" else "مجمد ❄️"
    tier = u.get("tier", 1)
    tier_str = "مستوى 1 🥉" if tier == 1 else ("مستوى 2 🥈" if tier == 2 else "مستوى 3 🥇")
    
    text = f"👤 **بيانات حسابك**\n\n📛 الاسم: {u.get('name')}\n🆔 ID: `{msg.chat.id}`\n📱 الهاتف: `{u.get('phone')}`\n💰 رصيدك: **{u.get('balance', 0.0)}**\n🎚️ تصنيف الحساب: {tier_str}\nحالة الحساب: {status_text}"
    
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
    if not u: return bot.answer_callback_query(call.id, "حسابك موقوف.", show_alert=True)

    if call.data == "client_purchases":
        history = list(transactions.find({"uid": uid, "type": "شراء"}).sort("_id", -1).limit(10))
        if not history: return bot.answer_callback_query(call.id, "لا توجد مشتريات.", show_alert=True)
        report_text = "🛒 **آخر 10 مشتريات:**\n\n"
        for t in history:
            report_text += f"▪️ {t['date']} | فاتورة #{t.get('order_id', 'N/A')} | {t['item_name']} (x{t.get('quantity', 1)}) | السعر: {t['price']}\n"
            
    elif call.data == "client_statement":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(20))
        if not history: return bot.answer_callback_query(call.id, "لا توجد عمليات.", show_alert=True)
        report_text = "🧾 **كشف حساب (آخر 20):**\n\n"
        for t in history:
            if t["type"] == "شراء": report_text += f"🔴 خصم | {t['date']} | شراء {t['item_name']} | -{t['price']}\n"
            else: report_text += f"🟢 إضافة | {t['date']} | {t['type']} | +{t['amount']}\n"
                
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
        if u and u.get("status") == "blocked": bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        else: bot.send_message(uid, "❌ حسابك مجمد. لا يمكنك الشحن.")
        return

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

    new_bal = u.get("balance", 0.0) + float(card["value"])
    users.update_one({"_id": uid}, {"$set": {"balance": new_bal, "failed_attempts": 0}})
    transactions.insert_one({"uid": uid, "user_name": u.get("name"), "type": "شحن كارت", "amount": float(card["value"]), "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(uid, f"✅ تم شحن رصيدك بقيمة {card['value']} بنجاح")
    
    for admin_id in get_all_admins():
        try: bot.send_message(admin_id, f"💳 **عملية شحن كارت!**\n\n📛 العميل: {u.get('name')}\n📱 الهاتف: `{u.get('phone')}`\n💰 قيمة الشحن: **{card['value']}**\n💵 الرصيد الجديد: **{new_bal}**", parse_mode="Markdown")
        except: pass

# ========= BULK PRICE UPDATE =========
@bot.message_handler(func=lambda m: m.text == "💵 أسعار المستويات")
def edit_tier_prices_cmd(msg):
    if not is_admin(msg.chat.id): return
    pipeline = [
        {"$match": {"sold": False}},
        {"$group": {
            "_id": "$name",
            "cat": {"$first": "$category"},
            "sub": {"$first": "$subcategory"},
            "p1": {"$first": "$price_1"},
            "p2": {"$first": "$price_2"},
            "p3": {"$first": "$price_3"},
            "old_p": {"$first": "$price"}
        }}
    ]
    products = list(stock.aggregate(pipeline))
    if not products: return bot.send_message(msg.chat.id, "❌ المخزن فارغ أو لا توجد منتجات متاحة للبيع.")
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تعديل الأسعار"
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    headers = ["الاسم (لا تقم بتعديله)", "القسم", "الفئة", "السعر 1 (🥉)", "السعر 2 (🥈)", "السعر 3 (🥇)"]
    ws.append(headers)
    for col_num in range(1, 7):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
    
    for p in products:
        p1 = p.get("p1") if p.get("p1") is not None else p.get("old_p", 0)
        p2 = p.get("p2") if p.get("p2") is not None else p1
        p3 = p.get("p3") if p.get("p3") is not None else p1
        ws.append([p["_id"], p.get("cat"), p.get("sub"), p1, p2, p3])
        
    for col in ws.columns:
        max_length = 0
        column_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length: max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column_letter].width = max_length + 4

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = "Prices_Update.xlsx"
    
    m = bot.send_document(msg.chat.id, file_stream, caption="📁 **أداة تعديل الأسعار المجمعة**\n\n1️⃣ قم بتحميل الملف.\n2️⃣ عدل الأسعار في الأعمدة الثلاثة الأخيرة (السعر 1، 2، 3).\n3️⃣ أعد رفع الملف هنا.\n\n⚠️ **ملاحظة هامة:** لا تقم بتغيير عمود (الاسم) أبداً.")
    bot.register_next_step_handler(m, process_bulk_price_update)

def process_bulk_price_update(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    if not msg.document or not msg.document.file_name.endswith(".xlsx"):
        return bot.send_message(msg.chat.id, "❌ يرجى رفع ملف إكسيل بصيغة .xlsx فقط.")
    
    bot.send_message(msg.chat.id, "⏳ جاري تحديث أسعار المتجر بالكامل...")
    try:
        file_info = bot.get_file(msg.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        wb = openpyxl.load_workbook(io.BytesIO(downloaded))
        ws = wb.active
        
        updated_count = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0: continue
            name = str(row[0]).strip() if row[0] else None
            if not name: continue
            
            p1 = float(row[3]) if row[3] is not None else 0
            p2 = float(row[4]) if row[4] is not None else p1
            p3 = float(row[5]) if row[5] is not None else p1
            
            res = stock.update_many({"name": name, "sold": False}, {"$set": {"price_1": p1, "price_2": p2, "price_3": p3}})
            if res.modified_count > 0: updated_count += 1
        
        bot.send_message(msg.chat.id, f"✅ تمت العملية بنجاح!\nتم تحديث أسعار **{updated_count}** نوع من المنتجات.")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء التحديث:\n{e}")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    u = check_user_access(msg.chat.id)
    if not u: return
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
    uid = call.message.chat.id
    u = check_user_access(uid)
    if not u: return
    tier = u.get("tier", 1)
    
    _, cat_name, sub_name = call.data.split("_",2)
    items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))
    available_count = len(items)
    
    if available_count < 10:
        return bot.answer_callback_query(call.id, "❌ الكمية المتوفرة أقل من الحد الأدنى للشراء (10 أكواد).", show_alert=True)
        
    item = items[0]
    p1 = item.get("price_1", item.get("price", 0))
    p2 = item.get("price_2", p1)
    p3 = item.get("price_3", p1)
    user_price = p1 if tier == 1 else (p2 if tier == 2 else p3)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 طلب شراء", callback_data=f"buy_{item['_id']}"))
    bot.send_message(uid, f"📦 المنتج: {item['name']}\n💰 السعر الخاص بك: {user_price}\n📊 المتوفر: {available_count}\n⚠️ أقل كمية للطلب: 10 ومضاعفاتها", reply_markup=kb)

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
    
    user_fresh = users.find_one({"_id": uid})
    tier = user_fresh.get("tier", 1)
    p1 = item_ref.get("price_1", item_ref.get("price", 0))
    p2 = item_ref.get("price_2", p1)
    p3 = item_ref.get("price_3", p1)
    user_price = p1 if tier == 1 else (p2 if tier == 2 else p3)
    
    total_price = qty * user_price

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
        "order_id": order_id, "uid": uid, "user_name": user_fresh.get("name"), "phone": user_fresh.get('phone'), 
        "type": "شراء", "item_name": name, "quantity": qty, "price": total_price, "date": dt_now
    })

    if SHEET_WEBHOOK_URL and SHEET_WEBHOOK_URL.startswith("http"):
        try: requests.post(SHEET_WEBHOOK_URL, json={"order_id": order_id, "date": dt_now, "phone": user_fresh.get('phone'), "item_name": f"{name} (x{qty})", "price": total_price}, timeout=3)
        except: pass

    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n💰 إجمالي المخصوم: {total_price}\n\nجاري تجهيز الفاتورة وملف الأكواد...", parse_mode="Markdown")

    for admin_id in get_all_admins():
        try: bot.send_message(admin_id, f"🛒 **شراء جديد بالجملة** | فاتورة #{order_id}\n📛 العميل: {user_fresh.get('name')}\n📱 الهاتف: {user_fresh.get('phone')}\n🎚️ مستوى العميل: {tier}\n📦 المنتج: {name} (الكمية: {qty})\n💰 المدفوع: {total_price}", parse_mode="Markdown")
        except: pass

    purchased_items_data = [{'code': d['code'], 'serial': d.get('serial', ''), 'pin': d.get('pin', ''), 'op_code': d.get('op_code', '')} for d in available_docs]
    file_stream = generate_customer_excel_file(purchased_items_data, order_id, dt_now, name)
    bot.send_document(uid, document=file_stream, caption=f"📁 فاتورة الأكواد | رقم #{order_id}")
    
    for admin_id in get_all_admins():
        try:
            file_stream.seek(0)
            bot.send_document(admin_id, document=file_stream, caption=f"📁 نسخة للإدارة | فاتورة #{order_id}")
        except: pass

    remaining_stock = stock.count_documents({"name": name, "sold": False})
    if remaining_stock <= 30:
        for admin_id in get_all_admins():
            try: bot.send_message(admin_id, f"⚠️ **تنبيه نقص مخزون** ⚠️\n\nالمنتج: `{name}`\nالكمية المتبقية: **{remaining_stock}** كود فقط!\nيرجى إعادة تعبئة المخزون قريباً.", parse_mode="Markdown")
            except: pass

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "👑 لوحة تحكم الإدارة", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def back_to_store(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل", reply_markup=menu())

# ===== MANAGE CUSTOMER & TIERS =====
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def manage_customer_cmd(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "أرسل رقم هاتف العميل (أو الـ ID):")
    bot.register_next_step_handler(msg, show_customer_panel)

def show_customer_panel(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "تم الإلغاء.")
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    render_customer_panel(u["_id"], msg.chat.id)

def render_customer_panel(uid, chat_id, message_id=None):
    u = users.find_one({"_id": uid})
    if not u: return
    stat = u.get("status")
    name = u.get("name", "غير مسجل")
    tier = u.get("tier", 1)
    tier_str = "مستوى 1 🥉" if tier == 1 else ("مستوى 2 🥈" if tier == 2 else "مستوى 3 🥇")
    
    if stat == "blocked": stat_ar = "محظور نهائياً 🚫"
    elif stat == "active": stat_ar = "نشط ✅"
    else: stat_ar = "مجمد (قيد المراجعة) ❄️"
    
    info = f"👤 بيانات العميل:\n📛 الاسم: {name}\nID: `{uid}`\nالهاتف: `{u.get('phone', 'بدون_رقم')}`\nالرصيد: {u.get('balance',0)}\n🎚️ مستوى الأسعار: {tier_str}\nالحالة: {stat_ar}"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    if stat == "active":
        kb.add(types.InlineKeyboardButton("❄️ تجميد", callback_data=f"freeze_{uid}"),
               types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}"))
    elif stat == "frozen":
        kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"),
               types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}"))
    elif stat == "blocked":
        kb.add(types.InlineKeyboardButton("✅ فك الحظر والتفعيل", callback_data=f"activate_{uid}"))
        
    kb.add(types.InlineKeyboardButton("🎚️ تغيير المستوى", callback_data=f"chgtier_{uid}"))
    kb.add(types.InlineKeyboardButton("📊 تقرير العمليات", callback_data=f"report_{uid}"))
    
    if message_id:
        try: bot.edit_message_text(info, chat_id, message_id, reply_markup=kb, parse_mode="Markdown")
        except: pass
    else:
        bot.send_message(chat_id, info, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith(("freeze_", "activate_", "block_", "report_", "chgtier_", "settier_", "backcust_")))
def admin_customer_actions(call):
    parts = call.data.split("_")
    action = parts[0]
    
    if action == "settier":
        level = int(parts[1])
        uid = int(parts[2])
        users.update_one({"_id": uid}, {"$set": {"tier": level}})
        bot.answer_callback_query(call.id, f"✅ تم تغيير مستوى العميل إلى المستوى {level}")
        render_customer_panel(uid, call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, f"🎉 تم ترقية مستوى أسعارك في المتجر إلى (المستوى {level}) من قبل الإدارة.")
        except: pass
        return
        
    uid = int(parts[1])
    
    if action == "chgtier":
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(
            types.InlineKeyboardButton("مستوى 1 🥉", callback_data=f"settier_1_{uid}"),
            types.InlineKeyboardButton("مستوى 2 🥈", callback_data=f"settier_2_{uid}"),
            types.InlineKeyboardButton("مستوى 3 🥇", callback_data=f"settier_3_{uid}")
        )
        kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"backcust_{uid}"))
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
        return
    elif action == "backcust":
        render_customer_panel(uid, call.message.chat.id, call.message.message_id)
        return
    elif action == "report":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(15))
        if not history: return bot.answer_callback_query(call.id, "لا يوجد عمليات.", show_alert=True)
        report_text = f"📊 آخر عمليات العميل `{uid}`:\n\n"
        for t in history:
            if t["type"] == "شراء": report_text += f"▪️ {t['date']} | 🛒 {t['item_name
