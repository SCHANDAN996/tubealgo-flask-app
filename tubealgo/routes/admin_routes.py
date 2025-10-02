# Filepath: tubealgo/routes/admin_routes.py
from flask import render_template, Blueprint, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from tubealgo.models import User, Coupon, SubscriptionPlan, SiteSetting, Payment, ApiCache, get_config_value, APIKeyStatus, SystemLog
from tubealgo.forms import CouponForm, PlanForm
from tubealgo.decorators import admin_required
from tubealgo import db
from datetime import date, timedelta, datetime
from sqlalchemy import func
import pytz

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
    users_today = User.query.filter(func.date(User.created_at) == date.today()).count()
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()

    # API Status Logic
    api_keys_str = get_config_value('YOUTUBE_API_KEYS', '')
    api_keys_list = [key.strip() for key in api_keys_str.split(',') if key.strip()]
    
    try:
        pacific_tz = pytz.timezone('America/Los_Angeles')
        pacific_now = datetime.now(pacific_tz)
        last_reset_pacific = pacific_now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_reset_utc = last_reset_pacific.astimezone(pytz.utc)

        APIKeyStatus.query.filter(
            APIKeyStatus.status == 'exhausted',
            APIKeyStatus.last_failure_at < last_reset_utc
        ).update({'status': 'active', 'last_failure_at': None})
        db.session.commit()
    except Exception as e:
        print(f"Timezone conversion or DB reset failed: {e}")
        db.session.rollback()

    def mask_key(key):
        if key and len(key) > 12:
            return f"{key[:8]}...{key[-4:]}"
        return "Invalid Key Format"
    
    key_identifiers = [mask_key(key) for key in api_keys_list]
    key_statuses_query = APIKeyStatus.query.filter(APIKeyStatus.key_identifier.in_(key_identifiers)).all()
    key_status_map = {status.key_identifier: status for status in key_statuses_query}
    
    exhausted_today_count = sum(1 for status in key_status_map.values() if status.status == 'exhausted')

    return render_template('admin/dashboard.html', 
                           total_users=total_users,
                           subscribed_users=subscribed_users,
                           users_today=users_today,
                           recent_users=recent_users,
                           api_key_count=len(api_keys_list),
                           key_identifiers=key_identifiers,
                           key_status_map=key_status_map,
                           exhausted_today_count=exhausted_today_count)

@admin_bp.route('/data/user_growth')
@login_required
@admin_required
def user_growth_data():
    thirty_days_ago = date.today() - timedelta(days=29)
    
    user_counts_query = db.session.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).filter(User.created_at >= thirty_days_ago).group_by('date').order_by('date').all()
    
    user_counts_dict = {str(item.date): item.count for item in user_counts_query}
    
    labels = []
    data = []
    
    for i in range(30):
        current_date = thirty_days_ago + timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        labels.append(current_date.strftime('%d %b'))
        data.append(user_counts_dict.get(date_str, 0))
        
    return jsonify({'labels': labels, 'data': data})

@admin_bp.route('/data/plan_distribution')
@login_required
@admin_required
def plan_distribution_data():
    plan_counts = db.session.query(
        User.subscription_plan,
        func.count(User.id)
    ).group_by(User.subscription_plan).all()
    
    labels = [item[0].capitalize() for item in plan_counts]
    data = [item[1] for item in plan_counts]
    
    return jsonify({'labels': labels, 'data': data})

@admin_bp.route('/data/monthly_revenue')
@login_required
@admin_required
def monthly_revenue_data():
    revenue_query = db.session.query(
        func.strftime('%Y-%m', Payment.created_at).label('month'),
        func.sum(Payment.amount).label('total')
    ).group_by('month').order_by('month').all()

    labels = [item.month for item in revenue_query]
    data = [item.total / 100 for item in revenue_query]

    return jsonify({'labels': labels, 'data': data})

@admin_bp.route('/logs')
@login_required
@admin_required
def system_logs():
    page = request.args.get('page', 1, type=int)
    logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=25)
    return render_template('admin/system_logs.html', logs=logs)

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
    return render_template('admin/user_details.html', user=user)

