# tubealgo/__init__.py

import os
from flask import Flask, url_for, session, g, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone, timedelta
from celery import Celery, Task
from celery.schedules import crontab
import config # Assuming config.py is in the parent directory
from sqlalchemy.exc import OperationalError
import pytz
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_sse import sse

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def limiter_key_func():
    if current_user and current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

limiter = Limiter(key_func=limiter_key_func, default_limits=["200 per day", "50 per hour"])

celery = Celery(__name__)


def localize_datetime(utc_dt, fmt='%d %b %Y, %I:%M %p'):
    """Jinja filter to convert a UTC datetime object to a user's preferred timezone."""
    if not utc_dt:
        return ""

    user_tz_str = 'Asia/Kolkata' # Default
    try:
        if current_user and current_user.is_authenticated and hasattr(current_user, 'timezone') and current_user.timezone:
            user_tz_str = current_user.timezone
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone('Asia/Kolkata') # Fallback

    if isinstance(utc_dt, datetime) and utc_dt.tzinfo is None:
        # Assume naive datetime is UTC
        utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    elif not isinstance(utc_dt, datetime):
         # If it's not a datetime object, return as string
         return str(utc_dt)

    try:
        local_dt = utc_dt.astimezone(user_tz)
        return local_dt.strftime(fmt)
    except Exception as e:
         print(f"Error localizing datetime: {e}")
         # Fallback to UTC display if conversion fails
         return utc_dt.strftime(fmt) + " UTC"


