import telebot
from telebot import types
import json
import os
import random
import string

# --- الإعدادات ---
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'
ADMIN_ID = 1262656649  # تم وضع رقمك كمدير
bot = telebot.TeleBot(API_TOKEN)
DATA_FILE = 'store_data.json'

# --- إدارة البيانات ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "topup_cards": {}, "stock": {}, "sales": []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {"users": {}, "topup_cards": {}, "stock": {}, "sales": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- لوحات المفاتيح ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("👤 حسابي", "🛒 شراء كود", "💳 شحن رصيد")
    return markup

# --- الأوامر الأساسية ---
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    uid = str(message.chat.id)
    if uid not in data['users']:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "مرحباً بك في متجرك! يرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, "مرحباً بك مجدداً!", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    data = load_data()
    uid = str(message.chat.id)
    if message.contact:
        data['users'][uid] = {"phone": message.contact.phone_number, "balance": 0}
        save_data(data)
        bot.send_message(uid, "✅ تم التسجيل بنجاح!", reply_markup=main_menu())

# --- لوحة الإدارة (فقط لك) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة (أكواد)", callback_data="add_stock"))
    markup.add(types.InlineKeyboardButton("🎫 توليد كرت شحن محفظة", callback_data="gen_topup"))
    markup.add(types.InlineKeyboardButton("📊 عرض المخزن", callback_data="view_stock"))
    bot.send_message(ADMIN_ID, "🛠 لوحة إدارة المتجر:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "gen_topup":
        data = load_data()
        new_code = "GIFT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        data['topup_cards'][new_code] = 10  # القيمة الافتراضية 10
        save_data(data)
        bot.send_message(ADMIN_ID, f"🎫 كرت شحن جديد (10 د.ل):\n`{new_code}`", parse_mode="Markdown")
    
    elif call.data == "add_stock":
        msg = bot.send_message(ADMIN_ID, "أرسل تفاصيل المنتج بهذا التنسيق حصراً:\n\nالاسم : السعر : الكود\n\nمثال:\nببجي 60 : 5 : ABCD-1234")
        bot.register_next_step_handler(msg, process_add_stock)
    
    elif call.data == "view_stock":
        data = load_data()
        text = "📦 المخزن الحالي:\n"
        for cat, items in data['stock'].items():
            text += f"- {cat}: {len(items)} قطعة متبقية\n"
        bot.send_message(ADMIN_ID, text if data['stock'] else "المخزن فارغ!")

def process_add_stock(message):
    try:
        parts = message.text.split(":")
        name = parts[0].strip()
        price = int(parts[1].strip())
        secret = parts[2].strip()
        
        data = load_data()
        if name not in data['stock']: data['stock'][name] = []
        data['stock'][name].append({"secret": secret, "price": price})
        save_data(data)
        bot.send_message(ADMIN_ID, f"✅ تم إضافة المنتج: {name}\nالسعر: {price}\nالكود: {secret}")
    except:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق! حاول مجدداً من لوحة الإدارة.")

# --- نظام الشحن والشراء للزبون ---
@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def ask_recharge(message):
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن الخاص بك:")
    bot.register_next_step_handler(msg, do_recharge)

def do_recharge(message):
    data = load_data()
    code = message.text.strip()
    uid = str(message.chat.id)
    if code in data['topup_cards']:
        val = data['topup_cards'].pop(code)
        data['users'][uid]['balance'] += val
        save_data(data)
        bot.send_message(uid, f"✅ تم شحن {val} د.ل بنجاح!")
    else:
        bot.send_message(uid, "❌ كود خاطئ.")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop(message):
    data = load_data()
    if not data['stock']: return bot.send_message(message.chat.id, "المتجر فارغ حالياً.")
    markup = types.InlineKeyboardMarkup()
    for cat in data['stock'].keys():
        if data['stock'][cat]:
            price = data['stock'][cat][0]['price']
            markup.add(types.InlineKeyboardButton(f"{cat} ({price} د.ل)", callback_data=f"buy_{cat}"))
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    data = load_data()
    uid = str(call.message.chat.id)
    cat = call.data.split("_")[1]
    
    if data['users'][uid]['balance'] >= data['stock'][cat][0]['price']:
        item = data['stock'][cat].pop(0)
        data['users'][uid]['balance'] -= item['price']
        save_data(data)
        bot.send_message(uid, f"✅ تم الشراء!\nكود المنتج:\n`{item['secret']}`", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ!", show_alert=True)

bot.infinity_polling()
