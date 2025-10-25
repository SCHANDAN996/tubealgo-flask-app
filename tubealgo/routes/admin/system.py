# tubealgo/routes/admin/system.py

from flask import render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required
from flask_wtf import FlaskForm
from flask_wtf.csrf import generate_csrf, validate_csrf, ValidationError
from . import admin_bp
from ... import db
from ...decorators import admin_required
from sqlalchemy import func, cast, Date, exc, text # text इम्पोर्ट किया गया
from datetime import date, timedelta, datetime
from ...models import SystemLog, ApiCache, SiteSetting, get_config_value, User, get_setting, log_system_event, APIKeyStatus
import json
import google.generativeai as genai
import pytz
import traceback

class CSRFOnlyForm(FlaskForm):
    """A simple form containing only the CSRF token field."""
    pass

def mask_api_key(key_name):
    """Masks an API key for display, handling potential lists."""
    key_value = get_config_value(key_name)
    if not key_value:
        return "Not Set"

    if key_name in ['GEMINI_API_KEY', 'YOUTUBE_API_KEYS']:
        keys_list = []
        try:
            loaded_keys = json.loads(key_value)
            if isinstance(loaded_keys, list):
                keys_list = [k.strip() for k in loaded_keys if isinstance(k, str) and k.strip()]
        # <<< FIX: Indentation corrected here >>>
        except (json.JSONDecodeError, TypeError):
            # Fallback for comma-separated or plain string
            [cite_start]if isinstance(key_value, str): # [cite: 1626]
                keys_list = [k.strip() for k in key_value.split(',') if k.strip()]
                # If splitting by comma gives one item, treat it as a single key if no comma was present
                [cite_start]if len(keys_list) == 1 and ',' not in key_value: # [cite: 1627]
                    keys_list = [key_value.strip()] # Treat as single key
            # <<< END FIX >>>

        if keys_list:
             first_key = keys_list[0]
             masked_first = f"{first_key[:4]}...{first_key[-4:]}" if len(first_key) > 8 else "Short Key"
             return f"~{len(keys_list)} keys set (e.g., {masked_first})"
        else:
             [cite_start]if key_value and isinstance(key_value, str) and key_value.strip(): # [cite: 1628]
                 return "Set (Invalid Format)"
             else:
                 return "Not Set or Empty"

    # Default masking for single keys
    if isinstance(key_value, str) and len(key_value) > 8:
        return f"{key_value[:4]}...{key_value[-4:]}"
    elif isinstance(key_value, str) and key_value:
        return "Set (Short Key)"
    else:
        [cite_start]if key_value: # [cite: 1629]
             return "Set (Invalid Format)"
        else:
             return "Not Set or Empty"

# --- बाकी के रूट्स (logs, cache, settings, ai-settings, test-config, user-growth, plan-distribution) पहले जैसे ही रहेंगे ---
# --- सुनिश्चित करें कि उनमें सही इम्पोर्ट्स ('SiteSetting', 'text') और CSRF हैंडलिंग हो ---

@admin_bp.route('/logs')
@login_required
@admin_required
def system_logs():
    page = request.args.get('page', 1, type=int)
    logs_pagination = None
    try:
        logs_pagination = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=25, error_out=False)
    except (exc.OperationalError, exc.ProgrammingError) as e:
        [cite_start]flash("Could not load system logs. Database table might be missing.", "error") # [cite: 1630]
        [cite_start]log_system_event("Failed to query SystemLog table", "ERROR", details=str(e)) # [cite: 1630]
        [cite_start]db.session.rollback() # [cite: 1630]
        from flask_sqlalchemy.pagination import Pagination
        [cite_start]logs_pagination = Pagination(None, page, 25, 0, []) # [cite: 1630]
    return render_template('admin/system_logs.html', logs=logs_pagination)


