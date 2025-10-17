# tubealgo/routes/api_routes.py

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from tubealgo.models import Competitor, ChannelSnapshot
from tubealgo.services.cache_manager import get_from_cache, set_to_cache
from tubealgo.services.youtube_fetcher import (
    analyze_channel, get_latest_videos, get_most_viewed_videos, 
    get_channel_main_category, search_for_channels, get_video_details,
    get_channel_playlists, get_most_used_tags, get_all_channel_videos
)
import json
from datetime import date, timedelta

api_bp = Blueprint('api', __name__, url_prefix='/api')

def get_full_competitor_package(competitor_id, force_refresh=False):
    """
    Fetches ALL data for a competitor, including growth stats.
    """
    cache_key = f"competitor_package_v5:{competitor_id}" # Version updated for new growth stats
    if not force_refresh:
        cached_data = get_from_cache(cache_key)
        if cached_data:
            return cached_data

    comp = Competitor.query.get_or_404(competitor_id)

    details = analyze_channel(comp.channel_id_youtube)
    if 'error' in details:
        return {'error': details['error']}

    # ===== Growth Data Calculation Logic =====
    growth_data = { '1d': None, '7d': None }
    
    # This logic assumes that a background job is taking daily snapshots for competitors as well.
    # To implement this, your `take_daily_snapshots` job in `jobs.py` needs to be modified
    # to iterate through all competitors in the database, not just user's main channels.
    # For now, this is a placeholder. If snapshots for competitors are not being taken,
    # this will correctly return `None` and the frontend will show "Tracking started...".
    
    # Placeholder logic - this part needs a background job to be fully effective.
    # Let's assume for now that the snapshots are not available.
    
    # ==========================================

    latest_videos_all = get_all_channel_videos(comp.channel_id_youtube)
    if isinstance(latest_videos_all, dict) and 'error' in latest_videos_all:
         return {'error': latest_videos_all['error']}

    most_viewed_data_api = get_most_viewed_videos(comp.channel_id_youtube, max_results=50)
    most_viewed_videos_all = most_viewed_data_api.get('videos', [])

    all_videos_dict = {}
    for video in (latest_videos_all + most_viewed_videos_all):
        if video and 'id' in video:
            all_videos_dict[video['id']] = video
    
    all_videos_unique = list(all_videos_dict.values())

    recent_videos_data = {
        'videos': sorted(all_videos_unique, key=lambda x: x.get('upload_date', ''), reverse=True),
        'nextPageToken': None
    }
    
    most_viewed_videos_data = {
        'videos': sorted(all_videos_unique, key=lambda x: x.get('view_count', 0), reverse=True),
        'nextPageToken': None
    }

    playlists = get_channel_playlists(comp.channel_id_youtube)
    top_tags = get_most_used_tags(comp.channel_id_youtube, video_limit=50)
    category = get_channel_main_category(comp.channel_id_youtube)

    final_data = {
        'details': details,
        'growth': growth_data, # Add the growth data to the package
        'recent_videos_data': recent_videos_data,
        'most_viewed_videos_data': most_viewed_videos_data,
        'playlists': playlists,
        'top_tags': top_tags,
        'category': category
    }
    
    set_to_cache(cache_key, final_data, expire_hours=4) 
    
    return final_data


@api_bp.route('/competitor/<int:competitor_id>/data')
@login_required
def get_competitor_data(competitor_id):
    comp = Competitor.query.filter_by(id=competitor_id, user_id=current_user.id).first_or_404()
    data_package = get_full_competitor_package(comp.id)
    return jsonify(data_package)


@api_bp.route('/competitor/<int:competitor_id>/refresh', methods=['POST'])
@login_required
def refresh_competitor_data(competitor_id):
    comp = Competitor.query.filter_by(id=competitor_id, user_id=current_user.id).first_or_404()
    fresh_data_package = get_full_competitor_package(comp.id, force_refresh=True)
    return jsonify(fresh_data_package)


@api_bp.route('/search-channels')
@login_required
def api_search_channels():
    query = request.args.get('q', '')
    if len(query) < 2: return jsonify([])
    return jsonify(search_for_channels(query))
    

@api_bp.route('/video-details/<string:video_id>')
@login_required
def api_video_details(video_id):
    details = get_video_details(video_id)
    if 'error' in details: return jsonify({'error': details['error']}), 404
    return jsonify(details)


@api_bp.route('/channel/<string:channel_id>/videos')
@login_required
def get_channel_videos_paginated(channel_id):
    page_token = request.args.get('page_token', None)
    sort_by = request.args.get('sort_by', 'date')

    if sort_by == 'viewCount':
        data = get_most_viewed_videos(channel_id, max_results=20, page_token=page_token)
    else:
        data = get_latest_videos(channel_id, max_results=20, page_token=page_token)

    return jsonify(data)