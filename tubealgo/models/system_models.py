# tubealgo/models/system_models.py

import os
import json
from datetime import datetime
from .. import db
from sqlalchemy.exc import OperationalError
import traceback # Ensure traceback is imported

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    log_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'ERROR', 'QUOTA_EXCEEDED', 'INFO'
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True) # For full tracebacks or JSON data

def log_system_event(message, log_type='INFO', details=None, traceback_info=None): # Add traceback_info parameter
    """Logs an event to the database and sends a notification for critical errors."""
    try:
        from ..services.notification_service import send_telegram_message

        details_str = ""
        if details:
            if isinstance(details, dict):
                # Ensure traceback is included if provided
                if traceback_info:
                    details['traceback'] = traceback_info
                details_str = json.dumps(details, indent=2, default=str) # Add default=str for non-serializable objects
            else:
                details_str = str(details)
                if traceback_info:
                    details_str += f"\n\nTraceback:\n{traceback_info}"
        elif traceback_info:
             details_str = f"Traceback:\n{traceback_info}"


        log_entry = SystemLog(
            log_type=log_type,
            message=message,
            details=details_str
        )
        db.session.add(log_entry)
        db.session.commit()

        CRITICAL_LOG_TYPES = ['QUOTA_EXCEEDED', 'ERROR', 'PROJECT_QUOTA_EXCEEDED'] # Added PROJECT_QUOTA_EXCEEDED
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
                    # Truncate details reasonably for Telegram
                    truncated_details = details_str[:1000] + ('...' if len(details_str) > 1000 else '')
                    telegram_message += f"*Details:* ```\n{truncated_details}\n```"

                send_telegram_message(admin_chat_id, telegram_message)

    except Exception as e:
        print(f"!!! FAILED TO LOG SYSTEM EVENT (Original message: {message}): {e}")
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
    """
    Safely gets a setting from the database.
    Returns default if the table doesn't exist (e.g., during migrations).
    """
    try:
        setting = SiteSetting.query.get(key)
        if setting and setting.value is not None:
            # Handle boolean strings explicitly
            val_lower = setting.value.lower()
            if val_lower == 'true': return True
            if val_lower == 'false': return False
            # Return the original string value otherwise
            return setting.value
    except OperationalError:
        # This can happen if the db is not initialized yet (e.g., during flask db init)
        return default
    except Exception as e:
        # Log other potential errors during setting retrieval
        print(f"Error getting setting '{key}': {e}") # Use print as logger might not be ready
        return default
    # Return default if setting not found or value is None
    return default


def get_config_value(key, default=None):
    """
    Gets a configuration value, prioritizing the database over environment variables.
    Handles potential boolean string values from the database.
    """
    db_value = get_setting(key) # get_setting handles boolean conversion

    if db_value is not None:
        # If get_setting returned True/False, use that.
        # If it returned a non-empty string, use that.
        return db_value

    # If db_value is None (not found or explicitly None in DB), fallback to environment variable
    return os.environ.get(key, default)


class ApiCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    cache_value = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True) # Add index for faster cleanup query


class APIKeyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_identifier = db.Column(db.String(20), unique=True, nullable=False, index=True) # Index added
    status = db.Column(db.String(20), nullable=False, default='active', index=True) # Index added
    last_failure_at = db.Column(db.DateTime, nullable=True, index=True) # Index added


class DashboardCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True) # Added ondelete
    data = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationship setup in user_models.py might be preferable to avoid circular imports
    # user = db.relationship('User', backref=db.backref('dashboard_cache', uselist=False, cascade="all, delete-orphan"))
