import os
import re
import time
import sqlite3
import threading
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
import telebot
from telebot import types

app = Flask(__name__)
RENDER_PORT = int(os.environ.get("PORT", 10000))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://pranav-smm-bot-2.onrender.com").strip()

CONFIG = {
    "SITE_URL": "https://pranavsmm.shop",
    "LOGIN_URL": "https://pranavsmm.shop/secure-admin",
    "CLIENTS_URL": "https://pranavsmm.shop/secure-admin/clients",
    "ADMIN_USER": "pranavbot",
    "ADMIN_EMAIL": "pranav67me@gmail.com",
    "ADMIN_PASS": os.environ.get("ADMIN_PASS", "pranavsmmbot").strip(),
    "ADMIN_TELEGRAM_ID": int(os.environ.get("ADMIN_ID", "8585055903")),
    "MAX_STRIKES": 4
}

def get_db():
    conn = sqlite3.connect("pranav_network.db", timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, username TEXT, web_username TEXT,
        web_name TEXT, web_email TEXT, web_phone TEXT, web_password TEXT,
        balance REAL DEFAULT 0.0, status TEXT DEFAULT 'ACTIVE',
        suspended_at TIMESTAMP, strikes INTEGER DEFAULT 0, last_low_alert TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, amount REAL,
        piece INTEGER DEFAULT 1, status TEXT DEFAULT 'ACTIVE', created_at TIMESTAMP,
        used_by INTEGER, used_at TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, target_username TEXT, amount REAL,
        added_by TEXT, created_at TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS utr_records (
        utr_number TEXT PRIMARY KEY, claimed_by TEXT, claimed_at TIMESTAMP, status TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS strike_counter (
        username TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, last_failed_at TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

class EnterpriseBridge:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }
        self.last_login = 0

    def get_token(self, url):
        try:
            r = self.session.get(url, headers={"User-Agent": self.headers["User-Agent"]}, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            inp = soup.find('input', {'name': '_token'})
            if inp and inp.get('value'): return inp.get('value')
            meta = soup.find('meta', {'name': 'csrf-token'})
            if meta and meta.get('content'): return meta.get('content')
        except Exception:
            pass
        return ''

    def login_admin(self):
        if time.time() - self.last_login < 300:
            return True
        url = CONFIG["LOGIN_URL"]
        csrf = self.get_token(url)
        creds = [
            {"username": CONFIG["ADMIN_USER"], "password": CONFIG["ADMIN_PASS"], "_token": csrf},
            {"email": CONFIG["ADMIN_EMAIL"], "password": CONFIG["ADMIN_PASS"], "_token": csrf}
        ]
        for p in creds:
            try:
                res = self.session.post(url, data=p, headers=self.headers, timeout=12, allow_redirects=True)
                if "logout" in res.text.lower() or "secure-admin/logout" in res.text.lower() or res.status_code == 200:
                    self.last_login = time.time()
                    return True
            except Exception:
                pass
        return False

    def find_client(self, username):
        if not self.login_admin():
            return None, "एडमिन लॉगिन नहीं हो सका।"
        url = CONFIG["CLIENTS_URL"]
        try:
            r = self.session.get(f"{url}?search={username}", headers=self.headers, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')
            for tr in soup.find_all('tr'):
                text = tr.text.lower()
                if username.lower() in text:
                    for td in tr.find_all('td'):
                        val = td.text.strip()
                        if val.isdigit():
                            return val, None
                    for a in tr.find_all('a', href=True):
                        match = re.search(r'/(?:edit|clients|view)/(\d+)', a['href'])
                        if match:
                            return match.group(1), None
            return None, "यूज़र पैनल पर नहीं मिला।"
        except Exception as e:
            return None, str(e)

    def trigger_status(self, username, action="deactivate"):
        if not self.login_admin():
            return False, "एडमिन लॉगिन नहीं हो सका।"
        cid, err = self.find_client(username)
        url = CONFIG["CLIENTS_URL"]
        csrf = self.get_token(url)
        status_num = "0" if action == "deactivate" else "1"
        status_word = "deactive" if action == "deactivate" else "active"

        endpoints = []
        if cid:
            endpoints.extend([
                (f"{url}/status/{cid}", {"status": status_num, "id": cid, "_token": csrf}),
                (f"{url}/status", {"status": status_num, "id": cid, "_token": csrf}),
                (f"{url}/ajax_status", {"id": cid, "status": status_num, "_token": csrf}),
                (f"{url}/action/{cid}", {"action": status_word, "id": cid, "_token": csrf})
            ])
        endpoints.append((f"{url}/status", {"username": username, "status": status_word, "_token": csrf}))

        for ep, payload in endpoints:
            try:
                res = self.session.post(ep, data=payload, headers=self.headers, timeout=10)
                if res.status_code in [200, 302]:
                    return True, f"यूज़र को {status_word.upper()} कर दिया गया।"
            except Exception:
                pass
        return False, "स्टेटस अपडेट करने में असमर्थ।"

    def add_fund(self, username, amount):
        if not self.login_admin():
            return False, "एडमिन लॉगिन नहीं हो सका।"
        cid, _ = self.find_client(username)
        csrf = self.get_token(CONFIG["CLIENTS_URL"])

        fund_endpoints = [
            f"{CONFIG['SITE_URL']}/secure-admin/clients/add-funds",
            f"{CONFIG['SITE_URL']}/secure-admin/fund-add-history/add-deduct",
            f"{CONFIG['SITE_URL']}/secure-admin/payments/add-funds",
            f"{CONFIG['SITE_URL']}/secure-admin/clients/edit/{cid}" if cid else None,
            CONFIG["CLIENTS_URL"]
        ]

        payloads = [
            {"username": username, "amount": str(amount), "type": "add", "payment_method": "Manual", "_token": csrf},
            {"client_id": cid or "", "username": username, "amount": str(amount), "action": "Add Balance", "_token": csrf},
            {"id": cid or "", "amount": str(amount), "action": "add", "_token": csrf}
        ]

        for ep in fund_endpoints:
            if not ep: continue
            for pay in payloads:
                try:
                    res = self.session.post(ep, data=pay, headers=self.headers, timeout=10)
                    if res.status_code in [200, 302] and ("success" in res.text.lower() or "added" in res.text.lower() or res.status_code == 302):
                        return True, f"₹{amount} खाते में जुड़ गए।"
                except Exception:
                    pass
        return True, f"₹{amount} फंड रिक्वेस्ट भेजी गई।"

bridge = EnterpriseBridge()

BOT4_TOKEN = os.environ.get("BOT4_TOKEN", "").strip()
bot4 = telebot.TeleBot(BOT4_TOKEN, threaded=False) if BOT4_TOKEN else None

admin_state = {}

def get_admin_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Add Funds", callback_data="adm_addbalance"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
        types.InlineKeyboardButton("🎁 Create Coupon", callback_data="adm_makecoupon"),
        types.InlineKeyboardButton("📊 System Stats", callback_data="adm_stats"),
        types.InlineKeyboardButton("💾 Backup DB", callback_data="adm_backup")
    )
    return markup

if bot4:
    @bot4.message_handler(commands=['start', 'panel'])
    def b4_start(message):
        if message.from_user.id != CONFIG["ADMIN_TELEGRAM_ID"]:
            return
        bot4.send_message(
            message.chat.id,
            "👑 *PRANAV JI SUPREME COMMANDER*\n\n⚡ एडमिन कंट्रोल पैनल तैयार है। चुनें:",
            reply_markup=get_admin_markup(),
            parse_mode="Markdown"
        )

    @bot4.callback_query_handler(func=lambda call: call.from_user.id == CONFIG["ADMIN_TELEGRAM_ID"])
    def b4_callbacks(call):
        cid = call.message.chat.id
        act = call.data

        if act == "adm_ban" or act == "adm_unban":
            action = "activate" if act == "adm_unban" else "deactivate"
            lbl = "Unban (Active)" if action == "activate" else "Ban (Deactive)"
            msg = bot4.send_message(cid, f"📝 जिस यूज़र को **{lbl}** करना है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, lambda m: step_ban_unban(m, action))

        elif act == "adm_addbalance":
            msg = bot4.send_message(cid, "💰 जिस यूज़र के खाते में फंड जोड़ना है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, step_fund_user)

        elif act == "adm_makecoupon":
            msg = bot4.send_message(cid, "🎁 कूपन कोड लिखें (उदा. `FEST50`):")
            bot4.register_next_step_handler(msg, step_coupon_name)

        elif act == "adm_backup":
            if os.path.exists("pranav_network.db"):
                with open("pranav_network.db", "rb") as doc:
                    bot4.send_document(cid, doc, caption="💾 Database Backup")
            else:
                bot4.send_message(cid, "❌ डेटाबेस फ़ाइल नहीं मिली।")

        elif act == "adm_stats":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            u_tot = cur.fetchone()[0]
            cur.execute("SELECT SUM(amount) FROM payments_log")
            rev = cur.fetchone()[0] or 0.0
            conn.close()
            bot4.send_message(cid, f"📊 *सिस्टम स्टैट्स:*\n👥 कुल यूज़र्स: `{u_tot}`\n💰 कुल फंड लॉग: `₹{rev:.2f}`\n🌐 pranavsmm.shop Live ✅", reply_markup=get_admin_markup(), parse_mode="Markdown")

    def step_ban_unban(m, action):
        target = m.text.strip()
        bot4.send_message(m.chat.id, f"⏳ `{target}` पर प्रोसेस चालू है...")
        ok, res_msg = bridge.trigger_status(target, action=action)
        status_word = "Active (Unban)" if action == "activate" else "Deactive (Ban)"
        if ok:
            conn = get_db()
            cur = conn.cursor()
            st_val = 'ACTIVE' if action == 'activate' else 'SUSPENDED'
            cur.execute("UPDATE users SET status=?, strikes=0 WHERE web_username=?", (st_val, target))
            conn.commit()
            conn.close()
            bot4.send_message(m.chat.id, f"✅ `{target}` को {status_word} कर दिया गया!\n({res_msg})", reply_markup=get_admin_markup())
        else:
            bot4.send_message(m.chat.id, f"❌ एरर: {res_msg}", reply_markup=get_admin_markup())

    def step_fund_user(m):
        admin_state[m.chat.id] = {"target": m.text.strip()}
        msg = bot4.send_message(m.chat.id, f"💵 `{m.text.strip()}` में कितनी रकम जोड़नी है? (संख्या भेजें, उदा. `100`):")
        bot4.register_next_step_handler(msg, step_fund_amount)

    def step_fund_amount(m):
        try:
            amt = float(m.text.strip())
            target = admin_state[m.chat.id]["target"]
            bot4.send_message(m.chat.id, f"⏳ `{target}` में ₹{amt} जोड़ा जा रहा है...")
            ok, msg = bridge.add_fund(target, amt)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance=balance+? WHERE web_username=?", (amt, target))
            cur.execute("INSERT INTO payments_log (target_username, amount, added_by, created_at) VALUES (?, ?, 'ADMIN', ?)", (target, amt, datetime.now()))
            conn.commit()
            conn.close()
            bot4.send_message(m.chat.id, f"✅ `{target}` के खाते में ₹{amt} अपडेट कर दिए गए!", reply_markup=get_admin_markup())
        except Exception as e:
            bot4.send_message(m.chat.id, f"❌ अमान्य इनपुट या एरर: {str(e)}", reply_markup=get_admin_markup())

    def step_coupon_name(m):
        admin_state[m.chat.id] = {"c_code": m.text.strip().upper()}
        msg = bot4.send_message(m.chat.id, "💵 कूपन की रकम (रुपये) भेजें:")
        bot4.register_next_step_handler(msg, step_coupon_amount)

    def step_coupon_amount(m):
        try:
            amt = float(m.text.strip())
            code = admin_state[m.chat.id]["c_code"]
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO coupons (code, amount, piece, status, created_at) VALUES (?, ?, 10, 'ACTIVE', ?)", (code, amt, datetime.now()))
            conn.commit()
            conn.close()
            bot4.send_message(m.chat.id, f"🎁 कूपन `{code}` (₹{amt:.2f}) डेटाबेस में एक्टिव कर दिया गया!", reply_markup=get_admin_markup())
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य रकम!", reply_markup=get_admin_markup())

def process_appeal(username, utr_code, photo_file=None):
    clean_utr = utr_code.strip().replace(" ", "").upper()
    conn = get_db()
    cur = conn.cursor()
    is_valid = bool(re.match(r'^[A-Z0-9]{10,24}$', clean_utr))

    cur.execute("SELECT claimed_by FROM utr_records WHERE utr_number=?", (clean_utr,))
    existing = cur.fetchone()

    if (existing and existing[0].lower() != username.lower()) or (not is_valid and not photo_file):
        cur.execute("SELECT attempts FROM strike_counter WHERE username=?", (username,))
        row = cur.fetchone()
        attempts = (row[0] + 1) if row else 1
        cur.execute("INSERT OR REPLACE INTO strike_counter (username, attempts, last_failed_at) VALUES (?, ?, ?)", (username, attempts, datetime.now()))
        conn.commit()
        conn.close()

        if attempts >= CONFIG["MAX_STRIKES"]:
            bridge.trigger_status(username, action="deactivate")
            if bot4:
                try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"🚨🚨 *[4-स्ट्राइक परमानेंट बैन]*\n👤 `{username}` को ब्लॉक कर दिया गया!")
                except Exception: pass
            return {"status": "banned", "attempts": attempts, "msg": "4 बार गलत प्रयास! खाता सस्पेंड।"}
        else:
            if bot4:
                try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"⚠️ गलत UTR प्रयास: `{username}` (स्ट्राइक {attempts}/4)")
                except Exception: pass
            return {"status": "failed", "attempts": attempts, "msg": f"अमान्य UTR! प्रयास {attempts}/4"}

    if clean_utr:
        cur.execute("INSERT OR REPLACE INTO utr_records (utr_number, claimed_by, claimed_at, status) VALUES (?, ?, ?, 'APPROVED')", (clean_utr, username, datetime.now()))
        cur.execute("DELETE FROM strike_counter WHERE username=?", (username,))
        conn.commit()
    conn.close()

    bridge.trigger_status(username, action="activate")
    if bot4:
        try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"⚡ *[ऑटो-अनबैन सफल]*\n👤 `{username}`\n💳 UTR: `{clean_utr}`\n✅ खाता Active कर दिया गया!")
        except Exception: pass
    return {"status": "success", "attempts": 0, "msg": "खाता एक्टिव कर दिया गया है!"}

@app.after_request
def apply_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return resp

@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "online", "system": "PRANAV SMM MASTER 24/7", "time": str(datetime.now())}), 200

@app.route('/api/appeal', methods=['POST', 'OPTIONS'])
def appeal_api():
    if request.method == 'OPTIONS': return jsonify({"status": "ok"}), 200
    user = request.form.get('username', 'User').strip()
    utr = request.form.get('utr', '').strip()
    photo = request.files.get('photo')
    return jsonify(process_appeal(user, utr, photo)), 200

def self_ping_loop():
    time.sleep(30)
    while True:
        try:
            requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=8)
            if RENDER_EXTERNAL_URL: requests.get(RENDER_EXTERNAL_URL.rstrip('/') + '/', timeout=10)
        except Exception:
            pass
        time.sleep(600)
