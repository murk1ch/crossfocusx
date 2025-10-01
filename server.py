import os
import psycopg
from psycopg.rows import dict_row
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
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            # keys — как у тебя
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

            # creators — контент-мейкеры
            cur.execute("""
                CREATE TABLE IF NOT EXISTS creators (
                    id SERIAL PRIMARY KEY,
                    nickname TEXT UNIQUE NOT NULL,
                    yt_url TEXT DEFAULT '',
                    tt_url TEXT DEFAULT '',
                    ig_url TEXT DEFAULT '',
                    commission_percent INTEGER DEFAULT 10,
                    active BOOLEAN DEFAULT TRUE,
                    note TEXT DEFAULT ''
                )
            """)

            # promo_codes — сами промокоды
            cur.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    creator_id INTEGER REFERENCES creators(id) ON DELETE SET NULL,
                    bonus_days INTEGER DEFAULT 7,
                    max_uses INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE,
                    start_at TIMESTAMP DEFAULT NOW(),
                    end_at TIMESTAMP,
                    only_new_users BOOLEAN DEFAULT FALSE,
                    note TEXT DEFAULT ''
                )
            """)

            # promo_redemptions — лог применений промокодов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS promo_redemptions (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    key TEXT NOT NULL,
                    hwid TEXT NOT NULL,
                    redeemed_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # purchases — учёт покупок (для комиссий)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS purchases (
                    id SERIAL PRIMARY KEY,
                    key TEXT NOT NULL,
                    amount NUMERIC(10,2) NOT NULL,
                    code TEXT,
                    creator_id INTEGER REFERENCES creators(id),
                    purchased_at TIMESTAMP DEFAULT NOW()
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

# ---------------- РОУТ: referrals ----------------
@app.route("/referrals")
def referrals():
    if not require_admin():
        return redirect(url_for("login"))

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Контент‑мейкеры
            cur.execute("SELECT * FROM creators ORDER BY id DESC")
            creators = cur.fetchall()

            # Промокоды + ник автора
            cur.execute("""
                SELECT p.*, c.nickname AS creator_nickname
                FROM promo_codes p
                LEFT JOIN creators c ON c.id = p.creator_id
                ORDER BY p.id DESC
            """)
            codes = cur.fetchall()

            # Статистика по промокодам
            cur.execute("""
                SELECT code, COUNT(*) AS uses
                FROM promo_redemptions
                GROUP BY code
            """)
            stats = {row["code"]: row["uses"] for row in cur.fetchall()}

            # Статистика по авторам
            cur.execute("""
                SELECT c.id, COUNT(r.id) AS uses
                FROM creators c
                LEFT JOIN promo_codes p ON p.creator_id = c.id
                LEFT JOIN promo_redemptions r ON r.code = p.code
                GROUP BY c.id
            """)
            creator_stats = {row["id"]: row["uses"] for row in cur.fetchall()}

            # История применений
            cur.execute("""
                SELECT * FROM promo_redemptions
                ORDER BY redeemed_at DESC
                LIMIT 50
            """)
            redemptions = cur.fetchall()

    return render_template(
        "referrals.html",
        creators=creators,
        codes=codes,
        stats=stats,
        creator_stats=creator_stats,
        redemptions=redemptions
    )

# ---------------- Управление авторами ----------------
@app.route("/creator/create", methods=["POST"])
def creator_create():
    if not require_admin():
        return redirect(url_for("login"))
    nickname = request.form["nickname"]
    yt_url = request.form.get("yt_url")
    tt_url = request.form.get("tt_url")
    ig_url = request.form.get("ig_url")
    commission_percent = request.form.get("commission_percent", 10)
    note = request.form.get("note")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO creators (nickname, yt_url, tt_url, ig_url, commission_percent, note, active)
                VALUES (%s,%s,%s,%s,%s,%s,TRUE)
            """, (nickname, yt_url, tt_url, ig_url, commission_percent, note))
            conn.commit()
    return redirect(url_for("referrals"))
    
@app.route("/promo/redeem", methods=["POST"])
def promo_redeem():
    data = request.get_json()
    key = data.get("key")
    hwid = data.get("hwid")
    promo = data.get("promo")

    # здесь твоя логика проверки промокода
    return jsonify({
        "success": True,
        "bonus_days": 7,
        "message": "Промокод применён, +7 дней!"
    })

@app.route("/creator/toggle/<int:creator_id>")
def creator_toggle(creator_id):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE creators SET active = NOT active WHERE id=%s", (creator_id,))
            conn.commit()
    return redirect(url_for("referrals"))

@app.route("/creator/delete/<int:creator_id>", methods=["POST"])
def creator_delete(creator_id):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM creators WHERE id=%s", (creator_id,))
            conn.commit()
    return redirect(url_for("referrals"))

