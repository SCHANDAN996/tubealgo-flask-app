# tubealgo/routes/admin/system.py

from flask import render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required
# CSRF के लिए FlaskForm या generate_csrf इम्पोर्ट करें
from flask_wtf import FlaskForm # <<< यह इम्पोर्ट जोड़ा गया है
from flask_wtf.csrf import generate_csrf, validate_csrf, ValidationError # <<< यह इम्पोर्ट जोड़ा गया है
from . import admin_bp
from ... import db
from ...decorators import admin_required
# ProgrammingError और OperationalError के लिए exc इम्पोर्ट करें
from sqlalchemy import func, cast, Date, exc
from datetime import date, timedelta, datetime # date, timedelta, datetime इम्पोर्ट करें
# Models इम्पोर्ट करें
from ...models import SystemLog, ApiCache, SiteSetting, get_config_value, User, get_setting, log_system_event, APIKeyStatus
import json
import google.generativeai as genai
import pytz
import traceback

# <<< यह क्लास जोड़ी गई है >>>
class CSRFOnlyForm(FlaskForm):
    """A simple form containing only the CSRF token field."""
    pass

def mask_api_key(key_name): # Changed function signature to accept key_name
    """Masks an API key for display, handling potential lists."""
    key_value = get_config_value(key_name) # Uses combined logic (DB > Env)
    if not key_value:
        return "Not Set"

    # Handle lists/JSON for multi-key fields
    if key_name in ['GEMINI_API_KEY', 'YOUTUBE_API_KEYS']:
        keys_list = []
        try:
            # Try loading as JSON list
            loaded_keys = json.loads(key_value)
            if isinstance(loaded_keys, list):
                keys_list = [k.strip() for k in loaded_keys if isinstance(k, str) and k.strip()]
        except (json.JSONDecodeError, TypeError):
            # Try splitting by comma
            if isinstance(key_value, str):
                keys_list = [k.strip() for k in key_value.split(',') if k.strip()]

        if keys_list:
             # Mask the first key found
             first_key = keys_list[0]
             masked_first = f"{first_key[:4]}...{first_key[-4:]}" if len(first_key) > 8 else "Short Key"
             return f"~{len(keys_list)} keys set (e.g., {masked_first})"
        else:
             # Check if the original value was non-empty but unparseable
             if key_value and isinstance(key_value, str) and key_value.strip():
                 return "Set (Invalid Format)"
             else:
                 return "Not Set or Empty" # Explicitly state if empty

    # Default masking for single keys
    if isinstance(key_value, str) and len(key_value) > 8:
        return f"{key_value[:4]}...{key_value[-4:]}"
    elif isinstance(key_value, str) and key_value:
        return "Set (Short Key)"
    else:
        # Handle cases where the value might be non-string or empty
        if key_value:
             return "Set (Invalid Format)"
        else:
             return "Not Set or Empty"


@admin_bp.route('/logs')
@login_required
@admin_required
def system_logs():
    page = request.args.get('page', 1, type=int)
    logs_pagination = None # Initialize
    try:
        # Renamed variable to avoid conflict
        logs_pagination = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=25, error_out=False)
    except (exc.OperationalError, exc.ProgrammingError) as e:
        flash("Could not load system logs. Database table might be missing.", "error")
        log_system_event("Failed to query SystemLog table", "ERROR", details=str(e))
        db.session.rollback()
        # Create an empty pagination object for consistent template rendering
        from flask_sqlalchemy.pagination import Pagination
        logs_pagination = Pagination(None, page, 25, 0, [])
    # Pass the renamed variable to the template
    return render_template('admin/system_logs.html', logs=logs_pagination)


@admin_bp.route('/cache')
@login_required
@admin_required
def cache_management():
    cache_items = []
    try:
        cache_items = ApiCache.query.order_by(ApiCache.expires_at.desc()).all()
    except (exc.OperationalError, exc.ProgrammingError) as e:
        flash("Could not load cache items. Database table might be missing.", "error")
        log_system_event("Failed to query ApiCache table", "ERROR", details=str(e))
        db.session.rollback()
    # <<< बदलाव यहाँ है: CSRFOnlyForm() इंस्टैंस पास किया गया >>>
    form = CSRFOnlyForm()
    return render_template('admin/cache_management.html', cache_items=cache_items, form=form)


