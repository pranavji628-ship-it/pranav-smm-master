import os
import sys
import time
import random
import socket
import sqlite3
import requests
import telebot
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from flask import Flask, request, jsonify, make_response

BOT4_TOKEN = os.getenv("BOT4_TOKEN", "YOUR_BOT4_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6779836173"))

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pranavji628@gmail.com")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "YOUR_16_DIGIT_GMAIL_APP_PASSWORD")

PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "https://pranavsmm.shop")
PANEL_API_KEY = os.getenv("PANEL_API_KEY", "")

DB_PATH = "bot4_database.db"

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

bot4 = None
if BOT4_TOKEN and BOT4_TOKEN != "YOUR_BOT4_TOKEN_HERE":
    try:
        bot4 = telebot.TeleBot(BOT4_TOKEN)
    except Exception as e:
        print(f"Bot init error: {e}")

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

def send_official_email_otp(target_email, username, otp_code):
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
          <div style="max-width:480px; margin:auto; background:#ffffff; border-radius:18px; border:1px solid #e2e8f0; overflow:hidden;">
            <div style="background:linear-gradient(135deg, #7928ca, #5b21b6); padding:24px; text-align:center; color:#ffffff;">
              <h1 style="margin:0; font-size:22px; font-weight:800;">PRANAV SMM PANEL</h1>
              <p style="margin:4px 0 0; font-size:12px; opacity:0.9;">Security & Account Recovery System</p>
            </div>
            <div style="padding:28px 24px; text-align:center;">
              <p style="color:#334155; font-size:14px;">Hello <b>{username}</b>,<br>Your OTP code to restore and activate your account:</p>
              <div style="background:#faf5ff; border:2px dashed #7928ca; border-radius:14px; padding:16px; margin:20px 0; display:inline-block; min-width:220px;">
                <span style="font-size:36px; font-weight:800; letter-spacing:8px; color:#6a1b9a;">{otp_code}</span>
              </div>
              <p style="color:#64748b; font-size:12px;">This code is valid for 10 minutes only.</p>
            </div>
          </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
        server.ehlo()
        server.starttls()
        server.login(SENDER_EMAIL, GMAIL_APP_PASS)
        server.sendmail(SENDER_EMAIL, [target_email], msg.as_string())
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
        "features": ["OTP System", "Add Fund", "Coupon System", "Persistent Lock"],
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
                bot4.send_message(ADMIN_ID, f"SMTP Error for {email}: {err_msg}")
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
                f"*[OTP DISPATCHED]*\n"
                f"User: `{username or email}`\n"
                f"Gmail: `{email}`\n"
                f"UTR: `{utr}`\n"
                f"Code: `{otp}`\n"
                f"Status: Sent to user inbox",
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
                f"*[USER RESTORED]*\n"
                f"User: `{real_name}`\n"
                f"Gmail: `{stored_email}`\n"
                f"UTR: `{stored_utr}`\n"
                f"Status: Account Activated on Panel",
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
                f"*[ADD FUND SUCCESS]*\n"
                f"User: `{username}`\n"
                f"UTR: `{utr}`\n"
                f"Amount: Rs. `{amount}`\n"
                f"New Balance: Rs. `{new_balance}`",
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
                f"*[COUPON APPLIED]*\n"
                f"User: `{username}`\n"
                f"Coupon: `{coupon_code}`\n"
                f"Bonus: Rs. `{amount}`\n"
                f"New Balance: Rs. `{new_balance}`",
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

if bot4:
    @bot4.message_handler(commands=["start"])
    def send_welcome(message):
        if message.chat.id == ADMIN_ID:
            bot4.reply_to(
                message,
                "*Pranav SMM Master Active!*\n\n"
                "Commands:\n"
                "• `/addcoupon <CODE> <AMOUNT>` - Create coupon\n"
                "• `/suspend <user/email>` - Suspend user\n"
                "• `/unban <user/email>` - Unban user\n"
                "• `/balance <user>` - Check balance\n"
                "• `/addbal <user> <amount>` - Add balance directly",
                parse_mode="Markdown"
            )

    @bot4.message_handler(commands=["addcoupon"])
    def cmd_addcoupon(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 3:
            bot4.reply_to(message, "Usage: `/addcoupon <CODE> <AMOUNT>`", parse_mode="Markdown")
            return
        code = args[1].strip().upper()
        try:
            amt = float(args[2].strip())
        except ValueError:
            bot4.reply_to(message, "Invalid amount provided!", parse_mode="Markdown")
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO coupons (code, amount, max_uses, used_count) VALUES (?, ?, 1000, 0)", (code, amt))
        conn.commit()
        conn.close()
        bot4.reply_to(message, f"Coupon `{code}` created with Rs. {amt} value!", parse_mode="Markdown")

    @bot4.message_handler(commands=["suspend"])
    def cmd_suspend(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot4.reply_to(message, "Usage: `/suspend <username or email>`", parse_mode="Markdown")
            return
        target = args[1].strip().lower()
        update_user_status_panel(target, "SUSPENDED")
        bot4.reply_to(message, f"Account `{target}` suspended successfully!", parse_mode="Markdown")

    @bot4.message_handler(commands=["unban"])
    def cmd_unban(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot4.reply_to(message, "Usage: `/unban <username or email>`", parse_mode="Markdown")
            return
        target = args[1].strip().lower()
        update_user_status_panel(target, "ACTIVE")
        bot4.reply_to(message, f"Account `{target}` restored to ACTIVE successfully!", parse_mode="Markdown")

    @bot4.message_handler(commands=["balance"])
    def cmd_balance(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot4.reply_to(message, "Usage: `/balance <username>`", parse_mode="Markdown")
            return
        user = args[1].strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE username=?", (user,))
        row = cur.fetchone()
        conn.close()
        bal = row["balance"] if row else 0.0
        bot4.reply_to(message, f"User `{user}` balance: Rs. {bal}", parse_mode="Markdown")

    @bot4.message_handler(commands=["addbal"])
    def cmd_addbal(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 3:
            bot4.reply_to(message, "Usage: `/addbal <username> <amount>`", parse_mode="Markdown")
            return
        user = args[1].strip()
        try:
            amt = float(args[2].strip())
        except ValueError:
            bot4.reply_to(message, "Invalid amount!", parse_mode="Markdown")
            return
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
        bot4.reply_to(message, f"Added Rs. {amt} to `{user}`. New balance: Rs. {row['balance']}", parse_mode="Markdown")

if __name__ == "__main__":
    if bot4:
        import threading
        def run_bot():
            try:
                bot4.infinity_polling(skip_pending=True)
            except Exception as e:
                print(f"Bot polling error: {e}")
        t = threading.Thread(target=run_bot, daemon=True)
        t.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
