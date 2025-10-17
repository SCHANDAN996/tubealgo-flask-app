# tubealgo/services/ai_service.py

import os
import openai
import json
import logging
from datetime import datetime
import google.generativeai as genai
from .cache_manager import get_from_cache, set_to_cache
# ========= यहाँ बदलाव किया गया है ('search_videos' को हटा दिया गया है) =========
from .youtube_fetcher import get_latest_videos
from tubealgo.models import get_config_value, get_setting, APIKeyStatus, log_system_event
from tubealgo import db

# Global variables for managing AI clients
gemini_keys = []
openai_client = None

def _mask_gemini_key(key):
    """Masks a Gemini API key for logging."""
    if isinstance(key, str) and len(key) > 8:
        return f"gemini_{key[:4]}...{key[-4:]}"
    return "invalid_gemini_key"

def initialize_ai_clients():
    """Initializes all AI clients once when the application starts."""
    global gemini_keys, openai_client
    
    gemini_keys_str = get_config_value('GEMINI_API_KEY', '')
    if gemini_keys_str:
        try:
            loaded_keys = json.loads(gemini_keys_str)
            if isinstance(loaded_keys, list):
                gemini_keys = [key.strip() for key in loaded_keys if key.strip()]
        except json.JSONDecodeError:
            gemini_keys = [key.strip() for key in gemini_keys_str.split(',') if key.strip()]
    
    if gemini_keys:
        print(f"INFO: Loaded {len(gemini_keys)} Gemini API keys from config.")

    openai_key = get_config_value('OPENAI_API_KEY')
    if openai_key:
        print("INFO: Initializing OpenAI Client.")
        openai_client = openai.OpenAI(api_key=openai_key)

def get_next_gemini_client():
    """
    Finds a valid, active Gemini key, configures the service, and returns it.
    Marks keys as 'exhausted' upon failure.
    """
    if not gemini_keys:
        return None

    all_key_identifiers = [_mask_gemini_key(key) for key in gemini_keys]
    
    exhausted_keys_query = APIKeyStatus.query.filter(
        APIKeyStatus.key_identifier.in_(all_key_identifiers),
        APIKeyStatus.status == 'exhausted'
    ).all()
    exhausted_identifiers = {k.key_identifier for k in exhausted_keys_query}

    active_keys_to_try = [key for key in gemini_keys if _mask_gemini_key(key) not in exhausted_identifiers]

    if not active_keys_to_try:
        log_system_event("All Gemini API keys are marked as exhausted.", "ERROR", "GEMINI_KEYS_EXHAUSTED")
        return None

    for key in active_keys_to_try:
        try:
            genai.configure(api_key=key)
            selected_model_name = get_config_value('SELECTED_AI_MODEL', 'gemini-1.5-flash-latest')
            model = genai.GenerativeModel(selected_model_name)
            
            model.generate_content("test", generation_config={'max_output_tokens': 1})

            print(f"INFO: Successfully configured Gemini with key {_mask_gemini_key(key)}")
            return model
        except Exception as e:
            error_message = str(e).lower()
            key_identifier = _mask_gemini_key(key)
            
            if 'api_key_invalid' in error_message or 'permission_denied' in error_message or 'quota' in error_message:
                logging.warning(f"Gemini API Key {key_identifier} failed and will be marked as exhausted. Reason: {error_message}")
                
                key_status = APIKeyStatus.query.filter_by(key_identifier=key_identifier).first()
                if not key_status:
                    key_status = APIKeyStatus(key_identifier=key_identifier)
                    db.session.add(key_status)
                
                key_status.status = 'exhausted'
                key_status.last_failure_at = datetime.utcnow()
                db.session.commit()

                log_system_event("Gemini API Key Exhausted", "QUOTA_EXCEEDED", f"Key: {key_identifier}")
            else:
                logging.error(f"An unexpected error occurred with Gemini key {key_identifier}: {e}")
            
            continue
            
    return None


