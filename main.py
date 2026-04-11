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
import traceback

# =======================================================
# 1. الإعدادات الأساسية (Configuration)
# =======================================================

API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"

OWNER_ID = 1262656649
ADMIN_IDS = [OWNER_ID] 

MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

client = MongoClient(
    MONGO_URI, 
    tlsCAFile=certifi.where(),
    maxPoolSize=50, 
    connectTimeoutMS=5000
)
db = client["AlAhram_DB"]

users = db["users"]
stock = db["stock"]
cards = db["cards"]
transactions = db["transactions"]
counters = db["counters"]
admins_db = db["admins"]

SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzPrw8oANq8Aek6O6URoTU0kDVjb1ZtoVdYkhpqAqM6Nuws4ZmcPRC9JtoNZvWoMzUb/exec"

bot = telebot.TeleBot(API_TOKEN)

MENU_BUTTONS = [
    "🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", 
    "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل", 
    "💰 ضبط الرصيد", "🧾 سجل الفواتير", "📦 إدارة المخزون", 
    "📊 تقارير إكسيل", "💵 أسعار المستويات", "🏪 العودة للمتجر"
]

temp_admin_data = {}

# =======================================================
# 2. الدوال المساعدة (Utility Functions)
# =======================================================

def safe_str(text):
    if text is None: return "بدون"
    bad_chars = ["_", "*", "`", "[", "]", "(", ")", "~", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    res = str(text)
    for char in bad_chars:
        res = res.replace(char, " ")
    return res.strip()

def is_admin(uid):
    if uid in ADMIN_IDS: return True
    if admins_db.find_one({"_id": uid}): return True
    return False

def get_all_admins():
    admins = list(ADMIN_IDS)
    all_extra_admins = admins_db.find()
    for a in all_extra_admins:
        if a["_id"] not in admins:
            admins.append(a["_id"])
    return admins

def is_valid_val(val):
    if val is None: return False
    s_val = str(val).strip().lower()
    if s_val in ["", "none", "null", "بدون", "nan"]: return False
    return True

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

def check_user_access(uid):
    u = users.find_one({"_id": uid})
    if not u:
        bot.send_message(uid, "⚠️ النظام مغلق. أرسل /start للتسجيل أولاً.")
        return None
    if not u.get("name"):
        msg = bot.send_message(uid, "يرجى كتابة اسمك الكريم أولاً للاستمرار:")
        bot.register_next_step_handler(msg, process_name)
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

# =======================================================
# 3. محرك الإكسيل والفواتير المطور 
# =======================================================

def generate_customer_excel_file(items_data, order_id, dt_now, product_name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Invoice_{order_id}"
    
    title_fill = PatternFill(start_color="002060", end_color="002060", fill_type="solid")
    info_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    white_font = Font(color="FFFFFF", bold=True)
    centered = Alignment(horizontal="center", vertical="center")
    
    has_serial = False; has_pin = False; has_opcode = False
    for d in items_data:
        if is_valid_val(d.get('serial')): has_serial = True
        if is_valid_val(d.get('pin')): has_pin = True
        if is_valid_val(d.get('op_code')): has_opcode = True
            
    headers = ["م", "اسم المنتج", "كود الشحن"]
    if has_serial: headers.append("الرقم التسلسلي")
    if has_pin: headers.append("الرقم السري (PIN)")
    if has_opcode: headers.append("أوبريشن كود")
        
    last_col_idx = len(headers)
    last_col_letter = get_column_letter(last_col_idx)
    
    ws.merge_cells(f'A1:{last_col_letter}1')
    ws['A1'] = "شركة الأهرام للإتصالات والتقنية"
    ws['A1'].font = Font(color="FFFFFF", bold=True, size=16)
    ws['A1'].fill = title_fill
    ws['A1'].alignment = centered
    ws.row_dimensions[1].height = 35
    
    ws.merge_cells(f'A2:{last_col_letter}2')
    ws['A2'] = f"فاتورة شراء رقم: #{order_id}   |   تاريخ العملية: {dt_now}"
    ws['A2'].fill = info_fill
    ws['A2'].alignment = centered
    ws.row_dimensions[2].height = 25
    
    ws.append([]); ws.append(headers)
    for cell in ws[4]:
        cell.font = white_font
        cell.fill = header_fill
        cell.alignment = centered
        
    for i, d in enumerate(items_data, 1):
        row_data = [i, product_name, str(d['code'])]
        if has_serial: row_data.append(str(d.get('serial', '')))
        if has_pin: row_data.append(str(d.get('pin', '')))
        if has_opcode: row_data.append(str(d.get('op_code', '')))
        ws.append(row_data)
        for cell in ws[ws.max_row]: cell.alignment = centered

    for col in ws.columns:
        max_length = 0
        if not col: continue
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception: pass
        ws.column_dimensions[col_letter].width = max_length + 5

    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()

def generate_admin_report_excel(report_type, history_data, summary_data=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    white_font = Font(color="FFFFFF", bold=True)
    
    if report_type == "all":
        ws.title = "سجل المبيعات الشامل"
        ws.append(["رقم الفاتورة", "التاريخ", "الاسم", "الهاتف", "نوع العملية", "البيان", "الكمية", "المبلغ"])
        for h in history_data:
            ws.append([
                h.get("order_id", "-"), h.get("date", ""), h.get("user_name", ""),
                h.get("phone", ""), h.get("type", ""), h.get("item_name", ""),
                h.get("quantity", 1), h.get("price", h.get("amount", 0))
            ])
        if summary_data:
            ws_sum = wb.create_sheet(title="ملخص العملاء")
            ws_sum.append(["اسم العميل", "رقم الهاتف", "إجمالي المشتريات"])
            for phone, data in summary_data.items():
                ws_sum.append([data["name"], phone, data["spent"]])

    elif report_type == "single":
        ws.title = "كشف حساب عميل"
        ws.append(["رقم الفاتورة", "التاريخ", "نوع العملية", "البيان", "الكمية", "المبلغ"])
        total_in, total_out = 0, 0
        for h in history_data:
            price_or_amount = h.get("price", h.get("amount", 0))
            ws.append([
                h.get("order_id", "-"), h.get("date", ""), h.get("type", ""),
                h.get("item_name", "-"), h.get("quantity", "-"), price_or_amount
            ])
            if h.get("type") == "شراء": total_out += price_or_amount
            else: total_in += price_or_amount
        
        ws.append([]); ws.append(["", "", "", "إجمالي الإيداعات:", "", total_in]); ws.append(["", "", "", "إجمالي المشتريات:", "", total_out])

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = white_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            
        for col in sheet.columns:
            max_length = 0
            if not col: continue
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except: pass
            sheet.column_dimensions[col_letter].width = max_length + 4

    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()

def generate_products_template():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Products_Template"
    ws.append(["القسم", "الفئة", "الاسم", "السعر 1", "السعر 2", "السعر 3", "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"])
    stream = io.BytesIO(); wb.save(stream)
    return stream.getvalue()

def generate_simple_excel(data_list):
    wb = openpyxl.Workbook(); ws = wb.active
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid"); header_font = Font(color="FFFFFF", bold=True)
    headers = ["القسم", "الفئة", "الاسم", "السعر 1", "السعر 2", "السعر 3", "كود الشحن", "الرقم التسلسلي", "الرقم السري (PIN)", "اوبريشن كود"]
    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num); cell.font = header_font; cell.fill = header_fill
    for d in data_list:
        ws.append([
            d.get('category', ''), d.get('subcategory', ''), d.get('name', ''),
            d.get('price_1', 0), d.get('price_2', 0), d.get('price_3', 0),
            d.get('code', ''), d.get('serial', ''), d.get('pin', ''), d.get('op_code', '')
        ])
    for col in ws.columns:
        max_length = 0
        if not col: continue
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value: max_length = max(max_length, len(str(cell.value)))
            except Exception: pass
        ws.column_dimensions[col_letter].width = max_length + 4
    stream = io.BytesIO(); wb.save(stream)
    return stream.getvalue()

# =======================================================
# 4. رادار منع التكرار 
# =======================================================

def process_radar_logic(chat_id, raw_codes_list, product_info=None):
    if not raw_codes_list:
        bot.send_message(chat_id, "❌ لم يتم العثور على أي بيانات صالحة لمعالجتها.")
        return
        
    bot.send_message(chat_id, "⏳ رادار الأمان يعمل الآن... يتم فحص التكرار في قاعدة البيانات.")
    incoming_codes = [str(item['code']).strip() for item in raw_codes_list if 'code' in item]
    existing_in_db = stock.find({"code": {"$in": incoming_codes}})
    db_set = set([str(doc['code']).strip() for doc in existing_in_db])
        
    accepted_docs = []; rejected_docs = []; seen_in_batch = set()
    for item in raw_codes_list:
        current_code = str(item.get('code', '')).strip()
        if not current_code: continue
        if current_code in db_set or current_code in seen_in_batch:
            rejected_docs.append(item)
        else:
            seen_in_batch.add(current_code)
            new_doc = item.copy()
            if product_info: new_doc.update(product_info)
            new_doc["sold"] = False
            new_doc["added_at"] = datetime.datetime.now()
            accepted_docs.append(new_doc)
            
    if len(accepted_docs) > 0: stock.insert_many(accepted_docs)
        
    report_msg = f"📊 **تقرير معالجة المخزون:**\n\n✅ مقبولة: `{len(accepted_docs)}`\n❌ مكررة (مرفوضة): `{len(rejected_docs)}`"
    bot.send_message(chat_id, report_msg, parse_mode="Markdown")
    
    try:
        if len(accepted_docs) > 0:
            file_bytes = generate_simple_excel(accepted_docs)
            doc_acc = io.BytesIO(file_bytes); doc_acc.name = "Accepted_New_Codes.xlsx"
            bot.send_document(chat_id, doc_acc, caption="📁 ملف الأكواد التي تم إضافتها بنجاح.")
        if len(rejected_docs) > 0:
            file_bytes = generate_simple_excel(rejected_docs)
            doc_rej = io.BytesIO(file_bytes); doc_rej.name = "Rejected_Duplicates.xlsx"
            bot.send_document(chat_id, doc_rej, caption="⚠️ ملف الأكواد المكررة (التي تم استبعادها).")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ تم تحديث المخزون بنجاح، لكن حدث خطأ أثناء إرسال ملفات الفرز: {e}")

# =======================================================
# 5. القوائم (Menus)
# =======================================================

def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 شراء", "💳 شحن", "👤 حسابي")
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

# =======================================================
# 6. التسجيل وإدارة العملاء 
# =======================================================

@bot.message_handler(commands=['start'])
def handle_start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        new_user = {
            "_id": uid, "name": None, "phone": None, "balance": 0.0, 
            "status": "frozen", "tier": 1, "failed_attempts": 0, "join": datetime.datetime.now()
        }
        users.insert_one(new_user)
        u = users.find_one({"_id": uid})

    if not u.get("name"):
        ask_msg = bot.send_message(uid, "👋 مرحباً بك في شركة الأهرام للإتصالات والتقنية.\n\nيرجى البدء بكتابة **اسمك بالكامل** (أو اسم متجرك):")
        bot.register_next_step_handler(ask_msg, process_name)
    elif not u.get("phone"):
        bot.send_message(uid, f"أهلاً بك يا {safe_str(u.get('name'))}! يرجى تزويدنا برقم هاتفك لاستكمال تفعيل الحساب.", reply_markup=contact_menu())
    else:
        status = u.get("status")
        if status == "blocked": bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        elif status == "frozen": bot.send_message(uid, "حسابك الآن (قيد المراجعة). سيتم إشعارك فور تفعيل الحساب من قبل الإدارة.")
        else: bot.send_message(uid, "أهلاً بك مجدداً في المتجر 🏪", reply_markup=menu())

def process_name(msg):
    if not msg.text or msg.text.startswith('/'):
        ask_msg = bot.send_message(msg.chat.id, "يرجى كتابة اسم صحيح بدون رموز:")
        bot.register_next_step_handler(ask_msg, process_name)
        return
    users.update_one({"_id": msg.chat.id}, {"$set": {"name": msg.text.strip()}})
    bot.send_message(msg.chat.id, f"تشرفنا بك يا {safe_str(msg.text.strip())}!\n\nالآن، يرجى مشاركة رقم هاتفك عبر الضغط على الزر بالأسفل 📱", reply_markup=contact_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact_sharing(msg):
    uid = msg.chat.id
    if msg.contact.user_id != uid:
        return bot.send_message(uid, "❌ يرجى مشاركة رقم هاتفك الخاص المرتبط بهذا الحساب.", reply_markup=contact_menu())
        
    phone = msg.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone, "tier": 1}})
    u = users.find_one({"_id": uid})
    
    if u.get("status") == "frozen":
        bot.send_message(uid, "✅ تم استلام بياناتك بنجاح.\nحسابك الآن قيد المراجعة، يرجى الانتظار لحين التفعيل من قبل الإدارة.", reply_markup=types.ReplyKeyboardRemove())
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"adm_activate_{uid}"), types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"adm_block_{uid}"))
        for admin_id in get_all_admins():
            try: bot.send_message(admin_id, f"🆕 **طلب تسجيل جديد!**\n\n📛 الاسم: {safe_str(u.get('name'))}\n🆔 ID: `{uid}`\n📱 الهاتف: `{phone}`", reply_markup=kb)
            except Exception: pass
    else: bot.send_message(uid, "✅ حسابك نشط وجاهز.", reply_markup=menu())

