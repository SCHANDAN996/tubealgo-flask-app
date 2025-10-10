# Filepath: tubealgo/services/analysis_service.py

from textblob import TextBlob
import logging

def analyze_comment_sentiment(comments):
    """
    Analyzes the sentiment of a list of comments.
    Returns a dictionary with the percentage of positive and negative comments,
    ignoring neutral ones for the percentage calculation.
    """
    if not comments:
        return {'positive': 0, 'negative': 0}

    positive_count = 0
    negative_count = 0
    
    for comment in comments:
        try:
            analysis = TextBlob(comment)
            # Polarity is a float within the range [-1.0, 1.0]
            if analysis.sentiment.polarity > 0.1:  # Consider slightly positive as positive
                positive_count += 1
            elif analysis.sentiment.polarity < -0.1:  # Consider slightly negative as negative
                negative_count += 1
        except Exception as e:
            logging.warning(f"Could not analyze comment sentiment for a comment: {e}")

    total_polarized = positive_count + negative_count
    if total_polarized == 0:
        return {'positive': 0, 'negative': 0}

    return {
        'positive': round((positive_count / total_polarized) * 100),
        'negative': round((negative_count / total_polarized) * 100)
    }