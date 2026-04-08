# ===== ADMIN PANEL FULL SYSTEM =====

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if msg.chat.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "❌ غير مصرح")

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 احصائيات", "🎫 توليد كروت")
    kb.add("💳 شحن مباشر", "➕ إضافة منتج")
    kb.add("👥 المستخدمين", "📦 الأقسام")

    bot.send_message(msg.chat.id, "👑 لوحة التحكم:", reply_markup=kb)

# ========= احصائيات =========
@bot.message_handler(func=lambda m: m.text == "📊 احصائيات")
def stats(msg):
    if msg.chat.id != ADMIN_ID: return

    users = users_col.count_documents({})
    active = users_col.count_documents({"status": {"$ne": "banned"}})
    banned = users_col.count_documents({"status": "banned"})

    stock = stock_col.count_documents({})
    sold = stock_col.count_documents({"sold": True})

    bot.send_message(msg.chat.id,
        f"📊 الإحصائيات\n\n"
        f"👥 المستخدمين: {users}\n"
        f"✅ النشطين: {active}\n"
        f"🚫 المحظورين: {banned}\n\n"
        f"📦 المنتجات: {stock}\n"
        f"🛒 المباعة: {sold}"
    )

# ========= توليد كروت =========
@bot.message_handler(func=lambda m: m.text == "🎫 توليد كروت")
def gen_cards(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (عدد:قيمة)\nمثال: 10:5")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    try:
        count, value = map(int, msg.text.split(":"))

        cards = []
        text = "🎫 الكروت:\n\n"

        for _ in range(count):
            code = ''.join(__import__('random').choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))
            cards.append({"code": code, "value": value, "used": False})
            text += f"`{code}`\n"

        cards_col.insert_many(cards)
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")

    except:
        bot.send_message(msg.chat.id, "❌ خطأ")

# ========= شحن مباشر =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن مباشر")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "أرسل (id:المبلغ)")
    bot.register_next_step_handler(msg, do_direct)

def do_direct(msg):
    try:
        uid, amount = msg.text.split(":")
        uid = int(uid)
        amount = int(amount)

        users_col.update_one({"_id": uid}, {"$inc": {"balance": amount}})
        bot.send_message(msg.chat.id, "✅ تم الشحن")

        bot.send_message(uid, f"💰 تم إضافة {amount}")

    except:
        bot.send_message(msg.chat.id, "❌ خطأ")

# ========= إضافة منتج =========
@bot.message_handler(func=lambda m: m.text == "➕ إضافة منتج")
def add_product(msg):
    if msg.chat.id != ADMIN_ID: return

    bot.send_message(msg.chat.id,
        "أرسل:\n"
        "القسم:الفئة:الاسم:السعر\n"
        "CODE1\nCODE2\nCODE3"
    )
    bot.register_next_step_handler(msg, save_product)

def save_product(msg):
    try:
        lines = msg.text.split("\n")
        cat, sub, name, price = lines[0].split(":")
        price = int(price)

        codes = lines[1:]

        docs = []
        for c in codes:
            docs.append({
                "category": cat,
                "subcategory": sub,
                "name": name,
                "price": price,
                "code": c,
                "sold": False
            })

        stock_col.insert_many(docs)
        bot.send_message(msg.chat.id, f"✅ تم إضافة {len(codes)} كود")

    except:
        bot.send_message(msg.chat.id, "❌ خطأ")

# ========= المستخدمين =========
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users(msg):
    if msg.chat.id != ADMIN_ID: return

    us = list(users_col.find().limit(20))

    text = "👥 المستخدمين:\n\n"
    kb = types.InlineKeyboardMarkup()

    for u in us:
        text += f"{u['_id']} | {u.get('balance',0)}\n"
        kb.add(types.InlineKeyboardButton(
            f"إدارة {u['_id']}",
            callback_data=f"user_{u['_id']}"
        ))

    bot.send_message(msg.chat.id, text, reply_markup=kb)

# ========= إدارة مستخدم =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("user_"))
def manage_user(call):
    uid = int(call.data.split("_")[1])

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚫 حظر", callback_data=f"ban_{uid}"))
    kb.add(types.InlineKeyboardButton("✅ فك الحظر", callback_data=f"unban_{uid}"))

    bot.send_message(call.message.chat.id, f"إدارة {uid}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ban_"))
def ban(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "banned"}})
    bot.send_message(uid, "🚫 تم حظرك")
    bot.answer_callback_query(call.id, "تم")

@bot.callback_query_handler(func=lambda c: c.data.startswith("unban_"))
def unban(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active"}})
    bot.send_message(uid, "✅ تم فك الحظر")
    bot.answer_callback_query(call.id, "تم")

# ========= عرض الأقسام =========
@bot.message_handler(func=lambda m: m.text == "📦 الأقسام")
def show_cats(msg):
    if msg.chat.id != ADMIN_ID: return

    cats = stock_col.distinct("category")
    text = "📦 الأقسام:\n\n"

    for c in cats:
        text += f"- {c}\n"

    bot.send_message(msg.chat.id, text)
