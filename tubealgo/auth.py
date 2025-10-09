# tubealgo/auth.py

import os
import secrets
from flask import render_template, request, redirect, url_for, flash, Blueprint, session
from flask_login import login_user, logout_user, current_user, login_required
from google_auth_oauthlib.flow import Flow
from datetime import datetime
from . import db
from .models import User, get_config_value
from .forms import SignupForm, LoginForm
from .services import user_service

auth = Blueprint('auth', __name__)

# --- SCOPES को दो भागों में बांटा गया ---
LOGIN_SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'https://www.googleapis.com/auth/userinfo.profile', 
    'openid'
]
YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube', 
    'https://www.googleapis.com/auth/youtube.upload'
]

def get_flow(scopes, redirect_uri):
    """Helper function to create a Google Auth Flow."""
    CLIENT_SECRETS_FILE = {
        "web": {
            "client_id": get_config_value("GOOGLE_CLIENT_ID"),
            "client_secret": get_config_value("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    }
    return Flow.from_client_config(CLIENT_SECRETS_FILE, scopes=scopes, redirect_uri=redirect_uri)

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
        
    form = SignupForm()
    if form.validate_on_submit():
        referral_code = session.pop('referral_code', None)
        new_user, message, category = user_service.create_new_user(
            email=form.email.data,
            password=form.password.data,
            referred_by_code=referral_code
        )
        if not new_user:
            flash(message, category)
            return redirect(url_for('auth.signup'))
        
        flash(message, category)
        return redirect(url_for('auth.login'))
        
    return render_template('signup.html', form=form)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'error')
            return render_template('login.html', form=form)
    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    session.clear() 
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('core.home'))

@auth.route('/login/google')
def google_login():
    flow = get_flow(LOGIN_SCOPES, url_for('auth.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    session['flow_type'] = 'login'
    return redirect(authorization_url)

@auth.route('/connect/youtube')
@login_required
def connect_youtube():
    # --- FIXED: Removed the database query for 'GoogleApiScope' ---
    # We will use the hardcoded YOUTUBE_SCOPES list directly.
    flow = get_flow(YOUTUBE_SCOPES, url_for('auth.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    session['flow_type'] = 'youtube'
    return redirect(authorization_url)

@auth.route('/callback')
def google_callback():
    state = session.get('state')
    flow_type = session.get('flow_type', 'login')
    
    if not state:
        flash('The authentication state is missing. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    scopes_to_use = YOUTUBE_SCOPES if flow_type == 'youtube' else LOGIN_SCOPES
    flow = get_flow(scopes_to_use, url_for('auth.google_callback', _external=True))
    
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f"Error fetching Google token: {e}", "error")
        return redirect(url_for('auth.login'))
        
    credentials = flow.credentials
    user, message, category = user_service.process_google_login(credentials, flow_type)

    if user:
        login_user(user)
        flash(message, category)
        return redirect(url_for('dashboard.dashboard'))
    else:
        flash(message, category)
        return redirect(url_for('auth.login'))

@auth.route('/connect_telegram/<telegram_chat_id>')
@login_required
def connect_telegram(telegram_chat_id):
    if not telegram_chat_id or not telegram_chat_id.isdigit():
        flash('Invalid Telegram connection link.', 'error')
        return redirect(url_for('settings.telegram_settings'))

    existing_user = User.query.filter(User.id != current_user.id, User.telegram_chat_id == telegram_chat_id).first()
    if existing_user:
        flash('This Telegram account is already linked to another user.', 'error')
        return redirect(url_for('settings.telegram_settings'))
    
    current_user.telegram_chat_id = telegram_chat_id
    db.session.commit()
    
    from .services.notification_service import send_telegram_message
    message = "🎉 Your Telegram account has been successfully connected to your TubeAlgo account!"
    send_telegram_message(telegram_chat_id, message)
    
    flash('Your Telegram account has been connected successfully!', 'success')
    return redirect(url_for('settings.telegram_settings'))