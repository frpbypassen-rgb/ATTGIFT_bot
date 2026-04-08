import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
from flask import Flask
from threading import Thread
import certifi

# --- 1. إعداد سيرفر الوهمي (Render Keep-Alive) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online and Secure"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. البيانات الأساسية ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT&tlsAllowInvalidCertificates=true"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "218913731533"

bot = telebot.TeleBot(API_TOKEN)

# الاتصال بقاعدة البيانات مع معالجة أخطاء SSL
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['StoreDB_v2']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- 3. الدوال المساعدة ونظام الحماية ---
def is_frozen(uid):
    """التحقق من حالة الحساب (تجميد/تفعيل)"""
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'مخالفة سياسة الاستخدام')
        bot.send_message(uid, f"⚠️ عذراً، حسابك مجمد حالياً!\n\n📌 السبب: {reason}\n\n📞 للتفعيل، يرجى التواصل مع الدعم الفني.")
        return True
    return False

def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن كود", "🏦 شحن مباشر")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- 4. أوامر المستخدم ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    if is_frozen(uid): return
    
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 مشاركة جهة الاتصال للتفعيل", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات والتقنية\nيرجى تسجيل حسابك بالضغط على الزر أدناه:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {user['balance']} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact:
        user_data = {
            "_id": message.chat.id, 
            "phone": message.contact.phone_number, 
            "balance": 0, 
            "status": "active",
            "join_date": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        users_col.update_one({"_id": message.chat.id}, {"$set": user_data}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم تفعيل حسابك بنجاح في النظام السحابي!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    if is_frozen(message.chat.id): return
    user = users_col.find_one({"_id": message.chat.id})
    if user:
        text = (f"👤 **بيانات الحساب:**\n\n"
                f"📱 الرقم: `{user['phone']}`\n"
                f"💰 الرصيد: {user['balance']} د.ل\n"
                f"📅 تاريخ التسجيل: {user['join_date']}")
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 واتساب الدعم الفني", url=f"https://wa.me/{SUPPORT_NUMBER}"))
    bot.send_message(message.chat.id, "لأية استفسارات أو مشاكل تقنية، نحن هنا للمساعدة:", reply_markup=markup)

# --- 5. نظام الشحن المباشر للمحفظة ---
@bot.message_handler(func=lambda m: m.text == "🏦 شحن مباشر")
def direct_request(message):
    if is_frozen(message.chat.id): return
    msg = bot.send_message(message.chat.id, "يرجى إرسال البيانات كالتالي:\n(رقم حسابك : القيمة المراد شحنها)\n\nمثال: 55667 : 100")
    bot.register_next_step_handler(msg, forward_charge_to_admin)

def forward_charge_to_admin(message):
    try:
        acc, amt = [i.strip() for i in message.text.split(":")]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تأكيد وإضافة رصيد", callback_data=f"pay_{message.chat.id}_{amt}"))
        bot.send_message(ADMIN_ID, f"⚠️ **طلب شحن محفظة:**\n\n👤 العميل: {message.chat.id}\n🏦 رقم الحساب: {acc}\n💰 المبلغ: {amt} د.ل", reply_markup=markup)
        bot.send_message(message.chat.id, "✅ تم إرسال طلبك للإدارة. ستتلقى إشعاراً فور التأكيد.")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في التنسيق، حاول مجدداً.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def admin_confirm_pay(call):
    _, uid, amt = call.data.split("_")
    users_col.update_one({"_id": int(uid)}, {"$inc": {"balance": int(amt)}})
    logs_col.insert_one({"uid": int(uid), "action": "شحن مباشر", "amt": int(amt), "date": datetime.datetime.now()})
    bot.send_message(int(uid), f"✅ تم تأكيد عملية الشحن! تم إضافة {amt} د.ل لمحفظتك.")
    bot.edit_message_text(f"✅ تم تنفيذ الشحن للمستخدم بنجاح ({amt} د.ل)", ADMIN_ID, call.message.message_id)

# --- 6. نظام الإدارة (تجميد، إضافة بضاعة، كروت) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📦 إضافة بضاعة (متعددة)", callback_data="adm_stock"),
        types.InlineKeyboardButton("🎫 توليد كروت شحن", callback_data="adm_gen"),
        types.InlineKeyboardButton("👥 إدارة وتجميد المستخدمين", callback_data="adm_users")
    )
    bot.send_message(ADMIN_ID, "🛠 لوحة التحكم المركزية:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_users")
def list_users_for_admin(call):
    users = users_col.find().limit(20)
    markup = types.InlineKeyboardMarkup()
    for u in users:
        status = "✅" if u.get('status') == 'active' else "❄️"
        markup.add(types.InlineKeyboardButton(f"{status} {u['phone']} - {u['balance']}د.ل", callback_data=f"manage_{u['_id']}"))
    bot.send_message(ADMIN_ID, "اختر مستخدماً للإدارة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_"))
