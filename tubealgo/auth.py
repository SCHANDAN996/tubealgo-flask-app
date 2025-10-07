import os
import secrets
from flask import render_template, request, redirect, url_for, flash, Blueprint, session
from flask_login import login_user, logout_user, current_user, login_required
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from . import db, limiter
from .models import User, YouTubeChannel, get_config_value
from .forms import SignupForm, LoginForm

auth = Blueprint('auth', __name__)

SCOPES = ['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid', 'https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.upload']

def generate_referral_code():
    while True:
        code = secrets.token_hex(4).upper()
        if not User.query.filter_by(referral_code=code).first():
            return code

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


@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
        
    form = SignupForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data.lower()).first()
        if existing_user:
            flash('This email is already registered.', 'error')
            return redirect(url_for('auth.signup'))
            
        new_user = User(email=form.email.data.lower(), referral_code=generate_referral_code())
        new_user.set_password(form.password.data)

        # --- यहाँ नया लॉजिक जोड़ा गया है ---
        # पहले एडमिन को स्वचालित रूप से सेट करने के लिए जाँच करें
        is_first_user = User.query.count() == 0
        if is_first_user:
            new_user.is_admin = True
            flash('Congratulations! You are the first user and have been granted admin privileges.', 'success')
        # --- बदलाव खत्म ---

        if 'referral_code' in session:
            referrer = User.query.filter_by(referral_code=session['referral_code']).first()
            if referrer:
                new_user.referred_by = session['referral_code']
            session.pop('referral_code', None)
            
        db.session.add(new_user)
        db.session.commit()
        
        if not is_first_user:
            flash('Your account has been created successfully.', 'success')
            
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
    session.pop('credentials', None)
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('core.home'))

@auth.route('/login/google')
def google_login():
    CLIENT_SECRETS_FILE = {
        "web": {
            "client_id": get_config_value("GOOGLE_CLIENT_ID"),
            "client_secret": get_config_value("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    }
    flow = Flow.from_client_config(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=url_for('auth.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@auth.route('/callback')
def google_callback():
    state = session.get('state')
    if not state:
        return 'State not found in session.', 400
    
    CLIENT_SECRETS_FILE = {
        "web": {
            "client_id": get_config_value("GOOGLE_CLIENT_ID"),
            "client_secret": get_config_value("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    }
    flow = Flow.from_client_config(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state, redirect_uri=url_for('auth.google_callback', _external=True))
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f"Error fetching Google token: {e}", "error")
        return redirect(url_for('auth.login'))
        
    credentials = flow.credentials
    
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    user_info_service = build('oauth2', 'v2', credentials=credentials)
    user_info = user_info_service.userinfo().get().execute()
    email = user_info.get('email')
    if not email:
        flash("Could not retrieve email from Google.", "error")
        return redirect(url_for('auth.login'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        is_first_user = User.query.count() == 0
        user = User(email=email, referral_code=generate_referral_code())
        user.set_password(os.urandom(16).hex())
        if is_first_user:
            user.is_admin = True
        db.session.add(user)
        db.session.commit()
        if is_first_user:
            flash('Congratulations! You are the first user and have been granted admin privileges.', 'success')
        
    login_user(user)
    
    try:
        youtube_service = build('youtube', 'v3', credentials=credentials)
        channels_response = youtube_service.channels().list(mine=True, part='snippet').execute()
        if channels_response.get('items'):
            channel_info = channels_response['items'][0]
            user_channel = current_user.channel
            if not user_channel:
                user_channel = YouTubeChannel(user_id=current_user.id)
                db.session.add(user_channel)
            user_channel.channel_id_youtube = channel_info['id']
            user_channel.channel_title = channel_info['snippet']['title']
            user_channel.thumbnail_url = channel_info['snippet']['thumbnails']['default']['url']
            db.session.commit()
            flash('Logged in and connected your channel successfully!', 'success')
        else:
            flash('Logged in successfully, but no YouTube channel was found.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while connecting your channel: {e}', 'error')
        
    return redirect(url_for('dashboard.dashboard'))