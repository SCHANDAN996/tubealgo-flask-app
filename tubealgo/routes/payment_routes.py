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

@payment_bp.route('/create_cashfree_order', methods=['POST'])
@login_required
def create_cashfree_order():
    # --- डीबगिंग लॉग्स यहाँ से शुरू ---
    print("\n--- [LOG] Payment process started: Inside create_cashfree_order ---")
    try:
        data = request.get_json()
        print(f"[LOG] 1. Data received from frontend: {data}")

        plan_id = data.get('plan')
        phone_number = data.get('phone_number')

        if not phone_number or not phone_number.isdigit() or len(phone_number) < 10:
            print("[ERROR LOG] 2. Phone number validation failed.")
            return jsonify({'error': 'A valid 10-digit phone number is required.'}), 400

        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            print(f"[ERROR LOG] 2. Plan '{plan_id}' not found in database.")
            return jsonify({'error': 'Invalid plan'}), 400
        
        print(f"[LOG] 2. Plan and phone number are valid. Plan: {plan.name}, Price: {plan.price / 100} INR")

        cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')
        cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')
        cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')
        
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
        print(f"[LOG] 3. Payload created to send to Cashfree: {order_data}")
        
        headers = {
            'Content-Type': 'application/json',
            'x-client-id': cashfree_app_id,
            'x-client-secret': cashfree_secret_key,
            'x-api-version': '2022-09-01'
        }
        
        # सुरक्षा के लिए, लॉग में सीक्रेट की को मास्क करें
        masked_headers = headers.copy()
        if cashfree_secret_key and len(cashfree_secret_key) > 8:
            masked_headers['x-client-secret'] = f"{cashfree_secret_key[:15]}...[MASKED]"
        print(f"[LOG] 4. Sending request to Cashfree API with headers: {masked_headers}")

        response = requests.post(f"{base_url}/orders", headers=headers, data=json.dumps(order_data))
        
        # --- सबसे महत्वपूर्ण लॉग ---
        print(f"\n[CRITICAL LOG] 5. Response received from Cashfree:")
        print(f"   - Status Code: {response.status_code}")
        print(f"   - Response Body: {response.text}\n")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('payment_session_id'):
                print("[LOG] 6. Success! payment_session_id received from Cashfree.")
                # ... (बाकी का डेटाबेस में सेव करने का कोड वैसा ही रहेगा) ...
                if not current_user.phone_number:
                    current_user.phone_number = phone_number
                
                payment = Payment(user_id=current_user.id, razorpay_order_id=order_id, amount=plan.price, plan_id=plan_id, status='created')
                db.session.add(payment)
                db.session.commit()
                
                return jsonify({
                    'order_id': order_id,
                    'payment_session_id': response_data['payment_session_id']
                })
            else:
                print("[ERROR LOG] 6. Status was 200 OK, but payment_session_id was NOT in the response.")
                return jsonify({'error': 'Failed to create payment session'}), 500
        else:
            print("[ERROR LOG] 6. Request to Cashfree failed with a non-200 status code.")
            error_msg = response.json().get('message', 'Failed to create order')
            return jsonify({'error': error_msg}), response.status_code
            
    except Exception as e:
        print(f"[FATAL ERROR LOG] An unexpected error occurred in the try block: {str(e)}")
        return jsonify({'error': 'An internal server error occurred'}), 500
