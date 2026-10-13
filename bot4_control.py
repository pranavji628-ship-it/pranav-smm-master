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
# 1. कॉन्फ़िगरेशन (RENDER ENV VARS)
# ==============================================================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
BOT_TOKEN = os.environ.get("BOT4_TOKEN", os.environ.get("BOT6_TOKEN", ""))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "pranav67me@gmail.com")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "pranavsmmsupport@gmail.com")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")

SITE_URL = "https://pranavsmm.shop"
ADMIN_LOGIN_URL = f"{SITE_URL}/secure-admin"

DB_PATH = "bot4_database.db"

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=True) if BOT_TOKEN else None
admin_state = {}

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# ==============================================================================
# 2. डेटाबेस (स्कैन किए गए रूट्स और OTP)
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
    CREATE TABLE IF NOT EXISTS scanned_menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        url TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 3. फुल ऑटोमैटिक एडमिन क्रॉलर और रोबोट
# ==============================================================================
class DynamicAdminCrawler:
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
        except Exception as e:
            print(f"[LOGIN FAIL] {e}")
        return False

    def scan_and_save_all_buttons(self):
        """एडमिन पैनल में लॉगिन करके सभी मौजूद लिंक्स को स्कैन करता है"""
        if not self.login():
            return {}

        try:
            r = self.session.get(ADMIN_LOGIN_URL, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            found = {}
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip()
                # केवल एडमिन पैनल के वैध नेविगेशन मेन्यू उठाना
                if "secure-admin" in href and text and "logout" not in href.lower():
                    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip()
                    if clean_name and len(clean_name) <= 20:
                        full_url = href if href.startswith("http") else f"{SITE_URL}{href}"
                        found[clean_name] = full_url

            self.routes = found

            conn = get_db()
            cur = conn.cursor()
            for name, url in found.items():
                cur.execute("INSERT OR REPLACE INTO scanned_menu (name, url) VALUES (?, ?)", (name, url))
            conn.commit()
            conn.close()

            return found
        except Exception as e:
            print(f"[SCAN FAIL] {e}")
            return self.get_stored_menu()

    def get_stored_menu(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, url FROM scanned_menu")
        rows = cur.fetchall()
        conn.close()
        return {r["name"]: r["url"] for r in rows}

    def fetch_page_content(self, url):
        self.login()
        try:
            r = self.session.get(url, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            # अगर पेज में टेबल है तो डेटा की पहली 5 लाइनें निकालें
            table_rows = []
            for tr in soup.find_all('tr')[:6]:
                tds = [td.text.strip() for td in tr.find_all(['td', 'th'])]
                if tds:
                    table_rows.append(" | ".join(tds[:4]))

            if table_rows:
                return "\n".join(table_rows)

            # अगर टेबल नहीं है तो हेडिंग्स और टेक्स्ट निकालें
            headings = [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3', 'h4'])[:4]]
            return "\n".join(headings) if headings else "पेज खुला है पर कोई डेटा प्रदर्शित नहीं है।"
        except Exception as e:
            return f"त्रुटि: {e}"

    def change_user_status(self, username, action="active"):
        self.login()
        status_val = "active" if action == "active" else "deactive"
        clients_url = self.routes.get("Clients", f"{ADMIN_LOGIN_URL}/clients")

        try:
            r = self.session.get(f"{clients_url}?search={username}", timeout=12)
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
                endpoints.append((f"{clients_url}/{status_val}/{client_id}", {}))
                endpoints.append((f"{clients_url}/status", {"id": client_id, "status": status_val, "_token": token}))
            endpoints.append((clients_url, {"username": username, "status": status_val, "action": status_val, "_token": token}))

            for url, data in endpoints:
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    return True
        except Exception:
            pass
        return False

    def add_funds(self, username, amount):
        self.login()
        clients_url = self.routes.get("Clients", f"{ADMIN_LOGIN_URL}/clients")
        payments_url = self.routes.get("Payments", f"{ADMIN_LOGIN_URL}/payments")

        try:
            r = self.session.get(f"{clients_url}?search={username}", timeout=10)
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
                (f"{clients_url}/add-funds", {"user_id": client_id or username, "amount": amount, "_token": token}),
                (f"{payments_url}/add", {"username": username, "amount": amount, "method": "Manual", "_token": token}),
                (f"{clients_url}/edit/{client_id}" if client_id else "", {"balance": amount, "_token": token, "action": "add_funds"})
            ]

            for url, data in endpoints:
                if not url: continue
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    return True
        except Exception:
            pass
        return False

crawler = DynamicAdminCrawler()

# ==============================================================================
# 4. GMAIL OTP सिस्टम (IPv4 BINDING)
# ==============================================================================
def send_official_email_otp(target_email, username, otp_code):
    if not SENDER_EMAIL or not GMAIL_APP_PASS:
        return False, "Gmail credentials missing"

    orig_getaddrinfo = socket.getaddrinfo
    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        socket.getaddrinfo = ipv4_getaddrinfo
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} - Pranav SMM Account Recovery Code"
        msg["From"] = f"Pranav SMM Support <{SENDER_EMAIL}>"
        msg["To"] = target_email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 16px; background: #ffffff;">
            <h2 style="color: #6a1b9a; text-align: center;">PRANAV SMM PANEL</h2>
            <p style="text-align: center; color: #64748b; font-size: 13px;">Security & Account Recovery</p>
            <div style="background: #faf5ff; border: 2px dashed #7928ca; border-radius: 12px; padding: 18px; text-align: center; margin: 25px 0;">
                <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #6a1b9a;">{otp_code}</span>
            </div>
            <p style="color: #334155; font-size: 14px;">Hello <b>{username}</b>,<br>Use this OTP code to verify and unban your account. Valid for 10 minutes.</p>
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
        return True, "Sent"
    except Exception as e:
        return False, str(e)
    finally:
        socket.getaddrinfo = orig_getaddrinfo

# ==============================================================================
# 5. FLASK API ENDPOINTS
# ==============================================================================
@app.route('/')
def home():
    routes = crawler.get_stored_menu()
    return jsonify({
        "status": "online",
        "service": "Pranav SMM Dynamic Crawler Engine",
        "port": RENDER_PORT,
        "scanned_buttons_count": len(routes)
    }), 200

@app.route('/api/check-google-user', methods=['POST', 'OPTIONS'])
def check_google_user_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    email = request.form.get("email", "").strip().lower()
    if not email:
        return jsonify({"suspended": False}), 200

    clients_url = crawler.routes.get("Clients", f"{ADMIN_LOGIN_URL}/clients")
    try:
        crawler.login()
        r = crawler.session.get(f"{clients_url}?search={email}", timeout=10)
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
        return jsonify({"status": "error", "msg": "Valid email required!"}), 400

    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now() + timedelta(minutes=10)

    sent_ok, err_msg = send_official_email_otp(email, username, otp)
    if not sent_ok:
        return jsonify({"status": "error", "msg": f"OTP Failed: {err_msg}"}), 500

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO otp_verification 
        (username, email, utr, otp_code, attempts, expires_at, created_at) 
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (email, email, utr, otp, expires_at, datetime.now()))
    conn.commit()
    conn.close()

    if bot and BOT_TOKEN:
        bot.send_message(
            ADMIN_ID,
            f"📧 *[OTP DISPATCHED]*\nUser: `{username}`\nGmail: `{email}`\nUTR: `{utr}`\nOTP: `{otp}`",
            parse_mode="Markdown"
        )

    return jsonify({"status": "otp_sent", "msg": f"OTP sent to {email}"}), 200

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
        return jsonify({"status": "error", "msg": "Invalid OTP code!"}), 400

    target_email = row["email"]
    target_utr = row["utr"]
    cur.execute("DELETE FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    conn.commit()
    conn.close()

    crawler.change_user_status(target_email, "active")
    if bot and BOT_TOKEN:
        bot.send_message(ADMIN_ID, f"⚡ *[VERIFIED UNBAN]*\nUser: `{target_email}`\nUTR: `{target_utr}`", parse_mode="Markdown")

    return jsonify({"status": "success", "msg": "OTP verified! Account activated."}), 200

# ==============================================================================
# 6. टेलीग्राम बोट (डायनामिक बटन्स क्रिएशन)
# ==============================================================================
def generate_dynamic_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    # 1. कोर ऑपरेशन्स
    markup.add(
        types.InlineKeyboardButton("🔄 फुल एडमिन री-स्कैन", callback_data="btn_rescan"),
        types.InlineKeyboardButton("💰 ऐड फंड्स", callback_data="btn_addfunds")
    )
    markup.add(
        types.InlineKeyboardButton("✅ यूज़र Unban", callback_data="btn_unban"),
        types.InlineKeyboardButton("🚫 यूज़र Ban", callback_data="btn_ban")
    )

    # 2. बोट द्वारा खुद स्कैन किए गए डायनामिक बटन्स
    routes = crawler.get_stored_menu()
    if routes:
        dynamic_buttons = []
        for name in list(routes.keys())[:12]:
            dynamic_buttons.append(types.InlineKeyboardButton(f"📂 {name}", callback_data=f"page_{name}"))
        markup.add(*dynamic_buttons)

    return markup

if bot:
    @bot.message_handler(commands=['start', 'scan', 'admin'])
    def handle_start(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "⛔ अनधिकृत एक्सेस!")
            return

        msg = bot.send_message(message.chat.id, "🤖 *प्रणव जी, बोट एडमिन वेबसाइट को लाइव स्कैन कर रहा है...*", parse_mode="Markdown")
        routes = crawler.scan_and_save_all_buttons()
        count = len(routes)

        bot.edit_message_text(
            f"👑 *PRANAV SMM ऑटोमैटिक एडमिन हब*\n\n"
            f"✅ लॉगिन: सफल\n"
            f"📡 स्कैन किए गए सेक्शंस/पेज: `{count}`\n\n"
            f"बोट ने वेबसाइट से सारे बटन खुद बना लिए हैं। नीचे से सेलेक्ट करें:",
            message.chat.id,
            msg.message_id,
            reply_markup=generate_dynamic_keyboard(),
            parse_mode="Markdown"
        )

    @bot.callback_query_handler(func=lambda c: True)
    def handle_callbacks(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "अनुमति नहीं है!", show_alert=True)
            return

        cid = call.message.chat.id
        data = call.data

        if data == "btn_rescan":
            msg = bot.send_message(cid, "🔄 पूरे एडमिन पैनल को दोबारा खंगाला जा रहा है...")
            routes = crawler.scan_and_save_all_buttons()
            bot.edit_message_text(f"✅ री-स्कैन पूरा! `{len(routes)}` मेन्यू बटन लाइव जुड़े।", cid, msg.message_id, reply_markup=generate_dynamic_keyboard(), parse_mode="Markdown")

        elif data == "btn_unban":
            admin_state[cid] = "unban"
            bot.send_message(cid, "✅ Unban करने के लिए यूज़रनेम या ईमेल भेजें:")

        elif data == "btn_ban":
            admin_state[cid] = "ban"
            bot.send_message(cid, "🚫 Ban करने के लिए यूज़रनेम या ईमेल भेजें:")

        elif data == "btn_addfunds":
            admin_state[cid] = "addfunds"
            bot.send_message(cid, "💰 फॉर्मेट में भेजें: `username amount`\nउदाहरण: `rahul12 100`", parse_mode="Markdown")

        elif data.startswith("page_"):
            page_name = data.replace("page_", "")
            routes = crawler.get_stored_menu()
            target_url = routes.get(page_name)

            if target_url:
                msg = bot.send_message(cid, f"⏳ `{page_name}` पेज से लाइव डेटा निकाला जा रहा है...")
                content = crawler.fetch_page_content(target_url)
                bot.edit_message_text(f"📂 *[{page_name.upper()} का डेटा]*\nURL: `{target_url}`\n\n{content}", cid, msg.message_id, reply_markup=generate_dynamic_keyboard(), parse_mode="Markdown")

    @bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.chat.id in admin_state and not m.text.startswith('/'))
    def handle_inputs(message):
        cid = message.chat.id
        action = admin_state.pop(cid, None)
        text = message.text.strip()

        if action == "unban":
            msg = bot.send_message(cid, f"⏳ `{text}` को एक्टिव किया जा रहा है...")
            ok = crawler.change_user_status(text, "active")
            res = f"✅ `{text}` को वेबसाइट पर **Active (Unban)** कर दिया गया!" if ok else f"❌ अनबैन विफल हुआ।"
            bot.edit_message_text(res, cid, msg.message_id, reply_markup=generate_dynamic_keyboard(), parse_mode="Markdown")

        elif action == "ban":
            msg = bot.send_message(cid, f"⏳ `{text}` को बैन किया जा रहा है...")
            ok = crawler.change_user_status(text, "deactivate")
            res = f"🚫 `{text}` को वेबसाइट पर **Deactive (Ban)** कर दिया गया!" if ok else f"❌ बैन विफल हुआ।"
            bot.edit_message_text(res, cid, msg.message_id, reply_markup=generate_dynamic_keyboard(), parse_mode="Markdown")

        elif action == "addfunds":
            parts = text.split()
            if len(parts) >= 2:
                user = parts[0]
                try:
                    amt = float(parts[1])
                    msg = bot.send_message(cid, f"⏳ `{user}` के खाते में ₹{amt} जोड़े जा रहे हैं...")
                    ok = crawler.add_funds(user, amt)
                    res = f"💰 ₹{amt} सफलतापूर्वक `{user}` के खाते में जोड़ दिए गए!" if ok else f"❌ बैलेंस अपडेट नहीं हो सका।"
                    bot.edit_message_text(res, cid, msg.message_id, reply_markup=generate_dynamic_keyboard(), parse_mode="Markdown")
                except ValueError:
                    bot.send_message(cid, "अमान्य राशि!", reply_markup=generate_dynamic_keyboard())
            else:
                bot.send_message(cid, "फॉर्मेट गलत है! उपयोग करें: `username amount`", reply_markup=generate_dynamic_keyboard())

# ==============================================================================
# 7. सर्वर व कीप-अलाइव
# ==============================================================================
def self_ping_loop():
    time.sleep(10)
    while True:
        try:
            requests.get("https://pranav-smm-master-0cgu.onrender.com/", timeout=10)
        except Exception:
            pass
        time.sleep(300)

def start_bot_polling():
    if not bot or not BOT_TOKEN: return
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
    threading.Thread(target=start_bot_polling, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
