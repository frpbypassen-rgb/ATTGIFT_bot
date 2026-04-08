import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime
import os
from flask import Flask
from threading import Thread

# --- سيرفر الاستقرار على Render ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- إعدادات الربط ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT&tlsAllowInvalidCertificates=true"
ADMIN_ID = 1262656649
SUPPORT_NUMBER = "218913731533"

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI)
db = client['StoreDB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['transaction_logs']

# --- وظائف مساعدة ---
def is_frozen(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'مخالفة الشروط')
        bot.send_message(uid, f"⚠️ حسابك مجمد حالياً!\nالسبب: {reason}\nللفك تواصل مع الدعم.")
        return True
    return False

def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد", "🏦 شحن مباشر")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- البوت للمستخدمين ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    if is_frozen(uid): return
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب", request_contact=True))
        bot.send_message(uid, "🔹 مرحباً بك في شركة الأهرام للاتصالات\nيرجى التسجيل للمتابعة:", reply_markup=markup)
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
            "freeze_reason": "",
            "join_date": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        users_col.update_one({"_id": message.chat.id}, {"$set": user_data}, upsert=True)
        bot.send_message(message.chat.id, "✅ تم تفعيل حسابك!", reply_markup=main_menu())

# --- الشحن المباشر ---
@bot.message_handler(func=lambda m: m.text == "🏦 شحن مباشر")
def direct_charge(message):
    if is_frozen(message.chat.id): return
    msg = bot.send_message(message.chat.id, "أرسل (رقم حسابك : المبلغ)\nمثال: 12345 : 100")
    bot.register_next_step_handler(msg, process_direct_charge)

def process_direct_charge(message):
    try:
        acc, amt = message.text.split(":")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تأكيد الشحن", callback_data=f"adm_pay_{message.chat.id}_{amt.strip()}"))
        bot.send_message(ADMIN_ID, f"⚠️ طلب شحن جديد:\nالحساب: {acc}\nالمبلغ: {amt} د.ل\nالمستخدم: {message.chat.id}", reply_markup=markup)
        bot.send_message(message.chat.id, "✅ تم إرسال الطلب، بانتظار التأكيد.")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في التنسيق.")

# --- لوحة الإدارة الشاملة ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📦 إضافة بضاعة", callback_data="add_stock"), 
               types.InlineKeyboardButton("🎫 توليد كروت", callback_data="gen_cards"))
    markup.add(types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="manage_users"))
    bot.send_message(ADMIN_ID, "🛠 لوحة التحكم المتقدمة:", reply_markup=markup)

