# tubealgo/routes/video_manager_routes.py
import os
import re
import threading
import json
import uuid
from datetime import timedelta, datetime, date, timezone # timezone इम्पोर्ट करें
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort, current_app
from flask_login import login_required, current_user
from google.auth.exceptions import RefreshError
from flask_wtf import FlaskForm
from ..forms import VideoForm, UploadForm
from ..services.youtube_manager import (
    get_user_videos, update_video_details, get_single_video,
    upload_video, set_video_thumbnail
)
from ..models import get_setting, log_system_event, User # User इम्पोर्ट करें
from .utils import get_credentials
from ..jobs import bulk_edit_videos
from .. import db # db इम्पोर्ट करें
import traceback # Traceback इम्पोर्ट करें

video_manager_bp = Blueprint('manager', __name__)

def _parse_duration(duration_str):
    if not duration_str: return 0
    duration_regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = duration_regex.match(duration_str)
    if not parts: return 0
    parts = parts.groups()
    time_params = {name: int(value) for name, value in zip(["hours", "minutes", "seconds"], parts) if value}
    return timedelta(**time_params).total_seconds()

def _upload_to_youtube_in_background(app, creds_json, video_filepath, thumbnail_filepath, metadata):
    with app.app_context():
        try:
            from google.oauth2.credentials import Credentials

            print("BACKGROUND TASK: Started uploading to YouTube.")
            creds = Credentials.from_authorized_user_info(json.loads(creds_json))

            upload_result = upload_video(creds, video_filepath, metadata)

            if 'error' in upload_result:
                log_system_event("Background YouTube upload failed", "ERROR", details=upload_result)
                return

            video_id = upload_result.get('id')
            print(f"BACKGROUND TASK: Video uploaded to YouTube with ID: {video_id}")

            if thumbnail_filepath:
                thumb_result = set_video_thumbnail(creds, video_id, thumbnail_filepath)
                if 'error' in thumb_result:
                    log_system_event("Background thumbnail upload failed", "ERROR", details=thumb_result)
                else:
                    print(f"BACKGROUND TASK: Thumbnail set for video ID: {video_id}")

        except Exception as e:
            log_system_event("Exception in background upload task", "ERROR", details=str(e), traceback=traceback.format_exc()) # Added traceback

        finally:
            # टेम्परेरी फाइल्स और फोल्डर क्लीनअप
            folder_path = os.path.dirname(video_filepath)
            if os.path.exists(video_filepath):
                try:
                    os.remove(video_filepath)
                    print(f"BACKGROUND TASK: Deleted temp video file: {video_filepath}")
                except Exception as e:
                     log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp video file: {video_filepath}. Error: {e}")

            if thumbnail_filepath and os.path.exists(thumbnail_filepath):
                try:
                    os.remove(thumbnail_filepath)
                    print(f"BACKGROUND TASK: Deleted temp thumbnail file: {thumbnail_filepath}")
                except Exception as e:
                    log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp thumbnail file: {thumbnail_filepath}. Error: {e}")

            try:
                # Delete folder only if it exists and is empty
                if os.path.exists(folder_path) and not os.listdir(folder_path):
                    os.rmdir(folder_path)
                    print(f"BACKGROUND TASK: Deleted temp directory: {folder_path}")
            except Exception as e:
                 log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp directory: {folder_path}. Error: {e}")


@video_manager_bp.route('/')
@login_required
def index():
    return redirect(url_for('manager.manage_videos'))

