# Filepath: tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, SubscriptionPlan, Payment, get_config_value
import time

# Cashfree SDK को इम्पोर्ट करें
from cashfree_pg.api_client import Cashfree
from cashfree_pg.api.orders_api import OrdersApi
from cashfree_pg.exceptions import ApiException
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails

payment_bp = Blueprint('payment', __name__)

# Cashfree क्लाइंट को इनिशियलाइज़ करें
Cashfree.X_CLIENT_ID = get_config_value('CASHFREE_APP_ID')
Cashfree.X_CLIENT_SECRET = get_config_value('CASHFREE_SECRET_KEY')
Cashfree.X_API_VERSION = "2022-09-01"
# 'TEST' या 'PROD' मोड सेट करें (PROD के लिए इसे बदलें)
# अभी के लिए हम 'TEST' का उपयोग करेंगे
Cashfree.X_ENVIRONMENT = Cashfree.SANDBOX 
# जब आप लाइव होंगे, तो इसे Cashfree.PRODUCTION में बदलें

@payment_bp.route('/create-cashfree-order', methods=['POST'])
@login_required
def create_cashfree_order():
    plan_id_from_request = request.json.get('plan')
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id_from_request).first()

    if not plan:
        return jsonify({'error': 'Invalid plan selected.'}), 400

    try:
        order_id = f"tubealgo-order-{int(time.time())}"
        
        create_order_request = CreateOrderRequest(
            order_id=order_id,
            order_amount=float(plan.price / 100),
            order_currency="INR",
            customer_details=CustomerDetails(
                customer_id=str(current_user.id),
                customer_email=current_user.email
            ),
            order_meta={
                "return_url": url_for('payment.cashfree_verification', order_id='{order_id}', _external=True)
            }
        )
        
        api_instance = OrdersApi()
        response = api_instance.create_order(create_order_request)
        
        return jsonify({
            'payment_session_id': response.payment_session_id,
            'order_id': response.order_id
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
        api_instance = OrdersApi()
        response = api_instance.get_order(order_id)

        if response.order_status == "PAID":
            plan_id = response.tags.get('plan', 'creator') # Fallback
            
            # जांचें कि क्या यह पेमेंट पहले से ही रिकॉर्ड किया गया है
            existing_payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if existing_payment:
                flash("This payment has already been processed.", "info")
                return redirect(url_for('dashboard.dashboard'))

            # यूज़र का प्लान अपग्रेड करें
            current_user.subscription_plan = plan_id
            
            # नया पेमेंट रिकॉर्ड बनाएँ
            new_payment = Payment(
                user_id=current_user.id,
                razorpay_payment_id=response.payments.data[0].cf_payment_id if response.payments.data else order_id,
                razorpay_order_id=order_id,
                amount=int(response.order_amount * 100),
                currency=response.order_currency,
                plan_id=plan_id,
                status='captured'
            )
            db.session.add(new_payment)
            db.session.commit()
            
            flash('Payment successful! Your plan has been upgraded.', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash(f"Payment was not successful. Status: {response.order_status}", "error")
            return redirect(url_for('core.pricing'))

    except ApiException as e:
        flash(f"Error verifying payment: {str(e.body)}", "error")
        return redirect(url_for('core.pricing'))
