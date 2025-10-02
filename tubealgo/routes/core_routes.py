# Filepath: tubealgo/routes/core_routes.py

from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from tubealgo.models import get_setting, SubscriptionPlan
from tubealgo.services.youtube_fetcher import analyze_channel

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def home():
    referral_code = request.args.get('ref')
    if referral_code:
        session['referral_code'] = referral_code
    
    seo_data = {
        'title': get_setting('seo_home_title', 'TubeAlgo - AI YouTube Tool'),
        'description': get_setting('seo_home_description', 'Grow your YouTube channel faster.'),
        'keywords': get_setting('seo_home_keywords', 'youtube, seo, ai')
    }
    return render_template('index.html', **seo_data)

@core_bp.route('/pricing')
def pricing():
    plans = SubscriptionPlan.query.filter(SubscriptionPlan.plan_id != 'free').order_by(SubscriptionPlan.price).all()
    
    seo_data = {
        'title': get_setting('seo_pricing_title', 'Pricing & Plans - TubeAlgo'),
        'description': get_setting('seo_pricing_description', "Explore TubeAlgo's affordable pricing plans.")
    }
    return render_template('pricing.html', plans=plans, **seo_data)

@core_bp.route('/about')
def about():
    seo_data = {
        'title': get_setting('seo_about_title', 'About Us - TubeAlgo'),
        'description': get_setting('seo_about_description', 'Learn about our mission.')
    }
    return render_template('about.html', **seo_data)

# === यहाँ से नया कोड जोड़ा गया है ===
@core_bp.route('/contact')
def contact():
    return render_template('contact.html', title='Contact Us - TubeAlgo')

@core_bp.route('/refund-policy')
def refund_policy():
    return render_template('refund_policy.html', title='Refund Policy - TubeAlgo')

@core_bp.route('/data-disclaimer')
def data_disclaimer():
    return render_template('data_disclaimer.html', title='Data Disclaimer - TubeAlgo')
# === यहाँ तक ===


@core_bp.route('/terms-of-service')
def terms():
    return render_template('terms.html', title='Terms of Service - TubeAlgo')

@core_bp.route('/privacy-policy')
def privacy():
    return render_template('privacy.html', title='Privacy Policy - TubeAlgo')

@core_bp.route('/instant-analysis', methods=['POST'])
def instant_analysis():
    if session.get('free_analysis_used', 0) >= 2:
        flash("You've used your free analyses. Please sign up to continue using the tool!", "error")
        return redirect(url_for('auth.signup'))

    channel_url = request.form.get('channel_url')
    if not channel_url:
        flash('Please enter a channel URL.', 'error')
        return redirect(url_for('core.home'))

    analysis_data = analyze_channel(channel_url)
    if 'error' in analysis_data:
        flash(analysis_data['error'], 'error')
        return redirect(url_for('core.home'))
    
    session['free_analysis_used'] = session.get('free_analysis_used', 0) + 1
    return render_template('analysis_result.html', data=analysis_data, is_guest=True)