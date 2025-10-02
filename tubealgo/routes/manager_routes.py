# Filepath: tubealgo/routes/manager_routes.py
import os
import datetime
import re
from datetime import timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, abort
from flask_login import login_required, current_user
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from flask_wtf import FlaskForm
from ..forms import VideoForm, UploadForm, PlaylistForm
from ..services.youtube_manager import (
    get_user_videos, update_video_details, get_single_video, 
    upload_video, set_video_thumbnail, get_user_playlists,
    create_playlist, get_single_playlist, update_playlist,
    get_competitors_playlists
)
from ..services.openai_service import generate_titles_and_tags, generate_description, generate_playlist_suggestions
from ..decorators import check_limits
from ..models import get_setting, log_system_event # <-- log_system_event को इम्पोर्ट करें

manager_bp = Blueprint('manager', __name__, url_prefix='/manage')

@manager_bp.route('/')
@login_required
def index():
    return redirect(url_for('manager.manage_videos'))

def get_credentials():
    creds_data = session.get('credentials')
    if not creds_data or 'token' not in creds_data or 'refresh_token' not in creds_data:
        return None
    return Credentials(**creds_data)

def handle_api_error(error_dict):
    """Parses API errors, logs them, and flashes a user-friendly message."""
    if isinstance(error_dict, dict) and 'error' in error_dict:
        error_message = str(error_dict['error'])
        
        # === YAHAN BADLAV KIYA GAYA HAI ===
        if 'quotaExceeded' in error_message:
            # Log the critical error for the admin
            log_system_event(
                message="YouTube API quota has been exceeded.",
                log_type='QUOTA_EXCEEDED',
                details={'error': error_message}
            )
            # Show a generic message to the user
            flash('Something went wrong on our end. Our team has been notified and we are working on it. Please try again later.', 'error')

        elif 'invalid_grant' in error_message:
             flash('Your permission has expired. Please grant permission again to manage your YouTube account.', 'warning')
             return redirect(url_for('auth.google_login'))
        else:
            # For other errors, show a more specific message but still log it
            log_system_event(
                message="An unhandled API error occurred in YT Manager.",
                log_type='ERROR',
                details={'error': error_message, 'user_id': current_user.id}
            )
            flash(f'An API error occurred. If the problem persists, please contact support.', 'error')
        # === YAHAN TAK ===

    return None


@manager_bp.route('/videos')
@login_required
def manage_videos():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account with YouTube permission to manage videos.', 'warning')
        return redirect(url_for('auth.google_login'))
    
    videos = []
    try:
        video_data = get_user_videos(creds)
        redirect_response = handle_api_error(video_data)
        if redirect_response:
            return redirect_response
        if video_data and 'error' not in video_data:
            videos = video_data

    except RefreshError:
        flash('Your permission has expired. Please grant permission to manage your YouTube videos.', 'warning')
        return redirect(url_for('auth.google_login'))
    except Exception as e:
        log_system_event(f"Unexpected error in manage_videos: {str(e)}", 'ERROR', {'user_id': current_user.id})
        flash('An unexpected error occurred. Our team has been notified.', 'error')
        
    return render_template('manage_videos.html', videos=videos)

@manager_bp.route('/playlists')
@login_required
def manage_playlists():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account with YouTube permission to manage playlists.', 'warning')
        return redirect(url_for('auth.google_login'))

    playlists = []
    try:
        playlist_data = get_user_playlists(creds)
        redirect_response = handle_api_error(playlist_data)
        if redirect_response:
            return redirect_response
        if playlist_data and 'error' not in playlist_data:
            playlists = playlist_data

    except RefreshError:
        flash('Your permission has expired. Please grant permission to manage your YouTube playlists.', 'warning')
        return redirect(url_for('auth.google_login'))
    except Exception as e:
        log_system_event(f"Unexpected error in manage_playlists: {str(e)}", 'ERROR', {'user_id': current_user.id})
        flash('An unexpected error occurred. Our team has been notified.', 'error')
    
    form = FlaskForm() 
    return render_template('manage_playlists.html', playlists=playlists, form=form)

# ... (बाकी के फंक्शन्स में कोई बदलाव नहीं)
@manager_bp.route('/playlists/create', methods=['GET', 'POST'])
@login_required
def create_playlist_route():
    form = PlaylistForm()
    if request.method == 'GET':
        prefill_title = request.args.get('title')
        prefill_desc = request.args.get('desc')
        if prefill_title:
            form.title.data = prefill_title
        if prefill_desc:
            form.description.data = prefill_desc
            
    if form.validate_on_submit():
        creds = get_credentials()
        if not creds:
            flash('Please connect your Google account to create playlists.', 'warning')
            return redirect(url_for('auth.google_login'))
        
        result = create_playlist(
            creds,
            title=form.title.data,
            description=form.description.data,
            privacy_status=form.privacy_status.data
        )
        if 'error' in result:
            flash(f"Error creating playlist: {result['error']}", 'error')
        else:
            flash(f"Playlist '{form.title.data}' created successfully!", 'success')
        return redirect(url_for('manager.manage_playlists'))
        
    return render_template('create_playlist.html', form=form)

