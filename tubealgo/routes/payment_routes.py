# Filepath: tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, SubscriptionPlan, Payment, get_config_value
import time

# === यहाँ बदलाव किया गया है (नए वर्शन के हिसाब से इम्पोर्ट) ===
from cashfree_pg import CFCreateOrderRequest, CFCustomerDetails, CFOrderMeta, Cashfree
from cashfree_pg.api.orders import Orders
from cashfree_pg.exceptions import ApiException

payment_bp = Blueprint('payment', __name__)

# Cashfree क्लाइंट को इनिशियलाइज़ करें
# X_CLIENT_ID और X_CLIENT_SECRET को सीधे यहाँ कॉन्फ़िगर करने की ज़रूरत नहीं है,
# SDK उन्हें एनवायरनमेंट से उठा सकता है यदि सही से सेट हो।
# हम उन्हें हर कॉल में स्पष्ट रूप से पास करेंगे ताकि कोई कन्फ्यूजन न हो।

def get_cashfree_config():
    """कैशफ्री कॉन्फ़िगरेशन प्राप्त करने के लिए एक हेल्पर फ़ंक्शन"""
    config = Cashfree.production() if get_config_value('CASHFREE_ENV') == 'PROD' else Cashfree.sandbox()
    config.client_id = get_config_value('CASHFREE_APP_ID')
    config.client_secret = get_config_value('CASHFREE_SECRET_KEY')
    return config

@payment_bp.route('/create-cashfree-order', methods=['POST'])
@login_required
def create_cashfree_order():
    plan_id_from_request = request.json.get('plan')
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id_from_request).first()

    if not plan:
        return jsonify({'error': 'Invalid plan selected.'}), 400

    try:
        config = get_cashfree_config()
        order_api = Orders(config)
        
        # === यहाँ भी कोड को नए वर्शन के हिसाब से अपडेट किया गया है ===
        create_order_request = CFCreateOrderRequest(
            order_id=f"tubealgo-order-{int(time.time())}",
            order_amount=float(plan.price / 100),
            order_currency="INR",
            customer_details=CFCustomerDetails(
                customer_id=str(current_user.id),
                customer_email=current_user.email
            ),
            order_meta=CFOrderMeta(
                return_url=url_for('payment.cashfree_verification', order_id='{order_id}', _external=True)
            ),
            order_tags={
                "plan": plan.plan_id
            }
        )
        
        api_response = order_api.create_order(x_api_version="2022-09-01", cf_create_order_request=create_order_request)
        
        return jsonify({
            'payment_session_id': api_response.payment_session_id,
            'order_id': api_response.order_id
        })

    except ApiException as e:
        print(f"Error creating Cashfree order: {e}")
        return jsonify({'error': str(e.body)}), 500

@payment_bp.route('/cashfree-verification')
@login_required
def cashfree_verification():
    order_id = request.args.get('order_id')
    if not order_id:
        flash("Payment verification failed. Order ID not found.", "error")
        return redirect(url_for('core.pricing'))

    try:
        config = get_cashfree_config()
        order_api = Orders(config)
        
        # === यहाँ भी कोड को नए वर्शन के हिसाब से अपडेट किया गया है ===
        api_response = order_api.get_order(x_api_version="2022-09-01", order_id=order_id)

        if api_response.order_status == "PAID":
            plan_id = api_response.order_tags.get('plan')
            if not plan_id:
                # अगर टैग्स में प्लान नहीं मिला, तो राशि से अनुमान लगाएं
                paid_amount = int(api_response.order_amount * 100)
                matching_plan = SubscriptionPlan.query.filter_by(price=paid_amount).first()
                plan_id = matching_plan.plan_id if matching_plan else 'creator'
            
            existing_payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if existing_payment:
                flash("This payment has already been processed.", "info")
                return redirect(url_for('dashboard.dashboard'))

            current_user.subscription_plan = plan_id
            
            new_payment = Payment(
                user_id=current_user.id,
                razorpay_payment_id=api_response.cf_order_id, # Using cf_order_id
                razorpay_order_id=order_id,
                amount=int(api_response.order_amount * 100),
                currency=api_response.order_currency,
                plan_id=plan_id,
                status='captured'
            )
            db.session.add(new_payment)
            db.session.commit()
            
            flash('Payment successful! Your plan has been upgraded.', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash(f"Payment was not successful. Status: {api_response.order_status}", "error")
            return redirect(url_for('core.pricing'))

    except ApiException as e:
        flash(f"Error verifying payment: {str(e.body)}", "error")
        return redirect(url_for('core.pricing'))
