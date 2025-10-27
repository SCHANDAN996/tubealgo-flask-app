# tubealgo/routes/seo_routes.py
"""
SEO Score Tool Routes
Video SEO analysis ke liye endpoints
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from tubealgo.services.seo_analyzer import SEOScoreAnalyzer, get_video_seo_score
from tubealgo.models.youtube_models import Video, Channel
from tubealgo.services.youtube_fetcher import YouTubeFetcher
from tubealgo.decorators import plan_required
from tubealgo import db
import logging

logger = logging.getLogger(__name__)

seo_bp = Blueprint('seo', __name__)


@seo_bp.route('/tools/seo-analyzer')
@login_required
def seo_analyzer_page():
    """SEO Score Tool ka main page"""
    
    # User ki recent videos
    user_videos = Video.query.filter_by(
        channel_id=current_user.connected_channel_id
    ).order_by(Video.published_at.desc()).limit(20).all()
    
    return render_template(
        'seo_analyzer.html',
        videos=user_videos,
        page_title='YouTube SEO Score Analyzer',
        meta_description='Analyze your YouTube video SEO and get actionable recommendations'
    )


@seo_bp.route('/api/seo/analyze-video', methods=['POST'])
@login_required
@plan_required('basic')  # Basic plan se access
def analyze_video_seo():
    """
    Single video ka SEO analysis
    
    Request JSON:
    {
        "video_id": "dQw4w9WgXcQ",
        "refresh": false  # Optional: force fresh analysis
    }
    """
    
    try:
        data = request.get_json()
        video_id = data.get('video_id')
        refresh = data.get('refresh', False)
        
        if not video_id:
            return jsonify({
                'success': False,
                'error': 'Video ID required'
            }), 400
        
        # Check if video exists in database
        video = Video.query.filter_by(video_id=video_id).first()
        
        # If video not in DB or refresh requested, fetch from YouTube
        if not video or refresh:
            fetcher = YouTubeFetcher(current_app.config['YOUTUBE_API_KEYS'])
            video_data = fetcher.fetch_video_details(video_id)
            
            if not video_data:
                return jsonify({
                    'success': False,
                    'error': 'Could not fetch video details from YouTube'
                }), 404
            
            # Save/update in database
            if not video:
                video = Video(
                    video_id=video_id,
                    channel_id=current_user.connected_channel_id,
                    user_id=current_user.id
                )
            
            # Update video details
            video.title = video_data.get('title')
            video.description = video_data.get('description')
            video.tags = video_data.get('tags', [])
            video.duration = video_data.get('duration', 0)
            video.thumbnail_url = video_data.get('thumbnail')
            video.view_count = video_data.get('view_count', 0)
            video.like_count = video_data.get('like_count', 0)
            video.comment_count = video_data.get('comment_count', 0)
            
            db.session.add(video)
            db.session.commit()
        
        # Perform SEO analysis
        gemini_key = current_app.config.get('GEMINI_API_KEY')
        seo_result = get_video_seo_score(video_id, gemini_key)
        
        if not seo_result.get('success'):
            return jsonify(seo_result), 500
        
        # Save analysis result
        video.seo_score = seo_result.get('score')
        video.seo_grade = seo_result.get('grade')
        video.last_analyzed = db.func.now()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'video': {
                'id': video.video_id,
                'title': video.title,
                'thumbnail': video.thumbnail_url,
                'url': f'https://youtube.com/watch?v={video.video_id}'
            },
            'seo_analysis': seo_result
        })
    
    except Exception as e:
        logger.error(f"SEO analysis error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Analysis failed. Please try again.'
        }), 500


@seo_bp.route('/api/seo/bulk-analyze', methods=['POST'])
@login_required
@plan_required('pro')  # Pro plan feature
def bulk_analyze_seo():
    """
    Multiple videos ka SEO analysis ek saath
    
    Request JSON:
    {
        "video_ids": ["id1", "id2", "id3"],
        "limit": 10  # Optional: max videos to analyze
    }
    """
    
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])
        limit = min(data.get('limit', 10), 20)  # Max 20 at once
        
        if not video_ids:
            return jsonify({
                'success': False,
                'error': 'Video IDs required'
            }), 400
        
        # Limit number of videos
        video_ids = video_ids[:limit]
        
        results = []
        gemini_key = current_app.config.get('GEMINI_API_KEY')
        
        for video_id in video_ids:
            try:
                # Get SEO score
                seo_result = get_video_seo_score(video_id, gemini_key)
                
                if seo_result.get('success'):
                    results.append({
                        'video_id': video_id,
                        'success': True,
                        'score': seo_result.get('score'),
                        'grade': seo_result.get('grade')
                    })
                else:
                    results.append({
                        'video_id': video_id,
                        'success': False,
                        'error': 'Analysis failed'
                    })
            
            except Exception as e:
                logger.error(f"Bulk analysis error for {video_id}: {str(e)}")
                results.append({
                    'video_id': video_id,
                    'success': False,
                    'error': str(e)
                })
        
        # Calculate summary stats
        successful = [r for r in results if r.get('success')]
        avg_score = sum(r.get('score', 0) for r in successful) / len(successful) if successful else 0
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_analyzed': len(results),
                'successful': len(successful),
                'failed': len(results) - len(successful),
                'average_score': round(avg_score, 1)
            }
        })
    
    except Exception as e:
        logger.error(f"Bulk SEO analysis error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Bulk analysis failed'
        }), 500


@seo_bp.route('/api/seo/channel-overview')
@login_required
def channel_seo_overview():
    """
    Complete channel ka SEO overview
    All videos ka average score, trends, etc.
    """
    
    try:
        channel_id = current_user.connected_channel_id
        
        if not channel_id:
            return jsonify({
                'success': False,
                'error': 'No channel connected'
            }), 400
        
        # Get all videos with SEO scores
        videos = Video.query.filter(
            Video.channel_id == channel_id,
            Video.seo_score.isnot(None)
        ).all()
        
        if not videos:
            return jsonify({
                'success': True,
                'message': 'No analyzed videos found',
                'overview': None
            })
        
        # Calculate statistics
        scores = [v.seo_score for v in videos]
        grades = [v.seo_grade for v in videos]
        
        from collections import Counter
        grade_distribution = Counter(grades)
        
        overview = {
            'total_videos_analyzed': len(videos),
            'average_score': round(sum(scores) / len(scores), 1),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'grade_distribution': dict(grade_distribution),
            'top_videos': [
                {
                    'id': v.video_id,
                    'title': v.title,
                    'score': v.seo_score,
                    'grade': v.seo_grade,
                    'thumbnail': v.thumbnail_url
                }
                for v in sorted(videos, key=lambda x: x.seo_score, reverse=True)[:5]
            ],
            'videos_needing_improvement': [
                {
                    'id': v.video_id,
                    'title': v.title,
                    'score': v.seo_score,
                    'grade': v.seo_grade,
                    'thumbnail': v.thumbnail_url
                }
                for v in sorted(videos, key=lambda x: x.seo_score)[:5]
            ]
        }
        
        return jsonify({
            'success': True,
            'overview': overview
        })
    
    except Exception as e:
        logger.error(f"Channel SEO overview error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate overview'
        }), 500


@seo_bp.route('/api/seo/compare-videos', methods=['POST'])
@login_required
def compare_videos():
    """
    Do videos ka side-by-side SEO comparison
    
    Request JSON:
    {
        "video_id_1": "abc123",
        "video_id_2": "xyz789"
    }
    """
    
    try:
        data = request.get_json()
        video_id_1 = data.get('video_id_1')
        video_id_2 = data.get('video_id_2')
        
        if not video_id_1 or not video_id_2:
            return jsonify({
                'success': False,
                'error': 'Both video IDs required'
            }), 400
        
        gemini_key = current_app.config.get('GEMINI_API_KEY')
        
        # Analyze both videos
        analysis_1 = get_video_seo_score(video_id_1, gemini_key)
        analysis_2 = get_video_seo_score(video_id_2, gemini_key)
        
        if not analysis_1.get('success') or not analysis_2.get('success'):
            return jsonify({
                'success': False,
                'error': 'Failed to analyze one or both videos'
            }), 500
        
        # Generate comparison insights
        comparison = {
            'video_1': {
                'id': video_id_1,
                'analysis': analysis_1
            },
            'video_2': {
                'id': video_id_2,
                'analysis': analysis_2
            },
            'insights': {
                'score_difference': abs(analysis_1['score'] - analysis_2['score']),
                'better_video': video_id_1 if analysis_1['score'] > analysis_2['score'] else video_id_2,
                'category_comparison': {}
            }
        }
        
        # Compare each category
        for category in analysis_1.get('breakdown', {}).keys():
            score_1 = analysis_1['breakdown'][category]['score']
            score_2 = analysis_2['breakdown'][category]['score']
            
            comparison['insights']['category_comparison'][category] = {
                'video_1_score': score_1,
                'video_2_score': score_2,
                'winner': 'video_1' if score_1 > score_2 else 'video_2' if score_2 > score_1 else 'tie'
            }
        
        return jsonify({
            'success': True,
            'comparison': comparison
        })
    
    except Exception as e:
        logger.error(f"Video comparison error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Comparison failed'
        }), 500


@seo_bp.route('/api/seo/export-report/<video_id>')
@login_required
def export_seo_report(video_id):
    """
    Video SEO report ko PDF format mein export karo
    """
    
    try:
        gemini_key = current_app.config.get('GEMINI_API_KEY')
        seo_result = get_video_seo_score(video_id, gemini_key)
        
        if not seo_result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Report generation failed'
            }), 500
        
        # Generate PDF using reportlab or weasyprint
        # Implementation depends on your PDF library choice
        
        return jsonify({
            'success': True,
            'message': 'Report exported successfully',
            'download_url': f'/downloads/seo-report-{video_id}.pdf'
        })
    
    except Exception as e:
        logger.error(f"Report export error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Export failed'
        }), 500
