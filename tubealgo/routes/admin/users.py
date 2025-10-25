# tubealgo/routes/admin/users.py

from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required
# from flask_wtf.csrf import generate_csrf # <<<--- यह इम्पोर्ट हटाएं
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import User, Competitor, DashboardCache, Goal, ContentIdea, Payment, SearchHistory, YouTubeChannel
from datetime import datetime, timedelta, timezone

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
    # csrf_token_value = generate_csrf() # <<<--- यह लाइन हटाएं

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

    # <<<--- csrf_token को टेम्प्लेट में पास न करें --->>>
    return render_template('admin/user_details.html', user=user, remaining_days=remaining_days) # csrf_token हटा दिया गया


# update_subscription, delete_user, reset_user, upgrade_user, toggle_user_status फंक्शन पहले जैसे ही रहेंगे...
# उनमें CSRF वैलिडेशन Flask-WTF द्वारा अपने आप हैंडल किया जाना चाहिए अगर फॉर्म ठीक से सेटअप है।

# --- बाकी रूट्स यहाँ हैं ---
@admin_bp.route('/users/update_subscription/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_subscription(user_id):
    user = User.query.get_or_404(user_id)
    days_str = request.form.get('days_to_add')
    try:
        days_to_add = int(days_str)
        end_date_aware = user.subscription_end_date
        if user.subscription_end_date and user.subscription_end_date.tzinfo is None:
             end_date_aware = user.subscription_end_date.replace(tzinfo=timezone.utc)
        now_aware = datetime.now(timezone.utc)
        if end_date_aware and end_date_aware > now_aware:
            user.subscription_end_date = end_date_aware + timedelta(days=days_to_add)
        else:
             user.subscription_end_date = now_aware + timedelta(days=days_to_add)
        db.session.commit()
        flash(f'Successfully updated subscription for {user.email}.', 'success')
    except (ValueError, TypeError):
        flash('Invalid number of days entered.', 'error')
    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Admin users cannot be deleted.', 'error')
        return redirect(url_for('admin.users'))
    email = user.email
    try:
        Competitor.query.filter_by(user_id=user.id).delete()
        DashboardCache.query.filter_by(user_id=user.id).delete()
        Goal.query.filter_by(user_id=user.id).delete()
        ContentIdea.query.filter_by(user_id=user.id).delete()
        SearchHistory.query.filter_by(user_id=user.id).delete()
        YouTubeChannel.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {email} and associated data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user {email}: {e}', 'error')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/reset/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_user(user_id):
    user = User.query.get_or_404(user_id)
    try:
        user.google_access_token = None
        user.google_refresh_token = None
        user.google_token_expiry = None
        if user.channel:
            db.session.delete(user.channel)
        Competitor.query.filter_by(user_id=user.id).delete()
        DashboardCache.query.filter_by(user_id=user.id).delete()
        Goal.query.filter_by(user_id=user.id).delete()
        ContentIdea.query.filter_by(user_id=user.id).delete()
        SearchHistory.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        flash(f'Account for {user.email} has been reset. All associated channel, competitor, dashboard, goal, idea, and search data has been cleared.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while resetting the user: {e}', 'error')
    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/upgrade/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def upgrade_user(user_id):
    user = User.query.get_or_404(user_id)
    new_plan = request.form.get('plan')
    if new_plan in ['free', 'creator', 'pro']:
        user.subscription_plan = new_plan
        if new_plan != 'free':
            end_date_aware = user.subscription_end_date
            if user.subscription_end_date and user.subscription_end_date.tzinfo is None:
                end_date_aware = user.subscription_end_date.replace(tzinfo=timezone.utc)
            now_aware = datetime.now(timezone.utc)
            start_date = end_date_aware if end_date_aware and end_date_aware > now_aware else now_aware
            user.subscription_end_date = start_date + timedelta(days=30)
        elif new_plan == 'free':
            user.subscription_end_date = None
        db.session.commit()
        flash(f"User {user.email}'s plan has been updated to {new_plan.capitalize()}.", 'success')
    else:
        flash("Invalid plan selected.", 'error')
    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/users/toggle-status/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.status == 'active':
        user.status = 'suspended'
        flash(f"User {user.email} has been suspended.", 'success')
    else:
        user.status = 'active'
        flash(f"User {user.email} has been reactivated.", 'success')
    db.session.commit()
    return redirect(url_for('admin.user_details', user_id=user.id))
