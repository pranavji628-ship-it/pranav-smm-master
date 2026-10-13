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
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# ==============================================================================
# 1. कॉन्फ़िगरेशन एवं पर्यावरण चर (RENDER ENV VARS)
# ==============================================================================
RENDER_PORT = int(os.environ.get("PORT", 8081))

BOT1_TOKEN = os.environ.get("BOT1_TOKEN", "").strip()
BOT2_TOKEN = os.environ.get("BOT2_TOKEN", "").strip()
BOT3_TOKEN = os.environ.get("BOT3_TOKEN", "").strip()
BOT4_TOKEN = os.environ.get("BOT4_TOKEN", "").strip()
BOT5_TOKEN = os.environ.get("BOT5_TOKEN", "").strip()

ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "pranav67me@gmail.com")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "pranavsmmsupport@gmail.com")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")

SITE_URL = "https://pranavsmm.shop"
ADMIN_LOGIN_URL = f"{SITE_URL}/secure-admin"
CLIENTS_URL = f"{ADMIN_LOGIN_URL}/clients"
PAYMENTS_URL = f"{ADMIN_LOGIN_URL}/payments"

DB_PATH = "pranav_master_system.db"
app = Flask(__name__)
admin_state = {}

# CORS हेडर
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# ==============================================================================
# 2. डेटाबेस इनिशियलाइज़ेशन
# ==============================================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_verification (
        username TEXT PRIMARY KEY,
        email TEXT,
        utr TEXT,
        otp_code TEXT,
        attempts INTEGER DEFAULT 0,
        expires_at TIMESTAMP,
        created_at TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scanned_routes (
        name TEXT PRIMARY KEY,
        url TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        target TEXT,
        details TEXT,
        timestamp TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()

def log_audit(action, target, details):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO audit_logs (action, target, details, timestamp) VALUES (?, ?, ?, ?)",
                    (action, target, str(details), datetime.now()))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ==============================================================================