@admin_bp.route('/cache')
@login_required
@admin_required
def cache_management():
    cache_items = []
    try:
        cache_items = ApiCache.query.order_by(ApiCache.expires_at.desc()).all()
    except (exc.OperationalError, exc.ProgrammingError) as e:
        [cite_start]flash("Could not load cache items. Database table might be missing.", "error") # [cite: 1631]
        [cite_start]log_system_event("Failed to query ApiCache table", "ERROR", details=str(e)) # [cite: 1631]
        [cite_start]db.session.rollback() # [cite: 1631]
    form = CSRFOnlyForm()
    return render_template('admin/cache_management.html', cache_items=cache_items, form=form)


@admin_bp.route('/cache/clear', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        try:
            num_rows_deleted = db.session.query(ApiCache).delete()
            db.session.commit()
            flash(f'Successfully cleared {num_rows_deleted} cache entries.', 'success')
        except Exception as e:
            [cite_start]db.session.rollback() # [cite: 1632]
            [cite_start]flash(f'Error clearing cache: {e}', 'error') # [cite: 1632]
            [cite_start]log_system_event("Error clearing cache", "ERROR", details=str(e)) # [cite: 1632]
    else:
        [cite_start]current_app.logger.warning(f"CSRF validation failed for clear_cache: {form.errors}") # [cite: 1632]
        [cite_start]flash("Invalid request or security token expired.", 'error') # [cite: 1632]
    return redirect(url_for('admin.cache_management'))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    form = FlaskForm()
    if form.validate_on_submit():
        form_data = request.form.to_dict()
        feature_flags = ['feature_referral_system', 'feature_video_upload']
        for flag in feature_flags:
            [cite_start]form_data[flag] = 'True' if flag in form_data else 'False' # [cite: 1633]
        bulk_edit_keys = ['bulk_edit_limit_free', 'bulk_edit_limit_creator', 'bulk_edit_limit_pro']
        for key in bulk_edit_keys:
            value_str = form_data.get(key, '0')
            value_int = 0
            try:
                value_int = int(value_str)
                value_int = 0 if value_int < -1 else value_int
            [cite_start]except (ValueError, TypeError): # [cite: 1634]
                default_val = -1 if 'pro' in key else (20 if 'creator' in key else 0)
                value_int = default_val
                [cite_start]flash(f"Invalid value for {key.replace('_', ' ').title()}. Using default: {'Unlimited' if default_val == -1 else default_val}", 'warning') # [cite: 1634]
            form_data[key] = str(value_int)
        [cite_start]secret_keys = ['OPENAI_API_KEY', 'YOUTUBE_API_KEYS', 'TELEGRAM_BOT_TOKEN', # [cite: 1635]
                       [cite_start]'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', # [cite: 1635]
                       [cite_start]'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', # [cite: 1635]
                       [cite_start]'CASHFREE_APP_ID', 'CASHFREE_SECRET_KEY'] # [cite: 1635]
        settings_to_update = {}
        settings_to_add = []
        for key, value in form_data.items():
            [cite_start]if key == 'csrf_token': continue # [cite: 1636]
            [cite_start]setting = None # [cite: 1636]
            try:
                setting = SiteSetting.query.get(key)
            except (exc.OperationalError, exc.ProgrammingError) as e:
                 [cite_start]flash("Error accessing settings table. Cannot save.", "error") # [cite: 1636]
                 [cite_start]log_system_event("Error accessing SiteSetting table on save", "ERROR", details=str(e)) # [cite: 1636]
                 [cite_start]db.session.rollback() # [cite: 1637]
                 [cite_start]return redirect(url_for('admin.site_settings')) # [cite: 1637]
            is_secret = key in secret_keys
            if is_secret and key in form_data and not value.strip():
                 continue
            if setting:
                 [cite_start]if setting.value != value: # [cite: 1638]
                      [cite_start]settings_to_update[key] = value # [cite: 1638]
            elif value.strip() or not is_secret:
                settings_to_add.append(SiteSetting(key=key, value=value))
        try:
            for key, value in settings_to_update.items():
                db.session.merge(SiteSetting(key=key, value=value))
            if settings_to_add:
                db.session.bulk_save_objects(settings_to_add)
            [cite_start]db.session.commit() # [cite: 1639]
            [cite_start]flash('Site settings updated successfully!', 'success') # [cite: 1639]
        except Exception as e:
            [cite_start]db.session.rollback() # [cite: 1639]
            [cite_start]flash(f'Error saving settings: {str(e)}', 'error') # [cite: 1639]
            [cite_start]log_system_event("Error saving site settings", "ERROR", details=str(e), traceback_info=traceback.format_exc()) # [cite: 1639]
        return redirect(url_for('admin.site_settings'))
    elif request.method == 'POST':
        [cite_start]current_app.logger.warning(f"CSRF validation failed for site_settings: {form.errors}") # [cite: 1640]
        [cite_start]flash("Invalid request or security token expired. Please try again.", 'error') # [cite: 1640]

    settings = {}
    try:
        settings_list = SiteSetting.query.all()
        settings = {s.key: s.value for s in settings_list}
    except (exc.OperationalError, exc.ProgrammingError) as e:
         [cite_start]flash("Could not load settings from database. Table might be missing.", "warning") # [cite: 1641]
         [cite_start]log_system_event("Failed to load SiteSetting table", "WARNING", details=str(e)) # [cite: 1641]
         [cite_start]db.session.rollback() # [cite: 1641]
    except Exception as e:
         [cite_start]flash(f"An unexpected error occurred loading settings: {e}", "error") # [cite: 1641]
         [cite_start]log_system_event("Unexpected error loading SiteSetting", "ERROR", details=str(e)) # [cite: 1641]
         [cite_start]db.session.rollback() # [cite: 1641]
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
    }
    [cite_start]for key, default_value in default_settings.items(): # [cite: 1642]
        [cite_start]settings.setdefault(key, default_value) # [cite: 1642]
    return render_template('admin/site_settings.html', settings=settings, mask_key=mask_api_key, form=form)


