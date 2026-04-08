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
    # 🌟 المنفذ 10000 متوافق مع منصة Render كما طلبت
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
            bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {user.get('balance', 0)} د.ل", reply_markup=get_main_menu())

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
    spent_today = sum(p['price'] for p in purchases if p['date'] >= today_start)
    spent_month = sum(p['price'] for p in purchases if p['date'] >= month_start)

    text = (f"👤 **تفاصيل الحساب:**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📱 هاتف: `{u['phone']}`\n"
            f"💰 الرصيد: {u.get('balance', 0)} د.ل\n\n"
            f"📊 **تقارير الإنفاق:**\n"
            f"▫️ إنفاق اليوم: {spent_today} د.ل\n"
            f"▫️ إنفاق الشهر: {spent_month} د.ل")
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
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل بنجاح لرصيدك!")
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
        markup.add(types.InlineKeyboardButton(f"🛒 شراء ({data['price']} د.ل)", callback_data=f"buy_{name}"))
        
        caption = (f"📦 **المنتج:** {name}\n"
                   f"💰 **السعر:** {data['price']} د.ل\n"
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
        logs_col.insert_one({"uid": uid, "type": "buy", "price": item['price'], "date": datetime.datetime.now(), "item": p_name})
        
        bot
