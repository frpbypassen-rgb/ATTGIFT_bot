import telebot
from telebot import types
import json
import os
import random
import string

# --- الإعدادات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
ADMIN_ID = 123456789  # !!! استبدل هذا الرقم بـ ID حسابك من بوت @userinfobot
bot = telebot.TeleBot(API_TOKEN)
DATA_FILE = 'store_data.json'

# --- إدارة البيانات ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "topup_cards": {}, "stock": {}, "sales": []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- لوحات المفاتيح ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("👤 حسابي", "🛒 شراء كود", "💳 شحن رصيد", "🛠 الدعم")
    return markup

# --- الأوامر الأساسية ---
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    uid = str(message.chat.id)
    if uid not in data['users']:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "مرحباً بك في متجر الأكواد! يرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, "مرحباً بك مجدداً في متجرك!", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    data = load_data()
    uid = str(message.chat.id)
    if message.contact:
        data['users'][uid] = {"phone": message.contact.phone_number, "balance": 0}
        save_data(data)
        bot.send_message(uid, "✅ تم التسجيل! رصيدك الحالي 0 د.ل", reply_markup=main_menu())

# --- نظام الشحن بكود تعبئة ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def recharge_btn(message):
    msg = bot.send_message(message.chat.id, "أدخل كود كرت التعبئة الذي حصلت عليه من الإدارة:")
    bot.register_next_step_handler(msg, process_recharge)

def process_recharge(message):
    data = load_data()
    code = message.text.strip()
    uid = str(message.chat.id)
    if code in data['topup_cards']:
        amount = data['topup_cards'][code]
        data['users'][uid]['balance'] += amount
        del data['topup_cards'][code]
        save_data(data)
        bot.send_message(uid, f"✅ تمت عملية الشحن بنجاح! تم إضافة {amount} د.ل لرصيدك.")
    else:
        bot.send_message(uid, "❌ الكود غير صحيح أو مستخدم مسبقاً.")

# --- نظام شراء الأكواد (المنتجات) ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop_btn(message):
    data = load_data()
    if not data['stock']:
        return bot.send_message(message.chat.id, "نعتذر، لا توجد منتجات متوفرة حالياً.")
    
    markup = types.InlineKeyboardMarkup()
    for category in data['stock'].keys():
        markup.add(types.InlineKeyboardButton(category, callback_data=f"cat_{category}"))
    bot.send_message(message.chat.id, "اختر التصنيف الذي تريد الشراء منه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def show_codes(call):
    data = load_data()
    category = call.data.split("_")[1]
    items = data['stock'][category]
    
    if not items:
        return bot.answer_callback_query(call.id, "هذا القسم فارغ حالياً!")
    
    text = f"قسم {category}:\n"
    markup = types.InlineKeyboardMarkup()
    # عرض أول كود متاح في هذا القسم
    price = items[0]['price']
    markup.add(types.InlineKeyboardButton(f"شراء (السعر: {price} د.ل)", callback_data=f"buy_{category}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def final_buy(call):
    data = load_data()
    uid = str(call.message.chat.id)
    category = call.data.split("_")[1]
    
    user_balance = data['users'][uid]['balance']
    item = data['stock'][category][0] # سحب أول كود في المخزن
    
    if user_balance >= item['price']:
        # خصم الرصيد
        data['users'][uid]['balance'] -= item['price']
        sold_code = data['stock'][category].pop(0) # حذف الكود من المخزن
        data['sales'].append({"user": uid, "code": sold_code['secret'], "date": str(call.message.date)})
        save_data(data)
        
        bot.edit_message_text(f"✅ تم الشراء بنجاح!\nكود المنتج الخاص بك هو:\n\n`{sold_code['secret']}`", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        # إشعار للمدير
        bot.send_message(ADMIN_ID, f"📢 عملية بيع جديدة!\nالمستخدم: {uid}\nالمنتج: {category}")
    else:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ! يرجى شحن المحفظة.", show_alert=True)

# --- لوحة الإدارة ---
@bot.message_handler(commands=['admin'])
def admin_menu(message):
    if message.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة (أكواد للبيع)", callback_data="add_stock"))
    markup.add(types.InlineKeyboardButton("🎫 توليد كرت شحن محفظة", callback_data="gen_topup"))
    bot.send_message(ADMIN_ID, "لوحة تحكم المدير:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "gen_topup")
def gen_topup(call):
    data = load_data()
    new_code = "CARD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    data['topup_cards'][new_code] = 10 # القيمة 10 د.ل كمثال
    save_data(data)
    bot.send_message(ADMIN_ID, f"تم توليد كرت شحن بقيمة 10 د.ل:\n`{new_code}`", parse_mode="Markdown")

# --- تشغيل البوت ---
print("تم تشغيل البوت بنجاح...")
bot.infinity_polling()
