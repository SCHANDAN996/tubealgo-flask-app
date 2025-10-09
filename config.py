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
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # Development only, disable in production if possible

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///local_dev.db'

    # Cashfree Payment Gateway
    CASHFREE_APP_ID = os.environ.get('CASHFREE_APP_ID')
    CASHFREE_SECRET_KEY = os.environ.get('CASHFREE_SECRET_KEY')
    CASHFREE_ENV = os.environ.get('CASHFREE_ENV', 'PROD')