def generate_ai_response(system_prompt, user_prompt, is_json=False):
    """
    Generates a response from the AI, using the robust key management system.
    """
    gemini_client = get_next_gemini_client()

    if gemini_client:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            if is_json:
                full_prompt += "\n\nIMPORTANT: Respond ONLY with a valid JSON object."
            
            response = gemini_client.generate_content(full_prompt)
            
            if is_json:
                cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
                return json.loads(cleaned_text)
            else:
                return response.text
        
        except Exception as e:
            logging.error(f"Gemini generation failed even with a selected client: {e}")

    if openai_client:
        try:
            print("INFO: Gemini failed or not available, falling back to OpenAI.")
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format = {"type": "json_object"} if is_json else {"type": "text"}
            response = openai_client.chat.completions.create(model="gpt-4o", messages=messages, response_format=response_format)
            content = response.choices[0].message.content
            return json.loads(content) if is_json else content
        except Exception as e:
            logging.error(f"OpenAI generation also failed: {e}")

    return {'error': 'No AI provider is configured or all API keys failed. Please check your keys.'}


def generate_idea_set(topic, language='English', description=None, video_type='any'):
    default_system_prompt = (
        "You are a world-class YouTube content strategist and scriptwriter. Your task is to generate a set of 3 creative, distinct, and engaging video ideas based on a user's topic. Each idea must come with a full script outline."
    )
    system_prompt = get_setting('prompt_generate_ideas', default_system_prompt)

    video_type_instruction = ""
    if video_type == 'short':
        video_type_instruction = "The user wants ideas for a **Short Video** (under 60 seconds, vertical format). The title should be very catchy and the script outline must be extremely concise, fast-paced, with a strong hook and a quick payoff."
    elif video_type == 'long':
        video_type_instruction = "The user wants ideas for a **Long Video** (standard 8-15 minute format). The script outline should be detailed, with multiple sections, talking points, and clear visual cues."
    if language.lower() == 'hindi':
        lang_instruction = "IMPORTANT: The entire output (all titles and script outlines) must be in pure Hindi (Devanagari script)."
    elif language.lower() == 'mix':
        lang_instruction = "IMPORTANT: The entire output must be in a mix of Hindi (Devanagari script) and English. Use technical terms in English and explanations in Hindi."
    elif language.lower() == 'hinglish':
        lang_instruction = "IMPORTANT: The entire output must be in Hinglish (a mix of Hindi and English, written in the Latin script, like 'Fan bending ka issue kaise solve karein')."
    else: 
        lang_instruction = "IMPORTANT: The entire output must be in English."
    description_context = ""
    if description and description.strip():
        description_context = f"The user has provided these additional details about their idea: '{description}'. Use these details to make the ideas more specific and relevant."
    user_prompt = (
        f"My video topic is: '{topic}'.\n"
        f"{description_context}\n"
        f"{video_type_instruction}\n\n"
        f"{lang_instruction}\n\n"
        "Please generate an array of exactly 3 unique video ideas. Each idea in the array should be a JSON object with two keys:\n"
        "1.  `title`: A catchy, viral-potential YouTube title for the video. Include 1-2 relevant emojis in the title.\n"
        "2.  `outline`: A complete, well-structured script outline in Markdown format. The outline MUST start directly with the 'Intro Hook' and MUST NOT repeat the title from the `title` key. Use emojis strategically (e.g., 훅 Intro, 💡 Main Points, 🎬 Visual, 🗣️ Host, ✅ Call to Action, 👋 Outro) to make the outline visually appealing and easy to scan. Use Markdown headings (like `### Main Talking Points`) for sections.\n\n"
        "The script outline must include these sections: 'Intro Hook', 'Main Talking Points' with visual cues, a 'Call to Action', and an 'Outro'.\n\n"
        "Return your response as a single, valid JSON object with a single top-level key: `ideas`. The value of `ideas` should be the array of the 3 idea objects."
    )
    
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

