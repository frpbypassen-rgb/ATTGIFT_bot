import telebot
from telebot import types
from pymongo import MongoClient
import random
import string
import datetime

# --- الإعدادات الأساسية ---
# توكن البوت الخاص بك
API_TOKEN = '8769145956:AAEKIAKJ2sGn9HFu_-M8diyND1J754fp_Wc'

# رابط الاتصال بقاعدة بيانات MongoDB (تأكد من وضع رابطك الصحيح هنا)
MONGO_URI = "mongodb+srv://frpbypassen_db_user:LpovkVYkrNU7qePp@attgift.rdamxpj.mongodb.net/?retryWrites=true&w=majority&appName=ATTGIFT"

# معرف المدير (أنت)
ADMIN_ID = 1262656649

# تهيئة البوت وقاعدة البيانات
bot = telebot.TeleBot(API_TOKEN)
client = MongoClient(MONGO_URI)
db = client['StoreDB']
users_col = db['users']
cards_col = db['topup_cards']
stock_col = db['stock']
sales_col = db['sales']

# --- لوحات المفاتيح (أزرار التحكم) ---

def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🛒 شراء كود"),
        types.KeyboardButton("💳 شحن رصيد"),
        types.KeyboardButton("👤 حسابي"),
        types.KeyboardButton("📢 الدعم الفني")
    )
    return markup

# --- الأوامر الأساسية ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user = users_col.find_one({"_id": uid})
    
    if not user:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تسجيل الحساب برقم الهاتف", request_contact=True))
        bot.send_message(uid, "مرحباً بك في متجر ATTGIFT! يرجى التسجيل للمتابعة:", reply_markup=markup)
    else:
        bot.send_message(uid, f"أهلاً بك مجدداً!\nرصيدك الحالي: {user['balance']} د.ل", reply_markup=main_menu())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if message.contact:
        # إنشاء مستخدم جديد في قاعدة البيانات
        user_data = {
            "_id": uid,
            "phone": message.contact.phone_number,
            "balance": 0,
            "join_date": str(datetime.datetime.now())
        }
        users_col.update_one({"_id": uid}, {"$set": user_data}, upsert=True)
        bot.send_message(uid, "✅ تم تسجيل حسابك بنجاح في قاعدة البيانات السحابية!", reply_markup=main_menu())

