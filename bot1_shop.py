import os
import re
import time
import random
import string
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types

BOT1_TOKEN = os.environ.get("BOT1_TOKEN", "").strip()
bot1 = telebot.TeleBot(BOT1_TOKEN, threaded=False) if BOT1_TOKEN else None

SITE_URL = "https://pranavsmm.shop"
user_reg_data = {}

def get_db():
    conn = sqlite3.connect("pranav_network.db", timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def generate_strong_password():
    letters = "".join(random.choices(string.ascii_letters, k=6))
    digits = "".join(random.choices(string.digits, k=3))
    special = random.choice(["@", "#", "$", "!"])
    return f"{letters.capitalize()}{special}{digits}"

class DirectWebSignup:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": f"{SITE_URL}/signup",
            "Origin": SITE_URL
        }

    def register(self, username, email, phone, password):
        session = requests.Session()
        session.headers.update(self.headers)
        target_url = f"{SITE_URL}/signup"
        token = ""

        # 1. CSRF टोकन और कुकी निकालना
        try:
            r = session.get(target_url, timeout=12)
            if r.status_code != 200:
                target_url = f"{SITE_URL}/auth/signup"
                r = session.get(target_url, timeout=12)

            soup = BeautifulSoup(r.text, 'html.parser')
            tok_inp = soup.find('input', {'name': '_token'})
            if tok_inp:
                token = tok_inp.get('value', '')
            else:
                meta = soup.find('meta', {'name': 'csrf-token'})
                if meta:
                    token = meta.get('content', '')
        except Exception:
            pass

        # जो Username रहेगा, वही Name रहेगा
        payload = {
            "_token": token,
            "username": username,
            "name": username,
            "first_name": username,
            "last_name": "Patel",
            "email": email,
            "telephone": phone,
            "phone": phone,
            "whatsapp": phone,
            "password": password,
            "password_again": password,
            "confirm_password": password,
            "repassword": password,
            "terms": "on",
            "terms_policy": "1",
            "agree": "1"
        }

        try:
            res = session.post(target_url, data=payload, timeout=15, allow_redirects=True)
            txt = res.text.lower()
            if "already exists" in txt or "already taken" in txt or "उपलब्ध नहीं" in txt:
                return False, "यह Username या Email पहले से वेबसाइट पर मौजूद है।"
            if res.status_code in [200, 302]:
                return True, "सफल"
        except Exception as e:
            return False, str(e)

        return True, "सफल"

signup_engine = DirectWebSignup()

def get_shop_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📝 Create Account", callback_data="shop_reg"),
        types.InlineKeyboardButton("🎁 Redeem Coupon", callback_data="shop_coupon"),
        types.InlineKeyboardButton("💳 Add Money (QR/Bank)", callback_data="shop_addmoney"),
        types.InlineKeyboardButton("💰 My Balance", callback_data="shop_balance"),
        types.InlineKeyboardButton("🌐 Visit Website", url=SITE_URL)
    )
    return markup

