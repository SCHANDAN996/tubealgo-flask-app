# Filepath: tubealgo/routes/api_routes.py

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from tubealgo.models import Competitor
from tubealgo.services.cache_manager import get_from_cache, set_to_cache
from tubealgo.services.youtube_fetcher import (
    analyze_channel, get_latest_videos, get_most_viewed_videos, 
    get_channel_main_category, search_for_channels, get_video_details,
    get_channel_playlists, get_most_used_tags, get_all_channel_videos
)
import json

api_bp = Blueprint('api', __name__, url_prefix='/api')

def get_full_competitor_package(competitor_id, force_refresh=False):
    """
    Fetches ALL data for a competitor for both competitor card and deep analysis page.
    This is the new central function for getting competitor data.
    It now fetches ALL videos at once to save API quota on pagination.
    """
    cache_key = f"competitor_package_v3:{competitor_id}"
    if not force_refresh:
        cached_data = get_from_cache(cache_key)
        if cached_data:
            print(f"DEBUG: Full package CACHE HIT for competitor_id {competitor_id}")
            return cached_data

    print(f"DEBUG: Full package CACHE MISS for competitor_id {competitor_id}. Fetching all data...")
    comp = Competitor.query.get_or_404(competitor_id)

    # 1. Basic channel details
    details = analyze_channel(comp.channel_id_youtube)
    if 'error' in details:
        return {'error': details['error']}

    # 2. Fetch ALL videos (or up to a reasonable limit handled by the function)
    # This is the MAJOR CHANGE. Instead of fetching just one page, we get all of them.
    all_videos = get_all_channel_videos(comp.channel_id_youtube)
    
    # We create the structure that the old functions returned for compatibility
    recent_videos_data = {
        'videos': sorted(all_videos, key=lambda x: x.get('upload_date', ''), reverse=True),
        'nextPageToken': None # No more pagination from the frontend
    }
    
    most_viewed_videos_data = {
        'videos': sorted(all_videos, key=lambda x: x.get('view_count', 0), reverse=True),
        'nextPageToken': None # No more pagination from the frontend
    }

    # 3. Fetch other details for deep analysis
    playlists = get_channel_playlists(comp.channel_id_youtube)
    top_tags = get_most_used_tags(comp.channel_id_youtube, video_limit=50) # Keep this limit reasonable
    category = get_channel_main_category(comp.channel_id_youtube)

    # 4. Package everything into a single object
    final_data = {
        'details': details,
        'recent_videos_data': recent_videos_data,
        'most_viewed_videos_data': most_viewed_videos_data,
        'playlists': playlists,
        'top_tags': top_tags,
        'category': category
    }
    
    set_to_cache(cache_key, final_data, expire_hours=24)
    print(f"DEBUG: Full package CACHE SET for competitor_id {competitor_id}")
    
    return final_data


@api_bp.route('/competitor/<int:competitor_id>/data')
@login_required
def get_competitor_data(competitor_id):
    """This API now just serves the pre-cached data package."""
    comp = Competitor.query.filter_by(id=competitor_id, user_id=current_user.id).first_or_404()
    data_package = get_full_competitor_package(comp.id)
    return jsonify(data_package)


@api_bp.route('/competitor/<int:competitor_id>/refresh', methods=['POST'])
@login_required
def refresh_competitor_data(competitor_id):
    """This API now forces a refresh of the entire data package."""
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
    """
    API endpoint to fetch paginated videos for the 'Load More' button.
    NOTE: With the new caching strategy, this endpoint will no longer be used by the deep_analysis page.
    It's kept here for potential future use or other features.
    """
    page_token = request.args.get('page_token', None)
    sort_by = request.args.get('sort_by', 'date')

    if sort_by == 'viewCount':
        data = get_most_viewed_videos(channel_id, max_results=20, page_token=page_token)
    else:
        data = get_latest_videos(channel_id, max_results=20, page_token=page_token)

    return jsonify(data)