@admin_bp.route('/settings/reset/<string:key_name>', methods=['POST'])
@login_required
@admin_required
def reset_setting(key_name):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('CSRF token validation failed. Could not reset setting.', 'error')
        redirect_url = url_for('admin.ai_settings') if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name else url_for('admin.site_settings')
        return redirect(redirect_url)

    setting = SiteSetting.query.get(key_name)
    if setting:
        try:
            [cite_start]db.session.delete(setting) # [cite: 1643]
            [cite_start]db.session.commit() # [cite: 1643]
            [cite_start]flash(f"Setting '{key_name}' removed from database. Using default.", 'success') # [cite: 1643]
        except Exception as e:
            [cite_start]db.session.rollback() # [cite: 1643]
            [cite_start]flash(f"Error resetting setting '{key_name}': {str(e)}", 'error') # [cite: 1643]
            [cite_start]log_system_event(f"Error resetting setting {key_name}", "ERROR", details=str(e)) # [cite: 1643]
    else:
        flash(f"Setting '{key_name}' not found in DB (already default).", 'info')

    [cite_start]redirect_url = url_for('admin.ai_settings') if key_name.startswith('prompt_') or 'GEMINI' in key_name or 'SELECTED_AI_MODEL' in key_name else url_for('admin.site_settings') # [cite: 1644]
    return redirect(redirect_url)


