import os
import sqlite3
from datetime import datetime
import telebot
from telebot import types

TOKEN = os.environ.get("BOT1_TOKEN", "").strip()
bot1 = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

def get_db():
    conn = sqlite3.connect("pranav_network.db", timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

user_states = {}

if bot1:
    @bot1.message_handler(commands=['start', 'help'])
    def b1_start(message):
        try:
            uid = message.from_user.id
            caller_name = message.from_user.first_name or "दोस्त"
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT status, balance, web_username FROM users WHERE telegram_id=?", (uid,))
            row = cur.fetchone()

            if not row:
                cur.execute("INSERT INTO users (telegram_id, username, last_low_alert) VALUES (?, ?, ?)", (uid, message.from_user.username or '', datetime.now()))
                conn.commit()
                balance, status, web_user = 0.0, "ACTIVE", None
            else:
                status, balance, web_user = row[0], row[1], row[2]

            if status == "SUSPENDED":
                conn.close()
                bot1.reply_to(message, f"🛑 *नमस्ते {caller_name}, आपका खाता सस्पेंड है!*\n━━━━━━━━━━━━━━\n📸 अनबैन के लिए पेमेंट का स्क्रीनशॉट या UTR भेजें।", parse_mode="Markdown")
                return
            conn.close()

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("💎 Services & Rates", callback_data="services"),
                types.InlineKeyboardButton("🎁 Redeem Coupon", callback_data="start_redeem"),
                types.InlineKeyboardButton("📝 New Sign Up", callback_data="start_signup"),
                types.InlineKeyboardButton("🔗 अपना अकाउंट जोड़ें", callback_data="link_account"),
                types.InlineKeyboardButton("🔑 Reset Password", callback_data="start_reset"),
                types.InlineKeyboardButton("🛰️ Order Tracker", url="https://t.me/pranavsmm_cmd_bot"),
                types.InlineKeyboardButton("🌐 Visit Website", url="https://pranavsmm.shop")
            )

            acc_info = f"🔗 *लिंक्ड खाता:* `{web_user}`" if web_user else "⚠️ *अकाउंट लिंक नहीं है: नीचे से साइनअप या लॉगिन करें*"
            welcome_text = (
                "┏━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "   👑 *PRANAV SMM OFFICIAL* 👑\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
                f"👋 *नमस्ते, {caller_name}!*\n"
                f"💰 *वॉलेट बैलेंस:* `₹{balance:.2f}`\n"
                f"{acc_info}\n\n"
                "👉 नीचे दिए गए विकल्प चुनें:"
            )
            bot1.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass

    @bot1.callback_query_handler(func=lambda call: True)
    def b1_callbacks(call):
        try:
            uid = call.from_user.id
            if call.data == "services":
                text = (
                    "💎 *POPULAR SERVICES & RATES* 💎\n\n"
                    "📌 Instagram Followers: ₹28 / 1K (Non-Drop)\n"
                    "📌 Instagram Likes: ₹4.50 / 1K (Instant)\n"
                    "📌 YouTube Subscribers: ₹210 / 1K (Guaranteed)\n"
                    "📌 Telegram Members: ₹45 / 1K (Active)\n\n"
                    "👉 ऑर्डर लगाने के लिए वेबसाइट पर जाएँ!"
                )
                bot1.send_message(call.message.chat.id, text, parse_mode="Markdown")
            elif call.data == "start_redeem":
                user_states[uid] = {"action": "redeem"}
                bot1.send_message(call.message.chat.id, "🎁 *कूपन कोड दर्ज करें:*\nअपना प्रोमो कोड लिखकर भेजें:", parse_mode="Markdown")
            elif call.data == "start_signup":
                user_states[uid] = {"action": "signup", "step": 1}
                bot1.send_message(call.message.chat.id, "📝 *स्टेप 1/5:* कृपया अपना **Username** (बिना स्पेस के) भेजें:")
            elif call.data == "link_account":
                user_states[uid] = {"action": "link", "step": 1}
                bot1.send_message(call.message.chat.id, "🔗 *स्टेप 1/2:* अपनी वेबसाइट का **Username** भेजें:")
            elif call.data == "start_reset":
                user_states[uid] = {"action": "reset"}
                bot1.send_message(call.message.chat.id, "🔑 *पासवर्ड रीसेट:* अपनी रजिस्टर्ड **Email ID या Username** भेजें:")
        except Exception:
            pass

    @bot1.message_handler(func=lambda msg: msg.text and not msg.text.startswith('/'))
    def handle_customer_steps(message):
        from bot4_control import bridge, bot4, CONFIG
        try:
            uid = message.from_user.id
            text = message.text.strip()

            if uid in user_states and user_states[uid].get("action") == "redeem":
                del user_states[uid]
                code = text.upper()
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT web_username FROM users WHERE telegram_id=?", (uid,))
                row = cur.fetchone()
                web_user = row[0] if (row and row[0]) else None

                if not web_user:
                    conn.close()
                    bot1.reply_to(message, "⚠️ कूपन क्लेम करने से पहले 'अपना अकाउंट जोड़ें' से लिंक करें!")
                    return

                cur.execute("SELECT id, amount, status FROM coupons WHERE code=?", (code,))
                c_row = cur.fetchone()
                if not c_row or c_row[2] != 'ACTIVE':
                    conn.close()
                    bot1.reply_to(message, "❌ *अमान्य या समाप्त कूपन कोड!*")
                    return

                cid, amt = c_row[0], c_row[1]
                bot1.reply_to(message, "⏳ वेबसाइट पर फंड जोड़ा जा रहा है...")
                ok, res_msg = bridge.add_fund(web_user, amt)
                if not ok:
                    conn.close()
                    bot1.reply_to(message, f"❌ एरर: {res_msg}")
                    return

                cur.execute("UPDATE coupons SET status='USED', used_by=?, used_at=? WHERE id=?", (uid, datetime.now(), cid))
                cur.execute("UPDATE users SET balance=balance+?, last_low_alert=? WHERE telegram_id=?", (amt, datetime.now(), uid))
                cur.execute("INSERT INTO payments_log (target_username, amount, added_by, created_at) VALUES (?, ?, ?, ?)", (web_user, amt, f"COUPON_{code}", datetime.now()))
                conn.commit()
                conn.close()
                bot1.reply_to(message, f"🎉 *बधाई! ₹{amt:.2f} आपके खाते में जुड़ गए!*\n👤 खाता: `{web_user}`", parse_mode="Markdown")
                return

            if uid in user_states and user_states[uid].get("action") == "signup":
                state = user_states[uid]
                st = state.get("step")
                if st == 1:
                    state["username"] = text
                    state["step"] = 2
                    bot1.reply_to(message, "👤 *स्टेप 2/5:* अपना **पूरा नाम** भेजें:")
                    return
                elif st == 2:
                    state["name"] = text
                    state["step"] = 3
                    bot1.reply_to(message, "📧 *स्टेप 3/5:* अपनी **E-Mail ID** भेजें:")
                    return
                elif st == 3:
                    state["email"] = text
                    state["step"] = 4
                    bot1.reply_to(message, "📱 *स्टेप 4/5:* अपना **Whatsapp No.** भेजें:")
                    return
                elif st == 4:
                    state["phone"] = text
                    state["step"] = 5
                    bot1.reply_to(message, "🔒 *स्टेप 5/5:* अपना **Password** सेट करें:")
                    return
                elif st == 5:
                    pwd, uname, fname, em, ph = text, state["username"], state["name"], state["email"], state["phone"]
                    del user_states[uid]
                    bot1.reply_to(message, "⏳ वेबसाइट पर खाता बनाया जा रहा है...")
                    ok, reg_msg = bridge.register_user(uname, fname, em, ph, pwd)
                    if ok:
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE users SET web_username=?, web_name=?, web_email=?, web_phone=?, web_password=?, balance=0.0, status='ACTIVE', last_low_alert=? WHERE telegram_id=?", (uname, fname, em, ph, pwd, datetime.now(), uid))
                        conn.commit()
                        conn.close()
                        bot1.reply_to(message, f"🎉 *अकाउंट बन गया!*\n👤 Username: `{uname}`\n🔒 Password: `{pwd}`\n🌐 लॉगिन करें: https://pranavsmm.shop", parse_mode="Markdown")
                    else:
                        bot1.reply_to(message, f"❌ वेबसाइट एरर: {reg_msg}")
                    return

            # बॉट 1 पर गलत इनपुट पर 4-स्ट्राइक ऑटो-बैन
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT strikes, web_username FROM users WHERE telegram_id=?", (uid,))
            r_u = cur.fetchone()
            strikes = (r_u[0] + 1) if (r_u and r_u[0]) else 1
            w_u = r_u[1] if (r_u and r_u[1]) else "unknown"

            if strikes >= 4:
                cur.execute("UPDATE users SET status='SUSPENDED', strikes=0, suspended_at=? WHERE telegram_id=?", (datetime.now(), uid))
                conn.commit()
                conn.close()
                bridge.trigger_status(w_u, "deactivate")
                bot1.reply_to(message, "🚨 *लगातार 4 बार गलत इनपुट! खाता सस्पेंड किया गया।*")
            else:
                cur.execute("UPDATE users SET strikes=? WHERE telegram_id=?", (strikes, uid))
                conn.commit()
                conn.close()
                bot1.reply_to(message, f"⚠️ *अमान्य इनपुट! (चेतावनी {strikes}/4)*")
        except Exception:
            pass

    @bot1.message_handler(content_types=['photo'])
    def b1_handle_screenshot(message):
        from bot4_control import bot4, CONFIG
        try:
            uid = message.from_user.id
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT web_username FROM users WHERE telegram_id=?", (uid,))
            row = cur.fetchone()
            conn.close()
            w_user = row[0] if (row and row[0]) else f"ID_{uid}"
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("➕ ₹10 जोड़ें", callback_data=f"quickadd_{uid}_{w_user}_10"),
                types.InlineKeyboardButton("➕ ₹50 जोड़ें", callback_data=f"quickadd_{uid}_{w_user}_50"),
                types.InlineKeyboardButton("➕ ₹100 जोड़ें", callback_data=f"quickadd_{uid}_{w_user}_100"),
                types.InlineKeyboardButton("✅ Unban करें", callback_data=f"unban_{uid}")
            )
            if bot4:
                bot4.send_photo(
                    CONFIG["ADMIN_TELEGRAM_ID"],
                    message.photo[-1].file_id,
                    caption=f"📸 *पेमेंट स्क्रीनशॉट आया!*\n🆔 ID: `{uid}`\n🌐 Web User: `{w_user}`\n👤 Name: {message.from_user.first_name}",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            bot1.reply_to(message, "✅ आपका स्क्रीनशॉट एडमिन को भेज दिया गया है।")
        except Exception:
            pass