if bot1:
    @bot1.message_handler(commands=['start', 'shop'])
    def send_welcome(message):
        bot1.send_message(
            message.chat.id,
            "🛍️ *PRANAV SMM OFFICIAL STORE*\n\n"
            "प्रणव एसएमएम स्टोर में आपका स्वागत है!\n"
            "👇 नीचे दिए गए विकल्पों में से चुनें:",
            reply_markup=get_shop_markup(),
            parse_mode="Markdown"
        )

    @bot1.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
    def handle_shop_callbacks(call):
        cid = call.message.chat.id
        if call.data == "shop_reg":
            user_reg_data[cid] = {}
            msg = bot1.send_message(cid, "✏️ *स्टेप 1/3:* अपनी पसंद का **Username** भेजें (बिना स्पेस):\n_(यही आपका डिस्प्ले नाम भी रहेगा)_", parse_mode="Markdown")
            bot1.register_next_step_handler(msg, step_username)
        elif call.data == "shop_coupon":
            msg = bot1.send_message(cid, "🎁 अपना **कूपन कोड** भेजें:")
            bot1.register_next_step_handler(msg, step_redeem_coupon)
        elif call.data == "shop_balance":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT web_username, balance FROM users WHERE telegram_id=?", (cid,))
            row = cur.fetchone()
            conn.close()
            if row:
                bot1.send_message(cid, f"👤 यूज़रनेम: `{row[0]}`\n💰 वर्तमान बैलेंस: `₹{row[1]:.2f}`", reply_markup=get_shop_markup(), parse_mode="Markdown")
            else:
                bot1.send_message(cid, "❌ आपका खाता लिंक नहीं है। पहले 'Create Account' करें।", reply_markup=get_shop_markup())
        elif call.data == "shop_addmoney":
            bot1.send_message(
                cid,
                "💳 *फंड जोड़ने के लिए:* वेबसाइट पर जाएँ या पेमेंट करके उसका UTR यहाँ भेजें।",
                reply_markup=get_shop_markup(),
                parse_mode="Markdown"
            )

    def step_username(m):
        cid = m.chat.id
        uname = re.sub(r'[^a-zA-Z0-9_]', '', m.text.strip())
        if len(uname) < 3:
            msg = bot1.send_message(cid, "❌ यूज़रनेम कम से कम 3 अक्षरों का होना चाहिए। दोबारा भेजें:")
            return bot1.register_next_step_handler(msg, step_username)
        user_reg_data[cid] = {"username": uname}
        msg = bot1.send_message(cid, "📧 *स्टेप 2/3:* अपनी **E-Mail ID** भेजें:", parse_mode="Markdown")
        bot1.register_next_step_handler(msg, step_email)

    def step_email(m):
        cid = m.chat.id
        em = m.text.strip()
        if "@" not in em or "." not in em:
            msg = bot1.send_message(cid, "❌ अमान्य ईमेल! कृपया सही ईमेल भेजें:")
            return bot1.register_next_step_handler(msg, step_email)
        user_reg_data[cid]["email"] = em
        msg = bot1.send_message(cid, "📱 *स्टेप 3/3:* अपना **WhatsApp No.** भेजें:", parse_mode="Markdown")
        bot1.register_next_step_handler(msg, step_phone_and_create)

    def step_phone_and_create(m):
        cid = m.chat.id
        phone = re.sub(r'[^0-9+]', '', m.text.strip())
        data = user_reg_data.get(cid, {})
        data["phone"] = phone
        auto_pwd = generate_strong_password()

        msg = bot1.send_message(cid, "⏳ **वेबसाइट पर खाता बनाया जा रहा है...**", parse_mode="Markdown")

        ok, res_msg = signup_engine.register(data["username"], data["email"], data["phone"], auto_pwd)

        if not ok and "पहले से" in res_msg:
            return bot1.edit_message_text(f"❌ {res_msg}", cid, msg.message_id, reply_markup=get_shop_markup())

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT OR REPLACE INTO users 
            (telegram_id, username, web_username, web_name, web_email, web_phone, web_password, balance, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 'ACTIVE')""",
            (cid, m.from_user.username or "", data["username"], data["username"], data["email"], data["phone"], auto_pwd))
        conn.commit()
        conn.close()

        bot1.edit_message_text(
            f"🎉 *बधाई हो! आपका खाता सफलतापूर्वक बन गया!*\n━━━━━━━━━━━━━━\n"
            f"👤 **Username:** `{data['username']}`\n"
            f"📛 **Name:** `{data['username']}`\n"
            f"📧 **Email:** `{data['email']}`\n"
            f"📱 **WhatsApp:** `{data['phone']}`\n"
            f"🔒 **Password:** `{auto_pwd}`\n"
            f"🌐 **Website:** https://pranavsmm.shop\n━━━━━━━━━━━━━━\n"
            f"💡 _पासवर्ड अपने आप सुरक्षित बना दिया गया है। आप तुरंत वेबसाइट पर लॉगिन कर सकते हैं!_",
            cid, msg.message_id,
            reply_markup=get_shop_markup(),
            parse_mode="Markdown"
        )

    def step_redeem_coupon(m):
        cid = m.chat.id
        code = m.text.strip().upper()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, amount, status FROM coupons WHERE code=?", (code,))
        c = cur.fetchone()
        if not c or c[2] != 'ACTIVE':
            conn.close()
            return bot1.send_message(cid, "❌ अमान्य या समाप्त हो चुका कूपन कोड!", reply_markup=get_shop_markup())
        
        amt = c[1]
        cur.execute("UPDATE coupons SET status='USED', used_by=?, used_at=? WHERE id=?", (cid, datetime.now(), c[0]))
        cur.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amt, cid))
        conn.commit()
        conn.close()
        bot1.send_message(cid, f"🎉 कूपन रिडीम हुआ! आपके खाते में ₹{amt:.2f} जोड़ दिए गए।", reply_markup=get_shop_markup())
