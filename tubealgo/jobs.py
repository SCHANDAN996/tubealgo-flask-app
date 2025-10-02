# Filepath: tubealgo/jobs.py

from . import db
from .models import User, Competitor
from .services.youtube_fetcher import get_latest_videos
from .services.notification_service import send_telegram_message
from .services.openai_service import generate_motivational_suggestion
from flask import current_app

def check_for_new_videos(app):
    with app.app_context():
        print("Scheduler: Running job to check for new videos...")
        users_with_telegram = User.query.filter(User.telegram_chat_id.isnot(None), User.telegram_notify_new_video == True).all()

        for user in users_with_telegram:
            print(f"Checking competitors for user: {user.email}")
            competitors = user.competitors.all()
            
            for comp in competitors:
                try:
                    # Fetch only the single latest video
                    latest_videos = get_latest_videos(comp.channel_id_youtube, max_results=1)
                    if not latest_videos:
                        continue

                    latest_video = latest_videos[0]
                    video_id = latest_video['id']
                    video_title = latest_video['title']
                    
                    # If there's no last known video, set it and continue
                    if not comp.last_known_video_id:
                        comp.last_known_video_id = video_id
                        db.session.commit()
                        continue

                    # If the latest video is different from the last known one, it's new
                    if comp.last_known_video_id != video_id:
                        print(f"Found new video for {comp.channel_title}: {video_title}")
                        
                        # Update the last known video ID
                        comp.last_known_video_id = video_id
                        db.session.commit()

                        # Prepare the base message
                        message = (
                            f"🚀 *New Video Alert!*\n\n"
                            f"आपके प्रतियोगी *{comp.channel_title}* ने अभी एक नया वीडियो अपलोड किया है!\n\n"
                            f"*वीडियो टाइटल:*\n \"{video_title}\"\n\n"
                            f"_[Watch on YouTube](https://www.youtube.com/watch?v={video_id})_"
                        )
                        
                        # If user wants AI suggestions, generate and append them
                        if user.telegram_notify_ai_suggestion:
                            ai_suggestion = generate_motivational_suggestion(video_title)
                            message += f"\n\n---\n💡 *आपका मोटिवेशनल AI असिस्टेंट:*\n\n{ai_suggestion}"

                        # Send the final message
                        send_telegram_message(user.telegram_chat_id, message)
                        
                except Exception as e:
                    print(f"Error checking competitor {comp.channel_title}: {e}")
                    db.session.rollback()
        
        print("Scheduler: Finished checking for new videos.")