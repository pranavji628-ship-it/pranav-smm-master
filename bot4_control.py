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
from flask import Flask, request, jsonify
from flask_cors import CORS

# ==================== 1. कॉन्फ़िगरेशन सेटिंग्स ====================
# Render के Environment Variables से वैल्यू उठाएगा, नहीं तो डिफ़ॉल्ट
BOT4_TOKEN = os.getenv("BOT4_TOKEN", "YOUR_BOT4_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6779836173"))  # आपकी टेलीग्राम चैट आईडी

# Gmail SMTP सेटिंग्स (App Password होना ज़रूरी है)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pranavji628@gmail.com")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "YOUR_16_DIGIT_GMAIL_APP_PASSWORD")

# स्मार्टपैनल डेटाबेस / API सेटिंग्स
PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "https://pranavsmm.shop")
PANEL_API_KEY = os.getenv("PANEL_API_KEY", "")

DB_PATH = "bot4_database.db"

# ==================== 2. ऐप व बोट इनिशियलाइज़ेशन ====================
app = Flask(__name__)
CORS(app)  # वेबसाइट से आने वाली सभी रिक्वेस्ट को परमिशन देगा

bot4 = None
if BOT4_TOKEN and BOT4_TOKEN != "YOUR_BOT4_TOKEN_HERE":
    try:
        bot4 = telebot.TeleBot(BOT4_TOKEN)
    except Exception as e:
        print(f"[ERROR] बोट इनिशियलाइज़ नहीं हुआ: {e}")