def get_ai_video_suggestions(user, user_videos=None):
    from tubealgo.models import Competitor
    if not user.competitors.first():
        return {'error': 'Please add at least one competitor to generate AI suggestions.'}
    cache_key = f"ai_suggestions_v2:{user.id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    try:
        competitors = user.competitors.order_by(Competitor.position).limit(5).all()
        all_videos_data = [get_latest_videos(c.channel_id_youtube, 5) for c in competitors]
        all_videos = [v for data in all_videos_data for v in data.get('videos', [])]
        if not all_videos: return {'error': 'Could not fetch competitor videos.'}
        successful_videos = sorted(all_videos, key=lambda x: x.get('view_count', 0), reverse=True)[:5]
        if not successful_videos: return {'error': 'Not enough data to analyze.'}
        prompt_context = "Here is a list of successful videos from competitors:\n\n"
        for i, video in enumerate(successful_videos, 1):
            prompt_context += (f"- Title: {video.get('title')}\n- Views: {video.get('view_count'):,}\n")
        system_prompt = "You are an expert YouTube growth strategist."
        user_prompt = (f"{prompt_context}\n\nAnalyze these videos. Generate exactly 3 unique and compelling video ideas for my channel. For each idea, provide a catchy 'title' and a one-sentence 'description'. Return the output as a JSON object with a key 'suggestions' which is an array of objects.")
        response_data = generate_ai_response(system_prompt, user_prompt, is_json=True)
        if 'error' in response_data: return response_data
        final_suggestions = response_data.get("suggestions", [])
        set_to_cache(cache_key, final_suggestions, expire_hours=24)
        return final_suggestions
    except Exception as e:
        return {'error': f'Could not generate AI suggestions. Details: {str(e)}'}

def generate_titles_and_tags(user, topic, exclude_tags=None):
    default_system_prompt = "You are a world-class YouTube viral title expert and SEO strategist. Your task is to generate a ranked list of title suggestions and categorized tags based on a user's topic."
    system_prompt = get_setting('prompt_titles_and_tags', default_system_prompt)

    user_prompt = (
        f"Analyze the user's video topic: '{topic}'.\n\n"
        "PART 1: TITLE GENERATION\n"
        "Generate an array of 10 unique title objects. You MUST rank them from best to worst based on their potential for virality, CTR, and SEO.\n"
        "Each title object must have three keys:\n"
        "1. 'title': A catchy, compelling video title. MUST include 1-2 relevant emojis.\n"
        "2. 'score': An integer score from 80 to 100, representing its overall effectiveness. The best title should have the highest score.\n"
        "3. 'strengths': An array of 2-3 short, powerful strings explaining why the title is good. Use professional terms from this list ONLY: 'High CTR', 'SEO Friendly', 'Sparks Curiosity', 'Emotional Hook', 'Urgency', 'Viral Potential', 'Strong Hook', 'Clear Benefit'.\n\n"
        
        "PART 2: TAG GENERATION\n"
        "Generate a JSON object for SEO tags with three keys:\n"
        "1. 'main_keywords': An array of 2-3 most critical, high-volume tags for the main topic.\n"
        "2. 'secondary_keywords': An array of 7-10 related LSI (Latent Semantic Indexing) tags that provide context.\n"
        "3. 'broad_tags': An array of 3-5 general category tags.\n\n"
        "FINAL OUTPUT:\n"
        "Return a single, valid JSON object with two top-level keys: 'titles' (containing the array of title objects) and 'tags' (containing the tag object with its categories)."
    )
    
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

