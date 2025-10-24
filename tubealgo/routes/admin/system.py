# tubealgo/routes/admin/system.py

from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import SystemLog, ApiCache, SiteSetting, get_config_value, User, get_setting # get_setting इम्पोर्ट करें
from sqlalchemy import func, cast, Date, exc # exc इम्पोर्ट करें (OperationalError के लिए)
from datetime import date, timedelta, datetime # datetime इम्पोर्ट करें
import json
import google.generativeai as genai
import pytz # pytz इम्पोर्ट करें
import traceback # Traceback इम्पोर्ट करें

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
            keys_list = json.loads(key_value)
            if not isinstance(keys_list, list):
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
             return "Set (Empty or Invalid Format)" # Indicate something is set but not parseable

    # Default masking for single keys
    if isinstance(key_value, str) and len(key_value) > 8:
        return f"{key_value[:4]}...{key_value[-4:]}"
    elif isinstance(key_value, str) and key_value:
        return "Set (Short Key)"
    else:
        return "Set (Invalid Format)" # Should ideally be string


@admin_bp.route('/logs')
@login_required
@admin_required
def system_logs():
    page = request.args.get('page', 1, type=int)
    logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=25, error_out=False) # Added error_out=False
    return render_template('admin/system_logs.html', logs=logs)

@admin_bp.route('/cache')
@login_required
@admin_required
def cache_management():
    cache_items = ApiCache.query.order_by(ApiCache.expires_at.desc()).all()
    return render_template('admin/cache_management.html', cache_items=cache_items)

