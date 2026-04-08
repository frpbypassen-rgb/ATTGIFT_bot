import telebot
from telebot import types
from pymongo import MongoClient
import datetime
import os
import certifi
import random
import string
from flask import Flask
from threading import Thread
import logging
import time

# --- 1. إعداد سيرفر Flask لتجاوز إغلاق منصة Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>Al-Ahram System is Fully Operational</h1>"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)

# --- 2. الإعدادات والربط بقاعدة البيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "+218 91-3731533"

bot = telebot.TeleBot(API_TOKEN)

try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['AlAhram_DB']
    users_col = db['users']
    cards_col = db['topup_cards']
    stock_col = db['stock']
    logs_col = db['logs']
except Exception as e:
    print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# --- 3. الوظائف الأمنية والقوائم ---
def is_account_active(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'تم تجميد حسابك بموجب سياسة النظام')
        bot.send_message(uid, f"⚠️ **{reason}**\n📞 للدعم الفني: {SUPPORT_NUMBER}", parse_mode="Markdown")
        return False
    return True

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

def format_price(price):
    return int(price) if float(price).is_integer() else price

# --- 4. معالجة أوامر المستخدمين ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات والتقنية\nيرجى مشاركة جهة الاتصال لتسجيل حسابك:", reply_markup=markup)
    else:
        if is_account_active(uid):
            bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {format_price(user.get('balance', 0))} د.ل", reply_markup=get_main_menu())

@bot.message_handler(content_types=['contact'])
def handle_registration(message):
    if message.contact:
        uid = message.chat.id
        if not users_col.find_one({"_id": uid}):
            new_user = {
                "_id": uid,
                "phone": message.contact.phone_number,
                "balance": 0,
                "status": "active",
                "failed_attempts": 0,
                "join_date": datetime.datetime.now()
            }
            users_col.insert_one(new_user)
            bot.send_message(uid, "✅ تم تسجيلك وتفعيل حسابك بنجاح!", reply_markup=get_main_menu())
        else:
            bot.send_message(uid, "حسابك مسجل بالفعل.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support_section(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💬 تواصل عبر واتساب", url=f"https://wa.me/{SUPPORT_NUMBER.replace('+', '').replace(' ', '').replace('-', '')}"),
        types.InlineKeyboardButton("✈️ تواصل عبر تيليجرام", url="https://t.me/AlAhram_Support")
    )
    text = (f"📞 **خدمة العملاء المباشرة:**\n\n"
            f"نحن هنا لخدمتكم طوال اليوم.\n"
            f"الرقم المباشر: `{SUPPORT_NUMBER}`\n\n"
            f"اختر وسيلة التواصل المناسبة لك بالأسفل:")
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    uid = message.chat.id
    if not is_account_active(uid): return
    u = users_col.find_one({"_id": uid})
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    purchases = list(logs_col.find({"uid": u['_id'], "type": "buy"}))
    spent_today = sum(p.get('price', 0) for p in purchases if p['date'] >= today_start)
    spent_month = sum(p.get('price', 0) for p in purchases if p['date'] >= month_start)

    text = (f"👤 **تفاصيل الحساب:**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📱 هاتف: `{u['phone']}`\n"
            f"💰 الرصيد: {format_price(u.get('balance', 0))} د.ل\n\n"
            f"📊 **تقارير الإنفاق:**\n"
            f"▫️ إنفاق اليوم: {format_price(spent_today)} د.ل\n"
            f"▫️ إنفاق الشهر: {format_price(spent_month)} د.ل")
    bot.send_message(uid, text, parse_mode="Markdown")

# --- 5. نظام الشحن والحماية ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def start_charge(message):
    uid = message.chat.id
    if not is_account_active(uid): return
    msg = bot.send_message(uid, "🔢 يرجى إرسال كود الكرت المكون من 12 رمزاً:")
    bot.register_next_step_handler(msg, process_card_check)

def process_card_check(message):
    uid = message.chat.id
    if message.text in ["🛒 شراء كود", "💳 شحن رصيد", "👤 حسابي", "📢 الدعم الفني"]:
        bot.send_message(uid, "تم إلغاء عملية الشحن.")
        return

    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}, "$set": {"failed_attempts": 0}})
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "by": uid, "at": datetime.datetime.now()}})
        bot.send_message(uid, f"✅ تم شحن {format_price(card['val'])} د.ل بنجاح لرصيدك!")
    else:
        fails = user.get('failed_attempts', 0) + 1
        if fails >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك لتجاوز محاولات الشحن الخاطئة.", "failed_attempts": fails}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب إدخال كود خاطئ 3 مرات متتالية.")
        else:
            users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": fails}})
            bot.send_message(uid, f"❌ كود خاطئ أو مستخدم مسبقاً! لديك {3 - fails} محاولات متبقية قبل تجميد الحساب.")

