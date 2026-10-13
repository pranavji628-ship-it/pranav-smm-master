import os
import sqlite3
import telebot

TOKEN = os.environ.get("BOT3_TOKEN", "").strip()
bot3 = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

def get_db():
    conn = sqlite3.connect("pranav_network.db", timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

if bot3:
    @bot3.message_handler(commands=['start', 'status', 'help'])
    def b3_start(message):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE status='SUSPENDED'")
        susp = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users")
        tot = cur.fetchone()[0]
        conn.close()
        bot3.send_message(
            message.chat.id,
            f"🛡️ *MASTER SENTINEL GUARD*\n\n👥 कुल यूज़र्स: `{tot}`\n⏳ सस्पेंडेड खाते: `{susp}`\n⚡ 24/7 ऑटो-सिक्योरिटी और एंटी-स्पैम शील्ड सक्रिय है!",
            parse_mode="Markdown"
        )
