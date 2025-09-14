from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
import sqlite3, random, string

app = Flask(__name__)
app.secret_key = "supersecretkey"

# --- Инициализация базы ---
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            expires_at TEXT,
            active INTEGER DEFAULT 1,
            owner TEXT DEFAULT ''
        )""")
        conn.commit()

init_db()

# --- Генератор коротких ключей ---
def generate_short_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Авторизация ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "12345az":
            session["admin"] = True
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Неверный пароль")
    return render_template("login.html")

# --- Панель ---
@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        keys = conn.execute("SELECT * FROM keys").fetchall()
    return render_template("dashboard.html", keys=keys)

# --- Создание ключа ---
@app.route("/generate", methods=["POST"])
def generate_key():
    if not session.get("admin"):
        return redirect(url_for("login"))
    custom_key = request.form.get("custom_key").strip()
    new_key = custom_key if custom_key else generate_short_key()
    days = int(request.form.get("days", 30))
    owner = request.form.get("owner", "")
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT INTO keys (key, expires_at, owner) VALUES (?, ?, ?)", (new_key, expires_at, owner))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- Деактивация ---
@app.route("/deactivate/<key>")
def deactivate_key(key):
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        conn.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- Активация ---
@app.route("/activate/<key>")
def activate_key(key):
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        conn.execute("UPDATE keys SET active=1 WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- Полное удаление ---
@app.route("/delete/<key>")
def delete_key(key):
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        conn.execute("DELETE FROM keys WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- Редактирование владельца ---
@app.route("/edit_owner/<key>", methods=["POST"])
def edit_owner(key):
    if not session.get("admin"):
        return redirect(url_for("login"))
    owner = request.form.get("owner", "")
    with sqlite3.connect("database.db") as conn:
        conn.execute("UPDATE keys SET owner=? WHERE key=?", (owner, key))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- API для клиента ---
@app.route("/check_key", methods=["POST"])
def check_key():
    data = request.json
    key = data.get("key")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT expires_at, active FROM keys WHERE key=?", (key,))
        row = c.fetchone()
        if row:
            expires_at, active = row
            if active and datetime.fromisoformat(expires_at) > datetime.now():
                return jsonify({"status": "ok"})
    return jsonify({"status": "invalid"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
