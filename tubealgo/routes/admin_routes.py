# tubealgo/routes/admin_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from tubealgo.decorators import admin_required
from tubealgo import db, csrf
from tubealgo.models import User, SubscriptionPlan, SystemLog, SystemSetting
from tubealgo.forms.admin_forms import AdminUserForm
from sqlalchemy import desc
import traceback

admin_bp = Blueprint('admin', __name__)

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
        flash(f"Error loading dashboard: {str(e)}", "error")
        return render_template('admin/dashboard.html')

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """List all users"""
    try:
        users_list = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin/users.html', users=users_list)
    except Exception as e:
        flash(f"Error loading users: {str(e)}", "error")
        return render_template('admin/users.html', users=[])

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_details(user_id):
    """User details page"""
    try:
        user = User.query.get_or_404(user_id)
        form = AdminUserForm()
        form.plan.data = user.subscription_plan
        return render_template('admin/user_details.html', user=user, form=form)
    except Exception as e:
        flash(f"Error loading user details: {str(e)}", "error")
        return redirect(url_for('admin.users'))

@admin_bp.route('/users/upgrade/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def upgrade_user(user_id):
    """Upgrade user subscription plan"""
    form = AdminUserForm()
    
    if form.validate_on_submit():
        try:
            user = User.query.get_or_404(user_id)
            new_plan = form.plan.data
            
            if new_plan in ['free', 'creator', 'pro']:
                old_plan = user.subscription_plan
                user.subscription_plan = new_plan
                db.session.commit()
                
                # Log the action
                SystemLog.log_system_event(
                    message=f"Admin {current_user.email} changed user {user.email} plan from {old_plan} to {new_plan}",
                    log_type='INFO',
                    details={'admin_id': current_user.id, 'user_id': user_id, 'old_plan': old_plan, 'new_plan': new_plan}
                )
                
                flash(f"User {user.email} has been upgraded to {new_plan} plan.", 'success')
            else:
                flash("Invalid plan selected.", 'error')
                
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating user plan: {str(e)}", "error")
            
    else:
        # CSRF token error or form validation failed
        if 'csrf_token' in form.errors:
            flash("Security token missing or invalid. Please try again.", "error")
        else:
            flash("Form validation failed. Please check your input.", "error")
    
    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/users/suspend/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def suspend_user(user_id):
    """Suspend or activate a user"""
    try:
        user = User.query.get_or_404(user_id)
        
        if user.status == 'active':
            user.status = 'suspended'
            action = 'suspended'
        else:
            user.status = 'active'
            action = 'activated'
            
        db.session.commit()
        
        # Log the action
        SystemLog.log_system_event(
            message=f"Admin {current_user.email} {action} user {user.email}",
            log_type='INFO',
            details={'admin_id': current_user.id, 'user_id': user_id, 'action': action}
        )
        
        flash(f"User {user.email} has been {action}.", 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating user status: {str(e)}", "error")
    
    return redirect(url_for('admin.user_details', user_id=user_id))

@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    """Manage subscription plans"""
    try:
        plans_list = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
        return render_template('admin/plans.html', plans=plans_list)
    except Exception as e:
        flash(f"Error loading plans: {str(e)}", "error")
        return render_template('admin/plans.html', plans=[])

@admin_bp.route('/plans/edit/<string:plan_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_plan(plan_id):
    """Edit subscription plan"""
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first_or_404()
    
    if request.method == 'POST':
        try:
            # Update plan details based on form data
            plan.name = request.form.get('name', plan.name)
            plan.price = int(request.form.get('price', plan.price) or 0)
            plan.slashed_price = int(request.form.get('slashed_price', plan.slashed_price) or 0)
            plan.competitors_limit = int(request.form.get('competitors_limit', plan.competitors_limit) or 0)
            plan.keyword_searches_limit = int(request.form.get('keyword_searches_limit', plan.keyword_searches_limit) or 0)
            plan.ai_generations_limit = int(request.form.get('ai_generations_limit', plan.ai_generations_limit) or 0)
            plan.playlist_suggestions_limit = int(request.form.get('playlist_suggestions_limit', plan.playlist_suggestions_limit) or 0)
            
            # Boolean fields
            plan.has_discover_tools = 'has_discover_tools' in request.form
            plan.has_ai_suggestions = 'has_ai_suggestions' in request.form
            plan.has_comment_reply = 'has_comment_reply' in request.form
            plan.is_popular = 'is_popular' in request.form
            
            db.session.commit()
            
            flash(f"Plan {plan.name} updated successfully.", 'success')
            return redirect(url_for('admin.plans'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating plan: {str(e)}", "error")
    
    return render_template('admin/edit_plan.html', plan=plan)

@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    """View payment history"""
    try:
        # You would typically have a Payment model to query
        # For now, return empty list
        payments_list = []
        return render_template('admin/payments.html', payments=payments_list)
    except Exception as e:
        flash(f"Error loading payments: {str(e)}", "error")
        return render_template('admin/payments.html', payments=[])

@admin_bp.route('/system/logs')
@login_required
@admin_required
def system_logs():
    """View system logs"""
    try:
        logs = SystemLog.query.order_by(desc(SystemLog.timestamp)).limit(100).all()
        return render_template('admin/system_logs.html', logs=logs)
    except Exception as e:
        flash(f"Error loading system logs: {str(e)}", "error")
        return render_template('admin/system_logs.html', logs=[])

@admin_bp.route('/system/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def site_settings():
    """Manage site settings"""
    try:
        if request.method == 'POST':
            # Update settings based on form submission
            site_name = request.form.get('site_name')
            site_announcement = request.form.get('site_announcement')
            maintenance_mode = 'maintenance_mode' in request.form
            
            # Update or create settings
            SystemSetting.set_setting('site_name', site_name)
            SystemSetting.set_setting('site_announcement', site_announcement)
            SystemSetting.set_setting('maintenance_mode', str(maintenance_mode))
            
            flash("Site settings updated successfully.", 'success')
            return redirect(url_for('admin.site_settings'))
        
        # Get current settings
        site_name = SystemSetting.get_setting('site_name', 'TubeAlgo')
        site_announcement = SystemSetting.get_setting('site_announcement', '')
        maintenance_mode = SystemSetting.get_setting('maintenance_mode', 'False') == 'True'
        
        return render_template('admin/site_settings.html',
                             site_name=site_name,
                             site_announcement=site_announcement,
                             maintenance_mode=maintenance_mode)
                             
    except Exception as e:
        flash(f"Error updating site settings: {str(e)}", "error")
        return redirect(url_for('admin.site_settings'))

@admin_bp.route('/system/cache')
@login_required
@admin_required
def cache_management():
    """Cache management page"""
    return render_template('admin/cache_management.html')

@admin_bp.route('/system/cache/clear', methods=['POST'])
@login_required
@admin_required
def clear_cache():
    """Clear system cache"""
    try:
        # Add cache clearing logic here
        # This would depend on your caching implementation
        
        flash("Cache cleared successfully.", 'success')
    except Exception as e:
        flash(f"Error clearing cache: {str(e)}", "error")
    
    return redirect(url_for('admin.cache_management'))

@admin_bp.route('/ai/settings')
@login_required
@admin_required
def ai_settings():
    """AI settings management"""
    try:
        # Get current AI settings
        gemini_key = SystemSetting.get_setting('GEMINI_API_KEY', '')
        openai_key = SystemSetting.get_setting('OPENAI_API_KEY', '')
        
        return render_template('admin/ai_settings.html',
                             gemini_key=gemini_key,
                             openai_key=openai_key)
    except Exception as e:
        flash(f"Error loading AI settings: {str(e)}", "error")
        return render_template('admin/ai_settings.html')

@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    """API endpoint for admin stats (for dashboard widgets)"""
    try:
        total_users = User.query.count()
        subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
        active_today = User.query.filter(User.last_login >= db.func.current_date()).count()
        
        stats = {
            'total_users': total_users,
            'subscribed_users': subscribed_users,
            'active_today': active_today,
            'free_plan': User.query.filter_by(subscription_plan='free').count(),
            'creator_plan': User.query.filter_by(subscription_plan='creator').count(),
            'pro_plan': User.query.filter_by(subscription_plan='pro').count()
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    """Coupon management"""
    try:
        # You would typically have a Coupon model
        coupons_list = []
        return render_template('admin/coupons.html', coupons=coupons_list)
    except Exception as e:
        flash(f"Error loading coupons: {str(e)}", "error")
        return render_template('admin/coupons.html', coupons=[])

@admin_bp.route('/coupons/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_coupon():
    """Create new coupon"""
    if request.method == 'POST':
        try:
            # Add coupon creation logic here
            flash("Coupon created successfully.", 'success')
            return redirect(url_for('admin.coupons'))
        except Exception as e:
            flash(f"Error creating coupon: {str(e)}", "error")
    
    return render_template('admin/create_coupon.html')

@admin_bp.route('/api/permissions')
@login_required
@admin_required
def api_permissions():
    """API permissions management"""
    return render_template('admin/api_permissions.html')