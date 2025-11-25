import os
import logging
from typing import Dict, List, Optional, Tuple
from apify_client import ApifyClient
from django.conf import settings

logger = logging.getLogger(__name__)

# Required emoji fingerprint for LinkedIn profiles
REQUIRED_EMOJI_FINGERPRINT = ['🧗‍♂️', '😄', '🤩', '🤖', '😛']


def fetch_linkedin_profile_data(profile_url: str) -> Optional[Dict]:
    """
    Fetch LinkedIn profile data from Apify.
    
    Args:
        profile_url: LinkedIn profile URL
        
    Returns:
        Profile data dictionary or None if error occurred
    """
    apify_token = os.getenv('APIFY_API_TOKEN')
    if not apify_token:
        logger.error("[linkedin_helper] APIFY_API_TOKEN not found in environment variables")
        return None
    
    try:
        client = ApifyClient(apify_token)
        
        run_input = {
            "profileUrls": [profile_url]
        }
        
        logger.info(f"[linkedin_helper] Starting Apify actor for profile: {profile_url}")
        run = client.actor("2SyF0bVxmgGr8IVCZ").call(run_input=run_input)
        
        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            results.append(item)
        
        if not results:
            logger.warning(f"[linkedin_helper] No results returned from Apify for profile: {profile_url}")
            return None
        
        profile_data = results[0] if results else None
        
        # Проверяем, не вернул ли Apify ошибку вместо данных
        if profile_data and 'error' in profile_data:
            error_msg = profile_data.get('error', 'Unknown error')
            logger.error(f"[linkedin_helper] Apify returned error: {error_msg}")
            # Сохраняем ошибку в глобальной переменной для передачи в details
            return {'_apify_error': error_msg}
        
        logger.info(f"[linkedin_helper] Successfully fetched profile data from Apify. Profile name: {profile_data.get('fullName') if profile_data else 'N/A'}")
        return profile_data
        
    except Exception as e:
        logger.error(f"[linkedin_helper] Error fetching LinkedIn profile data: {str(e)}", exc_info=True)
        return None


def check_emoji_fingerprint(text: Optional[str]) -> bool:
    """
    Check if text contains all required emoji fingerprint.
    
    Args:
        text: Text to check (headline, about, etc.)
        
    Returns:
        True if all emojis are present, False otherwise
    """
    if not text:
        return False
    
    text_str = str(text)
    for emoji in REQUIRED_EMOJI_FINGERPRINT:
        if emoji not in text_str:
            return False
    
    return True


def verify_linkedin_profile(profile_data: Dict) -> Tuple[bool, Dict]:
    """
    Verify LinkedIn profile against criteria.
    
    Criteria:
    1. Minimum 100 connections or followers
    2. Profile must have an avatar
    3. Clear profile description - who you are, what you do
    4. Profile must have emoji fingerprint 🧗‍♂️😄🤩🤖😛
    5. Profile must have 1 place of work
    
    Args:
        profile_data: Profile data dictionary from Apify
        
    Returns:
        Tuple of (is_valid: bool, validation_result: dict)
        validation_result contains:
        - is_valid: bool
        - failed_criteria: List[str] - list of failed criteria names
        - details: Dict with detailed validation info
    """
    failed_criteria = []
    details = {}
    
    # 1. Check connections or followers (minimum 100)
    connections = profile_data.get('connections', 0) or 0
    followers = profile_data.get('followers', 0) or 0
    total_connections_followers = connections + followers
    
    details['connections'] = connections
    details['followers'] = followers
    details['total_connections_followers'] = total_connections_followers
    
    if total_connections_followers < 100:
        failed_criteria.append('MINIMUM_CONNECTIONS_OR_FOLLOWERS')
        details['connections_followers_requirement'] = f"Required: 100, Got: {total_connections_followers}"
    
    # 2. Check if profile has avatar
    profile_pic = profile_data.get('profilePic') or profile_data.get('profilePicHighQuality')
    has_avatar = bool(profile_pic and profile_pic.strip())
    
    details['has_avatar'] = has_avatar
    details['profile_pic'] = profile_pic
    
    if not has_avatar:
        failed_criteria.append('PROFILE_MUST_HAVE_AVATAR')
    
    # 3. Check profile description (about or headline)
    about = profile_data.get('about', '') or ''
    headline = profile_data.get('headline', '') or ''
    description = f"{headline} {about}".strip()
    
    details['has_description'] = bool(description)
    details['headline'] = headline
    details['about'] = about
    
    if not description or len(description.strip()) < 10:
        failed_criteria.append('CLEAR_PROFILE_DESCRIPTION')
        details['description_requirement'] = "Profile must have clear description (headline or about section)"
    
    # 4. Check emoji fingerprint
    # Check in both headline and about sections
    headline_text = str(headline)
    about_text = str(about)
    combined_text = f"{headline_text} {about_text}"
    
    has_emoji_fingerprint = check_emoji_fingerprint(combined_text)
    
    details['has_emoji_fingerprint'] = has_emoji_fingerprint
    details['required_emojis'] = REQUIRED_EMOJI_FINGERPRINT
    
    if not has_emoji_fingerprint:
        failed_criteria.append('PROFILE_MUST_HAVE_EMOJI_FINGERPRINT')
        details['emoji_fingerprint_requirement'] = f"Profile must contain all emojis: {', '.join(REQUIRED_EMOJI_FINGERPRINT)}"
    
    # 5. Check if profile has at least 1 place of work
    experiences = profile_data.get('experiences', [])
    has_work_experience = bool(experiences and len(experiences) > 0)
    
    details['has_work_experience'] = has_work_experience
    details['experiences_count'] = len(experiences) if experiences else 0
    
    if not has_work_experience:
        failed_criteria.append('PROFILE_MUST_HAVE_1_PLACE_OF_WORK')
        details['work_experience_requirement'] = "Profile must have at least 1 place of work"
    
    is_valid = len(failed_criteria) == 0
    
    validation_result = {
        'is_valid': is_valid,
        'failed_criteria': failed_criteria,
        'details': details
    }
    
    return is_valid, validation_result


def verify_linkedin_profile_by_url(profile_url: str) -> Tuple[bool, Optional[Dict], Optional[Dict]]:
    """
    Fetch and verify LinkedIn profile by URL.
    
    Args:
        profile_url: LinkedIn profile URL
        
    Returns:
        Tuple of (is_valid: bool, profile_data: Optional[Dict], validation_result: Optional[Dict])
        If error occurred, returns (False, None, None)
    """
    profile_data = fetch_linkedin_profile_data(profile_url)
    
    if not profile_data:
        return False, None, {
            'is_valid': False,
            'failed_criteria': ['FAILED_TO_FETCH_PROFILE_DATA'],
            'details': {
                'error': 'Failed to fetch profile data from Apify'
            }
        }
    
    # Проверяем, не вернул ли Apify ошибку
    if isinstance(profile_data, dict) and '_apify_error' in profile_data:
        apify_error = profile_data.get('_apify_error', 'Unknown error')
        return False, None, {
            'is_valid': False,
            'failed_criteria': ['FAILED_TO_FETCH_PROFILE_DATA'],
            'details': {
                'error': apify_error
            }
        }
    
    is_valid, validation_result = verify_linkedin_profile(profile_data)
    
    return is_valid, profile_data, validation_result

