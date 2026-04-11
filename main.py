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

# =======================================================
# 1. الإعدادات الأساسية (Configuration)
# =======================================================

API_TOKEN = "8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc"

# المدير الأساسي (المالك)
OWNER_ID = 1262656649
ADMIN_IDS = [OWNER_ID] 

# الاتصال بقاعدة بيانات MongoDB
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["AlAhram_DB"]

# تعريف المجموعات (Collections)
users = db["users"]
stock = db["stock"]
cards = db["cards"]
transactions = db["transactions"]
counters = db["counters"]
admins_db = db["admins"]

# رابط جوجل شيت للمزامنة الخارجية
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzPrw8oANq8Aek6O6URoTU0kDVjb1ZtoVdYkhpqAqM6Nuws4ZmcPRC9JtoNZvWoMzUb/exec"

bot = telebot.TeleBot(API_TOKEN)

# قائمة الأزرار الرئيسية للإدارة للمقارنة والتحقق
MENU_BUTTONS = [
    "🛒 شراء", "💳 شحن", "👤 حسابي", "👥 المستخدمين", 
    "🎫 توليد", "➕ منتج", "💳 شحن يدوي", "⚙️ إدارة عميل", 
    "💰 ضبط الرصيد", "🧾 سجل الفواتير", "📦 إدارة المخزون", 
    "📊 تقارير إكسيل", "💵 أسعار المستويات", "🏪 العودة للمتجر"
]

temp_admin_data = {}

# =======================================================
# 2. الدوال المساعدة وتأمين النصوص (Utility Functions)
# =======================================================

