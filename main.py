import telebot
from telebot import types
from pymongo import MongoClient
import datetime
import os
import certifi
from flask import Flask
from threading import Thread

# --- إعداد السيرفر ---
app = Flask('')
@app.route('/')
def home(): return "System Online"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- إعدادات البوت وقاعدة البيانات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"
ADMIN_ID = 1262656649

bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['AlAhram_DB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
logs_col = db['logs']

# --- وظيفة التحقق من حالة الحساب ---
def is_account_active(uid):
    user = users_col.find_one({"_id": uid})
    if user and user.get('status') == 'frozen':
        reason = user.get('freeze_reason', 'مخالفة النظام')
        bot.send_message(uid, f"⚠️ **{reason}**")
        return False
    return True

# --- الأزرار الرئيسية ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🛒 شراء كود", "💳 شحن رصيد")
    markup.add("👤 حسابي", "📢 الدعم الفني")
    return markup

# --- معالجة الأوامر ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تفعيل الحساب", request_contact=True))
        bot.send_message(uid, "مرحباً بك في شركة الأهرام. يرجى الضغط على الزر لتسجيل حسابك:", reply_markup=markup)
    else:
        bot.send_message(uid, "أهلاً بك مجدداً في القائمة الرئيسية", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def tech_support(message):
    bot.send_message(message.chat.id, "📞 للتواصل مع الدعم الفني المباشر:\n@AlAhram_Support\nأو اتصل بنا على: 091XXXXXXX")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def buy_code_menu(message):
    if not is_account_active(message.chat.id): return
    products = list(stock_col.find({"sold": False}))
    if not products:
        bot.send_message(message.chat.id, "⚠️ عذراً، لا توجد أكواد متوفرة حالياً.")
        return
    
    markup = types.InlineKeyboardMarkup()
    # عرض المنتجات الفريدة (مثل WATCH IT, Snapchat)
    seen = set()
    for p in products:
        if p['name'] not in seen:
            markup.add(types.InlineKeyboardButton(f"{p['name']} ({p['price']} د.ل)", callback_data=f"buy_{p['name']}"))
            seen.add(p['name'])
    bot.send_message(message.chat.id, "اختر المنتج الذي ترغب بشرائه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_purchase(call):
    uid = call.message.chat.id
    p_name = call.data.split("_")[1]
    user = users_col.find_one({"_id": uid})
    product = stock_col.find_one({"name": p_name, "sold": False})
    
    if user['balance'] < product['price']:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ!", show_alert=True)
        return

    # إتمام العملية
    stock_col.update_one({"_id": product['_id']}, {"$set": {"sold": True, "sold_to": uid, "date": datetime.datetime.now()}})
    users_col.update_one({"_id": uid}, {"$inc": {"balance": -product['price']}})
    
    # تسجيل العملية في التقارير
    logs_col.insert_one({"uid": uid, "type": "buy", "price": product['price'], "date": datetime.datetime.now()})
    
    bot.send_message(uid, f"✅ تم الشراء بنجاح!\nكود المنتج: `{product['code']}`", parse_mode="Markdown")
    bot.answer_callback_query(call.id, "تمت العملية")

@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def charge_init(message):
    if not is_account_active(message.chat.id): return
    msg = bot.send_message(message.chat.id, "🔢 يرجى إرسال كود الكرت:")
    bot.register_next_step_handler(msg, check_topup_card)

def check_topup_card(message):
    uid = message.chat.id
    code = message.text.strip()
    user = users_col.find_one({"_id": uid})
    card = cards_col.find_one({"code": code, "used": False})

    if card:
        # شحن ناجح: تصفير عداد المحاولات الخاطئة
        users_col.update_one({"_id": uid}, {
            "$inc": {"balance": card['val']},
            "$set": {"failed_attempts": 0}
        })
        cards_col.update_one({"_id": card['_id']}, {"$set": {"used": True, "user": uid}})
        bot.send_message(uid, f"✅ تم شحن {card['val']} د.ل بنجاح!")
    else:
        # محاولة خاطئة: زيادة العداد
        new_attempts = user.get('failed_attempts', 0) + 1
        users_col.update_one({"_id": uid}, {"$set": {"failed_attempts": new_attempts}})
        
        if new_attempts >= 3:
            users_col.update_one({"_id": uid}, {"$set": {"status": "frozen", "freeze_reason": "تم تجميد حسابك بسبب المحاولة في تخريب النظام"}})
            bot.send_message(uid, "⚠️ تم تجميد حسابك بسبب المحاولة في تخريب النظام.")
        else:
            bot.send_message(uid, f"❌ كود خاطئ! لديك {3 - new_attempts} محاولات متبقية قبل التجميد.")

# --- تشغيل البوت مع حل تعارض 409 ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.remove_webhook() # إزالة أي Webhook سابق لضمان عمل Polling
    print("🚀 System Active...")
    bot.infinity_polling(skip_pending=True)
