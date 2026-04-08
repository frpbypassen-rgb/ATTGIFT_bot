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

# --- 1. إعداد سيرفر Flask لتجاوز إغلاق منصة Render ---
app = Flask('')

@app.route('/')
def home():
    return "<h1>Al-Ahram System is Fully Operational</h1>"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. الإعدادات والربط بقاعدة البيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "+218 91-3731533"

bot = telebot.TeleBot(API_TOKEN)

# الاتصال بـ MongoDB مع شهادة certifi لضمان الأمان والعمل في ليبيا
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- 3. الوظائف الأمنية والقوائم ---
def is_account_active(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'تم تجميد حسابك بموجب سياسة النظام')
        bot.send_message(uid, f"⚠️ **{reason}**\n📞 للدعم الفني: {SUPPORT_NUMBER}")
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
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات والتقنية\nيرجى تسجيل حسابك للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {user.get('balance', 0)} د.ل", reply_markup=get_main_menu())

@bot.message_handler(content_types=['contact'])
def handle_registration(message):
    if message.contact:
        uid = message.chat.id
        new_user = {
            "_id": uid,
            "phone": message.contact.phone_number,
            "balance": 0,
            "status": "active",
            "failed_attempts": 0,
            "join_date": datetime.datetime.now()
        }
        users_col.update_one({"_id": uid}, {"$set": new_user}, upsert=True)
        bot.send_message(uid, "✅ تم تسجيلك وتفعيل حسابك بنجاح!", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support_section(message):
    text = (f"📞 **خدمة العملاء المباشرة:**\n\n"
            f"📱 واتساب/اتصال: `{SUPPORT_NUMBER}`\n"
            f"💬 تلغرام المباشر: @AlAhram_Support\n\n"
            f"نحن هنا لخدمتكم طوال اليوم.")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    if not is_account_active(message.chat.id): return
    u = users_col.find_one({"_id": message.chat.id})
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    
    # جلب تقارير المشتريات
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
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 5. نظام الشحن والحماية (3 محاولات) ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def start_charge(message):
    if not is_account_active(message.chat.id): return
    msg = bot.send_message(message.chat.id, "🔢 يرجى إرسال كود الكرت المكون من 12 رمزاً:")
    bot.register_next_step_handler(msg, process_card_check)

def process_card_check(message):
    uid = message.chat.id
    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        # نجاح الشحن
        users_col.update_one({"_id": uid}, {"$inc": {"balance": card['val']}, "$set": {"failed_attempts": 0}})
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "by": uid, "at": datetime.datetime.now()}})
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل بنجاح لرصيدك!")
    else:
        # فشل الشحن: نظام الحماية
        fails = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": fails}})
        if fails >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك بسبب المحاولة في تخريب النظام"}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب المحاولة في تخريب النظام.")
        else:
            bot.send_message(uid, f"❌ كود خاطئ! لديك {3 - fails} محاولات متبقية قبل تجميد الحساب.")

# --- 6. نظام شراء الأكواد ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop_menu(message):
    if not is_account_active(message.chat.id): return
    items = list(stock_col.find({"sold": False}))
    if not items:
        return bot.send_message(message.chat.id, "⚠️ لا توجد منتجات متوفرة حالياً.")
    
    markup = types.InlineKeyboardMarkup()
    displayed = set()
    for item in items:
        if item['name'] not in displayed:
            markup.add(types.InlineKeyboardButton(f"{item['name']} - {item['price']} د.ل", callback_data=f"buy_{item['name']}"))
            displayed.add(item['name'])
    bot.send_message(message.chat.id, "اختر المنتج الذي ترغب في شرائه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def finalize_purchase(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name, "sold": False})

    if user['balance'] < item['price']:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ!", show_alert=True)
    else:
        stock_col.update_one({"_id": item['_id']}, {"$set": {"sold": True, "buyer": uid, "date": datetime.datetime.now()}})
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        logs_col.insert_one({"uid": uid, "type": "buy", "price": item['price'], "date": datetime.datetime.now()})
        bot.send_message(uid, f"✅ تم شراء {p_name} بنجاح!\nكود المنتج: `{item['code']}`", parse_mode="Markdown")
        bot.answer_callback_query(call.id)

# --- 7. لوحة التحكم (الأدمن) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👥 إدارة المشتركين", callback_data="adm_users"),
        types.InlineKeyboardButton("💰 شحن مباشر برقم الهاتف", callback_data="adm_direct"),
        types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen"),
        types.InlineKeyboardButton("➕ إضافة بضاعة جديدة", callback_data="adm_stock")
    )
    bot.send_message(ADMIN_ID, "🛠 **لوحة إدارة شركة الأهرام:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callback_handler(call):
    if call.data == "adm_direct":
        msg = bot.send_message(ADMIN_ID, "أرسل الرقم والقيمة هكذا (الرقم:القيمة)\nمثال: `0913731533:50`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, direct_recharge_exec)
    
    elif call.data == "adm_users":
        all_u = list(users_col.find())
        text = "👥 **قائمة المشتركين:**\n\n"
        markup = types.InlineKeyboardMarkup()
        for u in all_u:
            status = "✅" if u.get('status') == 'active' else "❄️"
            text += f"{status} `{u['phone']}` | {u.get('balance',0)} د.ل\n"
            markup.add(types.InlineKeyboardButton(f"التحكم: {u['phone']}", callback_data=f"opt_{u['_id']}"))
        bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode="Markdown")

def direct_recharge_exec(message):
    try:
        phone, amount = message.text.split(":")
        target = users_col.find_one({"phone": phone.strip()})
        if target:
            users_col.update_one({"_id": target['_id']}, {"$inc": {"balance": int(amount)}})
            bot.send_message(ADMIN_ID, f"✅ تم شحن {amount} د.ل للرقم {phone}")
            bot.send_message(target['_id'], f"✅ تم إضافة {amount} د.ل لرصيدك من قبل الإدارة.")
        else:
            bot.send_message(ADMIN_ID, "❌ الرقم غير مسجل في البوت.")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق. يرجى المحاولة مرة أخرى.")

# --- 8. تشغيل البوت النهائي ---
if __name__ == "__main__":
    # تشغيل خيط Flask لضمان بقاء البوت حياً
    Thread(target=run_flask).start()
    
    # تنظيف أي Webhook قديم لتجنب خطأ 409
    bot.remove_webhook()
    print("🚀 Al-Ahram Bot is Running Successfully...")
    
    # تشغيل البوت في وضع الاستمرارية
    bot.infinity_polling(skip_pending=True)