@manager_bp.route('/playlists/generate-ideas', methods=['POST'])
@login_required
@check_limits(feature='ai_generation')
def generate_playlist_ideas():
    creds = get_credentials()
    if not creds:
        return jsonify({'error': 'Please connect your Google Account first.'}), 400

    user_playlists = get_user_playlists(creds)
    user_playlist_titles = [p['title'] for p in user_playlists if 'title' in p]

    competitor_video_titles = get_competitors_playlists(current_user)
    
    suggestions = generate_playlist_suggestions(current_user, user_playlist_titles, competitor_video_titles)
    
    return jsonify(suggestions)

@manager_bp.route('/playlists/edit/<playlist_id>', methods=['GET', 'POST'])
@login_required
def edit_playlist_route(playlist_id):
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to edit playlists.', 'warning')
        return redirect(url_for('auth.google_login'))

    playlist_details = get_single_playlist(creds, playlist_id)
    if 'error' in playlist_details:
        flash(playlist_details['error'], 'error')
        return redirect(url_for('manager.manage_playlists'))
    
    form = PlaylistForm()
    if request.method == 'GET':
        form.title.data = playlist_details.get('snippet', {}).get('title')
        form.description.data = playlist_details.get('snippet', {}).get('description')
        form.privacy_status.data = playlist_details.get('status', {}).get('privacyStatus')

    if form.validate_on_submit():
        result = update_playlist(
            creds,
            playlist_id=playlist_id,
            title=form.title.data,
            description=form.description.data,
            privacy_status=form.privacy_status.data
        )
        if 'error' in result:
            flash(f"Error updating playlist: {result['error']}", 'error')
        else:
            flash(f"Playlist '{form.title.data}' updated successfully!", 'success')
        return redirect(url_for('manager.manage_playlists'))

    return render_template('edit_playlist.html', form=form, playlist=playlist_details)

@manager_bp.route('/edit/<video_id>', methods=['GET', 'POST'])
@login_required
def edit_video(video_id):
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to manage videos.', 'warning')
        return redirect(url_for('auth.google_login'))

    video_details = get_single_video(creds, video_id)
    if 'error' in video_details:
        flash(video_details['error'], 'error')
        return redirect(url_for('manager.manage_videos'))

    duration_str = video_details.get('contentDetails', {}).get('duration', 'PT0S')
    duration_regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = duration_regex.match(duration_str)
    total_seconds = 0
    if parts:
        parts = parts.groups()
        time_params = {}
        for (name, value) in zip(["hours", "minutes", "seconds"], parts):
            if value:
                time_params[name] = int(value)
        total_seconds = timedelta(**time_params).total_seconds()
    
    is_video_short = total_seconds > 0 and total_seconds <= 61
    
    form = VideoForm(obj=video_details['snippet'])
    
    is_scheduled = video_details['status'].get('publishAt') and datetime.datetime.fromisoformat(video_details['status']['publishAt'].replace('Z', '')) > datetime.datetime.utcnow()
    current_visibility = 'schedule' if is_scheduled else video_details['status'].get('privacyStatus', 'private')

    if request.method == 'GET':
        form.tags.data = ", ".join(video_details['snippet'].get('tags', []))
        if is_scheduled:
            form.publish_at.data = datetime.datetime.fromisoformat(video_details['status']['publishAt'].replace('Z', ''))

    if form.validate_on_submit():
        visibility_choice = request.form.get('visibility_choice')
        publish_at_time_str = request.form.get('publish_at')
        publish_at_time = None
        if visibility_choice == 'schedule' and publish_at_time_str:
            try:
                publish_at_time = datetime.datetime.fromisoformat(publish_at_time_str)
            except (ValueError, TypeError):
                try:
                    publish_at_time = datetime.datetime.strptime(publish_at_time_str, "%Y-%m-%dT%H:%M:%S")
                except (ValueError, TypeError):
                    publish_at_time = None

        final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice

        update_result = update_video_details(
            creds, video_id, 
            form.title.data, 
            form.description.data, 
            [tag.strip() for tag in form.tags.data.split(',') if tag.strip()],
            final_visibility,
            publish_at_time
        )
        if 'error' in update_result:
            flash(f"Error updating video details: {update_result['error']}", 'error')
        else:
            flash('Video details updated successfully!', 'success')

        thumbnail_file = form.thumbnail.data
        if thumbnail_file and thumbnail_file.filename and not is_video_short:
            thumb_result = set_video_thumbnail(creds, video_id, thumbnail_file)
            if 'error' in thumb_result:
                flash(f"Error setting thumbnail: {thumb_result['error']}", 'error')
            else:
                flash('Thumbnail updated successfully!', 'success')
        
        return redirect(url_for('manager.manage_videos'))

    return render_template(
        'edit_video.html', 
        video=video_details, 
        form=form, 
        current_visibility=current_visibility, 
        has_competitors=current_user.competitors.count() > 0,
        is_video_short=is_video_short
    )

