import os
import sys
import time
import random
import socket
import sqlite3
import requests
import telebot
from telebot import types
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from flask import Flask, request, jsonify

RENDER_PORT = int(os.environ.get("PORT", 5000))
BOT4_TOKEN = os.getenv("BOT4_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6779836173"))

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pranavji628@gmail.com")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")

PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "https://pranavsmm.shop")
PANEL_API_KEY = os.getenv("PANEL_API_KEY", "")

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")

DB_PATH = "bot4_database.db"

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

bot4 = None
if BOT4_TOKEN:
    try:
        bot4 = telebot.TeleBot(BOT4_TOKEN)
    except Exception as e:
        print(f"Bot init error: {e}")

user_states = {}

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        service_id TEXT,
        link TEXT,
        quantity INTEGER,
        charge REAL,
        provider_order_id TEXT,
        status TEXT DEFAULT 'PENDING',
        created_at TIMESTAMP
    )
    """)

    cur.execute("INSERT OR IGNORE INTO coupons (code, amount, max_uses) VALUES ('PRANAV100', 100.0, 1000)")
    cur.execute("INSERT OR IGNORE INTO coupons (code, amount, max_uses) VALUES ('WELCOME50', 50.0, 500)")

    conn.commit()
    conn.close()

init_db()

def self_ping_loop():
    time.sleep(10)
    while True:
        try:
            url = f"https://pranav-smm-master-0cgu.onrender.com/"
            requests.get(url, timeout=10)
        except Exception:
            pass
        time.sleep(300)

def send_official_email_otp(target_email, username, otp_code):
    if not SENDER_EMAIL or not GMAIL_APP_PASS:
        return False, "SENDER_EMAIL or GMAIL_APP_PASS is missing in Render settings"

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
        <!DOCTYPE html>
        <html>
        <body style="margin:0; padding:20px; background:#f8fafc; font-family:Arial, sans-serif;">
          <div style="max-width:480px; margin:auto; background:#ffffff; border-radius:18px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 10px 30px rgba(0,0,0,0.05);">
            <div style="background:linear-gradient(135deg, #7928ca, #5b21b6); padding:24px; text-align:center; color:#ffffff;">
              <h1 style="margin:0; font-size:22px; font-weight:800; letter-spacing:1px;">PRANAV SMM PANEL</h1>
              <p style="margin:4px 0 0; font-size:12px; opacity:0.9;">Security & Account Recovery System</p>
            </div>
            <div style="padding:28px 24px; text-align:center;">
              <p style="color:#334155; font-size:14px;">Hello <b>{username}</b>,<br>Your OTP code to restore and activate your account:</p>
              <div style="background:#faf5ff; border:2px dashed #7928ca; border-radius:14px; padding:16px; margin:20px 0; display:inline-block; min-width:220px;">
                <span style="font-size:36px; font-weight:800; letter-spacing:8px; color:#6a1b9a;">{otp_code}</span>
              </div>
              <p style="color:#64748b; font-size:12px;">This code is valid for 10 minutes only. Do not share it with anyone.</p>
              <hr style="border:none; border-top:1px solid #f1f5f9; margin:20px 0;">
              <p style="color:#94a3b8; font-size:11px;">Automated Security Engine - Pranav SMM</p>
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
        return True, "Email sent successfully"

    except Exception as e:
        return False, str(e)
    finally:
        socket.getaddrinfo = orig_getaddrinfo

def update_user_status_panel(email_or_user, new_status):
    target = email_or_user.strip().lower()
    real_username = target

    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE users SET status=? 
            WHERE LOWER(web_email)=? OR LOWER(username)=?
        """, (new_status, target, target))
        
        cur.execute("""
            SELECT username FROM users 
            WHERE LOWER(web_email)=? OR LOWER(username)=?
        """, (target, target))
        row = cur.fetchone()
        if row and row["username"]:
            real_username = row["username"]

        conn.commit()
        conn.close()

        if PANEL_API_KEY and PANEL_DOMAIN:
            try:
                requests.post(
                    f"{PANEL_DOMAIN}/api/v2",
                    data={
                        "key": PANEL_API_KEY,
                        "action": "status_update",
                        "username": real_username,
                        "status": new_status
                    },
                    timeout=5
                )
            except Exception:
                pass

        return True, real_username
    except Exception as e:
        return False, str(e)

@app.route("/", methods=["GET"])
def home_check():
    return jsonify({
        "status": "online",
        "service": "Pranav SMM Master Engine",
        "port": RENDER_PORT,
        "features": ["OTP System", "Add Fund", "Coupon System", "Orders API", "Persistent Lock"],
        "time": str(datetime.now())
    }), 200

