# tubealgo/routes/competitor_routes.py
"""
Competitor Analysis Routes
Updated to work without Redis/Celery (synchronous processing)
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from tubealgo import db
from tubealgo.models.youtube_models import Competitor
from tubealgo.services.channel_fetcher import fetch_channel_details
from tubealgo.services.cache_manager import CacheManager
from tubealgo.decorators import plan_required
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

competitor_bp = Blueprint('competitor', __name__, url_prefix='/competitors')
cache = CacheManager()


@competitor_bp.route('/')
@login_required
def competitors_page():
    """Competitor tracking dashboard"""
    
    # Get user's tracked competitors
    competitors = Competitor.query.filter_by(
        user_id=current_user.id
    ).order_by(Competitor.added_at.desc()).all()
    
    # Get plan limits
    plan_limit = 2  # Free plan default
    if current_user.plan:
        plan_limit = current_user.plan.features.get('competitor_tracking', 2)
    
    return render_template(
        'competitors.html',
        competitors=competitors,
        competitors_count=len(competitors),
        plan_limit=plan_limit,
        can_add_more=len(competitors) < plan_limit
    )


@competitor_bp.route('/add', methods=['POST'])
@login_required
@plan_required('free')
def add_competitor():
    """
    Add new competitor to track
    
    UPDATED: Works without Celery/Redis
    Uses synchronous processing
    
    Request JSON:
    {
        "channel_id": "UCxxxxx",
        "channel_url": "https://youtube.com/@channelname"  # Alternative
    }
    """
    
    try:
        data = request.get_json()
        
        # Get channel ID from request
        channel_id = data.get('channel_id')
        channel_url = data.get('channel_url')
        
        if not channel_id and not channel_url:
            return jsonify({
                'success': False,
                'error': 'Channel ID or URL is required'
            }), 400
        
        # Extract channel ID from URL if provided
        if channel_url and not channel_id:
            from tubealgo.services.youtube_core import extract_channel_id_from_url
            channel_id = extract_channel_id_from_url(channel_url)
            
            if not channel_id:
                return jsonify({
                    'success': False,
                    'error': 'Invalid YouTube channel URL'
                }), 400
        
        # Check plan limits
        current_count = Competitor.query.filter_by(user_id=current_user.id).count()
        plan_limit = 2  # Free plan default
        
        if current_user.plan:
            plan_limit = current_user.plan.features.get('competitor_tracking', 2)
        
        if current_count >= plan_limit:
            return jsonify({
                'success': False,
                'error': f'You have reached your plan limit of {plan_limit} competitors. Upgrade to track more.'
            }), 403
        
        # Check if already tracking this competitor
        existing = Competitor.query.filter_by(
            user_id=current_user.id,
            channel_id=channel_id
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'You are already tracking this competitor'
            }), 400
        
        # Try to get from cache first
        cache_key = f"channel_analysis_v6:{channel_id}"
        channel_data = cache.get(cache_key)
        
        if not channel_data:
            logger.info(f"Cache miss for channel: {channel_id}")
            
            # Fetch channel details synchronously (NO Celery)
            try:
                youtube_api_key = current_app.config['YOUTUBE_API_KEYS'][0]
                channel_data = fetch_channel_details(channel_id, youtube_api_key)
                
                if not channel_data:
                    return jsonify({
                        'success': False,
                        'error': 'Could not fetch channel details. Please check the channel ID.'
                    }), 404
                
                # Cache for 1 hour
                cache.set(cache_key, channel_data, ttl=3600)
                logger.info(f"Cached channel data for: {channel_id}")
                
            except Exception as e:
                logger.error(f"Error fetching channel: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to fetch channel details. Please try again.'
                }), 500
        else:
            logger.info(f"Cache hit for channel: {channel_id}")
        
        # Create competitor record
        competitor = Competitor(
            user_id=current_user.id,
            channel_id=channel_id,
            channel_title=channel_data.get('title', 'Unknown'),
            custom_name=channel_data.get('title'),  # User can rename later
            subscriber_count=channel_data.get('subscriber_count', 0),
            video_count=channel_data.get('video_count', 0),
            view_count=channel_data.get('view_count', 0),
            thumbnail_url=channel_data.get('thumbnail'),
            added_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        db.session.add(competitor)
        db.session.commit()
        
        logger.info(f"Competitor added successfully: {channel_id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Competitor added successfully!',
            'competitor': {
                'id': competitor.id,
                'channel_id': channel_id,
                'channel_title': competitor.channel_title,
                'subscriber_count': competitor.subscriber_count,
                'video_count': competitor.video_count,
                'thumbnail_url': competitor.thumbnail_url
            }
        })
        
    except Exception as e:
        logger.error(f"Error adding competitor: {str(e)}")
        db.session.rollback()
        
        return jsonify({
            'success': False,
            'error': 'An error occurred while adding competitor. Please try again.'
        }), 500


@competitor_bp.route('/remove/<int:competitor_id>', methods=['POST'])
@login_required
def remove_competitor(competitor_id):
    """Remove competitor from tracking"""
    
    try:
        competitor = Competitor.query.filter_by(
            id=competitor_id,
            user_id=current_user.id
        ).first()
        
        if not competitor:
            return jsonify({
                'success': False,
                'error': 'Competitor not found'
            }), 404
        
        db.session.delete(competitor)
        db.session.commit()
        
        logger.info(f"Competitor removed: {competitor_id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Competitor removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing competitor: {str(e)}")
        db.session.rollback()
        
        return jsonify({
            'success': False,
            'error': 'Failed to remove competitor'
        }), 500


@competitor_bp.route('/update/<int:competitor_id>', methods=['POST'])
@login_required
def update_competitor(competitor_id):
    """Update competitor data (refresh)"""
    
    try:
        competitor = Competitor.query.filter_by(
            id=competitor_id,
            user_id=current_user.id
        ).first()
        
        if not competitor:
            return jsonify({
                'success': False,
                'error': 'Competitor not found'
            }), 404
        
        # Fetch fresh data
        youtube_api_key = current_app.config['YOUTUBE_API_KEYS'][0]
        channel_data = fetch_channel_details(competitor.channel_id, youtube_api_key)
        
        if not channel_data:
            return jsonify({
                'success': False,
                'error': 'Could not fetch updated data'
            }), 500
        
        # Update competitor
        competitor.subscriber_count = channel_data.get('subscriber_count', 0)
        competitor.video_count = channel_data.get('video_count', 0)
        competitor.view_count = channel_data.get('view_count', 0)
        competitor.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        # Update cache
        cache_key = f"channel_analysis_v6:{competitor.channel_id}"
        cache.set(cache_key, channel_data, ttl=3600)
        
        return jsonify({
            'success': True,
            'message': 'Competitor data updated',
            'competitor': {
                'subscriber_count': competitor.subscriber_count,
                'video_count': competitor.video_count,
                'view_count': competitor.view_count
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating competitor: {str(e)}")
        db.session.rollback()
        
        return jsonify({
            'success': False,
            'error': 'Failed to update competitor'
        }), 500


@competitor_bp.route('/rename/<int:competitor_id>', methods=['POST'])
@login_required
def rename_competitor(competitor_id):
    """Rename competitor (custom name)"""
    
    try:
        data = request.get_json()
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return jsonify({
                'success': False,
                'error': 'Name is required'
            }), 400
        
        competitor = Competitor.query.filter_by(
            id=competitor_id,
            user_id=current_user.id
        ).first()
        
        if not competitor:
            return jsonify({
                'success': False,
                'error': 'Competitor not found'
            }), 404
        
        competitor.custom_name = new_name
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Competitor renamed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error renaming competitor: {str(e)}")
        db.session.rollback()
        
        return jsonify({
            'success': False,
            'error': 'Failed to rename competitor'
        }), 500


@competitor_bp.route('/compare', methods=['POST'])
@login_required
def compare_competitors():
    """
    Compare multiple competitors
    
    Request JSON:
    {
        "competitor_ids": [1, 2, 3]
    }
    """
    
    try:
        data = request.get_json()
        competitor_ids = data.get('competitor_ids', [])
        
        if not competitor_ids or len(competitor_ids) < 2:
            return jsonify({
                'success': False,
                'error': 'Please select at least 2 competitors to compare'
            }), 400
        
        competitors = Competitor.query.filter(
            Competitor.id.in_(competitor_ids),
            Competitor.user_id == current_user.id
        ).all()
        
        if len(competitors) < 2:
            return jsonify({
                'success': False,
                'error': 'Invalid competitor selection'
            }), 400
        
        # Prepare comparison data
        comparison = {
            'competitors': [],
            'metrics': {
                'subscribers': {},
                'videos': {},
                'views': {}
            }
        }
        
        for comp in competitors:
            comparison['competitors'].append({
                'id': comp.id,
                'name': comp.custom_name or comp.channel_title,
                'channel_id': comp.channel_id,
                'subscriber_count': comp.subscriber_count,
                'video_count': comp.video_count,
                'view_count': comp.view_count,
                'thumbnail_url': comp.thumbnail_url
            })
            
            comparison['metrics']['subscribers'][comp.id] = comp.subscriber_count
            comparison['metrics']['videos'][comp.id] = comp.video_count
            comparison['metrics']['views'][comp.id] = comp.view_count
        
        # Find leader in each category
        comparison['leaders'] = {
            'subscribers': max(comparison['competitors'], key=lambda x: x['subscriber_count']),
            'videos': max(comparison['competitors'], key=lambda x: x['video_count']),
            'views': max(comparison['competitors'], key=lambda x: x['view_count'])
        }
        
        return jsonify({
            'success': True,
            'comparison': comparison
        })
        
    except Exception as e:
        logger.error(f"Error comparing competitors: {str(e)}")
        
        return jsonify({
            'success': False,
            'error': 'Comparison failed'
        }), 500