# =======================================================
# 7. واجهة العميل (Customer Dashboard)
# =======================================================

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def show_account_info(msg):
    uid = msg.chat.id
    u = check_user_access(uid)
    if not u: return

    safe_n = safe_str(u.get('name'))
    bal = round(float(u.get('balance', 0.0)), 2)
    phone = u.get('phone', 'غير متوفر')
    status = "نشط ✅" if u.get('status') == 'active' else "قيد المراجعة ❄️"
    
    text = (f"👤 **بيانات حسابك**\n\n📛 الاسم: {safe_n}\n🆔 معرفك: `{uid}`\n📱 الهاتف: `{phone}`\n💰 رصيدك الحالي: **{bal}**\nحالة الحساب: {status}")
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🛒 سجل المشتريات", callback_data="client_purchases"), types.InlineKeyboardButton("🧾 كشف حساب تفصيلي", callback_data="client_statement"))
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["client_purchases", "client_statement"])
def handle_client_reports(call):
    uid = call.message.chat.id
    u = check_user_access(uid)
    if not u: return bot.answer_callback_query(call.id, "عذراً، حسابك غير مفعل حالياً.", show_alert=True)

    if call.data == "client_purchases":
        history = list(transactions.find({"uid": uid, "type": "شراء"}).sort("_id", -1).limit(10))
        if not history: return bot.answer_callback_query(call.id, "لا توجد مشتريات مسجلة في حسابك.", show_alert=True)
        txt = "🛒 **آخر 10 مشتريات لك:**\n\n"
        for t in history:
            txt += f"▪️ {t.get('date', '')} | الفاتورة #{t.get('order_id', 'N/A')} | {t.get('item_name', 'منتج')} (x{t.get('quantity', 1)}) | السعر: {round(float(t.get('price', 0)), 2)}\n"
            
    elif call.data == "client_statement":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(20))
        if not history: return bot.answer_callback_query(call.id, "لا توجد حركات في حسابك.", show_alert=True)
        txt = "🧾 **كشف حساب (آخر 20 حركة):**\n\n"
        for t in history:
            if t.get('type') == "شراء": txt += f"🔴 خصم | {t.get('date', '')} | شراء {t.get('item_name', '')} | -{round(float(t.get('price', 0)), 2)}\n"
            else: txt += f"🟢 إضافة | {t.get('date', '')} | {t.get('type', '')} | +{round(float(t.get('amount', 0)), 2)}\n"
                
    bot.send_message(uid, txt, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# =======================================================
# 8. الشحن والتسوق 
# =======================================================

@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def ask_for_card_code(msg):
    u = check_user_access(msg.chat.id)
    if not u: return
    ask_msg = bot.send_message(msg.chat.id, "يرجى إرسال كود شحن الرصيد (الكارت):")
    bot.register_next_step_handler(ask_msg, process_card_charging)

def process_card_charging(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "🔄 تم إلغاء عملية الشحن.")
        return
        
    uid = msg.chat.id
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active": return bot.send_message(uid, "❌ حسابك غير مفعل أو محظور.")

    input_code = msg.text.strip()
    card = cards.find_one_and_update({"code": input_code, "used": False}, {"$set": {"used": True, "used_by": uid, "used_at": datetime.datetime.now()}})
    
    if not card:
        attempts = u.get("failed_attempts", 0) + 1
        if attempts >= 5:
            users.update_one({"_id": uid}, {"$set": {"status": "frozen", "failed_attempts": 0}})
            bot.send_message(uid, "🚫 تم إيقاف حسابك وتجميده بسبب تكرار إدخال أكواد خاطئة. تواصل مع الإدارة.")
        else:
            users.update_one({"_id": uid}, {"$set": {"failed_attempts": attempts}})
            bot.send_message(uid, f"❌ الكود غير صحيح. متبقي لك {5 - attempts} محاولات قبل تجميد الحساب.")
        return

    card_value = round(float(card["value"]), 2)
    new_balance = round(float(u.get("balance", 0.0)) + card_value, 2)
    
    users.update_one({"_id": uid}, {"$set": {"balance": new_balance, "failed_attempts": 0}})
    transactions.insert_one({"uid": uid, "user_name": u.get("name"), "type": "شحن كارت", "amount": card_value, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(uid, f"✅ تم شحن حسابك بمبلغ {card_value} بنجاح.\n💰 رصيدك الجديد: {new_balance}")
    
    for admin_id in get_all_admins():
        try: bot.send_message(admin_id, f"💳 **عملية شحن جديدة!**\n\n👤 العميل: {safe_str(u.get('name'))}\n📱 الهاتف: `{u.get('phone')}`\n💰 المبلغ: {card_value}\n💵 الرصيد الجديد: {new_balance}", parse_mode="Markdown")
        except Exception: pass

@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def start_shopping_process(msg):
    u = check_user_access(msg.chat.id)
    if not u: return
    cats = stock.distinct("category", {"sold": False})
    if not cats: return bot.send_message(msg.chat.id, "❌ لا توجد منتجات متوفرة حالياً في المتجر.")
        
    kb = types.InlineKeyboardMarkup()
    for c in cats: kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))
    bot.send_message(msg.chat.id, "يرجى اختيار القسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def handle_category_selection(call):
    cat_name = call.data.split("_", 1)[1]
    subs = stock.distinct("subcategory", {"category": cat_name, "sold": False})
    kb = types.InlineKeyboardMarkup()
    for s in subs: kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat_name}_{s}"))
    bot.edit_message_text(f"القسم: {cat_name}\nاختر الفئة:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def handle_subcategory_selection(call):
    uid = call.message.chat.id
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active": return
    
    tier = u.get("tier", 1)
    parts = call.data.split("_", 2)
    cat_name = parts[1]
    sub_name = parts[2]
    
    available_items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))
    total_count = len(available_items)
    
    if total_count < 10:
        return bot.answer_callback_query(call.id, "⚠️ الكمية المتبقية أقل من الحد الأدنى للشراء (10 أكواد).", show_alert=True)
        
    sample_item = available_items[0]
    p1 = float(sample_item.get("price_1", sample_item.get("price", 0)))
    p2 = float(sample_item.get("price_2", p1))
    p3 = float(sample_item.get("price_3", p1))
    
    if tier == 1: final_price = p1
    elif tier == 2: final_price = p2
    else: final_price = p3
    final_price = round(final_price, 2)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 تأكيد طلب شراء", callback_data=f"buy_{sample_item['_id']}"))
    info_text = (f"📦 المنتج: **{sample_item['name']}**\n💰 السعر: **{final_price}**\n📊 الكمية المتوفرة: {total_count}\n\n⚠️ أقل كمية للطلب هي 10 ومضاعفاتها.")
    bot.send_message(uid, info_text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def ask_for_quantity(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]
    
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active": return
    
    item = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item: return bot.answer_callback_query(call.id, "❌ عذراً، المنتج لم يعد متوفراً أو تم بيعه.")
    
    product_name = item['name']
    available_qty = stock.count_documents({"name": product_name, "sold": False})
    
    ask_msg = bot.send_message(uid, f"📦 المنتج: {product_name}\n📊 المتوفر حالياً: {available_qty}\n\nيرجى إرسال الكمية المطلوبة (يجب أن تكون 10 أو 20 أو 30 إلخ...):")
    bot.register_next_step_handler(ask_msg, finalize_purchase, u, item, available_qty)

def finalize_purchase(msg, user_data, item_ref, available_qty):
    if msg.text in MENU_BUTTONS:
        return bot.send_message(msg.chat.id, "🔄 تم إلغاء عملية الشراء. يرجى الضغط على الزر المطلوب مجدداً.")
        
    uid = msg.chat.id
    try:
        requested_qty = int(msg.text.strip())
        if requested_qty < 10 or requested_qty % 10 != 0: return bot.send_message(uid, "❌ الكمية يجب أن تكون من مضاعفات الـ 10 (10، 20، 50...). تم إلغاء الطلب.")
    except ValueError: return bot.send_message(uid, "❌ يرجى إدخال أرقام صحيحة فقط. تم إلغاء الطلب.")
        
    if requested_qty > available_qty: return bot.send_message(uid, f"❌ الكمية المطلوبة غير متوفرة. المتاح حالياً: {available_qty}")

    tier = user_data.get("tier", 1)
    p1 = float(item_ref.get("price_1", item_ref.get("price", 0)))
    p2 = float(item_ref.get("price_2", p1))
    p3 = float(item_ref.get("price_3", p1))
    
    if tier == 1: unit_price = p1
    elif tier == 2: unit_price = p2
    else: unit_price = p3
        
    total_cost = round(requested_qty * unit_price, 2)
    user_balance = round(float(user_data.get("balance", 0.0)), 2)
    
    if user_balance < total_cost: return bot.send_message(uid, f"❌ رصيدك غير كافي لإتمام العملية.\nالمطلوب: {total_cost}\nرصيدك الحالي: {user_balance}")

    product_name = item_ref['name']
    batch = list(stock.find({"name": product_name, "sold": False}).limit(requested_qty))
    
    if len(batch) < requested_qty: return bot.send_message(uid, "❌ حدث خطأ في توافر الأكواد بسبب سحب آخر. يرجى المحاولة مرة أخرى.")
        
    ids_to_sell = [doc['_id'] for doc in batch]
    update_res = stock.update_many({"_id": {"$in": ids_to_sell}, "sold": False}, {"$set": {"sold": True, "buyer_id": uid, "order_date": datetime.datetime.now()}})
    
    if update_res.modified_count != requested_qty:
        stock.update_many({"_id": {"$in": ids_to_sell}}, {"$set": {"sold": False}})
        return bot.send_message(uid, "❌ حدث تضارب في عملية البيع، يرجى المحاولة مرة أخرى.")

    users.update_one({"_id": uid}, {"$inc": {"balance": -total_cost}})
    order_id = get_next_order_id()
    dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    transactions.insert_one({
        "order_id": order_id, "uid": uid, "user_name": user_data.get("name"), "phone": user_data.get("phone"), 
        "type": "شراء", "item_name": product_name, "quantity": requested_qty, "price": total_cost, "date": dt_str
    })
    
    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n💰 القيمة المخصومة: {total_cost}\n\nجاري إعداد ملف الأكواد الخاص بك...")
    
    try:
        purchased_items_data = []
        for d in batch:
            purchased_items_data.append({'code': d['code'], 'serial': d.get('serial', ''), 'pin': d.get('pin', ''), 'op_code': d.get('op_code', '')})
            
        file_bytes = generate_customer_excel_file(purchased_items_data, order_id, dt_str, product_name)
        doc_user = io.BytesIO(file_bytes)
        doc_user.name = f"Invoice_{order_id}.xlsx"
        bot.send_document(uid, doc_user, caption=f"📁 فاتورة الأكواد | رقم #{order_id}")
        
        safe_n = safe_str(user_data.get('name'))
        admin_msg = (
            f"🛒 **عملية شراء جديدة!**\n\nالفاتورة: #{order_id}\n👤 العميل: {safe_n}\n"
            f"📱 الهاتف: {user_data.get('phone')}\n🎚️ المستوى: {tier}\n📦 المنتج: {product_name}\n"
            f"🔢 الكمية: {requested_qty}\n💰 المبلغ المدفوع: {total_cost}"
        )
        
        for admin_id in get_all_admins():
            try:
                doc_admin = io.BytesIO(file_bytes)
                doc_admin.name = f"Admin_Inv_{order_id}.xlsx"
                bot.send_message(admin_id, admin_msg)
                bot.send_document(admin_id, doc_admin, caption=f"📁 نسخة فاتورة #{order_id}")
            except Exception: pass
            
    except Exception as e:
        traceback.print_exc()
        bot.send_message(uid, f"⚠️ تم حفظ مشترياتك في النظام بنجاح، لكن حدث خطأ أثناء تجهيز ملف الإكسيل. يرجى التواصل مع الإدارة للحصول على الأكواد.")

    remaining_stock = stock.count_documents({"name": product_name, "sold": False})
    if remaining_stock <= 30:
        for admin_id in get_all_admins():
            try: bot.send_message(admin_id, f"⚠️ **تنبيه انخفاض المخزون** ⚠️\n\nالمنتج: `{product_name}`\nالمتبقي: **{remaining_stock}** كود فقط.", parse_mode="Markdown")
            except Exception: pass

    if SHEET_WEBHOOK_URL and SHEET_WEBHOOK_URL.startswith("http"):
        try:
            payload = {"order_id": order_id, "date": dt_str, "phone": user_data.get('phone'), "item_name": f"{product_name} (x{requested_qty})", "price": total_cost}
            requests.post(SHEET_WEBHOOK_URL, json=payload, timeout=3)
        except Exception: pass

# =======================================================
# 10. لوحة تحكم الإدارة (Admin Dashboard)
# =======================================================

@bot.message_handler(commands=['admin'])
def show_admin_dashboard(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "👑 مرحباً بك في لوحة تحكم الإدارة العليا.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def return_to_client_mode(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل.", reply_markup=menu())

# --- أ. قائمة المستخدمين ---
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def admin_users_list(msg):
    if not is_admin(msg.chat.id): return
    try:
        text = "👥 قائمة آخر 30 مستخدم مسجل في النظام:\n\n"
        for u in users.find().sort("join", -1).limit(30):
            stat = "✅" if u.get('status') == 'active' else ("🚫" if u.get('status') == 'blocked' else "❄️")
            safe_n = safe_str(u.get('name'))
            phone = u.get('phone', 'بدون')
            balance = round(float(u.get('balance', 0)), 2)
            text += f"📛 {safe_n} | 📱 {phone} | 💰 {balance} | {stat}\n"
        bot.send_message(msg.chat.id, text)
    except Exception as e: bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء جلب قائمة المستخدمين:\n{e}")

# --- ب. سجل الفواتير ---
@bot.message_handler(func=lambda m: m.text == "🧾 سجل الفواتير")
def admin_invoices_log(msg):
    if not is_admin(msg.chat.id): return
    try:
        history = list(transactions.find({"type": "شراء", "order_id": {"$exists": True}}).sort("_id", -1).limit(40))
        if not history: return bot.send_message(msg.chat.id, "لا توجد فواتير مبيعات مسجلة حتى الآن.")
        text = "🧾 سجل آخر 40 فاتورة مبيعات:\n\n"
        for t in history:
            order_id = t.get('order_id', '-')
            safe_n = safe_str(t.get('user_name'))
            item_name = t.get('item_name', '-')
            qty = t.get('quantity', 1)
            price = round(float(t.get('price', 0)), 2)
            text += f"▪️ #{order_id} | 👤 {safe_n} | 🛒 {item_name} (x{qty}) | 💰 {price}\n"
        bot.send_message(msg.chat.id, text)
    except Exception as e: bot.send_message(msg.chat.id, f"❌ حدث خطأ:\n{e}")

# --- ج. إدارة العميل ---
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def admin_manage_customer(msg):
    if not is_admin(msg.chat.id): return
    ask_msg = bot.send_message(msg.chat.id, "يرجى إرسال رقم هاتف العميل للبحث عنه:")
    bot.register_next_step_handler(ask_msg, admin_find_and_render_customer)

def admin_find_and_render_customer(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء.")
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ لم يتم العثور على العميل.")
    admin_render_customer_card(u["_id"], msg.chat.id)

def admin_render_customer_card(uid, chat_id, message_id=None):
    u = users.find_one({"_id": uid})
    if not u: return
    tier = u.get("tier", 1)
    tier_label = "مستوى 1 🥉" if tier == 1 else ("مستوى 2 🥈" if tier == 2 else "مستوى 3 🥇")
    stat = u.get("status")
    stat_label = "محظور 🚫" if stat == "blocked" else ("نشط ✅" if stat == "active" else "مجمد ❄️")
    safe_n = safe_str(u.get('name'))
    bal = round(float(u.get('balance', 0)), 2)
    
    info = (
        f"👤 **ملف بيانات العميل:**\n\n📛 الاسم: {safe_n}\n🆔 ID: `{uid}`\n📱 الهاتف: `{u.get('phone')}`\n"
        f"💰 الرصيد: **{bal}**\n🎚️ المستوى الحالي: **{tier_label}**\nحالة الحساب: **{stat_label}**"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    if stat == "active":
        kb.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"adm_freeze_{uid}"), types.InlineKeyboardButton("🚫 حظر و طرد", callback_data=f"adm_block_{uid}"))
    elif stat == "frozen":
        kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"adm_activate_{uid}"), types.InlineKeyboardButton("🚫 حظر و طرد", callback_data=f"adm_block_{uid}"))
    elif stat == "blocked":
        kb.add(types.InlineKeyboardButton("✅ فك الحظر", callback_data=f"adm_activate_{uid}"))
        
    kb.add(types.InlineKeyboardButton("🎚️ تغيير مستوى الأسعار", callback_data=f"adm_chgtier_{uid}"), types.InlineKeyboardButton("📊 تقرير عمليات العميل", callback_data=f"adm_report_{uid}"))
    
    if message_id:
        try: bot.edit_message_text(info, chat_id, message_id, reply_markup=kb, parse_mode="Markdown")
        except: pass
    else: bot.send_message(chat_id, info, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def handle_admin_customer_actions(call):
    parts = call.data.split("_")
    action = parts[1]
    uid = int(parts[2])
    
    if action == "report":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(15))
        if not history: return bot.answer_callback_query(call.id, "لا توجد عمليات لهذا العميل.")
        txt = f"📊 آخر عمليات العميل:\n\n"
        for t in history:
            date_str = t.get('date', '')
            t_type = t.get('type', '')
            price = round(float(t.get('price', t.get('amount', 0))), 2)
            txt += f"▪️ {date_str} | {t_type} | {price}\n"
        bot.send_message(call.message.chat.id, txt)
        return bot.answer_callback_query(call.id)

    if action == "chgtier":
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("المستوى 1 🥉", callback_data=f"set_tier_1_{uid}"), types.InlineKeyboardButton("المستوى 2 🥈", callback_data=f"set_tier_2_{uid}"), types.InlineKeyboardButton("المستوى 3 🥇", callback_data=f"set_tier_3_{uid}"))
        kb.add(types.InlineKeyboardButton("🔙 رجوع للخلف", callback_data=f"adm_back_{uid}"))
        return bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)

    if action == "freeze": users.update_one({"_id": uid}, {"$set": {"status": "frozen"}})
    elif action == "activate": users.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
    elif action == "block": users.update_one({"_id": uid}, {"$set": {"status": "blocked"}})
    elif action == "back": pass
    
    bot.answer_callback_query(call.id, "تم تحديث بيانات العميل بنجاح.")
    admin_render_customer_card(uid, call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_tier_"))
def handle_tier_setting(call):
    parts = call.data.split("_")
    level = int(parts[2])
    uid = int(parts[3])
    users.update_one({"_id": uid}, {"$set": {"tier": level}})
    bot.answer_callback_query(call.id, f"تم تغيير مستوى العميل إلى {level}")
    admin_render_customer_card(uid, call.message.chat.id, call.message.message_id)

# --- د. إضافة منتجات ---
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def admin_add_product(msg):
    if not is_admin(msg.chat.id): return
    txt = (
        "➕ **إضافة منتجات للمخزن:**\n\n📁 **الطريقة الأولى:** قم بتحميل قالب الإكسيل المرفق، املأه وأعد رفعه.\n"
        "✍️ **الطريقة الثانية:** أرسل البيانات بالتنسيق التالي:\n`القسم:الفئة:الاسم:السعر1:السعر2:السعر3`"
    )
    try:
        file_bytes = generate_products_template()
        doc = io.BytesIO(file_bytes)
        doc.name = "Template_Products.xlsx"
        ask_msg = bot.send_document(msg.chat.id, doc, caption=txt, parse_mode="Markdown")
        bot.register_next_step_handler(ask_msg, admin_process_product_input)
    except Exception as e: bot.send_message(msg.chat.id, f"❌ حدث خطأ في توليد القالب: {e}")

def admin_process_product_input(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    if msg.document:
        if not msg.document.file_name.endswith('.xlsx'): return bot.send_message(msg.chat.id, "❌ يرجى رفع ملف إكسيل بصيغة .xlsx فقط.")
        bot.send_message(msg.chat.id, "⏳ جاري قراءة البيانات من الملف...")
        try:
            file_info = bot.get_file(msg.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            wb = openpyxl.load_workbook(io.BytesIO(downloaded))
            ws = wb.active
            
            batch_data, errors_count = [], 0
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0 or not row[0]: continue
                try:
                    price_1 = float(row[3])
                    price_2 = float(row[4]) if len(row) > 4 and row[4] else price_1
                    price_3 = float(row[5]) if len(row) > 5 and row[5] else price_1
                    
                    code_val = str(row[6]).strip() if len(row) > 6 and row[6] else ""
                    if not code_val:
                        errors_count += 1
                        continue
                        
                    batch_data.append({
                        "category": str(row[0]).strip(), "subcategory": str(row[1]).strip(), "name": str(row[2]).strip(),
                        "price_1": price_1, "price_2": price_2, "price_3": price_3,
                        "code": code_val, "serial": str(row[7]).strip() if len(row) > 7 and row[7] else "", 
                        "pin": str(row[8]).strip() if len(row) > 8 and row[8] else "", "op_code": str(row[9]).strip() if len(row) > 9 and row[9] else ""
                    })
                except Exception: errors_count += 1
            if errors_count > 0: bot.send_message(msg.chat.id, f"⚠️ تم تخطي {errors_count} صف لوجود بيانات ناقصة.")
            process_radar_logic(msg.chat.id, batch_data)
        except Exception as e: bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء معالجة الملف:\n{e}")
        
    elif msg.text and ":" in msg.text:
        try:
            parts = msg.text.split(":")
            p1 = float(parts[3].strip())
            p2 = float(parts[4].strip()) if len(parts) > 4 else p1
            p3 = float(parts[5].strip()) if len(parts) > 5 else p1
            
            temp_admin_data[msg.chat.id] = {"info": {"cat": parts[0].strip(), "sub": parts[1].strip(), "name": parts[2].strip(), "price_1": p1, "price_2": p2, "price_3": p3}}
            ask_msg = bot.send_message(msg.chat.id, "✅ تم حفظ بيانات المنتج.\nالآن أرسل الأكواد كـ **رسالة نصية** بالتنسيق التالي:\n`الكود:التسلسلي:PIN:أوبريشن`")
            bot.register_next_step_handler(ask_msg, admin_process_manual_codes)
        except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح. تأكد من إدخال البيانات مفصولة بنقطتين (:).")

def admin_process_manual_codes(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    p_info = temp_admin_data.get(msg.chat.id, {}).get("info")
    if not p_info: return bot.send_message(msg.chat.id, "❌ انتهت جلسة الإضافة. حاول من جديد.")
    
    batch_data = []
    if msg.text:
        for line in msg.text.split("\n"):
            if not line.strip(): continue
            pts = line.split(":")
            batch_data.append({
                "code": pts[0].strip(), "serial": pts[1].strip() if len(pts) > 1 else "",
                "pin": pts[2].strip() if len(pts) > 2 else "", "op_code": pts[3].strip() if len(pts) > 3 else ""
            })
    process_radar_logic(msg.chat.id, batch_data, p_info)
    if msg.chat.id in temp_admin_data: del temp_admin_data[msg.chat.id]

# --- هـ. تحديث الأسعار المجمع ---
@bot.message_handler(func=lambda m: m.text == "💵 أسعار المستويات")
def admin_bulk_price_edit(msg):
    if not is_admin(msg.chat.id): return
    prods = list(stock.aggregate([{"$match": {"sold": False}}, {"$group": {"_id": "$name", "cat": {"$first": "$category"}, "sub": {"$first": "$subcategory"}, "p1": {"$first": "$price_1"}, "p2": {"$first": "$price_2"}, "p3": {"$first": "$price_3"}}}]))
    if not prods: return bot.send_message(msg.chat.id, "❌ لا توجد منتجات للبيع في المخزن لتعديل أسعارها.")
        
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["الاسم (لا تقم بتعديله أبداً)", "القسم", "الفئة", "السعر للمستوى 1", "السعر للمستوى 2", "السعر للمستوى 3"])
    
    for cell in ws[1]: cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid"); cell.font = Font(color="FFFFFF", bold=True)
    for p in prods: ws.append([p["_id"], p.get("cat", ""), p.get("sub", ""), p.get("p1", 0), p.get("p2", 0), p.get("p3", 0)])
        
    for col in ws.columns:
        max_length = 0
        if not col: continue
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value: max_length = max(max_length, len(str(cell.value)))
            except Exception: pass
        ws.column_dimensions[col_letter].width = max_length + 4

    stream = io.BytesIO()
    wb.save(stream)
    doc = io.BytesIO(stream.getvalue())
    doc.name = "Prices_Update_List.xlsx"
    
    ask_msg = bot.send_document(msg.chat.id, doc, caption="📁 **أداة تعديل الأسعار الشاملة**\n\nقم بتحميل الملف، عدل الأسعار ثم أعد إرساله.")
    bot.register_next_step_handler(ask_msg, admin_finalize_price_update)

def admin_finalize_price_update(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    if not msg.document or not msg.document.file_name.endswith('.xlsx'): return bot.send_message(msg.chat.id, "❌ يرجى رفع ملف إكسيل بصيغة .xlsx")
        
    bot.send_message(msg.chat.id, "⏳ جاري تحديث الأسعار...")
    try:
        file_info = bot.get_file(msg.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        wb = openpyxl.load_workbook(io.BytesIO(downloaded))
        ws = wb.active
        
        updated_count = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 or not row[0]: continue
            name = str(row[0]).strip()
            try:
                p1 = float(row[3]) if row[3] is not None else 0
                p2 = float(row[4]) if row[4] is not None else p1
                p3 = float(row[5]) if row[5] is not None else p1
                res = stock.update_many({"name": name, "sold": False}, {"$set": {"price_1": p1, "price_2": p2, "price_3": p3}})
                if res.modified_count > 0: updated_count += 1
            except Exception: continue
                
        bot.send_message(msg.chat.id, f"✅ تمت العملية بنجاح. تم تحديث أسعار `{updated_count}` نوع من المنتجات لجميع المستويات.")
    except Exception as e: bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء المعالجة:\n{e}")

# --- و. إدارة المخزون الداخلي ---
@bot.message_handler(func=lambda m: m.text == "📦 إدارة المخزون")
def manage_stock_cmd(msg):
    if not is_admin(msg.chat.id): return
    names = stock.distinct("name", {"sold": False})
    if not names: return bot.send_message(msg.chat.id, "❌ المخزن فارغ حالياً.")
        
    text = "📦 **المنتجات المتوفرة حالياً في المخزن:**\n\n"
    for n in names:
        count = stock.count_documents({"name": n, "sold": False})
        text += f"▪️ `{n}` (الكمية: {count})\n"
        
    ask_msg = bot.send_message(msg.chat.id, text + "\n👉 أرسل **اسم المنتج** (انسخه من القائمة بالأعلى) لإدارته:", parse_mode="Markdown")
    bot.register_next_step_handler(ask_msg, show_stock_item_panel)

def show_stock_item_panel(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    name = msg.text.strip()
    count = stock.count_documents({"name": name, "sold": False})
    item = stock.find_one({"name": name, "sold": False})
    
    if not item: return bot.send_message(msg.chat.id, "❌ المنتج غير موجود في المخزن.")
        
    p1 = item.get("price_1", item.get("price", 0))
    p2 = item.get("price_2", p1)
    p3 = item.get("price_3", p1)
        
    text = (f"📦 المنتج: `{name}`\n💰 الأسعار الحالية:\nمستوى 1: {p1} | مستوى 2: {p2} | مستوى 3: {p3}\n📊 الكمية المتوفرة: {count}")
    
    temp_admin_data[msg.chat.id] = {"mng_item_name": name}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💰 تعديل السعر (فردي)", callback_data="stk_price"))
    kb.add(types.InlineKeyboardButton("➖ حذف كمية معينة", callback_data="stk_delqty"))
    kb.add(types.InlineKeyboardButton("❌ حذف المنتج بالكامل", callback_data="stk_delall"))
    bot.send_message(msg.chat.id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("stk_"))
def handle_stock_actions(call):
    action = call.data.split("_")[1]
    data = temp_admin_data.get(call.message.chat.id)
    
    if not data or "mng_item_name" not in data: return bot.answer_callback_query(call.id, "❌ انتهت الجلسة.", show_alert=True)
        
    name = data["mng_item_name"]
    if action == "price":
        ask_msg = bot.send_message(call.message.chat.id, f"أرسل الأسعار الجديدة للمنتج `{name}` بالتنسيق:\nسعر1:سعر2:سعر3", parse_mode="Markdown")
        bot.register_next_step_handler(ask_msg, admin_update_stock_price, name)
        bot.answer_callback_query(call.id)
    elif action == "delqty":
        ask_msg = bot.send_message(call.message.chat.id, f"أرسل عدد الأكواد المراد مسحها من منتج `{name}`:")
        bot.register_next_step_handler(ask_msg, admin_delete_stock_qty, name)
        bot.answer_callback_query(call.id)
    elif action == "delall":
        res = stock.delete_many({"name": name, "sold": False})
        bot.answer_callback_query(call.id, f"تم مسح {res.deleted_count} كود.")
        bot.edit_message_text(f"✅ تم حذف المنتج `{name}` بالكامل.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

def admin_update_stock_price(msg, name):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        parts = msg.text.split(":")
        p1 = float(parts[0].strip())
        p2 = float(parts[1].strip()) if len(parts) > 1 else p1
        p3 = float(parts[2].strip()) if len(parts) > 2 else p1
        
        res = stock.update_many({"name": name, "sold": False}, {"$set": {"price_1": p1, "price_2": p2, "price_3": p3}})
        bot.send_message(msg.chat.id, f"✅ تم تحديث الأسعار للمنتج `{name}` بنجاح.", parse_mode="Markdown")
    except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح.")

def admin_delete_stock_qty(msg, name):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        qty_to_delete = int(msg.text.strip())
        docs_to_delete = list(stock.find({"name": name, "sold": False}).limit(qty_to_delete))
        if not docs_to_delete: return bot.send_message(msg.chat.id, "❌ لا يوجد رصيد متاح للحذف.")
            
        ids = [d['_id'] for d in docs_to_delete]
        res = stock.delete_many({"_id": {"$in": ids}})
        bot.send_message(msg.chat.id, f"✅ تم حذف {res.deleted_count} كود بنجاح.", parse_mode="Markdown")
    except Exception: bot.send_message(msg.chat.id, "❌ يجب إرسال أرقام صحيحة.")

# --- ز. استخراج تقارير الإكسيل ---
@bot.message_handler(func=lambda m: m.text == "📊 تقارير إكسيل")
def admin_excel_reports(msg):
    if not is_admin(msg.chat.id): return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📄 تقرير شامل للمبيعات", callback_data="rep_all"),
           types.InlineKeyboardButton("👤 تقرير مخصص لعميل", callback_data="rep_single"))
    bot.send_message(msg.chat.id, "الرجاء اختيار نوع التقرير الذي تريد استخراجه:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rep_"))
def admin_report_dates(call):
    rep_type = call.data.split("_")[1]
    if call.message.chat.id not in temp_admin_data: temp_admin_data[call.message.chat.id] = {}
    temp_admin_data[call.message.chat.id]["rep_type"] = rep_type
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🕒 كل الأوقات والتواريخ", callback_data="dt_all"),
           types.InlineKeyboardButton("📅 تحديد فترة (من-إلى)", callback_data="dt_custom"))
    bot.edit_message_text("هل تريد استخراج التقرير لكل الأوقات، أم تحديد فترة زمنية معينة؟", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dt_"))
def admin_report_finalize(call):
    uid = call.message.chat.id
    mode = call.data.split("_")[1]
    rep_type = temp_admin_data.get(uid, {}).get("rep_type")
    
    if not rep_type: return bot.answer_callback_query(call.id, "انتهت الجلسة، حاول مرة أخرى.", show_alert=True)
    bot.answer_callback_query(call.id)
    
    if mode == "all": admin_execute_report(uid, rep_type, None, None)
    else:
        ask_msg = bot.send_message(uid, "أرسل التاريخ (من) و (إلى) بالتنسيق التالي بدقة:\n`YYYY-MM-DD:YYYY-MM-DD`", parse_mode="Markdown")
        bot.register_next_step_handler(ask_msg, admin_process_date_input, rep_type)

def admin_process_date_input(msg, rep_type):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        parts = msg.text.split(":")
        start_dt = parts[0].strip()
        end_dt = parts[1].strip()
        admin_execute_report(msg.chat.id, rep_type, start_dt, end_dt)
    except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح. قم بإعادة الطلب وتأكد من الفاصل (:).")

def admin_execute_report(uid, rep_type, start_date, end_date):
    filtr = {}
    if start_date and end_date: filtr = {"date": {"$gte": start_date, "$lte": end_date + " 23:59"}}
    
    if rep_type == "all":
        bot.send_message(uid, "⏳ جاري تجميع بيانات المبيعات وتجهيز ملف الإكسيل...")
        data = list(transactions.find(filtr).sort("_id", -1))
        
        if not data: return bot.send_message(uid, "❌ لا توجد عمليات مسجلة في النظام خلال هذه الفترة.")
            
        summary = {}
        for t in data:
            phone = t.get("phone", "بدون رقم")
            if t.get("type") == "شراء":
                if phone not in summary: summary[phone] = {"name": t.get("user_name", "غير مسجل"), "spent": 0}
                summary[phone]["spent"] += t.get("price", 0)
                
        file_bytes = generate_admin_report_excel("all", data, summary)
        doc = io.BytesIO(file_bytes)
        doc.name = "Report_All_Operations.xlsx"
        bot.send_document(uid, doc, caption="✅ تم تجهيز التقرير الشامل.")
        
    else:
        ask_msg = bot.send_message(uid, "يرجى إرسال رقم الهاتف للعميل المطلوب استخراج تقريره:")
        bot.register_next_step_handler(ask_msg, admin_execute_single_report, filtr)

def admin_execute_single_report(msg, filtr):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ العميل غير موجود.")
        
    query = {"uid": u["_id"]}
    query.update(filtr)
    
    data = list(transactions.find(query).sort("_id", -1))
    if not data: return bot.send_message(msg.chat.id, "❌ لا توجد عمليات مسجلة لهذا العميل في هذه الفترة.")
        
    file_bytes = generate_admin_report_excel("single", data)
    doc = io.BytesIO(file_bytes)
    doc.name = f"Report_{u.get('phone', 'Client')}.xlsx"
    bot.send_document(msg.chat.id, doc, caption=f"✅ تقرير مخصص للعميل: {safe_str(u.get('name'))}")

# --- ح. إدارة الرصيد ---
@bot.message_handler(func=lambda m: m.text == "💰 ضبط الرصيد")
def admin_set_balance(msg):
    if not is_admin(msg.chat.id): return
    ask = bot.send_message(msg.chat.id, "أرسل التعديل بالتنسيق (رقم_الهاتف:الرصيد_الجديد):\nمثال: `0940719000:500`", parse_mode="Markdown")
    bot.register_next_step_handler(ask, execute_set_balance)

def execute_set_balance(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        parts = msg.text.split(":")
        u = find_customer(parts[0])
        if u:
            new_bal = round(float(parts[1].strip()), 2)
            users.update_one({"_id": u["_id"]}, {"$set": {"balance": new_bal}})
            transactions.insert_one({"uid": u["_id"], "user_name": u.get("name"), "type": "ضبط رصيد من الإدارة", "amount": new_bal, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            bot.send_message(msg.chat.id, f"✅ تم ضبط رصيد العميل ليصبح {new_bal}")
            try: bot.send_message(u["_id"], f"⚙️ إشعار من الإدارة: تم تحديث رصيدك ليصبح {new_bal}")
            except: pass
        else: bot.send_message(msg.chat.id, "❌ العميل غير موجود.")
    except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح.")

@bot.message_handler(func=lambda m: m.text == "💳 شحن يدوي")
def admin_direct_charge(msg):
    if not is_admin(msg.chat.id): return
    ask = bot.send_message(msg.chat.id, "أرسل الشحن بالتنسيق (رقم_الهاتف:قيمة_الإضافة):\nمثال: `0940719000:50`", parse_mode="Markdown")
    bot.register_next_step_handler(ask, execute_direct_charge)

def execute_direct_charge(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        parts = msg.text.split(":")
        u = find_customer(parts[0])
        if u:
            amt = round(float(parts[1].strip()), 2)
            users.update_one({"_id": u["_id"]}, {"$inc": {"balance": amt}})
            transactions.insert_one({"uid": u["_id"], "user_name": u.get("name"), "type": "إضافة رصيد مباشر", "amount": amt, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            bot.send_message(msg.chat.id, f"✅ تمت الإضافة بنجاح.")
            try: bot.send_message(u["_id"], f"🎁 إشعار من الإدارة: تم إيداع {amt} في حسابك.")
            except: pass
        else: bot.send_message(msg.chat.id, "❌ العميل غير موجود.")
    except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح.")

@bot.message_handler(func=lambda m: m.text == "🎫 توليد")
def admin_generate_cards(msg):
    if not is_admin(msg.chat.id): return
    ask = bot.send_message(msg.chat.id, "أرسل العدد والقيمة بالتنسيق (العدد:القيمة)\nمثال لتوليد 10 كروت فئة 50:\n`10:50`", parse_mode="Markdown")
    bot.register_next_step_handler(ask, execute_generate_cards)

def execute_generate_cards(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        parts = msg.text.split(":")
        count = int(parts[0].strip())
        val = round(float(parts[1].strip()), 2)
        
        arr = []
        result_text = f"✅ تم توليد {count} كروت شحن فئة {val}:\n\n"
        
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            arr.append({"code": code, "value": val, "used": False})
            result_text += f"`{code}`\n"
            
        cards.insert_many(arr)
        bot.send_message(msg.chat.id, result_text, parse_mode="Markdown")
    except Exception: bot.send_message(msg.chat.id, "❌ التنسيق غير صحيح.")

# =======================================================
# 11. الأوامر المخفية والسرية
# =======================================================

@bot.message_handler(commands=['FRP', 'frp'])
def frp_reset_command(msg):
    if msg.chat.id != OWNER_ID: return
    ask = bot.send_message(
        msg.chat.id, 
        "⚠️ **تحذير: أمر فورمات المصنع الشامل** ⚠️\n\nأنت على وشك مسح كل شيء.\nأرسل هذه الجملة حرفياً للتأكيد:\n`تأكيد الحذف النهائي`", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(ask, execute_frp_wipe)

def execute_frp_wipe(msg):
    if msg.text == "تأكيد الحذف النهائي":
        users.delete_many({})
        stock.delete_many({})
        transactions.delete_many({})
        admins_db.delete_many({})
        counters.delete_many({})
        cards.delete_many({})
        bot.send_message(msg.chat.id, "✅ تم تصفير النظام وعودته لحالة المصنع بالكامل.")
    else: bot.send_message(msg.chat.id, "❌ تم إلغاء عملية المسح.")

@bot.message_handler(commands=['ADD', 'add'])
def add_sub_admin_command(msg):
    if msg.chat.id != OWNER_ID: return
    ask = bot.send_message(msg.chat.id, "أرسل رقم الـ ID الخاص بالشخص لترقيته إلى مدير:")
    bot.register_next_step_handler(ask, execute_add_admin)

def execute_add_admin(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    try:
        new_admin_id = int(msg.text.strip())
        admins_db.update_one(
            {"_id": new_admin_id}, 
            {"$set": {"added_by": msg.chat.id, "join_date": datetime.datetime.now()}}, 
            upsert=True
        )
        bot.send_message(msg.chat.id, f"✅ تمت ترقية `{new_admin_id}` بنجاح.", parse_mode="Markdown")
        try: bot.send_message(new_admin_id, "🎉 تهانينا! تمت ترقيتك لمشرف في النظام. أرسل /admin للدخول للوحة.")
        except: pass
    except Exception: bot.send_message(msg.chat.id, "❌ يرجى إرسال ID صحيح (أرقام فقط).")

@bot.message_handler(commands=['Block', 'block'])
def block_user_command(msg):
    if not is_admin(msg.chat.id): return
    ask = bot.send_message(msg.chat.id, "أرسل رقم الهاتف المراد حظره وطرد صاحبه من النظام:")
    bot.register_next_step_handler(ask, execute_block)

def execute_block(msg):
    if msg.text in MENU_BUTTONS: return bot.send_message(msg.chat.id, "🔄 تم الإلغاء. يرجى الضغط على الزر مجدداً.")
    u = find_customer(msg.text)
    if u:
        users.update_one({"_id": u["_id"]}, {"$set": {"status": "blocked"}})
        bot.send_message(msg.chat.id, "✅ تم الحظر.")
        try: bot.send_message(u["_id"], "تم حظرك من قبل الادارة وللاستفسار تواصل معنا", reply_markup=types.ReplyKeyboardRemove())
        except: pass
    else: bot.send_message(msg.chat.id, "❌ العميل غير موجود.")

# =======================================================
# 12. محرك تشغيل السيرفر المحصن (Render Setup)
# =======================================================

app = Flask(__name__)

@app.route('/')
def health_check_route():
    return "<h1>شركة الأهرام للإتصالات - البوت يعمل بكامل طاقته 🚀</h1>"

def bot_polling_worker():
    """عزل البوت عن الويب سيرفر وحل مشكلة 409 Conflict"""
    print("⏳ جاري تنظيف الاتصالات القديمة...")
    try:
        bot.remove_webhook()
    except: pass
    
    # إيقاف مؤقت للسماح لأي نسخة قديمة معلقة بالخروج (حل مشكلة 409)
    time.sleep(3) 
    
    print("🚀 STARTED: Telegram Polling Initialized...")
    while True:
        try:
            # إضافة skip_pending=True لتجاهل الطلبات المتضاربة
            bot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception as e:
            print(f"⚠️ POLLING ERROR: {e}")
            time.sleep(5)

if __name__ == "__main__":
    polling_thread = threading.Thread(target=bot_polling_worker)
    polling_thread.daemon = True
    polling_thread.start()
    
    port_number = int(os.environ.get("PORT", 8080))
    print(f"🌍 WEB SERVER: Listening on Port {port_number}")
    app.run(host="0.0.0.0", port=port_number)
