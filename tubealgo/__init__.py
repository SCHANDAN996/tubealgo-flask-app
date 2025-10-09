# tubealgo/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import config  # नई कॉन्फ़िग फाइल को इम्पोर्ट करें

load_dotenv()

# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] को config.py में मूव कर दिया गया है

db = SQLAlchemy()
login_manager = LoginManager()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

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
    if SubscriptionPlan.query.count() == 0:
        print("Seeding subscription plans...")
        
        free_plan = SubscriptionPlan(
            plan_id='free', name='Free', price=0, slashed_price=None,
            competitors_limit=2, keyword_searches_limit=5, ai_generations_limit=3,
            has_discover_tools=False, has_ai_suggestions=False, playlist_suggestions_limit=3
        )
        
        creator_plan = SubscriptionPlan(
            plan_id='creator', name='Creator', price=39900, slashed_price=79900,
            competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
            has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=10
        )
        
        pro_plan = SubscriptionPlan(
            plan_id='pro', name='Pro', price=99900, slashed_price=199900,
            competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1,
            has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=-1
        )
        
        db.session.add(free_plan)
        db.session.add(creator_plan)
        db.session.add(pro_plan)
        db.session.commit()
        print("Plans seeded successfully.")

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

    # --- यहाँ बदलाव किया गया है ---
    # सारी कॉन्फ़िगरेशन अब एक लाइन से लोड होगी
    app.config.from_object(config.Config)
    # --- बदलाव खत्म ---

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    app.jinja_env.filters['relative_time'] = format_relative_time
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = "error"

    # Blueprints को रजिस्टर करना (इसमें कोई बदलाव नहीं)
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
    from .jobs import check_for_new_videos, take_daily_snapshots, update_all_dashboards
    from .telegram_bot_handler import process_updates
    from .services.ai_service import initialize_ai_clients

    @app.context_processor
    def inject_now_and_settings():
        from .models import get_setting
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    with app.app_context():
        # Step 1: Create all tables first.
        db.create_all()
        
        # Step 2: Seed initial data like plans.
        seed_plans()

        # Step 3: Now that tables exist, initialize AI clients which might read from them.
        print("Initializing AI clients within app context...")
        initialize_ai_clients()

    scheduler = BackgroundScheduler(daemon=True)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        
        scheduler.add_job(
            func=lambda: take_daily_snapshots(app),
            trigger='interval',
            hours=24
        )

        scheduler.add_job(
            func=lambda: check_for_new_videos(app),
            trigger='interval',
            hours=1
        )
        
        scheduler.add_job(
            func=lambda: update_all_dashboards(app),
            trigger='interval',
            hours=4,
            id='update_all_dashboards_job'
        )

        scheduler.add_job(
            func=lambda: process_updates(app),
            trigger='interval',
            seconds=10
        )
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

    return app