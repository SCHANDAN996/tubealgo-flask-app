# tubealgo/routes/planner_routes.py

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import ContentIdea

planner_bp = Blueprint('planner', __name__)

@planner_bp.route('/planner')
@login_required
def planner():
    return render_template('planner.html')

@planner_bp.route('/api/planner/ideas', methods=['GET'])
@login_required
def get_ideas():
    ideas = ContentIdea.query.filter_by(user_id=current_user.id).order_by(ContentIdea.position).all()
    
    ideas_by_status = {
        'idea': [],
        'scripting': [],
        'filming': [],
        'editing': [],
        'scheduled': []
    }
    for idea in ideas:
        if idea.status in ideas_by_status:
            ideas_by_status[idea.status].append({
                'id': idea.id,
                'title': idea.title
            })
            
    return jsonify(ideas_by_status)

@planner_bp.route('/api/planner/ideas', methods=['POST'])
@login_required
def create_idea():
    data = request.json
    title = data.get('title')
    status = data.get('status', 'idea')
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    max_position = db.session.query(db.func.max(ContentIdea.position)).filter_by(user_id=current_user.id, status=status).scalar() or -1
    
    new_idea = ContentIdea(
        user_id=current_user.id,
        title=title,
        status=status,
        position=max_position + 1
    )
    db.session.add(new_idea)
    db.session.commit()
    
    return jsonify({'id': new_idea.id, 'title': new_idea.title, 'status': new_idea.status}), 201

@planner_bp.route('/api/planner/ideas/<int:idea_id>', methods=['PUT'])
@login_required
def update_idea(idea_id):
    idea = ContentIdea.query.get(idea_id)
    if not idea or idea.user_id != current_user.id:
        return jsonify({'error': 'Idea not found or unauthorized'}), 404

    data = request.json
    if 'title' in data:
        idea.title = data['title']
    if 'status' in data:
        idea.status = data['status']
        # नए कॉलम में अंत में रखने के लिए पोजीशन अपडेट करें
        max_position = db.session.query(db.func.max(ContentIdea.position)).filter_by(user_id=current_user.id, status=data['status']).scalar() or -1
        idea.position = max_position + 1

    db.session.commit()
    return jsonify({'id': idea.id, 'title': idea.title, 'status': idea.status})

@planner_bp.route('/api/planner/ideas/move', methods=['POST'])
@login_required
def move_idea():
    data = request.json
    for status, idea_ids in data.items():
        if not isinstance(idea_ids, list):
            continue
        for index, idea_id in enumerate(idea_ids):
            try:
                idea = ContentIdea.query.get(int(idea_id))
                if idea and idea.user_id == current_user.id:
                    idea.status = status
                    idea.position = index
            except (ValueError, TypeError):
                continue # अमान्य idea_id को छोड़ दें
                
    db.session.commit()
    return jsonify({'success': True, 'message': 'Planner updated successfully.'})

@planner_bp.route('/api/planner/ideas/<int:idea_id>', methods=['DELETE'])
@login_required
def delete_idea(idea_id):
    idea = ContentIdea.query.get(idea_id)
    if not idea or idea.user_id != current_user.id:
        return jsonify({'error': 'Idea not found or unauthorized'}), 404
        
    db.session.delete(idea)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Idea deleted.'})