@video_manager_bp.route('/videos')
@login_required
def manage_videos():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account with YouTube permission to manage videos.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    videos = []
    try:
        video_data = get_user_videos(current_user, creds)

        if isinstance(video_data, dict) and 'error' in video_data:
            flash(f"An API error occurred: {video_data['error']}", 'error')
            if 'invalid_grant' in video_data['error'] or 'token has been expired or revoked' in video_data['error'].lower():
                return redirect(url_for('auth_google.connect_youtube'))
        elif isinstance(video_data, list):
            videos = video_data
        elif video_data is None:
             flash("Could not retrieve video data. Please try again.", "warning")
             videos = []
        else:
             flash(f"Unexpected data format received for videos: {type(video_data)}", "error")
             videos = []

    except RefreshError:
        flash('Your Google connection has expired. Please reconnect your account.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))
    except Exception as e:
        log_system_event(f"Unexpected error in manage_videos: {str(e)}", 'ERROR', {'user_id': current_user.id, 'traceback': traceback.format_exc()})
        flash('An unexpected error occurred while fetching videos. Our team has been notified.', 'error')
        videos = []


    form = FlaskForm()

    # --- एडमिन सेटिंग्स से लिमिट्स प्राप्त करें ---
    limit_dict = {}
    limits_for_js = {}
    try:
        limit_dict['free'] = int(get_setting('bulk_edit_limit_free', '0'))
        limit_dict['creator'] = int(get_setting('bulk_edit_limit_creator', '20'))
        limit_dict['pro'] = int(get_setting('bulk_edit_limit_pro', '50'))

        limits_for_js = {plan: -1 if limit == -1 else limit for plan, limit in limit_dict.items()}

    except (ValueError, TypeError):
        limit_dict = {'free': 0, 'creator': 20, 'pro': 50}
        limits_for_js = limit_dict.copy()
        flash("Error reading bulk edit limits from settings, using defaults.", "warning")

    # --- दैनिक सीमाएँ दिखाने के लिए (डिस्क्लेमर में) ---
    daily_limits_display = {
        'free': "Unlimited" if limit_dict['free'] == -1 else str(limit_dict['free']),
        'creator': "Unlimited" if limit_dict['creator'] == -1 else str(limit_dict['creator']),
        'pro': "Unlimited" if limit_dict['pro'] == -1 else str(limit_dict['pro'])
    }

    # --- आज इस्तेमाल किए गए एडिट्स ---
    today = date.today()
    reset_performed = False
    if current_user.last_usage_date != today:
        current_user.daily_bulk_edits = 0
        current_user.last_usage_date = today
        reset_performed = True

    try:
        if reset_performed:
            db.session.commit()
        # Re-fetch user in case the session object is stale after commit/rollback
        user_for_count = User.query.get(current_user.id)
        edits_used_today = user_for_count.daily_bulk_edits or 0
    except Exception as e:
        db.session.rollback()
        log_system_event("Failed to reset/commit daily counters on page load", "ERROR", {'user_id': current_user.id, 'error': str(e)})
        edits_used_today = 0
        flash("Could not update usage counters, showing defaults.", "warning")


    # --- JS के लिए JSON डेटा तैयार करें ---
    page_data_for_js = {
         'dailyLimit': limits_for_js.get(current_user.subscription_plan, 0),
         'editsUsedToday': edits_used_today,
         'userPlan': current_user.subscription_plan
    }

    return render_template(
        'manage_videos.html',
        videos=videos,
        form=form,
        daily_limits=daily_limits_display,
        page_data_json=json.dumps(page_data_for_js)
    )


@video_manager_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # यह फंक्शन पहले जैसा ही रहेगा...
    if not get_setting('feature_video_upload', True):
        abort(404)

    form = UploadForm()
    creds = get_credentials()

    if not creds:
        if request.method == 'POST':
            return jsonify({'error': 'Authentication expired or invalid. Please reconnect your Google account.'}), 401
        flash('Please connect your Google account to upload videos.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    has_competitors = current_user.competitors.count() > 0

    if request.method == 'POST':
        form = UploadForm()

        if form.validate_on_submit():
            video_file = form.video_file.data
            thumbnail_file = form.thumbnail.data

            if not video_file:
                 return jsonify({'error': 'Video file is required.'}), 400

            upload_folder = os.path.join(current_app.instance_path, 'uploads', str(uuid.uuid4()))
            os.makedirs(upload_folder, exist_ok=True)

            video_filename = f"video_{uuid.uuid4().hex}_{video_file.filename}"
            video_filepath = os.path.join(upload_folder, video_filename)
            video_file.save(video_filepath)

            thumbnail_filepath = None
            if thumbnail_file and thumbnail_file.filename:
                thumb_filename = f"thumb_{uuid.uuid4().hex}_{thumbnail_file.filename}"
                thumbnail_filepath = os.path.join(upload_folder, thumb_filename)
                try:
                    thumbnail_file.save(thumbnail_filepath)
                except Exception as e:
                    log_system_event("Thumbnail save error during upload", "WARNING", {'error': str(e)})
                    thumbnail_filepath = None

            visibility_choice = form.visibility.data
            publish_at_str = request.form.get('publish_at')
            publish_at_time = None

            if visibility_choice == 'schedule' and publish_at_str:
                try:
                    publish_at_time = datetime.fromisoformat(publish_at_str.replace('Z', '+00:00'))
                    if publish_at_time.tzinfo is None:
                        publish_at_time = publish_at_time.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Clean up saved file if date is invalid
                    if os.path.exists(video_filepath): os.remove(video_filepath)
                    if thumbnail_filepath and os.path.exists(thumbnail_filepath): os.remove(thumbnail_filepath)
                    try:
                       if os.path.exists(upload_folder): os.rmdir(upload_folder)
                    except OSError: pass
                    return jsonify({'error': 'Invalid schedule date format received.'}), 400

            final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice

            metadata = {
                "title": form.title.data,
                "description": form.description.data,
                "tags": [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()],
                "privacy_status": final_visibility,
                "publish_at": publish_at_time
            }

            thread = threading.Thread(
                target=_upload_to_youtube_in_background,
                 args=(current_app._get_current_object(), creds.to_json(), video_filepath, thumbnail_filepath, metadata),
                 daemon=True
            )
            thread.start()

            return jsonify({
                'success': True,
                'message': 'Upload Started! Processing in the background. You can navigate away.',
                'redirect_url': url_for('manager.manage_videos')
            })
        else:
            error_message = "Invalid form data. Please check the fields."
            if form.errors:
                first_error_key = next(iter(form.errors))
                error_message = f"{first_error_key.replace('_', ' ').title()}: {form.errors[first_error_key][0]}"
            return jsonify({'error': error_message, 'details': form.errors}), 400

    return render_template('upload_video.html', form=form, has_competitors=has_competitors)


@video_manager_bp.route('/edit/<video_id>', methods=['GET', 'POST'])
@login_required
def edit_video(video_id):
    # यह फंक्शन पहले जैसा ही रहेगा...
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to manage videos.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    try:
        video_details = get_single_video(creds, video_id)
        if 'error' in video_details:
             flash(video_details['error'], 'error')
             if 'invalid_grant' in video_details['error'] or 'token has been expired or revoked' in video_details['error'].lower():
                 return redirect(url_for('auth_google.connect_youtube'))
             return redirect(url_for('manager.manage_videos'))
    except RefreshError:
         flash('Your Google connection has expired. Please reconnect your account.', 'warning')
         return redirect(url_for('auth_google.connect_youtube'))
    except Exception as e:
         log_system_event(f"Error fetching video details in edit_video: {str(e)}", "ERROR", {'video_id': video_id, 'traceback': traceback.format_exc()})
         flash("Could not load video details.", "error")
         return redirect(url_for('manager.manage_videos'))

    duration_str = video_details.get('contentDetails', {}).get('duration', 'PT0S')
    total_seconds = _parse_duration(duration_str)
    is_video_short = total_seconds > 0 and total_seconds <= 61

    form = VideoForm()

    is_scheduled = False
    publish_at_dt = None
    if video_details.get('status', {}).get('publishAt'):
        try:
            publish_at_dt = datetime.fromisoformat(video_details['status']['publishAt'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
            is_scheduled = publish_at_dt > datetime.now(timezone.utc)
        except ValueError:
            is_scheduled = False

    current_visibility = 'schedule' if is_scheduled else video_details.get('status', {}).get('privacyStatus', 'private')

    if request.method == 'GET':
        form.title.data = video_details.get('snippet', {}).get('title')
        form.description.data = video_details.get('snippet', {}).get('description')
        form.tags.data = ", ".join(video_details.get('snippet', {}).get('tags', []))
        form.visibility.data = current_visibility
        if is_scheduled and publish_at_dt:
             form.publish_at.data = publish_at_dt.replace(tzinfo=None) # For datetime-local input

    if form.validate_on_submit():
        visibility_choice = form.visibility.data
        publish_at_str_from_js = request.form.get('publish_at')
        publish_at_time = None

        if visibility_choice == 'schedule' and publish_at_str_from_js:
            try:
                publish_at_time = datetime.fromisoformat(publish_at_str_from_js.replace('Z', '+00:00'))
                if publish_at_time.tzinfo is None:
                     publish_at_time = publish_at_time.replace(tzinfo=timezone.utc)
            except ValueError:
                flash('Invalid schedule date format submitted.', 'error')
                return render_template( 'edit_video.html', video=video_details, form=form,
                    current_visibility=current_visibility,
                    has_competitors=current_user.competitors.count() > 0,
                    is_video_short=is_video_short )

        final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice
        tags_list = [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()]

        update_result = update_video_details(
            creds, video_id, form.title.data, form.description.data,
            tags_list, final_visibility, publish_at_time
        )

        if 'error' in update_result:
            flash(f"Error updating video details: {update_result['error']}", 'error')
            if 'invalid_grant' in update_result['error'] or 'token has been expired or revoked' in update_result['error'].lower():
                 return redirect(url_for('auth_google.connect_youtube'))
        else:
             flash('Video details updated successfully!', 'success')

        thumbnail_file = form.thumbnail.data
        if thumbnail_file and thumbnail_file.filename and not is_video_short:
            # Save thumbnail temporarily and upload (with cleanup)
            upload_folder = os.path.join(current_app.instance_path, 'uploads', str(uuid.uuid4()))
            os.makedirs(upload_folder, exist_ok=True)
            thumb_filename = f"thumb_{uuid.uuid4().hex}_{thumbnail_file.filename}"
            thumbnail_filepath = os.path.join(upload_folder, thumb_filename)
            try:
                thumbnail_file.save(thumbnail_filepath)
                thumb_result = set_video_thumbnail(creds, video_id, thumbnail_filepath)
                if 'error' in thumb_result:
                     flash(f"Error setting thumbnail: {thumb_result['error']}", 'error')
                     # Consider redirecting for auth errors here too?
                     # if 'invalid_grant'... return redirect(...)
                else:
                    flash('Thumbnail updated successfully!', 'success')
            except Exception as e:
                 log_system_event("Thumbnail save/upload error during edit", "ERROR", {'error': str(e), 'video_id': video_id})
                 flash("An error occurred processing the thumbnail.", "error")
            finally:
                 if os.path.exists(thumbnail_filepath):
                     try: os.remove(thumbnail_filepath)
                     except Exception as e: log_system_event("Cleanup Error", "WARNING", f"Could not remove temp thumb {thumbnail_filepath}: {e}")
                 try:
                     if os.path.exists(upload_folder) and not os.listdir(upload_folder):
                         os.rmdir(upload_folder)
                 except OSError as e:
                     log_system_event("Cleanup Error", "WARNING", f"Could not remove temp dir {upload_folder}: {e}")

        # Redirect after processing everything
        return redirect(url_for('manager.manage_videos'))

    elif request.method == 'POST': # If validation fails
        flash("Form validation failed. Please check the fields.", "error")

    # Render for GET or failed POST validation
    return render_template(
        'edit_video.html',
        video=video_details,
        form=form,
        current_visibility=current_visibility,
        has_competitors=current_user.competitors.count() > 0,
        is_video_short=is_video_short
    )


@video_manager_bp.route('/videos/bulk-edit', methods=['POST'])
@login_required
def bulk_edit_route():
    # यह फंक्शन पहले से अपडेटेड है और सही है
    data = request.json
    video_ids = data.get('video_ids')
    operations = data.get('operations')

    if not video_ids or not operations or not isinstance(video_ids, list):
        return jsonify({'error': 'Invalid request. Missing video_ids or operations.'}), 400

    num_videos_to_edit = len(video_ids)

    # --- लिमिट चेक लॉजिक ---
    user_plan = current_user.subscription_plan
    limit = 0
    try:
        if user_plan == 'pro':
            limit = int(get_setting('bulk_edit_limit_pro', '50'))
        elif user_plan == 'creator':
            limit = int(get_setting('bulk_edit_limit_creator', '20'))
        else: # free plan
            limit = int(get_setting('bulk_edit_limit_free', '0'))
        # Handle -1 for unlimited
        if limit == -1: limit = float('inf')

    except (ValueError, TypeError):
         limit = float('inf') if user_plan == 'pro' else (20 if user_plan == 'creator' else 0) # Fallback defaults
         log_system_event(f"Invalid bulk edit limit setting for plan '{user_plan}'. Using default: {limit if limit != float('inf') else -1}", "WARNING")

    # आज की तारीख चेक करें और ज़रूरत पड़ने पर काउंटर रीसेट करें
    today = date.today()
    reset_performed = False
    if current_user.last_usage_date != today:
        current_user.daily_bulk_edits = 0
        current_user.last_usage_date = today
        reset_performed = True

    try:
        if reset_performed:
             db.session.commit() # Commit reset first
        # Re-fetch user to get the potentially reset counter
        # Use a fresh query to avoid potential stale data in current_user session object
        user_for_count = User.query.get(current_user.id)
        edits_used_today = user_for_count.daily_bulk_edits or 0
    except Exception as e:
         db.session.rollback()
         log_system_event("Failed to reset/refresh daily counters", "ERROR", {'user_id': current_user.id, 'error': str(e)})
         return jsonify({'error': 'Could not process request due to a temporary issue (counter error).'}), 500


    remaining_edits = float('inf') if limit == float('inf') else max(0, limit - edits_used_today)

    # लिमिट चेक करें
    if num_videos_to_edit > remaining_edits:
        limit_str = f"{int(limit)}/day" if limit != float('inf') else "Unlimited"
        return jsonify({
            'error': f'Daily bulk edit limit exceeded for {user_plan.capitalize()} plan. You can edit {int(remaining_edits)} more videos today (Limit: {limit_str}).'
        }), 429 # Too Many Requests

    # लिमिट ठीक है, काउंटर बढ़ाएं और टास्क शुरू करें
    try:
        # Update counter on the potentially re-fetched user object
        user_for_count.daily_bulk_edits = edits_used_today + num_videos_to_edit
        db.session.commit()
    except Exception as e:
         db.session.rollback()
         log_system_event("Failed to update bulk edit counter", "ERROR", {'user_id': current_user.id, 'error': str(e)})
         return jsonify({'error': 'Could not process request due to a temporary issue (counter update failed).'}), 500
    # --- बदलाव खत्म ---


    # बैकग्राउंड टास्क शुरू करें
    bulk_edit_videos.delay(current_user.id, operations, video_ids)

    limit_str = f"{int(limit)}/day" if limit != float('inf') else "Unlimited"
    # Use the updated counter value in the response
    updated_edits_used = edits_used_today + num_videos_to_edit
    return jsonify({'message': f'Bulk update for {num_videos_to_edit} videos scheduled successfully! You have used {updated_edits_used}/{limit_str} of your daily edits for the {user_plan.capitalize()} plan. You will be notified on Telegram upon completion.'}), 202