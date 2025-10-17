# tubealgo/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone
from celery import Celery, Task
from celery.schedules import crontab
import config

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

# Celery ऑब्जेक्ट को यहाँ बिना कॉन्फ़िगरेशन के बनाया गया है
celery = Celery(__name__)

def create_app():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    static_folder_path = os.path.join(project_root, 'static')
    template_folder_path = os.path.join(project_root, 'tubealgo', 'templates')

    app = Flask(
        __name__.split('.')[0],
        instance_relative_config=True,
        static_folder=static_folder_path,
        template_folder=template_folder_path
    )

    app.config.from_object(config.Config)
    
    # Celery कॉन्फ़िगरेशन को यहाँ ऐप कॉन्टेक्स्ट के अंदर अपडेट करें
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"]
    )
    celery.conf.beat_schedule = {
        'take-daily-snapshots-every-day': {
            'task': 'tubealgo.jobs.take_daily_snapshots',
            'schedule': crontab(hour=0, minute=5),  # Runs daily at 00:05 UTC
        },
        'check-for-new-videos-every-hour': {
            'task': 'tubealgo.jobs.check_for_new_videos',
            'schedule': crontab(minute=0),  # Runs at the start of every hour
        },
        'update-all-dashboards-every-4-hours': {
            'task': 'tubealgo.jobs.update_all_dashboards',
            'schedule': crontab(minute=0, hour='*/4'), # Runs every 4 hours
        },
    }
    
    # Context Task Class ताकि Celery टास्क Flask कॉन्टेक्स्ट का उपयोग कर सकें
    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    app.jinja_env.filters['relative_time'] = format_relative_time
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = "error"

    # Blueprints
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/')
    from .routes.core_routes import core_bp
    app.register_blueprint(core_bp, url_prefix='/')
    from .routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/')
    from .routes.competitor_routes import competitor_bp
    app.register_blueprint(competitor_bp, url_prefix='/')
    from .routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/')   
    from .routes.api_routes import api_bp
    app.register_blueprint(api_bp)
    from .routes.tool_routes import tool_bp
    app.register_blueprint(tool_bp, url_prefix='/')
    from .routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/')
    from .routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/')
    from .routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    from .routes.manager_routes import manager_bp
    app.register_blueprint(manager_bp)
    from .routes.planner_routes import planner_bp
    app.register_blueprint(planner_bp)
    from .routes.goal_routes import goal_bp
    app.register_blueprint(goal_bp)

    from . import models
    from .services.ai_service import initialize_ai_clients
    
    @app.context_processor
    def inject_now_and_settings():
        from .models import get_setting
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    with app.app_context():
        db.create_all()
        seed_plans()
        print("Initializing AI clients within app context...")
        initialize_ai_clients()
    
    return app

def format_relative_time(dt_str):
    if not dt_str: return ""
    dt_obj = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    diff = now - dt_obj
    seconds = diff.total_seconds()
    if seconds < 60: return "just now"
    minutes = seconds / 60
    if minutes < 60: return f"{int(minutes)} minute{'s' if int(minutes) > 1 else ''} ago"
    hours = minutes / 60
    if hours < 24: return f"{int(hours)} hour{'s' if int(hours) > 1 else ''} ago"
    days = hours / 24
    if days < 30: return f"{int(days)} day{'s' if int(days) > 1 else ''} ago"
    months = days / 30
    if months < 12: return f"{int(months)} month{'s' if int(months) > 1 else ''} ago"
    years = months / 12
    return f"{int(years)} year{'s' if int(years) > 1 else ''} ago"

def seed_plans():
    from .models import SubscriptionPlan
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if not inspector.has_table("subscription_plan"):
        return
    if SubscriptionPlan.query.count() == 0:
        print("Seeding subscription plans...")
        free_plan = SubscriptionPlan(plan_id='free', name='Free', price=0, slashed_price=None, competitors_limit=2, keyword_searches_limit=5, ai_generations_limit=3, has_discover_tools=False, has_ai_suggestions=False, playlist_suggestions_limit=3)
        creator_plan = SubscriptionPlan(plan_id='creator', name='Creator', price=39900, slashed_price=79900, competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30, has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=10)
        pro_plan = SubscriptionPlan(plan_id='pro', name='Pro', price=99900, slashed_price=199900, competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1, has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=-1)
        db.session.add(free_plan)
        db.session.add(creator_plan)
        db.session.add(pro_plan)
        db.session.commit()
        print("Plans seeded successfully.")
