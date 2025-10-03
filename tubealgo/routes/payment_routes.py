from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, SubscriptionPlan, Payment, get_config_value
import time

# Cashfree SDK को नए और सही तरीके से इम्पोर्ट करें
from cashfree_pg.api_client import APIClient
from cashfree_pg.api.orders import Orders
from cashfree_pg.exceptions import ApiException
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails
from cashfree_pg.models.order_meta import OrderMeta

payment_bp = Blueprint('payment', __name__)

def get_cashfree_client():
    """कैशफ्री API क्लाइंट को कॉन्फ़िगर करने के लिए हेल्पर फ़ंक्शन"""
    is_prod = get_config_value('CASHFREE_ENV') == 'PROD'
    host = "https://api.cashfree.com/pg" if is_prod else "https://sandbox.cashfree.com/pg"
    
    client = APIClient(
        client_id=get_config_value('CASHFREE_APP_ID'),
        client_secret=get_config_value('CASHFREE_SECRET_KEY'),
        environment=host
    )
    return client

@payment_bp.route('/create-cashfree-order', methods=['POST'])
@login_required
def create_cashfree_order():
    plan_id_from_request = request.json.get('plan')
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id_from_request).first()

    if not plan:
        return jsonify({'error': 'Invalid plan selected.'}), 400

    try:
        client = get_cashfree_client()
        order_api = Orders(client)
        
        # <<!>> जरूरी सुधार: यूज़र से फ़ोन नंबर लें। अभी के लिए डमी नंबर इस्तेमाल कर रहे हैं।
        # आपको इसे User मॉडल में जोड़ना चाहिए और रजिस्ट्रेशन या प्रोफाइल पेज पर पूछना चाहिए।
        customer_phone = getattr(current_user, 'phone_number', "9999999999") or "9999999999"

        order_request = CreateOrderRequest(
            order_id=f"tubealgo-order-{current_user.id}-{int(time.time())}",
            order_amount=float(plan.price / 100),
            order_currency="INR",
            customer_details=CustomerDetails(
                customer_id=str(current_user.id),
                customer_email=current_user.email,
                customer_phone=customer_phone
            ),
            order_meta=OrderMeta(
                # Redirect URL जब पेमेंट हो जाए
                return_url=url_for('payment.cashfree_verification', order_id='{order_id}', _external=True)
            ),
            order_tags={
                "plan": plan.plan_id
            }
        )
        
        # Cashfree API को कॉल करें
        api_response = order_api.create_order(x_api_version="2023-08-01", create_order_request=order_request)
        
        # ये दो चीज़ें frontend को भेजनी हैं
        return jsonify({
            'payment_session_id': api_response.payment_session_id,
            'order_id': api_response.order_id
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
        client = get_cashfree_client()
        order_api = Orders(client)
        
        # Cashfree से ऑर्डर की डिटेल्स वेरिफाई करें
        api_response = order_api.get_order(x_api_version="2023-08-01", order_id=order_id)

        if api_response.order_status == "PAID":
            plan_id = api_response.order_tags.get('plan', 'creator')
            
            # चेक करें कि यह पेमेंट पहले से प्रोसेस तो नहीं हुआ
            existing_payment = Payment.query.filter_by(gateway_order_id=order_id).first()
            if existing_payment:
                flash("This payment has already been processed.", "info")
                return redirect(url_for('dashboard.dashboard'))

            # यूज़र का प्लान अपग्रेड करें
            current_user.subscription_plan = plan_id
            
            # पेमेंट को डेटाबेस में सेव करें
            new_payment = Payment(
                user_id=current_user.id,
                gateway_name='cashfree', # गेटवे का नाम
                gateway_payment_id=api_response.cf_order_id,
                gateway_order_id=order_id,
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
        flash(f"Error verifying payment: {e.body}", "error")
        return redirect(url_for('core.pricing'))