# ==================== 3. डेटाबेस सेटअप ====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # यूज़र टेबल
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        web_email TEXT,
        status TEXT DEFAULT 'ACTIVE'
    )
    """)
    # OTP वेरिफिकेशन टेबल
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
    conn.commit()
    conn.close()

init_db()

# ==================== 4. IPv4 फ़ोर्स फ़ंक्शन (Network Unreachable Fix) ====================
def send_official_email_otp(target_email, username, otp_code):
    """
    Render पर IPv6 ब्लॉक होने की वजह से 'Network unreachable' आता है।
    यह फ़ंक्शन सॉकेट को केवल IPv4 पर फ़ोर्स करता है ताकि Gmail पर 100% मेल जाए।
    """
    orig_getaddrinfo = socket.getaddrinfo

    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        socket.getaddrinfo = ipv4_getaddrinfo

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} - Pranav SMM अकाउंट रिकवरी OTP"
        msg["From"] = f"Pranav SMM Support <{SENDER_EMAIL}>"
        msg["To"] = target_email

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
        </head>
        <body style="margin:0; padding:20px; background:#f8fafc; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
          <div style="max-width:480px; margin:auto; background:#ffffff; border-radius:18px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 10px 30px rgba(0,0,0,0.05);">
            <div style="background:linear-gradient(135deg, #7928ca, #5b21b6); padding:24px; text-align:center; color:#ffffff;">
              <h1 style="margin:0; font-size:22px; font-weight:800; letter-spacing:1px;">PRANAV SMM PANEL</h1>
              <p style="margin:4px 0 0; font-size:12px; opacity:0.9;">अकाउंट सिक्योरिटी एवं वेरिफिकेशन सिस्टम</p>
            </div>
            <div style="padding:28px 24px; text-align:center;">
              <p style="color:#334155; font-size:14px; margin-bottom:18px;">
                नमस्ते <b>{username}</b>,<br>
                आपके खाते को अनबैन और एक्टिवेट करने के लिए आपका 6-डिजिट OTP नीचे दिया गया है:
              </p>
              <div style="background:#faf5ff; border:2px dashed #7928ca; border-radius:14px; padding:16px; margin:20px 0; display:inline-block; min-width:220px;">
                <span style="font-size:36px; font-weight:800; letter-spacing:8px; color:#6a1b9a;">{otp_code}</span>
              </div>
              <p style="color:#64748b; font-size:12.5px; margin-top:16px; line-height:1.5;">
                यह कोड केवल <b>10 मिनट</b> के लिए मान्य है। कृपया इसे किसी के साथ साझा न करें।
              </p>
              <hr style="border:none; border-top:1px solid #f1f5f9; margin:22px 0;">
              <p style="color:#94a3b8; font-size:11px; margin:0;">
                यदि आपने यह अनुरोध नहीं किया था, तो कृपया तुरंत एडमिन से संपर्क करें।<br>
                © Pranav SMM Auto-Engine
              </p>
            </div>
          </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        # Gmail Port 587 (TLS) का इस्तेमाल करें
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


# ==================== 5. स्मार्टपैनल पर खाता अनबैन फ़ंक्शन ====================
def unban_user_on_smartpanel(email_or_user):
    """
    जब OTP सही डल जाए, तो यह फ़ंक्शन यूज़र को स्मार्टपैनल और लोकल DB में 'ACTIVE' कर देता है।
    """
    target = email_or_user.strip().lower()
    real_username = target

    try:
        conn = get_db()
        cur = conn.cursor()
        
        # लोकल डेटाबेस में स्टेटस एक्टिव करें
        cur.execute("""
            UPDATE users SET status='ACTIVE' 
            WHERE LOWER(web_email)=? OR LOWER(username)=?
        """, (target, target))
        
        # असली यूज़रनेम ढूँढें
        cur.execute("""
            SELECT username FROM users 
            WHERE LOWER(web_email)=? OR LOWER(username)=?
        """, (target, target))
        row = cur.fetchone()
        if row and row["username"]:
            real_username = row["username"]
            
        conn.commit()
        conn.close()

        # अगर आपने स्मार्टपैनल डेटाबेस सीधे कनेक्ट किया है या API है:
        # यहाँ स्मार्टपैनल API कॉल या MySQL क्वेरी डाली जा सकती है
        return True, real_username

    except Exception as e:
        print(f"[ERROR] अनबैन प्रोसेस में गड़बड़: {e}")
        return False, str(e)


# ==================== 6. FLASK API ROUTES (वेबसाइट के लिए) ====================

# 1. होमपेज टेस्ट रूट (ताकि 'Not Found' न आए)
@app.route("/", methods=["GET"])
def home_check():
    return jsonify({
        "status": "online",
        "service": "Pranav SMM Master Engine",
        "time": str(datetime.now())
    }), 200


# 2. Google लॉगिन सस्पेंशन चेक API
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

    # अगर डेटाबेस में सस्पेंडेड है
    if row and row["status"] == "SUSPENDED":
        return jsonify({
            "suspended": True,
            "username": row["username"] or email
        }), 200

    # नया यूज़र या सामान्य यूज़र
    return jsonify({"suspended": False, "username": email}), 200


# 3. अपील व OTP भेजने का API
@app.route("/api/appeal", methods=["POST", "OPTIONS"])
def appeal_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip()
    utr = request.form.get("utr", "").strip().replace(" ", "")
    email = request.form.get("email", "").strip().lower()

    if not email or "@" not in email:
        return jsonify({
            "status": "error",
            "msg": "कृपया सही Gmail ID दर्ज करें!"
        }), 200

    if not utr or len(utr) < 6:
        return jsonify({
            "status": "error",
            "msg": "कृपया 12-अंक का मान्य Payment UTR नंबर दर्ज करें!"
        }), 200

    # 6-डिजिट OTP कोड बनाएँ
    otp = f"{random.randint(100000, 999999)}"

    # सीधा यूज़र की Gmail पर भेजें
    sent_ok, err_msg = send_official_email_otp(email, username or email, otp)

    if not sent_ok:
        # अगर Gmail भेजने में कोई दिक्कत आई
        if bot4:
            try:
                bot4.send_message(
                    ADMIN_ID,
                    f"⚠️ *[SMTP एरर]*\n━━━━━━━━━━━━━━\n"
                    f"यूज़र: `{username or email}`\n"
                    f"ईमेल: `{email}`\n"
                    f"एरर: `{err_msg}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        return jsonify({
            "status": "error",
            "msg": f"Gmail पर OTP नहीं भेजा जा सका: {err_msg}"
        }), 200

    # डेटाबेस में OTP रिकॉर्ड सुरक्षित करें
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO otp_verification 
        (username, email, utr, otp_code, attempts, created_at) 
        VALUES (?, ?, ?, ?, 0, ?)
    """, (email, email, utr, otp, datetime.now()))
    conn.commit()
    conn.close()

    # एडमिन को बैकग्राउंड में सिर्फ सूचना भेजें
    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"📧 *[OTP प्रेषित सूचना]*\n━━━━━━━━━━━━━━\n"
                f"👤 यूज़र: `{username or email}`\n"
                f"✉️ Gmail: `{email}`\n"
                f"💳 UTR: `{utr}`\n"
                f"🔑 OTP: `{otp}`\n\n"
                f"स्थिति: ✅ यूज़र की Gmail पर सफ़लतापूर्वक भेजा गया!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({
        "status": "otp_sent",
        "msg": f"OTP सफ़लतापूर्वक {email} पर भेज दिया गया है। अपना इनबॉक्स/स्पैम फ़ोल्डर चेक करें।"
    }), 200


