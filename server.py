from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)

# SQLite (локально) или PostgreSQL (на Render)
# Для PostgreSQL на Render строка подключения будет вида:
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host:port/dbname'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///licenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hwid = db.Column(db.String(128), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')  # active / revoked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    def is_valid(self):
        """Проверка, действительна ли лицензия"""
        if self.status != 'active':
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

# Создание таблиц
with app.app_context():
    db.create_all()
