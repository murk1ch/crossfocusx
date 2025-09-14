from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# --- Конфигурация базы ---
db_url = os.environ.get("DATABASE_URL")
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///licenses.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Модель лицензии ---
class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hwid = db.Column(db.String(128), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    def is_valid(self):
        if self.status != 'active':
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

with app.app_context():
    db.create_all()

# --- Главная страница ---
@app.route("/")
def index():
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

    lic = License.query.filter_by(hwid=data["hwid"]).first()
    return jsonify({"valid": bool(lic and lic.is_valid())})

# --- API: регистрация лицензии ---
@app.route("/register_license", methods=["POST"])
def register_license():
    admin_key = os.environ.get("ADMIN_KEY", "secret123")
    if request.headers.get("X-Admin-Key") != admin_key:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "HWID required"}), 400

    if License.query.filter_by(hwid=data["hwid"]).first():
        return jsonify({"error": "License already exists"}), 400

    expires_at = None
    if "expires_days" in data:
        expires_at = datetime.utcnow() + timedelta(days=int(data["expires_days"]))

    lic = License(hwid=data["hwid"], expires_at=expires_at, notes=data.get("notes"))
    db.session.add(lic)
    db.session.commit()

    return jsonify({"message": "License registered", "hwid": data["hwid"]})

# --- API: отзыв лицензии ---
@app.route("/revoke_license", methods=["POST"])
def revoke_license():
    admin_key = os.environ.get("ADMIN_KEY", "secret123")
    if request.headers.get("X-Admin-Key") != admin_key:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "HWID required"}), 400

    lic = License.query.filter_by(hwid=data["hwid"]).first()
    if not lic:
        return jsonify({"error": "License not found"}), 404

    lic.status = "revoked"
    db.session.commit()

    return jsonify({"message": "License revoked", "hwid": data["hwid"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
