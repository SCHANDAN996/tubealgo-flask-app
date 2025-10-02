# Filepath: tubealgo/routes/competitor_routes.py

from flask import render_template, request, redirect, url_for, flash, Blueprint, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from tubealgo import db
from tubealgo.models import Competitor, SubscriptionPlan
from tubealgo.services.youtube_fetcher import (
    analyze_channel, get_youtube_categories, get_top_channels_by_category, 
    find_similar_channels
)
from tubealgo.services.notification_service import send_telegram_photo_with_caption
from tubealgo.routes.api_routes import get_full_competitor_package
# MODIFIED: Import helper functions from the new utils.py file
from tubealgo.routes.utils import get_video_info_dict 
import json

competitor_bp = Blueprint('competitor', __name__)

@competitor_bp.route('/competitors', methods=['GET'])
@login_required
def competitors():
    user_competitors_query = current_user.competitors.order_by(Competitor.position.asc()).all()
    competitors_list = [{"id": comp.id, "channel_id_youtube": comp.channel_id_youtube, "channel_title": comp.channel_title} for comp in user_competitors_query]
    form = FlaskForm() 
    plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first() or SubscriptionPlan.query.filter_by(plan_id='free').first()
    return render_template('competitors.html', 
                           competitors=user_competitors_query,
                           competitors_json=json.dumps(competitors_list),
                           form=form,
                           competitor_limit=plan.competitors_limit if plan else 0,
                           active_page='competitors')

@competitor_bp.route('/competitors/add', methods=['POST'])
@login_required
def add_competitor():
    plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first() or SubscriptionPlan.query.filter_by(plan_id='free').first()
    limit = plan.competitors_limit if plan else 0
    if limit != -1 and current_user.competitors.count() >= limit:
        flash(f"You have reached your limit of {limit} competitors. Please upgrade your plan.", "error")
        return redirect(url_for('core.pricing'))

    channel_id_from_selection = request.form.get('channel_id_hidden')
    channel_query_from_input = request.form.get('channel_url')
    
    search_input = channel_id_from_selection if channel_id_from_selection else channel_query_from_input
    
    if not search_input or not search_input.strip():
        flash('Please enter a channel name or URL.', 'error')
        return redirect(url_for('competitor.competitors'))
    
    analysis_data = analyze_channel(search_input)
    
    if 'error' in analysis_data:
        flash(analysis_data['error'], 'error')
    else:
        existing = Competitor.query.filter_by(user_id=current_user.id, channel_id_youtube=analysis_data['id']).first()
        if existing:
            flash(f"'{analysis_data['Title']}' is already in your list.", f"warning-{analysis_data['id']}")
        else:
            max_pos = db.session.query(db.func.max(Competitor.position)).filter_by(user_id=current_user.id).scalar() or 0
            new_competitor = Competitor(user_id=current_user.id, channel_id_youtube=analysis_data['id'], channel_title=analysis_data['Title'], thumbnail_url=analysis_data.get('Thumbnail URL', ''), position=max_pos + 1)
            
            db.session.add(new_competitor)
            db.session.commit()
            
            print(f"DEBUG: Starting to pre-cache full data for new competitor ID: {new_competitor.id}")
            get_full_competitor_package(new_competitor.id, force_refresh=True)
            print(f"DEBUG: Finished pre-caching for new competitor ID: {new_competitor.id}")
            
            flash(f"'{analysis_data['Title']}' has been added and fully analyzed!", 'success')
            
    return redirect(url_for('competitor.competitors'))

@competitor_bp.route('/competitors/delete/<int:competitor_id>', methods=['POST'])
@login_required
def delete_competitor(competitor_id):
    comp = Competitor.query.get_or_404(competitor_id)
    if comp.user_id != current_user.id:
        return redirect(url_for('competitor.competitors'))
    
    from tubealgo.models import ApiCache
    cache_key = f"competitor_package_v3:{competitor_id}"
    ApiCache.query.filter_by(cache_key=cache_key).delete()
    
    deleted_position = comp.position
    db.session.delete(comp)
    
    Competitor.query.filter(Competitor.user_id == current_user.id, Competitor.position > deleted_position).update({Competitor.position: Competitor.position - 1})
    db.session.commit()
    flash(f"'{comp.channel_title}' has been removed.", 'success')
    return redirect(url_for('competitor.competitors'))

@competitor_bp.route('/competitors/move/<int:competitor_id>/<direction>', methods=['POST'])
@login_required
def move_competitor(competitor_id, direction):
    comp_to_move = Competitor.query.get_or_404(competitor_id)
    if comp_to_move.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    current_pos = comp_to_move.position
    
    if direction == 'up':
        swap_pos = current_pos - 1
    elif direction == 'down':
        swap_pos = current_pos + 1
    else:
        return jsonify({'success': False, 'error': 'Invalid direction'}), 400

    comp_to_swap = Competitor.query.filter_by(user_id=current_user.id, position=swap_pos).first()

    if comp_to_swap:
        comp_to_move.position, comp_to_swap.position = comp_to_swap.position, comp_to_move.position
        db.session.commit()
        return jsonify({'success': True, 'message': 'Position updated.'})
    
    return jsonify({'success': False, 'error': 'Move out of bounds'}), 400

@competitor_bp.route('/discover', methods=['GET', 'POST'])
@login_required
def discover():
    categories = get_youtube_categories()
    top_channels, similar_channels = [], []
    selected_category_id, searched_channel_name = None, ""
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'category_search':
            selected_category_id = request.form.get('category_id')
            if selected_category_id:
                top_channels = get_top_channels_by_category(selected_category_id)
                if not top_channels: flash('No popular channels found for this category.', 'info')
        elif form_type == 'similar_search':
            searched_channel_name = request.form.get('channel_url')
            if searched_channel_name:
                source_data = analyze_channel(searched_channel_name)
                if 'error' in source_data:
                    flash(source_data['error'], 'error')
                else:
                    similar_channels = find_similar_channels(source_data['id'])
                    if not similar_channels: flash(f"Could not find channels similar to '{source_data['Title']}'.", 'info')
    return render_template('discover.html', categories=categories, top_channels=top_channels, similar_channels=similar_channels, selected_category_id=selected_category_id, searched_channel_name=searched_channel_name, active_page='discover')

@competitor_bp.route('/video/<video_id>/send/telegram')
@login_required
def send_video_to_telegram(video_id):
    if not current_user.telegram_chat_id:
        flash('Please set your Telegram Chat ID in settings first.', 'error')
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
    
    video_info = get_video_info_dict(video_id)
    if 'error' in video_info:
        flash(video_info['error'], 'error')
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
    
    caption = (
        f"📊 *Video Analysis for:* {video_info['title']}\n\n"
        f"👀 Views: *{video_info['views']:,}*\n"
        f"👍 Likes: *{video_info['likes']:,}*\n"
        f"💬 Comments: *{video_info['comments']:,}*\n"
        f"📈 Views/Day: *{video_info['views_per_day']:,}*\n\n"
        f" Sentiment: ✅{video_info['sentiment'].get('positive', 0)}% | ❌{video_info['sentiment'].get('negative', 0)}% \n\n"
        f"[Watch on YouTube](https://youtu.be/{video_info['id']})"
    )
    send_telegram_photo_with_caption(current_user.telegram_chat_id, video_info['thumbnail_url'], caption)
    flash('Analysis has been sent to your Telegram!', 'success')
    return redirect(url_for('analysis.video_analysis', video_id=video_id))