# --- لوحة الإدارة (للمدير فقط) ---

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ إضافة بضاعة (أكواد للبيع)", callback_data="add_stock"))
    markup.add(types.InlineKeyboardButton("🎫 توليد كرت شحن (للمحفظة)", callback_data="gen_topup"))
    markup.add(types.InlineKeyboardButton("📦 عرض المخزن الحالي", callback_data="view_stock"))
    markup.add(types.InlineKeyboardButton("👥 إحصائيات المستخدمين", callback_data="user_stats"))
    
    bot.send_message(ADMIN_ID, "🛠 لوحة إدارة المتجر (السحابية):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_admin_queries(call):
    if call.data == "gen_topup":
        # توليد كود شحن محفظة بقيمة 10 دينار (كمثال)
        new_code = "GIFT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        cards_col.insert_one({"code": new_code, "value": 10})
        bot.send_message(ADMIN_ID, f"🎫 كرت شحن جديد بقيمة 10 د.ل:\n`{new_code}`", parse_mode="Markdown")
    
    elif call.data == "add_stock":
        msg = bot.send_message(ADMIN_ID, "يرجى إرسال تفاصيل الكود بالتنسيق التالي:\n\nالاسم : السعر : الكود\n\nمثال:\nببجي 60 شدة : 5 : ABCD-1234")
        bot.register_next_step_handler(msg, process_add_stock)
    
    elif call.data == "view_stock":
        items = list(stock_col.find())
        if not items:
            bot.send_message(ADMIN_ID, "📦 المخزن فارغ حالياً.")
        else:
            report = "📦 حالة المخزن:\n"
            counts = {}
            for i in items:
                counts[i['name']] = counts.get(i['name'], 0) + 1
            for name, count in counts.items():
                report += f"- {name}: متوفر ({count}) قطع\n"
            bot.send_message(ADMIN_ID, report)

    elif call.data == "user_stats":
        count = users_col.count_documents({})
        bot.send_message(ADMIN_ID, f"👥 عدد المشتركين المسجلين: {count}")

def process_add_stock(message):
    try:
        # تقسيم الرسالة بناءً على النقطتين :
        parts = [p.strip() for p in message.text.split(":")]
        if len(parts) != 3:
            raise ValueError
        
        name, price, secret = parts[0], int(parts[1]), parts[2]
        
        # إضافة الكود للمخزن في MongoDB
        stock_col.insert_one({
            "name": name,
            "price": price,
            "secret": secret,
            "added_at": str(datetime.datetime.now())
        })
        bot.send_message(ADMIN_ID, f"✅ تم إضافة المنتج بنجاح:\nالمنتج: {name}\nالسعر: {price} د.ل")
    except Exception as e:
        bot.send_message(ADMIN_ID, "❌ خطأ في التنسيق! يرجى المحاولة مرة أخرى والتأكد من استخدام النقطتين `:` للفصل بين البيانات.")

# --- وظائف المستخدم (الشحن والشراء) ---

@bot.message_handler(func=lambda m: m.text == "💳 شحن رصيد")
def recharge_request(message):
    msg = bot.send_message(message.chat.id, "أدخل كود الشحن الذي حصلت عليه من الإدارة:")
    bot.register_next_step_handler(msg, process_user_recharge)

def process_user_recharge(message):
    code = message.text.strip()
    uid = message.chat.id
    
    # البحث عن الكود وحذفه فوراً لضمان عدم استخدامه مرتين
    card = cards_col.find_one_and_delete({"code": code})
    
    if card:
        amount = card['value']
        users_col.update_one({"_id": uid}, {"$inc": {"balance": amount}})
        bot.send_message(uid, f"✅ تم شحن محفظتك بنجاح بـ {amount} د.ل!")
    else:
        bot.send_message(uid, "❌ كود الشحن غير صحيح أو تم استخدامه من قبل.")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء كود")
def shop_menu(message):
    # جلب أسماء المنتجات الفريدة المتوفرة في المخزن
    products = stock_col.distinct("name")
    
    if not products:
        bot.send_message(message.chat.id, "نعتذر، لا توجد منتجات متوفرة حالياً في المتجر.")
        return

    markup = types.InlineKeyboardMarkup()
    for p_name in products:
        # جلب أول قطعة متوفرة لمعرفة السعر
        sample_item = stock_col.find_one({"name": p_name})
        markup.add(types.InlineKeyboardButton(f"{p_name} - {sample_item['price']} د.ل", callback_data=f"buy_{p_name}"))
    
    bot.send_message(message.chat.id, "اختر المنتج الذي ترغب في شرائه:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def finalize_purchase(call):
    p_name = call.data.split("_")[1]
    uid = call.message.chat.id
    
    user = users_col.find_one({"_id": uid})
    # جلب أول كود متاح في المخزن لهذا المنتج
    item = stock_col.find_one({"name": p_name})
    
    if not item:
        bot.answer_callback_query(call.id, "نعتذر، نفدت الكمية من هذا المنتج!")
        return

    if user['balance'] >= item['price']:
        # خصم الرصيد وحذف الكود من المخزن
        users_col.update_one({"_id": uid}, {"$inc": {"balance": -item['price']}})
        stock_col.delete_one({"_id": item['_id']})
        
        # إرسال الكود للزبون
        bot.send_message(uid, f"✅ تمت عملية الشراء بنجاح!\n\nمنتجك: {p_name}\nكود التفعيل: `{item['secret']}`\n\nشكراً لتعاملك معنا!", parse_mode="Markdown")
        
        # إشعار للمدير
        bot.send_message(ADMIN_ID, f"🔔 عملية بيع جديدة:\nالمستخدم: {uid}\nالمنتج: {p_name}\nالسعر: {item['price']}")
    else:
        bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ! يرجى شحن المحفظة أولاً.", show_alert=True)

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def profile(message):
    user = users_col.find_one({"_id": message.chat.id})
    if user:
        text = f"👤 **معلومات حسابك**\n\n📱 الرقم: `{user['phone']}`\n💰 الرصيد: `{user['balance']}` د.ل\n🆔 المعرف: `{user['_id']}`"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📢 الدعم الفني")
def support(message):
    bot.send_message(message.chat.id, "للتواصل مع الإدارة مباشرة:\n@حساب_الدعم_الخاص_بك")

# تشغيل البوت بشكل مستمر
print("--- البوت الآن متصل بقاعدة بيانات MongoDB وهو يعمل ---")
bot.infinity_polling()