def create_app():
    # --- Correctly locate static and template folders relative to the root ---
    # project_root is the directory containing 'run.py', 'tubealgo/', 'static/', etc.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    static_folder_path = os.path.join(project_root, 'static')
    # Templates are inside the 'tubealgo' package
    template_folder_path = os.path.join(project_root, 'tubealgo', 'templates')
    instance_folder_path = os.path.join(project_root, 'instance')

    app = Flask(
        __name__.split('.')[0], # Use package name 'tubealgo'
        instance_path=instance_folder_path,
        instance_relative_config=True, # Looks for config in instance folder first
        static_folder=static_folder_path, # Set static folder path
        template_folder=template_folder_path # Set template folder path
    )

    # Load configuration from config.py
    app.config.from_object(config.Config)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass # Handle potential error during instance folder creation

    # --- SSE Configuration ---
    # Ensure REDIS_URL is correctly fetched from config
    app.config["REDIS_URL"] = app.config.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    app.register_blueprint(sse, url_prefix='/stream')

    # --- Celery Configuration ---
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        # Add other Celery settings if needed
    )
    # Define Celery Beat schedule
    celery.conf.beat_schedule = {
        'take-daily-snapshots-every-day': {
            'task': 'tubealgo.jobs.take_daily_snapshots',
            'schedule': crontab(hour=0, minute=5, day_of_week='*'), # Run daily at 00:05 UTC
        },
        'check-for-new-videos-every-hour': {
            'task': 'tubealgo.jobs.check_for_new_videos',
            'schedule': crontab(minute=0, hour='*'), # Run at the start of every hour
        },
        'update-all-dashboards-every-4-hours': {
            'task': 'tubealgo.jobs.update_all_dashboards',
            'schedule': crontab(minute=15, hour='*/4'), # Run every 4 hours at xx:15
        },
         'take-video-snapshots-every-3-hours': {
            'task': 'tubealgo.jobs.take_video_snapshots',
            'schedule': crontab(minute=30, hour='*/3'), # Run every 3 hours at xx:30
        },
        'cleanup-old-snapshots-daily': {
            'task': 'tubealgo.jobs.cleanup_old_snapshots',
            'schedule': crontab(hour=1, minute=0, day_of_week='*'), # Run daily at 01:00 UTC
        },
        # Add other scheduled tasks here
    }

    # Make Celery tasks run within Flask application context
    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask
    app.celery = celery # Attach celery instance to app

    # --- Initialize Extensions ---
    db.init_app(app)
    csrf.init_app(app) # Initialize CSRF protection
    login_manager.init_app(app)
    login_manager.login_view = 'auth_local.login' # Redirect to login page if needed
    login_manager.login_message_category = "error" # Flash category for login required message

    # Initialize Flask-Limiter with Redis storage if available
    limiter_storage_uri = app.config.get("REDIS_URL", "memory://") # Default to memory if Redis not set
    limiter.init_app(app)
    # Explicitly set storage_uri AFTER init_app if needed, or configure via app.config
    # limiter.storage_uri = limiter_storage_uri # Not typically needed if using app.config['RATELIMIT_STORAGE_URI']

    # --- Import and register Blueprints ---
    from .auth_local import auth_local_bp
    app.register_blueprint(auth_local_bp, url_prefix='/') # Handles /, /login, /signup, /logout
    from .auth_google import auth_google_bp
    app.register_blueprint(auth_google_bp, url_prefix='/') # Handles /login/google, /connect/youtube, /callback
    from .routes.core_routes import core_bp
    app.register_blueprint(core_bp, url_prefix='/') # Handles static pages like /about, /contact, /pricing etc.
    from .routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/') # Handles /dashboard, /referrals etc.
    from .routes.competitor_routes import competitor_bp
    app.register_blueprint(competitor_bp, url_prefix='/') # Handles /competitors, /discover etc.
    from .routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/') # Handles /deep-analysis, /video etc.
    from .routes.api_routes import api_bp
    app.register_blueprint(api_bp) # Handles /api/... routes
    from .routes.ai_api_routes import ai_api_bp
    app.register_blueprint(ai_api_bp) # Handles /manage/api/... routes
    from .routes.tool_routes import tool_bp
    app.register_blueprint(tool_bp, url_prefix='/') # Handles /keyword-research, /ai-generator etc.
    from .routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/') # Handles /settings etc.
    from .routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/payment') # Handles /payment/... routes
    from .routes.admin_routes import admin_bp # Import combined admin blueprint
    app.register_blueprint(admin_bp, url_prefix='/admin') # Register admin blueprint
    from .routes.video_manager_routes import video_manager_bp
    app.register_blueprint(video_manager_bp, url_prefix='/manage') # Handles /manage/videos, /manage/edit etc.
    from .routes.playlist_manager_routes import playlist_manager_bp
    app.register_blueprint(playlist_manager_bp, url_prefix='/manage') # Handles /manage/playlists etc.
    from .routes.ab_test_routes import ab_test_bp
    app.register_blueprint(ab_test_bp, url_prefix='/manage') # Handles /manage/ab-test etc.
    from .routes.report_routes import report_bp
    app.register_blueprint(report_bp) # Handles /report/... routes
    from .routes.video_analytics_routes import video_analytics_bp
    app.register_blueprint(video_analytics_bp) # Handles /manage/analytics/... routes
    from .routes.planner_routes import planner_bp
    app.register_blueprint(planner_bp) # Handles /planner, /api/planner/... routes
    from .routes.goal_routes import goal_bp
    app.register_blueprint(goal_bp) # Handles /api/goals/... routes
    from .routes.user_routes import user_bp
    app.register_blueprint(user_bp) # Handles /api/user/... routes

    # --- Exempt API blueprints from CSRF protection ---
    # Make sure these variables (api_bp, ai_api_bp) are defined before this point
    csrf.exempt(api_bp)
    csrf.exempt(ai_api_bp)
    # Exempt payment webhook if needed (depends on CSRF setup)
    csrf.exempt(payment_bp)

    # --- Import models AFTER db is initialized ---
    from . import models
    # Import AI service initialization function
    from .services.ai_service import initialize_ai_clients

    # --- Request Hooks ---
    @app.after_request
    def add_security_headers(response):
        # Recommended security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'" # Prevent clickjacking
        # Remove potentially less secure headers if present
        response.headers.pop('X-Frame-Options', None)
        response.headers.pop('X-XSS-Protection', None)
        # Prevent caching of HTML pages to avoid stale data issues
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # --- Context Processors ---
    # <<< बदलाव यहाँ है: dated_url_for हटा दिया गया, डिफ़ॉल्ट url_for का उपयोग किया जा रहा है >>>
    @app.context_processor
    def override_url_for():
        # Just return the default url_for function
        return dict(url_for=url_for)

    @app.context_processor
    def inject_now_and_settings():
        from .models import get_setting # Import locally to avoid circular dependency
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    @app.context_processor
    def inject_csrf_token():
         # Provides {{ csrf_token() }} macro in templates for manual token placement if needed
         # Flask-WTF's {{ form.hidden_tag() }} is preferred for forms.
        return dict(csrf_token=generate_csrf)

    # --- Jinja Filters ---
    app.jinja_env.filters['relative_time'] = format_relative_time
    app.jinja_env.filters['localize'] = localize_datetime

    # --- Error Handlers ---
    @app.errorhandler(500)
    def internal_error(error):
        # Log the error properly here if needed
        return render_template('errors/500.html'), 500

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404 # Changed status code to 404

    # --- Application Context Setup ---
    with app.app_context():
        try:
            print("Checking database connection...")
            # Test connection with a simple query
            db.session.execute('SELECT 1')
            print("Database connection successful.")
            # db.create_all() # <<< यह लाइन कमेंटेड या हटा दी गई है - माइग्रेशन का उपयोग करें >>>
            seed_plans() # Seed subscription plans if they don't exist
            print("Initializing AI clients within app context...")
            initialize_ai_clients() # Initialize AI clients (e.g., load API keys)

        except OperationalError as e:
            # Handle specific database connection errors during startup
            print(f"FATAL: Database operation failed during init. Check DB connection string and reachability: {e}")
            # Depending on severity, you might want to raise the exception
            # raise e
        except Exception as e:
            print(f"Error during app context initialization: {e}")
            # Log the full traceback for debugging
            import traceback
            traceback.print_exc()

    return app

