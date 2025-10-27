# tubealgo/__init__.py
"""
TubeAlgo Application Factory
Complete rewrite with Redis/Celery disabled for free tier
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
import os
import logging
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()

# Simple in-memory cache (Redis replacement)
from tubealgo.services.simple_cache import cache


def create_app(config_name=None):
    """
    Application factory pattern
    """
    app = Flask(__name__)
    
    # ============================================
    # Configuration
    # ============================================
    
    # Basic config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        # Fix for Render.com - postgres:// -> postgresql://
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///tubealgo.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Security
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit
    app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 2592000  # 30 days
    
    # File upload
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max
    app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')
    
    # API Keys
    app.config['YOUTUBE_API_KEYS'] = os.environ.get('YOUTUBE_API_KEYS', '').split(',')
    app.config['GEMINI_API_KEY'] = os.environ.get('GEMINI_API_KEY', '')
    app.config['TELEGRAM_BOT_TOKEN'] = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    
    # Payment gateways
    app.config['CASHFREE_APP_ID'] = os.environ.get('CASHFREE_APP_ID', '')
    app.config['CASHFREE_SECRET_KEY'] = os.environ.get('CASHFREE_SECRET_KEY', '')
    app.config['CASHFREE_ENV'] = os.environ.get('CASHFREE_ENV', 'TEST')
    
    # ============================================
    # REDIS/CELERY - DISABLED FOR FREE TIER
    # ============================================
    # Uncomment these when you upgrade to paid tier with Redis
    
    # redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    # app.config['CELERY_BROKER_URL'] = redis_url
    # app.config['CELERY_RESULT_BACKEND'] = redis_url
    # app.config['CACHE_TYPE'] = 'redis'
    # app.config['CACHE_REDIS_URL'] = redis_url
    
    # Temporary: Use simple in-memory cache
    app.config['CACHE_TYPE'] = 'simple'
    
    # ============================================
    # Initialize Extensions
    # ============================================
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Login manager settings
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from tubealgo.models.user_models import User
        return User.query.get(int(user_id))
    
    # ============================================
    # Logging Setup
    # ============================================
    
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/tubealgo.log',
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('TubeAlgo startup')
    
    # ============================================
    # Register Blueprints
    # ============================================
    
    # Core routes
    from tubealgo.routes.core_routes import core_bp
    app.register_blueprint(core_bp)
    
    # Authentication
    from tubealgo.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    # Dashboard
    from tubealgo.routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    # Analysis
    from tubealgo.routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp)
    
    # Tools
    from tubealgo.routes.tool_routes import tool_bp
    app.register_blueprint(tool_bp)
    
    # Competitors
    from tubealgo.routes.competitor_routes import competitor_bp
    app.register_blueprint(competitor_bp)
    
    # Video Analytics
    from tubealgo.routes.video_analytics_routes import video_analytics_bp
    app.register_blueprint(video_analytics_bp)
    
    # YouTube Manager
    from tubealgo.routes.manager_routes import manager_bp
    app.register_blueprint(manager_bp)
    
    from tubealgo.routes.video_manager_routes import video_manager_bp
    app.register_blueprint(video_manager_bp)
    
    from tubealgo.routes.playlist_manager_routes import playlist_manager_bp
    app.register_blueprint(playlist_manager_bp)
    
    # Content Planner
    from tubealgo.routes.planner_routes import planner_bp
    app.register_blueprint(planner_bp)
    
    # AI Routes
    from tubealgo.routes.ai_api_routes import ai_api_bp
    app.register_blueprint(ai_api_bp)
    
    # API Routes
    from tubealgo.routes.api_routes import api_bp
    app.register_blueprint(api_bp)
    
    # User Routes
    from tubealgo.routes.user_routes import user_bp
    app.register_blueprint(user_bp)
    
    # Settings
    from tubealgo.routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp)
    
    # Payment Routes
    from tubealgo.routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp)
    
    # Report Routes
    from tubealgo.routes.report_routes import report_bp
    app.register_blueprint(report_bp)
    
    # Goal Routes
    from tubealgo.routes.goal_routes import goal_bp
    app.register_blueprint(goal_bp)
    
    # A/B Test Routes
    from tubealgo.routes.ab_test_routes import ab_test_bp
    app.register_blueprint(ab_test_bp)
    
    # Admin Routes
    from tubealgo.routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # ============================================
    # Error Handlers
    # ============================================
    
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template, jsonify, request
        if request.is_json:
            return jsonify({'error': 'Forbidden'}), 403
        return render_template('errors/403.html'), 403
    
    # ============================================
    # Template Filters
    # ============================================
    
    @app.template_filter('format_number')
    def format_number(value):
        """Format number with commas"""
        try:
            return "{:,}".format(int(value))
        except (ValueError, TypeError):
            return value
    
    @app.template_filter('format_duration')
    def format_duration(seconds):
        """Format duration from seconds to HH:MM:SS"""
        try:
            seconds = int(seconds)
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes}:{secs:02d}"
        except (ValueError, TypeError):
            return "0:00"
    
    @app.template_filter('time_ago')
    def time_ago(dt):
        """Format datetime as time ago"""
        from datetime import datetime, timezone
        
        if not dt:
            return ""
        
        # Ensure timezone aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days}d ago"
        else:
            return dt.strftime('%b %d, %Y')
    
    # ============================================
    # Context Processors
    # ============================================
    
    @app.context_processor
    def inject_global_data():
        """Inject data available in all templates"""
        from flask import request
        from datetime import datetime
        
        return {
            'current_year': datetime.now().year,
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'app_name': 'TubeAlgo',
            'app_version': '2.0.0',
            'request_path': request.path
        }
    
    # ============================================
    # Startup Tasks
    # ============================================
    
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Initialize default data
        from tubealgo.models.user_models import Plan
        
        # Check if default plans exist
        if Plan.query.count() == 0:
            # Create default plans
            plans = [
                Plan(
                    name='Free',
                    price=0,
                    currency='INR',
                    features={
                        'daily_searches': 10,
                        'competitor_tracking': 2,
                        'ai_generations': 5,
                        'video_analysis': 10,
                        'advanced_analytics': False
                    },
                    is_active=True
                ),
                Plan(
                    name='Basic',
                    price=499,
                    currency='INR',
                    features={
                        'daily_searches': 50,
                        'competitor_tracking': 5,
                        'ai_generations': 50,
                        'video_analysis': 100,
                        'advanced_analytics': True,
                        'bulk_operations': True
                    },
                    is_active=True
                ),
                Plan(
                    name='Pro',
                    price=999,
                    currency='INR',
                    features={
                        'daily_searches': -1,  # Unlimited
                        'competitor_tracking': 20,
                        'ai_generations': 500,
                        'video_analysis': -1,  # Unlimited
                        'advanced_analytics': True,
                        'bulk_operations': True,
                        'priority_support': True,
                        'api_access': True
                    },
                    is_active=True
                )
            ]
            
            for plan in plans:
                db.session.add(plan)
            
            db.session.commit()
            app.logger.info('Default plans created')
    
    app.logger.info('TubeAlgo application initialized successfully')
    
    return app


# ============================================
# Celery Configuration (Disabled)
# ============================================

# Uncomment when Redis is available:

# def make_celery(app):
#     """Create Celery instance"""
#     from celery import Celery
#     
#     celery = Celery(
#         app.import_name,
#         backend=app.config['CELERY_RESULT_BACKEND'],
#         broker=app.config['CELERY_BROKER_URL']
#     )
#     celery.conf.update(app.config)
#     
#     class ContextTask(celery.Task):
#         def __call__(self, *args, **kwargs):
#             with app.app_context():
#                 return self.run(*args, **kwargs)
#     
#     celery.Task = ContextTask
#     return celery

# Temporary: No Celery
celery = None
