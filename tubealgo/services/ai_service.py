# tubealgo/services/ai_service.py

import os
import openai
import json
import logging
import google.generativeai as genai
from .cache_manager import get_from_cache, set_to_cache
from .youtube_fetcher import get_latest_videos, get_video_details, get_most_viewed_videos, search_videos
from tubealgo.models import get_config_value

# Global variables for managing AI clients
gemini_keys = []
current_key_index = 0
openai_client = None

def initialize_ai_clients():
    """Initializes all AI clients once when the application starts."""
    global gemini_keys, openai_client
    
    # Load and split Gemini Keys from the database/config
    gemini_keys_json = get_config_value('GEMINI_API_KEY', '[]')
    try:
        loaded_keys = json.loads(gemini_keys_json)
        if isinstance(loaded_keys, list):
            gemini_keys = [key.strip() for key in loaded_keys if key.strip()]
            if gemini_keys:
                print(f"INFO: Loaded {len(gemini_keys)} Gemini API keys from database/config.")
    except json.JSONDecodeError:
        print("ERROR: Could not parse GEMINI_API_KEY from database. It's not a valid JSON list.")

    # Load OpenAI client
    openai_key = get_config_value('OPENAI_API_KEY')
    if openai_key:
        print("INFO: Initializing OpenAI Client.")
        openai_client = openai.OpenAI(api_key=openai_key)

def get_next_gemini_client():
    """Rotates to the next Gemini API key and configures the model selected in the admin panel."""
    global current_key_index
    if not gemini_keys:
        return None

    key_to_use = gemini_keys[current_key_index]
    current_key_index = (current_key_index + 1) % len(gemini_keys)
    
    try:
        genai.configure(api_key=key_to_use)
        
        # Get the selected model from the database, with a fallback default.
        selected_model_name = get_config_value('SELECTED_AI_MODEL', 'gemini-1.5-flash-latest')
        print(f"INFO: Using model: {selected_model_name}")
        
        # Use that model
        model = genai.GenerativeModel(selected_model_name) 
        
        print(f"INFO: Using Gemini key ending in ...{key_to_use[-4:]}")
        return model
    except Exception as e:
        print(f"ERROR: Failed to configure Gemini with key ...{key_to_use[-4:]}. Error: {e}")
        return None

def generate_ai_response(system_prompt, user_prompt, is_json=False):
    """
    Generates a response from the AI, handling key rotation and retries for Gemini.
    """
    if gemini_keys:
        for _ in range(len(gemini_keys)):
            try:
                gemini_client = get_next_gemini_client()
                if not gemini_client:
                    continue # If key fails to configure, try the next one

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
                key_index = ((current_key_index - 1) + len(gemini_keys)) % len(gemini_keys)
                logging.error(f"AI generation failed for key index {key_index}: {e}")
                # Loop will continue to the next key
        
    if openai_client:
        try:
            print("INFO: All Gemini keys failed, falling back to OpenAI.")
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format = {"type": "json_object"} if is_json else {"type": "text"}
            response = openai_client.chat.completions.create(model="gpt-4o", messages=messages, response_format=response_format)
            content = response.choices[0].message.content
            return json.loads(content) if is_json else content
        except Exception as e:
            logging.error(f"OpenAI generation also failed: {e}")

    return {'error': 'No AI provider is configured or all API keys failed. Please check your keys.'}

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
    system_prompt = "You are a world-class YouTube viral title expert and SEO strategist. Your task is to generate a ranked list of title suggestions and categorized tags based on a user's topic."
    
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
    if user.default_channel_name: defaults_context += f"- Channel Name: {user.default_channel_name}\n"
    if user.default_social_handles: defaults_context += f"- Social Media Links:\n{user.default_social_handles}\n"
    if user.default_contact_info: defaults_context += f"- Contact Info: {user.default_contact_info}\n"
    
    system_prompt = "You are a world-class YouTube SEO expert. Your task is to write a highly-optimized YouTube description following a professional structure."
    
    user_prompt = (
        f"My video title is: '{title}'\nThe main topic is: '{topic}'\nThe requested language for the output is: {language}\n\n{defaults_context}\n"
        "Generate a new, unique, and well-structured YouTube description (at least 200 words). The description MUST follow this professional format:\n\n"
        "1. **Compelling Hook (First 2-3 lines):** Start with a strong hook that grabs the viewer's attention, uses keywords from the title, and makes them want to watch.\n\n"
        "2. **Detailed Summary:** Write a detailed paragraph summarizing the video's content. Naturally include important keywords from the topic. Use emojis to break up text and make it easy to read.\n\n"
        "3. **Timestamps:** Provide a template with 3-5 logical chapter timestamps based on the topic. Use the format '(00:00) Chapter Title'. The user will edit the exact times later.\n\n"
        "4. **Call to Action (CTA):** Include a clear call to subscribe to the channel and a placeholder encouraging viewers to watch another relevant video (e.g., '📺 Watch Next: [Link to Your Other Video]').\n\n"
        "5. **User's Links:** (If provided in the context) Add a section for the user's social media and contact info under a clear heading like 'Connect with Me'.\n\n"
        "6. **Relevant Hashtags:** End with a list of 3-5 relevant #hashtags on new lines.\n\n"
        "Return the entire, perfectly formatted description as a single string."
    )
    
    description_text = generate_ai_response(system_prompt, user_prompt, is_json=False)
    return {'description': description_text} if isinstance(description_text, str) else description_text

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