# --- إدارة المستخدمين والتجميد ---
@bot.callback_query_handler(func=lambda call: call.data == "manage_users")
def list_users(call):
    users = users_col.find().limit(10)
    markup = types.InlineKeyboardMarkup()
    for u in users:
        status_icon = "✅" if u.get('status') == 'active' else "❄️"
        markup.add(types.InlineKeyboardButton(f"{status_icon} {u['phone']}", callback_data=f"userinfo_{u['_id']}"))
    bot.send_message(ADMIN_ID, "اختر مستخدماً لإدارته:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("userinfo_"))
def user_info(call):
    uid = int(call.data.split("_")[1])
    u = users_col.find_one({"_id": uid})
    logs = list(logs_col.find({"uid": uid}).sort("_id", -1).limit(5))
    log_text = "\n".join([f"- {l['type']}: {l['amt']} د.ل ({l['date']})" for l in logs])
    
    text = f"👤 **بيانات المشترك:**\nالرقم: `{u['phone']}`\nالرصيد: {u['balance']} د.ل\nالحالة: {u.get('status')}\n\n📊 **آخر العمليات:**\n{log_text if log_text else 'لا يوجد سجل'}"
    
    markup = types.InlineKeyboardMarkup()
    if u.get('status') == 'active':
        markup.add(types.InlineKeyboardButton("❄️ تجميد الحساب", callback_data=f"freeze_{uid}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل الحساب", callback_data=f"activate_{uid}"))
    bot.edit_message_text(text, ADMIN_ID, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("freeze_"))
def freeze_step1(call):
    uid = call.data.split("_")[1]
    msg = bot.send_message(ADMIN_ID, "اكتب سبب التجميد ليظهر للمستخدم:")
    bot.register_next_step_handler(msg, lambda m: freeze_step2(m, uid))

def freeze_step2(message, uid):
    users_col.update_one({"_id": int(uid)}, {"$set": {"status": "frozen", "freeze_reason": message.text}})
    bot.send_message(ADMIN_ID, "✅ تم تجميد الحساب.")
    bot.send_message(int(uid), f"⚠️ تم تجميد حسابك.\nالسبب: {message.text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("activate_"))
def activate_user(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active", "freeze_reason": ""}})
    bot.send_message(ADMIN_ID, "✅ تم إعادة تفعيل الحساب.")
    bot.send_message(uid, "✅ تم تفعيل حسابك مجدداً، يمكنك استخدام البوت الآن.")

# --- توليد كروت الشحن بالفئات ---
@bot.callback_query_handler(func=lambda call: call.data == "gen_cards")
def gen_cards_prompt(call):
    msg = bot.send_message(ADMIN_ID, "أرسل الفئة والعدد بالتنسيق التالي:\n(الفئة : العدد)\nمثال: 10 : 50")
    bot.register_next_step_handler(msg, process_card_gen)

def process_card_gen(message):
    try:
        val, count = message.text.split(":")
        val, count = int(val.strip()), int(count.strip())
        generated = []
        for _ in range(count):
            card = "AHRAM-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            cards_col.insert_one({"code": card, "value": val, "used": False})
            generated.append(f"`{card}`")
        
        bot.send_message(ADMIN_ID, f"✅ تم توليد {count} كرت من فئة {val}:\n\n" + "\n".join(generated), parse_mode="Markdown")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق.")

# --- شحن الرصيد بالكروت ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge_card(message):
    if is_frozen(message.chat.id): return
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن الخاص بك:")
    bot.register_next_step_handler(msg, redeem_card)

def redeem_card(message):
    card = cards_col.find_one({"code": message.text, "used": False})
    if card:
        cards_col.update_one({"_id": card["_id"]}, {"$set": {"used": True}})
        users_col.update_one({"_id": message.chat.id}, {"$inc": {"balance": card["value"]}})
        logs_col.insert_one({"uid": message.chat.id, "type": "شحن كرت", "amt": card["value"], "date": datetime.datetime.now().strftime("%Y-%m-%d")})
        bot.send_message(message.chat.id, f"✅ تم شحن {card['value']} د.ل بنجاح!")
    else:
        bot.send_message(message.chat.id, "❌ الكود غير صحيح أو مستخدم.")

# --- معالج دفع الأدمن ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pay_"))
def admin_confirm_pay(call):
    _, _, uid, amt = call.data.split("_")
    users_col.update_one({"_id": int(uid)}, {"$inc": {"balance": int(amt)}})
    logs_col.insert_one({"uid": int(uid), "type": "شحن مباشر", "amt": int(amt), "date": datetime.datetime.now().strftime("%Y-%m-%d")})
    bot.send_message(int(uid), f"✅ تم تأكيد شحن محفظتك بـ {amt} د.ل!")
    bot.edit_message_text(f"✅ تم تنفيذ الشحن للمستخدم {uid}", ADMIN_ID, call.message.message_id)

# --- نظام الشراء ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    if is_frozen(message.chat.id): return
    products = stock_col.distinct("name")
    if not products: return bot.send_message(message.chat.id, "المخزن فارغ.")
    markup = types.InlineKeyboardMarkup()
    for p in products:
        item = stock_col.find_one({"name": p})
        markup.add(types.InlineKeyboardButton(f"{p} ({item['price']} د.ل)", callback_data=f"buy_{p}"))
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    if is_frozen(uid): return
    user = users_col.find_one({"_id": uid})
    item = stock_col.find_one({"name": p_name})
    if item and user['balance'] >= item['price']:
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        logs_col.insert_one({"uid": uid, "type": f"شراء {p_name}", "amt": -item['price'], "date": datetime.datetime.now().strftime("%Y-%m-%d")})
        bot.send_message(uid, f"✅ تم الشراء!\nكودك: `{item['secret']}`", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ رصيد غير كافٍ", show_alert=True)

# --- تشغيل ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