# 3. स्मार्टपैनल ऑटोनॉमस कंट्रोलर
# ==============================================================================
class SmartPanelMaster:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"
        })
        self.routes = {}

    def extract_token(self, soup):
        inp = soup.find('input', {'name': '_token'})
        if inp: return inp.get('value', '')
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta: return meta.get('content', '')
        return ''

    def login(self):
        try:
            r = self.session.get(ADMIN_LOGIN_URL, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')
            token = self.extract_token(soup)

            payloads = [
                {"email": ADMIN_EMAIL, "password": ADMIN_PASS, "_token": token},
                {"username": ADMIN_EMAIL, "password": ADMIN_PASS, "_token": token},
                {"username": "pranavbot", "password": ADMIN_PASS, "_token": token}
            ]
            for p in payloads:
                res = self.session.post(ADMIN_LOGIN_URL, data=p, timeout=12)
                if "logout" in res.text.lower() or res.status_code == 302:
                    return True
        except Exception:
            pass
        return False

    def scan_all_routes(self):
        if not self.login():
            return {}
        try:
            r = self.session.get(ADMIN_LOGIN_URL, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')
            found = {}
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip()
                if "secure-admin" in href and text and "logout" not in href.lower():
                    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip()
                    if clean_name and len(clean_name) <= 20:
                        full_url = href if href.startswith("http") else f"{SITE_URL}{href}"
                        found[clean_name] = full_url
            self.routes = found
            conn = get_db()
            cur = conn.cursor()
            for name, url in found.items():
                cur.execute("INSERT OR REPLACE INTO scanned_routes (name, url) VALUES (?, ?)", (name, url))
            conn.commit()
            conn.close()
            return found
        except Exception:
            return {}

    def change_user_status(self, username, action="active"):
        self.login()
        status_val = "active" if action == "active" else "deactive"
        try:
            r = self.session.get(f"{CLIENTS_URL}?search={username}", timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')
            client_id = None
            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    td = tr.find('td')
                    if td and td.text.strip().isdigit():
                        client_id = td.text.strip()
                        break

            token = self.extract_token(soup)
            endpoints = []
            if client_id:
                endpoints.append((f"{CLIENTS_URL}/{status_val}/{client_id}", {}))
                endpoints.append((f"{CLIENTS_URL}/status", {"id": client_id, "status": status_val, "_token": token}))
            endpoints.append((CLIENTS_URL, {"username": username, "status": status_val, "action": status_val, "_token": token}))

            for url, data in endpoints:
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    log_audit(f"STATUS_{action.upper()}", username, "Success")
                    return True
        except Exception:
            pass
        return False

    def add_funds(self, username, amount):
        self.login()
        try:
            r = self.session.get(f"{CLIENTS_URL}?search={username}", timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            client_id = None
            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    td = tr.find('td')
                    if td and td.text.strip().isdigit():
                        client_id = td.text.strip()
                        break

            token = self.extract_token(soup)
            endpoints = [
                (f"{CLIENTS_URL}/add-funds", {"user_id": client_id or username, "amount": amount, "_token": token}),
                (f"{PAYMENTS_URL}/add", {"username": username, "amount": amount, "method": "Manual", "_token": token}),
                (f"{CLIENTS_URL}/edit/{client_id}" if client_id else "", {"balance": amount, "_token": token, "action": "add_funds"})
            ]
            for url, data in endpoints:
                if not url: continue
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    log_audit("ADD_FUNDS", username, f"Amount: {amount}")
                    return True
        except Exception:
            pass
        return False

panel = SmartPanelMaster()

# ==============================================================================
# 4. GMAIL OTP सिस्टम (IPv4 BINDING)
# ==============================================================================
def send_official_email_otp(target_email, username, otp_code):
    if not SENDER_EMAIL or not GMAIL_APP_PASS:
        return False, "Render में Gmail क्रेडेंशियल्स उपलब्ध नहीं हैं"

    orig_getaddrinfo = socket.getaddrinfo
    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        socket.getaddrinfo = ipv4_getaddrinfo
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} - Pranav SMM Account Verification Code"
        msg["From"] = f"Pranav SMM Support <{SENDER_EMAIL}>"
        msg["To"] = target_email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 16px; background: #ffffff;">
            <h2 style="color: #6a1b9a; text-align: center;">PRANAV SMM PANEL</h2>
            <p style="text-align: center; color: #64748b; font-size: 13px;">Security & Account Recovery System</p>
            <div style="background: #faf5ff; border: 2px dashed #7928ca; border-radius: 12px; padding: 18px; text-align: center; margin: 25px 0;">
                <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #6a1b9a;">{otp_code}</span>
            </div>
            <p style="color: #334155; font-size: 14px;">नमस्ते <b>{username}</b>,<br>खाता सक्रिय करने का 6-अंक का OTP कोड ऊपर दिया गया है। मान्य अवधि: 10 मिनट।</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        clean_pass = GMAIL_APP_PASS.replace(" ", "")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
        server.ehlo()
        server.starttls()
        server.login(SENDER_EMAIL.strip(), clean_pass)
        server.sendmail(SENDER_EMAIL.strip(), [target_email.strip()], msg.as_string())
        server.quit()
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)
    finally:
        socket.getaddrinfo = orig_getaddrinfo

# ==============================================================================
# 5. FLASK API ENDPOINTS
# ==============================================================================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Pranav SMM Master All-In-One Engine",
        "port": RENDER_PORT,
        "bots": ["Bot1 Support", "Bot2 Orders", "Bot3 Payment", "Bot4 Admin Hub", "Bot5 Alerts"]
    }), 200

@app.route('/api/check-google-user', methods=['POST', 'OPTIONS'])
def check_google_user_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    email = request.form.get("email", "").strip().lower()
    if not email:
        return jsonify({"suspended": False}), 200
    try:
        panel.login()
        r = panel.session.get(f"{CLIENTS_URL}?search={email}", timeout=10)
        if "deactive" in r.text.lower() or "banned" in r.text.lower():
            return jsonify({"suspended": True, "username": email}), 200
    except Exception:
        pass
    return jsonify({"suspended": False, "username": email}), 200

