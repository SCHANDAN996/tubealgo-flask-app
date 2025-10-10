# Filepath: tubealgo/services/suggestion_service.py
import requests
import json

def get_keyword_suggestions(keyword):
    try:
        url = f"http://google.com/complete/search?client=chrome&q={keyword}"
        response = requests.get(url)
        response.raise_for_status()
        suggestions_list = json.loads(response.text)[1]
        formatted_suggestions = [{"keyword": suggestion, "volume": "(coming soon)"} for suggestion in suggestions_list]
        if not formatted_suggestions:
            return {"suggestions": [{"keyword": "No suggestions found.", "volume": ""}]}
        return {"suggestions": formatted_suggestions}
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}
