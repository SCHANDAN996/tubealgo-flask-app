# tubealgo/routes/admin/system.py

from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
# CSRF के लिए FlaskForm या generate_csrf इम्पोर्ट करें
from flask_wtf.csrf import generate_csrf
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

def mask_api_key(key):
    """Masks an API key for display, handling potential lists."""
    key_value = get_config_value(key) # Uses combined logic (DB > Env)
    if not key_value:
        return "Not Set"

    # Handle lists/JSON for multi-key fields
    if key in ['GEMINI_API_KEY', 'YOUTUBE_API_KEYS']:
        keys_list = []
        try:
            # Try loading as JSON list
            loaded_keys = json.loads(key_value)
            if not isinstance(loaded_keys, list):
                keys_list = [] # Reset if not a list
        except json.JSONDecodeError:
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
    try:
        logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=25, error_out=False)
    except (exc.OperationalError, exc.ProgrammingError) as e:
        flash("Could not load system logs. Database table might be missing.", "error")
        log_system_event("Failed to query SystemLog table", "ERROR", details=str(e))
        db.session.rollback()
        logs = None # Or an empty pagination object if preferred
        # You might want to create an empty pagination object for consistent template rendering
        from flask_sqlalchemy.pagination import Pagination
        logs = Pagination(None, page, 25, 0, [])
    return render_template('admin/system_logs.html', logs=logs)


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
    return render_template('admin/cache_management.html', cache_items=cache_items)


