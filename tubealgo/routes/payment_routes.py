import razorpay
from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import User, SubscriptionPlan, Payment, get_config_value

payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/create-order', methods=['POST'])
@login_required
def create_order():
    plan_id_from_request = request.json.get('plan')
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id_from_request).first()

    if not plan:
        return jsonify({'error': 'Invalid plan selected.'}), 400

    amount = plan.price
    plan_name = plan.name
    
    client = razorpay.Client(auth=(get_config_value('RAZORPAY_KEY_ID'), get_config_value('RAZORPAY_KEY_SECRET')))
    
    order_data = {
        'amount': amount, 
        'currency': 'INR', 
        'receipt': f'receipt_user_{current_user.id}_{plan.plan_id}', 
        'notes': {
            'user_id': current_user.id, 
            'plan': plan.plan_id
        }
    }
    
    try:
        order = client.order.create(data=order_data)
        return jsonify({
            'order_id': order['id'], 
            'key_id': get_config_value('RAZORPAY_KEY_ID'), 
            'amount': order['amount'], 
            'currency': order['currency'], 
            'name': 'TubeAlgo', 
            'description': plan_name, 
            'prefill': {'email': current_user.email}
        })
    except Exception as e:
        print(f"Error creating Razorpay order: {e}")
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/verify-payment', methods=['POST'])
@login_required
def verify_payment():
    data = request.json
    try:
        client = razorpay.Client(auth=(get_config_value('RAZORPAY_KEY_ID'), get_config_value('RAZORPAY_KEY_SECRET')))
        client.utility.verify_payment_signature(data)
        
        order_details = client.order.fetch(data['razorpay_order_id'])
        plan = order_details['notes']['plan']
        
        # यूज़र का प्लान अपग्रेड करें
        current_user.subscription_plan = plan
        
        # नया पेमेंट रिकॉर्ड बनाएँ
        new_payment = Payment(
            user_id=current_user.id,
            razorpay_payment_id=data['razorpay_payment_id'],
            razorpay_order_id=data['razorpay_order_id'],
            amount=order_details['amount'],
            currency=order_details['currency'],
            plan_id=plan,
            status='captured'
        )
        db.session.add(new_payment)
        
        # रेफरल क्रेडिट्स अपडेट करें
        if current_user.referred_by:
            referrer = User.query.filter_by(referral_code=current_user.referred_by).first()
            if referrer:
                referrer.referral_credits = (referrer.referral_credits or 0) + 100
                current_user.referred_by = None 

        db.session.commit()
        flash('Payment successful! Your plan has been upgraded.', 'success')
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        print(f"Error verifying Razorpay payment: {e}")
        flash(f'Payment verification failed.', 'error')
        return jsonify({'status': 'error', 'message': str(e)}), 400