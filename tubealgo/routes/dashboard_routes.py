from flask import render_template, request, redirect, url_for, flash, Blueprint, jsonify, abort, session
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, YouTubeChannel, ChannelSnapshot, log_system_event, Goal, DashboardCache, Competitor
from tubealgo.services.youtube_fetcher import analyze_channel, get_latest_videos
from tubealgo.services.ai_service import get_ai_video_suggestions
from tubealgo.services.youtube_manager import get_user_videos
from .utils import get_credentials
from datetime import date, timedelta, datetime, timezone
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

    if cache_entry and cache_entry.data and (datetime.utcnow() - cache_entry.updated_at).total_seconds() < 14400:
        return jsonify(cache_entry.data)
    
    try:
        channel_id = current_user.channel.id
        
        channel_data = analyze_channel(current_user.channel.channel_id_youtube)
        if 'error' in channel_data:
            raise Exception(channel_data['error'])

        kpis = {
            'subscribers': channel_data.get('Subscribers', 0),
            'views': channel_data.get('Total Views', 0),
            'videos': channel_data.get('Video Count', 0),
        }
        
        today = date.today()
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

        # ========= 'Top Recent Videos' का नया लॉजिक START =========
        top_recent_videos = []
        competitors = current_user.competitors.limit(5).all()
        all_recent_competitor_videos = []
        if competitors:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            for comp in competitors:
                comp_videos_data = get_latest_videos(comp.channel_id_youtube, max_results=20)
                if comp_videos_data and 'videos' in comp_videos_data:
                    for video in comp_videos_data['videos']:
                        upload_date = datetime.fromisoformat(video['upload_date'].replace('Z', '+00:00'))
                        if upload_date > thirty_days_ago:
                            video['channel_title'] = comp.channel_title
                            all_recent_competitor_videos.append(video)
            
            if all_recent_competitor_videos:
                top_recent_videos = sorted(all_recent_competitor_videos, key=lambda x: x.get('view_count', 0), reverse=True)[:4]
        # ========= 'Top Recent Videos' का नया लॉजिक END =========

        goal_data = None
        active_goal = Goal.query.filter_by(user_id=current_user.id, is_active=True).first()
        if active_goal:
            current_value = 0
            if active_goal.goal_type == 'subscribers':
                current_value = kpis['subscribers']
            elif active_goal.goal_type == 'views':
                current_value = kpis['views']
            
            progress_percentage = 0
            if active_goal.target_value > active_goal.start_value:
                progress_percentage = ((current_value - active_goal.start_value) / (active_goal.target_value - active_goal.start_value)) * 100

            goal_data = {
                'goal_type': active_goal.goal_type,
                'target_value': active_goal.target_value,
                'current_value': current_value,
                'target_date': active_goal.target_date.isoformat() if active_goal.target_date else None,
                'progress_percentage': min(100, max(0, progress_percentage)),
                'projection_text': "🚀 Keep up the great work!"
            }

        ai_assistant_suggestions = []
        if top_recent_videos:
            top_topic_title = top_recent_videos[0]['title']
            ai_assistant_suggestions.append({
                "type": "topic",
                "title": "Popular Topic",
                "text": f"Your competitors are finding success with recent videos like '{top_topic_title[:50]}...'. Consider making a video on a similar topic."
            })
        
        ai_assistant_suggestions.append({
            "type": "consistency",
            "title": "Consistency Tip",
            "text": "Uploading a new video every week can boost your channel's momentum. Plan your next upload now!"
        })

        live_data = {
            'kpis': kpis, 
            'growth_chart': growth_chart_data,
            'ai_assistant': ai_assistant_suggestions,
            'top_recent_videos': top_recent_videos,
            'goal': goal_data
        }

        if not cache_entry:
            cache_entry = DashboardCache(user_id=current_user.id)
            db.session.add(cache_entry)
        
        cache_entry.data = live_data
        cache_entry.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify(live_data)

    except Exception as e:
        tb_str = traceback.format_exc()
        log_system_event(f"Dashboard live fetch failed: {str(e)}", "ERROR", {'user_id': current_user.id, 'traceback': tb_str})
        if cache_entry and cache_entry.data:
            return jsonify(cache_entry.data)
        return jsonify({'error': 'Could not load your dashboard data at this time. Please try again later.'}), 500


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