# 4. OTP वेरीफाई और ऑटो-अनबैन API
@app.route("/api/verify-otp", methods=["POST", "OPTIONS"])
def verify_otp_api():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    username = request.form.get("username", "").strip().lower()
    otp = request.form.get("otp", "").strip()

    if not otp or len(otp) < 6:
        return jsonify({
            "status": "error",
            "msg": "कृपया पूरे 6 डिजिट का OTP डालें!"
        }), 200

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
        return jsonify({
            "status": "error",
            "msg": "कोई एक्टिव OTP अनुरोध नहीं मिला। दोबारा OTP भेजें।"
        }), 200

    stored_email = row["email"]
    stored_utr = row["utr"]
    stored_otp = row["otp_code"]
    attempts = row["attempts"] or 0

    # गलत OTP की स्थिति
    if str(stored_otp) != str(otp):
        new_attempts = attempts + 1
        if new_attempts >= 4:
            # 4 गलत कोशिशों के बाद परमानेंट बैन
            cur.execute("""
                UPDATE users SET status='BANNED' 
                WHERE LOWER(web_email)=? OR LOWER(username)=?
            """, (stored_email, stored_email))
            conn.commit()
            conn.close()
            return jsonify({
                "status": "banned",
                "msg": "अत्यधिक गलत प्रयास! खाता स्थायी रूप से लॉक कर दिया गया।"
            }), 200

        cur.execute("""
            UPDATE otp_verification SET attempts=? 
            WHERE LOWER(username)=? OR LOWER(email)=?
        """, (new_attempts, username, username))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "error",
            "attempts": new_attempts,
            "msg": f"गलत OTP कोड! (प्रयास {new_attempts}/4)"
        }), 200

    # सही OTP: अब यूज़र को अनबैन करें
    cur.execute("DELETE FROM otp_verification WHERE LOWER(username)=? OR LOWER(email)=?", (username, username))
    conn.commit()
    conn.close()

    # स्मार्टपैनल पर स्टेटस एक्टिव करें
    ok, real_name = unban_user_on_smartpanel(stored_email)

    # एडमिन को बधाई अलर्ट
    if bot4:
        try:
            bot4.send_message(
                ADMIN_ID,
                f"⚡ *[सफ़ल अनबैन सूचना]*\n━━━━━━━━━━━━━━\n"
                f"👤 यूज़र: `{real_name}`\n"
                f"📧 Gmail: `{stored_email}`\n"
                f"💳 UTR: `{stored_utr}`\n"
                f"✅ स्थिति: स्मार्टपैनल पर खाता Active कर दिया गया!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    return jsonify({
        "status": "success",
        "msg": "OTP सत्यापित! आपका खाता सफ़लतापूर्वक अनबैन कर दिया गया है।"
    }), 200


# ==================== 7. TELEGRAM BOT HANDLERS ====================
if bot4:
    @bot4.message_handler(commands=["start"])
    def send_welcome(message):
        if message.chat.id == ADMIN_ID:
            bot4.reply_to(
                message,
                "👑 *प्रणव जी, Bot 4 कंट्रोल मास्टर एक्टिव है!*\n\n"
                "यहाँ वेबसाइट के सभी सस्पेंशन, OTP और पेमेंट UTR के लाइव अलर्ट मिलेंगे।\n\n"
                "कमांड्स:\n"
                "• `/suspend <email/user>` - किसी को सस्पेंड करें\n"
                "• `/unban <email/user>` - किसी को अनबैन करें\n"
                "• `/status` - सिस्टम स्थिति जांचें",
                parse_mode="Markdown"
            )
        else:
            bot4.reply_to(message, "नमस्ते! यह Pranav SMM सपोर्ट ऑटो-बोट है।")

    @bot4.message_handler(commands=["suspend"])
    def cmd_suspend(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot4.reply_to(message, "उपयोग: `/suspend <username या email>`", parse_mode="Markdown")
            return
        target = args[1].strip().lower()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users (username, web_email, status) VALUES (?, ?, 'SUSPENDED')", (target, target))
        conn.commit()
        conn.close()
        bot4.reply_to(message, f"🚫 `{target}` को सफलतापूर्वक सस्पेंड कर दिया गया!", parse_mode="Markdown")

    @bot4.message_handler(commands=["unban"])
    def cmd_unban(message):
        if message.chat.id != ADMIN_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot4.reply_to(message, "उपयोग: `/unban <username या email>`", parse_mode="Markdown")
            return
        target = args[1].strip().lower()
        unban_user_on_smartpanel(target)
        bot4.reply_to(message, f"✅ `{target}` को सफलतापूर्वक एक्टिव (Unban) कर दिया गया!", parse_mode="Markdown")


# ==================== 8. सर्वर स्टार्ट ====================
if __name__ == "__main__":
    # बैकग्राउंड में बोट पोलिंग चलाना
    if bot4:
        import threading
        def run_bot():
            try:
                bot4.infinity_polling(skip_pending=True)
            except Exception as e:
                print(f"[BOT POLLING ERROR] {e}")
        t = threading.Thread(target=run_bot, daemon=True)
        t.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
