# tubealgo/routes/settings_routes.py

from flask import render_template, request, redirect, url_for, flash, Blueprint
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from tubealgo import db
from tubealgo.models import User, log_system_event
from tubealgo.services.notification_service import send_telegram_message

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/test-telegram', methods=['POST'])
@login_required
def test_telegram():
    """Saves the Chat ID from form (if POST) and then sends a test message."""
    
    if request.method == 'POST':
        chat_id = request.form.get('telegram_chat_id', '').strip()
        if not chat_id or not chat_id.isdigit():
            flash('Please enter a valid numeric Telegram Chat ID to test.', 'error')
            return redirect(url_for('settings.telegram_settings'))
        
        # Check if this chat_id is already taken by another user
        existing_user = User.query.filter(User.id != current_user.id, User.telegram_chat_id == chat_id).first()
        if existing_user:
            flash('This Telegram account is already linked to another user.', 'error')
            return redirect(url_for('settings.telegram_settings'))
        
        # Save the new chat_id before testing
        current_user.telegram_chat_id = chat_id
        db.session.commit()
        flash('Your Telegram Chat ID has been saved!', 'success')

    # Proceed with testing using the saved chat_id
    if not current_user.telegram_chat_id:
        flash('Please set and save your Telegram Chat ID first.', 'error')
        return redirect(url_for('settings.telegram_settings'))

    chat_id_to_test = current_user.telegram_chat_id
    message = "✅ This is a test message from TubeAlgo! Your notifications are working correctly. 🚀"
    
    response = send_telegram_message(chat_id_to_test, message)
    
    if response and response.get('ok'):
        flash('Test message sent successfully! Please check your Telegram.', 'success')
    else:
        error_description = response.get('description', 'Unknown error.') if response else 'Could not connect to Telegram.'
        flash(f'Failed to send test message. Error: {error_description}', 'error')
        
    return redirect(url_for('settings.telegram_settings'))


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = FlaskForm()
    if form.validate_on_submit():
        # Check which button was pressed via its 'name' and 'value' attributes
        action = request.form.get('action')
        
        if action == 'update_phone':
            phone = request.form.get('phone_number', '').strip()
            # Basic validation for a 10-digit number
            if phone.isdigit() and len(phone) >= 10:
                current_user.phone_number = phone
                db.session.commit()
                flash('Your phone number has been updated!', 'success')
            else:
                flash('Please enter a valid phone number (at least 10 digits).', 'error')
        
        elif action == 'update_defaults':
            current_user.default_channel_name = request.form.get('channel_name')
            current_user.default_social_handles = request.form.get('social_handles')
            current_user.default_contact_info = request.form.get('contact_info')
            db.session.commit()
            flash('Your default information has been saved!', 'success')
        
        return redirect(url_for('settings.settings'))

    return render_template('settings.html', form=form, active_page='settings')


@settings_bp.route('/settings/telegram', methods=['GET', 'POST'])
@login_required
def telegram_settings():
    form = FlaskForm()
    if form.validate_on_submit():
        chat_id = request.form.get('telegram_chat_id', '').strip()
        
        if chat_id and chat_id != current_user.telegram_chat_id:
            if not chat_id.isdigit():
                flash('Please enter a valid numeric Telegram Chat ID.', 'error')
            else:
                existing_user = User.query.filter(User.id != current_user.id, User.telegram_chat_id == chat_id).first()
                if existing_user:
                    flash('This Telegram account is already linked to another user.', 'error')
                else:
                    current_user.telegram_chat_id = chat_id
                    message = "🎉 Your Telegram account has been successfully connected to TubeAlgo!"
                    send_telegram_message(chat_id, message)
                    flash('Your Telegram Chat ID has been updated!', 'success')
        elif not chat_id and current_user.telegram_chat_id:
            current_user.telegram_chat_id = None
            flash('Telegram Chat ID has been removed.', 'success')

        current_user.telegram_notify_new_video = 'notify_new_video' in request.form
        current_user.telegram_notify_viral_video = 'notify_viral_video' in request.form
        current_user.telegram_notify_milestone = 'notify_milestone' in request.form
        current_user.telegram_notify_ai_suggestion = 'notify_ai_suggestion' in request.form
        current_user.telegram_notify_weekly_report = 'notify_weekly_report' in request.form
        
        db.session.commit()
        flash('Telegram settings saved successfully!', 'success')
        return redirect(url_for('settings.telegram_settings'))
        
    return render_template('telegram_settings.html', form=form, active_page='settings')

@settings_bp.route('/settings/request-deletion', methods=['POST'])
@login_required
def request_data_deletion():
    log_system_event(
        message=f"Data deletion request received from user: {current_user.email}",
        log_type='USER_ACTION',
        details={'user_id': current_user.id, 'email': current_user.email}
    )
    
    flash('Your data deletion request has been received. We will process it within 7 business days.', 'success')
    return redirect(url_for('settings.settings'))
