# Filepath: tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
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
    try:
        data = request.get_json()
        plan_id = data.get('plan')
        
        # Get plan details
        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return jsonify({'error': 'Invalid plan'}), 400
        
        # Cashfree API configuration
        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        
        if not cashfree_app_id or not cashfree_secret_key:
            return jsonify({'error': 'Payment gateway not configured'}), 500
        
        # Determine API base URL based on environment
        if cashfree_env == 'PROD':
            base_url = "https://api.cashfree.com/pg"
        else:
            base_url = "https://sandbox.cashfree.com/pg"
        
        # Create unique order ID
        order_id = f"order_{current_user.id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
        
        # Prepare order data
        order_data = {
            "order_amount": plan.price / 100,  # Convert paise to rupees
            "order_currency": "INR",
            "order_id": order_id,
            "customer_details": {
                "customer_id": str(current_user.id),
                "customer_email": current_user.email,
                "customer_phone": "9999999999"  # Default phone number
            },
            "order_meta": {
                "return_url": url_for('payment.cashfree_verification', _external=True)
            }
        }
        
        # Make API call to Cashfree
        headers = {
            'Content-Type': 'application/json',
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }
        
        response = requests.post(
            f"{base_url}/orders",
            headers=headers,
            data=json.dumps(order_data)
        )
        
        if response.status_code == 200:
            response_data = response.json()
            
            if response_data.get('payment_session_id'):
                # Save payment record
                payment = Payment(
                    user_id=current_user.id,
                    razorpay_payment_id="",  # Keep for compatibility
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
                return jsonify({'error': 'Failed to create payment session'}), 500
        else:
            error_msg = response.json().get('message', 'Failed to create order')
            return jsonify({'error': error_msg}), response.status_code
            
    except Exception as e:
        current_app.logger.error(f"Cashfree order creation error: {str(e)}")
        return jsonify({'error': 'Payment processing failed'}), 500

@payment_bp.route('/cashfree_verification')
@login_required
def cashfree_verification():
    try:
        order_id = request.args.get('order_id')
        payment_status = request.args.get('payment_status', '')
        
        if not order_id:
            flash('Payment verification failed', 'error')
            return redirect(url_for('core.pricing'))
        
        # Find payment record
        payment = Payment.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()
        
        if not payment:
            flash('Payment record not found', 'error')
            return redirect(url_for('core.pricing'))
        
        # Verify payment status with Cashfree API
        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        
        if cashfree_env == 'PROD':
            base_url = "https://api.cashfree.com/pg"
        else:
            base_url = "https://sandbox.cashfree.com/pg"
        
        headers = {
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }
        
        # Get order details from Cashfree
        order_response = requests.get(
            f"{base_url}/orders/{order_id}",
            headers=headers
        )
        
        if order_response.status_code == 200:
            order_data = order_response.json()
            actual_payment_status = order_data.get('order_status', '').upper()
            
            if actual_payment_status in ['PAID', 'SUCCESS']:
                # Update user subscription
                current_user.subscription_plan = payment.plan_id
                payment.status = 'captured'
                db.session.commit()
                flash('Payment successful! Your subscription has been activated.', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                payment.status = 'failed'
                db.session.commit()
                flash('Payment failed or is pending. Please try again.', 'error')
                return redirect(url_for('core.pricing'))
        else:
            # If API verification fails, use the status from redirect
            if payment_status.upper() == 'SUCCESS':
                current_user.subscription_plan = payment.plan_id
                payment.status = 'captured'
                db.session.commit()
                flash('Payment successful! Your subscription has been activated.', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                payment.status = 'failed'
                db.session.commit()
                flash('Payment failed. Please try again.', 'error')
                return redirect(url_for('core.pricing'))
            
    except Exception as e:
        current_app.logger.error(f"Cashfree verification error: {str(e)}")
        flash('Payment verification failed', 'error')
        return redirect(url_for('core.pricing'))

@payment_bp.route('/cashfree_webhook', methods=['POST'])
def cashfree_webhook():
    try:
        webhook_data = request.get_json()
        
        # Verify webhook signature (you should implement this)
        # Implement signature verification as per Cashfree docs
        
        order_id = webhook_data.get('data', {}).get('order', {}).get('order_id')
        payment_status = webhook_data.get('data', {}).get('order', {}).get('order_status', '').upper()
        
        if payment_status in ['PAID', 'SUCCESS']:
            payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if payment and payment.status != 'captured':
                user = User.query.get(payment.user_id)
                if user:
                    user.subscription_plan = payment.plan_id
                    payment.status = 'captured'
                    db.session.commit()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        current_app.logger.error(f"Cashfree webhook error: {str(e)}")
        return jsonify({'status': 'error'}), 500

# Keep existing Razorpay routes for backward compatibility
@payment_bp.route('/create_order', methods=['POST'])
@login_required
def create_order():
    # Your existing Razorpay code here
    return jsonify({'error': 'Razorpay is disabled. Use Cashfree instead.'}), 400

@payment_bp.route('/verification', methods=['POST'])
@login_required
def verification():
    # Your existing Razorpay code here
    flash('Razorpay is disabled. Please use Cashfree payments.', 'error')
    return redirect(url_for('core.pricing'))
