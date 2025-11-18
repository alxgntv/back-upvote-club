#!/usr/bin/env python3
"""
Test script for URL normalization functionality
Tests various corner cases for social network URLs
"""
import os
import sys
import django

# Add the backend directory to Python path
sys.path.append('/Users/alexign/Desktop/BB/backend')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')
django.setup()

from api.utils.url_normalizer import URLNormalizer

def test_url_normalization():
    """Test URL normalization with various corner cases"""
    
    print("=== Testing URL Normalization ===\n")
    
    # Test cases for different social networks
    test_cases = [
        # Twitter/X variations
        {
            'name': 'Twitter/X URL variations',
            'urls': [
                'https://twitter.com/username/status/1234567890',
                'https://x.com/username/status/1234567890',
                'https://www.twitter.com/username/status/1234567890',
                'https://www.x.com/username/status/1234567890',
                'https://twitter.com/username/status/1234567890?ref_src=twsrc%5Etfw',
                'https://x.com/username/status/1234567890?utm_source=twitter&utm_medium=web',
            ],
            'expected_fingerprint': 'https://twitter.com/username/status/1234567890|LIKE|TWITTER'
        },
        
        # Instagram variations
        {
            'name': 'Instagram URL variations',
            'urls': [
                'https://instagram.com/p/ABC123/',
                'https://www.instagram.com/p/ABC123/',
                'https://instagram.com/p/ABC123/?utm_source=ig_web',
                'https://www.instagram.com/p/ABC123/?igshid=xyz123',
            ],
            'expected_fingerprint': 'https://instagram.com/p/ABC123|LIKE|INSTAGRAM'
        },
        
        # YouTube variations
        {
            'name': 'YouTube URL variations',
            'urls': [
                'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'https://youtube.com/watch?v=dQw4w9WgXcQ',
                'https://youtu.be/dQw4w9WgXcQ',
                'https://www.youtu.be/dQw4w9WgXcQ',
                'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s',
                'https://youtu.be/dQw4w9WgXcQ?t=10',
            ],
            'expected_fingerprint': 'https://youtube.com/watch?v=dQw4w9WgXcQ|LIKE|YOUTUBE'
        },
        
        # TikTok variations
        {
            'name': 'TikTok URL variations',
            'urls': [
                'https://www.tiktok.com/@username/video/1234567890',
                'https://tiktok.com/@username/video/1234567890',
                'https://www.tiktok.com/@username/video/1234567890?is_from_webapp=1',
            ],
            'expected_fingerprint': 'https://tiktok.com/@username/video/1234567890|LIKE|TIKTOK'
        },
        
        # LinkedIn variations
        {
            'name': 'LinkedIn URL variations',
            'urls': [
                'https://www.linkedin.com/posts/activity-1234567890',
                'https://linkedin.com/posts/activity-1234567890',
                'https://www.linkedin.com/posts/activity-1234567890-abc123/',
            ],
            'expected_fingerprint': 'https://linkedin.com/posts/activity-1234567890|LIKE|LINKEDIN'
        },
        
        # Facebook variations
        {
            'name': 'Facebook URL variations',
            'urls': [
                'https://www.facebook.com/posts/1234567890',
                'https://facebook.com/posts/1234567890',
                'https://fb.com/posts/1234567890',
                'https://www.fb.com/posts/1234567890',
            ],
            'expected_fingerprint': 'https://facebook.com/posts/1234567890|LIKE|FACEBOOK'
        },
        
        # Reddit variations
        {
            'name': 'Reddit URL variations',
            'urls': [
                'https://www.reddit.com/r/programming/comments/abc123/',
                'https://reddit.com/r/programming/comments/abc123/',
                'https://www.reddit.com/r/programming/comments/abc123/?utm_source=share',
            ],
            'expected_fingerprint': 'https://reddit.com/r/programming/comments/abc123|LIKE|REDDIT'
        },
        
        # Pinterest variations
        {
            'name': 'Pinterest URL variations',
            'urls': [
                'https://www.pinterest.com/pin/1234567890/',
                'https://pinterest.com/pin/1234567890/',
                'https://pin.it/abc123',
                'https://www.pin.it/abc123',
            ],
            'expected_fingerprint': 'https://pinterest.com/pin/1234567890|LIKE|PINTEREST'
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"Testing {test_case['name']}:")
        print("-" * 50)
        
        fingerprints = []
        for url in test_case['urls']:
            fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'TWITTER')
            if 'TWITTER' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'TWITTER')
            elif 'INSTAGRAM' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'INSTAGRAM')
            elif 'YOUTUBE' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'YOUTUBE')
            elif 'TIKTOK' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'TIKTOK')
            elif 'LINKEDIN' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'LINKEDIN')
            elif 'FACEBOOK' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'FACEBOOK')
            elif 'REDDIT' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'REDDIT')
            elif 'PINTEREST' in test_case['name']:
                fingerprint = URLNormalizer.get_url_fingerprint(url, 'LIKE', 'PINTEREST')
            
            fingerprints.append(fingerprint)
            print(f"  {url}")
            print(f"  -> {fingerprint}")
        
        # Check if all fingerprints are the same
        unique_fingerprints = set(fingerprints)
        if len(unique_fingerprints) == 1:
            print(f"  ✅ PASS: All URLs normalized to same fingerprint")
        else:
            print(f"  ❌ FAIL: URLs normalized to different fingerprints:")
            for fp in unique_fingerprints:
                print(f"    - {fp}")
            all_passed = False
        
        print()
    
    # Test URL equivalence
    print("=== Testing URL Equivalence ===\n")
    
    equivalence_tests = [
        ('https://twitter.com/user/status/123', 'https://x.com/user/status/123'),
        ('https://www.youtube.com/watch?v=abc123', 'https://youtu.be/abc123'),
        ('https://instagram.com/p/ABC123/', 'https://www.instagram.com/p/ABC123/'),
        ('https://facebook.com/posts/123', 'https://fb.com/posts/123'),
    ]
    
    for url1, url2 in equivalence_tests:
        are_equivalent = URLNormalizer.are_urls_equivalent(url1, url2)
        status = "✅ PASS" if are_equivalent else "❌ FAIL"
        print(f"{status}: {url1} <-> {url2}")
    
    print()
    
    # Test different task types with same URL
    print("=== Testing Different Task Types ===\n")
    
    test_url = "https://twitter.com/user/status/1234567890"
    task_types = ['LIKE', 'REPOST', 'COMMENT', 'FOLLOW']
    
    for task_type in task_types:
        fingerprint = URLNormalizer.get_url_fingerprint(test_url, task_type, 'TWITTER')
        print(f"{task_type}: {fingerprint}")
    
    print()
    
    # Summary
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    return all_passed

if __name__ == "__main__":
    test_url_normalization()
