from . import db, celery # celery को इम्पोर्ट करें
from .models import User, Competitor, ChannelSnapshot, DashboardCache
from .services.youtube_fetcher import get_latest_videos, analyze_channel
from .services.notification_service import send_telegram_message
from .services.ai_service import get_ai_video_suggestions, generate_motivational_suggestion
from flask import current_app
from datetime import date, timedelta, datetime
import traceback
from .routes.api_routes import get_full_competitor_package

@celery.task
def take_daily_snapshots():
    """हर दिन सभी उपयोगकर्ताओं के चैनलों के आँकड़ों का स्नैपशॉट लेता है।"""
    print("Celery Task: Running job to take daily channel snapshots...")
    users_with_channels = User.query.join(User.channel).all()
    
    for user in users_with_channels:
        try:
            channel_data = analyze_channel(user.channel.channel_id_youtube)
            if 'error' in channel_data:
                print(f"Could not fetch data for user {user.email}: {channel_data['error']}")
                continue

            today_snapshot = ChannelSnapshot.query.filter_by(
                channel_db_id=user.channel.id, 
                date=date.today()
            ).first()

            if today_snapshot:
                today_snapshot.subscribers = channel_data.get('Subscribers', 0)
                today_snapshot.views = channel_data.get('Total Views', 0)
                today_snapshot.video_count = channel_data.get('Video Count', 0)
            else:
                new_snapshot = ChannelSnapshot(
                    channel_db_id=user.channel.id,
                    date=date.today(),
                    subscribers=channel_data.get('Subscribers', 0),
                    views=channel_data.get('Total Views', 0),
                    video_count=channel_data.get('Video Count', 0)
                )
                db.session.add(new_snapshot)
            
            db.session.commit()
            print(f"Successfully took snapshot for user: {user.email}")

        except Exception as e:
            db.session.rollback()
            print(f"Error taking snapshot for user {user.email}: {e}")
    
    print("Celery Task: Finished taking daily snapshots.")


@celery.task
def check_for_new_videos():
    print("Celery Task: Running job to check for new videos...")
    users_with_telegram = User.query.filter(User.telegram_chat_id.isnot(None), User.telegram_notify_new_video == True).all()

    for user in users_with_telegram:
        print(f"Checking competitors for user: {user.email}")
        competitors = user.competitors.all()
        
        for comp in competitors:
            try:
                latest_videos_data = get_latest_videos(comp.channel_id_youtube, max_results=1)
                if not latest_videos_data or not latest_videos_data.get('videos'):
                    continue

                latest_video = latest_videos_data['videos'][0]
                video_id = latest_video['id']
                video_title = latest_video['title']
                
                if not comp.last_known_video_id:
                    comp.last_known_video_id = video_id
                    db.session.commit()
                    continue

                if comp.last_known_video_id != video_id:
                    print(f"Found new video for {comp.channel_title}: {video_title}")
                    
                    comp.last_known_video_id = video_id
                    db.session.commit()

                    message = (
                        f"🚀 *New Video Alert!*\n\n"
                        f"Your competitor *{comp.channel_title}* just uploaded a new video!\n\n"
                        f"*Video Title:*\n \"{video_title}\"\n\n"
                        f"_[Watch on YouTube](https://www.youtube.com/watch?v={video_id})_"
                    )
                    
                    if user.telegram_notify_ai_suggestion:
                        ai_suggestion = generate_motivational_suggestion(video_title)
                        message += f"\n\n---\n💡 *Your Motivational AI Assistant:*\n\n{ai_suggestion}"

                    send_telegram_message(user.telegram_chat_id, message)
                    
            except Exception as e:
                print(f"Error checking competitor {comp.channel_title}: {e}")
                db.session.rollback()
    
    print("Celery Task: Finished checking for new videos.")


