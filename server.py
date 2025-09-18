import os
import psycopg
from psycopg.extras import RealDictCursor
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import random
import string
from math import floor

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.getenv("DATABASE_URL")

UPDATE_VERSION = os.getenv("LATEST_VERSION", "1.0.0")
UPDATE_URL = os.getenv("DOWNLOAD_URL", "")
UPDATE_SHA256 = os.getenv("UPDATE_SHA256", "")
UPDATE_CHANGELOG = os.getenv("UPDATE_CHANGELOG", "")

# Добавьте этот endpoint в server.py
@app.route("/check_update", methods=["GET"])
def check_update():
    return jsonify({
        "version": UPDATE_VERSION,
        "url": UPDATE_URL,
        "sha256": UPDATE_SHA256,
        "changelog": UPDATE_CHANGELOG
    })

def get_conn():
    return psycopg.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS keys (
                    id SERIAL PRIMARY KEY,
                    key TEXT UNIQUE,
                    expires_at TIMESTAMP,
                    active BOOLEAN DEFAULT TRUE,
                    owner TEXT DEFAULT '',
                    hwid TEXT DEFAULT ''
                )
            """)
            conn.commit()

init_db()

def generate_short_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def require_admin():
    return session.get("admin")

@app.template_filter("format_datetime")
def format_datetime(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return value

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "12345az":
            session["admin"] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Неверный пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM keys ORDER BY id DESC")
            keys = cur.fetchall()
    return render_template("dashboard.html", keys=keys)

@app.route("/generate", methods=["POST"])
def generate_key():
    if not require_admin():
        return redirect(url_for("login"))
    custom_key = (request.form.get("custom_key") or "").strip().upper()
    new_key = custom_key if custom_key else generate_short_key()
    days = int(request.form.get("days", 30))
    owner = (request.form.get("owner") or "").strip()
    expires_at = datetime.now() + timedelta(days=days)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO keys (key, expires_at, owner, active, hwid) VALUES (%s, %s, %s, TRUE, '')",
                (new_key, expires_at, owner)
            )
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/activate/<path:key>")
def activate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET active=TRUE WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/deactivate/<path:key>")
def deactivate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET active=FALSE WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete/<path:key>", methods=["POST"])
def delete_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM keys WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/edit_owner/<path:key>", methods=["POST"])
def edit_owner(key):
    if not require_admin():
        return redirect(url_for("login"))
    owner = (request.form.get("owner") or "").strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET owner=%s WHERE key=%s", (owner, key))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/reset_hwid/<path:key>")
def reset_hwid(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET hwid='' WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/check_key", methods=["POST"])
def check_key():
    data = request.json or {}
    key = (data.get("key") or "").strip().upper()
    hwid = (data.get("hwid") or "").strip()

    if not key or not hwid:
        return jsonify({"status": "invalid", "reason": "missing_data"})

    with get_conn() as conn:
        with conn.cursor() as cur:
            # берём owner, active, expires_at, hwid
            cur.execute(
                "SELECT owner, active, expires_at, hwid FROM keys WHERE key=%s", 
                (key,)
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "invalid", "reason": "not_found"})

            owner, active, expires_at, saved_hwid = (
                row["owner"], row["active"], row["expires_at"], row["hwid"]
            )

            if not active:
                return jsonify({"status": "invalid", "reason": "inactive"})

            if expires_at <= datetime.now():
                return jsonify({"status": "invalid", "reason": "expired"})

            if not saved_hwid:
                cur.execute(
                    "UPDATE keys SET hwid=%s WHERE key=%s", 
                    (hwid, key)
                )
                conn.commit()
            elif saved_hwid != hwid:
                return jsonify({"status": "invalid", "reason": "hwid_mismatch"})

            # время до окончания
            delta = expires_at - datetime.now()
            days_left = delta.days
            hours_left = delta.seconds // 3600

            return jsonify({
                "status": "ok",
                "key": key,
                "owner": owner,
                "active": True,
                "hwid": saved_hwid or hwid,
                "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                "days_left": days_left,
                "hours_left": hours_left
            })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)