# --- Helper Functions (format_relative_time, seed_plans) ---
def format_relative_time(dt_input):
    """Jinja filter to format datetime object or string into relative time."""
    if not dt_input: return ""
    dt_obj = None
    if isinstance(dt_input, str):
        try: dt_obj = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
        except ValueError: return dt_input # Return original string if parsing fails
    elif isinstance(dt_input, datetime): dt_obj = dt_input
    else: return str(dt_input) # Return string representation if not datetime or string

    if not dt_obj: return str(dt_input)

    # Make the datetime object timezone-aware (assume UTC if naive)
    if dt_obj.tzinfo is None: dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt_obj
    seconds = diff.total_seconds()

    if seconds < 0: return "in the future"
    if seconds < 60: return "just now"
    minutes = seconds / 60
    if minutes < 60: return f"{int(minutes)} minute{'s' if int(minutes) > 1 else ''} ago"
    hours = minutes / 60
    if hours < 24: return f"{int(hours)} hour{'s' if int(hours) > 1 else ''} ago"
    days = hours / 24
    if days < 7: return f"{int(days)} day{'s' if int(days) > 1 else ''} ago"
    weeks = days / 7
    if weeks < 4.345: return f"{int(weeks)} week{'s' if int(weeks) > 1 else ''} ago"
    months = days / 30.437
    if months < 12: return f"{int(months)} month{'s' if int(months) > 1 else ''} ago"
    years = days / 365.25
    return f"{int(years)} year{'s' if int(years) > 1 else ''} ago"

def seed_plans():
    """Seeds the database with default subscription plans if none exist."""
    from .models import SubscriptionPlan # Import locally inside function
    from sqlalchemy import inspect # Import inspect locally
    try:
        inspector = inspect(db.engine)
        # Check if the table exists before querying
        if inspector.has_table(SubscriptionPlan.__tablename__):
            if SubscriptionPlan.query.count() == 0:
                print("Seeding subscription plans...")
                # Define plans (ensure price is integer, e.g., paise/cents)
                free_plan = SubscriptionPlan(
                    plan_id='free', name='Free', price=0, competitors_limit=2,
                    keyword_searches_limit=5, ai_generations_limit=3, playlist_suggestions_limit=3, has_comment_reply=False
                )
                creator_plan = SubscriptionPlan(
                    plan_id='creator', name='Creator', price=39900, slashed_price=79900,
                    competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
                    has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=10,
                    is_popular=True, has_comment_reply=False # Add default for new field
                )
                pro_plan = SubscriptionPlan(
                    plan_id='pro', name='Pro', price=99900, slashed_price=199900,
                    competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1,
                    has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=-1,
                    has_comment_reply=True # Add default for new field
                )
                db.session.add_all([free_plan, creator_plan, pro_plan])
                db.session.commit()
                print("Plans seeded successfully.")
        else:
            print("SubscriptionPlan table does not exist. Skipping seeding.")
    except OperationalError as e:
        # Catch errors if DB is not ready during initial setup
        print(f"Skipping seed_plans due to database error: {e}")
        db.session.rollback()
    except Exception as e:
        print(f"Error seeding plans: {e}")
        db.session.rollback() # Rollback on any other error during seeding
