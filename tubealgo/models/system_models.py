# tubealgo/models/system_models.py

import os
import json
from datetime import datetime
from .. import db
from sqlalchemy.exc import OperationalError

# --- SystemLog, log_system_event, is_admin_telegram_user ---
# (यह कोड पहले जैसा ही रहेगा)
class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    [cite_start]log_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'ERROR', 'QUOTA_EXCEEDED', 'INFO' [cite: 1697]
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True) # For full tracebacks or JSON data

def log_system_event(message, log_type='INFO', details=None):
    """Logs an event to the database and sends a notification for critical errors."""
    try:
        [cite_start]from ..services.notification_service import send_telegram_message # [cite: 1697]

        details_str = ""
        if details:
            if isinstance(details, dict):
                [cite_start]details_str = json.dumps(details, indent=2) # [cite: 1698]
            else:
                details_str = str(details)

        log_entry = SystemLog(
            log_type=log_type,
            message=message,
            details=details_str
        )
        db.session.add(log_entry)
        db.session.commit()

        [cite_start]CRITICAL_LOG_TYPES = ['QUOTA_EXCEEDED', 'ERROR'] # [cite: 1699]
        if log_type in CRITICAL_LOG_TYPES:
            [cite_start]admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID') # [cite: 1699]
            if admin_chat_id:
                alert_title = "Critical Alert" if log_type == 'ERROR' else "Quota Alert"
                icon = "🚨" if log_type == 'ERROR' else "⚠️"

                [cite_start]telegram_message = ( # [cite: 1700]
                    f"{icon} *{alert_title}: {log_type}*\n\n"
                    f"*Message:* {message}\n\n"
                )
                if details_str:
                    [cite_start]telegram_message += f"*Details:* ```\n{details_str[:1000]}\n```" # [cite: 1701]

                send_telegram_message(admin_chat_id, telegram_message)

    except Exception as e:
        print(f"!!! FAILED TO LOG SYSTEM EVENT: {e}")
        db.session.rollback()

def is_admin_telegram_user(chat_id):
    """Checks if a given Telegram chat_id belongs to the admin."""
    [cite_start]admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID') # [cite: 1701]
    [cite_start]if admin_chat_id and str(chat_id) == str(admin_chat_id): # [cite: 1701]
        return True
    [cite_start]return False # [cite: 1702]

# --- SiteSetting Model (महत्वपूर्ण हिस्सा) ---
class SiteSetting(db.Model):
    key = db.Column(db.String(100), primary_key=True, unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

def get_setting(key, default=None):
    """
    Safely gets a setting from the database.
    Returns default if the table doesn't exist (e.g., during migrations).
    """
    try:
        setting = SiteSetting.query.get(key)
        if setting and setting.value is not None:
            [cite_start]if setting.value.lower() == 'true': return True # [cite: 1702]
            [cite_start]if setting.value.lower() == 'false': return False # [cite: 1702]
            [cite_start]return setting.value # [cite: 1703]
    [cite_start]except OperationalError: # [cite: 1703]
        # This can happen if the db is not initialized yet (e.g., during flask db init)
        return default
    [cite_start]return default # [cite: 1703]

def get_config_value(key, default=None):
    """
    Gets a configuration value, prioritizing the database over environment variables.
    """
    [cite_start]db_value = get_setting(key) # [cite: 1703]
    if db_value is not None:
        [cite_start]if isinstance(db_value, bool): # [cite: 1703]
            return db_value
        [cite_start]if db_value: # [cite: 1704]
            return db_value
    [cite_start]return os.environ.get(key, default) # [cite: 1704]

# --- ApiCache, APIKeyStatus, DashboardCache ---
# (यह कोड पहले जैसा ही रहेगा)
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
    [cite_start]data = db.Column(db.JSON, nullable=True) # [cite: 1705]
    [cite_start]updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) # [cite: 1705]

    [cite_start]user = db.relationship('User', backref=db.backref('dashboard_cache', uselist=False, cascade="all, delete-orphan")) # [cite: 1705]
