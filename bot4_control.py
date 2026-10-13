import os
import sys
import time
import random
import re
import socket
import sqlite3
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
import telebot
from telebot import types
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# ==============================================================================
# 1. कॉन्फ़िगरेशन एवं सेटिंग्स
# ==============================================================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
BOT_TOKEN = os.environ.get("BOT4_TOKEN", os.environ.get("BOT6_TOKEN", ""))
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "pranavsmm.help@gmail.com")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")

CONFIG = {
    "SITE_URL": "https://pranavsmm.shop",
    "LOGIN_URL": "https://pranavsmm.shop/secure-admin",
    "CLIENTS_URL": "https://pranavsmm.shop/secure-admin/clients",
    "ADMIN_USER": "pranavbot",
    "ADMIN_EMAIL": "pranav67me@gmail.com",
    "ADMIN_PASS": ADMIN_PASS
}

DB_PATH = "bot4_database.db"
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
admin_state = {}

# CORS हेडर जोड़ना
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# ==============================================================================
# 2. डेटाबेस सेटअप
# ==============================================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        web_email TEXT,
        balance REAL DEFAULT 0.0,
        status TEXT DEFAULT 'ACTIVE'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_verification (
        username TEXT PRIMARY KEY,
        email TEXT,
        utr TEXT,
        otp_code TEXT,
        attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        utr TEXT UNIQUE,
        amount REAL,
        status TEXT DEFAULT 'APPROVED',
        created_at TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY,
        amount REAL,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS coupon_redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        coupon_code TEXT,
        amount REAL,
        redeemed_at TIMESTAMP
    )
    """)
    cur.execute("INSERT OR IGNORE INTO coupons (code, amount, max_uses) VALUES ('PRANAV100', 100.0, 1000)")
    cur.execute("INSERT OR IGNORE INTO coupons (code, amount, max_uses) VALUES ('WELCOME50', 50.0, 500)")
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 3. SMARTPANEL BAN/UNBAN इंजन
# ==============================================================================
class PanelController:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"
        })

    def login(self):
        try:
            r = self.session.get(CONFIG["LOGIN_URL"], timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')
            token = ""
            inp = soup.find('input', {'name': '_token'})
            if inp:
                token = inp.get('value', '')
            else:
                meta = soup.find('meta', {'name': 'csrf-token'})
                if meta: token = meta.get('content', '')

            payloads = [
                {"username": CONFIG["ADMIN_USER"], "password": CONFIG["ADMIN_PASS"], "_token": token},
                {"email": CONFIG["ADMIN_EMAIL"], "password": CONFIG["ADMIN_PASS"], "_token": token}
            ]
            for p in payloads:
                res = self.session.post(CONFIG["LOGIN_URL"], data=p, timeout=12)
                if "logout" in res.text.lower() or res.status_code == 302:
                    return True
        except Exception:
            pass
        return False

    def change_user_status(self, username, action="active"):
        self.login()
        status_val = "active" if action == "active" else "deactive"

        try:
            search_url = f"{CONFIG['CLIENTS_URL']}?search={username}"
            r = self.session.get(search_url, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            client_id = None
            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    td = tr.find('td')
                    if td and td.text.strip().isdigit():
                        client_id = td.text.strip()
                        break

            token = ""
            inp = soup.find('input', {'name': '_token'})
            if inp: token = inp.get('value', '')

            endpoints = []
            if client_id:
                endpoints.append((f"{CONFIG['CLIENTS_URL']}/{status_val}/{client_id}", {}))
                endpoints.append((f"{CONFIG['CLIENTS_URL']}/status", {"id": client_id, "status": status_val, "_token": token}))
            endpoints.append((CONFIG['CLIENTS_URL'], {"username": username, "status": status_val, "action": status_val, "_token": token}))

            for url, data in endpoints:
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    conn = get_db()
                    cur = conn.cursor()
                    db_st = "ACTIVE" if action == "active" else "SUSPENDED"
                    cur.execute("UPDATE users SET status=? WHERE LOWER(username)=? OR LOWER(web_email)=?", (db_st, username.lower(), username.lower()))
                    conn.commit()
                    conn.close()
                    return True
        except Exception:
            pass
        return False

panel = PanelController()

# ==============================================================================
# 4. GMAIL OTP इंजन (IPv4 फिक्स)
# ==============================================================================
def send_official_email_otp(target_email, username, otp_code):
    if not SENDER_EMAIL or not GMAIL_APP_PASS:
        return False, "SENDER_EMAIL या GMAIL_APP_PASS Render में सेट नहीं है"

    orig_getaddrinfo = socket.getaddrinfo
    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        socket.getaddrinfo = ipv4_getaddrinfo
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} - Pranav SMM अकाउंट रिकवरी कोड"
        msg["From"] = f"Pranav SMM Support <{SENDER_EMAIL}>"
        msg["To"] = target_email

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0; padding:20px; background:#f8fafc; font-family:Arial, sans-serif;">
          <div style="max-width:480px; margin:auto; background:#ffffff; border-radius:18px; border:1px solid #e2e8f0; overflow:hidden;">
            <div style="background:linear-gradient(135deg, #7928ca, #5b21b6); padding:24px; text-align:center; color:#ffffff;">
              <h1 style="margin:0; font-size:22px; font-weight:800;">PRANAV SMM PANEL</h1>
              <p style="margin:4px 0 0; font-size:12px; opacity:0.9;">अकाउंट सिक्योरिटी एवं वेरिफिकेशन सिस्टम</p>
            </div>
            <div style="padding:28px 24px; text-align:center;">
              <p style="color:#334155; font-size:14px;">नमस्ते <b>{username}</b>,<br>अकाउंट अनबैन करने का OTP कोड नीचे दिया गया है:</p>
              <div style="background:#faf5ff; border:2px dashed #7928ca; border-radius:14px; padding:16px; margin:20px 0; display:inline-block; min-width:220px;">
                <span style="font-size:36px; font-weight:800; letter-spacing:8px; color:#6a1b9a;">{otp_code}</span>
              </div>
              <p style="color:#64748b; font-size:12px;">यह कोड 10 मिनट के लिए मान्य है।</p>
            </div>
          </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        clean_pass = GMAIL_APP_PASS.replace(" ", "")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
        server.ehlo()
        server.starttls()
        server.login(SENDER_EMAIL.strip(), clean_pass)
        server.sendmail(SENDER_EMAIL.strip(), [target_email.strip()], msg.as_string())
        server.quit()
        return True, "Email Sent"
    except Exception as e:
        return False, str(e)
    finally:
        socket.getaddrinfo = orig_getaddrinfo

# ==============================================================================
# 5. FLASK API (वेबसाइट, ऐड फंड, कूपन और अपील)
# ==============================================================================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Pranav SMM Autonomous Engine",
        "port": RENDER_PORT
    }), 200

@app.route('/api/check-google-user', methods=['POST', 'OPTIONS'])
def check_google_user_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    email = request.form.get("email", "").strip().lower()
    if not email:
        return jsonify({"suspended": False}), 200
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, username FROM users WHERE LOWER(web_email)=? OR LOWER(username)=?", (email, email))
    row = cur.fetchone()
    conn.close()
    if row and row["status"] == "SUSPENDED":
        return jsonify({"suspended": True, "username": row["username"] or email}), 200
    return jsonify({"suspended": False, "username": email}), 200

@app.route('/api/appeal', methods=['POST', 'OPTIONS'])
def receive_appeal():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get('username', 'User').strip()
    utr = request.form.get('utr', '').strip()
    email = request.form.get('email', '').strip().lower()

    if email and "@" in email:
        otp = f"{random.randint(100000, 999999)}"
        sent_ok, err_msg = send_official_email_otp(email, username, otp)
        if sent_ok:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO otp_verification (username, email, utr, otp_code, attempts, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                        (email, email, utr, otp, datetime.now()))
            conn.commit()
            conn.close()
            if bot and BOT_TOKEN:
                bot.send_message(ADMIN_ID, f"📧 *[OTP प्रेषित]*\nयूज़र: `{username}`\nGmail: `{email}`\nUTR: `{utr}`\nOTP: `{otp}`", parse_mode="Markdown")
            return jsonify({"status": "otp_sent", "msg": f"OTP {email} पर भेज दिया गया है।"}), 200

    threading.Thread(target=auto_unban_process, args=(username, utr)).start()
    return jsonify({"status": "success", "msg": "Appeal received, processing..."}), 200

@app.route('/api/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get("username", "").strip().lower()
    otp = request.form.get("otp", "").strip()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT email, utr, otp_code, attempts FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "msg": "कोई सक्रिय OTP अनुरोध नहीं मिला।"}), 200

    stored_email = row["email"]
    stored_utr = row["utr"]
    stored_otp = row["otp_code"]

    if str(stored_otp) != str(otp):
        conn.close()
        return jsonify({"status": "error", "msg": "गलत OTP कोड!"}), 200

    cur.execute("DELETE FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    conn.commit()
    conn.close()

    ok = panel.change_user_status(stored_email, "active")
    if bot and BOT_TOKEN:
        bot.send_message(ADMIN_ID, f"⚡ *[OTP सत्यापित - खाता Active]*\nयूज़र: `{stored_email}`\nUTR: `{stored_utr}`", parse_mode="Markdown")

    return jsonify({"status": "success", "msg": "OTP सत्यापित! अकाउंट Active कर दिया गया।"}), 200

@app.route('/api/add-fund', methods=['POST', 'OPTIONS'])
def add_fund_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get("username", "").strip()
    utr = request.form.get("utr", "").strip().replace(" ", "").upper()
    amount_str = request.form.get("amount", "0").strip()

    try:
        amount = float(amount_str)
    except ValueError:
        return jsonify({"status": "error", "msg": "अमान्य राशि!"}), 200

    if not username or not utr or amount <= 0:
        return jsonify({"status": "error", "msg": "सभी फ़ील्ड आवश्यक हैं!"}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM payments WHERE utr=?", (utr,))
    if cur.fetchone():
        conn.close()
        return jsonify({"status": "error", "msg": "यह UTR पहले ही उपयोग हो चुका है!"}), 200

    cur.execute("INSERT INTO payments (username, utr, amount, status, created_at) VALUES (?, ?, ?, 'APPROVED', ?)",
                (username, utr, amount, datetime.now()))
    cur.execute("""
        INSERT INTO users (username, balance) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET balance = balance + ?
    """, (username, amount, amount))
    cur.execute("SELECT balance FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    new_bal = row["balance"] if row else amount
    conn.commit()
    conn.close()

    if bot and BOT_TOKEN:
        bot.send_message(ADMIN_ID, f"💰 *[ADD FUND]*\nयूज़र: `{username}`\nUTR: `{utr}`\nराशि: ₹`{amount}`\nनया बैलेंस: ₹`{new_bal}`", parse_mode="Markdown")

    return jsonify({"status": "success", "msg": f"₹{amount} खाते में जोड़ दिए गए!", "new_balance": new_bal}), 200

@app.route('/api/redeem-coupon', methods=['POST', 'OPTIONS'])
def redeem_coupon_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get("username", "").strip()
    code = request.form.get("code", "").strip().upper()

    if not username or not code:
        return jsonify({"status": "error", "msg": "यूज़रनेम और कूपन कोड आवश्यक हैं!"}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT amount, max_uses, used_count FROM coupons WHERE code=?", (code,))
    coupon = cur.fetchone()

    if not coupon:
        conn.close()
        return jsonify({"status": "error", "msg": "अमान्य कूपन कोड!"}), 200

    if coupon["used_count"] >= coupon["max_uses"]:
        conn.close()
        return jsonify({"status": "error", "msg": "कूपन समाप्त हो चुका है!"}), 200

    cur.execute("SELECT id FROM coupon_redemptions WHERE username=? AND coupon_code=?", (username, code))
    if cur.fetchone():
        conn.close()
        return jsonify({"status": "error", "msg": "आप यह कूपन पहले ही उपयोग कर चुके हैं!"}), 200

    amt = coupon["amount"]
    cur.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code=?", (code,))
    cur.execute("INSERT INTO coupon_redemptions (username, coupon_code, amount, redeemed_at) VALUES (?, ?, ?, ?)",
                (username, code, amt, datetime.now()))
    cur.execute("""
        INSERT INTO users (username, balance) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET balance = balance + ?
    """, (username, amt, amt))
    cur.execute("SELECT balance FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    new_bal = row["balance"] if row else amt
    conn.commit()
    conn.close()

    if bot and BOT_TOKEN:
        bot.send_message(ADMIN_ID, f"🎟️ *[COUPON APPLIED]*\nयूज़र: `{username}`\nकूपन: `{code}`\nबोनस: ₹`{amt}`\nनया बैलेंस: ₹`{new_bal}`", parse_mode="Markdown")

    return jsonify({"status": "success", "msg": f"कूपन लागू! ₹{amt} खाते में जोड़े गए।", "new_balance": new_bal}), 200

def auto_unban_process(username, utr):
    success = panel.change_user_status(username, action="active")
    if bot and BOT_TOKEN:
        if success:
            msg = f"⚡ *[ऑटो-अनबैन सफल]*\n👤 यूज़र: `{username}`\n💳 UTR: `{utr if utr else 'N/A'}`\n✅ अकाउंट Active कर दिया गया!"
        else:
            msg = f"⚠️ *[ऑटो-अनबैन विफल]*\n👤 यूज़र: `{username}`\n❌ स्टेटस नहीं बदला। मैन्युअल बटन से करें।"
        try:
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
        except Exception:
            pass

# ==============================================================================
# 6. टेलीग्राम बोट (इनलाइन बटन्स)
# ==============================================================================
def get_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Unban User", callback_data="do_unban"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="do_ban"),
        types.InlineKeyboardButton("💰 Add Balance", callback_data="do_addbal"),
        types.InlineKeyboardButton("🔍 Check Balance", callback_data="do_checkbal"),
        types.InlineKeyboardButton("🎟️ Create Coupon", callback_data="do_addcoupon"),
        types.InlineKeyboardButton("📊 Status", callback_data="do_status")
    )
    return markup

if bot:
    @bot.message_handler(commands=['start', 'admin'])
    def start_admin(message):
        if message.from_user.id != ADMIN_ID:
            return
        bot.send_message(
            message.chat.id,
            "👑 **PRANAV SMM मास्टर कंट्रोल पैनल**\n\nनीचे दिए गए बटनों से संचालन करें:",
            reply_markup=get_keyboard(),
            parse_mode="Markdown"
        )

    @bot.callback_query_handler(func=lambda c: c.from_user.id == ADMIN_ID and c.data.startswith("do_"))
    def handle_clicks(call):
        cid = call.message.chat.id
        action = call.data.replace("do_", "")
        if action == "unban":
            admin_state[cid] = "unban"
            bot.send_message(cid, "✅ Unban करने के लिए यूज़रनेम या ईमेल भेजें:")
        elif action == "ban":
            admin_state[cid] = "ban"
            bot.send_message(cid, "🚫 Ban करने के लिए यूज़रनेम या ईमेल भेजें:")
        elif action == "addbal":
            admin_state[cid] = "addbal"
            bot.send_message(cid, "फॉर्मेट भेजें: `username amount`\nउदाहरण: `rahul12 100`", parse_mode="Markdown")
        elif action == "checkbal":
            admin_state[cid] = "checkbal"
            bot.send_message(cid, "बैलेंस देखने के लिए यूज़रनेम भेजें:")
        elif action == "addcoupon":
            admin_state[cid] = "addcoupon"
            bot.send_message(cid, "फॉर्मेट भेजें: `CODE AMOUNT`\nउदाहरण: `BONUS50 50`", parse_mode="Markdown")
        elif action == "status":
            bot.send_message(cid, f"⚡ सर्वर ऑनलाइन है!\nPort: `{RENDER_PORT}`", reply_markup=get_keyboard(), parse_mode="Markdown")

    @bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.chat.id in admin_state and not m.text.startswith('/'))
    def handle_text(message):
        cid = message.chat.id
        action_type = admin_state.pop(cid, None)
        text = message.text.strip()

        if action_type == "unban":
            msg = bot.send_message(cid, f"⏳ `{text}` को Unban किया जा रहा है...")
            ok = panel.change_user_status(text, "active")
            res_text = f"✅ `{text}` को Active कर दिया गया!" if ok else f"❌ `{text}` अनबैन नहीं हो सका।"
            bot.edit_message_text(res_text, cid, msg.message_id, reply_markup=get_keyboard())

        elif action_type == "ban":
            msg = bot.send_message(cid, f"⏳ `{text}` को Ban किया जा रहा है...")
            ok = panel.change_user_status(text, "deactivate")
            res_text = f"🚫 `{text}` को Deactive कर दिया गया!" if ok else f"❌ `{text}` बैन नहीं हो सका।"
            bot.edit_message_text(res_text, cid, msg.message_id, reply_markup=get_keyboard())

        elif action_type == "addbal":
            parts = text.split()
            if len(parts) >= 2:
                user = parts[0]
                try:
                    amt = float(parts[1])
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO users (username, balance) VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET balance = balance + ?", (user, amt, amt))
                    cur.execute("SELECT balance FROM users WHERE username=?", (user,))
                    row = cur.fetchone()
                    conn.commit()
                    conn.close()
                    bot.send_message(cid, f"💰 `{user}` के खाते में ₹{amt} जोड़े गए। नया बैलेंस: ₹{row['balance']}", reply_markup=get_keyboard())
                except ValueError:
                    bot.send_message(cid, "अमान्य राशि!", reply_markup=get_keyboard())
            else:
                bot.send_message(cid, "गलत फॉर्मेट!", reply_markup=get_keyboard())

        elif action_type == "checkbal":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT balance FROM users WHERE username=?", (text,))
            row = cur.fetchone()
            conn.close()
            bal = row["balance"] if row else 0.0
            bot.send_message(cid, f"👤 `{text}` का बैलेंस: ₹{bal}", reply_markup=get_keyboard())

        elif action_type == "addcoupon":
            parts = text.split()
            if len(parts) >= 2:
                c_code = parts[0].upper()
                try:
                    c_amt = float(parts[1])
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO coupons (code, amount, max_uses, used_count) VALUES (?, ?, 1000, 0)", (c_code, c_amt))
                    conn.commit()
                    conn.close()
                    bot.send_message(cid, f"🎟️ कूपन `{c_code}` (₹{c_amt}) बन गया!", reply_markup=get_keyboard())
                except ValueError:
                    bot.send_message(cid, "अमान्य राशि!", reply_markup=get_keyboard())
            else:
                bot.send_message(cid, "गलत फॉर्मेट!", reply_markup=get_keyboard())

    @bot.message_handler(content_types=['photo'])
    def catch_photo(message):
        cap = message.caption or ""
        u_match = re.search(r'User:\s*`([^`]+)`', cap) or re.search(r'यूज़र:\s*`([^`]+)`', cap)
        utr_match = re.search(r'Payment UTR:\s*`([^`]+)`', cap) or re.search(r'UTR:\s*`([^`]+)`', cap)
        user = u_match.group(1) if u_match else None
        utr = utr_match.group(1) if utr_match else ""
        if user: auto_unban_process(user, utr)

    @bot.message_handler(func=lambda m: m.text and ('User:' in m.text or 'यूज़र:' in m.text))
    def catch_text(message):
        txt = message.text
        u_match = re.search(r'User:\s*`([^`]+)`', txt) or re.search(r'यूज़र:\s*`([^`]+)`', txt)
        utr_match = re.search(r'Payment UTR:\s*`([^`]+)`', txt) or re.search(r'UTR:\s*`([^`]+)`', txt)
        user = u_match.group(1) if u_match else None
        utr = utr_match.group(1) if utr_match else ""
        if user: auto_unban_process(user, utr)

def self_ping_loop():
    time.sleep(10)
    while True:
        try:
            requests.get(f"https://pranav-smm-master-0cgu.onrender.com/", timeout=10)
        except Exception:
            pass
        time.sleep(300)

def start_bot_polling():
    if not bot or not BOT_TOKEN:
        return
    try:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    t_bot = threading.Thread(target=start_bot_polling, daemon=True)
    t_bot.start()
    t_ping = threading.Thread(target=self_ping_loop, daemon=True)
    t_ping.start()
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
