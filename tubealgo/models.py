# tubealgo/models.py

import os
import json
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db, login_manager
from datetime import date, datetime

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    log_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'ERROR', 'QUOTA_EXCEEDED', 'INFO'
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True) # For full tracebacks or JSON data

def log_system_event(message, log_type='INFO', details=None):
    """Logs an event to the database and sends a notification for critical errors."""
    try:
        from .services.notification_service import send_telegram_message # Local import
        
        log_entry = SystemLog(
            log_type=log_type,
            message=message,
            details=json.dumps(details, indent=2) if isinstance(details, dict) else str(details)
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
                if details:
                    details_str = json.dumps(details, indent=2) if isinstance(details, dict) else str(details)
                    telegram_message += f"*Details:* ```\n{details_str[:500]}\n```" # Details के पहले 500 अक्षर
                
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

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    telegram_chat_id = db.Column(db.String(100), unique=True, nullable=True)
    default_channel_name = db.Column(db.String(100), nullable=True)
    default_social_handles = db.Column(db.Text, nullable=True)
    default_contact_info = db.Column(db.String(200), nullable=True)
    subscription_plan = db.Column(db.String(20), nullable=False, default='free')
    last_usage_date = db.Column(db.Date, default=date.today)
    daily_keyword_searches = db.Column(db.Integer, default=0)
    daily_ai_generations = db.Column(db.Integer, default=0)
    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    referred_by = db.Column(db.String(20), nullable=True)
    referral_credits = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='active')

    telegram_notify_new_video = db.Column(db.Boolean, default=True)
    telegram_notify_viral_video = db.Column(db.Boolean, default=True)
    telegram_notify_milestone = db.Column(db.Boolean, default=True)
    telegram_notify_ai_suggestion = db.Column(db.Boolean, default=True)
    telegram_notify_weekly_report = db.Column(db.Boolean, default=False)
    
    channel = db.relationship('YouTubeChannel', backref='user', uselist=False, cascade="all, delete-orphan")
    competitors = db.relationship('Competitor', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    search_history = db.relationship('SearchHistory', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class YouTubeChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    channel_id_youtube = db.Column(db.String(100), unique=True, nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))

class Competitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id_youtube = db.Column(db.String(100), nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))
    position = db.Column(db.Integer, nullable=False)
    last_known_video_id = db.Column(db.String(50), nullable=True)

class ApiCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    cache_value = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False, default='percentage')
    discount_value = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    max_uses = db.Column(db.Integer, default=100)
    times_used = db.Column(db.Integer, default=0)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Razorpay की जगह अब ये नए कॉलम
    order_id = db.Column(db.String(100), unique=True, nullable=False, index=True) # हमारा बनाया हुआ यूनिक ऑर्डर ID
    gateway_order_id = db.Column(db.String(100), nullable=True) # Cashfree से मिला ऑर्डर ID
    gateway_payment_id = db.Column(db.String(100), nullable=True) # Cashfree से मिला पेमेंट ID
    
    amount = db.Column(db.Integer, nullable=False) # पैसे में स्टोर होगा
    currency = db.Column(db.String(10), nullable=False, default='INR')
    plan_id = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='created') # e.g., created, captured, failed
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    user = db.relationship('User', backref='payments')

class APIKeyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_identifier = db.Column(db.String(20), unique=True, nullable=False) # e.g., "AIzaS...h28"
    status = db.Column(db.String(20), nullable=False, default='active') # 'active' or 'exhausted'
    last_failure_at = db.Column(db.DateTime, nullable=True)

class SubscriptionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    slashed_price = db.Column(db.Integer, nullable=True)
    competitors_limit = db.Column(db.Integer, nullable=False)
    keyword_searches_limit = db.Column(db.Integer, nullable=False)
    ai_generations_limit = db.Column(db.Integer, nullable=False)
    has_discover_tools = db.Column(db.Boolean, default=False)
    has_ai_suggestions = db.Column(db.Boolean, default=False)

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
