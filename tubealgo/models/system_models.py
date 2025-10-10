# tubealgo/models/system_models.py

import os
import json
from datetime import datetime
from .. import db

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    log_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'ERROR', 'QUOTA_EXCEEDED', 'INFO'
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True) # For full tracebacks or JSON data

def log_system_event(message, log_type='INFO', details=None):
    """Logs an event to the database and sends a notification for critical errors."""
    try:
        from ..services.notification_service import send_telegram_message # Local import
        
        details_str = ""
        if details:
            if isinstance(details, dict):
                details_str = json.dumps(details, indent=2)
            else:
                details_str = str(details)

        log_entry = SystemLog(
            log_type=log_type,
            message=message,
            details=details_str
        )
        db.session.add(log_entry)
        db.session.commit()

        CRITICAL_LOG_TYPES = ['QUOTA_EXCEEDED', 'ERROR']
        if log_type in CRITICAL_LOG_TYPES:
            admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID')
            if admin_chat_id:
                alert_title = "Critical Alert" if log_type == 'ERROR' else "Quota Alert"
                icon = "🚨" if log_type == 'ERROR' else "⚠️"
                
                telegram_message = (
                    f"{icon} *{alert_title}: {log_type}*\n\n"
                    f"*Message:* {message}\n\n"
                )
                if details_str:
                    telegram_message += f"*Details:* ```\n{details_str[:1000]}\n```" # Limit details length
                
                send_telegram_message(admin_chat_id, telegram_message)

    except Exception as e:
        print(f"!!! FAILED TO LOG SYSTEM EVENT: {e}")
        db.session.rollback()

def is_admin_telegram_user(chat_id):
    """Checks if a given Telegram chat_id belongs to the admin."""
    admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID')
    if admin_chat_id and str(chat_id) == str(admin_chat_id):
        return True
    return False

class SiteSetting(db.Model):
    key = db.Column(db.String(100), primary_key=True, unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

def get_setting(key, default=None):
    setting = SiteSetting.query.get(key)
    if setting and setting.value is not None:
        if setting.value.lower() == 'true': return True
        if setting.value.lower() == 'false': return False
        return setting.value
    return default

def get_config_value(key, default=None):
    db_value = get_setting(key)
    if db_value is not None:
        if isinstance(db_value, bool):
            return db_value
        if db_value:
            return db_value
    return os.environ.get(key, default)

class ApiCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    cache_value = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

class APIKeyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_identifier = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')
    last_failure_at = db.Column(db.DateTime, nullable=True)

class DashboardCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    data = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('dashboard_cache', uselist=False, cascade="all, delete-orphan"))