def generate_description(user, topic, title, language='English'):
    defaults_context = "Use the following user-provided details to personalize the description. If a detail is not provided, DO NOT mention it.\n"
    has_defaults = False
    if user.default_channel_name:
        defaults_context += f"- Channel Name: {user.default_channel_name}\n"
        has_defaults = True
    if user.default_social_handles:
        defaults_context += f"- Social Media Links:\n{user.default_social_handles}\n"
        has_defaults = True
    if user.default_contact_info:
        defaults_context += f"- Contact Info: {user.default_contact_info}\n"
        has_defaults = True

    if not has_defaults:
        defaults_context = "" 

    default_system_prompt = "You are a world-class YouTube SEO expert. Your task is to write a highly-optimized YouTube description following a professional structure."
    system_prompt = get_setting('prompt_description', default_system_prompt)

    user_prompt = (
        f"My video title is: '{title}'\nThe main topic is: '{topic}'\nThe requested language for the output is: {language}\n\n{defaults_context}\n"
        "Generate a new, unique, and well-structured YouTube description (at least 200 words). The description MUST follow this professional format:\n\n"
        "1. **Compelling Hook (First 2-3 lines):** Start with a strong hook that grabs the viewer's attention, uses keywords from the title, and makes them want to watch.\n\n"
        "2. **Detailed Summary:** Write a detailed paragraph summarizing the video's content. Naturally include important keywords from the topic. Use emojis to break up text and make it easy to read.\n\n"
        "3. **Timestamps:** Provide a template with 3-5 logical chapter timestamps based on the topic. Use the format '(00:00) Chapter Title'. The user will edit the exact times later.\n\n"
        "4. **Call to Action (CTA):** Include a clear call to subscribe to the channel and a placeholder encouraging viewers to watch another relevant video (e.g., '📺 Watch Next: [Link to Your Other Video]').\n\n"
        "5. **User's Links:** (If provided in the context) Add a section for the user's social media and contact info under a clear heading like '🔗 Connect with Me' or 'Follow Us'.\n\n"
        "6. **Relevant Hashtags:** End with a list of 3-5 relevant #hashtags on new lines. The hashtags should be single words and relevant to the video topic.\n\n"
        "Return the entire, perfectly formatted description as a single string."
    )
    
    description_text = generate_ai_response(system_prompt, user_prompt, is_json=False)
    return {'description': description_text} if isinstance(description_text, str) else description_text

def generate_script_outline(video_title, language='English'):
    """This function is a wrapper for generate_idea_set for backward compatibility."""
    idea_set = generate_idea_set(topic=video_title, language=language)
    if 'ideas' in idea_set and len(idea_set['ideas']) > 0:
        return {'outline': idea_set['ideas'][0]['outline']}
    elif 'error' in idea_set:
        return {'error': idea_set['error']}
    return {'error': 'Could not generate a script outline.'}

def generate_motivational_suggestion(video_title):
    system_prompt = "You are a YouTube growth strategist. Your goal is to provide creative, motivational video ideas in Hindi, formatted for a Telegram message."
    user_prompt = (f"My competitor had success with a video titled: '{video_title}'.\n\nBased on this topic, do the following in a friendly, motivational tone:\n1. Generate 2 alternative, more engaging, video titles for me in Hindi.\n2. Provide one short, actionable 'Pro Tip' in English with Hindi translation for making the video better.\nFormat the output as a single string for a Telegram message, using Markdown (*bold*). Start with a motivational sentence.")
    return generate_ai_response(system_prompt, user_prompt, is_json=False)

def generate_playlist_suggestions(user, user_playlists_titles, competitor_video_titles, limit=3):
    
    if not competitor_video_titles:
        return {'error': 'Not enough competitor data to generate suggestions.'}
    channel_name = user.channel.channel_title if user.channel else "my channel"
    system_prompt = f"You are a YouTube expert specializing in content strategy. Your client's channel name is '{channel_name}'."
    user_prompt = (f"My existing playlists:\n- {'\n- '.join(user_playlists_titles)}\n\nPopular video titles from my competitors:\n- {'\n- '.join(competitor_video_titles[:20])}\n\nSuggest exactly {limit} new playlist ideas that I don't already have.\nFor each idea, provide a catchy, SEO-friendly 'title' and a detailed 'description' (100-150 words).\n\nReturn the output as a single, valid JSON object with a key 'suggestions', which is an array of objects. Each object must have 'title' and 'description' keys.")
    return generate_ai_response(system_prompt, user_prompt, is_json=True)