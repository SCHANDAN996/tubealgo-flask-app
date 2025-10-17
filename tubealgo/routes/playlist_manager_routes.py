# tubealgo/routes/playlist_manager_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from ..forms import PlaylistForm
from ..services.youtube_manager import (
    get_user_playlists, create_playlist, get_single_playlist, update_playlist,
    get_competitors_playlists
)
from ..services.ai_service import generate_playlist_suggestions
from ..decorators import check_limits, RateLimitExceeded
from ..models import SubscriptionPlan
from .utils import get_credentials

playlist_manager_bp = Blueprint('playlist_manager', __name__, url_prefix='/manage/playlists')

@playlist_manager_bp.route('/')
@login_required
def manage_playlists():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to manage playlists.', 'warning')
        return redirect(url_for('auth.google_login'))

    playlists = []
    try:
        playlist_data = get_user_playlists(creds)
        if isinstance(playlist_data, dict) and 'error' in playlist_data:
            flash(f"An API error occurred: {playlist_data['error']}", 'error')
        elif playlist_data:
            playlists = playlist_data
    except Exception as e:
        flash('An unexpected error occurred.', 'error')
        
    form = FlaskForm()  
    return render_template('manage_playlists.html', playlists=playlists, form=form)

@playlist_manager_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_playlist_route():
    # ... (Copy the create_playlist_route logic from manager_routes.py) ...
    form = PlaylistForm()
    if form.validate_on_submit():
        # ... create playlist logic ...
        return redirect(url_for('playlist_manager.manage_playlists'))
    return render_template('create_playlist.html', form=form)

@playlist_manager_bp.route('/edit/<playlist_id>', methods=['GET', 'POST'])
@login_required
def edit_playlist_route(playlist_id):
    # ... (Copy the edit_playlist_route logic from manager_routes.py) ...
    creds = get_credentials()
    # ... get playlist details ...
    form = PlaylistForm()
    if form.validate_on_submit():
        # ... update playlist logic ...
        return redirect(url_for('playlist_manager.manage_playlists'))
    return render_template('edit_playlist.html', form=form, playlist={})

@playlist_manager_bp.route('/generate-ideas', methods=['POST'])
@login_required
def generate_playlist_ideas():
    # ... (Copy the generate_playlist_ideas logic from manager_routes.py) ...
    try:
        @check_limits(feature='ai_generation')
        def do_generation():
            # ... generation logic ...
            return jsonify({})
        return do_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': {'details': str(e)}}), 429