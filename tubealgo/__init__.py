# tubealgo/__init__.py

import os
from flask import Flask, url_for, session, g # session and g might be needed by limiter or other extensions
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone, timedelta
from celery import Celery, Task
from celery.schedules import crontab
import config # Assuming your config.py is at the root level alongside run.py
from sqlalchemy.exc import OperationalError
import pytz
from flask_wtf.csrf import CSRFProtect, generate_csrf
# <<< Flask-SSE इम्पोर्ट करें >>>
from flask_sse import sse

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect() # Initialize CSRFProtect

# Limiter configuration - use a function that can handle anonymous users
def limiter_key_func():
    # Use remote address for anonymous users, user ID for logged-in users
    if current_user and current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

limiter = Limiter(key_func=limiter_key_func)

celery = Celery(__name__)


def localize_datetime(utc_dt, fmt='%d %b %Y, %I:%M %p'):
    """Jinja filter to convert a UTC datetime object to a user's preferred timezone."""
    if not utc_dt:
        return ""

    # Default to IST if user or timezone is not set
    user_tz_str = 'Asia/Kolkata'
    if current_user and current_user.is_authenticated and hasattr(current_user, 'timezone') and current_user.timezone:
        user_tz_str = current_user.timezone

    try:
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone('Asia/Kolkata') # Fallback to IST

    # Make the naive datetime from DB timezone-aware (it's UTC)
    if isinstance(utc_dt, datetime) and utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    elif not isinstance(utc_dt, datetime): # Handle potential non-datetime values
         return str(utc_dt) # Return as string if not datetime

    # Convert to user's timezone
    try:
        local_dt = utc_dt.astimezone(user_tz)
        return local_dt.strftime(fmt)
    except Exception as e:
         # Fallback if conversion fails
         print(f"Error localizing datetime: {e}") # Log error for debugging
         return utc_dt.strftime(fmt) + " UTC"


