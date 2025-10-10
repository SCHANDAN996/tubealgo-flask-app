# Filepath: tubealgo/services/youtube_core.py

import itertools
import logging
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tubealgo.models import get_config_value, APIKeyStatus
from tubealgo import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_youtube_service():
    """
    Creates and returns a YouTube Data API service object.
    Cycles through available API keys if a quota error occurs.
    """
    API_KEYS_STRING = get_config_value('YOUTUBE_API_KEYS', '')
    API_KEYS = [key.strip() for key in API_KEYS_STRING.split(',') if key.strip()]
    
    if not API_KEYS: 
        return None, "Server API Key not configured."

    key_cycler = itertools.cycle(API_KEYS)
    
    for _ in range(len(API_KEYS)):
        api_key = next(key_cycler)
        try:
            service = build('youtube', 'v3', developerKey=api_key)
            service.search().list(part='snippet', q='test', maxResults=1).execute()
            logging.info(f"Using API Key starting with: {api_key[:5]}")
            return service, None
        except HttpError as e:
            error_content = getattr(e, 'content', str(e)).decode('utf-8', 'ignore')
            if 'quotaExceeded' in error_content:
                logging.warning(f"API Key {api_key[:5]} quota exceeded. Cycling to next key.")
                
                try:
                    key_identifier = f"{api_key[:8]}...{api_key[-4:]}"
                    key_status = APIKeyStatus.query.filter_by(key_identifier=key_identifier).first()
                    if not key_status:
                        key_status = APIKeyStatus(key_identifier=key_identifier)
                        db.session.add(key_status)
                    
                    key_status.status = 'exhausted'
                    key_status.last_failure_at = datetime.utcnow()
                    db.session.commit()
                except Exception as db_error:
                    db.session.rollback()
                    logging.error(f"Failed to update API key status in DB: {db_error}")
                    
                continue
            return None, f"API Key Error: {error_content}"
    return None, "All API Keys have exhausted their quota."