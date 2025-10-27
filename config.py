# config.py

import os
from dotenv import load_dotenv

# .env फ़ाइल से एनवायरनमेंट वेरिएबल्स लोड करें
load_dotenv()

class Config:
    """Base configuration class."""
    
    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-local-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Google Analytics
    MEASUREMENT_ID = os.environ.get('MEASUREMENT_ID')

    # OAuth Settings
    # This should be inside a debug check in production
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///local_dev.db'

    # Cashfree Payment Gateway
    CASHFREE_APP_ID = os.environ.get('CASHFREE_APP_ID')
    CASHFREE_SECRET_KEY = os.environ.get('CASHFREE_SECRET_KEY')
    CASHFREE_ENV = os.environ.get('CASHFREE_ENV', 'PROD')

    # Celery Configuration (Corrected)
    CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
