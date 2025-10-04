# tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from tubealgo import db
from tubealgo.models import Payment, SubscriptionPlan, User
import cashfree_pg
from cashfree_pg import Cashfree, Environment
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
        
        # Initialize Cashfree
        cashfree = Cashfree()
        cashfree.set_environment(Environment.PRODUCTION if current_app.config.get('CASHFREE_ENV') == 'PROD' else Environment.SANDBOX)
        cashfree.set_client_id(current_app.config.get('CASHFREE_APP_ID'))
        cashfree.set_client_secret(current_app.config.get('CASHFREE_SECRET_KEY'))
        
        # Create unique order ID
        order_id = f"order_{current_user.id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
        
        # Create order request
        order_request = cashfree_pg.CreateOrderRequest(
            order_amount=plan.price / 100,  # Convert paise to rupees
            order_currency="INR",
            order_id=order_id,
            customer_details=cashfree_pg.CustomerDetails(
                customer_id=str(current_user.id),
                customer_email=current_user.email,
                customer_phone="9999999999"  # You can collect this from user
            ),
            order_meta=cashfree_pg.OrderMeta(
                return_url=url_for('payment.cashfree_verification', _external=True)
            )
        )
        
        # Create order
        order_response = cashfree.PGCreateOrder(order_request)
        
        if order_response and hasattr(order_response, 'payment_session_id'):
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
                'payment_session_id': order_response.payment_session_id
            })
        else:
            return jsonify({'error': 'Failed to create order'}), 500
            
    except Exception as e:
        current_app.logger.error(f"Cashfree order creation error: {str(e)}")
        return jsonify({'error': 'Payment processing failed'}), 500

@payment_bp.route('/cashfree_verification')
@login_required
def cashfree_verification():
    try:
        order_id = request.args.get('order_id')
        payment_status = request.args.get('payment_status')
        
        if not order_id:
            flash('Payment verification failed', 'error')
            return redirect(url_for('core.pricing'))
        
        # Find payment record
        payment = Payment.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()
        
        if not payment:
            flash('Payment record not found', 'error')
            return redirect(url_for('core.pricing'))
        
        if payment_status == 'SUCCESS':
            # Update user subscription
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
        
        # Verify webhook signature (important for security)
        # Implement signature verification as per Cashfree docs
        
        order_id = webhook_data.get('orderId')
        payment_status = webhook_data.get('paymentStatus')
        
        if payment_status == 'SUCCESS':
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
