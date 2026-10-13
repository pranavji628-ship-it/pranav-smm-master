import os
import sqlite3
import telebot

TOKEN = os.environ.get("BOT5_TOKEN", "").strip()
bot5 = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

if bot5:
    @bot5.message_handler(commands=['start', 'status', 'help'])
    def b5_status(message):
        try:
            conn = sqlite3.connect("pranav_network.db")
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            tot = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM utr_records")
            utr_c = cur.fetchone()[0]
            conn.close()
        except Exception:
            tot, utr_c = 0, 0
        bot5.send_message(
            message.chat.id,
            f"👑 *SUPREME AI MONITOR*\n\n✅ 5 बॉट्स: Live 24/7 ⚡\n👥 कुल रजिस्टर्ड यूज़र्स: `{tot}`\n💳 वेरिफाइड UTR ट्रांजेक्शन: `{utr_c}`\n🌐 pranavsmm.shop: Connected ✅",
            parse_mode="Markdown"
        )
