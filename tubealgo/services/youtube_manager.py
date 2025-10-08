import os
import logging
import re
from datetime import timedelta, datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from ..services.youtube_fetcher import get_latest_videos as get_videos_by_channel_id

def _parse_duration(duration_str):
    if not duration_str: return 0
    duration_regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = duration_regex.match(duration_str)
    if not parts: return 0
    parts = parts.groups()
    time_params = {name: int(value) for name, value in zip(["hours", "minutes", "seconds"], parts) if value}
    return timedelta(**time_params).total_seconds()

def get_user_videos(credentials):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        
        search_request = youtube.search().list(
            part="id", 
            forMine=True, 
            maxResults=25, 
            type="video", 
            order="date"
        )
        search_response = search_request.execute()
        
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        if not video_ids:
            return []

        details_request = youtube.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(video_ids)
        )
        details_response = details_request.execute()

        videos = []
        for item in details_response.get('items', []):
            duration_seconds = _parse_duration(item.get('contentDetails', {}).get('duration'))
            videos.append({
                'id': item.get('id'),
                'title': item.get('snippet', {}).get('title'),
                'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                'published_at': item.get('snippet', {}).get('publishedAt'),
                'view_count': int(item.get('statistics', {}).get('viewCount', 0)),
                'like_count': int(item.get('statistics', {}).get('likeCount', 0)),
                'comment_count': int(item.get('statistics', {}).get('commentCount', 0)),
                'is_short': 0 < duration_seconds <= 61,
                'privacy_status': item.get('status', {}).get('privacyStatus')
            })
        
        return videos

    except Exception as e:
        logging.error(f"Could not fetch user videos: {e}")
        return {'error': str(e)}

def get_user_playlists(credentials):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        playlists_request = youtube.playlists().list(
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=50
        )
        playlists_response = playlists_request.execute()

        playlists = []
        for item in playlists_response.get('items', []):
            playlists.append({
                'id': item.get('id'),
                'title': item.get('snippet', {}).get('title'),
                'description': item.get('snippet', {}).get('description'),
                'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                'published_at': item.get('snippet', {}).get('publishedAt'),
                'video_count': item.get('contentDetails', {}).get('itemCount', 0),
                'privacy_status': item.get('status', {}).get('privacyStatus')
            })
        return playlists
    except Exception as e:
        logging.error(f"Could not fetch user playlists: {e}")
        return {'error': str(e)}

def get_competitors_playlists(user):
    from ..models import Competitor
    competitors = user.competitors.all()
    if not competitors:
        return []

    all_video_titles = []
    for comp in competitors:
        try:
            video_data = get_videos_by_channel_id(comp.channel_id_youtube, max_results=10)
            
            if 'error' in video_data:
                logging.error(f"Could not fetch videos for competitor {comp.channel_title}: {video_data['error']}")
                return {'error': f"Could not fetch videos for competitor {comp.channel_title}. YouTube API quota may be exceeded."}

            videos = video_data.get('videos', [])
            for video in videos:
                if 'title' in video:
                    all_video_titles.append(video['title'])
        except Exception as e:
            logging.error(f"An unexpected error occurred while fetching data for competitor {comp.channel_id_youtube}: {e}")
            continue
    
    return list(set(all_video_titles))

def get_single_video(credentials, video_id):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        request = youtube.videos().list(part="snippet,status,contentDetails", id=video_id)
        response = request.execute()
        if not response.get('items'):
            return {'error': 'Video not found or you do not have permission to view it.'}
        return response['items'][0]
    except Exception as e:
        logging.error(f"Could not fetch single video {video_id}: {e}")
        return {'error': str(e)}

def get_single_playlist(credentials, playlist_id):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        request = youtube.playlists().list(
            part="snippet,status",
            id=playlist_id
        )
        response = request.execute()
        if not response.get('items'):
            return {'error': 'Playlist not found or you do not have permission to view it.'}
        return response['items'][0]
    except Exception as e:
        logging.error(f"Could not fetch single playlist {playlist_id}: {e}")
        return {'error': str(e)}

