# tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app, render_template
from flask_login import current_user, login_required
from tubealgo import db
from tubealgo.models import Payment, SubscriptionPlan, User
import requests
import json
from datetime import datetime
import uuid

payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/create_cashfree_order', methods=['POST'])
@login_required
def create_cashfree_order():
    """Cashfree पर एक नया ऑर्डर बनाता है और पेमेंट सेशन ID लौटाता है।"""
    try:
        data = request.get_json()
        plan_id = data.get('plan')
        
        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return jsonify({'error': 'Invalid plan selected.'}), 400
        
        # Cashfree API कॉन्फ़िगरेशन
        app_id = current_app.config.get('CASHFREE_APP_ID')
        secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        env = current_app.config.get('CASHFREE_ENV', 'PROD').upper()
        
        if not app_id or not secret_key:
            return jsonify({'error': 'Payment gateway is not configured on the server.'}), 500
        
        base_url = "https://api.cashfree.com/pg" if env == 'PROD' else "https://sandbox.cashfree.com/pg"
        
        # एक यूनिक ऑर्डर ID बनाएँ
        order_id = f"TA_{current_user.id}_{uuid.uuid4().hex[:12]}"
        
        order_data = {
            "order_amount": plan.price / 100.0,  # पैसे को रुपये में बदलें
            "order_currency": "INR",
            "order_id": order_id,
            "customer_details": {
                "customer_id": str(current_user.id),
                "customer_email": current_user.email,
                "customer_phone": "9999999999"  # एक डिफ़ॉल्ट नंबर, आप चाहें तो यूज़र से ले सकते हैं
            },
            "order_meta": {
                # यह URL Cashfree पेमेंट के बाद यूज़र को वापस लाएगा
                "return_url": url_for('payment.cashfree_verification', order_id=order_id, _external=True)
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'x-client-id': app_id,
            'x-client-secret': secret_key,
            'x-api-version': '2022-09-01'
        }
        
        response = requests.post(f"{base_url}/orders", headers=headers, data=json.dumps(order_data))
        response.raise_for_status() # अगर कोई HTTP एरर है तो यहीं रुक जाएगा
        
        response_data = response.json()
        
        if response_data.get('payment_session_id'):
            # डेटाबेस में पेमेंट रिकॉर्ड बनाएँ
            payment = Payment(
                user_id=current_user.id,
                order_id=order_id,
                gateway_order_id=response_data.get('cf_order_id'),
                amount=plan.price,
                plan_id=plan_id,
                status='created'
            )
            db.session.add(payment)
            db.session.commit()
            
            return jsonify({
                'order_id': order_id,
                'payment_session_id': response_data['payment_session_id']
            })
        else:
            return jsonify({'error': 'Failed to create payment session.'}), 500
            
    except requests.exceptions.HTTPError as e:
        error_details = e.response.json().get('message', 'Failed to create order.')
        current_app.logger.error(f"Cashfree API Error: {error_details}")
        return jsonify({'error': error_details}), e.response.status_code
    except Exception as e:
        current_app.logger.error(f"Cashfree order creation unexpected error: {str(e)}")
        return jsonify({'error': 'An internal error occurred while processing payment.'}), 500

@payment_bp.route('/cashfree_verification')
@login_required
def cashfree_verification():
    """पेमेंट के बाद Cashfree से वापस आने पर पेमेंट को वेरिफाई करता है।"""
    order_id = request.args.get('order_id')
    if not order_id:
        flash('Invalid payment verification request.', 'error')
        return redirect(url_for('core.pricing'))

    payment = Payment.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if not payment:
        flash('Payment record not found. Please contact support.', 'error')
        return redirect(url_for('core.pricing'))

    # अगर पेमेंट पहले ही वेरिफाई हो चुका है तो दोबारा न करें
    if payment.status == 'captured':
        flash('Your subscription is already active!', 'success')
        return redirect(url_for('dashboard.dashboard'))

    try:
        # Cashfree से ऑर्डर की स्थिति की जाँच करें
        app_id = current_app.config.get('CASHFREE_APP_ID')
        secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        env = current_app.config.get('CASHFREE_ENV', 'PROD').upper()
        
        base_url = "https://api.cashfree.com/pg" if env == 'PROD' else "https://sandbox.cashfree.com/pg"
        
        headers = {
            'x-client-id': app_id,
            'x-client-secret': secret_key,
            'x-api-version': '2022-09-01'
        }
        
        response = requests.get(f"{base_url}/orders/{order_id}", headers=headers)
        response.raise_for_status()
        
        order_data = response.json()
        
        if order_data.get('order_status') == 'PAID':
            # पेमेंट सफल
            current_user.subscription_plan = payment.plan_id
            payment.status = 'captured'
            payment.gateway_payment_id = order_data.get('cf_payment_id') # पेमेंट ID को स्टोर करें
            db.session.commit()
            flash('Payment successful! Your subscription has been activated.', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            # पेमेंट विफल
            payment.status = 'failed'
            db.session.commit()
            flash(f'Payment failed or is pending. Status: {order_data.get("order_status")}', 'error')
            return redirect(url_for('core.pricing'))

    except Exception as e:
        current_app.logger.error(f"Cashfree verification error for order {order_id}: {str(e)}")
        flash('There was an error verifying your payment. Please contact support.', 'error')
        return redirect(url_for('core.pricing'))
