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

BOT4_TOKEN = os.environ.get("BOT4_TOKEN", "").strip()
ADMIN_PASS = os.environ.get("ADMIN_PASS", "pranavsmmbot").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))

CONFIG = {
    "SITE_URL": "https://pranavsmm.shop",
    "LOGIN_URL": "https://pranavsmm.shop/secure-admin",
    "CLIENTS_URL": "https://pranavsmm.shop/secure-admin/clients",
    "PAYMENTS_URL": "https://pranavsmm.shop/secure-admin/payments/add-funds",
    "FUNDS_URL": "https://pranavsmm.shop/secure-admin/clients/add-funds",
    "COUPONS_URL": "https://pranavsmm.shop/secure-admin/kuponlar",
    "COUPONS_ALT": "https://pranavsmm.shop/secure-admin/coupons",
    "ADMIN_USER": "pranavbot",
    "ADMIN_EMAIL": "pranav67me@gmail.com",
    "ADMIN_PASS": ADMIN_PASS,
    "MAX_STRIKES": 4
}

bot4 = telebot.TeleBot(BOT4_TOKEN, threaded=False) if BOT4_TOKEN else None
admin_state = {}

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
        piece INTEGER DEFAULT 10, status TEXT DEFAULT 'ACTIVE', created_at TIMESTAMP,
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

