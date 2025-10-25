# tubealgo/routes/admin/users.py

from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
from flask_wtf import FlaskForm # <<< यह इम्पोर्ट जोड़ा गया है
# from flask_wtf.csrf import generate_csrf # <<< यह इम्पोर्ट हटाया गया है
from wtforms import HiddenField # <<< यह इम्पोर्ट जोड़ा गया है (CSRFOnlyForm के लिए)
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import User, Competitor, DashboardCache, Goal, ContentIdea, Payment, SearchHistory, YouTubeChannel
from datetime import datetime, timedelta, timezone

# <<< यह क्लास जोड़ी गई है >>>
class CSRFOnlyForm(FlaskForm):
    """A simple form containing only the CSRF token field."""
    pass # FlaskForm में CSRF टोकन अपने आप शामिल होता है

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '')
    plan_filter = request.args.get('plan', '')
    query = User.query
    if search_term:
        query = query.filter(User.email.ilike(f'%{search_term}%'))
    if plan_filter:
        query = query.filter_by(subscription_plan=plan_filter)
    pagination = query.order_by(User.id.desc()).paginate(page=page, per_page=15)
    return render_template('admin/users.html',
                           pagination=pagination,
                           search_term=search_term,
                           plan_filter=plan_filter)

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_details(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRFOnlyForm() इंस्टैंस बनाया गया >>>
    csrf_form = CSRFOnlyForm() # यह टेम्पलेट में {{ form.hidden_tag() }} के लिए टोकन जेनरेट करेगा

    remaining_days = None
    if user.subscription_plan != 'free' and user.subscription_end_date:
        end_date_aware = user.subscription_end_date # Assume UTC if naive
        if user.subscription_end_date.tzinfo is None:
             end_date_aware = user.subscription_end_date.replace(tzinfo=timezone.utc)
        now_aware = datetime.now(timezone.utc) # Use UTC now

        if end_date_aware > now_aware:
            remaining_days = (end_date_aware - now_aware).days
        else:
            remaining_days = 0

    # <<< बदलाव यहाँ है: form=csrf_form पास किया गया >>>
    return render_template('admin/user_details.html', user=user, remaining_days=remaining_days, form=csrf_form)


@admin_bp.route('/users/update_subscription/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_subscription(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        days_str = request.form.get('days_to_add')
        try:
            days_to_add = int(days_str)
            end_date_aware = user.subscription_end_date # Assume UTC if naive
            if user.subscription_end_date and user.subscription_end_date.tzinfo is None:
                end_date_aware = user.subscription_end_date.replace(tzinfo=timezone.utc)
            now_aware = datetime.now(timezone.utc) # Use UTC now

            if end_date_aware and end_date_aware > now_aware:
                user.subscription_end_date = end_date_aware + timedelta(days=days_to_add)
            else:
                user.subscription_end_date = now_aware + timedelta(days=days_to_add)

            db.session.commit()
            flash(f'Successfully updated subscription for {user.email}.', 'success')
        except (ValueError, TypeError):
            flash('Invalid number of days entered.', 'error')
    else:
        # <<< बदलाव यहाँ है: CSRF एरर मैसेज >>>
        current_app.logger.warning(f"CSRF validation failed for update_subscription (User ID: {user_id}): {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        if user.is_admin:
            flash('Admin users cannot be deleted.', 'error')
            return redirect(url_for('admin.users'))

        email = user.email
        try:
            # Manually delete related data
            Competitor.query.filter_by(user_id=user.id).delete()
            DashboardCache.query.filter_by(user_id=user.id).delete()
            Goal.query.filter_by(user_id=user.id).delete()
            ContentIdea.query.filter_by(user_id=user.id).delete()
            SearchHistory.query.filter_by(user_id=user.id).delete()
            # Delete channel *after* snapshots that might reference it via cascade? Check cascade config.
            # If cascade isn't set up perfectly, delete snapshots first or handle FK constraints.
            # Assuming cascade="all, delete-orphan" on User->YouTubeChannel relationship handles snapshots
            YouTubeChannel.query.filter_by(user_id=user.id).delete()

            # Delete the user itself
            db.session.delete(user)
            db.session.commit()
            flash(f'User {email} and associated data have been permanently deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting user {email} (ID: {user_id}): {e}", exc_info=True)
            flash(f'Error deleting user {email}: {e}', 'error')
    else:
        # <<< बदलाव यहाँ है: CSRF एरर मैसेज >>>
        current_app.logger.warning(f"CSRF validation failed for delete_user (User ID: {user_id}): {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')

    return redirect(url_for('admin.users'))

@admin_bp.route('/users/reset/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_user(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        try:
            # Clear Google tokens
            user.google_access_token = None
            user.google_refresh_token = None
            user.google_token_expiry = None

            # Delete related data
            if user.channel:
                # Assuming cascade="all, delete-orphan" on User->YouTubeChannel handles snapshots
                db.session.delete(user.channel) # Delete channel object directly

            Competitor.query.filter_by(user_id=user.id).delete()
            DashboardCache.query.filter_by(user_id=user.id).delete()
            Goal.query.filter_by(user_id=user.id).delete()
            ContentIdea.query.filter_by(user_id=user.id).delete()
            SearchHistory.query.filter_by(user_id=user.id).delete()

            db.session.commit()
            flash(f'Account for {user.email} has been reset. All associated channel, competitor, dashboard, goal, idea, and search data has been cleared.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error resetting user {user.email} (ID: {user_id}): {e}", exc_info=True)
            flash(f'An error occurred while resetting the user: {e}', 'error')
    else:
        # <<< बदलाव यहाँ है: CSRF एरर मैसेज >>>
        current_app.logger.warning(f"CSRF validation failed for reset_user (User ID: {user_id}): {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/upgrade/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def upgrade_user(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        new_plan = request.form.get('plan')
        if new_plan in ['free', 'creator', 'pro']:
            user.subscription_plan = new_plan
            # Only set/extend expiry if upgrading TO a paid plan
            if new_plan != 'free':
                # Check if current subscription exists and is valid (timezone aware)
                end_date_aware = user.subscription_end_date # Assume UTC if naive
                if user.subscription_end_date and user.subscription_end_date.tzinfo is None:
                    end_date_aware = user.subscription_end_date.replace(tzinfo=timezone.utc)
                now_aware = datetime.now(timezone.utc)

                # If current subscription is valid, extend it, otherwise start a new 30-day period
                start_date = end_date_aware if end_date_aware and end_date_aware > now_aware else now_aware
                user.subscription_end_date = start_date + timedelta(days=30)

            elif new_plan == 'free':
                # Downgrading to free usually means clearing the end date
                user.subscription_end_date = None

            db.session.commit()
            flash(f"User {user.email}'s plan has been updated to {new_plan.capitalize()}.", 'success')
        else:
            flash("Invalid plan selected.", 'error')
    else:
        # <<< बदलाव यहाँ है: CSRF एरर मैसेज >>>
        current_app.logger.warning(f"CSRF validation failed for upgrade_user (User ID: {user_id}): {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/users/toggle-status/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    # <<< बदलाव यहाँ है: CSRF वैलिडेशन जोड़ा गया >>>
    form = CSRFOnlyForm()
    if form.validate_on_submit():
        if user.status == 'active':
            user.status = 'suspended'
            flash(f"User {user.email} has been suspended.", 'success')
        else:
            user.status = 'active'
            flash(f"User {user.email} has been reactivated.", 'success')
        db.session.commit()
    else:
        # <<< बदलाव यहाँ है: CSRF एरर मैसेज >>>
        current_app.logger.warning(f"CSRF validation failed for toggle_user_status (User ID: {user_id}): {form.errors}")
        flash("Invalid request or security token expired. Please try again.", 'error')

    return redirect(url_for('admin.user_details', user_id=user.id))