@admin_bp.route('/users/upgrade/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def upgrade_user(user_id):
    user = User.query.get_or_404(user_id)
    new_plan = request.form.get('plan')

    if new_plan in ['free', 'creator', 'pro']:
        user.subscription_plan = new_plan
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

@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    page = request.args.get('page', 1, type=int)
    pagination = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/payments.html', pagination=pagination)

@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    all_coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    return render_template('admin/coupons.html', coupons=all_coupons)

@admin_bp.route('/coupons/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_coupon():
    form = CouponForm()
    if form.validate_on_submit():
        new_coupon = Coupon(code=form.code.data.upper(), discount_type=form.discount_type.data, discount_value=form.discount_value.data, max_uses=form.max_uses.data, valid_until=form.valid_until.data)
        db.session.add(new_coupon)
        db.session.commit()
        flash(f"Coupon '{new_coupon.code}' created successfully!", 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/create_coupon.html', form=form, legend='Create New Coupon')

@admin_bp.route('/coupons/edit/<int:coupon_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    form = CouponForm(obj=coupon)
    if form.validate_on_submit():
        coupon.code = form.code.data.upper()
        coupon.discount_type = form.discount_type.data
        coupon.discount_value = form.discount_value.data
        coupon.max_uses = form.max_uses.data
        coupon.valid_until = form.valid_until.data
        db.session.commit()
        flash(f"Coupon '{coupon.code}' updated successfully!", 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/create_coupon.html', form=form, legend=f"Edit Coupon: {coupon.code}")

@admin_bp.route('/coupons/toggle/<int:coupon_id>', methods=['POST'])
@login_required
@admin_required
def toggle_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    status = "activated" if coupon.is_active else "deactivated"
    flash(f"Coupon '{coupon.code}' has been {status}.", 'success')
    return redirect(url_for('admin.coupons'))

@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    all_plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
    return render_template('admin/plans.html', plans=all_plans)

@admin_bp.route('/plans/edit/<int:plan_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    form = PlanForm(obj=plan)
    if form.validate_on_submit():
        plan.price = form.price.data
        plan.slashed_price = form.slashed_price.data
        plan.competitors_limit = form.competitors_limit.data
        plan.keyword_searches_limit = form.keyword_searches_limit.data
        plan.ai_generations_limit = form.ai_generations_limit.data
        plan.has_discover_tools = form.has_discover_tools.data
        plan.has_ai_suggestions = form.has_ai_suggestions.data
        db.session.commit()
        flash(f"Plan '{plan.name}' updated successfully!", 'success')
        return redirect(url_for('admin.plans'))
    return render_template('admin/edit_plan.html', form=form, plan=plan)

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    if request.method == 'POST':
        form_data = request.form.to_dict()
        if 'feature_referral_system' not in form_data:
            form_data['feature_referral_system'] = 'False'
        if 'feature_video_upload' not in form_data:
            form_data['feature_video_upload'] = 'False'

        for key, value in form_data.items():
            secret_keys = [
                'OPENAI_API_KEY', 'YOUTUBE_API_KEYS', 'TELEGRAM_BOT_TOKEN',
                'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
                'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'
            ]
            if key in secret_keys and not value:
                continue
            
            setting = SiteSetting.query.get(key)
            if setting:
                setting.value = value
            else:
                setting = SiteSetting(key=key, value=value)
                db.session.add(setting)
        db.session.commit()
        flash('Site settings updated successfully!', 'success')
        return redirect(url_for('admin.site_settings'))
        
    settings = {s.key: s.value for s in SiteSetting.query.all()}
    
    if 'ADMIN_TELEGRAM_CHAT_ID' not in settings:
        settings['ADMIN_TELEGRAM_CHAT_ID'] = ''

    def mask_key(key_name):
        key_value = settings.get(key_name)
        if key_value and len(key_value) > 8:
            return f"{key_value[:5]}...{key_value[-4:]}"
        elif key_value:
            return "Set"
        return "Not Set"
        
    return render_template('admin/site_settings.html', settings=settings, mask_key=mask_key)

@admin_bp.route('/settings/reset/<string:key_name>', methods=['POST'])
@login_required
@admin_required
def reset_setting(key_name):
    """Deletes a specific setting from the database to revert to .env default."""
    setting = SiteSetting.query.get(key_name)
    if setting:
        db.session.delete(setting)
        db.session.commit()
        flash(f"Setting '{key_name}' has been reset to its default value.", 'success')
    else:
        flash(f"Setting '{key_name}' was not found in the database.", 'warning')
    
    return redirect(url_for('admin.site_settings'))

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
    try:
        num_rows_deleted = db.session.query(ApiCache).delete()
        db.session.commit()
        flash(f'Successfully cleared {num_rows_deleted} cache entries.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error clearing cache: {e}', 'error')
    return redirect(url_for('admin.cache_management'))