def create_app():
    # Correctly determine project root and paths
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    static_folder_path = os.path.join(project_root, 'static')
    template_folder_path = os.path.join(project_root, 'tubealgo', 'templates')
    instance_folder_path = os.path.join(project_root, 'instance') # Define instance folder path

    app = Flask(
        __name__.split('.')[0],
        instance_path=instance_folder_path, # Set instance path
        instance_relative_config=True,
        static_folder=static_folder_path,
        template_folder=template_folder_path
    )

    app.config.from_object(config.Config)
    # Optional: Load instance config if it exists
    # app.config.from_pyfile('config.py', silent=True)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass # Handle potential errors if needed

    # <<< SSE Configuration >>>
    app.config["REDIS_URL"] = app.config.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    app.register_blueprint(sse, url_prefix='/stream')

    # Celery Configuration
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"]
    )
    celery.conf.beat_schedule = {
        'take-daily-snapshots-every-day': {
            'task': 'tubealgo.jobs.take_daily_snapshots',
            'schedule': crontab(hour=0, minute=5, day_of_week='*'), # Runs daily at 00:05 UTC
        },
        'check-for-new-videos-every-hour': {
            'task': 'tubealgo.jobs.check_for_new_videos',
            'schedule': crontab(minute=0, hour='*'), # Runs every hour at minute 0
        },
        'update-all-dashboards-every-4-hours': {
            'task': 'tubealgo.jobs.update_all_dashboards',
            'schedule': crontab(minute=15, hour='*/4'), # Runs every 4 hours at minute 15
        },
        'take-video-snapshots-every-3-hours': {
            'task': 'tubealgo.jobs.take_video_snapshots',
            'schedule': crontab(minute=30, hour='*/3'), # Runs every 3 hours at minute 30
        },
        'cleanup-old-snapshots-daily': {
            'task': 'tubealgo.jobs.cleanup_old_snapshots',
            'schedule': crontab(hour=1, minute=0, day_of_week='*'), # Runs daily at 01:00 UTC
        },
    }

    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask

    app.celery = celery

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db) # Initialize Flask-Migrate
    csrf.init_app(app) # Initialize CSRFProtect
    login_manager.init_app(app)
    login_manager.login_view = 'auth_local.login'
    login_manager.login_message_category = "error"

    limiter.init_app(app)
    # Use Redis for limiter storage if REDIS_URL is set (from config)
    limiter_storage_uri = app.config.get("REDIS_URL", "memory://")
    # Limiter needs storage_uri, not storage_url
    limiter.storage_uri = limiter_storage_uri
    # Default limits (example: 100 per day, 20 per hour for all routes)
    # You can apply specific limits using decorators in routes
    # app.config['RATELIMIT_DEFAULT'] = "100/day;20/hour"


    # Register custom Jinja filters
    app.jinja_env.filters['relative_time'] = format_relative_time
    app.jinja_env.filters['localize'] = localize_datetime


    # --- Import and register blueprints ---
    # Import Blueprints here to avoid circular imports
    from .auth_local import auth_local_bp
    app.register_blueprint(auth_local_bp, url_prefix='/')

    from .auth_google import auth_google_bp
    app.register_blueprint(auth_google_bp, url_prefix='/')

    from .routes.core_routes import core_bp
    app.register_blueprint(core_bp, url_prefix='/')
    from .routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/')
    from .routes.competitor_routes import competitor_bp
    app.register_blueprint(competitor_bp, url_prefix='/')
    from .routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/')
    from .routes.api_routes import api_bp
    app.register_blueprint(api_bp) # Assumes url_prefix='/api' is defined within api_bp
    from .routes.ai_api_routes import ai_api_bp
    app.register_blueprint(ai_api_bp) # Assumes url_prefix='/manage/api' is defined within ai_api_bp
    from .routes.tool_routes import tool_bp
    app.register_blueprint(tool_bp, url_prefix='/')
    from .routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/')
    from .routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/payment')
    from .routes.admin import admin_bp # Import the main admin blueprint
    app.register_blueprint(admin_bp, url_prefix='/admin')
    from .routes.video_manager_routes import video_manager_bp
    app.register_blueprint(video_manager_bp, url_prefix='/manage')
    from .routes.playlist_manager_routes import playlist_manager_bp
    app.register_blueprint(playlist_manager_bp, url_prefix='/manage')
    from .routes.ab_test_routes import ab_test_bp
    app.register_blueprint(ab_test_bp, url_prefix='/manage')
    from .routes.report_routes import report_bp
    app.register_blueprint(report_bp) # Assumes url_prefix='/report' is defined within report_bp
    from .routes.video_analytics_routes import video_analytics_bp
    app.register_blueprint(video_analytics_bp) # Assumes url_prefix is defined within video_analytics_bp or handles root
    from .routes.planner_routes import planner_bp
    app.register_blueprint(planner_bp) # Assumes url_prefix is defined within planner_bp or handles root
    from .routes.goal_routes import goal_bp
    app.register_blueprint(goal_bp) # Assumes url_prefix='/api/goals' is defined within goal_bp
    from .routes.user_routes import user_bp
    app.register_blueprint(user_bp) # Assumes url_prefix is defined within user_bp or handles root

    # --- Import models after db init and blueprints ---
    from . import models # Ensure models are imported so Flask-Login user_loader works
    from .services.ai_service import initialize_ai_clients # AI client initialization

    @app.after_request
    def add_security_headers(response):
        # Basic security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        response.headers.pop('X-Frame-Options', None)
        response.headers.pop('X-XSS-Protection', None)
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    @app.context_processor
    def override_url_for():
        # Version static files based on modification time for cache busting
        def dated_url_for(endpoint, **values):
            if endpoint == 'static':
                filename = values.get('filename', None)
                if filename:
                    file_path = os.path.join(app.static_folder, filename)
                    if os.path.exists(file_path):
                        values['v'] = int(os.stat(file_path).st_mtime)
            # Handle external URLs correctly
            if '_external' in values:
                return url_for(endpoint, **values)
            return url_for(endpoint, **values)
        return dict(url_for=dated_url_for)


    @app.context_processor
    def inject_now_and_settings():
        # Make datetime and get_setting available in all templates
        from .models import get_setting # Import locally to avoid potential circular dependency during init
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    @app.context_processor
    def inject_csrf_token():
        # Make CSRF token generation available in templates if needed outside forms
        return dict(csrf_token=generate_csrf)

    with app.app_context():
        # Run functions requiring app context on startup
        try:
            # Attempt to create tables if they don't exist (useful for first run/dev)
            # db.create_all() # Generally avoid in prod with migrations, but can be ok for setup
            # Seed plans only if the table exists and is empty
            seed_plans()
            print("Initializing AI clients within app context...")
            initialize_ai_clients()
        except OperationalError as e:
            print(f"Database operation failed during init (maybe migrating?): {e}")
        except Exception as e:
            print(f"Error during app context initialization: {e}")


    return app