@admin_bp.route('/cache/clear', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    try:
        num_rows_deleted = db.session.query(ApiCache).delete()
        db.session.commit()
        flash(f'Successfully cleared {num_rows_deleted} cache entries.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error clearing cache: {e}', 'error')
        log_system_event("Error clearing cache", "ERROR", details=str(e))
    return redirect(url_for('admin.cache_management'))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    csrf_token_value = generate_csrf() # Generate CSRF token

    if request.method == 'POST':
        form_data = request.form.to_dict()

        # Handle checkboxes
        feature_flags = ['feature_referral_system', 'feature_video_upload']
        for flag in feature_flags:
            form_data[flag] = 'True' if flag in form_data else 'False'

        # Handle bulk edit limits
        bulk_edit_keys = ['bulk_edit_limit_free', 'bulk_edit_limit_creator', 'bulk_edit_limit_pro']
        for key in bulk_edit_keys:
            value_str = form_data.get(key, '0')
            value_int = 0
            try:
                value_int = int(value_str)
                value_int = 0 if value_int < -1 else value_int
            except (ValueError, TypeError):
                default_val = 50 if 'pro' in key else (20 if 'creator' in key else 0)
                value_int = default_val
                flash(f"Invalid value for {key.replace('_', ' ').title()}. Using default: {default_val}", 'warning')
            form_data[key] = str(value_int)

        # Keys considered secrets
        secret_keys = ['OPENAI_API_KEY', 'YOUTUBE_API_KEYS', 'TELEGRAM_BOT_TOKEN',
                       'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
                       'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                       'GEMINI_API_KEY', # Managed in ai_settings now
                       'CASHFREE_APP_ID', 'CASHFREE_SECRET_KEY']

        settings_to_update = {}
        settings_to_add = []

        # Prepare updates/inserts
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
            if is_secret and not value.strip(): continue # Skip saving empty secrets

            if setting:
                if setting.value != value:
                    settings_to_update[key] = value
            # Add new non-secret or non-empty secret only if value is provided or it's not a secret
            elif value.strip() or not is_secret:
                settings_to_add.append(SiteSetting(key=key, value=value))

        try:
            # Perform updates
            for key, value in settings_to_update.items():
                # Use merge to handle potential concurrent updates or inserts safely
                db.session.merge(SiteSetting(key=key, value=value))

            # Perform inserts
            if settings_to_add:
                db.session.bulk_save_objects(settings_to_add)

            db.session.commit()
            flash('Site settings updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'error')
            log_system_event("Error saving site settings", "ERROR", details=str(e), traceback_info=traceback.format_exc())

        return redirect(url_for('admin.site_settings'))

    # GET Request Handling
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

    # Ensure defaults exist if needed by template
    default_settings = {
        'ADMIN_TELEGRAM_CHAT_ID': '',
        'bulk_edit_limit_free': '0',
        'bulk_edit_limit_creator': '20',
        'bulk_edit_limit_pro': '50',
        'feature_referral_system': 'True',
        'feature_video_upload': 'True',
        'MEASUREMENT_ID': '',
        'site_announcement': '',
        'seo_home_title': '',
        'seo_home_description': '',
        # Add other API keys defaults if needed, though they should ideally come from .env first
    }
    for key, default_value in default_settings.items():
        settings.setdefault(key, default_value)

    # Pass csrf_token_value for the reset forms inside the template
    return render_template('admin/site_settings.html', settings=settings, mask_key=mask_api_key, csrf_token_value=csrf_token_value)


@admin_bp.route('/settings/reset/<string:key_name>', methods=['POST'])
@login_required
@admin_required
def reset_setting(key_name):
    # CSRF protection should be handled by Flask-WTF or manually checked
    # from flask_wtf.csrf import validate_csrf
    # try:
    #     validate_csrf(request.form.get('csrf_token'))
    # except ValidationError:
    #     flash('CSRF token validation failed.', 'error')
    #     # Redirect appropriately

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

    # Redirect based on context
    if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name:
         return redirect(url_for('admin.ai_settings'))
    else:
         return redirect(url_for('admin.site_settings'))


@admin_bp.route('/ai-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_settings():
    if request.method == 'POST':
        keys_from_form = request.form.getlist('gemini_keys')
        valid_keys = [key.strip() for key in keys_from_form if key and key.strip()]
        keys_json = json.dumps(valid_keys)

        # Update or create GEMINI_API_KEY setting
        keys_setting = SiteSetting.query.get('GEMINI_API_KEY')
        if keys_setting:
            if keys_setting.value != keys_json: keys_setting.value = keys_json
        elif valid_keys:
            db.session.add(SiteSetting(key='GEMINI_API_KEY', value=keys_json))

        # Update or create SELECTED_AI_MODEL setting
        selected_model = request.form.get('selected_model')
        if selected_model:
            model_setting = SiteSetting.query.get('SELECTED_AI_MODEL')
            if model_setting:
                if model_setting.value != selected_model: model_setting.value = selected_model
            else:
                db.session.add(SiteSetting(key='SELECTED_AI_MODEL', value=selected_model))

        # Update or create/delete Prompts
        prompt_keys = ['prompt_generate_ideas', 'prompt_titles_and_tags', 'prompt_description']
        for key in prompt_keys:
            value = request.form.get(key, '').strip()
            setting = SiteSetting.query.get(key)
            if setting:
                if value:
                    if setting.value != value: setting.value = value
                else:
                    db.session.delete(setting) # Delete if value is empty
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

    # --- GET Request ---
    current_keys = []
    keys_setting_value = get_config_value('GEMINI_API_KEY', '[]')
    try:
        loaded_keys = json.loads(keys_setting_value)
        if isinstance(loaded_keys, list): current_keys = [k for k in loaded_keys if k and k.strip()]
    except json.JSONDecodeError:
        if isinstance(keys_setting_value, str): current_keys = [k.strip() for k in keys_setting_value.split(',') if k.strip()]
        else: flash("Error reading Gemini API keys format.", "error")
    if not current_keys: current_keys = [""] # Add empty input if none

    def get_model_display_info(model_name):
        if not model_name: return "Unknown Model"
        if "flash" in model_name: return "Fast & cost-effective"
        if "pro" in model_name: return "Powerful & versatile"
        return "General model"

    default_model = 'gemini-1.5-flash-latest'
    available_models_info = [{'name': default_model, 'display': get_model_display_info(default_model)}]
    first_valid_key = next((key for key in current_keys if key), None)
    if first_valid_key:
        try:
            genai.configure(api_key=first_valid_key)
            fetched_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    model_name = m.name.replace('models/', '')
                    fetched_models.append({'name': model_name, 'display': get_model_display_info(model_name)})
            if fetched_models:
                unique_models = {d['name']: d for d in fetched_models}
                available_models_info = sorted(unique_models.values(), key=lambda x: ('flash' not in x['name'], x['name']))
            else: flash("No compatible models found for the first API key.", "warning")
        except Exception as e: flash(f"Could not fetch models: {str(e)[:150]}...", "warning")
    else: flash("Add a valid Gemini API key to fetch models.", "info")

    selected_model = get_config_value('SELECTED_AI_MODEL', default_model)
    settings = {}
    try:
        settings = {s.key: s.value for s in SiteSetting.query.all()}
    except (exc.OperationalError, exc.ProgrammingError):
        flash("Could not load prompt settings from database.", "warning")
        db.session.rollback() # Important after failed query

    return render_template('admin/ai_settings.html', current_keys=current_keys, available_models_info=available_models_info, selected_model=selected_model, settings=settings)


@admin_bp.route('/api/test-ai-config', methods=['POST'])
@login_required
@admin_required
def test_ai_config():
    # --- Testing logic remains the same ---
    data = request.json; api_keys = data.get('keys', []); model_name = data.get('model')
    if not model_name: return jsonify({'status': 'error', 'message': 'Model name required.'}), 400
    if not isinstance(api_keys, list): return jsonify({'status': 'error', 'message': 'Keys must be a list.'}), 400
    results = []; overall_success = False; valid_keys_provided = False
    for key in api_keys:
        key = key.strip();
        if not key: continue; valid_keys_provided = True
        key_masked = mask_api_key(key) # Use the correct function name
        try:
            genai.configure(api_key=key); model = genai.GenerativeModel(model_name)
            response = model.generate_content("test", generation_config={'max_output_tokens': 1, 'temperature': 0})
            if hasattr(response, 'text') and isinstance(response.text, str): results.append({'key_mask': key_masked, 'status': 'Valid'}); overall_success = True
            else: results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': 'API Response Invalid'})
        except Exception as e:
            error_message = str(e).lower(); error_detail = "Failed (Check Model/Key/Billing)"
            if 'api_key_not_valid' in error_message or 'provide an api key' in error_message: error_detail = "API Key Invalid"
            elif 'permission_denied' in error_message: error_detail = "Permission Denied (Check Project/API/Billing)"
            elif 'quota' in error_message: error_detail = "Quota Exceeded"
            elif '404' in error_message or 'not found' in error_message: error_detail = "Model Not Found or Not Available"
            elif 'invalid argument' in error_message: error_detail = "Invalid Argument (Check Model?)"
            results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': error_detail})
    if not valid_keys_provided: return jsonify({'status': 'error', 'message': 'No valid API keys provided.'})
    return jsonify({'status': 'success' if overall_success else 'error', 'results': results})

# --- Updated user_growth_data function ---
@admin_bp.route('/data/user_growth')
@login_required
@admin_required
def user_growth_data():
    # Correctly calculate 30 days ago (start date)
    thirty_days_ago_dt = datetime.utcnow().date() - timedelta(days=29)
    user_counts = {} # Use dict for easier lookup {date: count}

    try:
        # Query counts grouped by date using SQLAlchemy functions
        user_counts_query = db.session.query(
            func.count(User.id),
            cast(User.created_at, Date) # Cast timestamp to date for grouping
        ).filter(
            User.created_at >= thirty_days_ago_dt # Filter using the start date (inclusive)
        ).group_by(
            cast(User.created_at, Date) # Group by the casted date
        ).order_by(
            cast(User.created_at, Date) # Order by the casted date
        ).all()
        # Convert list of tuples [(count, date), ...] to dictionary {date: count}
        user_counts = {day_date: count for count, day_date in user_counts_query}

    except (exc.OperationalError, exc.ProgrammingError) as e:
         # Log error if query fails (e.g., table doesn't exist)
         log_system_event("Error fetching user growth data", "ERROR", details=str(e), traceback_info=traceback.format_exc())
         db.session.rollback() # Rollback potentially failed transaction
         user_counts = {} # Ensure it's an empty dict on error
    except Exception as e:
         # Catch other unexpected errors
         log_system_event("Unexpected error in user_growth_data", "ERROR", details=str(e), traceback_info=traceback.format_exc())
         db.session.rollback()
         user_counts = {}

    labels = []
    data = []
    # Loop through the last 30 days (from thirty_days_ago_dt up to today)
    for i in range(30):
        # Calculate the date for the current iteration
        current_date = thirty_days_ago_dt + timedelta(days=i)
        # Format the label (e.g., "24 Oct")
        labels.append(current_date.strftime('%d %b'))
        # Get the count for this date from the dictionary, default to 0 if not found
        data.append(user_counts.get(current_date, 0))

    return jsonify({'labels': labels, 'data': data})
# --- End of user_growth_data function ---

@admin_bp.route('/data/plan_distribution')
@login_required
@admin_required
def plan_distribution_data():
    plan_data = {}
    try:
        plan_counts = db.session.query(
            User.subscription_plan,
            func.count(User.id)
        ).group_by(User.subscription_plan).all()
        plan_data = {plan: count for plan, count in plan_counts}
    except (exc.OperationalError, exc.ProgrammingError) as e:
        log_system_event("Error fetching plan distribution data", "ERROR", details=str(e))
        db.session.rollback()
        plan_data = {}
    except Exception as e:
        log_system_event("Unexpected error in plan_distribution_data", "ERROR", details=str(e))
        db.session.rollback()
        plan_data = {}


    labels = ['Free', 'Creator', 'Pro']
    data = [plan_data.get('free', 0), plan_data.get('creator', 0), plan_data.get('pro', 0)]
    return jsonify({'labels': labels, 'data': data})