@admin_bp.route('/cache/clear', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    # Add CSRF protection if form is used
    # csrf_token = request.form.get('csrf_token') # Example if using Flask-WTF
    # if not validate_csrf(csrf_token): # Implement validation
    #     abort(400)

    try:
        num_rows_deleted = db.session.query(ApiCache).delete()
        db.session.commit()
        flash(f'Successfully cleared {num_rows_deleted} cache entries.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error clearing cache: {e}', 'error')
    return redirect(url_for('admin.cache_management'))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    # CSRF protection (ensure form includes {{ csrf_token() }} if using Flask-WTF)
    # form = YourSiteSettingsForm() # Replace with your form class if needed
    # if request.method == 'POST' and form.validate_on_submit(): ...

    if request.method == 'POST':
        form_data = request.form.to_dict()

        # Handle checkboxes correctly - value is only sent if checked
        feature_flags = ['feature_referral_system', 'feature_video_upload']
        for flag in feature_flags:
            form_data[flag] = 'True' if flag in form_data else 'False'

        # --- बल्क एडिट लिमिट्स को हैंडल करें ---
        bulk_edit_keys = ['bulk_edit_limit_free', 'bulk_edit_limit_creator', 'bulk_edit_limit_pro']
        for key in bulk_edit_keys:
            value_str = form_data.get(key, '0') # Default to '0' if missing
            try:
                # वैल्यू को integer में बदलने की कोशिश करें, -1 मान्य है
                value_int = int(value_str)
                if value_int < -1: value_int = 0 # -1 से कम वैल्यू को 0 मानें
                form_data[key] = str(value_int) # वापस स्ट्रिंग में बदलें DB के लिए
            except (ValueError, TypeError):
                # अगर integer में नहीं बदलता है, तो डिफ़ॉल्ट वैल्यू सेट करें
                default_val = 50 if 'pro' in key else (20 if 'creator' in key else 0)
                form_data[key] = str(default_val)
                flash(f"Invalid value entered for {key.replace('_', ' ').title()}. Using default: {default_val}", 'warning')
        # --- बदलाव खत्म ---

        # Keys considered secrets - don't save empty value unless overwriting existing
        secret_keys = ['OPENAI_API_KEY', 'YOUTUBE_API_KEYS', 'TELEGRAM_BOT_TOKEN',
                       'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
                       'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                       'GEMINI_API_KEY', # Managed in ai_settings now, but keep for reset logic?
                       'CASHFREE_APP_ID', 'CASHFREE_SECRET_KEY']

        settings_to_update = {}
        settings_to_add = []

        # Prepare updates/inserts
        for key, value in form_data.items():
            if key == 'csrf_token': continue # Skip CSRF token

            setting = SiteSetting.query.get(key)

            # Logic for handling secrets: only update/add if value is provided
            if key in secret_keys:
                if value: # Only save if a new value is provided
                    if setting:
                        settings_to_update[key] = value
                    else:
                        settings_to_add.append(SiteSetting(key=key, value=value))
                # If value is empty, do nothing (don't clear existing secret unless reset explicitly)
            else: # Non-secret keys
                if setting:
                    # Update if value changed
                    if setting.value != value:
                        settings_to_update[key] = value
                else:
                    # Add new non-secret setting
                    settings_to_add.append(SiteSetting(key=key, value=value))

        try:
            # Perform updates
            for key, value in settings_to_update.items():
                SiteSetting.query.filter_by(key=key).update({'value': value})

            # Perform inserts
            if settings_to_add:
                db.session.bulk_save_objects(settings_to_add)

            db.session.commit()
            flash('Site settings updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'error')
            # Log the error for debugging
            log_system_event("Error saving site settings", "ERROR", {'error': str(e), 'traceback': traceback.format_exc()})


        return redirect(url_for('admin.site_settings'))

    # GET Request Handling
    try:
        settings_list = SiteSetting.query.all()
        settings = {s.key: s.value for s in settings_list}
    except exc.OperationalError as e:
         # Handle case where table might not exist yet (e.g., initial migration)
         flash("Could not load settings from database. Table might not exist yet.", "warning")
         settings = {}
         log_system_event("Failed to load SiteSetting table", "WARNING", {'error': str(e)})


    # Ensure default keys exist if needed by template
    if 'ADMIN_TELEGRAM_CHAT_ID' not in settings:
        settings['ADMIN_TELEGRAM_CHAT_ID'] = ''
    # Add defaults for bulk edit limits if not in DB
    if 'bulk_edit_limit_free' not in settings: settings['bulk_edit_limit_free'] = '0'
    if 'bulk_edit_limit_creator' not in settings: settings['bulk_edit_limit_creator'] = '20'
    if 'bulk_edit_limit_pro' not in settings: settings['bulk_edit_limit_pro'] = '50'


    return render_template('admin/site_settings.html', settings=settings, mask_key=mask_api_key)


@admin_bp.route('/settings/reset/<string:key_name>', methods=['POST'])
@login_required
@admin_required
def reset_setting(key_name):
    # Add CSRF protection here as well
    # ...

    setting = SiteSetting.query.get(key_name)
    if setting:
        try:
            db.session.delete(setting)
            db.session.commit()
            flash(f"Setting '{key_name}' removed from database. The application will now use the value from the .env file (if available) or its internal default.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error resetting setting '{key_name}': {str(e)}", 'error')
            log_system_event(f"Error resetting setting {key_name}", "ERROR", {'error': str(e)})
    else:
        flash(f"Setting '{key_name}' was not found in the database (already using default).", 'info')

    # Redirect based on where the reset was likely triggered
    if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name:
         return redirect(url_for('admin.ai_settings'))
    else:
         return redirect(url_for('admin.site_settings'))


@admin_bp.route('/ai-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_settings():
    # CSRF protection
    # ...

    if request.method == 'POST':
        keys_from_form = request.form.getlist('gemini_keys')
        # Filter out empty strings explicitly
        valid_keys = [key.strip() for key in keys_from_form if key and key.strip()]
        # Store as JSON list string
        keys_json = json.dumps(valid_keys)

        # Update or create GEMINI_API_KEY setting
        keys_setting = SiteSetting.query.filter_by(key='GEMINI_API_KEY').first()
        if keys_setting:
            keys_setting.value = keys_json
        elif valid_keys: # Only add if there are actual keys
            new_keys_setting = SiteSetting(key='GEMINI_API_KEY', value=keys_json)
            db.session.add(new_keys_setting)

        # Update or create SELECTED_AI_MODEL setting
        selected_model = request.form.get('selected_model')
        if selected_model: # Ensure a model was actually selected
            model_setting = SiteSetting.query.filter_by(key='SELECTED_AI_MODEL').first()
            if model_setting:
                model_setting.value = selected_model
            else:
                new_model_setting = SiteSetting(key='SELECTED_AI_MODEL', value=selected_model)
                db.session.add(new_model_setting)

        # Update or create/delete Prompts
        prompt_keys = ['prompt_generate_ideas', 'prompt_titles_and_tags', 'prompt_description']
        for key in prompt_keys:
            value = request.form.get(key, '').strip() # Default to empty string and strip
            setting = SiteSetting.query.filter_by(key=key).first()
            if setting:
                if value:
                    setting.value = value # Update if value provided
                else:
                    db.session.delete(setting) # Delete if value is empty
            elif value: # Only create if not empty
                new_setting = SiteSetting(key=key, value=value)
                db.session.add(new_setting)

        try:
            db.session.commit()
            flash('AI Settings updated successfully! Changes to API keys might require an application restart to take full effect.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving AI settings: {str(e)}', 'error')
            log_system_event("Error saving AI settings", "ERROR", {'error': str(e), 'traceback': traceback.format_exc()})

        return redirect(url_for('admin.ai_settings'))

    # GET Request
    current_keys = [] # Default to empty list
    keys_setting_value = get_config_value('GEMINI_API_KEY', '[]') # Get from DB or Env, default to empty JSON list string

    try:
        loaded_keys = json.loads(keys_setting_value)
        if isinstance(loaded_keys, list):
            current_keys = loaded_keys # Keep empty list if that's what was loaded
    except json.JSONDecodeError:
        # Handle case where value might be comma-separated string from .env or old DB value
        if isinstance(keys_setting_value, str):
            current_keys = [k.strip() for k in keys_setting_value.split(',') if k.strip()]
        else:
             flash("Error reading saved Gemini API keys. Format seems incorrect.", "error")
             current_keys = [] # Fallback to empty

    # Add an empty input field if no keys are present
    if not current_keys:
         current_keys = [""]


    def get_model_display_info(model_name):
        # Simplified display logic
        if not model_name: return "Unknown Model"
        if "flash" in model_name: return "Fast & cost-effective"
        if "pro" in model_name: return "Powerful & versatile"
        return "General model"

    # Default available model
    available_models_info = [{'name': 'gemini-1.5-flash-latest', 'display': get_model_display_info('gemini-1.5-flash-latest')}]

    # Try fetching models from Google using the first valid key found
    first_valid_key = next((key for key in current_keys if key and key.strip()), None)
    if first_valid_key:
        try:
            genai.configure(api_key=first_valid_key)
            fetched_models = []
            for m in genai.list_models():
                # Filter for models supporting 'generateContent'
                if 'generateContent' in m.supported_generation_methods:
                    model_name = m.name.replace('models/', '') # Clean name
                    # Optional: Add filters here if needed, e.g., exclude older models
                    # if 'gemini-1.0' not in model_name:
                    fetched_models.append({'name': model_name, 'display': get_model_display_info(model_name)})

            if fetched_models:
                # Deduplicate and sort (e.g., flash first, then others alphabetically)
                unique_models = {d['name']: d for d in fetched_models}
                available_models_info = sorted(unique_models.values(), key=lambda x: ('flash' not in x['name'], x['name']))
            else:
                 flash("Could not find any compatible models using the first API key.", "warning")

        except Exception as e:
            flash(f"Could not fetch latest models from Google: {str(e)[:150]}...", "warning")
            # Keep the default model in the list even if fetching fails
    else:
        flash("Add a valid Gemini API key to fetch the list of available models.", "info")

    selected_model = get_config_value('SELECTED_AI_MODEL', 'gemini-1.5-flash-latest')
    # Fetch all settings again for prompts
    settings = {s.key: s.value for s in SiteSetting.query.all()}

    return render_template(
        'admin/ai_settings.html',
        current_keys=current_keys,
        available_models_info=available_models_info,
        selected_model=selected_model,
        settings=settings # Pass all settings for prompts
    )


@admin_bp.route('/api/test-ai-config', methods=['POST'])
@login_required
@admin_required
def test_ai_config():
    # CSRF protection could be added here if needed
    data = request.json
    api_keys = data.get('keys', [])
    model_name = data.get('model')

    if not model_name:
         return jsonify({'status': 'error', 'message': 'Model name is required for testing.'}), 400
    if not isinstance(api_keys, list):
         return jsonify({'status': 'error', 'message': 'Keys must be provided as a list.'}), 400

    results = []
    overall_success = False
    valid_keys_provided = False

    for key in api_keys:
        key = key.strip() # Ensure no leading/trailing whitespace
        if not key: continue # Skip empty keys in the list
        valid_keys_provided = True
        key_masked = mask_api_key(key) # Use the same masking function
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name)
            # Use a minimal generate_content call to verify key and model access
            response = model.generate_content("test", generation_config={'max_output_tokens': 1, 'temperature': 0})
            # Basic check if response has text (more robust checks could be added)
            if hasattr(response, 'text') and isinstance(response.text, str):
                 results.append({'key_mask': key_masked, 'status': 'Valid'})
                 overall_success = True # At least one key worked
            else:
                 results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': 'API Response Invalid'})
        except Exception as e:
            error_message = str(e).lower() # Lowercase for easier matching
            error_detail = "Failed (Check Model/Key/Billing)" # Default error
            # More specific error checks based on google.generativeai exceptions if possible
            # Example using string matching (less reliable than specific exceptions)
            if 'api_key_not_valid' in error_message or 'provide an api key' in error_message:
                error_detail = "API Key Invalid"
            elif 'permission_denied' in error_message:
                 # This often relates to project setup, API enabling, or billing
                 error_detail = "Permission Denied (Check Project/API/Billing)"
            elif 'quota' in error_message:
                 error_detail = "Quota Exceeded"
            elif '404' in error_message or 'not found' in error_message:
                 error_detail = "Model Not Found or Not Available for Key"
            elif 'invalid argument' in error_message: # Broader category
                 error_detail = "Invalid Argument (Check Model Name?)"

            results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': error_detail})

    if not valid_keys_provided:
        return jsonify({'status': 'error', 'message': 'No valid API keys were provided in the list to test.'})

    return jsonify({'status': 'success' if overall_success else 'error', 'results': results})


# --- डेटा रूट्स पहले जैसे ही रहेंगे ---
@admin_bp.route('/data/user_growth')
@login_required
@admin_required
def user_growth_data():
    thirty_days_ago = date.today() - timedelta(days=29)
    try:
        user_counts = db.session.query(
            func.count(User.id),
            func.date(User.created_at) # Use func.date for grouping
        ).filter(
            User.created_at >= thirty_days_ago # Filter by datetime
        ).group_by(
            func.date(User.created_at) # Group by date part
        ).order_by(
            func.date(User.created_at) # Order by date part
        ).all()
        counts_by_date = {day: count for count, day in user_counts}
    except Exception as e:
         log_system_event("Error fetching user growth data", "ERROR", {'error': str(e)})
         counts_by_date = {} # Return empty on error


    labels = [(thirty_days_ago + timedelta(days=i)).strftime('%d %b') for i in range(30)]
    # Use .date() when looking up in counts_by_date
    data = [counts_by_date.get((thirty_days_ago + timedelta(days=i)).date(), 0) for i in range(30)]

    return jsonify({'labels': labels, 'data': data})

@admin_bp.route('/data/plan_distribution')
@login_required
@admin_required
def plan_distribution_data():
    try:
        plan_counts = db.session.query(
            User.subscription_plan,
            func.count(User.id)
        ).group_by(User.subscription_plan).all()
        plan_data = {plan: count for plan, count in plan_counts}
    except Exception as e:
        log_system_event("Error fetching plan distribution data", "ERROR", {'error': str(e)})
        plan_data = {} # Return empty on error


    labels = ['Free', 'Creator', 'Pro']
    data = [
        plan_data.get('free', 0),
        plan_data.get('creator', 0),
        plan_data.get('pro', 0)
    ]

    return jsonify({'labels': labels, 'data': data})