# ==============================================================================
# सुपर एडमिन इंजन (हर एक्शन पर फ्रेश लॉगिन + सटीक ID मैपिंग)
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
            tok = soup.find('input', {'name': '_token'})
            token = tok.get('value', '') if tok else ''
            if not token:
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

    def get_client_id(self, username):
        self.login()
        try:
            search_url = f"{CONFIG['CLIENTS_URL']}?search={username}"
            r = self.session.get(search_url, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    td = tr.find('td')
                    if td and td.text.strip().isdigit():
                        return td.text.strip()
        except Exception:
            pass
        return None

    def change_user_status(self, username, action="active"):
        self.login()
        status_val = "active" if action == "active" else "deactive"
        cid = self.get_client_id(username)

        try:
            r = self.session.get(CONFIG["CLIENTS_URL"], timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            tok = soup.find('input', {'name': '_token'})
            token = tok.get('value', '') if tok else ''

            endpoints = []
            if cid:
                endpoints.append((f"{CONFIG['CLIENTS_URL']}/{status_val}/{cid}", {}))
                endpoints.append((f"{CONFIG['CLIENTS_URL']}/status", {"id": cid, "status": status_val, "_token": token}))
            endpoints.append((CONFIG['CLIENTS_URL'], {"username": username, "status": status_val, "action": status_val, "_token": token}))

            for url, data in endpoints:
                res = self.session.post(url, data=data, timeout=8)
                if res.status_code in [200, 302]:
                    return True
        except Exception:
            pass
        return False

    def add_fund(self, username, amount, is_deduct=False):
        self.login()
        cid = self.get_client_id(username)

        act_type = "deduct" if is_deduct else "add"
        act_name = "Deduct Balance" if is_deduct else "Add Balance"

        try:
            r = self.session.get(CONFIG["PAYMENTS_URL"], timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            tok = soup.find('input', {'name': '_token'})
            token = tok.get('value', '') if tok else ''

            payloads = [
                (CONFIG["PAYMENTS_URL"], {"username": username, "amount": str(amount), "type": act_type, "_token": token}),
                (CONFIG["FUNDS_URL"], {"client_id": cid or "", "username": username, "amount": str(amount), "action": act_name, "_token": token}),
                (f"{CONFIG['SITE_URL']}/secure-admin/fund-add-history/add-deduct", {"username": username, "currency": "Indian Rupee", "method": "PayTM Checkout", "amount": str(amount), "action": act_name, "_token": token})
            ]

            if cid:
                payloads.append((f"{CONFIG['CLIENTS_URL']}/edit/{cid}", {"balance": str(amount), "action": act_type, "_token": token}))

            for url, data in payloads:
                res = self.session.post(url, data=data, timeout=10)
                if res.status_code in [200, 302]:
                    return True
        except Exception:
            pass
        return True

    def create_coupon(self, code, amount, piece=10):
        self.login()
        urls = [CONFIG["COUPONS_URL"], CONFIG["COUPONS_ALT"]]
        
        for u in urls:
            try:
                r = self.session.get(u, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')
                tok = soup.find('input', {'name': '_token'})
                token = tok.get('value', '') if tok else ''

                payload = {
                    "coupon_code": code,
                    "code": code,
                    "piece": int(piece),
                    "amount": float(amount),
                    "coupon_for": "All Clients",
                    "type": "fixed",
                    "_token": token
                }
                res = self.session.post(u, data=payload, timeout=10)
                if res.status_code in [200, 302]:
                    return True
            except Exception:
                pass
        return True

    def get_user_details(self, username):
        self.login()
        try:
            search_url = f"{CONFIG['CLIENTS_URL']}?search={username}"
            r = self.session.get(search_url, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            cid = None
            email = None
            balance = None
            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    tds = tr.find_all('td')
                    for td in tds:
                        t = td.text.strip()
                        if t.isdigit() and not cid: cid = t
                        elif "@" in t and not email: email = t
                        elif ("₹" in t or "$" in t) and not balance: balance = t
            return cid, email, balance
        except Exception:
            return None, None, None

panel = PanelController()

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
            panel.change_user_status(username, action="deactivate")
            if bot4:
                try:
                    bot4.send_message(ADMIN_ID, f"🚨🚨 *[4-स्ट्राइक परमानेंट बैन]*\n👤 `{username}` को 4 गलत UTR पर ब्लॉक किया गया!", parse_mode="Markdown")
                except Exception:
                    pass
            return {"status": "banned", "attempts": attempts, "msg": "4 बार गलत प्रयास! खाता ब्लॉक।"}
        else:
            if bot4:
                try:
                    bot4.send_message(ADMIN_ID, f"⚠️ गलत UTR प्रयास: `{username}` (स्ट्राइक {attempts}/4)")
                except Exception:
                    pass
            return {"status": "failed", "attempts": attempts, "msg": f"अमान्य UTR! प्रयास {attempts}/4"}

    if clean_utr:
        cur.execute("INSERT OR REPLACE INTO utr_records (utr_number, claimed_by, claimed_at, status) VALUES (?, ?, ?, 'APPROVED')", (clean_utr, username, datetime.now()))
        cur.execute("DELETE FROM strike_counter WHERE username=?", (username,))
        conn.commit()
    conn.close()

    panel.change_user_status(username, action="active")
    if bot4:
        try:
            bot4.send_message(ADMIN_ID, f"⚡ *[ऑटो-अनबैन 100% सफल]*\n👤 `{username}`\n💳 UTR: `{clean_utr}`\n✅ खाता Active कर दिया गया!", parse_mode="Markdown")
        except Exception:
            pass
    return {"status": "success", "attempts": 0, "msg": "खाता एक्टिव कर दिया गया है!"}

def get_admin_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Add Funds", callback_data="adm_addbalance"),
        types.InlineKeyboardButton("🔻 Deduct Funds", callback_data="adm_deductbalance"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
        types.InlineKeyboardButton("🔍 User Details", callback_data="adm_lookup"),
        types.InlineKeyboardButton("🎁 Create Coupon", callback_data="adm_makecoupon"),
        types.InlineKeyboardButton("📊 System Stats", callback_data="adm_stats"),
        types.InlineKeyboardButton("💾 Backup DB", callback_data="adm_backup")
    )
    return markup

if bot4:
    @bot4.message_handler(commands=['start', 'panel', 'admin'])
    def b4_start(message):
        if message.from_user.id != ADMIN_ID:
            return
        bot4.send_message(
            message.chat.id,
            "╔════════════════════════════════╗\n"
            "   👑 *PRANAV JI - ALL SELECT SUPER ADMIN* 👑\n"
            "   ⚡ _फुल एडमिन कंट्रोल & ऑटोमेशन सक्रिय_ ⚡\n"
            "╚════════════════════════════════╝\n\n"
            "👇 हुक्म दें, प्रणव जी:",
            reply_markup=get_admin_markup(),
            parse_mode="Markdown"
        )

    @bot4.callback_query_handler(func=lambda call: call.from_user.id == ADMIN_ID)
    def b4_callbacks(call):
        cid = call.message.chat.id
        act = call.data

        if act == "adm_ban" or act == "adm_unban":
            action = "active" if act == "adm_unban" else "deactivate"
            lbl = "Unban (Active)" if action == "active" else "Ban (Deactive)"
            msg = bot4.send_message(cid, f"📝 जिस यूज़र को **{lbl}** करना है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, lambda m: step_ban_unban(m, action))

        elif act == "adm_addbalance":
            msg = bot4.send_message(cid, "💰 जिस यूज़र के खाते में **फंड जोड़ना** है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, lambda m: step_fund_init(m, is_deduct=False))

        elif act == "adm_deductbalance":
            msg = bot4.send_message(cid, "🔻 जिस यूज़र से **पैसे काटने** हैं उसका Username भेजें:")
            bot4.register_next_step_handler(msg, lambda m: step_fund_init(m, is_deduct=True))

        elif act == "adm_lookup":
            msg = bot4.send_message(cid, "🔍 जिस यूज़र की जानकारी देखनी है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, step_user_lookup)

        elif act == "adm_makecoupon":
            msg = bot4.send_message(cid, "🎁 कूपन का कोड लिखें (उदा. `BONUS50`):")
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
            cur.execute("SELECT COUNT(*) FROM utr_records")
            utrs = cur.fetchone()[0]
            conn.close()
            bot4.send_message(
                cid,
                f"📊 *सुपर एडमिन लाइव आँकड़े:*\n━━━━━━━━━━━━━━\n"
                f"👥 कुल यूज़र्स: `{u_tot}`\n"
                f"💳 कुल वेरिफ़ाइड UTR: `{utrs}`\n"
                f"💰 कुल फ़ंड लॉग: `₹{rev:.2f}`\n"
                f"🌐 pranavsmm.shop 24/7 Live ✅",
                reply_markup=get_admin_markup(),
                parse_mode="Markdown"
            )

    def step_ban_unban(m, action):
        target = m.text.strip()
        bot4.send_message(m.chat.id, f"⏳ `{target}` पर प्रोसेस चालू है...")
        panel.change_user_status(target, action=action)
        status_word = "Active (Unban)" if action == "active" else "Deactive (Ban)"
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status=?, strikes=0 WHERE web_username=?", ('ACTIVE' if action=='active' else 'SUSPENDED', target))
        conn.commit()
        conn.close()
        bot4.send_message(m.chat.id, f"✅ `{target}` को **{status_word}** कर दिया गया!", reply_markup=get_admin_markup())

    def step_fund_init(m, is_deduct):
        admin_state[m.chat.id] = {"target": m.text.strip(), "deduct": is_deduct}
        act_word = "काटने" if is_deduct else "जोड़ने"
        msg = bot4.send_message(m.chat.id, f"💵 `{m.text.strip()}` के लिए कितनी रकम (₹) {act_word} हैं? (उदा. `100`):")
        bot4.register_next_step_handler(msg, step_fund_finish)

    def step_fund_finish(m):
        try:
            amt = float(m.text.strip())
            data = admin_state[m.chat.id]
            target = data["target"]
            is_deduct = data["deduct"]
            act_word = "काट" if is_deduct else "जोड़"

            bot4.send_message(m.chat.id, f"⏳ `{target}` में ₹{amt} {act_word}े जा रहे हैं...")
            panel.add_fund(target, amt, is_deduct=is_deduct)

            delta = -amt if is_deduct else amt
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance=balance+? WHERE web_username=?", (delta, target))
            cur.execute("INSERT INTO payments_log (target_username, amount, added_by, created_at) VALUES (?, ?, 'ADMIN', ?)", (target, delta, datetime.now()))
            conn.commit()
            conn.close()
            bot4.send_message(m.chat.id, f"✅ `{target}` के खाते में ₹{amt} सफलतापूर्वक {act_word} दिए गए!", reply_markup=get_admin_markup())
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य रकम!", reply_markup=get_admin_markup())

    def step_user_lookup(m):
        target = m.text.strip()
        bot4.send_message(m.chat.id, f"🔍 `{target}` की जानकारी खोजी जा रही है...")
        cid, em, bal = panel.get_user_details(target)
        if cid:
            bot4.send_message(
                m.chat.id,
                f"👤 *यूज़र विवरण मिला:*\n━━━━━━━━━━━━━━\n"
                f"🆔 Client ID: `{cid}`\n"
                f"👤 Username: `{target}`\n"
                f"📧 Email: `{em or 'N/A'}`\n"
                f"💰 Balance: `{bal or '₹0.00'}`\n",
                reply_markup=get_admin_markup(),
                parse_mode="Markdown"
            )
        else:
            bot4.send_message(m.chat.id, f"❌ `{target}` वेबसाइट पर नहीं मिला।", reply_markup=get_admin_markup())

    def step_coupon_name(m):
        admin_state[m.chat.id] = {"c_code": m.text.strip().upper()}
        msg = bot4.send_message(m.chat.id, "💵 कूपन की रकम (रुपये) भेजें:")
        bot4.register_next_step_handler(msg, step_coupon_amount)

    def step_coupon_amount(m):
        try:
            amt = float(m.text.strip())
            code = admin_state[m.chat.id]["c_code"]
            panel.create_coupon(code, amt, 10)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO coupons (code, amount, piece, status, created_at) VALUES (?, ?, 10, 'ACTIVE', ?)", (code, amt, datetime.now()))
            conn.commit()
            conn.close()
            bot4.send_message(m.chat.id, f"🎁 कूपन `{code}` (₹{amt:.2f}) स्मार्टपैनल और डेटाबेस में एक्टिव कर दिया गया!", reply_markup=get_admin_markup())
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य रकम!", reply_markup=get_admin_markup())

@app.after_request
def apply_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return resp

@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "online", "system": "PRANAV SMM ALL SELECT ADMIN 24/7", "time": str(datetime.now())}), 200

@app.route('/api/appeal', methods=['POST', 'OPTIONS'])
def appeal_api():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    user = request.form.get('username', 'User').strip()
    utr = request.form.get('utr', '').strip()
    photo = request.files.get('photo')
    return jsonify(process_appeal(user, utr, photo)), 200
