from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# --- Конфигурация базы ---
# Если на Render есть переменная окружения DATABASE_URL (PostgreSQL) — используем её
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Render выдаёт URL в формате postgres://, SQLAlchemy ждёт postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Локально используем SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///licenses.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Модель лицензии ---
class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hwid = db.Column(db.String(128), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')  # active / revoked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    def is_valid(self):
        if self.status != 'active':
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

# Создаём таблицы, если их нет
with app.app_context():
    db.create_all()

# --- Главная страница ---
@app.route("/")
def index():
    # Если есть шаблон test1.html в папке templates
    try:
        return render_template("test1.html")
    except:
        return "Сервер работает! 🎯"

# --- API: проверка лицензии ---
@app.route("/check_license", methods=["POST"])
def check_license():
    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "HWID required"}), 400

    hwid = data["hwid"]
    lic = License.query.filter_by(hwid=hwid).first()
    if lic and lic.is_valid():
        return jsonify({"valid": True})
    return jsonify({"valid": False})

# --- API: регистрация лицензии ---
@app.route("/register_license", methods=["POST"])
def register_license():
    # Простейшая защита: ключ администратора в переменной окружения ADMIN_KEY
    admin_key = os.environ.get("ADMIN_KEY", "secret123")
    key = request.headers.get("X-Admin-Key")
    if key != admin_key:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "HWID required"}), 400

    hwid = data["hwid"]
    expires_days = data.get("expires_days")  # можно задать срок действия
    notes = data.get("notes")

    if License.query.filter_by(hwid=hwid).first():
        return jsonify({"error": "License already exists"}), 400

    expires_at = None
    if expires_days:
        expires_at = datetime.utcnow() + timedelta(days=int(expires_days))

    lic = License(hwid=hwid, expires_at=expires_at, notes=notes)
    db.session.add(lic)
    db.session.commit()

    return jsonify({"message": "License registered", "hwid": hwid})

# --- API: отзыв лицензии ---
@app.route("/revoke_license", methods=["POST"])
def revoke_license():
    admin_key = os.environ.get("ADMIN_KEY", "secret123")
    key = request.headers.get("X-Admin-Key")
    if key != admin_key:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "HWID required"}), 400

    hwid = data["hwid"]
    lic = License.query.filter_by(hwid=hwid).first()
    if not lic:
        return jsonify({"error": "License not found"}), 404

    lic.status = "revoked"
    db.session.commit()

    return jsonify({"message": "License revoked", "hwid": hwid})

# --- Запуск локально ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
