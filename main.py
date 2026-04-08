# ===== ADMIN PANEL FULL SYSTEM (FIXED) =====

# ========= لوحة الأدمن =========
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
    banned = users_col.count_documents({"status": "banned"})
    active = users - banned

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
    bot.send_message(msg.chat.id, "📩 أرسل (عدد:قيمة)\nمثال: 10:5")
    bot.register_next_step_handler(msg, create_cards)

def create_cards(msg):
    if msg.chat.id != ADMIN_ID: return
    try:
        count, value = map(int, msg.text.split(":"))

        if count > 100:
            return bot.send_message(msg.chat.id, "❌ الحد الأقصى 100 كرت")

        import random, string

        cards = []
        text = "🎫 الكروت:\n\n"

        for _ in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            cards.append({
                "code": code,
                "value": value,
                "used": False,
                "created_at": datetime.datetime.now()
            })
            text += f"`{code}`\n"

        cards_col.insert_many(cards)
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")

    except:
        bot.send_message(msg.chat.id, "❌ تأكد من الصيغة (عدد:قيمة)")

# ========= شحن مباشر =========
@bot.message_handler(func=lambda m: m.text == "💳 شحن مباشر")
def direct(msg):
    if msg.chat.id != ADMIN_ID: return
    bot.send_message(msg.chat.id, "📩 أرسل (id:المبلغ)")
    bot.register_next_step_handler(msg, do_direct)

def do_direct(msg):
    if msg.chat.id != ADMIN_ID: return
    try:
        uid, amount = msg.text.split(":")
        uid = int(uid.strip())
        amount = int(amount.strip())

        user = users_col.find_one({"_id": uid})
        if not user:
            return bot.send_message(msg.chat.id, "❌ المستخدم غير موجود")

        users_col.update_one({"_id": uid}, {"$inc": {"balance": amount}})

        bot.send_message(msg.chat.id, "✅ تم الشحن")
        bot.send_message(uid, f"💰 تم إضافة {amount} د.ل إلى حسابك")

    except:
        bot.send_message(msg.chat.id, "❌ تأكد من الصيغة")

# ========= إضافة منتج =========
@bot.message_handler(func=lambda m: m.text == "➕ إضافة منتج")
def add_product(msg):
    if msg.chat.id != ADMIN_ID: return

    bot.send_message(msg.chat.id,
        "📩 أرسل:\n"
        "القسم:الفئة:الاسم:السعر\n"
        "CODE1\nCODE2\nCODE3"
    )
    bot.register_next_step_handler(msg, save_product)

def save_product(msg):
    if msg.chat.id != ADMIN_ID: return
    try:
        lines = msg.text.strip().split("\n")

        if len(lines) < 2:
            return bot.send_message(msg.chat.id, "❌ يجب إضافة أكواد")

        cat, sub, name, price = lines[0].split(":")
        price = float(price)

        codes = [c.strip() for c in lines[1:] if c.strip()]

        docs = [{
            "category": cat.strip(),
            "subcategory": sub.strip(),
            "name": name.strip(),
            "price": price,
            "code": c,
            "sold": False,
            "created_at": datetime.datetime.now()
        } for c in codes]

        stock_col.insert_many(docs)

        bot.send_message(msg.chat.id, f"✅ تم إضافة {len(codes)} كود")

    except:
        bot.send_message(msg.chat.id, "❌ خطأ في الصيغة")

# ========= المستخدمين =========
@bot.message_handler(func=lambda m: m.text == "👥 المستخدمين")
def users(msg):
    if msg.chat.id != ADMIN_ID: return

    us = list(users_col.find().sort("join_date", -1).limit(20))

    text = "👥 آخر المستخدمين:\n\n"
    kb = types.InlineKeyboardMarkup()

    for u in us:
        uid = u['_id']
        bal = u.get('balance', 0)

        text += f"{uid} | {bal}\n"

        kb.add(types.InlineKeyboardButton(
            f"⚙️ {uid}",
            callback_data=f"user_{uid}"
        ))

    bot.send_message(msg.chat.id, text, reply_markup=kb)

# ========= إدارة مستخدم =========
@bot.callback_query_handler(func=lambda c: c.data.startswith("user_"))
def manage_user(call):
    uid = int(call.data.split("_")[1])

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚫 حظر", callback_data=f"ban_{uid}"))
    kb.add(types.InlineKeyboardButton("✅ فك الحظر", callback_data=f"unban_{uid}"))

    bot.send_message(call.message.chat.id, f"👤 إدارة {uid}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ban_"))
def ban(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "banned"}})

    try:
        bot.send_message(uid, "🚫 تم حظرك")
    except:
        pass

    bot.answer_callback_query(call.id, "تم الحظر")

@bot.callback_query_handler(func=lambda c: c.data.startswith("unban_"))
def unban(call):
    uid = int(call.data.split("_")[1])
    users_col.update_one({"_id": uid}, {"$set": {"status": "active"}})

    try:
        bot.send_message(uid, "✅ تم فك الحظر")
    except:
        pass

    bot.answer_callback_query(call.id, "تم فك الحظر")

# ========= عرض الأقسام =========
@bot.message_handler(func=lambda m: m.text == "📦 الأقسام")
def show_cats(msg):
    if msg.chat.id != ADMIN_ID: return

    cats = stock_col.distinct("category")

    if not cats:
        return bot.send_message(msg.chat.id, "❌ لا توجد أقسام")

    text = "📦 الأقسام:\n\n"
    for c in cats:
        text += f"• {c}\n"

    bot.send_message(msg.chat.id, text)
