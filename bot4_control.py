import os
import re
import time
import sqlite3
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
    "SIGNUP_URL": "https://pranavsmm.shop/signup",
    "CLIENTS_URL": "https://pranavsmm.shop/secure-admin/clients",
    "FUNDS_URL": "https://pranavsmm.shop/secure-admin/fund-add-history",
    "COUPONS_URL": "https://pranavsmm.shop/secure-admin/kuponlar",
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
    cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, issue TEXT,
        status TEXT DEFAULT 'OPEN', created_at TIMESTAMP
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
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}
        self.last_login = 0

    def get_token(self, url):
        try:
            r = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            inp = soup.find('input', {'name': '_token'})
            if inp: return inp.get('value', '')
            meta = soup.find('meta', {'name': 'csrf-token'})
            if meta: return meta.get('content', '')
        except Exception:
            pass
        return ''

    def login_admin(self):
        if time.time() - self.last_login < 400: return True
        url = CONFIG["LOGIN_URL"]
        csrf = self.get_token(url)
        for p in [{"username": CONFIG["ADMIN_USER"], "password": CONFIG["ADMIN_PASS"], "_token": csrf},
                  {"email": CONFIG["ADMIN_EMAIL"], "password": CONFIG["ADMIN_PASS"], "_token": csrf}]:
            try:
                res = self.session.post(url, data=p, headers=self.headers, timeout=10)
                if "logout" in res.text.lower() or res.status_code == 302:
                    self.last_login = time.time()
                    return True
            except Exception:
                pass
        return False

    def trigger_status(self, username, action="deactivate"):
        if not self.login_admin(): return False, "एडमिन लॉगिन फ़ेल"
        url = CONFIG["CLIENTS_URL"]
        status_val = "deactive" if action == "deactivate" else "active"
        cid = None
        try:
            r = self.session.get(f"{url}?search={username}", headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for tr in soup.find_all('tr'):
                if username.lower() in tr.text.lower():
                    td = tr.find('td')
                    if td and td.text.strip().isdigit():
                        cid = td.text.strip()
                        break
        except Exception:
            pass

        csrf = self.get_token(url)
        payload = {"username": username, "id": cid, "status": status_val, "action": status_val, "_token": csrf}
        endpoints = [f"{url}/status", f"{url}/{status_val}/{cid}" if cid else None, url]
        for ep in endpoints:
            if not ep: continue
            try:
                res = self.session.post(ep, data=payload, headers=self.headers, timeout=8)
                if res.status_code in [200, 302]: return True, f"Status: {status_val.upper()}"
            except Exception:
                pass
        return False, "वेबसाइट स्टेटस अपडेट नहीं हो सका।"

    def add_fund(self, username, amount):
        if not self.login_admin(): return False, "एडमिन लॉगिन फ़ेल"
        url = CONFIG["FUNDS_URL"]
        csrf = self.get_token(url)
        payload = {"username": username, "currency": "Indian Rupee", "method": "PayTM Checkout", "amount": str(amount), "action": "Add Balance", "_token": csrf}
        for ep in [f"{url}/add-deduct", url]:
            try:
                res = self.session.post(ep, data=payload, headers=self.headers, timeout=10)
                if res.status_code in [200, 302]: return True, f"₹{amount} खाते में जुड़ गए!"
            except Exception:
                pass
        return False, "फंड रिक्वेस्ट रिजेक्ट हुई।"

    def create_coupon(self, code, amount, piece=1):
        if not self.login_admin(): return False, "एडमिन लॉगिन फ़ेल"
        url = CONFIG["COUPONS_URL"]
        csrf = self.get_token(url)
        payload = {"coupon_code": code, "code": code, "piece": int(piece), "amount": float(amount), "coupon_for": "All Clients", "_token": csrf}
        for ep in [f"{url}/new", url, f"{url}/create"]:
            try:
                res = self.session.post(ep, data=payload, headers=self.headers, timeout=10)
                if res.status_code in [200, 302]: return True, f"कूपन '{code}' लाइव बन गया!"
            except Exception:
                pass
        return False, "कूपन नहीं बन सका।"

    def register_user(self, username, name, email, phone, password):
        s = requests.Session()
        s.headers.update(self.headers)
        try:
            csrf = self.get_token(CONFIG["SIGNUP_URL"])
            payload = {"username": username, "name": name, "email": email, "telephone": phone, "password": password, "password_again": password, "terms": "on", "_token": csrf}
            res = s.post(CONFIG["SIGNUP_URL"], data=payload, timeout=10, allow_redirects=True)
            if "logout" in res.text.lower() or "dashboard" in res.url.lower(): return True, "सफल"
            return False, "साइनअप फॉर्म सबमिट नहीं हो सका।"
        except Exception as e:
            return False, str(e)

bridge = EnterpriseBridge()

BOT4_TOKEN = os.environ.get("BOT4_TOKEN", "").strip()
bot4 = telebot.TeleBot(BOT4_TOKEN, threaded=False) if BOT4_TOKEN else None

admin_state = {}

def get_admin_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Add Funds", callback_data="adm_addbalance"),
        types.InlineKeyboardButton("🎁 Create Coupon", callback_data="adm_makecoupon"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
        types.InlineKeyboardButton("📋 View Coupons", callback_data="adm_viewcoupons"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("💾 Backup DB", callback_data="adm_backup"),
        types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats")
    )
    return markup

if bot4:
    try:
        bot4.set_my_name("PRANAV SMM")
        bot4.set_my_short_description("Official Control Bot | pranavsmm.shop")
    except Exception:
        pass

    @bot4.message_handler(commands=['start', 'panel'])
    def b4_start(message):
        if message.from_user.id != CONFIG["ADMIN_TELEGRAM_ID"]: return
        bot4.send_message(
            message.chat.id,
            "╔════════════════════════════════╗\n"
            "   👑 *PRANAV JI SUPREME COMMANDER* 👑\n"
            "   ⚡ _फुल एडमिन कंट्रोल & ऑटोमेशन सक्रिय_ ⚡\n"
            "╚════════════════════════════════╝\n\n"
            "👇 हुक्म दें, प्रणव जी:",
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
            msg = bot4.send_message(cid, "💰 जिस यूज़र में फंड जोड़ना है उसका Username भेजें:")
            bot4.register_next_step_handler(msg, step_fund_user)

        elif act == "adm_makecoupon":
            msg = bot4.send_message(cid, "🎁 कूपन का कोड नाम लिखें (उदा. `FEST50`):")
            bot4.register_next_step_handler(msg, step_coupon_name)

        elif act == "adm_viewcoupons":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT code, amount, status, piece FROM coupons ORDER BY id DESC LIMIT 10")
            rows = cur.fetchall()
            conn.close()
            txt = "🎁 *कूपन सूची:*\n━━━━━━━━━━━━━━\n"
            for r in rows:
                txt += f"{'🟢' if r[2]=='ACTIVE' else '🔴'} `{r[0]}`: ₹{r[1]:.2f} (लिमिट: {r[3]})\n"
            bot4.send_message(cid, txt or "कोई कूपन नहीं मिला।", reply_markup=get_admin_markup(), parse_mode="Markdown")

        elif act == "adm_backup":
            if os.path.exists("pranav_network.db"):
                with open("pranav_network.db", "rb") as doc:
                    bot4.send_document(cid, doc, caption="💾 Database Backup")
            else:
                bot4.send_message(cid, "❌ बैकअप फ़ाइल नहीं मिली!")

        elif act == "adm_stats":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            u_tot = cur.fetchone()[0]
            cur.execute("SELECT SUM(amount) FROM payments_log")
            rev = cur.fetchone()[0] or 0.0
            conn.close()
            bot4.send_message(cid, f"📊 *सिस्टम स्टैट्स:*\n👥 कुल यूज़र्स: `{u_tot}`\n💰 कुल फंड लॉग: `₹{rev:.2f}`\n🌐 pranavsmm.shop Live ✅", reply_markup=get_admin_markup(), parse_mode="Markdown")

        elif act.startswith("quickadd_"):
            p = act.split("_")
            uid, u_name, amt = int(p[1]), p[2], float(p[3])
            ok, msg = bridge.add_fund(u_name, amt)
            if ok:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amt, uid))
                conn.commit()
                conn.close()
                bot4.send_message(cid, f"✅ ₹{amt} क्रेडिट हो गए `{u_name}` में!")
            else:
                bot4.send_message(cid, f"❌ एरर: {msg}")

        elif act.startswith("unban_"):
            uid = int(act.split("_")[1])
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT web_username FROM users WHERE telegram_id=?", (uid,))
            row = cur.fetchone()
            u_name = row[0] if (row and row[0]) else "User"
            bridge.trigger_status(u_name, "activate")
            cur.execute("UPDATE users SET status='ACTIVE', strikes=0 WHERE telegram_id=?", (uid,))
            conn.commit()
            conn.close()
            bot4.send_message(cid, f"✅ `{u_name}` को बहाल कर दिया गया!")

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
            bot4.send_message(m.chat.id, f"✅ `{target}` को {status_word} कर दिया गया!", reply_markup=get_admin_markup())
        else:
            bot4.send_message(m.chat.id, f"❌ एरर: {res_msg}", reply_markup=get_admin_markup())

    def step_fund_user(m):
        admin_state[m.chat.id] = {"target": m.text.strip()}
        msg = bot4.send_message(m.chat.id, f"💵 `{m.text.strip()}` में कितनी रकम जोड़नी है? (उदा. `100`):")
        bot4.register_next_step_handler(msg, step_fund_amount)

    def step_fund_amount(m):
        try:
            amt = float(m.text.strip())
            target = admin_state[m.chat.id]["target"]
            bot4.send_message(m.chat.id, f"⏳ `{target}` में ₹{amt} जोड़ा जा रहा है...")
            ok, msg = bridge.add_fund(target, amt)
            if ok:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE users SET balance=balance+? WHERE web_username=?", (amt, target))
                cur.execute("INSERT INTO payments_log (target_username, amount, added_by, created_at) VALUES (?, ?, 'ADMIN', ?)", (target, amt, datetime.now()))
                conn.commit()
                conn.close()
                bot4.send_message(m.chat.id, f"✅ ₹{amt} सफलतापूर्वक जुड़ गए!", reply_markup=get_admin_markup())
            else:
                bot4.send_message(m.chat.id, f"❌ एरर: {msg}", reply_markup=get_admin_markup())
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य रकम!", reply_markup=get_admin_markup())

    def step_coupon_name(m):
        admin_state[m.chat.id] = {"c_code": m.text.strip().upper()}
        msg = bot4.send_message(m.chat.id, "💵 कूपन की रकम (रुपये) भेजें (उदा. `50`):")
        bot4.register_next_step_handler(msg, step_coupon_amount)

    def step_coupon_amount(m):
        try:
            admin_state[m.chat.id]["c_amt"] = float(m.text.strip())
            msg = bot4.send_message(m.chat.id, "🎟️ कितने यूज़र्स क्लेम कर सकते हैं? (संख्या भेजें, उदा. `10`):")
            bot4.register_next_step_handler(msg, step_coupon_piece)
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य संख्या!", reply_markup=get_admin_markup())

    def step_coupon_piece(m):
        try:
            pc = int(m.text.strip())
            code = admin_state[m.chat.id]["c_code"]
            amt = admin_state[m.chat.id]["c_amt"]
            bot4.send_message(m.chat.id, f"⏳ वेबसाइट पर कूपन `{code}` बन रहा है...")
            ok, msg = bridge.create_coupon(code, amt, pc)
            if ok:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO coupons (code, amount, piece, status, created_at) VALUES (?, ?, ?, 'ACTIVE', ?)", (code, amt, pc, datetime.now()))
                conn.commit()
                conn.close()
                bot4.send_message(m.chat.id, f"🎁 कूपन `{code}` (₹{amt:.2f}) लाइव बन गया!", reply_markup=get_admin_markup())
            else:
                bot4.send_message(m.chat.id, f"❌ एरर: {msg}", reply_markup=get_admin_markup())
        except Exception:
            bot4.send_message(m.chat.id, "❌ अमान्य इनपुट!", reply_markup=get_admin_markup())

# --- WEB APPEAL API & 4-STRIKE AUTO BAN ENGINE ---
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
                try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"🚨🚨 *[4-स्ट्राइक परमानेंट बैन]*\n👤 `{username}` को 4 बार गलत UTR डालने पर हमेशा के लिए ब्लॉक कर दिया गया!")
                except Exception: pass
            return {"status": "banned", "attempts": attempts, "msg": "4 बार गलत प्रयास! खाता हमेशा के लिए ब्लॉक।"}
        else:
            if bot4:
                try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"⚠️ गलत UTR प्रयास: `{username}` (स्ट्राइक {attempts}/4)")
                except Exception: pass
            return {"status": "failed", "attempts": attempts, "msg": f"अमान्य UTR! प्रयास {attempts}/4 (4 पर हमेशा के लिए ब्लॉक)"}

    if clean_utr:
        cur.execute("INSERT OR REPLACE INTO utr_records (utr_number, claimed_by, claimed_at, status) VALUES (?, ?, ?, 'APPROVED')", (clean_utr, username, datetime.now()))
        cur.execute("DELETE FROM strike_counter WHERE username=?", (username,))
        conn.commit()
    conn.close()

    bridge.trigger_status(username, action="activate")
    if bot4:
        try: bot4.send_message(CONFIG["ADMIN_TELEGRAM_ID"], f"⚡ *[ऑटो-अनबैन 100% सफल]*\n👤 `{username}`\n💳 UTR: `{clean_utr}`\n✅ स्मार्टपैनल पर खाता Active कर दिया गया!")
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
    return jsonify({"status": "online", "system": "PRANAV SMM SUPREME ENTERPRISE ENGINE 24/7", "time": str(datetime.now())}), 200

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