def manage_single_user(call):
    uid = int(call.data.split("_")[1])
    u = users_col.find_one({"_id": uid})
    markup = types.InlineKeyboardMarkup()
    if u.get('status') == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"freeze_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"))
    
    bot.send_message(ADMIN_ID, f"👤 المشترك: {u['phone']}\n💰 الرصيد: {u['balance']}\nالحالة: {u.get('status')}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freeze_"))
def freeze_input(call):
    uid = call.data.split("_")[1]
    msg = bot.send_message(ADMIN_ID, "ارسل سبب التجميد:")
    bot.register_next_step_handler(msg, lambda m: execute_freeze(m, uid))

def execute_freeze(message, uid):
    users_col.update_one({"_id": int(uid)}, {"$set": {"status": "frozen", "freeze_reason": message.text}})
    bot.send_message(ADMIN_ID, "✅ تم التجميد.")
    bot.send_message(int(uid), f"⚠️ تم تجميد حسابك.\nالسبب: {message.text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("activate_"))
def execute_activate(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active", "freeze_reason": ""}})
    bot.send_message(ADMIN_ID, "✅ تم تفعيل الحساب.")
    bot.send_message(uid, "✅ تم إعادة تفعيل حسابك، يمكنك استخدامه الآن.")

# --- 7. توليد الكروت والشراء ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_gen")
def prompt_gen(call):
    msg = bot.send_message(ADMIN_ID, "أرسل (الفئة : العدد)\nمثال: 50 : 10")
    bot.register_next_step_handler(msg, finalize_gen)

def finalize_gen(message):
    try:
        val, count = [int(i.strip()) for i in message.text.split(":")]
        cards = []
        for _ in range(count):
            code = "AHRAM-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            cards_col.insert_one({"code": code, "value": val, "used": False})
            cards.append(f"`{code}`")
        bot.send_message(ADMIN_ID, f"✅ تم توليد {count} كرت فئة {val}د.ل:\n\n" + "\n".join(cards), parse_mode="Markdown")
    except: bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

@bot.message_handler(func=lambda m: m.text == "💳 شحن كود")
def redeem_input(message):
    if is_frozen(message.chat.id): return
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن:")
    bot.register_next_step_handler(msg, do_redeem)

def do_redeem(message):
    card = cards_col.find_one_and_delete({"code": message.text.strip(), "used": False})
    if card:
        users_col.update_one({"_id": message.chat.id}, {"$inc": {"balance": card['value']}})
        bot.send_message(message.chat.id, f"✅ تم شحن {card['value']} د.ل بنجاح!")
    else: bot.send_message(message.chat.id, "❌ كود خاطئ أو مستخدم.")

@bot.callback_query_handler(func=lambda call: call.data == "adm_stock")
def prompt_stock(call):
    msg = bot.send_message(ADMIN_ID, "أرسل البضاعة هكذا:\n(الاسم : السعر : كود1, كود2, كود3)")
    bot.register_next_step_handler(msg, finalize_stock)

def finalize_stock(message):
    try:
        name, price, codes = message.text.split(":")
        price = int(price.strip())
        code_list = [c.strip() for c in codes.replace("\n", ",").split(",")]
        for c in code_list:
            if c: stock_col.insert_one({"name": name.strip(), "price": price, "secret": c})
        bot.send_message(ADMIN_ID, f"✅ تم إضافة {len(code_list)} كود لمنتج {name}")
    except: bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def show_shop(message):
    if is_frozen(message.chat.id): return
    prods = stock_col.distinct("name")
    if not prods: return bot.send_message(message.chat.id, "المخزن فارغ حالياً.")
    markup = types.InlineKeyboardMarkup()
    for p in prods:
        item = stock_col.find_one({"name": p})
        markup.add(types.InlineKeyboardButton(f"{p} - {item['price']} د.ل", callback_data=f"buy_{p}"))
    bot.send_message(message.chat.id, "اختر المنتج المراد شراؤه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def finish_buy(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    if is_frozen(uid): return
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name})
    if item and user['balance'] >= item['price']:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        bot.send_message(uid, f"✅ تم الشراء بنجاح!\nمنتجك: {p_name}\nالكود: `{item['secret']}`", parse_mode="Markdown")
    else: bot.answer_callback_query(call.id, "❌ رصيد غير كافٍ", show_alert=True)

# --- 8. تشغيل السيرفر والبوت ---
if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("--- Al-Ahram Bot is Secure and Running ---")
    bot.infinity_polling()
