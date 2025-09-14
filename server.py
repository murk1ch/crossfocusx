import os
import sqlite3
import random
import string
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)

# Секрет лучше хранить в переменной окружения
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey_change_me")

DB_PATH = "database.db"


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        # Базовая таблица
        c.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                expires_at TEXT,
                active INTEGER DEFAULT 1,
                owner TEXT DEFAULT ''
            )
        """)
        conn.commit()

        # Добавляем столбец hwid, если его нет
        c.execute("PRAGMA table_info(keys)")
        cols = [row[1] for row in c.fetchall()]
        if "hwid" not in cols:
            try:
                c.execute("ALTER TABLE keys ADD COLUMN hwid TEXT DEFAULT ''")
                conn.commit()
            except sqlite3.OperationalError:
                pass


init_db()


def generate_short_key(length=12):
    # Буквы + цифры, верхний регистр — удобно читать/вводить
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def require_admin():
    if not session.get("admin"):
        return False
    return True


# ------- Авторизация --------
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


# ------- Админ‑панель --------
@app.route("/dashboard")
def dashboard():
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        keys = conn.execute("SELECT id, key, expires_at, active, owner, hwid FROM keys ORDER BY id DESC").fetchall()
    return render_template("dashboard.html", keys=keys)


@app.route("/generate", methods=["POST"])
def generate_key():
    if not require_admin():
        return redirect(url_for("login"))
    custom_key = (request.form.get("custom_key") or "").strip().upper()
    new_key = custom_key if custom_key else generate_short_key()

    try:
        days = int(request.form.get("days", 30))
    except ValueError:
        days = 30

    owner = (request.form.get("owner") or "").strip()
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO keys (key, expires_at, owner, active, hwid) VALUES (?, ?, ?, 1, '')",
            (new_key, expires_at, owner)
        )
        conn.commit()
    return redirect(url_for("dashboard"))


@app.route("/activate/<key>")
def activate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        conn.execute("UPDATE keys SET active=1 WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))


@app.route("/deactivate/<key>")
def deactivate_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        conn.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))


@app.route("/delete/<key>")
def delete_key(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        conn.execute("DELETE FROM keys WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))


@app.route("/edit_owner/<key>", methods=["POST"])
def edit_owner(key):
    if not require_admin():
        return redirect(url_for("login"))
    owner = (request.form.get("owner") or "").strip()
    with get_conn() as conn:
        conn.execute("UPDATE keys SET owner=? WHERE key=?", (owner, key))
        conn.commit()
    return redirect(url_for("dashboard"))


@app.route("/reset_hwid/<key>")
def reset_hwid(key):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        conn.execute("UPDATE keys SET hwid='' WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))


# ------- API для клиента (ключ + HWID) --------
@app.route("/check_key", methods=["POST"])
def check_key():
    data = request.json or {}
    key = (data.get("key") or "").strip().upper()
    hwid = (data.get("hwid") or "").strip()

    if not key or not hwid:
        return jsonify({"status": "invalid"})

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT expires_at, active, hwid FROM keys WHERE key=?", (key,))
        row = c.fetchone()
        if not row:
            return jsonify({"status": "invalid"})

        expires_at, active, saved_hwid = row

        # Срок/активность
        try:
            if not active or datetime.fromisoformat(expires_at) <= datetime.now():
                return jsonify({"status": "invalid"})
        except Exception:
            return jsonify({"status": "invalid"})

        # Привязка HWID: если пуст — привязываем, если совпадает — ок, иначе — invalid
        if not saved_hwid:
            c.execute("UPDATE keys SET hwid=? WHERE key=?", (hwid, key))
            conn.commit()
            return jsonify({"status": "ok"})

        if saved_hwid == hwid:
            return jsonify({"status": "ok"})

        return jsonify({"status": "invalid"})


if __name__ == "__main__":
    # Локальный запуск (на Render используется gunicorn)
    app.run(host="0.0.0.0", port=5000)
