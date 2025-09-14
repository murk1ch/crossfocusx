from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
import sqlite3, uuid

app = Flask(__name__)
app.secret_key = "supersecret"  # замени на свой ключ

# --- Инициализация БД ---
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            expires_at TEXT,
            active INTEGER DEFAULT 1
        )""")
        conn.commit()

init_db()

# --- Авторизация ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "1234":
            session["admin"] = True
            return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        keys = conn.execute("SELECT * FROM keys").fetchall()
    return render_template("dashboard.html", keys=keys)

# --- Генерация ключа ---
@app.route("/generate", methods=["POST"])
def generate_key():
    if not session.get("admin"):
        return redirect(url_for("login"))
    new_key = str(uuid.uuid4())
    days = int(request.form.get("days", 30))
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT INTO keys (key, expires_at) VALUES (?, ?)", (new_key, expires_at))
        conn.commit()
    return redirect(url_for("dashboard"))

# --- API для проверки ключа ---
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

# --- Удаление ключа ---
@app.route("/delete/<key>")
def delete_key(key):
    if not session.get("admin"):
        return redirect(url_for("login"))
    with sqlite3.connect("database.db") as conn:
        conn.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
        conn.commit()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
