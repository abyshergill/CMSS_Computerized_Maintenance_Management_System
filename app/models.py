from datetime import datetime, timezone
from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='Authorized') # Admin, Authorized
    logs = db.relationship('MaintenanceLog', backref='author', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    components = db.relationship('Component', backref='section', lazy='dynamic', cascade="all, delete-orphan")

class Component(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(64), unique=True, index=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'))
    status = db.Column(db.String(20), default='Good') # Good, Alert, Bad
    expiry_date = db.Column(db.DateTime)
    history = db.relationship('MaintenanceLog', backref='component', lazy='dynamic', cascade="all, delete-orphan")
    alert_settings = db.relationship('AlertSettings', backref='component', uselist=False, cascade="all, delete-orphan")

class MaintenanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('component.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.DateTime, index=True, default=datetime.now)
    notes = db.Column(db.Text)
    file_path = db.Column(db.String(256))

class AlertSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('component.id'))
    interval_days = db.Column(db.Integer, default=0)
    interval_hours = db.Column(db.Integer, default=0)