def safe_str(text):
    """تنظيف النصوص من رموز الماركدوان لمنع تعليق الرسائل في تيليجرام"""
    if text is None:
        return "بدون"
    bad_chars = ["_", "*", "`", "[", "]", "(", ")", "~", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    res = str(text)
    for char in bad_chars:
        res = res.replace(char, " ")
    return res.strip()

def is_admin(uid):
    """التحقق مما إذا كان المستخدم مديراً"""
    if uid in ADMIN_IDS:
        return True
    if admins_db.find_one({"_id": uid}):
        return True
    return False

def get_all_admins():
    """جلب قائمة بكل المشرفين لإرسال الإشعارات"""
    admins = list(ADMIN_IDS)
    for a in admins_db.find():
        if a["_id"] not in admins:
            admins.append(a["_id"])
    return admins

def is_valid_val(val):
    """التحقق من صحة القيمة المدخلة في ملفات الإكسيل"""
    if val is None:
        return False
    s_val = str(val).strip().lower()
    if s_val in ["", "none", "null", "بدون", "nan"]:
        return False
    return True

def find_customer(text):
    """البحث عن عميل عبر ID أو رقم الهاتف"""
    text = text.strip()
    if text.isdigit():
        u = users.find_one({"_id": int(text)})
        if u: return u
    
    # تنظيف رقم الهاتف للبحث
    clean_phone = text.replace("+", "").replace(" ", "").lstrip("0")
    if clean_phone:
        u = users.find_one({"phone": {"$regex": f"{clean_phone}$"}})
        if u: return u
    return None

def get_next_order_id():
    """توليد رقم تسلسلي للفواتير"""
    doc = counters.find_one_and_update(
        {"_id": "order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

# =======================================================
# 3. محرك معالجة الإكسيل (Excel Engine)
# =======================================================

def generate_customer_excel_file(items_data, order_id, dt_now, product_name):
    """إنشاء فاتورة العميل الديناميكية التي تخفي الأعمدة الفارغة"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Invoice_{order_id}"
    
    # إعدادات الألوان والتنسيق
    title_fill = PatternFill(start_color="002060", end_color="002060", fill_type="solid")
    info_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    white_font = Font(color="FFFFFF", bold=True)
    centered = Alignment(horizontal="center", vertical="center")
    
    # فحص البيانات المتوفرة في هذه العملية
    has_serial = any(is_valid_val(d.get('serial')) for d in items_data)
    has_pin = any(is_valid_val(d.get('pin')) for d in items_data)
    has_opcode = any(is_valid_val(d.get('op_code')) for d in items_data)
    
    # بناء الهيدر ديناميكياً
    headers = ["م", "اسم المنتج", "كود الشحن"]
    if has_serial: headers.append("الرقم التسلسلي")
    if has_pin: headers.append("الرقم السري (PIN)")
    if has_opcode: headers.append("أوبريشن كود")
    
    last_col_idx = len(headers)
    last_col_letter = get_column_letter(last_col_idx)
    
    # تصميم رأس الصفحة
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
    
    ws.append([]) # سطر فارغ للجمالية
    
    # إضافة عناوين الجدول
    ws.append(headers)
    for cell in ws[4]:
        cell.font = white_font
        cell.fill = header_fill
        cell.alignment = centered
    
    # تعبئة البيانات
    for i, d in enumerate(items_data, 1):
        row_data = [i, product_name, d['code']]
        if has_serial: row_data.append(d.get('serial', ''))
        if has_pin: row_data.append(d.get('pin', ''))
        if has_opcode: row_data.append(d.get('op_code', ''))
        
        ws.append(row_data)
        for cell in ws[ws.max_row]:
            cell.alignment = centered

    # ضبط تلقائي لعرض الأعمدة
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 5

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

def generate_admin_report_excel(report_type, history_data, summary_data=None):
    """إنشاء تقارير الإدارة الشاملة أو الفردية"""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    white_font = Font(color="FFFFFF", bold=True)
    
    if report_type == "all":
        ws.title = "سجل المبيعات الشامل"
        headers = ["الفاتورة", "التاريخ", "الاسم", "الهاتف", "المنتج", "الكمية", "المبلغ"]
        ws.append(headers)
        for h in history_data:
            ws.append([
                h.get("order_id", "-"), h.get("date", ""), 
                h.get("user_name", ""), h.get("phone", ""),
                h.get("item_name", ""), h.get("quantity", 1), 
                h.get("price", 0)
            ])
            
        if summary_data:
            ws_sum = wb.create_sheet(title="ملخص العملاء")
            ws_sum.append(["اسم العميل", "رقم الهاتف", "إجمالي المسحوبات"])
            for phone, data in summary_data.items():
                ws_sum.append([data["name"], phone, data["spent"]])

    elif report_type == "single":
        ws.title = "كشف حساب عميل"
        headers = ["التاريخ", "العملية", "البيان", "المبلغ"]
        ws.append(headers)
        total_in = 0
        total_out = 0
        for h in history_data:
            ws.append([h.get("date"), h.get("type"), h.get("item_name", "-"), h.get("price", h.get("amount", 0))])
            if h.get("type") == "شراء": total_out += h.get("price", 0)
            else: total_in += h.get("amount", 0)
        
        ws.append([])
        ws.append(["", "إجمالي الإيداعات:", "", total_in])
        ws.append(["", "إجمالي المشتريات:", "", total_out])

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = white_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

# =======================================================
# 4. رادار منع التكرار (The Duplicate Radar)
# =======================================================

def process_radar_logic(chat_id, raw_codes_list, product_info=None):
    """فحص الأكواد المكررة وتوليد تقارير الإكسيل الفورية للإدارة"""
    if not raw_codes_list:
        bot.send_message(chat_id, "❌ لم يتم العثور على أي بيانات لمعالجتها.")
        return
        
    bot.send_message(chat_id, "⏳ رادار الأمان يعمل الآن... يتم فحص التكرار في قاعدة البيانات.")
    
    # تجميع الأكواد المدخلة للبحث المجمع في الداتابيز
    incoming_codes = [str(item['code']).strip() for item in raw_codes_list if 'code' in item]
    
    # البحث عن الأكواد التي لها وجود مسبق
    existing_in_db = stock.find({"code": {"$in": incoming_codes}})
    db_set = set([str(doc['code']).strip() for doc in existing_in_db])
    
    accepted_docs = []
    rejected_docs = []
    seen_in_batch = set()
    
    for item in raw_codes_list:
        current_code = str(item.get('code', '')).strip()
        if not current_code: continue
        
        # إذا كان مكرراً في الداتابيز أو مكرراً داخل نفس الملف المرفوع
        if current_code in db_set or current_code in seen_in_batch:
            rejected_docs.append(item)
        else:
            seen_in_batch.add(current_code)
            # دمج معلومات المنتج مع الكود
            new_doc = item.copy()
            if product_info:
                new_doc.update(product_info)
            new_doc["sold"] = False
            new_doc["added_at"] = datetime.datetime.now()
            accepted_docs.append(new_doc)
            
    # تنفيذ الإضافة
    if accepted_docs:
        stock.insert_many(accepted_docs)
        
    # تقرير النتائج
    report_msg = (
        f"📊 **تقرير معالجة المخزون:**\n\n"
        f"✅ أكواد جديدة مقبولة: `{len(accepted_docs)}`\n"
        f"❌ أكواد مكررة مرفوضة: `{len(rejected_docs)}`"
    )
    bot.send_message(chat_id, report_msg, parse_mode="Markdown")
    
    # إرسال ملفات الإكسيل للفرز
    if accepted_docs:
        f_acc = generate_simple_excel(accepted_docs, "Accepted_New_Codes")
        bot.send_document(chat_id, f_acc, caption="📁 ملف الأكواد التي تم إضافتها بنجاح.")
        
    if rejected_docs:
        f_rej = generate_simple_excel(rejected_docs, "Rejected_Duplicates")
        bot.send_document(chat_id, f_rej, caption="⚠️ ملف الأكواد المكررة (التي تم استبعادها).")

def generate_simple_excel(data_list, title):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["القسم", "الفئة", "الاسم", "سعر 1", "سعر 2", "سعر 3", "كود الشحن", "التسلسلي", "PIN", "أوبريشن"])
    for d in data_list:
        ws.append([
            d.get('category',''), d.get('subcategory',''), d.get('name',''),
            d.get('price_1', 0), d.get('price_2', 0), d.get('price_3', 0),
            d.get('code',''), d.get('serial',''), d.get('pin',''), d.get('op_code','')
        ])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    stream.name = f"{title}.xlsx"
    return stream

# =======================================================
# 5. نظام التسجيل (Registration & Onboarding)
# =======================================================

@bot.message_handler(commands=['start'])
def handle_start(msg):
    uid = msg.chat.id
    u = users.find_one({"_id": uid})

    if not u:
        users.insert_one({
            "_id": uid, "name": None, "phone": None, "balance": 0.0, 
            "status": "frozen", "tier": 1, "failed_attempts": 0, 
            "join": datetime.datetime.now()
        })
        u = users.find_one({"_id": uid})

    if not u.get("name"):
        bot.send_message(uid, "👋 مرحباً بك في شركة الأهرام للإتصالات والتقنية.\n\nيرجى البدء بكتابة **اسمك بالكامل** (أو اسم متجرك):")
        bot.register_next_step_handler(msg, save_user_name)
    elif not u.get("phone"):
        bot.send_message(uid, f"أهلاً بك يا {safe_str(u.get('name'))}! يرجى تزويدنا برقم هاتفك لاستكمال تفعيل الحساب.", reply_markup=contact_menu())
    else:
        # فحص الحالة
        status = u.get("status")
        if status == "blocked":
            bot.send_message(uid, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        elif status == "frozen":
            bot.send_message(uid, "حسابك الآن (قيد المراجعة). سيتم إشعارك فور تفعيل الحساب من قبل الإدارة.")
        else:
            bot.send_message(uid, "أهلاً بك مجدداً في المتجر 🏪", reply_markup=menu())

def save_user_name(msg):
    if not msg.text or msg.text.startswith('/'):
        bot.send_message(msg.chat.id, "يرجى كتابة اسم صحيح:")
        bot.register_next_step_handler(msg, save_user_name)
        return
    
    name = msg.text.strip()
    users.update_one({"_id": msg.chat.id}, {"$set": {"name": name}})
    bot.send_message(msg.chat.id, f"تشرفنا بك يا {safe_str(name)}!\n\nالآن، يرجى مشاركة رقم هاتفك عبر الزر أدناه 📱", reply_markup=contact_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact_sharing(msg):
    uid = msg.chat.id
    if msg.contact.user_id != uid:
        bot.send_message(uid, "❌ يرجى مشاركة رقم هاتفك الخاص المرتبط بهذا الحساب.")
        return
    
    phone = msg.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    users.update_one({"_id": uid}, {"$set": {"phone": phone, "tier": 1}})
    u = users.find_one({"_id": uid})
    name = safe_str(u.get("name"))
    
    if u.get("status") == "frozen":
        bot.send_message(uid, "✅ تم استلام بياناتك بنجاح.\nحسابك الآن قيد المراجعة، يرجى الانتظار لحين التفعيل من قبل الإدارة.", reply_markup=types.ReplyKeyboardRemove())
        
        # إشعار الإدارة
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"),
               types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"block_{uid}"))
        
        for admin_id in get_all_admins():
            try:
                bot.send_message(admin_id, f"🆕 **طلب تسجيل جديد!**\n\n📛 الاسم: {name}\n🆔 ID: `{uid}`\n📱 الهاتف: `{phone}`", reply_markup=kb)
            except: pass
    else:
        bot.send_message(uid, "✅ حسابك نشط وجاهز.", reply_markup=menu())

# =======================================================
# 6. واجهة العميل (Customer Interface)
# =======================================================

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def show_account_info(msg):
    u = users.find_one({"_id": msg.chat.id})
    if not u or not u.get("name"):
        bot.send_message(msg.chat.id, "يرجى تسجيل بياناتك أولاً عبر إرسال /start")
        return
        
    if u.get("status") == "blocked":
        bot.send_message(msg.chat.id, "تم حظرك من قبل الادارة وللاستفسار تواصل معنا")
        return

    name = safe_str(u.get('name'))
    bal = u.get('balance', 0.0)
    phone = u.get('phone', 'غير متوفر')
    status = "نشط ✅" if u.get('status') == 'active' else "قيد المراجعة ❄️"
    
    text = (
        f"👤 **بيانات حسابك**\n\n"
        f"📛 الاسم: {name}\n"
        f"🆔 معرفك: `{msg.chat.id}`\n"
        f"📱 الهاتف: `{phone}`\n"
        f"💰 رصيدك الحالي: **{bal}**\n"
        f"حالة الحساب: {status}"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🛒 سجل المشتريات", callback_data="client_purchases"),
        types.InlineKeyboardButton("🧾 كشف حساب تفصيلي", callback_data="client_statement")
    )
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["client_purchases", "client_statement"])
def handle_client_reports(call):
    uid = call.message.chat.id
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active":
        bot.answer_callback_query(call.id, "عذراً، حسابك غير مفعل حالياً.", show_alert=True)
        return

    if call.data == "client_purchases":
        history = list(transactions.find({"uid": uid, "type": "شراء"}).sort("_id", -1).limit(10))
        if not history:
            bot.answer_callback_query(call.id, "لا توجد مشتريات مسجلة.", show_alert=True)
            return
        txt = "🛒 **آخر 10 مشتريات لك:**\n\n"
        for t in history:
            txt += f"▪️ {t['date']} | {t['item_name']} (x{t.get('quantity', 1)}) | {t['price']}\n"
            
    elif call.data == "client_statement":
        history = list(transactions.find({"uid": uid}).sort("_id", -1).limit(20))
        if not history:
            bot.answer_callback_query(call.id, "لا توجد حركات في حسابك.", show_alert=True)
            return
        txt = "🧾 **كشف حساب (آخر 20 حركة):**\n\n"
        for t in history:
            if t["type"] == "شراء": txt += f"🔴 خصم | {t['date']} | {t['item_name']} | {t['price']}\n"
            else: txt += f"🟢 إضافة | {t['date']} | {t['type']} | {t['amount']}\n"
                
    bot.send_message(uid, txt, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# =======================================================
# 7. نظام الشحن التلقائي (Auto Charging System)
# =======================================================

@bot.message_handler(func=lambda m: m.text == "💳 شحن")
def ask_for_card_code(msg):
    u = check_user_access(msg.chat.id)
    if not u: return
    bot.send_message(msg.chat.id, "يرجى إرسال كود شحن الرصيد:")
    bot.register_next_step_handler(msg, process_card_charging)

def process_card_charging(msg):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم إلغاء عملية الشحن.")
        return
        
    uid = msg.chat.id
    u = users.find_one({"_id": uid})
    
    if not u or u.get("status") != "active":
        bot.send_message(uid, "❌ حسابك غير مفعل.")
        return

    input_code = msg.text.strip()
    card = cards.find_one_and_update({"code": input_code, "used": False}, {"$set": {"used": True, "used_by": uid, "used_at": datetime.datetime.now()}})
    
    if not card:
        attempts = u.get("failed_attempts", 0) + 1
        if attempts >= 5:
            users.update_one({"_id": uid}, {"$set": {"status": "frozen", "failed_attempts": 0}})
            bot.send_message(uid, "🚫 تم إيقاف حسابك بسبب تكرار إدخال أكواد خاطئة. تواصل مع الإدارة.")
        else:
            users.update_one({"_id": uid}, {"$set": {"failed_attempts": attempts}})
            bot.send_message(uid, f"❌ الكود غير صحيح. متبقي لك {5 - attempts} محاولات.")
        return

    card_value = float(card["value"])
    new_balance = u.get("balance", 0.0) + card_value
    users.update_one({"_id": uid}, {"$set": {"balance": new_balance, "failed_attempts": 0}})
    
    # تسجيل العملية
    transactions.insert_one({
        "uid": uid, "user_name": u.get("name"), "type": "شحن كارت", 
        "amount": card_value, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    bot.send_message(uid, f"✅ تم شحن حسابك بمبلغ {card_value} بنجاح.\n💰 رصيدك الجديد: {new_balance}")
    
    # إشعار الإدارة
    for admin_id in get_all_admins():
        try:
            bot.send_message(admin_id, f"💳 **عملية شحن جديدة!**\n\n👤 العميل: {safe_str(u.get('name'))}\n📱 الهاتف: `{u.get('phone')}`\n💰 المبلغ: {card_value}")
        except: pass

# =======================================================
# 8. نظام الشراء (Shopping & Invoicing)
# =======================================================

@bot.message_handler(func=lambda m: m.text == "🛒 شراء")
def start_shopping_process(msg):
    u = check_user_access(msg.chat.id)
    if not u: return
    
    # جلب الأقسام المتوفرة
    cats = stock.distinct("category", {"sold": False})
    if not cats:
        bot.send_message(msg.chat.id, "❌ لا توجد منتجات متوفرة حالياً في المتجر.")
        return
        
    kb = types.InlineKeyboardMarkup()
    for c in cats:
        kb.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))
    bot.send_message(msg.chat.id, "يرجى اختيار القسم:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def handle_category_selection(call):
    cat_name = call.data.split("_", 1)[1]
    subs = stock.distinct("subcategory", {"category": cat_name, "sold": False})
    
    kb = types.InlineKeyboardMarkup()
    for s in subs:
        kb.add(types.InlineKeyboardButton(s, callback_data=f"sub_{cat_name}_{s}"))
    bot.edit_message_text(f"القسم: {cat_name}\nاختر الفئة:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def handle_subcategory_selection(call):
    uid = call.message.chat.id
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active": return
    
    tier = u.get("tier", 1)
    _, cat_name, sub_name = call.data.split("_", 2)
    
    # جلب الأكواد المتوفرة
    available_items = list(stock.find({"category": cat_name, "subcategory": sub_name, "sold": False}))
    total_count = len(available_items)
    
    if total_count < 10:
        bot.answer_callback_query(call.id, "⚠️ الكمية المتبقية أقل من الحد الأدنى للشراء (10 أكواد).", show_alert=True)
        return
        
    sample = available_items[0]
    
    # تحديد السعر بناء على المستوى بشكل صامت
    p1 = sample.get("price_1", sample.get("price", 0))
    p2 = sample.get("price_2", p1)
    p3 = sample.get("price_3", p1)
    
    final_price = p1 if tier == 1 else (p2 if tier == 2 else p3)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛒 تأكيد طلب شراء", callback_data=f"buy_{sample['_id']}"))
    
    info_text = (
        f"📦 المنتج: **{sample['name']}**\n"
        f"💰 السعر: **{final_price}**\n"
        f"📊 الكمية المتوفرة: {total_count}\n\n"
        f"⚠️ أقل كمية للطلب هي 10 ومضاعفاتها."
    )
    bot.send_message(uid, info_text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def ask_for_quantity(call):
    uid = call.message.chat.id
    pid = call.data.split("_")[1]
    
    u = users.find_one({"_id": uid})
    if not u or u.get("status") != "active": return
    
    item = stock.find_one({"_id": ObjectId(pid), "sold": False})
    if not item:
        bot.answer_callback_query(call.id, "❌ عذراً، المنتج لم يعد متوفراً.")
        return
    
    name = item['name']
    available = stock.count_documents({"name": name, "sold": False})
    
    msg = bot.send_message(uid, f"📦 المنتج: {name}\n📊 المتوفر حالياً: {available}\n\nيرجى إرسال الكمية المطلوبة (10، 20، 30...):")
    bot.register_next_step_handler(msg, finalize_purchase, u, item, available)

def finalize_purchase(msg, user_data, item_ref, available_qty):
    if msg.text in MENU_BUTTONS:
        bot.send_message(msg.chat.id, "تم إلغاء عملية الشراء.")
        return
        
    uid = msg.chat.id
    try:
        requested_qty = int(msg.text.strip())
        if requested_qty < 10 or requested_qty % 10 != 0:
            bot.send_message(uid, "❌ الكمية يجب أن تكون من مضاعفات الـ 10 (10، 20، 50...).")
            return
    except:
        bot.send_message(uid, "❌ يرجى إدخال رقم صحيح.")
        return
        
    if requested_qty > available_qty:
        bot.send_message(uid, f"❌ الكمية المطلوبة غير متوفرة. المتاح حالياً: {available_qty}")
        return

    # حساب السعر النهائي بناء على المستوى
    tier = user_data.get("tier", 1)
    p1 = item_ref.get("price_1", item_ref.get("price", 0))
    p2 = item_ref.get("price_2", p1)
    p3 = item_ref.get("price_3", p1)
    unit_price = p1 if tier == 1 else (p2 if tier == 2 else p3)
    
    total_cost = requested_qty * unit_price
    
    # فحص الرصيد
    if float(user_data.get("balance", 0.0)) < total_cost:
        bot.send_message(uid, f"❌ رصيدك غير كافي.\nالمطلوب: {total_cost}\nرصيدك: {user_data.get('balance')}")
        return

    # سحب الأكواد من المخزن وتأكيد البيع
    batch = list(stock.find({"name": item_ref['name'], "sold": False}).limit(requested_qty))
    if len(batch) < requested_qty:
        bot.send_message(uid, "❌ حدث خطأ في توافر الأكواد، حاول مجدداً.")
        return
        
    ids_to_sell = [doc['_id'] for doc in batch]
    update_res = stock.update_many({"_id": {"$in": ids_to_sell}, "sold": False}, {"$set": {"sold": True, "buyer_id": uid, "order_date": datetime.datetime.now()}})
    
    if update_res.modified_count != requested_qty:
        stock.update_many({"_id": {"$in": ids_to_sell}}, {"$set": {"sold": False}})
        bot.send_message(uid, "❌ حدث تضارب في عملية البيع، يرجى المحاولة مرة أخرى.")
        return

    # تحديث رصيد العميل
    users.update_one({"_id": uid}, {"$inc": {"balance": -total_cost}})
    
    # إنشاء الفاتورة
    order_id = get_next_order_id()
    dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    transactions.insert_one({
        "order_id": order_id, "uid": uid, "user_name": user_data.get("name"), 
        "phone": user_data.get("phone"), "type": "شراء", "item_name": item_ref['name'], 
        "quantity": requested_qty, "price": total_cost, "date": dt_str
    })
    
    bot.send_message(uid, f"✅ تم الشراء بنجاح!\n🧾 رقم الفاتورة: #{order_id}\n💰 القيمة المخصومة: {total_cost}\n\nجاري إعداد ملف الأكواد الخاص بك...")
    
    # توليد وإرسال ملف الإكسيل الديناميكي
    p_data = [
        {'code': d['code'], 'serial': d.get('serial', ''), 'pin': d.get('pin', ''), 'op_code': d.get('op_code', '')} 
        for d in batch
    ]
    file_stream = generate_customer_excel_file(p_data, order_id, dt_str, item_ref['name'])
    bot.send_document(uid, file_stream, caption=f"📁 فاتورة الأكواد | رقم #{order_id}")
    
    # إرسال نسخة للإدارة
    for admin_id in get_all_admins():
        try:
            file_stream.seek(0)
            bot.send_message(admin_id, f"🛒 **عملية شراء جديدة!**\n\n👤 العميل: {safe_str(user_data.get('name'))}\n📦 المنتج: {item_ref['name']}\n🔢 الكمية: {requested_qty}\n💰 المبلغ: {total_cost}")
            bot.send_document(admin_id, file_stream, caption=f"📁 نسخة فاتورة #{order_id}")
        except: pass

# =======================================================
# 9. لوحة تحكم الإدارة الشاملة (Super Admin Panel)
# =======================================================

@bot.message_handler(commands=['admin'])
def show_admin_dashboard(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "👑 مرحباً بك في لوحة تحكم الإدارة العليا.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🏪 العودة للمتجر")
def return_to_client_mode(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "🔄 تم تحويلك لوضع العميل.", reply_markup=menu())

# ----- ميزة المستخدمين -----
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def admin_users_list(msg):
    if not is_admin(msg.chat.id): return
    try:
        text = "👥 **قائمة آخر 30 مستخدم مسجل:**\n\n"
        for u in users.find().sort("join", -1).limit(30):
            stat = "✅" if u.get('status') == 'active' else ("🚫" if u.get('status') == 'blocked' else "❄️")
            text += f"📛 {safe_str(u.get('name'))} | 📱 `{u.get('phone')}` | 💰 {u.get('balance', 0)} | {stat}\n"
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطأ في عرض القائمة: {e}")

# ----- ميزة إدارة عميل (تفعيل، تجميد، حظر، تغيير مستوى) -----
@bot.message_handler(func=lambda m: m.text == "⚙️ إدارة عميل")
def admin_manage_customer(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "يرجى إرسال رقم هاتف العميل:")
    bot.register_next_step_handler(msg, admin_find_and_render_customer)

def admin_find_and_render_customer(msg):
    if msg.text in MENU_BUTTONS: return
    u = find_customer(msg.text)
    if not u:
        bot.send_message(msg.chat.id, "❌ العميل غير موجود.")
        return
    admin_render_customer_card(u["_id"], msg.chat.id)

def admin_render_customer_card(uid, chat_id, message_id=None):
    u = users.find_one({"_id": uid})
    if not u: return
    
    tier = u.get("tier", 1)
    tier_label = "مستوى 1 🥉" if tier == 1 else ("مستوى 2 🥈" if tier == 2 else "مستوى 3 🥇")
    stat = u.get("status")
    stat_label = "محظور 🚫" if stat == "blocked" else ("نشط ✅" if stat == "active" else "مجمد ❄️")
    
    info = (
        f"👤 **ملف بيانات العميل:**\n\n"
        f"📛 الاسم: {safe_str(u.get('name'))}\n"
        f"🆔 ID: `{uid}`\n"
        f"📱 الهاتف: `{u.get('phone')}`\n"
        f"💰 الرصيد: **{u.get('balance',0)}**\n"
        f"🎚️ المستوى الحالي: **{tier_label}**\n"
        f"حالة الحساب: **{stat_label}**"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    if stat == "active":
        kb.add(types.InlineKeyboardButton("❄️ تجميد", callback_data=f"adm_freeze_{uid}"), 
               types.InlineKeyboardButton("🚫 حظر", callback_data=f"adm_block_{uid}"))
    elif stat == "frozen":
        kb.add(types.InlineKeyboardButton("✅ تفعيل", callback_data=f"adm_activate_{uid}"), 
               types.InlineKeyboardButton("🚫 حظر", callback_data=f"adm_block_{uid}"))
    elif stat == "blocked":
        kb.add(types.InlineKeyboardButton("✅ فك الحظر", callback_data=f"adm_activate_{uid}"))
        
    kb.add(types.InlineKeyboardButton("🎚️ تغيير المستوى", callback_data=f"adm_chgtier_{uid}"), 
           types.InlineKeyboardButton("📊 تقرير العمليات", callback_data=f"adm_report_{uid}"))
    
    if message_id:
        try: bot.edit_message_text(info, chat_id, message_id, reply_markup=kb, parse_mode="Markdown")
        except: pass
    else:
        bot.send_message(chat_id, info, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def handle_admin_actions(call):
    parts = call.data.split("_")
    action = parts[1]
    uid = int(parts[2])
    
    if action == "report":
        h = list(transactions.find({"uid": uid}).sort("_id", -1).limit(15))
        if not h:
            bot.answer_callback_query(call.id, "لا توجد عمليات.")
            return
        txt = f"📊 **آخر عمليات العميل `{uid}`:**\n\n"
        for t in h: txt += f"▪️ {t['date']} | {t['type']} | {t.get('price', t.get('amount'))}\n"
        bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        return

    if action == "chgtier":
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("1 🥉", callback_data=f"set_tier_1_{uid}"),
               types.InlineKeyboardButton("2 🥈", callback_data=f"set_tier_2_{uid}"),
               types.InlineKeyboardButton("3 🥇", callback_data=f"set_tier_3_{uid}"))
        kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_back_{uid}"))
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if action == "freeze": users.update_one({"_id": uid}, {"$set": {"status": "frozen"}})
    elif action == "activate": users.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
    elif action == "block": users.update_one({"_id": uid}, {"$set": {"status": "blocked"}})
    elif action == "back": pass
    
    bot.answer_callback_query(call.id, "تم تحديث البيانات.")
    admin_render_customer_card(uid, call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_tier_"))
def handle_tier_setting(call):
    parts = call.data.split("_")
    level = int(parts[2])
    uid = int(parts[3])
    users.update_one({"_id": uid}, {"$set": {"tier": level}})
    bot.answer_callback_query(call.id, f"تم تغيير المستوى إلى {level}")
    admin_render_customer_card(uid, call.message.chat.id, call.message.message_id)

# ----- ميزة إضافة المنتجات (Manual & Radar Template) -----
@bot.message_handler(func=lambda m: m.text == "➕ منتج")
def admin_add_product(msg):
    if not is_admin(msg.chat.id): return
    txt = (
        "➕ **إضافة منتجات للمخزن:**\n\n"
        "📁 **الطريقة 1:** رفع ملف الإكسيل المرفق.\n"
        "✍️ **الطريقة 2:** الإضافة اليدوية بالتنسيق:\n"
        "`القسم:الفئة:الاسم:سعر1:سعر2:سعر3`"
    )
    temp = generate_products_template()
    bot.send_document(msg.chat.id, temp, caption=txt, parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_process_product_input)

def admin_process_product_input(msg):
    if msg.text in MENU_BUTTONS: return
    
    if msg.document:
        if not msg.document.file_name.endswith('.xlsx'):
            bot.send_message(msg.chat.id, "❌ يرجى رفع ملف إكسيل .xlsx")
            return
        try:
            file_info = bot.get_file(msg.document.file_id)
            down = bot.download_file(file_info.file_path)
            wb = openpyxl.load_workbook(io.BytesIO(down))
            ws = wb.active
            batch = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0 or not row[0]: continue
                try:
                    batch.append({
                        "category": str(row[0]), "subcategory": str(row[1]), "name": str(row[2]),
                        "price_1": float(row[3]), "price_2": float(row[4]) if row[4] else float(row[3]),
                        "price_3": float(row[5]) if row[5] else float(row[3]),
                        "code": str(row[6]), "serial": str(row[7]) if row[7] else "",
                        "pin": str(row[8]) if row[8] else "", "op_code": str(row[9]) if row[9] else ""
                    })
                except: pass
            process_radar_logic(msg.chat.id, batch)
        except Exception as e: bot.send_message(msg.chat.id, f"❌ خطأ: {e}")
        
    elif msg.text and ":" in msg.text:
        try:
            p = msg.text.split(":")
            info = {"cat": p[0], "sub": p[1], "name": p[2], "price_1": float(p[3]), 
                    "price_2": float(p[4]) if len(p)>4 else float(p[3]), 
                    "price_3": float(p[5]) if len(p)>5 else float(p[3])}
            temp_admin_data[msg.chat.id] = {"info": info}
            bot.send_message(msg.chat.id, "✅ بيانات المنتج محفوظة. أرسل الأكواد الآن (كود:تسلسلي:PIN:أوبريشن):")
            bot.register_next_step_handler(msg, admin_process_manual_codes)
        except: bot.send_message(msg.chat.id, "❌ تنسيق غير صحيح.")

def admin_process_manual_codes(msg):
    if msg.text in MENU_BUTTONS: return
    p_info = temp_admin_data.get(msg.chat.id, {}).get("info")
    if not p_info: return
    
    batch = []
    for line in msg.text.split("\n"):
        if not line.strip(): continue
        pts = line.split(":")
        batch.append({
            "code": pts[0].strip(), "serial": pts[1].strip() if len(pts)>1 else "",
            "pin": pts[2].strip() if len(pts)>2 else "", "op_code": pts[3].strip() if len(pts)>3 else ""
        })
    process_radar_logic(msg.chat.id, batch, p_info)

# ----- ميزة تحديث الأسعار المجمعة -----
@bot.message_handler(func=lambda m: m.text == "💵 أسعار المستويات")
def admin_bulk_price_edit(msg):
    if not is_admin(msg.chat.id): return
    prods = list(stock.aggregate([{"$match":{"sold":False}}, {"$group":{"_id":"$name", "cat":{"$first":"$category"}, "sub":{"$first":"$subcategory"}, "p1":{"$first":"$price_1"}, "p2":{"$first":"$price_2"}, "p3":{"$first":"$price_3"}}}]))
    if not prods:
        bot.send_message(msg.chat.id, "❌ لا توجد منتجات لتعديل أسعارها.")
        return
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["الاسم (لا تعدله)", "القسم", "الفئة", "سعر 1", "سعر 2", "سعر 3"])
    for p in prods: ws.append([p["_id"], p["cat"], p["sub"], p.get("p1",0), p.get("p2",0), p.get("p3",0)])
    stream = io.BytesIO(); wb.save(stream); stream.seek(0); stream.name = "Prices_Update.xlsx"
    m = bot.send_document(msg.chat.id, stream, caption="📁 أرسل الملف بعد تعديل الأسعار.")
    bot.register_next_step_handler(m, admin_finalize_price_update)

def admin_finalize_price_update(msg):
    if not msg.document: return
    try:
        f = bot.get_file(msg.document.file_id); d = bot.download_file(f.file_path); wb = openpyxl.load_workbook(io.BytesIO(d)); ws = wb.active
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 or not row[0]: continue
            stock.update_many({"name": str(row[0]), "sold": False}, {"$set": {"price_1": float(row[3]), "price_2": float(row[4]), "price_3": float(row[5])}})
        bot.send_message(msg.chat.id, "✅ تم تحديث الأسعار بنجاح.")
    except Exception as e: bot.send_message(msg.chat.id, f"❌ خطأ: {e}")

# ----- ميزة التقارير المحاسبية (تاريخ من وإلى) -----
@bot.message_handler(func=lambda m: m.text == "📊 تقارير إكسيل")
def admin_excel_reports(msg):
    if not is_admin(msg.chat.id): return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📄 تقرير شامل", callback_data="rep_all"),
           types.InlineKeyboardButton("👤 تقرير عميل", callback_data="rep_single"))
    bot.send_message(msg.chat.id, "اختر نوع التقرير:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rep_"))
def admin_report_dates(call):
    temp_admin_data[call.message.chat.id] = {"rep_type": call.data.split("_")[1]}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🕒 كل الوقت", callback_data="dt_all"),
           types.InlineKeyboardButton("📅 فترة محددة", callback_data="dt_custom"))
    bot.edit_message_text("تحديد الفترة الزمنية:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dt_"))
def admin_report_finalize(call):
    uid = call.message.chat.id
    mode = call.data.split("_")[1]
    rep_type = temp_admin_data.get(uid, {}).get("rep_type")
    
    if mode == "all":
        admin_execute_report(uid, rep_type, None, None)
    else:
        bot.send_message(uid, "أرسل التواريخ بالتنسيق `YYYY-MM-DD:YYYY-MM-DD`:")
        bot.register_next_step_handler(call.message, admin_process_date_input, rep_type)
    bot.answer_callback_query(call.id)

def admin_process_date_input(msg, rep_type):
    try:
        s, e = msg.text.split(":")
        admin_execute_report(msg.chat.id, rep_type, s.strip(), e.strip())
    except: bot.send_message(msg.chat.id, "❌ تنسيق تاريخ خاطئ.")

def admin_execute_report(uid, rep_type, start, end):
    filtr = {}
    if start and end: filtr = {"date": {"$gte": start, "$lte": end + " 23:59"}}
    
    if rep_type == "all":
        data = list(transactions.find(filtr).sort("_id", -1))
        summary = {}
        for t in data:
            p = t.get("phone", "بدون")
            if t.get("type") == "شراء":
                if p not in summary: summary[p] = {"name": t.get("user_name"), "spent": 0}
                summary[p]["spent"] += t.get("price", 0)
        f = generate_admin_report_excel("all", data, summary)
        bot.send_document(uid, f, caption="✅ التقرير الشامل.")
    else:
        bot.send_message(uid, "أرسل رقم الهاتف لاستخراج تقريره:")
        bot.register_next_step_handler_by_chat_id(uid, admin_execute_single_report, filtr)

def admin_execute_single_report(msg, filtr):
    u = find_customer(msg.text)
    if not u: return bot.send_message(msg.chat.id, "❌ غير موجود.")
    q = {"uid": u["_id"]}
    q.update(filtr)
    data = list(transactions.find(q).sort("_id", -1))
    f = generate_admin_report_excel("single", data)
    bot.send_document(msg.chat.id, f, caption=f"✅ تقرير العميل: {safe_str(u.get('name'))}")

# ----- الأوامر المخفية (FRP, ADD, Block) -----
@bot.message_handler(commands=['FRP', 'frp'])
def frp_reset_command(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, "⚠️ **فورمات المصنع** ⚠️\nأرسل `تأكيد الحذف النهائي` للمسح الشامل:")
    bot.register_next_step_handler(msg, frp_execute)

def frp_execute(msg):
    if msg.text == "تأكيد الحذف النهائي":
        users.delete_many({}); stock.delete_many({}); transactions.delete_many({}); admins_db.delete_many({}); counters.delete_many({}); cards.delete_many({})
        bot.send_message(msg.chat.id, "✅ تم تصفير النظام بالكامل.")

@bot.message_handler(commands=['ADD', 'add'])
def add_admin_command(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, "أرسل الـ ID لترقيته لأدمن:")
    bot.register_next_step_handler(msg, add_admin_execute)

def add_admin_execute(msg):
    try:
        new_id = int(msg.text.strip())
        admins_db.update_one({"_id": new_id}, {"$set": {"join_date": datetime.datetime.now()}}, upsert=True)
        bot.send_message(msg.chat.id, "✅ تمت إضافة الأدمن بنجاح.")
        bot.send_message(new_id, "🎉 تمت ترقيتك لمشرف. أرسل /admin.")
    except: pass

@bot.message_handler(commands=['Block', 'block'])
def block_user_command(msg):
    if not is_admin(msg.chat.id): return
    bot.send_message(msg.chat.id, "أرسل رقم الهاتف للحظر:")
    bot.register_next_step_handler(msg, block_execute)

def block_execute(msg):
    u = find_customer(msg.text)
    if u:
        users.update_one({"_id": u["_id"]}, {"$set": {"status": "blocked"}})
        bot.send_message(msg.chat.id, "✅ تم الحظر.")

# =======================================================
# 10. تشغيل السيرفر ومنع تعليق رندر (Server Core)
# =======================================================

app = Flask(__name__)

@app.route('/')
def health_check():
    return "<h1>شركة الأهرام للإتصالات - البوت يعمل بكامل طاقته</h1>"

def bot_worker():
    bot.remove_webhook()
    print("🚀 BOT POLLING STARTED...")
    bot.infinity_polling(timeout=30, long_polling_timeout=15)

if __name__ == "__main__":
    # تشغيل البوت في خيط منفصل لضمان استجابة Flask لـ Render
    worker = threading.Thread(target=bot_worker)
    worker.daemon = True
    worker.start()
    
    # تشغيل سيرفر الويب على المنفذ المطلوب
    port = int(os.environ.get("PORT", 8080))
    print(f"🌍 WEB SERVER RUNNING ON PORT {port}")
    app.run(host="0.0.0.0", port=port)
