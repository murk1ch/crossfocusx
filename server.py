import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import random
import string

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

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

@app.route("/activate/<key>")
def activate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET active=TRUE WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/deactivate/<key>")
def deactivate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET active=FALSE WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete/<key>")
def delete_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM keys WHERE key=%s", (key,))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/edit_owner/<key>", methods=["POST"])
def edit_owner(key):
    if not require_admin():
        return redirect(url_for("login"))
    owner = (request.form.get("owner") or "").strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE keys SET owner=%s WHERE key=%s", (owner, key))
            conn.commit()
    return redirect(url_for("dashboard"))

@app.route("/reset_hwid/<key>")
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
        return jsonify({"status": "invalid"})
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT expires_at, active, hwid FROM keys WHERE key=%s", (key,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "invalid"})
            expires_at, active, saved_hwid = row["expires_at"], row["active"], row["hwid"]
            if not active or expires_at <= datetime.now():
                return jsonify({"status": "invalid"})
            if not saved_hwid:
                cur.execute("UPDATE keys SET hwid=%s WHERE key=%s", (hwid, key))
                conn.commit()
                return jsonify({"status": "ok"})
            if saved_hwid == hwid:
                return jsonify({"status": "ok"})
            return jsonify({"status": "invalid"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
