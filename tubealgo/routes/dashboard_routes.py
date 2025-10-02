# Filepath: tubealgo/routes/dashboard_routes.py

from flask import render_template, request, redirect, url_for, flash, Blueprint, abort
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, YouTubeChannel, get_setting # <-- get_setting को इम्पोर्ट करें
from tubealgo.services.youtube_fetcher import analyze_channel
from tubealgo.services.openai_service import get_ai_video_suggestions

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    user_channel = current_user.channel
    channel_data = None
    ai_suggestions = None
    
    if user_channel:
        channel_data = analyze_channel(user_channel.channel_id_youtube)
    
    ai_suggestions = get_ai_video_suggestions(current_user)
    
    return render_template('dashboard.html', 
                           channel=user_channel, 
                           data=channel_data, 
                           ai_suggestions=ai_suggestions,
                           active_page='dashboard')

@dashboard_bp.route('/referrals')
@login_required
def referrals():
    # --- यह लाइन अपडेट करें ---
    if not get_setting('feature_referral_system', True):
        abort(404)
    # --- यहाँ तक ---

    base_url = request.url_root.replace('http://', 'https://')
    referral_link = f"{base_url}?ref={current_user.referral_code}"
    return render_template('referrals.html', 
                           referral_link=referral_link, 
                           active_page='referrals')

@dashboard_bp.route('/connect_channel', methods=['POST'])
@login_required
def connect_channel():
    channel_url = request.form.get('channel_url')
    if not channel_url:
        flash('Please enter a channel URL.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    analysis_data = analyze_channel(channel_url)
    if 'error' in analysis_data:
        flash(analysis_data['error'], 'error')
        return redirect(url_for('dashboard.dashboard'))

    existing_channel = current_user.channel
    if existing_channel:
        existing_channel.channel_id_youtube = analysis_data['id']
        existing_channel.channel_title = analysis_data['Title']
        existing_channel.thumbnail_url = analysis_data['Thumbnail URL']
    else:
        new_channel = YouTubeChannel(user_id=current_user.id, 
                                     channel_id_youtube=analysis_data['id'], 
                                     channel_title=analysis_data['Title'], 
                                     thumbnail_url=analysis_data['Thumbnail URL'])
        db.session.add(new_channel)
    
    db.session.commit()
    flash('Your channel has been connected successfully!', 'success')
    return redirect(url_for('dashboard.dashboard'))