# ---------------- Управление промокодами ----------------
@app.route("/promo/create", methods=["POST"])
def promo_create():
    if not require_admin():
        return redirect(url_for("login"))
    code = request.form["code"]
    creator_id = request.form.get("creator_id") or None
    bonus_days = request.form.get("bonus_days", 7)
    max_uses = request.form.get("max_uses", 0)
    end_at = request.form.get("end_at") or None
    only_new = "only_new_users" in request.form
    note = request.form.get("note")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO promo_codes (code, creator_id, bonus_days, max_uses, end_at, only_new_users, note, active, start_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,NOW())
            """, (code, creator_id, bonus_days, max_uses, end_at, only_new, note))
            conn.commit()
    return redirect(url_for("referrals"))

@app.route("/promo/toggle/<code>")
def promo_toggle(code):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE promo_codes SET active = NOT active WHERE code=%s", (code,))
            conn.commit()
    return redirect(url_for("referrals"))

@app.route("/promo/delete/<code>", methods=["POST"])
def promo_delete(code):
    if not require_admin():
        return redirect(url_for("login"))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM promo_codes WHERE code=%s", (code,))
            conn.commit()
    return redirect(url_for("referrals"))

@app.route("/apply_promo", methods=["POST"])
def apply_promo():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    key = (data.get("key") or "").strip().upper()
    hwid = (data.get("hwid") or "").strip()
    if not code or not key or not hwid:
        return jsonify({"status": "invalid", "reason": "missing_data"}), 400
    now = datetime.now()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Проверяем ключ
            cur.execute("SELECT id, expires_at, active, hwid AS saved_hwid FROM keys WHERE key=%s", (key,))
            k = cur.fetchone()
            if not k:
                return jsonify({"status": "invalid", "reason": "key_not_found"}), 404
            if not k["active"]:
                return jsonify({"status": "invalid", "reason": "key_inactive"}), 403
            if k["expires_at"] <= now:
                return jsonify({"status": "invalid", "reason": "key_expired"}), 403
            if k["saved_hwid"] and k["saved_hwid"] != hwid:
                return jsonify({"status": "invalid", "reason": "hwid_mismatch"}), 403
            if not k["saved_hwid"]:
                cur.execute("UPDATE keys SET hwid=%s WHERE id=%s", (hwid, k["id"]))

            # Проверяем промокод
            cur.execute("""
                SELECT p.*, c.nickname AS creator_nickname
                FROM promo_codes p
                LEFT JOIN creators c ON c.id = p.creator_id
                WHERE p.code=%s
            """, (code,))
            p = cur.fetchone()
            if not p:
                return jsonify({"status": "invalid", "reason": "promo_not_found"}), 404
            if not p["active"]:
                return jsonify({"status": "invalid", "reason": "promo_inactive"}), 403
            if p["start_at"] and p["start_at"] > now:
                return jsonify({"status": "invalid", "reason": "promo_not_started"}), 403
            if p["end_at"] and p["end_at"] < now:
                return jsonify({"status": "invalid", "reason": "promo_expired"}), 403

            # Антифрод: один раз на связку key+hwid
            cur.execute("""
                SELECT 1 FROM promo_redemptions
                WHERE code=%s AND key=%s AND hwid=%s
            """, (code, key, hwid))
            if cur.fetchone():
                return jsonify({"status": "invalid", "reason": "already_redeemed"}), 409

            # Лимит применений
            if p["max_uses"] and p["max_uses"] > 0:
                cur.execute("SELECT COUNT(*) AS used FROM promo_redemptions WHERE code=%s", (code,))
                used = cur.fetchone()["used"]
                if used >= p["max_uses"]:
                    return jsonify({"status": "invalid", "reason": "promo_limit_reached"}), 409

            # «Только для новых»
            if p["only_new_users"]:
                cur.execute("SELECT 1 FROM promo_redemptions WHERE key=%s", (key,))
                if cur.fetchone():
                    return jsonify({"status": "invalid", "reason": "not_new_user"}), 403

            # Применяем бонус
            bonus_days = int(p["bonus_days"] or 7)
            new_expires = k["expires_at"] + timedelta(days=bonus_days)
            cur.execute("UPDATE keys SET expires_at=%s WHERE id=%s", (new_expires, k["id"]))

            # Логируем применение
            cur.execute("""
                INSERT INTO promo_redemptions (code, key, hwid)
                VALUES (%s, %s, %s)
            """, (code, key, hwid))
            conn.commit()

            delta = new_expires - now
            return jsonify({
                "status": "ok",
                "code": code,
                "creator": p["creator_nickname"],
                "bonus_days": bonus_days,
                "new_expires_at": new_expires.strftime("%Y-%m-%d %H:%M:%S"),
                "days_left": delta.days,
                "hours_left": delta.seconds // 3600
            })

@app.route("/purchase/create", methods=["POST"])
def purchase_create():
    if not require_admin():
        return redirect(url_for("login"))
    key = (request.form.get("key") or "").strip().upper()
    amount = float(request.form.get("amount") or 0)
    code = (request.form.get("code") or "").strip().upper()

    creator_id = None
    if code:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT creator_id FROM promo_codes WHERE code=%s", (code,))
                row = cur.fetchone()
                if row:
                    creator_id = row["creator_id"]
            conn.commit()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO purchases (key, amount, code, creator_id)
                VALUES (%s, %s, %s, %s)
            """, (key, amount, code or None, creator_id))
            conn.commit()
    return redirect(url_for("referrals"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)







