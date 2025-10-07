# tubealgo/routes/goal_routes.py

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import Goal, User
from tubealgo.services.youtube_fetcher import analyze_channel
from datetime import datetime

goal_bp = Blueprint('goal', __name__, url_prefix='/api/goals')

@goal_bp.route('/', methods=['POST'])
@login_required
def set_goal():
    data = request.json
    goal_type = data.get('goal_type')
    target_value = data.get('target_value')
    target_date_str = data.get('target_date')

    if not all([goal_type, target_value]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        target_value = int(target_value)
        if target_value <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid target value'}), 400

    target_date = None
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # पुराने सक्रिय लक्ष्य को निष्क्रिय करें
    Goal.query.filter_by(user_id=current_user.id, goal_type=goal_type, is_active=True).update({'is_active': False})

    # वर्तमान मूल्य प्राप्त करें
    channel_data = analyze_channel(current_user.channel.channel_id_youtube)
    start_value = 0
    if 'error' not in channel_data:
        if goal_type == 'subscribers':
            start_value = channel_data.get('Subscribers', 0)
        elif goal_type == 'views':
            start_value = channel_data.get('Total Views', 0)
    
    new_goal = Goal(
        user_id=current_user.id,
        goal_type=goal_type,
        target_value=target_value,
        start_value=start_value,
        target_date=target_date,
        is_active=True
    )
    db.session.add(new_goal)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Goal set successfully!'}), 201