def create_playlist(credentials, title, description, privacy_status):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            "snippet": { "title": title, "description": description },
            "status": { "privacyStatus": privacy_status }
        }
        request = youtube.playlists().insert(part="snippet,status", body=body)
        response = request.execute()
        return response
    except Exception as e:
        logging.error(f"Could not create playlist: {e}")
        return {'error': str(e)}

def update_playlist(credentials, playlist_id, title, description, privacy_status):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        
        playlist_response = youtube.playlists().list(part='snippet,status', id=playlist_id).execute()
        if not playlist_response.get('items'):
            return {'error': 'Playlist not found.'}
        
        playlist = playlist_response['items'][0]
        
        playlist['snippet']['title'] = title
        playlist['snippet']['description'] = description
        playlist['status']['privacyStatus'] = privacy_status

        request = youtube.playlists().update(part="snippet,status", body=playlist)
        response = request.execute()
        return response
    except Exception as e:
        logging.error(f"Could not update playlist {playlist_id}: {e}")
        return {'error': str(e)}

def update_video_details(credentials, video_id, title, description, tags, privacy_status, publish_at=None):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        video_response = youtube.videos().list(part='snippet,status', id=video_id).execute()
        if not video_response.get('items'): return {'error': 'Video not found.'}
        video = video_response['items'][0]
        video['snippet']['title'] = title
        video['snippet']['description'] = description
        video['snippet']['tags'] = tags
        video['status']['privacyStatus'] = privacy_status
        if publish_at:
            video['status']['publishAt'] = publish_at.isoformat(timespec='seconds') + "Z"
        else:
            video['status'].pop('publishAt', None)
        request = youtube.videos().update(part="snippet,status", body=video)
        response = request.execute()
        return response
    except Exception as e:
        logging.error(f"Could not update video {video_id}: {e}")
        return {'error': str(e)}

def upload_video(credentials, video_file, metadata):
    media_body = None
    temp_filepath = None
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            "snippet": {
                "title": metadata.get('title'),
                "description": metadata.get('description'),
                "tags": metadata.get('tags', []),
                "categoryId": metadata.get('category_id', '22')
            },
            "status": { "privacyStatus": metadata.get('privacy_status', 'private') }
        }
        if metadata.get('publish_at'):
            body['status']['publishAt'] = metadata['publish_at'].isoformat(timespec='seconds') + "Z"
        
        temp_dir = "/tmp" if os.path.exists("/tmp") else "tmp"
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        temp_filepath = os.path.join(temp_dir, video_file.filename)
        video_file.save(temp_filepath)

        media_body = MediaFileUpload(temp_filepath, chunksize=-1, resumable=True)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media_body
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logging.info(f"Uploaded {int(status.progress() * 100)}%.")
        
        return response
    except Exception as e:
        logging.error(f"Could not upload video: {e}")
        return {'error': str(e)}
    finally:
        if media_body and hasattr(media_body, '_stream') and not media_body._stream.closed:
            media_body._stream.close()
            logging.info("Media stream for video upload closed.")
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                logging.info(f"Temporary video file {temp_filepath} removed.")
            except Exception as e:
                logging.error(f"Error removing temporary video file {temp_filepath}: {e}")

def set_video_thumbnail(credentials, video_id, image_file):
    media_body = None
    temp_filepath = None
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        temp_dir = "/tmp" if os.path.exists("/tmp") else "tmp"
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        temp_filepath = os.path.join(temp_dir, image_file.filename)
        image_file.save(temp_filepath)
        
        media_body = MediaFileUpload(temp_filepath)
        
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=media_body
        )
        response = request.execute()
        return response
    except Exception as e:
        logging.error(f"Could not set thumbnail for video {video_id}: {e}")
        return {'error': str(e)}
    finally:
        if media_body and hasattr(media_body, '_stream') and not media_body._stream.closed:
            media_body._stream.close()
            logging.info("Media stream for thumbnail closed.")
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                logging.info(f"Temporary thumbnail file {temp_filepath} removed.")
            except Exception as e:
                logging.error(f"Error removing temporary thumbnail file {temp_filepath}: {e}")
