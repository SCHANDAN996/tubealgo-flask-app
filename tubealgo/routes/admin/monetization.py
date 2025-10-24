# tubealgo/routes/admin/monetization.py

from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import Payment, Coupon, SubscriptionPlan
from ...forms import CouponForm, PlanForm

@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    page = request.args.get('page', 1, type=int)
    pagination = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('payments.html', pagination=pagination)

@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    all_coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    return render_template('coupons.html', coupons=all_coupons)

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
    return render_template('create_coupon.html', form=form, legend='Create New Coupon')

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
    return render_template('create_coupon.html', form=form, legend=f"Edit Coupon: {coupon.code}")

@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    all_plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
    return render_template('plans.html', plans=all_plans)

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
        plan.playlist_suggestions_limit = form.playlist_suggestions_limit.data
        plan.has_discover_tools = form.has_discover_tools.data
        plan.has_ai_suggestions = form.has_ai_suggestions.data
        plan.is_popular = form.is_popular.data
        db.session.commit()
        flash(f"Plan '{plan.name}' updated successfully!", 'success')
        return redirect(url_for('admin.plans'))
    return render_template('edit_plan.html', form=form, plan=plan)