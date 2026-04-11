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
def safe_str(text):
    """دالة لتنظيف النصوص من رموز الماركدوان التي تسبب أخطاء في تيليجرام"""
    if not text: return "بدون"
    return str(text).replace("_", " ").replace("*", "").replace("`", "").replace("[", "").replace("]", "")

def is_admin(uid):
    if uid in ADMIN_IDS:
        return True
    if admins_db.find_one({"_id": uid}):
        return True
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
        if u:
            return u
            
    clean_phone = text.replace("+", "").replace(" ", "").lstrip("0")
    if clean_phone:
        u = users.find_one({"phone": {"$regex": f"{clean_phone}$"}}) 
        if u:
            return u
            
    return None

def get_next_order_id():
    doc = counters.find_one_and_update(
        {"_id": "order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

def is_valid_val(val):
    if not val:
        return False
    if str(val).strip().lower() in ["", "none", "null", "بدون"]:
        return False
    return True

# ========= EXCEL GENERATORS =========
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
    if has_serial:
        headers.append("الرقم التسلسلي")
    if has_pin:
        headers.append("الرقم السري (PIN)")
    if has_opcode:
        headers.append("اوبريشن كود")
    
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
        if has_serial:
            row.append(data.get('serial', ''))
        if has_pin:
            row.append(data.get('pin', ''))
        if has_opcode:
            row.append(data.get('op_code', ''))
            
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
            except:
                pass
        adjusted_width = (max_length + 4)
        if adjusted_width < 15:
            adjusted_width = 15
        if column_letter == 'A':
            adjusted_width = 8
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
    ws.append([
        "القسم", "الفئة", "الاسم", "السعر 1", "السعر 2", "السعر 3", 
        "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"
    ])
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
    
    headers = [
        "القسم", "الفئة", "الاسم", "السعر 1", 
        "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"
    ]
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
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
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
                t.get("order_id", "-"), 
                t.get("date", ""), 
                t.get("user_name", "غير_مسجل"), 
                t.get("phone", "بدون"),
                t.get("type", ""), 
                t.get("item_name", "-"), 
                t.get("quantity", "-"),
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
                t.get("order_id", "-"), 
                t.get("date", ""), 
                t.get("type", ""), 
                t.get("item_name", "-"), 
                t.get("quantity", "-"), 
                price_or_amount
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
        bot.send_message(chat_id, "❌ لم يتم العثور على بيانات صالحة للاستيراد.")
        return
        
    bot.send_message(chat_id, "🔍 جاري فحص الأكواد للتأكد من عدم وجود تكرار...")
    
    codes_to_check = [str(d['code']).strip() for d in extracted_data]
    existing_docs = stock.find({"code": {"$in": codes_to_check}})
    existing_set = set()
    for doc in existing_docs:
        existing_set.add(str(doc['code']).strip())
    
    valid_docs = []
    duplicate_docs = []
    seen_in_this_batch = set()
    
    for d in extracted_data:
        if product_info:
            d.update(product_info)
        c = str(d['code']).strip()
        if c in existing_set or c in seen_in_this_batch:
            duplicate_docs.append(d)
        else:
            seen_in_this_batch.add(c)
            d["sold"] = False
            valid_docs.append(d)
            
    bot.send_message(
        chat_id, 
        f"📊 **نتيجة الإضافة النهائية:**\n\n✅ الأكواد المقبولة: {len(valid_docs)}\n❌ الأكواد المكررة: {len(duplicate_docs)}"
    )
            
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
    if msg.chat.id not in ADMIN_IDS:
        bot.send_message(msg.chat.id, "❌ هذه الصلاحية للمدير الأساسي فقط.")
        return
    bot.send_message(
        msg.chat.id, 
        "⚠️ **تحذير خطير جداً** ⚠️\n\nأنت على وشك عمل فورمات كامل للمتجر.\nللتأكيد، أرسل:\n`تأكيد الحذف النهائي`", 
        parse_mode="Markdown"
    )
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
    else:
        bot.send_message(msg.chat.id, "❌ تم إلغاء الفورمات.")

@bot.message_handler(commands=['ADD', 'add'])
def add_admin_cmd(msg):
    if msg.chat.id not in ADMIN_IDS:
        bot.send_message(msg.chat.id, "❌ هذه الصلاحية للمدير الأساسي فقط.")
        return
    bot.send_message(msg.chat.id, "أرسل الـ ID الخاص بالشخص المراد تعيينه كأدمن إضافي:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        new_admin_id = int(msg.text.strip())
        admins_db.update_one(
            {"_id": new_admin_id}, 
            {"$set": {"added_by": msg.chat.id, "date": datetime.datetime.now()}}, 
            upsert=True
        )
        bot.send_message(msg.chat.id, f"✅ تم إضافة الأدمن `{new_admin_id}` بنجاح.", parse_mode="Markdown")
        bot.send_message(new_admin_id, "🎉 تمت ترقيتك لتصبح مشرفاً في المتجر!\nأرسل /admin لفتح لوحة التحكم.")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ، يرجى إرسال أرقام فقط (ID).")

@bot.message_handler(commands=['Block', 'block'])
def block_user_cmd(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل رقم هاتف العميل المراد حظره:")
    bot.register_next_step_handler(msg, process_block_user)

def process_block_user(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    u = find_customer(msg.text)
    if not u:
        bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
        return
    users.update_one({"_id": u["_id"]}, {"$set": {"status": "blocked"}})
    bot.send_message(msg.chat.id, f"✅ تم حظر العميل {u.get('phone')} بنجاح.")
    try:
        bot.send_message(u["_id"], "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
    except Exception:
        pass

# ========= START & CONTACT & NAME HANDLER =========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({
            "_id": uid, 
            "name": None, 
            "phone": None, 
            "balance": 0.0, 
            "status": "frozen", 
            "tier": 1, 
            "failed_attempts": 0, 
            "join": datetime.datetime.now()
        })
        u = {"name": None, "phone": None, "status": "frozen", "tier": 1}

    if not u.get("name"):
        m = bot.send_message(uid, "👋 مرحباً بك في المتجر!\n\nللبدء، يرجى كتابة **اسمك** (أو اسم محلك):", parse_mode="Markdown")
        bot.register_next_step_handler(m, process_name)
    elif not u.get("phone"):
        bot.send_message(uid, f"أهلاً بك يا {safe_str(u.get('name'))}! يرجى مشاركة رقم هاتفك لاستكمال التسجيل بالضغط على الزر أدناه.", reply_markup=contact_menu())
    else:
        if u.get("status") == "blocked":
            bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        elif u.get("status") == "frozen":
            bot.send_message(uid, "حسابك الآن (قيد المراجعة). يرجى الانتظار حتى تقوم الإدارة بتفعيل حسابك.")
        else:
            bot.send_message(uid, "👋 مرحباً بك في المتجر", reply_markup=menu())

def process_name(msg):
    if msg.text and msg.text.startswith('/'): 
        m = bot.send_message(msg.chat.id, "يرجى كتابة اسم صحيح دون رموز:")
        bot.register_next_step_handler(m, process_name)
        return
        
    name = msg.text.strip()
    users.update_one({"_id": msg.chat.id}, {"$set": {"name": name}})
    bot.send_message(
        msg.chat.id, 
        f"تشرفنا بك يا {safe_str(name)}!\nالآن يرجى مشاركة رقم هاتفك بالضغط على الزر أدناه 📱", 
        reply_markup=contact_menu()
    )

@bot.message_handler(content_types=['contact'])
def handle_contact(msg):
    uid = msg.chat.id
    if msg.contact.user_id != uid:
        bot.send_message(uid, "❌ الرجاء إرسال رقم هاتفك الخاص المرتبط بتيليجرام.", reply_markup=contact_menu())
        return
    
    phone = msg.contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone, "tier": 1}})
    u = users.find_one({"_id": uid})
    safe_name = safe_str(u.get("name"))
    
    if u.get("status") == "frozen":
        bot.send_message(
            uid, 
            f"✅ تم التسجيل بنجاح يا {safe_name}.\n\n⚠️ حسابك الآن (قيد المراجعة). يرجى الانتظار حتى تقوم الإدارة بتفعيل حسابك.", 
            reply_markup=types.ReplyKeyboardRemove()
        )
        
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"),
            types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}")
        )
        for admin_id in get_all_admins():
            try:
                bot.send_message(
                    admin_id, 
                    f"🆕 **تسجيل مستخدم جديد! (قيد المراجعة)**\n\n🆔 ID: `{uid}`\n📛 الاسم: {safe_name}\n📱 الهاتف: `{phone}`\n\nيرجى مراجعة الحساب وتحديد حالته:", 
                    reply_markup=kb, 
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    else:
        bot.send_message(uid, f"✅ حسابك نشط وجاهز.", reply_markup=menu())

# ========= ACCOUNT & REPORTS =========
@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def account(msg):
    u = users.find_one({"_id": msg.chat.id})
    if not u or not u.get("name"):
        bot.send_message(msg.chat.id, "⚠️ أرسل /start لتسجيل اسمك أولاً.")
        return
    if not u.get("phone"):
        bot.send_message(msg.chat.id, "⚠️ أرسل رقم هاتفك أولاً.", reply_markup=contact_menu())
        return
    if u.get("status") == "blocked":
        bot.send_message(msg.chat.id, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        return

    status_text = "نشط ✅" if u.get("status") == "active" else "مجمد ❄️"
    tier = u.get("tier", 1)
    
    if tier == 1:
        tier_str = "مستوى 1 🥉"
    elif tier == 2:
        tier_str = "مستوى 2 🥈"
    else:
        tier_str = "مستوى 3 🥇"
    
    safe_name = safe_str(u.get('name'))
    text = f"👤 **بيانات حسابك**\n\n📛 الاسم: {safe_name}\n🆔 ID: `{msg.chat.id}`\n📱 الهاتف: `{u.get('phone')}`\n💰 رصيدك: **{u.get('balance', 0.0)}**\n🎚️ تصنيف الحساب: {tier_str}\nحالة الحساب: {status_text}"
    
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
    if not u:
        bot.answer_callback_query(call.id, "حسابك موقوف.", show_alert=True)
        return

    if call.data == "client_purchases":
        history = list(transactions.find({"uid": uid, "type": "شراء"}).sort("_id", -1).limit(10))
        if not history:
            bot.answer_callback_query(call.id, "لا توجد مشتريات.", show_alert=True)
            return
            
        report_text = "🛒 **آخر 10 مشتريات:**\n\n"
        for t in history:
            report_text += f"▪️ {t['date']} | فاتورة #{t.get('order_id', 'N/A')} | {t['item_name']} (x{t.get('quantity', 1)}) | السعر: {t['price']}\n"
            
    elif call.data == "client_statement":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(20))
        if not history:
            bot.answer_callback_query(call.id, "لا توجد عمليات.", show_alert=True)
            return
            
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
    if not check_user_access(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل كود الشحن:")
    bot.register_next_step_handler(msg, check_card)

def check_card(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    uid = msg.chat.id
    u = users.find_one({"_id": uid})
    
    if not u or u.get("status") != "active":
        if u and u.get("status") == "blocked":
            bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        else:
            bot.send_message(uid, "❌ حسابك مجمد. لا يمكنك الشحن.")
        return

    code = msg.text.strip()
    card = cards.find_one_and_update({"code": code, "used": False}, {"$set": {"used": True}})
    
    if not card:
        failed_attempts = u.get("failed_attempts", 0) + 1
        if failed_attempts >= 5:
            users.update_one({"_id": uid}, {"$set": {"status": "frozen", "failed_attempts": 0}})
            bot.send_message(uid, "🚫 تم إيقاف الحساب بسبب التلاعب بالنظام.")
            return
        else:
            users.update_one({"_id": uid}, {"$set": {"failed_attempts": failed_attempts}})
            attempts_left = 5 - failed_attempts
            bot.send_message(uid, f"❌ كود غير صالح. (متبقي لك {attempts_left} محاولات قبل تجميد الحساب)")
            return

    new_bal = u.get("balance", 0.0) + float(card["value"])
    users.update_one({"_id": uid}, {"$set": {"balance": new_bal, "failed_attempts": 0}})
    
    transactions.insert_one({
        "uid": uid, 
        "user_name": u.get("name"), 
        "type": "شحن كارت", 
        "amount": float(card["value"]), 
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    bot.send_message(uid, f"✅ تم شحن رصيدك بقيمة {card['value']} بنجاح")
    
    safe_name = safe_str(u.get('name'))
    for admin_id in get_all_admins():
        try:
            bot.send_message(
                admin_id, 
                f"💳 **عملية شحن كارت!**\n\n📛 العميل: {safe_name}\n📱 الهاتف: `{u.get('phone')}`\n💰 قيمة الشحن: **{card['value']}**\n💵 الرصيد الجديد: **{new_bal}**", 
                parse_mode="Markdown"
            )
        except Exception:
            pass

# ========= BULK PRICE UPDATE =========
@bot.message_handler(func=lambda m: m.text == "💵 أسعار المستويات")
def edit_tier_prices_cmd(msg):
    if not is_admin(msg.chat.id):
        return
        
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
    if not products:
        bot.send_message(msg.chat.id, "❌ المخزن فارغ أو لا توجد منتجات متاحة للبيع.")
        return
    
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
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = max_length + 4

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    file_stream.name = "Prices_Update.xlsx"
    
    caption = "📁 **أداة تعديل الأسعار المجمعة**\n\n1️⃣ قم بتحميل الملف.\n2️⃣ عدل الأسعار في الأعمدة الثلاثة الأخيرة (السعر 1، 2، 3) حسب ما تراه مناسباً لكل مستوى.\n3️⃣ أعد رفع الملف هنا.\n\n⚠️ **ملاحظة هامة:** لا تقم بتغيير عمود (الاسم) أبداً لأنه الدليل الذي يربط السعر بالمنتج."
    m = bot.send_document(msg.chat.id, file_stream, caption=caption)
    bot.register_next_step_handler(m, process_bulk_price_update)

def process_bulk_price_update(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    if not msg.document or not msg.document.file_name.endswith(".xlsx"):
        bot.send_message(msg.chat.id, "❌ يرجى رفع ملف إكسيل بصيغة .xlsx فقط.")
        return
    
    bot.send_message(msg.chat.id, "⏳ جاري تحديث أسعار المتجر بالكامل...")
    try:
        file_info = bot.get_file(msg.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        wb = openpyxl.load_workbook(io.BytesIO(downloaded))
        ws = wb.active
        
        updated_count = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
                
            name = str(row[0]).strip() if row[0] else None
            if not name:
                continue
            
            p1 = float(row[3]) if row[3] is not None else 0
            p2 = float(row[4]) if row[4] is not None else p1
            p3 = float(row[5]) if row[5] is not None else p1
            
            res = stock.update_many(
                {"name": name, "sold": False}, 
                {"$set": {"price_1": p1, "price_2": p2, "price_3": p3}}
            )
            
            if res.modified_count > 0:
                updated_count += 1
        
        bot.send_message(
            msg.chat.id, 
            f"✅ تمت العملية بنجاح!\nتم تحديث أسعار **{updated_count}** نوع من المنتجات/الخدمات لكافة المستويات."
        )
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء قراءة الملف وتحديث الأسعار:\n{e}")

# ========= SHOP =========
@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def shop(msg):
    u = check_user_access(msg.chat.id)
    if not u:
        return
        
    cats = stock.distinct("category")
    if not cats:
        bot.send_message(msg.chat.id, "❌ لا توجد منتجات حالياً")
        return
        
    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))
    bot.send_message(msg.chat.id, "اختر قسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cat(call):
    cat_name = call.data.split("_", 1)[1]
    subs = stock.distinct("subcategory", {"category": cat_name})
    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat_name}_{s}"))
    bot.edit_message_text("اختر فئة:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def sub(call):
    uid = call.message.chat.id
    u = check_user_access(uid)
    if not u:
        return
        
    tier = u.get("tier", 1)
    
    _, cat_name, sub_name = call.data.split("_", 2)
    items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))
    available_count = len(items)
    
    if available_count < 10:
        bot.answer_callback_query(call.id, "❌ الكمية المتوفرة أقل من الحد الأدنى للشراء (10 أكواد).", show_alert=True)
        return
        
    item = items[0]
    p1 = item.get("price_1", item.get("price", 0))
    p2 = item.get("price_2", p1)
    p3 = item.get("price_3", p1)
    
    if tier == 1:
        user_price = p1
    elif tier == 2:
        user_price = p2
    else:
        user_price = p3
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 طلب شراء", callback_data=f"buy_{item['_id']}"))
    
    msg_text = f"📦 المنتج: {item['name']}\n💰 السعر الخاص بك: {user_price}\n📊 المتوفر: {available_count}\n⚠️ أقل كمية للطلب: 10 ومضاعفاتها"
    bot.send_message(uid, msg_text, reply_markup=kb)

# ========= BUY (BULK WITH MINIMUM 10) =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy_quantity_prompt(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]

    user = check_user_access(uid)
    if not user:
        bot.answer_callback_query(call.id, "❌ حسابك غير مؤهل.", show_alert=True)
        return

    item_preview = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item_preview:
        bot.answer_callback_query(call.id, "❌ نفذت الكمية أو تم بيعها.", show_alert=True)
        return
    
    product_name = item_preview['name']
    available = stock.count_documents({"name": product_name, "sold": False})
    
    if available < 10:
        bot.answer_callback_query(call.id, "❌ الكمية المتبقية أقل من 10.", show_alert=True)
        return

    msg = bot.send_message(uid, f"📦 المنتج: {product_name}\n📊 المتوفر: {available}\n\n👉 أرسل **الكمية المطلوبة** (يجب أن تكون 10 أو مضاعفاتها كـ 20، 30...):")
    bot.register_next_step_handler(msg, process_purchase, user, item_preview, available)
    bot.answer_callback_query(call.id)

def process_purchase(msg, user, item_ref, available):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم إلغاء الشراء.")
        return
        
    uid = msg.chat.id
    
    try:
        qty = int(msg.text.strip())
        if qty < 10 or qty % 10 != 0:
            bot.send_message(uid, "❌ الكمية يجب أن تكون 10 أو مضاعفاتها (10, 20, 30...). تم الإلغاء.")
            return
    except ValueError:
        bot.send_message(uid, "❌ الرجاء إدخال رقم صحيح. تم الإلغاء.")
        return

    if qty > available:
        bot.send_message(uid, f"❌ الكمية المطلوبة غير متوفرة. أقصى كمية: {available}")
        return

    name = item_ref['name']
    
    user_fresh = users.find_one({"_id": uid})
    tier = user_fresh.get("tier", 1)
    
    p1 = item_ref.get("price_1", item_ref.get("price", 0))
    p2 = item_ref.get("price_2", p1)
    p3 = item_ref.get("price_3", p1)
    
    if tier == 1:
        user_price = p1
    elif tier == 2:
        user_price = p2
    else:
        user_price = p3
        
    total_price = qty * user_price

    if float(user_fresh.get("balance", 0.0)) < total_price: 
        bot.send_message(uid, f"❌ رصيدك غير كافي.\nالمطلوب: {total_price}\nرصيدك: {user_fresh.get('balance', 0)}")
        return

    available_docs = list(stock.find({"name": name, "sold": False}).limit(qty))
    if len(available_docs) < qty:
        bot.send_message(uid, "❌ حدث خطأ، الكمية نفذت فجأة. يرجى المحاولة مرة أخرى.")
        return

    doc_ids = [d['_id'] for d in available_docs]
    res = stock.update_many({"_id": {"$in": doc_ids}, "sold": False}, {"$set": {"sold": True}})
    
    if res.modified_count != qty:
        stock.update_many({"_id": {"$in": doc_ids}}, {"$set": {"sold": False}})
        bot.send_message(uid, "❌ حدث تضارب أثناء الشراء، الرجاء المحاولة مرة أخرى.")
        return

    users.update_one({"_id": uid}, {"$inc": {"balance": -total_price}})
    order_id = get_next_order_id()
    dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    transactions.insert_one({
        "order_id": order_id, 
        "uid": uid, 
        "user_name": user_fresh.get("name"), 
        "phone": user_fresh.get('phone'), 
        "type": "شراء", 
        "item_name": name, 
        "quantity": qty, 
        "price": total_price, 
        "date": dt_now
    })

    if SHEET_WEBHOOK_URL and SHEET_WEBHOOK_URL.startswith("http"):
        try:
            requests.post(
                SHEET_WEBHOOK_URL, 
                json={
                    "order_id": order_id, 
                    "date": dt_now, 
                    "phone": user_fresh.get('phone'), 
                    "item_name": f"{name} (x{qty})", 
                    "price": total_price
                }, 
                timeout=3
            )
        except Exception:
            pass

    bot.send_message(
        uid, 
        f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n💰 إجمالي المخصوم: {total_price}\n\nجاري تجهيز الفاتورة وملف الأكواد...", 
        parse_mode="Markdown"
    )

    safe_name = safe_str(user_fresh.get('name'))
    for admin_id in get_all_admins():
        try:
            bot.send_message(
                admin_id, 
                f"🛒 **شراء جديد بالجملة** | فاتورة #{order_id}\n📛 العميل: {safe_name}\n📱 الهاتف: {user_fresh.get('phone')}\n🎚️ مستوى العميل: {tier}\n📦 المنتج: {name} (الكمية: {qty})\n💰 المدفوع: {total_price}", 
                parse_mode="Markdown"
            )
        except Exception:
            pass

    purchased_items_data = []
    for d in available_docs:
        purchased_items_data.append({
            'code': d['code'], 
            'serial': d.get('serial', ''), 
            'pin': d.get('pin', ''), 
            'op_code': d.get('op_code', '')
        })
        
    file_stream = generate_customer_excel_file(purchased_items_data, order_id, dt_now, name)
    bot.send_document(uid, document=file_stream, caption=f"📁 فاتورة الأكواد | رقم #{order_id}")
    
    for admin_id in get_all_admins():
        try:
            file_stream.seek(0)
            bot.send_document(admin_id, document=file_stream, caption=f"📁 نسخة للإدارة | فاتورة #{order_id}")
        except Exception:
            pass

    remaining_stock = stock.count_documents({"name": name, "sold": False})
    if remaining_stock <= 30:
        for admin_id in get_all_admins():
            try:
                bot.send_message(
                    admin_id, 
                    f"⚠️ **تنبيه نقص مخزون** ⚠️\n\nالمنتج: `{name}`\nالكمية المتبقية: **{remaining_stock}** كود فقط!\nيرجى إعادة تعبئة المخزون قريباً.", 
                    parse_mode="Markdown"
                )
            except Exception:
                pass

# ========= ADMIN =========
@bot.message_handler(commands=['admin'])
def admin(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "👑 لوحة تحكم الإدارة", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def back_to_store(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل", reply_markup=menu())

# ===== MANAGE CUSTOMER & TIERS =====
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def manage_customer_cmd(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل رقم هاتف العميل (أو الـ ID):")
    bot.register_next_step_handler(msg, show_customer_panel)

def show_customer_panel(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    u = find_customer(msg.text)
    if not u:
        bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
        return
        
    render_customer_panel(u["_id"], msg.chat.id)

def render_customer_panel(uid, chat_id, message_id=None):
    u = users.find_one({"_id": uid})
    if not u:
        return
        
    stat = u.get("status")
    safe_name = safe_str(u.get("name"))
    tier = u.get("tier", 1)
    
    if tier == 1:
        tier_str = "مستوى 1 🥉"
    elif tier == 2:
        tier_str = "مستوى 2 🥈"
    else:
        tier_str = "مستوى 3 🥇"
    
    if stat == "blocked":
        stat_ar = "محظور نهائياً 🚫"
    elif stat == "active":
        stat_ar = "نشط ✅"
    else:
        stat_ar = "مجمد (قيد المراجعة) ❄️"
    
    info = f"👤 بيانات العميل:\n📛 الاسم: {safe_name}\nID: `{uid}`\nالهاتف: `{u.get('phone', 'بدون_رقم')}`\nالرصيد: {u.get('balance',0)}\n🎚️ مستوى الأسعار: {tier_str}\nالحالة: {stat_ar}"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    if stat == "active":
        kb.add(
            types.InlineKeyboardButton("❄️ تجميد", callback_data=f"freeze_{uid}"),
            types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}")
        )
    elif stat == "frozen":
        kb.add(
            types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"),
            types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}")
        )
    elif stat == "blocked":
        kb.add(
            types.InlineKeyboardButton("✅ فك الحظر والتفعيل", callback_data=f"activate_{uid}")
        )
        
    kb.add(types.InlineKeyboardButton("🎚️ تغيير المستوى", callback_data=f"chgtier_{uid}"))
    kb.add(types.InlineKeyboardButton("📊 تقرير العمليات", callback_data=f"report_{uid}"))
    
    if message_id:
        try:
            bot.edit_message_text(info, chat_id, message_id, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass
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
        try:
            bot.send_message(uid, f"🎉 تم ترقية مستوى أسعارك في المتجر إلى (المستوى {level}) من قبل الإدارة.")
        except Exception:
            pass
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
        if not history:
            bot.answer_callback_query(call.id, "لا يوجد عمليات.", show_alert=True)
            return
            
        report_text = f"📊 آخر عمليات العميل `{uid}`:\n\n"
        for t in history:
            if t["type"] == "شراء":
                report_text += f"▪️ {t['date']} | 🛒 {t['item_name']} | بـ {t['price']}\n"
            else:
                report_text += f"▪️ {t['date']} | 💳 {t['type']} | بـ {t['amount']}\n"
        bot.send_message(call.message.chat.id, report_text, parse_mode="Markdown")
        return

    if action == "freeze":
        users.update_one({"_id": uid}, {"$set": {"status": "frozen"}})
        bot.answer_callback_query(call.id, "✅ تم تجميد الحساب")
        try:
            bot.send_message(uid, "⚠️ تم تجميد حسابك.", reply_markup=types.ReplyKeyboardRemove())
        except Exception:
            pass
            
    elif action == "activate":
        users.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
        bot.answer_callback_query(call.id, "✅ تم التفعيل")
        try:
            bot.send_message(uid, "✅ تم تفعيل حسابك بنجاح. يمكنك الاستمتاع بخدمات المتجر الآن.", reply_markup=menu())
        except Exception:
            pass
            
    elif action == "block":
        users.update_one({"_id": uid}, {"$set": {"status": "blocked"}})
        bot.answer_callback_query(call.id, "🚫 تم حظر الحساب")
        try:
            bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا", reply_markup=types.ReplyKeyboardRemove())
        except Exception:
            pass

    render_customer_panel(uid, call.message.chat.id, call.message.message_id)

# ===== ADD PRODUCT (TEMPLATE & MANUAL) =====
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def add_product(msg):
    if not is_admin(msg.chat.id):
        return
        
    text = "اختر طريقة إضافة المنتجات:\n\n📁 **الطريقة الأولى: القالب الشامل**\nحمل القالب، املأه بالمنتجات (ملاحظة: التسلسلي، الـ PIN، وأوبريشن كود اختياريان) وأعد رفعه.\n\n✍️ **الطريقة الثانية: الإضافة اليدوية**\nأرسل:\n`القسم:الفئة:الاسم:السعر1:السعر2:السعر3`\n*(ملاحظة: إذا أردت سعراً واحداً لكل المستويات يمكنك كتابة سعر واحد فقط)*"
    try:
        template = generate_products_template()
        bot.send_document(msg.chat.id, template, caption=text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, handle_add_product_choice)
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ: {e}")

def handle_add_product_choice(msg):
    if msg.text and msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    if msg.document:
        if not msg.document.file_name.endswith('.xlsx'):
            bot.send_message(msg.chat.id, "❌ يرجى رفع ملف .xlsx فقط.")
            return
            
        bot.send_message(msg.chat.id, "⏳ جاري قراءة القالب...")
        try:
            file_info = bot.get_file(msg.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_stream = io.BytesIO(downloaded_file)
            wb = openpyxl.load_workbook(file_stream)
            ws = wb.active
            extracted_data = []
            errors = 0
            
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0 or not any(row):
                    continue 
                try:
                    cat = str(row[0]).strip() if len(row) > 0 and row[0] else ""
                    sub = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                    name = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                    p1 = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
                    p2 = float(row[4]) if len(row) > 4 and row[4] is not None else p1
                    p3 = float(row[5]) if len(row) > 5 and row[5] is not None else p1
                    code_val = str(row[6]).strip() if len(row) > 6 and row[6] else ""
                    serial_val = str(row[7]).strip() if len(row) > 7 and row[7] else ""
                    pin_val = str(row[8]).strip() if len(row) > 8 and row[8] else ""
                    op_code_val = str(row[9]).strip() if len(row) > 9 and row[9] else ""
                    
                    if not all([cat, sub, name, code_val]):
                        errors += 1
                        continue
                        
                    extracted_data.append({
                        "category": cat, 
                        "subcategory": sub, 
                        "name": name, 
                        "price_1": p1, 
                        "price_2": p2, 
                        "price_3": p3, 
                        "code": code_val, 
                        "serial": serial_val, 
                        "pin": pin_val, 
                        "op_code": op_code_val
                    })
                except Exception:
                    errors += 1
                    continue
                
            if errors > 0:
                bot.send_message(msg.chat.id, f"⚠️ تم تخطي {errors} صف لوجود بيانات ناقصة أو غير صحيحة.")
                
            filter_and_insert_codes(msg.chat.id, extracted_data)
            
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ خطأ:\n{e}")
            
    elif msg.text and ":" in msg.text:
        save_product_info(msg)
    else:
        bot.send_message(msg.chat.id, "❌ إدخال غير صالح.")

def save_product_info(msg):
    try:
        parts = msg.text.split(":")
        cat = parts[0].strip()
        sub = parts[1].strip()
        name = parts[2].strip()
        p1 = float(parts[3].strip()) if len(parts) > 3 else 0.0
        p2 = float(parts[4].strip()) if len(parts) > 4 else p1
        p3 = float(parts[5].strip()) if len(parts) > 5 else p1
        
        if msg.chat.id not in temp_admin_data:
            temp_admin_data[msg.chat.id] = {}
            
        temp_admin_data[msg.chat.id]["new_product"] = {
            "cat": cat, 
            "sub": sub, 
            "name": name, 
            "price_1": p1, 
            "price_2": p2, 
            "price_3": p3
        }
        
        bot.send_message(
            msg.chat.id, 
            "✅ تم حفظ بيانات المنتج والأسعار.\nالآن أرسل الأكواد كـ **رسالة نصية** بالتنسيق التالي:\n`الكود:التسلسلي:PIN:اوبريشن كود`\n\n*(ملاحظة: يمكنك إرسال الكود فقط وسيعتبر البوت أن الباقي غير متوفر)*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_product_codes_manual)
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ في التنسيق. تأكد من إدخال البيانات بشكل صحيح.")

def process_product_codes_manual(msg):
    if msg.text and msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    product_info = temp_admin_data.get(msg.chat.id, {}).get("new_product")
    if not product_info:
        bot.send_message(msg.chat.id, "❌ حدث خطأ.")
        return
    
    extracted_data = []
    if msg.text:
        for line in msg.text.split("\n"):
            if line.strip():
                parts = line.split(":")
                c_val = parts[0].strip()
                s_val = parts[1].strip() if len(parts) > 1 else ""
                p_val = parts[2].strip() if len(parts) > 2 else ""
                op_val = parts[3].strip() if len(parts) > 3 else ""
                extracted_data.append({
                    "code": c_val, 
                    "serial": s_val, 
                    "pin": p_val, 
                    "op_code": op_val
                })
                
    filter_and_insert_codes(msg.chat.id, extracted_data, product_info)
    if msg.chat.id in temp_admin_data and "new_product" in temp_admin_data[msg.chat.id]:
        del temp_admin_data[msg.chat.id]["new_product"]

# ===== SET BALANCE =====
@bot.message_handler(func=lambda m: m.text == "💰 ضبط الرصيد")
def set_balance_cmd(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:الرصيد_الجديد)\nمثال: 0940719000:500")
    bot.register_next_step_handler(msg, do_set_balance)

def do_set_balance(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        phone_str, val_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            new_bal = float(val_str.strip())
            users.update_one({"_id": u["_id"]}, {"$set": {"balance": new_bal}})
            transactions.insert_one({
                "uid": u["_id"], 
                "user_name": u.get("name"), 
                "type": "ضبط رصيد", 
                "amount": new_bal, 
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            bot.send_message(msg.chat.id, f"✅ تم ضبط رصيد {u.get('phone')} ليصبح {new_bal}")
            try:
                bot.send_message(u["_id"], f"⚙️ تم تحديث رصيدك من قبل الإدارة ليصبح: {new_bal}")
            except Exception:
                pass
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== DIRECT CHARGE =====
@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def direct(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل (رقم_الهاتف:قيمة_الإضافة)\nمثال: 0940719000:50")
    bot.register_next_step_handler(msg, do_charge)

def do_charge(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        phone_str, amt_str = msg.text.split(":")
        u = find_customer(phone_str)
        if u:
            amt = float(amt_str.strip())
            users.update_one({"_id": u["_id"]}, {"$inc": {"balance": amt}})
            transactions.insert_one({
                "uid": u["_id"], 
                "user_name": u.get("name"), 
                "type": "شحن إضافي", 
                "amount": amt, 
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            bot.send_message(msg.chat.id, f"✅ تم إضافة {amt} لرصيد {u.get('phone')}")
            try:
                bot.send_message(u["_id"], f"🎁 تم إضافة {amt} لرصيدك من قِبل الإدارة")
            except Exception:
                pass
        else:
            bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ===== MANAGE STOCK =====
@bot.message_handler(func=lambda m: m.text == "📦 إدارة المخزون")
def manage_stock_cmd(msg):
    if not is_admin(msg.chat.id):
        return
    names = stock.distinct("name", {"sold": False})
    if not names:
        bot.send_message(msg.chat.id, "❌ المخزن فارغ حالياً أو تم بيع كل المنتجات.")
        return
        
    text = "📦 **المنتجات المتوفرة في المخزن:**\n\n"
    for n in names:
        count = stock.count_documents({"name": n, "sold": False})
        text += f"▪️ `{n}` (الكمية: {count})\n"
        
    text += "\n👉 أرسل **اسم المنتج** (انسخه من القائمة بالأعلى) لإدارته:"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, show_stock_item_panel)

def show_stock_item_panel(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    name = msg.text.strip()
    count = stock.count_documents({"name": name, "sold": False})
    item = stock.find_one({"name": name, "sold": False})
    if not item:
        bot.send_message(msg.chat.id, "❌ المنتج غير موجود.")
        return
        
    p1 = item.get("price_1", item.get("price", 0))
    p2 = item.get("price_2", p1)
    p3 = item.get("price_3", p1)
        
    text = f"📦 المنتج: `{name}`\n💰 الأسعار:\nم1: {p1} | م2: {p2} | م3: {p3}\n📊 الكمية المتوفرة: {count}"
    
    if msg.chat.id not in temp_admin_data:
        temp_admin_data[msg.chat.id] = {}
        
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
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة.", show_alert=True)
        return
        
    name = data["mng_item_name"]
    
    if action == "price":
        msg = bot.send_message(call.message.chat.id, f"أرسل الأسعار الجديدة للمنتج `{name}` بالتنسيق:\nسعر1:سعر2:سعر3", parse_mode="Markdown")
        bot.register_next_step_handler(msg, update_stock_price, name)
        bot.answer_callback_query(call.id)
        
    elif action == "delqty":
        msg = bot.send_message(call.message.chat.id, f"أرسل عدد الأكواد المراد حذفها من المنتج `{name}`:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, delete_stock_qty, name)
        bot.answer_callback_query(call.id)
        
    elif action == "delall":
        res = stock.delete_many({"name": name, "sold": False})
        bot.answer_callback_query(call.id, f"✅ تم حذف {res.deleted_count} كود.")
        bot.edit_message_text(
            f"✅ تم حذف المنتج `{name}` بالكامل.", 
            call.message.chat.id, 
            call.message.message_id, 
            parse_mode="Markdown"
        )

def update_stock_price(msg, name):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        parts = msg.text.split(":")
        p1 = float(parts[0].strip())
        p2 = float(parts[1].strip()) if len(parts) > 1 else p1
        p3 = float(parts[2].strip()) if len(parts) > 2 else p1
        
        res = stock.update_many(
            {"name": name, "sold": False}, 
            {"$set": {"price_1": p1, "price_2": p2, "price_3": p3}}
        )
        bot.send_message(msg.chat.id, f"✅ تم تحديث الأسعار للمنتج `{name}` لـ {res.modified_count} كود.", parse_mode="Markdown")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ، يرجى التنسيق الصحيح (سعر1:سعر2:سعر3).")

def delete_stock_qty(msg, name):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        qty_to_delete = int(msg.text.strip())
        docs_to_delete = list(stock.find({"name": name, "sold": False}).limit(qty_to_delete))
        if not docs_to_delete:
            bot.send_message(msg.chat.id, "❌ لا توجد أكواد متاحة للحذف.")
            return
            
        doc_ids = [d['_id'] for d in docs_to_delete]
        res = stock.delete_many({"_id": {"$in": doc_ids}})
        bot.send_message(msg.chat.id, f"✅ تم حذف {res.deleted_count} كود من منتج `{name}` بنجاح.", parse_mode="Markdown")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ، يرجى إرسال رقم صحيح.")

# ===== USERS =====
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users_list(msg):
    if not is_admin(msg.chat.id):
        return
        
    try:
        text = "👥 قائمة آخر 30 مستخدم:\n\n"
        for u in users.find().sort("join", -1).limit(30):
            stat = "✅" if u.get('status') == 'active' else ("🚫" if u.get('status') == 'blocked' else "❄️")
            safe_name = safe_str(u.get('name'))
            phone = str(u.get('phone', 'بدون رقم'))
            bal = u.get('balance', 0)
            
            text += f"📛 {safe_name} | 📱 `{phone}` | الرصيد: {bal} | {stat}\n"
            
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ تعذر عرض القائمة بسبب خطأ:\n{e}")

# ===== INVOICE LOG =====
@bot.message_handler(func=lambda m: m.text == "🧾 سجل الفواتير")
def invoices_log(msg):
    if not is_admin(msg.chat.id):
        return
        
    history = list(transactions.find({"type": "شراء", "order_id": {"$exists": True}}).sort("_id", -1).limit(40))
    if not history:
        bot.send_message(msg.chat.id, "لا توجد فواتير مبيعات حتى الآن.")
        return
        
    text = "🧾 **سجل آخر 40 فاتورة:**\n\n"
    for t in history:
        safe_name = safe_str(t.get('user_name'))
        text += f"▪️ #{t['order_id']} | 👤 {safe_name} | 🛒 {t['item_name']} (x{t.get('quantity', 1)}) | 💰 {t['price']}\n"
        
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ===== EXCEL REPORTS & DATE FILTERING =====
@bot.message_handler(func=lambda m: m.text == "📊 تقارير إكسيل")
def excel_reports_cmd(msg):
    if not is_admin(msg.chat.id):
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📄 تقرير شامل (كل العملاء والعمليات)", callback_data="rep_all"))
    kb.add(types.InlineKeyboardButton("👤 تقرير عميل محدد", callback_data="rep_single"))
    bot.send_message(msg.chat.id, "📊 اختر نوع التقرير الذي تريد استخراجه:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rep_"))
def handle_report_callback(call):
    admin_id = call.message.chat.id
    action = call.data.split("_")[1]
    
    if admin_id not in temp_admin_data:
        temp_admin_data[admin_id] = {}
        
    temp_admin_data[admin_id]["rep_type"] = action
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🕒 كل التواريخ والأوقات", callback_data="date_all"))
    kb.add(types.InlineKeyboardButton("📅 تحديد فترة (من - إلى)", callback_data="date_custom"))
    bot.edit_message_text(
        "📅 هل تريد استخراج التقرير لجميع التواريخ، أم تحديد فترة معينة؟", 
        admin_id, 
        call.message.message_id, 
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("date_"))
def handle_report_date(call):
    admin_id = call.message.chat.id
    choice = call.data.split("_")[1]
    rep_type = temp_admin_data.get(admin_id, {}).get("rep_type")
    
    if not rep_type:
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة. الرجاء طلب التقرير من جديد.", show_alert=True)
        return
        
    bot.answer_callback_query(call.id)
    
    if choice == "all":
        execute_report(admin_id, rep_type, None, None)
    elif choice == "custom":
        msg = bot.send_message(
            admin_id, 
            "أرسل التاريخ (من) و (إلى) بالتنسيق التالي:\n`YYYY-MM-DD:YYYY-MM-DD`\n\nمثال:\n`2026-03-01:2026-04-10`", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_custom_date_report, rep_type)

def process_custom_date_report(msg, rep_type):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        start_date, end_date = msg.text.split(":")
        execute_report(msg.chat.id, rep_type, start_date.strip(), end_date.strip())
    except Exception:
        bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح. قم بطلب التقرير مرة أخرى.")

def execute_report(admin_id, rep_type, start_date, end_date):
    date_filter = {}
    if start_date and end_date:
        date_filter = {"date": {"$gte": start_date, "$lte": end_date + " 23:59"}}

    if rep_type == "all":
        bot.send_message(admin_id, "⏳ جاري تجميع البيانات وتجهيز ملف الإكسيل...")
        history = list(transactions.find(date_filter).sort("_id", -1))
        
        if not history:
            bot.send_message(admin_id, "❌ لا توجد عمليات مسجلة في هذه الفترة.")
            return
            
        summary = {}
        for t in history:
            phone = t.get("phone", "غير_مسجل")
            name = t.get("user_name", "غير_مسجل")
            if t.get("type") == "شراء":
                if phone not in summary:
                    summary[phone] = {"spent": 0.0, "name": name}
                summary[phone]["spent"] += float(t.get("price", 0))
                
        file_stream = generate_admin_report_excel("all", history, summary)
        bot.send_document(admin_id, document=file_stream, caption="✅ التقرير الشامل للعمليات.")
        
    elif rep_type == "single":
        msg = bot.send_message(admin_id, "👉 أرسل **رقم هاتف العميل** لاستخراج تقريره:")
        bot.register_next_step_handler(msg, process_single_report_excel_final, date_filter)

def process_single_report_excel_final(msg, date_filter):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
        
    u = find_customer(msg.text)
    if not u:
        bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
        return
        
    uid = u["_id"]
    phone = u.get("phone", "بدون_رقم")
    bot.send_message(msg.chat.id, "⏳ جاري استخراج تقرير العميل...")
    
    query = {"uid": uid}
    query.update(date_filter)
    history = list(transactions.find(query).sort("_id", -1))
    
    if not history:
        bot.send_message(msg.chat.id, "❌ لا توجد عمليات مسجلة لهذا العميل في هذه الفترة.")
        return
        
    file_stream = generate_admin_report_excel("single", history)
    file_stream.name = f"Report_{phone}.xlsx"
    bot.send_document(msg.chat.id, document=file_stream, caption=f"✅ تقرير العمليات الخاص بالعميل: {phone}")

# ===== GENERATE CARDS =====
@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def gen_cards(msg):
    if not is_admin(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "أرسل (العدد:القيمة)")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم الإلغاء.")
        return
    try:
        count_str, val_str = msg.text.split(":")
        count, val = int(count_str), float(val_str)
        arr = []
        txt = f"✅ تم توليد {count} كروت بقيمة {val}:\n\n"
        
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            arr.append({"code": code, "value": val, "used": False})
            txt += f"`{code}`\n"
            
        cards.insert_many(arr)
        bot.send_message(msg.chat.id, txt, parse_mode="Markdown")
    except Exception:
        bot.send_message(msg.chat.id, "❌ خطأ في الإدخال.")

# ========= DUMMY WEB SERVER FOR RENDER =========
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_bot():
    """هذه الدالة لتشغيل البوت في مسار منفصل لكي لا يوقف سيرفر رندر"""
    try:
        bot.remove_webhook()
        time.sleep(2)
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Bot Polling Error: {e}")

# ========= RUN =========
if __name__ == "__main__":
    print("⏳ Starting background bot thread...")
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    print("🚀 Starting Flask Server for Render Port Binding...")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