@app.route("/api/check-google-user", methods=["POST", "OPTIONS"])
def check_google_user_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    email = request.form.get("email", "").strip().lower()
    if not email:
        return jsonify({"suspended": False}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT status, username FROM users 
        WHERE LOWER(web_email)=? OR LOWER(username)=?
    """, (email, email))
    row = cur.fetchone()
    conn.close()

    if row and row["status"] == "SUSPENDED":
        return jsonify({"suspended": True, "username": row["username"] or email}), 200

    return jsonify({"suspended": False, "username": email}), 200

@app.route("/api/appeal", methods=["POST", "OPTIONS"])
def appeal_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip()
    utr = request.form.get("utr", "").strip().replace(" ", "")
    email = request.form.get("email", "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"status": "error", "msg": "Invalid Gmail ID provided!"}), 200

    if not utr or len(utr) < 6:
        return jsonify({"status": "error", "msg": "Invalid Payment UTR code!"}), 200

    otp = f"{random.randint(100000, 999999)}"

    sent_ok, err_msg = send_official_email_otp(email, username or email, otp)

    if not sent_ok:
        if bot4:
            try:
                bot4.send_message(ADMIN_ID, f"⚠️ SMTP Error for {email}: {err_msg}")
            except Exception:
                pass
        return jsonify({"status": "error", "msg": f"Failed to send OTP to Gmail: {err_msg}"}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO otp_verification 
        (username, email, utr, otp_code, attempts, created_at) 
        VALUES (?, ?, ?, ?, 0, ?)
    """, (email, email, utr, otp, datetime.now()))
    conn.commit()
    conn.close()

    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"📧 *[OTP DISPATCHED]*\n━━━━━━━━━━━━━━\n"
                f"👤 User: `{username or email}`\n"
                f"✉️ Gmail: `{email}`\n"
                f"💳 UTR: `{utr}`\n"
                f"🔑 Code: `{otp}`\n\n"
                f"✅ Status: Delivered to User Inbox",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({
        "status": "otp_sent",
        "msg": f"OTP successfully sent to {email}. Check your inbox or spam folder."
    }), 200