# --- 6. نظام الأقسام وشراء الأكواد ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop_categories(message):
    uid = message.chat.id
    if not is_account_active(uid): return
    items = list(stock_col.find({"sold": False}))
    if not items:
        return bot.send_message(uid, "⚠️ لا توجد منتجات متوفرة حالياً في المخزن.")
    
    categories = set(item.get('category', 'عام') for item in items)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        markup.add(types.InlineKeyboardButton(f"📁 {cat}", callback_data=f"showcat_{cat}"))
        
    bot.send_message(uid, "🛒 **أقسام المتجر:**\nاختر القسم الذي تريده من الأسفل:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("showcat_"))
def show_category_items(call):
    cat_name = call.data.split("_")[1]
    uid = call.message.chat.id
    
    if cat_name == 'عام':
        items = list(stock_col.find({"sold": False, "$or": [{"category": cat_name}, {"category": {"$exists": False}}]}))
    else:
        items = list(stock_col.find({"sold": False, "category": cat_name}))

    if not items:
        return bot.answer_callback_query(call.id, "⚠️ لا توجد منتجات متاحة في هذا القسم حالياً.", show_alert=True)
    
    bot.delete_message(uid, call.message.message_id)
    bot.send_message(uid, f"📦 **قسم:** {cat_name}\nجاري تحميل المنتجات...", parse_mode="Markdown")
    
    unique_products = {}
    for item in items:
        name = item['name']
        if name not in unique_products:
            unique_products[name] = {
                'price': item['price'],
                'image_url': item.get('image_url', ''),
                'count': 1
            }
        else:
            unique_products[name]['count'] += 1

    for name, data in unique_products.items():
        markup = types.InlineKeyboardMarkup()
        p_price = format_price(data['price'])
        markup.add(types.InlineKeyboardButton(f"🛒 شراء ({p_price} د.ل)", callback_data=f"buy_{name}"))
        
        caption = (f"📦 **المنتج:** {name}\n"
                   f"💰 **السعر:** {p_price} د.ل\n"
                   f"📊 **المتوفر:** {data['count']} كود")
        
        if data['image_url'] and data['image_url'].startswith("http"):
            try:
                bot.send_photo(uid, data['image_url'], caption=caption, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.send_message(uid, caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(uid, caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def finalize_purchase(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name, "sold": False})

    if not item:
        return bot.answer_callback_query(call.id, "❌ نفدت الكمية من هذا المنتج!", show_alert=True)

    if user['balance'] < item['price']:
        bot.answer_callback_query(call.id, "❌ رصيدك الحالي غير كافٍ لإتمام العملية!", show_alert=True)
    else:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": True, "buyer": uid, "date": datetime.datetime.now()}})
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        
        # حفظ بيانات الشراء والربح في التقارير
        logs_col.insert_one({
            "uid": uid, 
            "type": "buy", 
            "price": item['price'], 
            "cost_price": item.get('cost_price', 0), 
            "date": datetime.datetime.now(), 
            "item": p_name
        })
        
        bot.send_message(uid, f"✅ تم شراء **{p_name}** بنجاح!\n🎫 كود المنتج: `{item['code']}`", parse_mode="Markdown")
        bot.answer_callback_query(call.id, "تم الشراء بنجاح!")
        bot.delete_message(uid, call.message.message_id)

# --- 7. لوحة التحكم (الأدمن) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👥 إدارة المشتركين", callback_data="adm_users"),
        types.InlineKeyboardButton("🔍 بحث برقم الهاتف", callback_data="adm_search_user")
    )
    markup.add(
        types.InlineKeyboardButton("💰 شحن مباشر", callback_data="adm_direct"),
        types.InlineKeyboardButton("📊 تقارير النظام", callback_data="adm_reports")
    )
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen"),
        types.InlineKeyboardButton("➕ إضافة بضاعة متقدمة", callback_data="adm_stock_bulk")
    )
    bot.send_message(ADMIN_ID, "🛠 **لوحة تحكم الإدارة:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.message.chat.id != ADMIN_ID: return

    if call.data == "adm_direct":
        msg = bot.send_message(ADMIN_ID, "📝 أرسل الرقم والقيمة هكذا (الرقم:القيمة)\nمثال: `0913731533:50`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_direct_recharge)
    
    elif call.data == "adm_users":
        all_u = list(users_col.find().sort("join_date", -1).limit(30))
        text = "👥 **قائمة المشتركين (آخر 30):**\n\n"
        markup = types.InlineKeyboardMarkup()
        for u in all_u:
            status = "✅" if u.get('status') == 'active' else "❄️"
            text += f"{status} `{u['phone']}` | {format_price(u.get('balance',0))} د.ل\n"
            markup.add(types.InlineKeyboardButton(f"⚙️ إدارة: {u['phone']}", callback_data=f"opt_{u['_id']}"))
        bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "adm_search_user":
        msg = bot.send_message(ADMIN_ID, "🔍 أرسل رقم هاتف المشترك للبحث عنه:")
        bot.register_next_step_handler(msg, admin_search_user_exec)

    elif call.data == "adm_reports":
        total_users = users_col.count_documents({})
        active_users = users_col.count_documents({"status": "active"})
        frozen_users = users_col.count_documents({"status": "frozen"})
        total_balance = sum(u.get('balance', 0) for u in users_col.find())
        
        # حساب المبيعات والتكاليف والأرباح
        buy_logs = list(logs_col.find({"type": "buy"}))
        total_sales = sum(log.get('price', 0) for log in buy_logs)
        total_costs = sum(log.get('cost_price', 0) for log in buy_logs)
        total_profit = total_sales - total_costs
        
        text = (f"📊 **تقارير وإحصائيات النظام:**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 إجمالي المشتركين: **{total_users}**\n"
                f"✅ الحسابات النشطة: **{active_users}**\n"
                f"❄️ الحسابات المجمدة: **{frozen_users}**\n\n"
                f"💳 إجمالي أرصدة المستخدمين: **{format_price(total_balance)} د.ل**\n\n"
                f"🛒 **التقارير المالية (المبيعات):**\n"
                f"📈 إجمالي المبيعات: **{format_price(total_sales)} د.ل**\n"
                f"📉 إجمالي التكلفة: **{format_price(total_costs)} د.ل**\n"
                f"💵 **صافي الأرباح:** **{format_price(total_profit)} د.ل**")
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown")

    elif call.data == "adm_gen":
        msg = bot.send_message(ADMIN_ID, "🎫 أرسل (عدد الكروت:قيمة الكرت الواحد)\nمثال لتوليد 10 كروت بقيمة 5 دينار: `10:5`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_generate_cards)

    elif call.data == "adm_stock_bulk":
        msg_text = ("➕ **إضافة منتجات (أكواد متعددة) مع حساب الأرباح:**\n\n"
                    "أرسل البيانات بالصيغة التالية بالضبط (في رسالة واحدة):\n\n"
                    "**القسم:الاسم:سعر التكلفة:سعر البيع:رابط الصورة**\n"
                    "كود1\n"
                    "كود2\n\n"
                    "*(ملاحظة: إذا لم توجد صورة اكتب 'لا' مكان الرابط)*\n\n"
                    "**مثال عملي لرسالة صحيحة:**\n"
                    "ألعاب:ببجي 60 شدة:4:5:https://example.com/pubg.jpg\n"
                    "PUBG-1234\n"
                    "PUBG-5678")
        msg = bot.send_message(ADMIN_ID, msg_text, parse_mode="Markdown", disable_web_page_preview=True)
        bot.register_next_step_handler(msg, admin_add_stock_bulk)

def show_user_panel(uid):
    user = users_col.find_one({"_id": uid})
    if not user: return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    if user.get('status') == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"action_freeze_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل الحساب (فك التجميد)", callback_data=f"action_unfreeze_{uid}"))
        
    bot.send_message(ADMIN_ID, f"👤 **معلومات وإدارة المشترك:**\n\n📱 الهاتف: `{user['phone']}`\n💰 الرصيد الحالي: {format_price(user.get('balance', 0))} د.ل\n📅 تاريخ التسجيل: {user['join_date'].strftime('%Y-%m-%d')}", reply_markup=markup, parse_mode="Markdown")

def admin_search_user_exec(message):
    phone = message.text.strip()
    user = users_col.find_one({"phone": phone})
    if user:
        show_user_panel(user['_id'])
    else:
        bot.send_message(ADMIN_ID, "❌ لم يتم العثور على أي مشترك بهذا الرقم.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("opt_") or call.data.startswith("action_"))
def admin_user_management(call):
    if call.message.chat.id != ADMIN_ID: return

    data_parts = call.data.split("_")
    
    if call.data.startswith("opt_"):
        uid = int(data_parts[1])
        show_user_panel(uid)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("action_"):
        action = data_parts[1]
        uid = int(data_parts[2])
        if action == "freeze":
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك من قبل الإدارة."}})
            bot.answer_callback_query(call.id, "تم تجميد الحساب بنجاح.", show_alert=True)
            bot.send_message(uid, "⚠️ تم تجميد حسابك من قبل الإدارة.")
        elif action == "unfreeze":
            users_col.update_one({"_id": uid}, {"$set": {"status": "active", "failed_attempts": 0}})
            bot.answer_callback_query(call.id, "تم فك التجميد بنجاح.", show_alert=True)
            bot.send_message(uid, "✅ تم تفعيل حسابك مجدداً من قبل الإدارة.")
        bot.delete_message(ADMIN_ID, call.message.message_id)

def admin_direct_recharge(message):
    try:
        phone, amount = message.text.split(":")
        amount = int(amount.strip())
        phone = phone.strip()
        target = users_col.find_one({"phone": phone})
        if target:
            users_col.update_one({"_id": target['_id']}, {"$inc": {"balance": amount}})
            bot.send_message(ADMIN_ID, f"✅ تم شحن {amount} د.ل للرقم {phone} بنجاح.")
            bot.send_message(target['_id'], f"💰 **تم إضافة {amount} د.ل لرصيدك من قبل الإدارة.**", parse_mode="Markdown")
        else:
            bot.send_message(ADMIN_ID, "❌ لم يتم العثور على هذا الرقم في قاعدة البيانات.")
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ خطأ في الإدخال! يرجى التأكد من الصيغة (الرقم:القيمة).")

def admin_generate_cards(message):
    try:
        count, value = map(int, message.text.split(":"))
        if count > 50:
            bot.send_message(ADMIN_ID, "❌ لتجنب الضغط، أقصى عدد لتوليد الكروت في المرة الواحدة هو 50.")
            return

        cards = []
        msg_text = f"✅ **تم توليد {count} كرت بقيمة {value} د.ل:**\n\n"
        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            cards.append({"code": code, "val": value, "used": False, "generated_at": datetime.datetime.now()})
            msg_text += f"`{code}`\n"
        
        cards_col.insert_many(cards)
        bot.send_message(ADMIN_ID, msg_text, parse_mode="Markdown")
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ خطأ في الإدخال! يرجى التأكد من إدخال أرقام صحيحة بالصيغة (العدد:القيمة).")

def admin_add_stock_bulk(message):
    lines = message.text.strip().split('\n')
    if len(lines) < 2:
        bot.send_message(ADMIN_ID, "❌ إدخال خاطئ! يجب كتابة تفاصيل المنتج في السطر الأول، والأكواد في الأسطر التالية.")
        return
    try:
        # استخدام split("", 4) يضمن عدم تقسيم الروابط التي تحتوي على : مثل https://
        parts = lines[0].split(":", 4)
        
        if len(parts) < 5:
            bot.send_message(ADMIN_ID, "❌ إدخال ناقص! تأكد من وجود 5 عناصر في السطر الأول مفصولة بـ (:)\nمثال: القسم:الاسم:سعرالتكلفة:سعرالبيع:رابط_الصورة")
            return
            
        category = parts[0].strip()
        name = parts[1].strip()
        cost_price = float(parts[2].strip())
        price = float(parts[3].strip())
        image_url = parts[4].strip()
        
        if image_url.lower() in ["لا", "بدون", "none", "no", ""]:
            image_url = ""
        
        codes = [line.strip() for line in lines[1:] if line.strip()]
        
        if not codes:
             bot.send_message(ADMIN_ID, "❌ لم يتم العثور على أكواد في الرسالة.")
             return

        docs = [{
            "category": category, 
            "name": name, 
            "cost_price": cost_price, 
            "price": price, 
            "image_url": image_url, 
            "code": c, 
            "sold": False, 
            "added_at": datetime.datetime.now()
        } for c in codes]
        
        stock_col.insert_many(docs)
        
        bot.send_message(ADMIN_ID, f"✅ تم إضافة **{len(codes)}** أكواد بنجاح.\n\n📁 **القسم:** {category}\n📦 **المنتج:** {name}\n📉 **سعر التكلفة:** {format_price(cost_price)} د.ل\n💰 **سعر البيع:** {format_price(price)} د.ل\n💵 **الربح للكود الواحد:** {format_price(price - cost_price)} د.ل\n🖼️ **الصورة:** {'مرفقة' if image_url else 'لا توجد'}", parse_mode="Markdown")
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ خطأ في السعر! تأكد من كتابة سعر التكلفة وسعر البيع كأرقام فقط.")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ حدث خطأ غير متوقع: {e}")

# --- 8. تشغيل البوت و Flask ---
def run_bot():
    while True:
        try:
            bot.remove_webhook()
            print("⏳ Waiting 5 seconds to clear old instances...")
            time.sleep(5) 
            print("🚀 Al-Ahram Bot is Running Successfully with Profit Reports & Multi-codes...")
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ توقف البوت فجأة، سيتم إعادة التشغيل بعد 10 ثوانٍ. السبب: {e}")
            time.sleep(10)

if __name__ == "__main__":
    Thread(target=run_bot).start()
    run_flask()
