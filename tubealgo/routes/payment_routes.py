# Filepath: tubealgo/routes/payment_routes.py

from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, SubscriptionPlan, Payment, get_config_value
import time

# --- Correct Imports for Cashfree ---
from cashfree_pg import ApiClient, Configuration
from cashfree_pg.api.orders_api import OrdersApi
from cashfree_pg.exceptions import ApiException
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails
from cashfree_pg.models.order_meta import OrderMeta

payment_bp = Blueprint('payment', __name__)

def get_cashfree_api_instance():
    """Configures and returns a Cashfree API client instance."""
    is_prod = get_config_value('CASHFREE_ENV') == 'PROD'
    host = "https://api.cashfree.com/pg" if is_prod else "https://sandbox.cashfree.com/pg"
    
    # Check if keys are present
    client_id = get_config_value('CASHFREE_APP_ID')
    client_secret = get_config_value('CASHFREE_SECRET_KEY')
    if not client_id or not client_secret:
        print("ERROR: CASHFREE_APP_ID or CASHFREE_SECRET_KEY not set.")
        return None

    config = Configuration(
        host = host,
        api_key = {
            'XClientID': client_id,
            'XClientSecret': client_secret
        }
    )
    api_client = ApiClient(config)
    return api_client

@payment_bp.route('/create-cashfree-order', methods=['POST'])
@login_required
def create_cashfree_order():
    plan_id_from_request = request.json.get('plan')
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id_from_request).first()

    if not plan:
        return jsonify({'error': 'Invalid plan selected.'}), 400

    try:
        api_client = get_cashfree_api_instance()
        if not api_client:
            return jsonify({'error': 'Payment gateway is not configured correctly.'}), 500

        order_api_instance = OrdersApi(api_client)
        
        order_request = CreateOrderRequest(
            order_id=f"tubealgo-order-{int(time.time())}",
            order_amount=float(plan.price / 100),
            order_currency="INR",
            customer_details=CustomerDetails(
                customer_id=str(current_user.id),
                customer_email=current_user.email,
                customer_phone="9999999999"  # This is a required field
            ),
            order_meta=OrderMeta(
                return_url=url_for('payment.cashfree_verification', _external=True) + "?order_id={order_id}"
            ),
            order_tags={
                "plan": plan.plan_id
            }
        )
        
        api_response = order_api_instance.create_order(x_api_version="2023-08-01", create_order_request=order_request)
        
        return jsonify({
            'payment_session_id': api_response.data.payment_session_id,
            'order_id': api_response.data.order_id
        })

    except ApiException as e:
        print(f"Cashfree API Error: {e.body}")
        return jsonify({'error': 'Could not create payment order.'}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({'error': 'An unexpected server error occurred.'}), 500

@payment_bp.route('/cashfree-verification')
@login_required
def cashfree_verification():
    order_id = request.args.get('order_id')
    if not order_id:
        flash("Payment verification failed. Order ID not found.", "error")
        return redirect(url_for('core.pricing'))

    try:
        api_client = get_cashfree_api_instance()
        if not api_client:
            flash("Payment gateway is not configured correctly.", "error")
            return redirect(url_for('core.pricing'))
            
        order_api_instance = OrdersApi(api_client)
        
        api_response = order_api_instance.get_order(x_api_version="2023-08-01", order_id=order_id)
        order_data = api_response.data

        if order_data.order_status == "PAID":
            plan_id = order_data.order_tags.get('plan', 'creator') if order_data.order_tags else 'creator'
            
            existing_payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            if existing_payment:
                flash("This payment has already been processed.", "info")
                return redirect(url_for('dashboard.dashboard'))

            current_user.subscription_plan = plan_id
            
            new_payment = Payment(
                user_id=current_user.id,
                razorpay_payment_id=order_data.cf_order_id,
                razorpay_order_id=order_id,
                amount=int(order_data.order_amount * 100),
                currency=order_data.order_currency,
                plan_id=plan_id,
                status='captured'
            )
            db.session.add(new_payment)
            db.session.commit()
            
            flash('Payment successful! Your plan has been upgraded.', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash(f"Payment was not successful. Status: {order_data.order_status}", "error")
            return redirect(url_for('core.pricing'))

    except ApiException as e:
        flash(f"Error verifying payment: {e.body}", "error")
        return redirect(url_for('core.pricing'))
