# tubealgo/routes/admin/dashboard.py

from flask import render_template, jsonify # jsonify को import करें
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
# User, Payment, func, cast, Date, datetime, timedelta, log_system_event को import करें
from ...models import User, Payment, SubscriptionPlan, APIKeyStatus, get_config_value, log_system_event
from sqlalchemy import func, cast, Date
from datetime import date, datetime, timedelta
import pytz
import json # json को import करें
import traceback # traceback को import करें
from flask_wtf import FlaskForm # FlaskForm को import करें

class CSRFOnlyForm(FlaskForm): # CSRFOnlyForm की परिभाषा
    pass

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
    users_today = User.query.filter(func.date(User.created_at) == date.today()).count()
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()

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

    def mask_key_yt(key):
        if key and len(key) > 12:
            return f"{key[:8]}...{key[-4:]}"
        return "Invalid Key Format"

    key_identifiers = [mask_key_yt(key) for key in api_keys_list]
    key_statuses_query = APIKeyStatus.query.filter(APIKeyStatus.key_identifier.in_(key_identifiers)).all()
    key_status_map = {status.key_identifier: status for status in key_statuses_query}

    exhausted_today_count = sum(1 for status in key_status_map.values() if status.status == 'exhausted')

    form = CSRFOnlyForm() # फॉर्म इंस्टेंस बनाएं

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           subscribed_users=subscribed_users,
                           users_today=users_today,
                           recent_users=recent_users,
                           api_key_count=len(api_keys_list),
                           key_identifiers=key_identifiers,
                           key_status_map=key_status_map,
                           exhausted_today_count=exhausted_today_count,
                           form=form) # फॉर्म पास करें


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
            User.created_at >= thirty_days_ago_dt
        ).group_by(
            cast(User.created_at, Date)
        ).order_by(
            cast(User.created_at, Date)
        ).all()
        user_counts = {day_date: count for count, day_date in user_counts_query}
    except Exception as e:
        log_system_event("Error fetching user growth data", "ERROR", details=str(e), traceback_info=traceback.format_exc())
        db.session.rollback()
        user_counts = {}

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
            func.count(User.id)
        ).group_by(User.subscription_plan).all()
        plan_data = {plan: count for plan, count in plan_counts}
    except Exception as e:
        log_system_event("Error fetching plan distribution data", "ERROR", details=str(e))
        db.session.rollback()
        plan_data = {}

    labels = ['Free', 'Creator', 'Pro']
    data = [plan_data.get('free', 0), plan_data.get('creator', 0), plan_data.get('pro', 0)]
    return jsonify({'labels': labels, 'data': data})


@admin_bp.route('/data/daily_plan_signups')
@login_required
@admin_required
def daily_plan_signup_data():
    """ पिछले 30 दिनों में हर प्लान के लिए दैनिक नए यूजर/सब्सक्रिप्शन का डेटा देता है """
    try:
        thirty_days_ago_dt = datetime.utcnow().date() - timedelta(days=29)

        # 1. नए Free यूजर्स की गिनती (User टेबल से)
        free_user_counts_query = db.session.query(
            func.count(User.id),
            cast(User.created_at, Date)
        ).filter(
            User.created_at >= thirty_days_ago_dt,
            User.subscription_plan == 'free' # केवल फ्री यूजर्स
        ).group_by(
            cast(User.created_at, Date)
        ).order_by(
            cast(User.created_at, Date)
        ).all()
        free_user_counts = {day_date: count for count, day_date in free_user_counts_query}

        # 2. नए Creator और Pro सब्सक्रिप्शन की गिनती (Payment टेबल से - सफल पेमेंट्स)
        paid_subs_counts_query = db.session.query(
            func.count(Payment.id),
            cast(Payment.created_at, Date),
            Payment.plan_id # प्लान के अनुसार ग्रुप करने के लिए
        ).filter(
            Payment.created_at >= thirty_days_ago_dt,
            Payment.status == 'captured', # केवल सफल पेमेंट्स
            Payment.plan_id.in_(['creator', 'pro']) # केवल पेड प्लान्स
        ).group_by(
            cast(Payment.created_at, Date),
            Payment.plan_id
        ).order_by(
            cast(Payment.created_at, Date)
        ).all()

        creator_subs_counts = {}
        pro_subs_counts = {}
        for count, day_date, plan_id in paid_subs_counts_query:
            if plan_id == 'creator':
                creator_subs_counts[day_date] = count
            elif plan_id == 'pro':
                pro_subs_counts[day_date] = count

        # 3. डेटा को Chart.js के लिए फॉर्मेट करें
        labels = []
        free_data = []
        creator_data = []
        pro_data = []

        for i in range(30):
            current_date = thirty_days_ago_dt + timedelta(days=i)
            labels.append(current_date.strftime('%d %b'))
            free_data.append(free_user_counts.get(current_date, 0))
            creator_data.append(creator_subs_counts.get(current_date, 0))
            pro_data.append(pro_subs_counts.get(current_date, 0))

        return jsonify({
            'labels': labels,
            'datasets': {
                'free': free_data,
                'creator': creator_data,
                'pro': pro_data
            }
        })

    except Exception as e:
        # एरर लॉग करें
        from ...models import log_system_event # log_system_event को इम्पोर्ट करें
        log_system_event("Error fetching daily plan signup data for admin", "ERROR", details=str(e), traceback_info=traceback.format_exc())
        # एरर के साथ खाली डेटा लौटाएं
        return jsonify({'error': 'Could not load plan signup data.', 'labels': [], 'datasets': {'free': [], 'creator': [], 'pro': []}}), 500
