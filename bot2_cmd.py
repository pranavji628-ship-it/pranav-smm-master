import os
import sqlite3
from datetime import datetime
import telebot
from telebot import types

TOKEN = os.environ.get("BOT2_TOKEN", "").strip()
bot2 = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

def get_db():
    conn = sqlite3.connect("pranav_network.db", timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

if bot2:
    @bot2.message_handler(commands=['start', 'help'])
    def b2_start(message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📦 Track Order", callback_data="track_info"),
            types.InlineKeyboardButton("📩 Raise Ticket", callback_data="ticket_info"),
            types.InlineKeyboardButton("🌐 Open Site", url="https://pranavsmm.shop")
        )
        bot2.send_message(message.chat.id, "🛰️ *PRANAV SMM SUPPORT & TRACKING HUB*\n\nऑर्डर ट्रैक या सहायता के लिए विकल्प चुनें:", reply_markup=markup, parse_mode="Markdown")

    @bot2.callback_query_handler(func=lambda call: True)
    def b2_cb(call):
        if call.data == "track_info":
            bot2.send_message(call.message.chat.id, "👉 ऑर्डर ट्रैक करने के लिए लिखें: `/track <Order_ID>`", parse_mode="Markdown")
        elif call.data == "ticket_info":
            bot2.send_message(call.message.chat.id, "👉 शिकायत दर्ज करने के लिए लिखें: `/ticket समस्या का विवरण`", parse_mode="Markdown")

    @bot2.message_handler(commands=['track'])
    def b2_track(message):
        parts = message.text.split()
        if len(parts) < 2: return bot2.reply_to(message, "👉 उपयोग: `/track <Order_ID>`")
        oid = parts[1].replace("#", "")
        bot2.reply_to(message, f"📦 *Order #{oid}*\n📊 स्थिति: Active / Processing ⚡\n(डिटेल्स वेबसाइट पर सिंक हैं)", parse_mode="Markdown")

    @bot2.message_handler(commands=['ticket'])
    def b2_ticket(message):
        issue = message.text.replace("/ticket", "").strip()
        if not issue: return bot2.reply_to(message, "👉 समस्या लिखें: `/ticket समस्या`")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO tickets (telegram_id, issue, created_at) VALUES (?, ?, ?)", (message.from_user.id, issue, datetime.now()))
        tid = cur.lastrowid
        conn.commit()
        conn.close()
        bot2.reply_to(message, f"✅ टिकट #{tid} दर्ज हो गया। एडमिन जल्द संपर्क करेगा।")
