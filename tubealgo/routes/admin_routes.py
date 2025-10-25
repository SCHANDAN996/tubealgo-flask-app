# tubealgo/routes/admin_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm # Import FlaskForm
from tubealgo.decorators import admin_required
from tubealgo import db, csrf
# <<< बदलाव यहाँ है: SystemSetting को SiteSetting से बदला गया >>>
from tubealgo.models import User, SubscriptionPlan, SystemLog, SiteSetting # Was SystemSetting
from tubealgo.forms.admin_forms import AdminUserForm # Assuming this exists
from sqlalchemy import desc
import traceback

admin_bp = Blueprint('admin', __name__)

# <<< CSRFOnlyForm की परिभाषा यहाँ भी जोड़ें (या इसे forms.py से इम्पोर्ट करें) >>>
class CSRFOnlyForm(FlaskForm):
    """A simple form containing only the CSRF token field."""
    pass

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with system overview"""
    try:
        total_users = User.query.count()
        subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_logs = SystemLog.query.order_by(desc(SystemLog.timestamp)).limit(10).all()

        return render_template('admin/dashboard.html',
                             total_users=total_users,
                             subscribed_users=subscribed_users,
                             recent_users=recent_users,
                             recent_logs=recent_logs)
    except Exception as e:
        # Log the error for debugging
        current_app.logger.error(f"Error loading admin dashboard: {str(e)}", exc_info=True)
        flash(f"Error loading dashboard data. Please check logs.", "error")
        # Render template with empty data or defaults
        return render_template('admin/dashboard.html',
                             total_users=0, subscribed_users=0, recent_users=[], recent_logs=[])


# --- Users Routes ---
# Note: These routes were moved to tubealgo/routes/admin/users.py.
# Ensure they are NOT duplicated here if they exist in that file.
# If they only exist here, keep them, but ensure CSRFOnlyForm is defined or imported.

# --- Plans Routes ---
# Note: These routes seem related to monetization. Consider moving them to monetization.py
@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    """Manage subscription plans"""
    try:
        plans_list = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
        return render_template('admin/plans.html', plans=plans_list)
    except Exception as e:
        current_app.logger.error(f"Error loading plans: {str(e)}", exc_info=True)
        flash(f"Error loading plans: {str(e)}", "error")
        return render_template('admin/plans.html', plans=[])

@admin_bp.route('/plans/edit/<int:plan_id>', methods=['GET', 'POST']) # Changed plan_id to int
@login_required
@admin_required
def edit_plan(plan_id):
    """Edit subscription plan details."""
    plan = SubscriptionPlan.query.get_or_404(plan_id) # Use get_or_404
    # Assuming PlanForm is correctly imported or defined elsewhere
    from tubealgo.forms import SubscriptionPlanForm # Correct import if PlanForm is SubscriptionPlanForm
    form = SubscriptionPlanForm(obj=plan) # Use SubscriptionPlanForm

    if form.validate_on_submit():
        try:
            # Update plan details from form data
            plan.price = form.price.data
            plan.slashed_price = form.slashed_price.data
            plan.competitors_limit = form.competitors_limit.data
            plan.keyword_searches_limit = form.keyword_searches_limit.data
            plan.ai_generations_limit = form.ai_generations_limit.data
            plan.playlist_suggestions_limit = form.playlist_suggestions_limit.data
            plan.has_discover_tools = form.has_discover_tools.data
            plan.has_ai_suggestions = form.has_ai_suggestions.data
            plan.has_comment_reply = form.has_comment_reply.data
            # plan.is_popular = form.is_popular.data # is_popular might not be in your form

            db.session.commit()
            flash(f"Plan '{plan.name}' updated successfully.", 'success')
            return redirect(url_for('admin.plans'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating plan {plan_id}: {str(e)}", exc_info=True)
            flash(f"Error updating plan: {str(e)}", "error")

    # Populate form defaults on GET request if not using obj=plan
    # elif request.method == 'GET':
    #     form.process(obj=plan) # Alternative way to populate form

    # Pass the correct form variable name 'SubscriptionPlanForm' if needed by template,
    # or just 'form' as it's conventionally named.
    return render_template('admin/edit_plan.html', plan=plan, form=form)


# --- Payments Route ---
# Note: Moved to monetization.py? If so, remove from here.
@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    """View payment history"""
    try:
        from tubealgo.models import Payment # Import locally if needed
        page = request.args.get('page', 1, type=int)
        pagination = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
        return render_template('admin/payments.html', pagination=pagination)
    except Exception as e:
        current_app.logger.error(f"Error loading payments: {str(e)}", exc_info=True)
        flash(f"Error loading payments. Please check logs.", "error")
        # Render template with empty pagination
        from flask_sqlalchemy.pagination import Pagination
        pagination = Pagination(None, 1, 20, 0, [])
        return render_template('admin/payments.html', pagination=pagination)

# --- System Logs Route ---
# Note: Moved to system.py? If so, remove from here.
@admin_bp.route('/system/logs')
@login_required
@admin_required
def system_logs():
    """View system logs"""
    try:
        page = request.args.get('page', 1, type=int)
        logs_pagination = SystemLog.query.order_by(desc(SystemLog.timestamp)).paginate(page=page, per_page=25, error_out=False)
        return render_template('admin/system_logs.html', logs=logs_pagination)
    except Exception as e:
        current_app.logger.error(f"Error loading system logs: {str(e)}", exc_info=True)
        flash(f"Error loading system logs. Please check logs.", "error")
        from flask_sqlalchemy.pagination import Pagination
        logs_pagination = Pagination(None, 1, 25, 0, [])
        return render_template('admin/system_logs.html', logs=logs_pagination)

# --- Site Settings Route ---
# Note: Moved to system.py? If so, remove from here.
# Ensure the correct import 'SiteSetting' is used if kept here.

# --- Cache Management Routes ---
# Note: Moved to system.py? If so, remove from here.

# --- AI Settings Routes ---
# Note: Moved to system.py? If so, remove from here.

# --- API Stats Route ---
@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    """API endpoint for admin stats (for dashboard widgets)"""
    try:
        total_users = User.query.count()
        subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
        # Example: Active today based on last_login (if you add that field)
        # active_today = User.query.filter(User.last_login >= db.func.current_date()).count()

        stats = {
            'total_users': total_users,
            'subscribed_users': subscribed_users,
            # 'active_today': active_today,
            'plan_distribution': {
                'free': User.query.filter_by(subscription_plan='free').count(),
                'creator': User.query.filter_by(subscription_plan='creator').count(),
                'pro': User.query.filter_by(subscription_plan='pro').count()
            }
            # Add more stats as needed
        }
        return jsonify(stats)

    except Exception as e:
        current_app.logger.error(f"Error fetching API stats: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# --- Coupons Routes ---
# Note: Moved to monetization.py? If so, remove from here.
@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    """Coupon management"""
    try:
        from tubealgo.models import Coupon # Import locally if needed
        coupons_list = Coupon.query.order_by(Coupon.id.desc()).all()
        return render_template('admin/coupons.html', coupons=coupons_list)
    except Exception as e:
        current_app.logger.error(f"Error loading coupons: {str(e)}", exc_info=True)
        flash(f"Error loading coupons. Please check logs.", "error")
        return render_template('admin/coupons.html', coupons=[])

@admin_bp.route('/coupons/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_coupon():
    """Create new coupon"""
    # Assuming CouponForm is imported or defined
    from tubealgo.forms import CouponForm
    form = CouponForm()
    if form.validate_on_submit():
        try:
            from tubealgo.models import Coupon # Import locally
            # Add coupon creation logic here based on CouponForm fields
            new_coupon = Coupon(
                code=form.code.data.upper(),
                discount_type=form.discount_type.data,
                discount_value=form.discount_value.data
                # Add other fields like max_uses, valid_until if they are in the form
            )
            # Example: Setting optional fields
            if form.max_uses.data:
                 new_coupon.max_uses = form.max_uses.data
            if form.valid_until.data:
                 new_coupon.valid_until = form.valid_until.data # Ensure form field type matches model

            db.session.add(new_coupon)
            db.session.commit()
            flash(f"Coupon '{new_coupon.code}' created successfully.", 'success')
            return redirect(url_for('admin.coupons'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating coupon: {str(e)}", exc_info=True)
            flash(f"Error creating coupon: {str(e)}", "error")

    # Pass form to template for GET request or failed validation
    return render_template('admin/create_coupon.html', form=form, legend="Create New Coupon")

# Add edit_coupon route if needed, similar to create_coupon but fetching the coupon first.


# --- API Permissions Route ---
# Note: This might belong in system.py if it configures system-wide permissions
@admin_bp.route('/api/permissions')
@login_required
@admin_required
def api_permissions():
    """API permissions management (Placeholder)"""
    # You would need a model to store scope permissions
    # Fetch current permissions from DB
    scopes_data = [
        {'id': 1, 'name': 'YouTube Data API', 'description': 'Read channel/video data', 'scope_url': 'https://www.googleapis.com/auth/youtube.readonly', 'is_enabled': True},
        {'id': 2, 'name': 'YouTube Management', 'description': 'Manage videos, playlists', 'scope_url': 'https://www.googleapis.com/auth/youtube', 'is_enabled': True},
        {'id': 3, 'name': 'YouTube Analytics', 'description': 'Read analytics data', 'scope_url': 'https://www.googleapis.com/auth/yt-analytics.readonly', 'is_enabled': True},
         {'id': 4, 'name': 'Google User Info', 'description': 'Read email and profile', 'scope_url': 'openid profile email', 'is_enabled': True}, # Combined
    ]
    return render_template('admin/api_permissions.html', scopes=scopes_data)
