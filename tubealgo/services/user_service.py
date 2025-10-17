# tubealgo/services/user_service.py

import os
from googleapiclient.discovery import build
from flask_login import current_user
from .. import db
from ..models import User, YouTubeChannel
import secrets
from datetime import datetime

def generate_referral_code():
    while True:
        code = secrets.token_hex(4).upper()
        if not User.query.filter_by(referral_code=code).first():
            return code

def create_new_user(email, password=None, referred_by_code=None):
    existing_user = User.query.filter_by(email=email.lower().strip()).first()
    if existing_user:
        return None, 'This email is already registered.', 'error'
    is_first_user = User.query.count() == 0
    new_user = User(email=email.lower().strip(), referral_code=generate_referral_code())
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
    message = 'Congratulations! You are the first user and have been granted admin privileges.' if is_first_user else 'Your account has been created successfully.'
    return new_user, message, 'success'

def process_google_login(credentials, flow_type):
    try:
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        email_from_google = user_info.get('email', '').lower().strip()
        picture_url = user_info.get('picture') # <-- यह लाइन जोड़ी गई है

        if not email_from_google:
            return None, "Could not retrieve email from Google.", "error"

        user = None
        if current_user.is_authenticated:
            user = current_user
        
        if not user:
            user = User.query.filter_by(email=email_from_google).first()
        
        if not user:
            user, message, category = create_new_user(email=email_from_google)
            if not user:
                return None, message, category

        if credentials.refresh_token:
            user.google_refresh_token = credentials.refresh_token
        user.google_access_token = credentials.token
        user.google_token_expiry = credentials.expiry
        user.profile_pic_url = picture_url # <-- यह लाइन जोड़ी गई है
        db.session.commit()

        message = 'Logged in successfully!'
        category = 'success'

        if flow_type == 'youtube':
            youtube_service = build('youtube', 'v3', credentials=credentials)
            channels_response = youtube_service.channels().list(mine=True, part='snippet').execute()

            if channels_response.get('items'):
                channel_info = channels_response['items'][0]
                channel_id_from_google = channel_info['id']

                existing_link = YouTubeChannel.query.filter_by(channel_id_youtube=channel_id_from_google).first()
                if existing_link and existing_link.user_id != user.id:
                    db.session.rollback()
                    return None, "This YouTube channel is already connected to another TubeAlgo account.", "error"

                user_channel = user.channel
                if not user_channel:
                    user_channel = YouTubeChannel(user_id=user.id)
                    db.session.add(user_channel)
                
                user_channel.channel_id_youtube = channel_id_from_google
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
        if "UNIQUE constraint failed" in str(e):
             return None, "This YouTube channel is already connected to a TubeAlgo account.", "error"
        return None, f'An error occurred while connecting your account: {e}', 'error'