@app.route("/api/verify-otp", methods=["POST", "OPTIONS"])
def verify_otp_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip().lower()
    otp = request.form.get("otp", "").strip()

    if not otp or len(otp) < 6:
        return jsonify({"status": "error", "msg": "Please enter full 6-digit OTP code!"}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT email, utr, otp_code, attempts 
        FROM otp_verification 
        WHERE LOWER(username)=? OR LOWER(email)=?
    """, (username, username))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "msg": "No active OTP request found. Please resend."}), 200

    stored_email = row["email"]
    stored_utr = row["utr"]
    stored_otp = row["otp_code"]
    attempts = row["attempts"] or 0

    if str(stored_otp) != str(otp):
        new_attempts = attempts + 1
        if new_attempts >= 4:
            cur.execute("UPDATE users SET status='BANNED' WHERE LOWER(web_email)=? OR LOWER(username)=?", (stored_email, stored_email))
            conn.commit()
            conn.close()
            return jsonify({"status": "banned", "msg": "Maximum attempts exceeded! Account permanently locked."}), 200

        cur.execute("UPDATE otp_verification SET attempts=? WHERE LOWER(username)=? OR LOWER(email)=?", (new_attempts, username, username))
        conn.commit()
        conn.close()
        return jsonify({"status": "error", "attempts": new_attempts, "msg": f"Incorrect OTP! Attempt {new_attempts}/4"}), 200

    cur.execute("DELETE FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    conn.commit()
    conn.close()

    ok, real_name = update_user_status_panel(stored_email, "ACTIVE")

    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"⚡ *[USER UNBANNED & ACTIVE]*\n━━━━━━━━━━━━━━\n"
                f"👤 User: `{real_name}`\n"
                f"📧 Gmail: `{stored_email}`\n"
                f"💳 UTR: `{stored_utr}`\n"
                f"✅ Status: Activated on Database & Panel",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({"status": "success", "msg": "OTP verified! Your account is now active."}), 200

@app.route("/api/add-fund", methods=["POST", "OPTIONS"])
def add_fund_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip()
    utr = request.form.get("utr", "").strip().replace(" ", "").upper()
    amount_str = request.form.get("amount", "0").strip()

    try:
        amount = float(amount_str)
    except ValueError:
        return jsonify({"status": "error", "msg": "Invalid Amount format!"}), 200

    if not username:
        return jsonify({"status": "error", "msg": "Username is required!"}), 200
    if not utr or len(utr) < 8:
        return jsonify({"status": "error", "msg": "Valid 12-digit UTR is required!"}), 200
    if amount <= 0:
        return jsonify({"status": "error", "msg": "Amount must be greater than zero!"}), 200

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM payments WHERE utr=?", (utr,))
    if cur.fetchone():
        conn.close()
        return jsonify({"status": "error", "msg": "This UTR code has already been processed!"}), 200

    cur.execute("""
        INSERT INTO payments (username, utr, amount, status, created_at)
        VALUES (?, ?, ?, 'APPROVED', ?)
    """, (username, utr, amount, datetime.now()))

    cur.execute("""
        INSERT INTO users (username, balance) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET balance = balance + ?
    """, (username, amount, amount))

    cur.execute("SELECT balance FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    new_balance = row["balance"] if row else amount

    conn.commit()
    conn.close()

    if PANEL_API_KEY and PANEL_DOMAIN:
        try:
            requests.post(
                f"{PANEL_DOMAIN}/api/v2",
                data={
                    "key": PANEL_API_KEY,
                    "action": "add_funds",
                    "username": username,
                    "amount": amount
                },
                timeout=5
            )
        except Exception:
            pass

    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"💰 *[ADD FUND APPROVED]*\n━━━━━━━━━━━━━━\n"
                f"👤 User: `{username}`\n"
                f"💳 UTR: `{utr}`\n"
                f"💵 Amount: Rs. `{amount}`\n"
                f"📊 New Balance: Rs. `{new_balance}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({
        "status": "success",
        "msg": f"Rs. {amount} successfully added to your account balance!",
        "new_balance": new_balance
    }), 200

@app.route("/api/redeem-coupon", methods=["POST", "OPTIONS"])
def redeem_coupon_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip()
    coupon_code = request.form.get("code", "").strip().upper()

    if not username:
        return jsonify({"status": "error", "msg": "Username is required!"}), 200
    if not coupon_code:
        return jsonify({"status": "error", "msg": "Coupon code is required!"}), 200

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT amount, max_uses, used_count FROM coupons WHERE code=?", (coupon_code,))
    coupon = cur.fetchone()

    if not coupon:
        conn.close()
        return jsonify({"status": "error", "msg": "Invalid coupon code!"}), 200

    if coupon["used_count"] >= coupon["max_uses"]:
        conn.close()
        return jsonify({"status": "error", "msg": "This coupon code has expired!"}), 200

    cur.execute("SELECT id FROM coupon_redemptions WHERE username=? AND coupon_code=?", (username, coupon_code))
    if cur.fetchone():
        conn.close()
        return jsonify({"status": "error", "msg": "You have already redeemed this coupon!"}), 200

    amount = coupon["amount"]

    cur.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code=?", (coupon_code,))

    cur.execute("""
        INSERT INTO coupon_redemptions (username, coupon_code, amount, redeemed_at)
        VALUES (?, ?, ?, ?)
    """, (username, coupon_code, amount, datetime.now()))

    cur.execute("""
        INSERT INTO users (username, balance) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET balance = balance + ?
    """, (username, amount, amount))

    cur.execute("SELECT balance FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    new_balance = row["balance"] if row else amount

    conn.commit()
    conn.close()

    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"🎟️ *[COUPON REDEEMED]*\n━━━━━━━━━━━━━━\n"
                f"👤 User: `{username}`\n"
                f"🏷️ Coupon: `{coupon_code}`\n"
                f"🎁 Bonus: Rs. `{amount}`\n"
                f"📊 New Balance: Rs. `{new_balance}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({
        "status": "success",
        "msg": f"Coupon '{coupon_code}' applied! Rs. {amount} credited.",
        "added_amount": amount,
        "new_balance": new_balance
    }), 200

def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("🚫 Suspend User", callback_data="btn_suspend")
    b2 = types.InlineKeyboardButton("✅ Unban User", callback_data="btn_unban")
    b3 = types.InlineKeyboardButton("💰 Add Balance", callback_data="btn_addbal")
    b4 = types.InlineKeyboardButton("🔍 Check Balance", callback_data="btn_checkbal")
    b5 = types.InlineKeyboardButton("🎟️ Create Coupon", callback_data="btn_addcoupon")
    b6 = types.InlineKeyboardButton("📊 System Status", callback_data="btn_status")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    return markup

if bot4:
    @bot4.message_handler(commands=["start"])
    def send_welcome(message):
        if message.chat.id == ADMIN_ID:
            bot4.send_message(
                message.chat.id,
                "👑 *Pranav SMM Master Control Panel*\n\n"
                "Please choose an action from the buttons below:",
                reply_markup=get_main_menu_markup(),
                parse_mode="Markdown"
            )
        else:
            bot4.reply_to(message, "Welcome to Pranav SMM Support.")

    @bot4.callback_query_handler(func=lambda call: True)
    def handle_query(call):
        if call.message.chat.id != ADMIN_ID:
            return

        if call.data == "btn_suspend":
            user_states[call.message.chat.id] = "AWAIT_SUSPEND"
            bot4.send_message(call.message.chat.id, "Send username or email to suspend:")
        
        elif call.data == "btn_unban":
            user_states[call.message.chat.id] = "AWAIT_UNBAN"
            bot4.send_message(call.message.chat.id, "Send username or email to unban:")

        elif call.data == "btn_addbal":
            user_states[call.message.chat.id] = "AWAIT_ADDBAL"
            bot4.send_message(call.message.chat.id, "Send in format: `username amount`\nExample: `rahul12 100`", parse_mode="Markdown")

        elif call.data == "btn_checkbal":
            user_states[call.message.chat.id] = "AWAIT_CHECKBAL"
            bot4.send_message(call.message.chat.id, "Send username to check balance:")

        elif call.data == "btn_addcoupon":
            user_states[call.message.chat.id] = "AWAIT_ADDCOUPON"
            bot4.send_message(call.message.chat.id, "Send in format: `CODE AMOUNT`\nExample: `BONUS50 50`", parse_mode="Markdown")

        elif call.data == "btn_status":
            bot4.send_message(
                call.message.chat.id,
                f"*[SYSTEM STATUS]*\n"
                f"Server: Online\n"
                f"Port: `{RENDER_PORT}`\n"
                f"Domain: `{PANEL_DOMAIN}`\n"
                f"Time: `{datetime.now()}`",
                reply_markup=get_main_menu_markup(),
                parse_mode="Markdown"
            )

    @bot4.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID)
    def handle_admin_text(message):
        state = user_states.get(message.chat.id)

        if state == "AWAIT_SUSPEND":
            target = message.text.strip().lower()
            update_user_status_panel(target, "SUSPENDED")
            user_states.pop(message.chat.id, None)
            bot4.send_message(message.chat.id, f"🚫 `{target}` has been suspended!", reply_markup=get_main_menu_markup(), parse_mode="Markdown")

        elif state == "AWAIT_UNBAN":
            target = message.text.strip().lower()
            update_user_status_panel(target, "ACTIVE")
            user_states.pop(message.chat.id, None)
            bot4.send_message(message.chat.id, f"✅ `{target}` restored to ACTIVE!", reply_markup=get_main_menu_markup(), parse_mode="Markdown")

        elif state == "AWAIT_ADDBAL":
            parts = message.text.strip().split()
            if len(parts) >= 2:
                user = parts[0]
                try:
                    amt = float(parts[1])
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO users (username, balance) VALUES (?, ?)
                        ON CONFLICT(username) DO UPDATE SET balance = balance + ?
                    """, (user, amt, amt))
                    cur.execute("SELECT balance FROM users WHERE username=?", (user,))
                    row = cur.fetchone()
                    conn.commit()
                    conn.close()
                    user_states.pop(message.chat.id, None)
                    bot4.send_message(message.chat.id, f"💰 Added Rs. {amt} to `{user}`. New balance: Rs. {row['balance']}", reply_markup=get_main_menu_markup(), parse_mode="Markdown")
                except ValueError:
                    bot4.send_message(message.chat.id, "Invalid amount format. Try again:")
            else:
                bot4.send_message(message.chat.id, "Send in format: `username amount`", parse_mode="Markdown")

        elif state == "AWAIT_CHECKBAL":
            user = message.text.strip()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT balance FROM users WHERE username=?", (user,))
            row = cur.fetchone()
            conn.close()
            bal = row["balance"] if row else 0.0
            user_states.pop(message.chat.id, None)
            bot4.send_message(message.chat.id, f"👤 User `{user}` balance: Rs. {bal}", reply_markup=get_main_menu_markup(), parse_mode="Markdown")

        elif state == "AWAIT_ADDCOUPON":
            parts = message.text.strip().split()
            if len(parts) >= 2:
                code = parts[0].upper()
                try:
                    amt = float(parts[1])
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO coupons (code, amount, max_uses, used_count) VALUES (?, ?, 1000, 0)", (code, amt))
                    conn.commit()
                    conn.close()
                    user_states.pop(message.chat.id, None)
                    bot4.send_message(message.chat.id, f"🎟️ Coupon `{code}` created with value Rs. {amt}!", reply_markup=get_main_menu_markup(), parse_mode="Markdown")
                except ValueError:
                    bot4.send_message(message.chat.id, "Invalid amount. Try again:")
            else:
                bot4.send_message(message.chat.id, "Send in format: `CODE AMOUNT`", parse_mode="Markdown")

if __name__ == "__main__":
    if bot4:
        t = threading.Thread(target=bot4.infinity_polling, kwargs={"skip_pending": True}, daemon=True)
        t.start()

    p_thread = threading.Thread(target=self_ping_loop, daemon=True)
    p_thread.start()

    app.run(host="0.0.0.0", port=RENDER_PORT)
