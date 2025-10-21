# tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from tubealgo import db
from tubealgo.models import Payment, SubscriptionPlan, User
import requests
import json
from datetime import datetime, timedelta
import uuid

payment_bp = Blueprint('payment', __name__)

# tubealgo/routes/payment_routes.py

# ... (ऊपर के imports वैसे ही रहेंगे) ...

@payment_bp.route('/create_cashfree_order', methods=['POST'])
@login_required
def create_cashfree_order():
    try:
        # ... (पिछला कोड वैसा ही रहेगा) ...

        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        
        # +++++++++++++ यह नई डीबग लाइन जोड़ें +++++++++++++
        print(f"\n[CRITICAL DEBUG] The application is running in '{cashfree_env}' mode.\n")
        # +++++++++++++++++++++++++++++++++++++++++++++++++++++
        
        base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"
        
        # ... (बाकी का पूरा फंक्शन वैसा ही रहेगा) ...

    except Exception as e:
        current_app.logger.error(f"Cashfree order creation error: {str(e)}", exc_info=True)
        return jsonify({'error': 'An internal server error occurred'}), 500

# ... (बाकी की फाइल वैसी ही रहेगी) ...
        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return jsonify({'error': 'Invalid plan specified.'}), 400

        # अगर यूजर के प्रोफाइल में फोन नंबर नहीं है, तो इसे सेव कर दें
        if not current_user.phone_number:
            current_user.phone_number = phone_number
            db.session.commit()
        
        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        
        if not cashfree_app_id or not cashfree_secret_key:
            return jsonify({'error': 'Payment gateway is not configured on the server.'}), 500
        
        base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"
        order_id = f"order_{current_user.id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
        
        order_data = {
            "order_amount": plan.price / 100,
            "order_currency": "INR",
            "order_id": order_id,
            "customer_details": {
                "customer_id": str(current_user.id),
                "customer_email": current_user.email,
                "customer_phone": phone_number
            },
            "order_meta": {
                "return_url": url_for('payment.cashfree_verification', _external=True) + "?order_id={order_id}"
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }
        
        response = requests.post(f"{base_url}/orders", headers=headers, data=json.dumps(order_data))
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('payment_session_id'):
                # Create a local record of the payment attempt
                payment = Payment(
                    user_id=current_user.id,
                    razorpay_payment_id="",  # Will be updated on verification
                    razorpay_order_id=order_id,
                    amount=plan.price,
                    currency='INR',
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
                current_app.logger.error("Cashfree OK response but no payment_session_id.")
                return jsonify({'error': 'Failed to create payment session from gateway.'}), 500
        else:
            error_msg = response.json().get('message', 'Failed to create order with payment gateway.')
            current_app.logger.error(f"Cashfree API error: {response.status_code} - {response.text}")
            return jsonify({'error': error_msg}), response.status_code
            
    except Exception as e:
        current_app.logger.error(f"Cashfree order creation exception: {str(e)}", exc_info=True)
        return jsonify({'error': 'An internal server error occurred during payment processing.'}), 500

@payment_bp.route('/cashfree_verification')
@login_required
def cashfree_verification():
    try:
        order_id = request.args.get('order_id')
        
        if not order_id:
            flash('Payment verification failed. Order ID not found.', 'error')
            return redirect(url_for('core.pricing'))
        
        payment = Payment.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()
        
        if not payment:
            flash('Payment record not found in our system.', 'error')
            return redirect(url_for('core.pricing'))
        
        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"

        headers = {
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }
        
        order_response = requests.get(f"{base_url}/orders/{order_id}", headers=headers)
        
        if order_response.status_code == 200:
            order_data = order_response.json()
            actual_payment_status = order_data.get('order_status', '').upper()
            
            if actual_payment_status in ['PAID', 'SUCCESS']:
                current_user.subscription_plan = payment.plan_id
                current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                payment.status = 'captured'
                payment.razorpay_payment_id = order_data.get('cf_order_id', order_id) 
                db.session.commit()
                flash('Payment successful! Your subscription has been activated for 30 days.', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                payment.status = 'failed'
                db.session.commit()
                flash(f'Payment {actual_payment_status.lower()}. Please try again or contact support.', 'error')
                return redirect(url_for('core.pricing'))
        else:
            flash('Could not verify payment status with the gateway. Please contact support.', 'error')
            return redirect(url_for('core.pricing'))
            
    except Exception as e:
        current_app.logger.error(f"Cashfree verification exception: {str(e)}", exc_info=True)
        flash('Payment verification failed due to an unexpected error.', 'error')
        return redirect(url_for('core.pricing'))

@payment_bp.route('/cashfree_webhook', methods=['POST'])
def cashfree_webhook():
    try:
        webhook_data = request.get_json()
        
        order_id = webhook_data.get('data', {}).get('order', {}).get('order_id')
        payment_status = webhook_data.get('data', {}).get('order', {}).get('order_status', '').upper()
        
        if payment_status in ['PAID', 'SUCCESS']:
            payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if payment and payment.status != 'captured':
                user = User.query.get(payment.user_id)
                if user:
                    user.subscription_plan = payment.plan_id
                    user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                    payment.status = 'captured'
                    db.session.commit()
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Cashfree webhook error: {str(e)}", exc_info=True)
        return jsonify({'status': 'error'}), 500