@app.route('/api/appeal', methods=['POST', 'OPTIONS'])
def receive_appeal():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get('username', 'User').strip()
    utr = request.form.get('utr', '').strip()
    email = request.form.get('email', '').strip().lower()

    if not email or "@" not in email:
        return jsonify({"status": "error", "msg": "Invalid email"}), 400

    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now() + timedelta(minutes=10)

    sent_ok, err_msg = send_official_email_otp(email, username, otp)
    if not sent_ok:
        return jsonify({"status": "error", "msg": err_msg}), 500

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO otp_verification 
        (username, email, utr, otp_code, attempts, expires_at, created_at) 
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (email, email, utr, otp, expires_at, datetime.now()))
    conn.commit()
    conn.close()

    if bot5:
        try:
            bot5.send_message(ADMIN_ID, f"🔔 *[अपील अलर्ट]*\nयूज़र: `{username}`\nGmail: `{email}`\nUTR: `{utr}`\nOTP: `{otp}`", parse_mode="Markdown")
        except Exception:
            pass

    return jsonify({"status": "otp_sent", "msg": f"OTP successfully sent to {email}"}), 200

@app.route('/api/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    username = request.form.get("username", "").strip().lower()
    otp = request.form.get("otp", "").strip()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT email, utr, otp_code, attempts, expires_at FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    row = cur.fetchone()

    if not row or str(row["otp_code"]) != str(otp):
        conn.close()
        return jsonify({"status": "error", "msg": "गलत OTP कोड!"}), 400

    target_email = row["email"]
    target_utr = row["utr"]
    cur.execute("DELETE FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    conn.commit()
    conn.close()

    panel.change_user_status(target_email, "active")
    if bot4:
        try:
            bot4.send_message(ADMIN_ID, f"⚡ *[सत्यापित खाता Active]*\nयूज़र: `{target_email}`\nUTR: `{target_utr}`", parse_mode="Markdown")
        except Exception:
            pass

    return jsonify({"status": "success", "msg": "Account Activated!"}), 200

# ==============================================================================
# 6. टेलीग्राम बॉट्स (BOT 1, 2, 3, 4, 5)
# ==============================================================================
bot1 = telebot.TeleBot(BOT1_TOKEN, threaded=True) if BOT1_TOKEN else None
bot2 = telebot.TeleBot(BOT2_TOKEN, threaded=True) if BOT2_TOKEN else None
bot3 = telebot.TeleBot(BOT3_TOKEN, threaded=True) if BOT3_TOKEN else None
bot4 = telebot.TeleBot(BOT4_TOKEN, threaded=True) if BOT4_TOKEN else None
bot5 = telebot.TeleBot(BOT5_TOKEN, threaded=True) if BOT5_TOKEN else None

# --- BOT 1: कस्टमर सपोर्ट ---
if bot1:
    @bot1.message_handler(commands=['start', 'help'])
    def b1_start(m):
        bot1.reply_to(m, "👋 *Pranav SMM Support Hub* में आपका स्वागत है!\n\nवेबसाइट: https://pranavsmm.shop\nअपनी समस्या यहाँ लिखें।", parse_mode="Markdown")

# --- BOT 2: ऑर्डर ट्रैकर ---
if bot2:
    @bot2.message_handler(commands=['start'])
    def b2_start(m):
        bot2.reply_to(m, "📦 *Pranav SMM Order Tracker*\n\nऑर्डर स्टेटस देखने के लिए Order ID भेजें:")

    @bot2.message_handler(func=lambda m: m.text and m.text.isdigit())
    def b2_order(m):
        bot2.reply_to(m, f"🔍 Order `{m.text}` की जांच की जा रही है... स्थिति: Processing", parse_mode="Markdown")

# --- BOT 3: पेमेंट व UTR रिसीवर ---
if bot3:
    @bot3.message_handler(commands=['start'])
    def b3_start(m):
        bot3.reply_to(m, "💳 *Pranav SMM Payment Gateway*\n\nफंड जोड़ने या अपील के लिए पेमेंट स्क्रीनशॉट या 12-अंक का UTR भेजें।")

    @bot3.message_handler(func=lambda m: m.text and len(m.text.strip()) >= 8)
    def b3_utr(m):
        bot3.reply_to(m, f"✅ UTR `{m.text.strip()}` प्राप्त हुआ! एडमिन सत्यापन जारी है।", parse_mode="Markdown")
        if bot5:
            bot5.send_message(ADMIN_ID, f"💰 *नया UTR प्राप्त:*\nUser: `{m.from_user.username or m.from_user.id}`\nUTR: `{m.text.strip()}`", parse_mode="Markdown")

# --- BOT 4: मास्टर एडमिन कंट्रोलर (वेबसाइट ऑटो-स्कैनर) ---
def get_b4_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 फुल एडमिन री-स्कैन", callback_data="act_rescan"),
        types.InlineKeyboardButton("💰 ऐड फंड्स", callback_data="act_addfunds")
    )
    markup.add(
        types.InlineKeyboardButton("✅ यूज़र Unban", callback_data="act_unban"),
        types.InlineKeyboardButton("🚫 यूज़र Ban", callback_data="act_ban")
    )
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, url FROM scanned_routes")
    routes = cur.fetchall()
    conn.close()
    if routes:
        btns = [types.InlineKeyboardButton(f"📂 {r['name']}", callback_data=f"page_{r['name']}") for r in routes[:8]]
        markup.add(*btns)
    return markup

if bot4:
    @bot4.message_handler(commands=['start', 'admin', 'scan'])
    def b4_start(m):
        if m.from_user.id != ADMIN_ID:
            bot4.reply_to(m, "⛔ अनधिकृत एक्सेस!")
            return
        msg = bot4.send_message(m.chat.id, "🤖 *प्रणव जी, स्मार्टपैनल लाइव स्कैन हो रहा है...*", parse_mode="Markdown")
        routes = panel.scan_all_routes()
        bot4.edit_message_text(
            f"👑 *PRANAV SMM मास्टर एडमिन रोबोट*\n\n"
            f"✅ लॉगिन: सफल\n"
            f"📡 स्कैन किए गए मेन्यू: `{len(routes)}`\n\n"
            f"वेबसाइट कंट्रोल करने के लिए नीचे बटन चुनें:",
            m.chat.id,
            msg.message_id,
            reply_markup=get_b4_keyboard(),
            parse_mode="Markdown"
        )

    @bot4.callback_query_handler(func=lambda c: True)
    def b4_clicks(c):
        if c.from_user.id != ADMIN_ID:
            bot4.answer_callback_query(c.id, "अनुमति नहीं है!", show_alert=True)
            return
        cid = c.message.chat.id
        data = c.data

        if data == "act_rescan":
            msg = bot4.send_message(cid, "🔄 पूरा एडमिन पैनल री-स्कैन हो रहा है...")
            routes = panel.scan_all_routes()
            bot4.edit_message_text(f"✅ री-स्कैन पूरा हुआ! `{len(routes)}` मेन्यू बटन जुड़े।", cid, msg.message_id, reply_markup=get_b4_keyboard(), parse_mode="Markdown")
        elif data == "act_unban":
            admin_state[cid] = "unban"
            bot4.send_message(cid, "✅ Unban करने के लिए यूज़रनेम या ईमेल भेजें:")
        elif data == "act_ban":
            admin_state[cid] = "ban"
            bot4.send_message(cid, "🚫 Ban करने के लिए यूज़रनेम या ईमेल भेजें:")
        elif data == "act_addfunds":
            admin_state[cid] = "addfunds"
            bot4.send_message(cid, "💰 फॉर्मेट में भेजें: `username amount`\nउदाहरण: `rahul12 100`", parse_mode="Markdown")

    @bot4.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.chat.id in admin_state and not m.text.startswith('/'))
    def b4_inputs(m):
        cid = m.chat.id
        action = admin_state.pop(cid, None)
        text = m.text.strip()

        if action == "unban":
            msg = bot4.send_message(cid, f"⏳ `{text}` को एक्टिव किया जा रहा है...")
            ok = panel.change_user_status(text, "active")
            res = f"✅ `{text}` को वेबसाइट पर **Active (Unban)** कर दिया गया!" if ok else f"❌ अनबैन विफल हुआ।"
            bot4.edit_message_text(res, cid, msg.message_id, reply_markup=get_b4_keyboard(), parse_mode="Markdown")
        elif action == "ban":
            msg = bot4.send_message(cid, f"⏳ `{text}` को बैन किया जा रहा है...")
            ok = panel.change_user_status(text, "deactivate")
            res = f"🚫 `{text}` को वेबसाइट पर **Deactive (Ban)** कर दिया गया!" if ok else f"❌ बैन विफल हुआ।"
            bot4.edit_message_text(res, cid, msg.message_id, reply_markup=get_b4_keyboard(), parse_mode="Markdown")
        elif action == "addfunds":
            parts = text.split()
            if len(parts) >= 2:
                user = parts[0]
                try:
                    amt = float(parts[1])
                    msg = bot4.send_message(cid, f"⏳ `{user}` के खाते में ₹{amt} जोड़े जा रहे हैं...")
                    ok = panel.add_funds(user, amt)
                    res = f"💰 ₹{amt} सफलतापूर्वक `{user}` के खाते में जोड़ दिए गए!" if ok else f"❌ बैलेंस अपडेट विफल हुआ।"
                    bot4.edit_message_text(res, cid, msg.message_id, reply_markup=get_b4_keyboard(), parse_mode="Markdown")
                except ValueError:
                    bot4.send_message(cid, "अमान्य राशि!", reply_markup=get_b4_keyboard())

