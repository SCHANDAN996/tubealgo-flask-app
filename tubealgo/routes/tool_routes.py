# tubealgo/routes/tool_routes.py

from flask import render_template, request, flash, Blueprint, jsonify, redirect, url_for
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models import SearchHistory
from tubealgo.services.suggestion_service import get_keyword_suggestions
from tubealgo.services.ai_service import generate_titles_and_tags, generate_description
from tubealgo.decorators import check_limits, RateLimitExceeded
import re

tool_bp = Blueprint('tool', __name__)

# ... (extract_video_id और video_analyzer फंक्शन में कोई बदलाव नहीं) ...
def extract_video_id(url):
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([a-zA-Z0-9_-]{11})',
        r'^[a-zA-Z0-9_-]{11}$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@tool_bp.route('/video-analyzer', methods=['GET', 'POST'])
@login_required
def video_analyzer():
    if request.method == 'POST':
        video_url = request.form.get('video_url')
        if not video_url:
            flash('Please enter a YouTube video URL or ID.', 'error')
            return redirect(url_for('tool.video_analyzer'))
            
        video_id = extract_video_id(video_url)
        
        if not video_id:
            flash('Invalid YouTube URL or Video ID provided.', 'error')
            return redirect(url_for('tool.video_analyzer'))
            
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
        
    return render_template('video_analyzer_tool.html', active_page='video_analyzer')

@tool_bp.route('/keyword-research', methods=['GET', 'POST'])
@login_required
def keyword_research():
    if request.method == 'POST':
        try:
            @check_limits(feature='keyword_search')
            def do_search():
                keyword_in = request.form.get('keyword', '')
                sugg = None
                if keyword_in:
                    sugg = get_keyword_suggestions(keyword_in)
                    if isinstance(sugg, dict) and 'error' in sugg:
                        flash(sugg['error'], 'error')
                        sugg = None
                return render_template('keyword_tool.html', keyword=keyword_in, suggestions=sugg, active_page='keyword_research')
            return do_search()
        except RateLimitExceeded as e:
            flash(str(e), 'error')
            return redirect(url_for('core.pricing'))
    
    return render_template('keyword_tool.html', keyword="", suggestions=None, active_page='keyword_research')

@tool_bp.route('/api/keyword-suggestions')
@login_required
def api_keyword_suggestions():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    return jsonify(get_keyword_suggestions(query))

# ===== यह फंक्शन अपडेट किया गया है =====
@tool_bp.route('/ai-generator', methods=['GET', 'POST'])
@login_required
def ai_generator():
    if request.method == 'POST':
        try:
            @check_limits(feature='ai_generation')
            def do_generation():
                # अब यह JSON डेटा हैंडल करेगा
                if not request.is_json:
                    return jsonify({'error': 'Invalid request format. Must be JSON.'}), 400
                
                data = request.get_json()
                topic_in = data.get('topic', '')

                if not topic_in:
                    return jsonify({'error': 'Topic is required.'}), 400

                # Search History को सेव करें
                new_search = SearchHistory(user_id=current_user.id, topic=topic_in)
                db.session.add(new_search)
                history_count = current_user.search_history.count()
                if history_count > 10: # लिमिट थोड़ी बढ़ा दी गई है
                    oldest_entry = current_user.search_history.order_by(SearchHistory.timestamp.asc()).first()
                    db.session.delete(oldest_entry)
                db.session.commit()
                
                # AI से रिजल्ट्स जेनरेट करें
                results = generate_titles_and_tags(current_user, topic_in)
                if isinstance(results, dict) and 'error' in results:
                    return jsonify({'error': results['error']}), 500
                
                return jsonify(results)
            return do_generation()
        except RateLimitExceeded as e:
            return jsonify({'error': str(e), 'details': str(e)}), 429

    # GET रिक्वेस्ट के लिए पेज रेंडर करें
    return render_template('ai_generator.html', topic="", results=None, active_page='ai_generator')

@tool_bp.route('/api/generate-description', methods=['POST'])
@login_required
def api_generate_description():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            title = data.get('title')
            language = data.get('language', 'English')
            
            if not topic or not title:
                return jsonify({'error': 'Topic and title are required.'}), 400
                
            result = generate_description(current_user, topic, title, language)
            return jsonify(result)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429