@manager_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if not get_setting('feature_video_upload', True):
        abort(404)
    form = UploadForm()
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to upload videos.', 'warning')
        return redirect(url_for('auth.google_login'))

    if form.validate_on_submit():
        visibility_choice = request.form.get('visibility_choice')
        publish_at_time_str = request.form.get('publish_at')
        publish_at_time = None

        if visibility_choice == 'schedule' and publish_at_time_str:
            try:
                publish_at_time = datetime.datetime.fromisoformat(publish_at_time_str)
            except (ValueError, TypeError):
                try:
                    publish_at_time = datetime.datetime.strptime(publish_at_time_str, "%Y-%m-%dT%H:%M:%S")
                except (ValueError, TypeError):
                    publish_at_time = None

        final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice

        metadata = {
            "title": form.title.data,
            "description": form.description.data,
            "tags": [tag.strip() for tag in form.tags.data.split(',') if tag.strip()],
            "privacy_status": final_visibility,
            "publish_at": publish_at_time,
            "category_id": request.form.get('category_id', '22')
        }
        
        video_file = form.video_file.data
        upload_result = upload_video(creds, video_file, metadata)
        
        if 'error' in upload_result:
            flash(f"Error uploading video: {upload_result['error']}", 'error')
        else:
            video_id = upload_result.get('id')
            flash(f"Video uploaded successfully! Watch it here: https://youtu.be/{video_id}", 'success')
            
            thumbnail_file = form.thumbnail.data
            if thumbnail_file and thumbnail_file.filename:
                thumb_result = set_video_thumbnail(creds, video_id, thumbnail_file)
                if 'error' in thumb_result:
                    flash(f"Note: Could not set thumbnail. This may happen if the video is a Short. Error: {thumb_result['error']}", 'warning')
                else:
                    flash('Thumbnail set successfully!', 'success')
        
        return redirect(url_for('manager.manage_videos'))
    
    return render_template('upload_video.html', form=form, has_competitors=current_user.competitors.count() > 0)

@manager_bp.route('/api/generate-titles', methods=['POST'])
@login_required
@check_limits(feature='ai_generation')
def api_generate_titles():
    if current_user.competitors.count() == 0:
        return jsonify({'error': 'no_competitors', 'message': 'Please add competitors for better suggestions.'}), 400
    data = request.json
    topic = data.get('topic')
    if not topic:
        return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
    results = generate_titles_and_tags(current_user, topic)
    if 'titles' in results:
        return jsonify({'titles': results['titles']})
    if 'error' in results and 'message' not in results:
        results['message'] = results['error']
    return jsonify(results)

@manager_bp.route('/api/generate-tags', methods=['POST'])
@login_required
@check_limits(feature='ai_generation')
def api_generate_tags():
    if current_user.competitors.count() == 0:
        return jsonify({'error': 'no_competitors', 'message': 'Please add competitors for better suggestions.'}), 400
    data = request.json
    topic = data.get('topic')
    exclude_tags = data.get('exclude_tags', [])
    if not topic:
        return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
    results = generate_titles_and_tags(current_user, topic, exclude_tags=exclude_tags)
    if 'tags' in results and current_user.channel and current_user.channel.channel_title:
        channel_name_tag = current_user.channel.channel_title
        if channel_name_tag.lower() not in [tag.lower() for tag in results['tags']]:
            results['tags'].insert(0, channel_name_tag)
    if 'tags' in results:
        return jsonify({'tags': results['tags']})
    if 'error' in results and 'message' not in results:
        results['message'] = results['error']
    return jsonify(results)

@manager_bp.route('/api/generate-description', methods=['POST'])
@login_required
@check_limits(feature='ai_generation')
def api_generate_description():
    data = request.json
    topic = data.get('topic')
    title = data.get('title')
    if not topic or not title:
        return jsonify({'error': 'bad_request', 'message': 'Topic and title are required.'}), 400
    result = generate_description(current_user, topic, title)
    if 'error' in result and 'message' not in result:
        result['message'] = result['error']
    return jsonify(result)