# --- BOT 5: सिस्टम मॉनिटर व अलर्ट्स ---
if bot5:
    @bot5.message_handler(commands=['start', 'status'])
    def b5_start(m):
        if m.from_user.id != ADMIN_ID: return
        bot5.reply_to(m, f"🛡️ *PRANAV SMM गार्ड सिस्टम लाइव*\n\nPort: `{RENDER_PORT}`\nसमय: `{datetime.now()}`", parse_mode="Markdown")

# ==============================================================================
# 7. मल्टी-बॉट पोलर व कीप-अलाइव थ्रेड्स
# ==============================================================================
def run_single_bot(b_instance, token):
    if not b_instance or not token:
        return
    try:
        requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass
    while True:
        try:
            b_instance.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception:
            time.sleep(3)

def self_ping_loop():
    time.sleep(10)
    while True:
        try:
            requests.get("https://pranav-smm-master-0cgu.onrender.com/", timeout=10)
        except Exception:
            pass
        time.sleep(300)

if __name__ == "__main__":
    # पाँचों बॉट्स को अलग-अलग थ्रेड्स में एक साथ चालू करना
    if bot1 and BOT1_TOKEN: threading.Thread(target=run_single_bot, args=(bot1, BOT1_TOKEN), daemon=True).start()
    if bot2 and BOT2_TOKEN: threading.Thread(target=run_single_bot, args=(bot2, BOT2_TOKEN), daemon=True).start()
    if bot3 and BOT3_TOKEN: threading.Thread(target=run_single_bot, args=(bot3, BOT3_TOKEN), daemon=True).start()
    if bot4 and BOT4_TOKEN: threading.Thread(target=run_single_bot, args=(bot4, BOT4_TOKEN), daemon=True).start()
    if bot5 and BOT5_TOKEN: threading.Thread(target=run_single_bot, args=(bot5, BOT5_TOKEN), daemon=True).start()

    threading.Thread(target=self_ping_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
