# Filepath: tubealgo/services/openai_service.py

import os
import openai
import json
import logging
import hashlib
from .cache_manager import get_from_cache, set_to_cache
from .youtube_fetcher import get_latest_videos, get_video_details, get_most_viewed_videos, search_videos
from tubealgo.models import get_config_value

def get_ai_video_suggestions(user):
    from tubealgo.models import Competitor
    if not user.competitors.first():
        return {'error': 'Please add at least one competitor to generate AI suggestions.'}
    cache_key = f"ai_suggestions:{user.id}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data
    try:
        competitors = user.competitors.order_by(Competitor.position).limit(5).all()
        all_videos = []
        for comp in competitors:
            # MODIFIED: Handle new data structure {'videos': [...]}
            video_data = get_latest_videos(comp.channel_id_youtube, max_results=5)
            all_videos.extend(video_data.get('videos', []))
        
        if not all_videos:
            return {'error': 'Could not fetch competitor videos to analyze.'}
        
        detailed_videos = [get_video_details(v['id']) for v in all_videos if v and 'id' in v]
        successful_videos = sorted(
            [v for v in detailed_videos if v and 'error' not in v], 
            key=lambda x: x.get('view_count', 0), 
            reverse=True
        )[:5]
        
        if not successful_videos:
            return {'error': 'Not enough data from successful videos to analyze.'}
        
        prompt_context = "Here is a list of highly successful recent videos from my competitors:\n\n"
        for i, video in enumerate(successful_videos, 1):
            tags = ", ".join(video.get('tags', []))
            prompt_context += (f"Video {i}:\n- Title: {video.get('title')}\n- Tags: {tags}\n- Views: {video.get('view_count'):,}\n\n")
        
        system_prompt = "You are an expert YouTube growth strategist. Your goal is to identify patterns and suggest unique, viral video ideas."
        user_prompt = (
            f"{prompt_context}"
            "Analyze these videos. Identify common themes and keywords. "
            "Generate exactly 3 unique and compelling video ideas for my channel. "
            "For each idea, provide a catchy title and a one-sentence description. "
            "Return the output as a valid JSON object with a single key 'suggestions' which is an array of objects. Each object must have 'title' and 'description' keys."
        )
        
        client = openai.OpenAI(api_key=get_config_value('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        suggestions_data = json.loads(response.choices[0].message.content)
        final_suggestions = suggestions_data.get("suggestions", [])
        set_to_cache(cache_key, final_suggestions, expire_hours=24)
        return final_suggestions
    except Exception as e:
        print(f"Error getting AI suggestions: {e}")
        return {'error': f'Could not generate AI suggestions. Details: {str(e)}'}

def generate_titles_and_tags(user, topic, exclude_tags=None):
    from tubealgo.models import Competitor
    if not user.competitors.first():
        return {'error': 'Please add at least one competitor for smart generation.'}

    exclude_hash = hashlib.md5(str(sorted(exclude_tags or [])).encode()).hexdigest()[:6]
    cache_key = f"titles_tags_v3:{user.id}:{topic}:{exclude_hash}"
    
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data
    try:
        competitors = user.competitors.order_by(Competitor.position).limit(3).all()
        prompt_context = "Here are examples of successful video titles and tags from top competitors in this niche:\n\n"
        for comp in competitors:
            # MODIFIED: Handle new data structure {'videos': [...]}
            video_data = get_most_viewed_videos(comp.channel_id_youtube, max_results=3)
            videos = video_data.get('videos', [])
            for video in videos:
                details = get_video_details(video['id'])
                if details and 'error' not in details:
                    tags = ", ".join(details.get('tags', []))
                    prompt_context += f"Example Title: {details.get('title')}\nExample Tags: {tags}\n\n"
        
        exclusion_prompt = ""
        if exclude_tags:
            exclusion_prompt = f"IMPORTANT: You MUST NOT suggest any of the following tags as they have been seen before: {', '.join(exclude_tags)}.\n\n"

        system_prompt = "You are a world-class YouTube content strategist specializing in creating viral video titles and SEO-optimized tags."
        user_prompt = (
            f"{prompt_context}"
            f"Based on the patterns from these successful examples, my new video is about: '{topic}'.\n\n"
            f"{exclusion_prompt}"
            "Your task is:\n"
            "1. Generate 5 catchy, viral-style video titles for my topic. Add 1 or 2 relevant emojis to each title.\n"
            "2. Generate a list of 15-20 highly relevant, SEO-optimized tags for this video.\n\n"
            "Return the output as a single, valid JSON object with two keys: 'titles' (an array of strings) and 'tags' (an array of strings)."
        )
        client = openai.OpenAI(api_key=get_config_value('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        results = json.loads(response.choices[0].message.content)
        set_to_cache(cache_key, results, expire_hours=24)
        return results
    except Exception as e:
        print(f"Error generating titles/tags: {e}")
        return {'error': f"Could not generate results. Details: {str(e)}"}

def generate_description(user, topic, title, language='English'):
    cache_key = f"description_v4:{user.id}:{topic}:{title}:{language}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data
    try:
        # MODIFIED: Handle new data structure {'videos': [...]}
        video_search_data = search_videos(topic, max_results=3)
        competitor_videos = video_search_data.get('videos', [])
        
        competitor_descriptions = []
        if competitor_videos:
            for video in competitor_videos:
                details = get_video_details(video['id'])
                if details and 'error' not in details and details.get('description'):
                    competitor_descriptions.append(details['description'])
        
        system_prompt = "You are a world-class YouTube SEO and content strategist. Your task is to write a long, detailed, engaging, and highly optimized YouTube video description in the requested language, inspired by successful examples."
        inspiration_context = "To help you, here are descriptions from top-ranking videos on the same topic. Analyze their structure, keywords, tone, and calls-to-action:\n\n"
        if competitor_descriptions:
            for i, desc in enumerate(competitor_descriptions, 1):
                inspiration_context += f"--- COMPETITOR DESCRIPTION EXAMPLE {i} ---\n{desc}\n\n"
        else:
            inspiration_context = "No direct competitor descriptions were found, so create a high-quality description based on best practices.\n\n"
        
        defaults_context = "Use the following user-provided details to personalize the description. If a detail is not provided, DO NOT mention it or create placeholders for it.\n"
        if user.default_channel_name: defaults_context += f"- Channel Name: {user.default_channel_name}\n"
        if user.default_social_handles: defaults_context += f"- Social Media Links:\n{user.default_social_handles}\n"
        if user.default_contact_info: defaults_context += f"- Contact Info: {user.default_contact_info}\n"
        
        user_prompt = (
            f"My video title is: '{title}'\n"
            f"The main topic is: '{topic}'\n"
            f"The requested language for the output is: {language}\n\n"
            f"{inspiration_context}"
            f"{defaults_context}\n"
            "Now, based on all this information, generate a new, unique, and long-form YouTube description (at least 150-200 words). The description MUST include:\n"
            "1. Start by repeating the video title for SEO.\n"
            "2. A compelling 2-3 sentence hook.\n"
            "3. A detailed, multi-paragraph summary of the video content. Use relevant emojis (like ✅, 👉, 🔴) to break up text and improve readability.\n"
            "4. A section for social media links ONLY IF provided.\n"
            "5. A contact/business inquiries section ONLY IF provided.\n"
            "6. A concluding sentence.\n"
            "7. A list of 3-5 relevant and popular #hashtags at the very end.\n\n"
            "Write the entire description in the requested language."
        )
        
        client = openai.OpenAI(api_key=get_config_value('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        description = response.choices[0].message.content
        result = {'description': description}
        set_to_cache(cache_key, result, expire_hours=24)
        return result
    except Exception as e:
        print(f"Error generating description: {e}")
        return {'error': f"Could not generate description. Details: {str(e)}"}

def generate_motivational_suggestion(video_title):
    try:
        client = openai.OpenAI(api_key=get_config_value('OPENAI_API_KEY'))
        system_prompt = "You are a world-class YouTube growth strategist. Your goal is to provide creative, engaging, and motivational video ideas in Hindi, formatted for a Telegram message."
        user_prompt = (
            f"My competitor just had success with a video titled: '{video_title}'.\n\n"
            "Based on this topic, do the following:\n"
            "1. Generate 2 alternative, more engaging, and catchy video titles for me in Hindi.\n"
            "2. Provide one short, actionable 'Pro Tip' in English with Hindi translation for making the video even better (e.g., thumbnail, title, or editing advice).\n"
            "3. Frame the entire response in a friendly, motivational tone.\n\n"
            "Format the output as a single string for a Telegram message. Use Markdown for formatting (like *bold*). Start with a motivational sentence.\n"
            "Example format:\n"
            "यह एक बेहतरीन टॉपिक है! दर्शक इसे पसंद कर रहे हैं। आप इससे भी अच्छा वीडियो बना सकते हैं:\n\n"
            "* *आइडिया 1:* [Your Idea 1]\n"
            "* *आइडिया 2:* [Your Idea 2]\n\n"
            "*✨ प्रो टिप:* [Your Tip in English] (Your Tip in Hindi)"
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating motivational suggestion: {e}")
        return "Could not generate AI suggestion at this time."

def generate_playlist_suggestions(user, user_playlists_titles, competitor_video_titles):
    if not competitor_video_titles:
        return {'error': 'Not enough competitor data to generate suggestions. Please add competitors.'}

    channel_name = user.channel.channel_title if user.channel else user.default_channel_name or "my channel"

    system_prompt = f"You are a YouTube expert specializing in content strategy and SEO. Your client's channel name is '{channel_name}'. You will be given a list of their existing playlists and a list of popular video titles from their competitors. Your task is to identify content gaps and suggest new, engaging playlists."
    user_prompt = (
        f"Here are my existing playlists:\n- {'\n- '.join(user_playlists_titles)}\n\n"
        f"Here are popular video titles from my competitors, which represent popular topics in my niche:\n- {'\n- '.join(competitor_video_titles[:20])}\n\n"
        "Based on this, please suggest 3 to 5 new playlist ideas that I don't already have but would be a good fit for my channel. "
        "For each idea, provide:\n"
        "1. A catchy, SEO-friendly 'title' (under 150 characters).\n"
        "2. A detailed 'description' (around 100-150 words) that explains what the playlist is about. The description should be SEO-optimized and include my channel name '{channel_name}'.\n\n"
        "Return the output as a single, valid JSON object with a key 'suggestions', which is an array of objects. Each object must have 'title' and 'description' keys."
    )

    try:
        client = openai.OpenAI(api_key=get_config_value('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        results = json.loads(response.choices[0].message.content)
        return results
    except Exception as e:
        logging.error(f"Error generating playlist suggestions: {e}")
        return {'error': f"Could not generate suggestions. Details: {str(e)}"}