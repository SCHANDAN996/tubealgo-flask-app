# tubealgo/routes/payment_routes.py

[span_0](start_span)from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app[span_0](end_span)
[span_1](start_span)from flask_login import current_user, login_required[span_1](end_span)
[span_2](start_span)from tubealgo import db[span_2](end_span)
[span_3](start_span)from tubealgo.models import Payment, SubscriptionPlan, User[span_3](end_span)
[span_4](start_span)import requests[span_4](end_span)
[span_5](start_span)import json[span_5](end_span)
[span_6](start_span)from datetime import datetime, timedelta[span_6](end_span)
[span_7](start_span)import uuid[span_7](end_span)

[span_8](start_span)payment_bp = Blueprint('payment', __name__)[span_8](end_span)

[span_9](start_span)@payment_bp.route('/create_cashfree_order', methods=['POST'])[span_9](end_span)
[span_10](start_span)@login_required[span_10](end_span)
[span_11](start_span)def create_cashfree_order():[span_11](end_span)
    # 1. सबसे पहले जांचें कि यूजर का फोन नंबर मौजूद है या नहीं
    [span_12](start_span)if not current_user.phone_number:[span_12](end_span)
        [span_13](start_span)return jsonify({'error': 'Please add your phone number in the Settings page before making a payment.'}), 400[span_13](end_span)

    try:
        [span_14](start_span)data = request.get_json()[span_14](end_span)
        [span_15](start_span)plan_id = data.get('plan')[span_15](end_span)
        
        [span_16](start_span)plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()[span_16](end_span)
        [span_17](start_span)if not plan:[span_17](end_span)
            [span_18](start_span)return jsonify({'error': 'Invalid plan'}), 400[span_18](end_span)
        
        [span_19](start_span)cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')[span_19](end_span)
        [span_20](start_span)cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')[span_20](end_span)
        [span_21](start_span)cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')[span_21](end_span)
        
        [span_22](start_span)if not cashfree_app_id or not cashfree_secret_key:[span_22](end_span)
            [span_23](start_span)return jsonify({'error': 'Payment gateway not configured'}), 500[span_23](end_span)
        
        [span_24](start_span)base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"[span_24](end_span)
        
        [span_25](start_span)order_id = f"order_{current_user.id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"[span_25](end_span)
        
        order_data = {
            [span_26](start_span)"order_amount": plan.price / 100,[span_26](end_span)
            [span_27](start_span)"order_currency": "INR",[span_27](end_span)
            [span_28](start_span)"order_id": order_id,[span_28](end_span)
            [span_29](start_span)"customer_details": {[span_29](end_span)
                [span_30](start_span)"customer_id": str(current_user.id),[span_30](end_span)
                [span_31](start_span)"customer_email": current_user.email,[span_31](end_span)
                [span_32](start_span)"customer_phone": current_user.phone_number[span_32](end_span)
            },
            [span_33](start_span)"order_meta": {[span_33](end_span)
                [span_34](start_span)"return_url": url_for('payment.cashfree_verification', _external=True) + "?order_id={order_id}"[span_34](end_span)
            }
        }
        
        [span_35](start_span)headers = {[span_35](end_span)
            [span_36](start_span)'Content-Type': 'application/json',[span_36](end_span)
            [span_37](start_span)'x-client-id': cashfree_app_id,[span_37](end_span)
            [span_38](start_span)'x-client-secret': cashfree_secret_key,[span_38](end_span)
            [span_39](start_span)'x-api-version': '2022-09-01'[span_39](end_span)
        }
        
        [span_40](start_span)response = requests.post(f"{base_url}/orders", headers=headers, data=json.dumps(order_data))[span_40](end_span)
        
        [span_41](start_span)if response.status_code == 200:[span_41](end_span)
            [span_42](start_span)response_data = response.json()[span_42](end_span)
            
            [span_43](start_span)if response_data.get('payment_session_id'):[span_43](end_span)
                [span_44](start_span)payment = Payment([span_44](end_span)
                    [span_45](start_span)user_id=current_user.id,[span_45](end_span)
                    [span_46](start_span)razorpay_payment_id="",[span_46](end_span)
                    [span_47](start_span)razorpay_order_id=order_id,[span_47](end_span)
                    [span_48](start_span)amount=plan.price,[span_48](end_span)
                    [span_49](start_span)currency='INR',[span_49](end_span)
                    [span_50](start_span)plan_id=plan_id,[span_50](end_span)
                    [span_51](start_span)status='created'[span_51](end_span)
                )
                [span_52](start_span)db.session.add(payment)[span_52](end_span)
                [span_53](start_span)db.session.commit()[span_53](end_span)
                
                [span_54](start_span)return jsonify({[span_54](end_span)
                    [span_55](start_span)'order_id': order_id,[span_55](end_span)
                    [span_56](start_span)'payment_session_id': response_data['payment_session_id'][span_56](end_span)
                })
            [span_57](start_span)else:[span_57](end_span)
                [span_58](start_span)return jsonify({'error': 'Failed to create payment session'}), 500[span_58](end_span)
        else:
            [span_59](start_span)error_msg = response.json().get('message', 'Failed to create order')[span_59](end_span)
            [span_60](start_span)return jsonify({'error': error_msg}), response.status_code[span_60](end_span)
            
    except Exception as e:
        
        [span_61](start_span)current_app.logger.error(f"Cashfree order creation error: {str(e)}")[span_61](end_span)
        [span_62](start_span)return jsonify({'error': 'Payment processing failed'}), 500[span_62](end_span)

