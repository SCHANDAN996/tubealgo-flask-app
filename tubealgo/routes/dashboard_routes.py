# tubealgo/routes/dashboard_routes.py

from flask import render_template, request, redirect, url_for, flash, Blueprint, jsonify, abort, session
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, YouTubeChannel, get_setting, ChannelSnapshot, log_system_event, Goal, DashboardCache
from tubealgo.services.youtube_fetcher import analyze_channel, get_latest_videos
from tubealgo.services.ai_service import get_ai_video_suggestions
from tubealgo.services.youtube_manager import get_user_videos
from .utils import get_credentials
from datetime import date, timedelta, datetime
import random
import json
import traceback

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.channel:
        return render_template('dashboard.html', channel=None)
    return render_template('dashboard.html', channel=current_user.channel)


@dashboard_bp.route('/api/dashboard/main-data')
@login_required
def main_dashboard_data():
    if not current_user.channel:
        return jsonify({'error': 'Channel not connected'}), 404

    cache_entry = DashboardCache.query.filter_by(user_id=current_user.id).first()

    if cache_entry and cache_entry.data:
        print(f"Dashboard Cache HIT for user {current_user.email}")
        return jsonify(cache_entry.data)
    
    print(f"Dashboard Cache MISS for user {current_user.email}. Performing a one-time live fetch and caching the result.")
    
    try:
        channel_id = current_user.channel.id
        channel_data = analyze_channel(current_user.channel.channel_id_youtube)
        if 'error' in channel_data:
            raise Exception(channel_data['error'])

        today = date.today()
        yesterday = today - timedelta(days=1)
        yesterday_snapshot = ChannelSnapshot.query.filter_by(channel_db_id=channel_id, date=yesterday).first()
        kpis = {
            'subscribers': channel_data.get('Subscribers', 0),
            'views': channel_data.get('Total Views', 0),
            'videos': channel_data.get('Video Count', 0),
            'subscribers_change': channel_data.get('Subscribers', 0) - yesterday_snapshot.subscribers if yesterday_snapshot else 0,
            'views_change': channel_data.get('Total Views', 0) - yesterday_snapshot.views if yesterday_snapshot else 0
        }
        
        start_date = today - timedelta(days=29)
        snapshots = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date >= start_date).order_by(ChannelSnapshot.date.asc()).all()
        labels = [(start_date + timedelta(days=i)).strftime('%d %b') for i in range(30)]
        sub_data, view_data, last_subs, last_views = [], [], 0, 0
        first_snapshot = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date < start_date).order_by(ChannelSnapshot.date.desc()).first()
        if first_snapshot:
            last_subs, last_views = first_snapshot.subscribers, first_snapshot.views
        elif snapshots:
            last_subs, last_views = snapshots[0].subscribers, snapshots[0].views
        snapshot_dict = {s.date: s for s in snapshots}
        for i in range(30):
            current_date = start_date + timedelta(days=i)
            if current_date in snapshot_dict:
                last_subs, last_views = snapshot_dict[current_date].subscribers, snapshot_dict[current_date].views
            sub_data.append(last_subs)
            view_data.append(last_views)
        growth_chart_data = {'labels': labels, 'subscribers': sub_data, 'views': view_data}

        # --- Authentication Fix ---
        all_user_videos = []
        creds = get_credentials()
        if creds:
            videos_data = get_user_videos(creds)
            if 'error' not in videos_data:
                all_user_videos = videos_data
        
        # Fallback if OAuth fails or is not available
        if not all_user_videos:
            print("INFO: Falling back to public API for user videos. Private/Unlisted videos will not be shown.")
            videos_data = get_latest_videos(current_user.channel.channel_id_youtube, max_results=50)
            all_user_videos = videos_data.get('videos', [])
        
        latest_video = all_user_videos[0] if all_user_videos else None
        if latest_video and len(all_user_videos) > 1:
            other_videos = all_user_videos[1:10]
            avg_views = sum(v['view_count'] for v in other_videos) / len(other_videos) if other_videos else 0
            performance = round(((latest_video['view_count'] - avg_views) / avg_views) * 100) if avg_views > 0 else 100
            latest_video['performance_vs_avg'] = performance
        elif latest_video:
            latest_video['performance_vs_avg'] = 100
        
        top_videos = sorted([v for v in all_user_videos if 'view_count' in v], key=lambda x: x['view_count'], reverse=True)[:3]
        ai_suggestions = get_ai_video_suggestions(current_user, user_videos=all_user_videos)
        
        live_data = {
            'kpis': kpis, 
            'growth_chart': growth_chart_data,
            'latest_video': latest_video,
            'top_videos': top_videos,
            'ai_suggestions': ai_suggestions
        }

        # --- Database Fix ---
        cache_entry = DashboardCache.query.filter_by(user_id=current_user.id).first()
        if not cache_entry:
            cache_entry = DashboardCache(user_id=current_user.id)
            db.session.add(cache_entry)
        
        cache_entry.data = live_data
        cache_entry.updated_at = datetime.utcnow()
        db.session.commit()
        print(f"Live data fetched and SAVED to DashboardCache for user {current_user.email}")

        return jsonify(live_data)

    except Exception as e:
        # Rollback the session to prevent PendingRollbackError
        db.session.rollback()
        tb_str = traceback.format_exc()
        log_system_event(f"Dashboard one-time live fetch failed: {str(e)}", "ERROR", {'user_id': current_user.id, 'traceback': tb_str})
        return jsonify({'error': 'Could not load live data. Your dashboard will be ready soon.'}), 500


@dashboard_bp.route('/referrals')
@login_required
def referrals():
    if not get_setting('feature_referral_system', True):
        abort(404)
    base_url = request.url_root.replace('http://', 'https://')
    referral_link = f"{base_url}?ref={current_user.referral_code}"
    return render_template('referrals.html', referral_link=referral_link, active_page='referrals')

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
    flash('Your channel has been connected successfully! Your dashboard is being prepared.', 'success')
    return redirect(url_for('dashboard.dashboard'))