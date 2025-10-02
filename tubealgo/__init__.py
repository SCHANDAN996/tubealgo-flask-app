# Filepath: tubealgo/__init__.py

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

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
            has_discover_tools=False, has_ai_suggestions=False
        )
        
        creator_plan = SubscriptionPlan(
            plan_id='creator', name='Creator', price=39900, slashed_price=79900,
            competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
            has_discover_tools=True, has_ai_suggestions=True
        )
        
        pro_plan = SubscriptionPlan(
            plan_id='pro', name='Pro', price=99900, slashed_price=199900,
            competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1,
            has_discover_tools=True, has_ai_suggestions=True
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

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-local-dev')
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///local_dev.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MEASUREMENT_ID'] = os.environ.get('MEASUREMENT_ID')

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

    from . import models
    from .jobs import check_for_new_videos
    # === यहाँ से नया कोड जोड़ा गया है ===
    from .telegram_bot_handler import process_updates
    # === यहाँ तक ===


    @app.context_processor
    def inject_now_and_settings():
        from .models import get_setting
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    with app.app_context():
        db.create_all()
        seed_plans()

    scheduler = BackgroundScheduler(daemon=True)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Job 1: Competitor video check (every hour)
        scheduler.add_job(
            func=lambda: check_for_new_videos(app),
            trigger='interval',
            hours=1
        )
        # === यहाँ से नया कोड जोड़ा गया है ===
        # Job 2: Telegram command polling (every 10 seconds)
        scheduler.add_job(
            func=lambda: process_updates(app),
            trigger='interval',
            seconds=10
        )
        # === यहाँ तक ===
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

    return app# Filepath: tubealgo/__init__.py

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

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
            has_discover_tools=False, has_ai_suggestions=False
        )
        
        creator_plan = SubscriptionPlan(
            plan_id='creator', name='Creator', price=39900, slashed_price=79900,
            competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
            has_discover_tools=True, has_ai_suggestions=True
        )
        
        pro_plan = SubscriptionPlan(
            plan_id='pro', name='Pro', price=99900, slashed_price=199900,
            competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1,
            has_discover_tools=True, has_ai_suggestions=True
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

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-local-dev')
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///local_dev.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MEASUREMENT_ID'] = os.environ.get('MEASUREMENT_ID')

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

    from . import models
    from .jobs import check_for_new_videos
    # === यहाँ से नया कोड जोड़ा गया है ===
    from .telegram_bot_handler import process_updates
    # === यहाँ तक ===


    @app.context_processor
    def inject_now_and_settings():
        from .models import get_setting
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    with app.app_context():
        db.create_all()
        seed_plans()

    scheduler = BackgroundScheduler(daemon=True)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Job 1: Competitor video check (every hour)
        scheduler.add_job(
            func=lambda: check_for_new_videos(app),
            trigger='interval',
            hours=1
        )
        # === यहाँ से नया कोड जोड़ा गया है ===
        # Job 2: Telegram command polling (every 10 seconds)
        scheduler.add_job(
            func=lambda: process_updates(app),
            trigger='interval',
            seconds=10
        )
        # === यहाँ तक ===
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

    return app