@admin_bp.route('/ai-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_settings():
    form = FlaskForm()
    if form.validate_on_submit():
        keys_from_form = request.form.getlist('gemini_keys')
        valid_keys = [key.strip() for key in keys_from_form if key and key.strip()]
        keys_json = json.dumps(valid_keys)
        keys_setting = SiteSetting.query.get('GEMINI_API_KEY')
        if keys_setting:
            if keys_setting.value != keys_json: keys_setting.value = keys_json
        elif valid_keys:
            db.session.add(SiteSetting(key='GEMINI_API_KEY', value=keys_json))
        [cite_start]selected_model = request.form.get('selected_model') # [cite: 1645]
        if selected_model:
            model_setting = SiteSetting.query.get('SELECTED_AI_MODEL')
            if model_setting:
                if model_setting.value != selected_model: model_setting.value = selected_model
            else:
                db.session.add(SiteSetting(key='SELECTED_AI_MODEL', value=selected_model))
        prompt_keys = ['prompt_generate_ideas', 'prompt_titles_and_tags', 'prompt_description']
        for key in prompt_keys:
            [cite_start]value = request.form.get(key, '').strip() # [cite: 1646]
            setting = SiteSetting.query.get(key)
            if setting:
                if value:
                    if setting.value != value: setting.value = value
                else:
                    [cite_start]db.session.delete(setting) # [cite: 1647]
            [cite_start]elif value: # [cite: 1647]
                [cite_start]db.session.add(SiteSetting(key=key, value=value)) # [cite: 1647]
        try:
            db.session.commit()
            flash('AI Settings updated successfully!', 'success')
        except Exception as e:
            [cite_start]db.session.rollback() # [cite: 1648]
            [cite_start]flash(f'Error saving AI settings: {str(e)}', 'error') # [cite: 1648]
            [cite_start]log_system_event("Error saving AI settings", "ERROR", details=str(e), traceback_info=traceback.format_exc()) # [cite: 1648]
        return redirect(url_for('admin.ai_settings'))
    elif request.method == 'POST':
        [cite_start]current_app.logger.warning(f"CSRF validation failed for ai_settings: {form.errors}") # [cite: 1648]
        [cite_start]flash("Invalid request or security token expired. Please try again.", 'error') # [cite: 1648]

    # GET Request
    current_keys = []
    keys_setting_value = get_config_value('GEMINI_API_KEY', '[]')
    try:
        loaded_keys = json.loads(keys_setting_value)
        if isinstance(loaded_keys, list): current_keys = [k for k in loaded_keys if isinstance(k, str) and k.strip()]
    [cite_start]except (json.JSONDecodeError, TypeError): # [cite: 1649]
        [cite_start]if isinstance(keys_setting_value, str) and keys_setting_value.strip(): # [cite: 1649]
             [cite_start]current_keys = [k.strip() for k in keys_setting_value.split(',') if k.strip()] # [cite: 1649]
             [cite_start]if len(current_keys) == 1 and ',' not in keys_setting_value: # [cite: 1649]
                 [cite_start]current_keys = [keys_setting_value.strip()] # [cite: 1649]
        else:
            flash("Warning: Could not parse Gemini API keys format.", "warning")
            current_keys = []
    if not current_keys: current_keys = [""]

    def get_model_display_info(model_name):
        [cite_start]if not model_name: return "Unknown Model" # [cite: 1650]
        [cite_start]if "flash" in model_name: return "Fast & cost-effective" # [cite: 1650]
        [cite_start]if "pro" in model_name: return "Powerful & versatile" # [cite: 1650]
        [cite_start]return "General model" # [cite: 1650]

    default_model = 'gemini-1.5-flash-latest'
    available_models_info = [{'name': default_model, 'display': get_model_display_info(default_model)}]
    first_valid_key = next((key for key in current_keys if key), None)
    if first_valid_key:
        try:
            genai.configure(api_key=first_valid_key)
            fetched_models = []
            [cite_start]for m in genai.list_models(): # [cite: 1651]
                [cite_start]if 'generateContent' in m.supported_generation_methods: # [cite: 1651]
                    [cite_start]model_name = m.name.replace('models/', '') # [cite: 1651]
                    [cite_start]fetched_models.append({'name': model_name, 'display': get_model_display_info(model_name)}) # [cite: 1651]
            if fetched_models:
                unique_models_dict = {d['name']: d for d in fetched_models}
                [cite_start]available_models_info = sorted(unique_models_dict.values(), key=lambda x: ('flash' not in x['name'], x['name'])) # [cite: 1652]
            else:
                 [cite_start]flash("No compatible Gemini models found for the first API key.", "warning") # [cite: 1652]
                 [cite_start]available_models_info = [{'name': default_model, 'display': get_model_display_info(default_model)}] # [cite: 1652]
        except Exception as e:
            [cite_start]flash(f"Could not fetch available models using the first key: {str(e)[:150]}... Check key validity.", "warning") # [cite: 1653]
            [cite_start]available_models_info = [{'name': default_model, 'display': get_model_display_info(default_model)}] # [cite: 1653]
    else:
        [cite_start]flash("Add a valid Gemini API key to fetch models.", "info") # [cite: 1653]
        [cite_start]available_models_info = [{'name': default_model, 'display': get_model_display_info(default_model)}] # [cite: 1653]

    selected_model = get_config_value('SELECTED_AI_MODEL', default_model)
    settings = {}
    try:
        settings = {s.key: s.value for s in SiteSetting.query.all()}
    except (exc.OperationalError, exc.ProgrammingError):
        flash("Could not load prompt settings from database.", "warning")
        db.session.rollback()

    [cite_start]return render_template('admin/ai_settings.html', # [cite: 1654]
                           [cite_start]current_keys=current_keys, # [cite: 1654]
                           [cite_start]available_models_info=available_models_info, # [cite: 1654]
                           [cite_start]selected_model=selected_model, # [cite: 1654]
                           [cite_start]settings=settings, # [cite: 1654]
                           [cite_start]form=form) # Pass form instance # [cite: 1655]


@admin_bp.route('/api/test-ai-config', methods=['POST'])
@login_required
@admin_required
def test_ai_config():
    csrf_token_from_request = request.json.get('csrf_token') or request.headers.get('X-CSRFToken')
    try:
        if csrf_token_from_request:
            validate_csrf(csrf_token_from_request)
        else:
            raise ValidationError('CSRF token missing')
    except ValidationError as e:
        current_app.logger.warning(f"CSRF validation failed for test_ai_config: {e}")
        return jsonify({'status': 'error', 'message': 'CSRF token validation failed.'}), 400

    [cite_start]data = request.json; api_keys = data.get('keys', []); model_name = data.get('model') # [cite: 1656]
    [cite_start]if not model_name: return jsonify({'status': 'error', 'message': 'Model name required.'}), 400 # [cite: 1656]
    [cite_start]if not isinstance(api_keys, list): return jsonify({'status': 'error', 'message': 'Keys must be a list.'}), 400 # [cite: 1656]

    [cite_start]results = []; overall_success = False; valid_keys_provided = False # [cite: 1656]
    for key in api_keys:
        key = key.strip();
        if not key: continue;
        valid_keys_provided = True
        key_masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "Short Key"
        try:
            genai.configure(api_key=key);
            model = genai.GenerativeModel(model_name)
            [cite_start]response = model.generate_content("Say 'Test OK'", generation_config={'max_output_tokens': 5, 'temperature': 0}) # [cite: 1657]
            [cite_start]if hasattr(response, 'text') and isinstance(response.text, str) and 'ok' in response.text.lower(): # [cite: 1657]
                [cite_start]results.append({'key_mask': key_masked, 'status': 'Valid'}) # [cite: 1657]
                [cite_start]overall_success = True # [cite: 1657]
            else:
                 reason = "API Response Invalid Format"
                 [cite_start]if hasattr(response, 'prompt_feedback') and response.prompt_feedback: # [cite: 1658]
                     [cite_start]reason = f"Prompt Feedback: {response.prompt_feedback}" # [cite: 1658]
                 [cite_start]results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': reason}) # [cite: 1658]
        except Exception as e:
            [cite_start]error_message = str(e).lower(); error_detail = "Failed (Check Model/Key/Billing/Permissions)" # [cite: 1659]
            [cite_start]if 'api_key_not_valid' in error_message or 'provide an api key' in error_message: error_detail = "API Key Invalid" # [cite: 1659]
            [cite_start]elif 'permission_denied' in error_message: error_detail = "Permission Denied (Check Project/API Enablement/Billing)" # [cite: 1659]
            [cite_start]elif 'quota' in error_message: error_detail = "Quota Exceeded" # [cite: 1659]
            [cite_start]elif '404' in error_message or 'not found' in error_message: error_detail = "Model Not Found or Not Available for Key" # [cite: 1659]
            [cite_start]elif '400' in error_message or 'invalid argument' in error_message: error_detail = "Invalid Argument (Check Model Name?)" # [cite: 1659]
            [cite_start]elif 'deadline_exceeded' in error_message: error_detail = "Request Timeout" # [cite: 1659]
            [cite_start]elif 'resource_exhausted' in error_message: error_detail = "Resource Exhausted (Likely Quota)" # [cite: 1660]
            [cite_start]results.append({'key_mask': key_masked, 'status': 'Invalid', 'reason': error_detail}) # [cite: 1660]

    if not valid_keys_provided:
        return jsonify({'status': 'error', 'message': 'No API keys were provided for testing.'})

    return jsonify({'status': 'success' if overall_success else 'error', 'results': results})


@admin_bp.route('/data/user_growth')
@login_required
@admin_required
def user_growth_data():
    thirty_days_ago_dt = datetime.utcnow().date() - timedelta(days=29)
    user_counts = {}
    try:
        user_counts_query = db.session.query(
            func.count(User.id), cast(User.created_at, Date)
        ).filter(
            [cite_start]User.created_at >= thirty_days_ago_dt # [cite: 1661]
        [cite_start]).group_by( # [cite: 1661]
            [cite_start]cast(User.created_at, Date) # [cite: 1661]
        [cite_start]).order_by( # [cite: 1661]
            [cite_start]cast(User.created_at, Date) # [cite: 1661]
        [cite_start]).all() # [cite: 1661]
        user_counts = {day_date: count for count, day_date in user_counts_query}
    except (exc.OperationalError, exc.ProgrammingError) as e:
        [cite_start]log_system_event("Error fetching user growth data", "ERROR", details=str(e), traceback_info=traceback.format_exc()) # [cite: 1661]
        [cite_start]db.session.rollback() # [cite: 1661]
        [cite_start]user_counts = {} # [cite: 1661]
    except Exception as e:
        [cite_start]log_system_event("Unexpected error in user_growth_data", "ERROR", details=str(e), traceback_info=traceback.format_exc()) # [cite: 1662]
        [cite_start]db.session.rollback() # [cite: 1662]
        [cite_start]user_counts = {} # [cite: 1662]

    labels = []
    data = []
    for i in range(30):
        current_date = thirty_days_ago_dt + timedelta(days=i)
        labels.append(current_date.strftime('%d %b'))
        data.append(user_counts.get(current_date, 0))

    return jsonify({'labels': labels, 'data': data})

@admin_bp.route('/data/plan_distribution')
@login_required
@admin_required
def plan_distribution_data():
    plan_data = {}
    try:
        plan_counts = db.session.query(
            User.subscription_plan,
            [cite_start]func.count(User.id) # [cite: 1663]
        [cite_start]).group_by(User.subscription_plan).all() # [cite: 1663]
        [cite_start]plan_data = {plan: count for plan, count in plan_counts} # [cite: 1663]
    except (exc.OperationalError, exc.ProgrammingError) as e:
        [cite_start]log_system_event("Error fetching plan distribution data", "ERROR", details=str(e)) # [cite: 1663]
        [cite_start]db.session.rollback() # [cite: 1663]
        [cite_start]plan_data = {} # [cite: 1663]
    except Exception as e:
        [cite_start]log_system_event("Unexpected error in plan_distribution_data", "ERROR", details=str(e)) # [cite: 1663]
        [cite_start]db.session.rollback() # [cite: 1663]
        [cite_start]plan_data = {} # [cite: 1663]

    labels = ['Free', 'Creator', 'Pro']
    [cite_start]data = [plan_data.get('free', 0), plan_data.get('creator', 0), plan_data.get('pro', 0)] # [cite: 1664]
    return jsonify({'labels': labels, 'data': data})
