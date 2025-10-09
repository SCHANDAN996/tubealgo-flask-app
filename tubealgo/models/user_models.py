# tubealgo/models/user_models.py

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .. import db, login_manager
from datetime import date, datetime, timedelta

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    # --- Google OAuth Fields ---
    google_access_token = db.Column(db.String(1024), nullable=True)
    google_refresh_token = db.Column(db.String(1024), nullable=True)
    google_token_expiry = db.Column(db.DateTime, nullable=True)

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

    dashboard_layout = db.Column(db.Text, nullable=True)

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

class ContentIdea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='idea', index=True) # e.g., 'idea', 'scripting', 'filming', 'editing', 'scheduled'
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref='content_ideas')

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal_type = db.Column(db.String(50), nullable=False) # 'subscribers', 'views'
    target_value = db.Column(db.Integer, nullable=False)
    start_value = db.Column(db.Integer, nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref='goals')
    __table_args__ = (db.UniqueConstraint('user_id', 'goal_type', 'is_active', name='_user_goal_type_active_uc'),)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))