@celery.task
def update_all_dashboards():
    """
    सभी यूज़र्स के लिए डैशबोर्ड डेटा को बैकग्राउंड में रीफ्रेश और कैश करता है।
    """
    from .routes.utils import get_credentials
    print("Celery Task: Running job to update all user dashboards...")
    users_with_channels = User.query.join(User.channel).all()
    
    for user in users_with_channels:
        try:
            print(f"Updating dashboard for user: {user.email}")
            channel_id = user.channel.id
            
            channel_data = analyze_channel(user.channel.channel_id_youtube)
            if 'error' in channel_data: continue

            kpis = {'subscribers': channel_data.get('Subscribers', 0), 'views': channel_data.get('Total Views', 0), 'videos': channel_data.get('Video Count', 0)}
            
            today = date.today()
            start_date = today - timedelta(days=29)
            snapshots = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date >= start_date).order_by(ChannelSnapshot.date.asc()).all()
            labels = [(start_date + timedelta(days=i)).strftime('%d %b') for i in range(30)]
            sub_data, view_data, last_subs, last_views = [], [], 0, 0
            first_snapshot = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date < start_date).order_by(ChannelSnapshot.date.desc()).first()
            if first_snapshot:
                last_subs, last_views = first_snapshot.subscribers, first_snapshot.views
            elif snapshots:
                last_subs, last_views = snapshots[0].subscribers, snapshots[0].views
            snapshot_dict = {s.date: s for s in snapshots}
            for i in range(30):
                current_date = start_date + timedelta(days=i)
                if current_date in snapshot_dict:
                    last_subs, last_views = snapshot_dict[current_date].subscribers, snapshot_dict[current_date].views
                sub_data.append(last_subs)
                view_data.append(last_views)
            growth_chart_data = {'labels': labels, 'subscribers': sub_data, 'views': view_data}

            videos_data = get_latest_videos(user.channel.channel_id_youtube, max_results=50)
            all_user_videos = videos_data.get('videos', [])
            latest_video = all_user_videos[0] if all_user_videos else None
            if latest_video and len(all_user_videos) > 1:
                other_videos = all_user_videos[1:10]
                avg_views = sum(v['view_count'] for v in other_videos) / len(other_videos) if other_videos else 0
                performance = round(((latest_video['view_count'] - avg_views) / avg_views) * 100) if avg_views > 0 else 100
                latest_video['performance_vs_avg'] = performance
            elif latest_video:
                latest_video['performance_vs_avg'] = 100
            top_videos = sorted([v for v in all_user_videos if 'view_count' in v], key=lambda x: x['view_count'], reverse=True)[:3]
            
            ai_suggestions = get_ai_video_suggestions(user, user_videos=all_user_videos)

            final_data_package = {
                'kpis': kpis,
                'growth_chart': growth_chart_data,
                'latest_video': latest_video,
                'top_videos': top_videos,
                'ai_suggestions': ai_suggestions
            }

            cache_entry = DashboardCache.query.filter_by(user_id=user.id).first()
            if not cache_entry:
                cache_entry = DashboardCache(user_id=user.id)
                db.session.add(cache_entry)
            
            cache_entry.data = final_data_package
            cache_entry.updated_at = datetime.utcnow()
            db.session.commit()
            print(f"Successfully updated dashboard for user: {user.email}")

        except Exception as e:
            db.session.rollback()
            tb_str = traceback.format_exc()
            print(f"Error updating dashboard for user {user.email}: {e}\n{tb_str}")
    
    print("Celery Task: Finished updating all user dashboards.")

@celery.task
def perform_full_analysis(competitor_id):
    """
    एक प्रतियोगी के लिए बैकग्राउंड में पूरा डेटा पैकेज लाता है और कैश करता है।
    """
    print(f"Celery Task: Starting full analysis for competitor_id: {competitor_id}")
    try:
        # force_refresh=True यह सुनिश्चित करेगा कि हम हमेशा ताजा डेटा लाएं
        get_full_competitor_package(competitor_id, force_refresh=True)
        print(f"Celery Task: Successfully completed analysis for competitor_id: {competitor_id}")
    except Exception as e:
        print(f"Celery Task Error: Analysis failed for competitor_id: {competitor_id}. Error: {e}")