def format_relative_time(dt_input):
    """Jinja filter to format datetime object or string into relative time."""
    if not dt_input: return ""

    dt_obj = None
    if isinstance(dt_input, str):
        try:
            # Handle ISO format strings (with or without Z/offset)
            dt_obj = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
        except ValueError:
            return dt_input # Return original string if parsing fails
    elif isinstance(dt_input, datetime):
        dt_obj = dt_input
    else:
        return str(dt_input) # Return string representation for other types

    if not dt_obj: return str(dt_input) # Fallback

    # Ensure dt_obj is timezone-aware (assume UTC if naive)
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt_obj
    seconds = diff.total_seconds()

    if seconds < 0: return "in the future" # Handle future dates if necessary
    if seconds < 60: return "just now"
    minutes = seconds / 60
    if minutes < 60: return f"{int(minutes)} minute{'s' if int(minutes) > 1 else ''} ago"
    hours = minutes / 60
    if hours < 24: return f"{int(hours)} hour{'s' if int(hours) > 1 else ''} ago"
    days = hours / 24
    if days < 7: return f"{int(days)} day{'s' if int(days) > 1 else ''} ago"
    weeks = days / 7
    if weeks < 4.345: # Average weeks in a month
        return f"{int(weeks)} week{'s' if int(weeks) > 1 else ''} ago"
    months = days / 30.437 # Average days in a month
    if months < 12: return f"{int(months)} month{'s' if int(months) > 1 else ''} ago"
    years = days / 365.25 # Account for leap years
    return f"{int(years)} year{'s' if int(years) > 1 else ''} ago"

def seed_plans():
    """Seeds the database with default subscription plans if none exist."""
    from .models import SubscriptionPlan # Import locally
    from sqlalchemy import inspect # Import locally

    try:
        inspector = inspect(db.engine)
        if not inspector.has_table("subscription_plan"):
            print("Skipping seed_plans: table 'subscription_plan' does not exist (likely during migration).")
            return

        if SubscriptionPlan.query.count() == 0:
            print("Seeding subscription plans...")
            free_plan = SubscriptionPlan(
                plan_id='free', name='Free', price=0, slashed_price=None,
                competitors_limit=2, keyword_searches_limit=5, ai_generations_limit=3,
                has_discover_tools=False, has_ai_suggestions=False, playlist_suggestions_limit=3,
                has_comment_reply=False, is_popular=False
            )
            creator_plan = SubscriptionPlan(
                plan_id='creator', name='Creator', price=39900, slashed_price=79900,
                competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
                has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=10,
                has_comment_reply=False, is_popular=True # Mark Creator as popular
            )
            pro_plan = SubscriptionPlan(
                plan_id='pro', name='Pro', price=99900, slashed_price=199900,
                competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1, # -1 for unlimited
                has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=-1,
                has_comment_reply=True, is_popular=False
            )
            db.session.add_all([free_plan, creator_plan, pro_plan])
            db.session.commit()
            print("Plans seeded successfully.")
    except OperationalError:
        print("Skipping seed_plans due to database schema mismatch (likely during migration).")
        db.session.rollback()
    except Exception as e:
        print(f"Error seeding plans: {e}")
        db.session.rollback()