[span_63](start_span)@payment_bp.route('/cashfree_verification')[span_63](end_span)
[span_64](start_span)@login_required[span_64](end_span)
[span_65](start_span)def cashfree_verification():[span_65](end_span)
    try:
        [span_66](start_span)order_id = request.args.get('order_id')[span_66](end_span)
        
        [span_67](start_span)if not order_id:[span_67](end_span)
            [span_68](start_span)flash('Payment verification failed. Order ID not found.', 'error')[span_68](end_span)
            [span_69](start_span)return redirect(url_for('core.pricing'))[span_69](end_span)
        
        [span_70](start_span)payment = Payment.query.filter_by(razorpay_order_id=order_id, user_id=current_user.id).first()[span_70](end_span)
        
        [span_71](start_span)if not payment:[span_71](end_span)
            [span_72](start_span)flash('Payment record not found.', 'error')[span_72](end_span)
            [span_73](start_span)return redirect(url_for('core.pricing'))[span_73](end_span)
        
        [span_74](start_span)cashfree_app_id = current_app.config.get('CASHFREE_APP_ID')[span_74](end_span)
        [span_75](start_span)cashfree_secret_key = current_app.config.get('CASHFREE_SECRET_KEY')[span_75](end_span)
        [span_76](start_span)cashfree_env = current_app.config.get('CASHFREE_ENV', 'PROD')[span_76](end_span)
        [span_77](start_span)base_url = "https://api.cashfree.com/pg" if cashfree_env == 'PROD' else "https://sandbox.cashfree.com/pg"[span_77](end_span)

        [span_78](start_span)headers = {[span_78](end_span)
            [span_79](start_span)'x-client-id': cashfree_app_id,[span_79](end_span)
            [span_80](start_span)'x-client-secret': cashfree_secret_key,[span_80](end_span)
            [span_81](start_span)'x-api-version': '2022-09-01'[span_81](end_span)
        }
        
        [span_82](start_span)order_response = requests.get(f"{base_url}/orders/{order_id}", headers=headers)[span_82](end_span)
        
        [span_83](start_span)if order_response.status_code == 200:[span_83](end_span)
            [span_84](start_span)order_data = order_response.json()[span_84](end_span)
            [span_85](start_span)actual_payment_status = order_data.get('order_status', '').upper()[span_85](end_span)
            
            [span_86](start_span)if actual_payment_status in ['PAID', 'SUCCESS']:[span_86](end_span)
                [span_87](start_span)current_user.subscription_plan = payment.plan_id[span_87](end_span)
                [span_88](start_span)current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)[span_88](end_span)
                [span_89](start_span)payment.status = 'captured'[span_89](end_span)
                [span_90](start_span)payment.razorpay_payment_id = order_data.get('cf_order_id', '')[span_90](end_span)
                [span_91](start_span)db.session.commit()[span_91](end_span)
                [span_92](start_span)flash('Payment successful! Your subscription has been activated for 30 days.', 'success')[span_92](end_span)
                [span_93](start_span)return redirect(url_for('dashboard.dashboard'))[span_93](end_span)
            else:
                [span_94](start_span)payment.status = 'failed'[span_94](end_span)
                [span_95](start_span)db.session.commit()[span_95](end_span)
                [span_96](start_span)flash('Payment failed or is pending. Please try again.', 'error')[span_96](end_span)
                [span_97](start_span)return redirect(url_for('core.pricing'))[span_97](end_span)
        else:
            [span_98](start_span)flash('Could not verify payment status with the gateway.', 'error')[span_98](end_span)
            [span_99](start_span)return redirect(url_for('core.pricing'))[span_99](end_span)
            
    except Exception as e:
        [span_100](start_span)current_app.logger.error(f"Cashfree verification error: {str(e)}")[span_100](end_span)
        [span_101](start_span)flash('Payment verification failed due to an unexpected error.', 'error')[span_101](end_span)
        [span_102](start_span)return redirect(url_for('core.pricing'))[span_102](end_span)

[span_103](start_span)@payment_bp.route('/cashfree_webhook', methods=['POST'])[span_103](end_span)
[span_104](start_span)def cashfree_webhook():[span_104](end_span)
    try:
        [span_105](start_span)webhook_data = request.get_json()[span_105](end_span)
        
        [span_106](start_span)order_id = webhook_data.get('data', {}).get('order', {}).get('order_id')[span_106](end_span)
        [span_107](start_span)payment_status = webhook_data.get('data', {}).get('order', {}).get('order_status', '').upper()[span_107](end_span)
        
        [span_108](start_span)if payment_status in ['PAID', 'SUCCESS']:[span_108](end_span)
            [span_109](start_span)payment = Payment.query.filter_by(razorpay_order_id=order_id).first()[span_109](end_span)
            [span_110](start_span)if payment and payment.status != 'captured':[span_110](end_span)
                [span_111](start_span)user = User.query.get(payment.user_id)[span_111](end_span)
                [span_112](start_span)if user:[span_112](end_span)
                    [span_113](start_span)user.subscription_plan = payment.plan_id[span_113](end_span)
                    [span_114](start_span)user.subscription_end_date = datetime.utcnow() + timedelta(days=30)[span_114](end_span)
                    [span_115](start_span)payment.status = 'captured'[span_115](end_span)
                    [span_116](start_span)db.session.commit()[span_116](end_span)
        
        [span_117](start_span)return jsonify({'status': 'success'}), 200[span_117](end_span)
        
    except Exception as e:
        [span_118](start_span)current_app.logger.error(f"Cashfree webhook error: {str(e)}")[span_118](end_span)
        [span_119](start_span)return jsonify({'status': 'error'}), 500[span_119](end_span)
