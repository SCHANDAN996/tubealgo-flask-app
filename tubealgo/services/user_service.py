# tubealgo/services/user_service.py

import os
from googleapiclient.discovery import build
from flask_login import current_user
from .. import db
from ..models import User, YouTubeChannel
import secrets
from datetime import datetime

def generate_referral_code():
    """एक यूनिक रेफरल कोड बनाता है।"""
    while True:
        code = secrets.token_hex(4).upper()
        if not User.query.filter_by(referral_code=code).first():
            return code

def create_new_user(email, password=None, referred_by_code=None):
    """
    एक नया यूजर बनाने और उसे डेटाबेस में सेव करने के लिए सेंट्रलाइज्ड फंक्शन।
    यह (user, message, category) का एक टपल लौटाता है।
    """
    if User.query.filter_by(email=email).first():
        return None, 'This email is already registered.', 'error'

    is_first_user = User.query.count() == 0
    
    new_user = User(email=email.lower(), referral_code=generate_referral_code())

    if password:
        new_user.set_password(password)
    else:
        new_user.set_password(os.urandom(16).hex())

    if is_first_user:
        new_user.is_admin = True

    if referred_by_code:
        referrer = User.query.filter_by(referral_code=referred_by_code).first()
        if referrer:
            new_user.referred_by = referred_by_code
    
    db.session.add(new_user)
    db.session.commit()

    if is_first_user:
        message = 'Congratulations! You are the first user and have been granted admin privileges.'
    else:
        message = 'Your account has been created successfully.'
        
    return new_user, message, 'success'


def process_google_login(credentials, flow_type):
    """
    Google credentials से यूजर को प्रोसेस करता है।
    यह अब पहले से लॉग इन यूज़र को प्राथमिकता देता है।
    """
    try:
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        email_from_google = user_info.get('email').lower() # ईमेल को हमेशा लोअरकेस में रखें

        if not email_from_google:
            return None, "Could not retrieve email from Google.", "error"

        user = None
        # --- FIXED LOGIC START ---
        # 1. पहले जांचें कि क्या कोई यूज़र पहले से लॉग इन है
        if current_user.is_authenticated:
            # अगर लॉग इन यूज़र का ईमेल गूगल से मिले ईमेल से मेल खाता है, तो उसी यूज़र का उपयोग करें
            if current_user.email == email_from_google:
                user = current_user
            else:
                # अगर ईमेल मेल नहीं खाता है, तो एरर दिखाएं
                return None, "The logged-in user's email does not match the Google account's email.", "error"
        
        # 2. अगर कोई यूज़र लॉग इन नहीं है, तो ईमेल से उसे ढूंढें
        if not user:
            user = User.query.filter_by(email=email_from_google).first()
        
        # 3. अगर यूज़र अभी भी नहीं मिला, तो एक नया बनाएं
        if not user:
            user, message, category = create_new_user(email=email_from_google)
            if not user:
                return None, message, category
        # --- FIXED LOGIC END ---
        
        # क्रेडेंशियल्स को डेटाबेस में सेव करें
        if credentials.refresh_token:
            user.google_refresh_token = credentials.refresh_token
        user.google_access_token = credentials.token
        user.google_token_expiry = credentials.expiry
        db.session.commit()

        message = 'Logged in successfully!'
        category = 'success'

        # अगर यह YouTube कनेक्शन फ्लो है, तो चैनल को सिंक करें
        if flow_type == 'youtube':
            youtube_service = build('youtube', 'v3', credentials=credentials)
            channels_response = youtube_service.channels().list(mine=True, part='snippet').execute()

            if channels_response.get('items'):
                channel_info = channels_response['items'][0]
                user_channel = user.channel
                if not user_channel:
                    user_channel = YouTubeChannel(user_id=user.id)
                    db.session.add(user_channel)
                
                user_channel.channel_id_youtube = channel_info['id']
                user_channel.channel_title = channel_info['snippet']['title']
                user_channel.thumbnail_url = channel_info['snippet']['thumbnails']['default']['url']
                db.session.commit()
                
                message = 'Logged in and connected your channel successfully!'
            else:
                message = 'Logged in successfully, but no YouTube channel was found.'
                category = 'warning'
        
        if user.is_admin and not message.startswith('Congratulations'):
             message = 'Welcome back, Admin! Logged in successfully.'

        return user, message, category

    except Exception as e:
        db.session.rollback()
        return None, f'An error occurred while connecting your account: {e}', 'error'