@admin_bp.route('/cache/clear', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        try:
            num_rows_deleted = db.session.query(ApiCache).delete()
            db.session.commit()
            flash(f'Successfully cleared {num_rows_deleted} cache entries.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error clearing cache: {e}', 'error')
            log_system_event("Error clearing cache", "ERROR", details=str(e))
    else:
        current_app.logger.warning(f"CSRF validation failed for clear_cache: {form.errors}")
        flash("Invalid request or security token expired.", 'error')

    return redirect(url_for('admin.cache_management'))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    # <<< बदलाव यहाँ है: FlaskForm इंस्टैंस बनाया गया >>>
    form = FlaskForm() # Use FlaskForm for CSRF handling

    if form.validate_on_submit(): # This handles POST and validates CSRF
        form_data = request.form.to_dict()

        # Handle checkboxes (unchanged)
        feature_flags = ['feature_referral_system', 'feature_video_upload']
        for flag in feature_flags:
            # Checkbox value is 'True' only if it's present in form_data
            form_data[flag] = 'True' if flag in form_data else 'False'

        # Handle bulk edit limits (unchanged)
        bulk_edit_keys = ['bulk_edit_limit_free', 'bulk_edit_limit_creator', 'bulk_edit_limit_pro']
        for key in bulk_edit_keys:
            value_str = form_data.get(key, '0')
            value_int = 0
            try:
                value_int = int(value_str)
                # Allow -1 for unlimited, default to 0 if less than -1
                value_int = 0 if value_int < -1 else value_int
            except (ValueError, TypeError):
                default_val = -1 if 'pro' in key else (20 if 'creator' in key else 0)
                value_int = default_val
                flash(f"Invalid value for {key.replace('_', ' ').title()}. Using default: {'Unlimited' if default_val == -1 else default_val}", 'warning')
            form_data[key] = str(value_int)

        # Keys considered secrets (unchanged)
        secret_keys = ['OPENAI_API_KEY', 'YOUTUBE_API_KEYS', 'TELEGRAM_BOT_TOKEN',
                       'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
                       'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                       # 'GEMINI_API_KEY', # Managed in ai_settings now
                       'CASHFREE_APP_ID', 'CASHFREE_SECRET_KEY']

        settings_to_update = {}
        settings_to_add = []

        # Prepare updates/inserts (unchanged)
        for key, value in form_data.items():
            if key == 'csrf_token': continue

            setting = None
            try:
                setting = SiteSetting.query.get(key)
            except (exc.OperationalError, exc.ProgrammingError) as e:
                 flash("Error accessing settings table. Cannot save.", "error")
                 log_system_event("Error accessing SiteSetting table on save", "ERROR", details=str(e))
                 db.session.rollback()
                 return redirect(url_for('admin.site_settings'))

            is_secret = key in secret_keys
            # Skip saving secrets only if the *submitted* value is empty.
            # Don't skip if the secret was never submitted (keep existing value).
            if is_secret and key in form_data and not value.strip():
                 continue

            if setting:
                 # Update only if value actually changed
                 if setting.value != value:
                     settings_to_update[key] = value
            # Add new non-secret or non-empty secret only if value is provided or it's not a secret
            elif value.strip() or not is_secret:
                settings_to_add.append(SiteSetting(key=key, value=value))

        try:
            # Perform updates (unchanged)
            for key, value in settings_to_update.items():
                db.session.merge(SiteSetting(key=key, value=value))

            # Perform inserts (unchanged)
            if settings_to_add:
                db.session.bulk_save_objects(settings_to_add)

            db.session.commit()
            flash('Site settings updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'error')
            log_system_event("Error saving site settings", "ERROR", details=str(e), traceback_info=traceback.format_exc())

        return redirect(url_for('admin.site_settings'))

    elif request.method == 'POST': # If CSRF validation failed
        current_app.logger.warning(f"CSRF validation failed for site_settings: {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')
        # Fall through to GET rendering

    # --- GET Request Handling (unchanged) ---
    settings = {}
    try:
        settings_list = SiteSetting.query.all()
        settings = {s.key: s.value for s in settings_list}
    except (exc.OperationalError, exc.ProgrammingError) as e:
         flash("Could not load settings from database. Table might be missing.", "warning")
         log_system_event("Failed to load SiteSetting table", "WARNING", details=str(e))
         db.session.rollback() # Rollback transaction
    except Exception as e:
         flash(f"An unexpected error occurred loading settings: {e}", "error")
         log_system_event("Unexpected error loading SiteSetting", "ERROR", details=str(e))
         db.session.rollback()

    # Ensure defaults exist if needed by template (unchanged)
    default_settings = {
        'ADMIN_TELEGRAM_CHAT_ID': '',
        'bulk_edit_limit_free': '0',
        'bulk_edit_limit_creator': '20',
        'bulk_edit_limit_pro': '50', # Changed default to 50 as per template
        'feature_referral_system': 'True',
        'feature_video_upload': 'True',
        'MEASUREMENT_ID': '',
        'site_announcement': '',
        'seo_home_title': '',
        'seo_home_description': '',
    }
    for key, default_value in default_settings.items():
        settings.setdefault(key, default_value)

    # <<< बदलाव यहाँ है: csrf_token() मैक्रो सीधे टेम्पलेट में इस्तेमाल होगा, इसे पास करने की जरूरत नहीं >>>
    # csrf_token_value = generate_csrf() # Generate CSRF token for reset forms

    # Pass form=form for {{ form.hidden_tag() }} in template
    return render_template('admin/site_settings.html', settings=settings, mask_key=mask_api_key, form=form)


@admin_bp.route('/settings/reset/<string:key_name>', methods=['POST'])
@login_required
@admin_required
def reset_setting(key_name):
    # <<< बदलाव यहाँ है: CSRF Validation जोड़ा गया >>>
    # Use Flask-WTF's built-in validation
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('CSRF token validation failed. Could not reset setting.', 'error')
        # Redirect based on context
        if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name:
             return redirect(url_for('admin.ai_settings'))
        else:
             return redirect(url_for('admin.site_settings'))

    setting = SiteSetting.query.get(key_name)
    if setting:
        try:
            db.session.delete(setting)
            db.session.commit()
            flash(f"Setting '{key_name}' removed from database. Using default.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error resetting setting '{key_name}': {str(e)}", 'error')
            log_system_event(f"Error resetting setting {key_name}", "ERROR", details=str(e))
    else:
        flash(f"Setting '{key_name}' not found in DB (already default).", 'info')

    # Redirect based on context (unchanged)
    if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name:
         return redirect(url_for('admin.ai_settings'))
    else:
         return redirect(url_for('admin.site_settings'))


@admin_bp.route('/ai-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_settings():
    # <<< बदलाव यहाँ है: FlaskForm इंस्टैंस बनाया गया >>>
    form = FlaskForm() # Use FlaskForm for CSRF handling

    if form.validate_on_submit(): # Handles POST and CSRF
        keys_from_form = request.form.getlist('gemini_keys')
        valid_keys = [key.strip() for key in keys_from_form if key and key.strip()]
        # Store as JSON list string
        keys_json = json.dumps(valid_keys)

        # Update or create GEMINI_API_KEY setting
        keys_setting = SiteSetting.query.get('GEMINI_API_KEY')
        if keys_setting:
            if keys_setting.value != keys_json: keys_setting.value = keys_json
        elif valid_keys: # Only add if there are valid keys
            db.session.add(SiteSetting(key='GEMINI_API_KEY', value=keys_json))

        # Update or create SELECTED_AI_MODEL setting
        selected_model = request.form.get('selected_model')
        if selected_model:
            model_setting = SiteSetting.query.get('SELECTED_AI_MODEL')
            if model_setting:
                if model_setting.value != selected_model: model_setting.value = selected_model
            else:
                db.session.add(SiteSetting(key='SELECTED_AI_MODEL', value=selected_model))

        # Update or create/delete Prompts (unchanged)
        prompt_keys = ['prompt_generate_ideas', 'prompt_titles_and_tags', 'prompt_description']
        for key in prompt_keys:
            value = request.form.get(key, '').strip()
            setting = SiteSetting.query.get(key)
            if setting:
                if value: # If new value is provided
                    if setting.value != value: setting.value = value
                else: # If new value is empty, delete the setting
                    db.session.delete(setting)
            elif value: # Only create if not empty
                db.session.add(SiteSetting(key=key, value=value))

        try:
            db.session.commit()
            flash('AI Settings updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving AI settings: {str(e)}', 'error')
            log_system_event("Error saving AI settings", "ERROR", details=str(e), traceback_info=traceback.format_exc())

        return redirect(url_for('admin.ai_settings'))

    elif request.method == 'POST': # If CSRF validation failed
        current_app.logger.warning(f"CSRF validation failed for ai_settings: {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')
        # Fall through to GET rendering

    # --- GET Request (logic remains mostly the same, just pass form) ---
    current_keys = []
    keys_setting_value = get_config_value('GEMINI_API_KEY', '[]') # Uses DB > Env
    try:
        loaded_keys = json.loads(keys_setting_value)
        if isinstance(loaded_keys, list):
             current_keys = [k for k in loaded_keys if isinstance(k, str) and k.strip()]
    except (json.JSONDecodeError, TypeError):
        # Fallback for comma-
