# tubealgo/routes/admin/users.py

from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required
from . import admin_bp
from ... import db # <<< यह लाइन बदली गई है
from ...decorators import admin_required
from ...models import User, Competitor, DashboardCache # login_manager की जगह models से User इम्पोर्ट करें
from datetime import datetime, timedelta

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

    remaining_days = None
    if user.subscription_plan != 'free' and user.subscription_end_date:
        # Make sure subscription_end_date is timezone-aware (assuming UTC) or compare naive datetimes
        end_date_aware = user.subscription_end_date.replace(tzinfo=None) if user.subscription_end_date.tzinfo else user.subscription_end_date
        now_aware = datetime.utcnow() # Use UTC now for comparison

        if end_date_aware > now_aware:
            remaining_days = (end_date_aware - now_aware).days
        else:
            remaining_days = 0

    return render_template('admin/user_details.html', user=user, remaining_days=remaining_days)

@admin_bp.route('/users/update_subscription/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_subscription(user_id):
    user = User.query.get_or_404(user_id)
    days_str = request.form.get('days_to_add')

    try:
        days_to_add = int(days_str)

        # Make sure subscription_end_date is timezone-aware (assuming UTC) or use naive UTC now
        end_date_aware = user.subscription_end_date.replace(tzinfo=None) if user.subscription_end_date and user.subscription_end_date.tzinfo else user.subscription_end_date
        now_aware = datetime.utcnow() # Use UTC now

        if end_date_aware and end_date_aware > now_aware:
            user.subscription_end_date = end_date_aware + timedelta(days=days_to_add)
        else:
            # If expired or never set, start from now
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
    # Manually delete related data due to cascade issues or specific logic
    try:
        Competitor.query.filter_by(user_id=user.id).delete()
        DashboardCache.query.filter_by(user_id=user.id).delete()
        # Add other related data deletions here if needed (e.g., ContentIdea, Goal, Payment, SearchHistory)
        # Goal.query.filter_by(user_id=user.id).delete()
        # ContentIdea.query.filter_by(user_id=user.id).delete()
        # Payment.query.filter_by(user_id=user.id).delete() # Be careful deleting payment history
        # SearchHistory.query.filter_by(user_id=user.id).delete()
        # YouTubeChannel.query.filter_by(user_id=user.id).delete() # If channel relationship doesn't cascade correctly

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

        # Delete related data, relying less on cascade if issues arise
        if user.channel:
            db.session.delete(user.channel) # Delete channel object directly

        Competitor.query.filter_by(user_id=user.id).delete()
        DashboardCache.query.filter_by(user_id=user.id).delete()
        # Add deletion for other related models if needed
        # Goal.query.filter_by(user_id=user.id).delete()
        # ContentIdea.query.filter_by(user_id=user.id).delete()
        # SearchHistory.query.filter_by(user_id=user.id).delete()

        db.session.commit()
        flash(f'Account for {user.email} has been reset. All associated channel, competitor, and dashboard data has been cleared.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while resetting the user: {e}', 'error')

    return redirect(url_for('admin.user_details', user_id=user.id))


@admin_bp.route('/users/upgrade/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def upgrade_user(user_id):
    user = User.query.get_or_404(user_id)
    new_plan = request.form.get('plan')
    if new_plan in ['free', 'creator', 'pro']:
        user.subscription_plan = new_plan
        # Only set/extend expiry if upgrading TO a paid plan
        if new_plan != 'free':
            # Check if current subscription exists and is valid
            end_date_aware = user.subscription_end_date.replace(tzinfo=None) if user.subscription_end_date and user.subscription_end_date.tzinfo else user.subscription_end_date
            now_aware = datetime.utcnow()
            # If current subscription is valid, extend it, otherwise start a new 30-day period
            start_date = end_date_aware if end_date_aware and end_date_aware > now_aware else now_aware
            user.subscription_end_date = start_date + timedelta(days=30)

        elif new_plan == 'free':
            # Downgrading to free usually means clearing the end date or letting it expire naturally.
            # Let's clear it for simplicity if manually set to free.
            user.subscription_end_date = None

        db.session.commit()
        flash(f"User {user.email}'s plan has been updated to {new_plan.capitalize()}.", 'success')
    else:
        flash("Invalid plan selected.", 'error')
    return redirect(url_for('admin.user_details', user_id=user.id))

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