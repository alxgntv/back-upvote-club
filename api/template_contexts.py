from django.conf import settings

EMAIL_TEMPLATE_CONTEXTS = {
    'task_completed': {
        'template_path': 'email/task_completed.html',
        'context': {
            'task': {
                'type': 'LIKE',
                'price': 100,
                'actions_required': 5,
                'twitter_url': 'https://twitter.com/example/status/123',
            },
            'reward': 50,
            'new_balance': 150,
            'completion_time': '2 hours 15 minutes',
            'site_url': settings.SITE_URL,
            'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/test-token/"
        }
    },
    'daily_tasks': {
        'template_path': 'email/daily_tasks.html',
        'context': {
            'tasks': [
                {
                    'type': 'Like Tweet',
                    'price': 100,
                    'twitter_url': 'https://twitter.com/example1/status/123',
                    'post_url': 'https://twitter.com/example1/status/123'
                },
                {
                    'type': 'Repost Tweet',
                    'price': 200,
                    'twitter_url': 'https://twitter.com/example2/status/456',
                    'post_url': 'https://twitter.com/example2/status/456'
                }
            ],
            'site_url': settings.SITE_URL,
            'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/test-token/"
        }
    },
    'complete_registration': {
        'template_path': 'email/complete_registration.html',
        'context': {
            'username': 'Test User',
            'missing_steps': [
                'Verify Twitter account',
                'Complete profile information'
            ],
            'registration_link': f"{settings.SITE_URL}/complete-registration/",
            'time_left': '48 hours',
            'site_url': settings.SITE_URL,
            'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/test-token/"
        }
    },
    'weekly_digest': {
        'template_path': 'email/weekly_digest.html',
        'context': {
            'stats': {
                'tasks_completed': 15,
                'total_earned': 750,
                'average_completion_time': '1.5 hours',
                'most_profitable_day': 'Wednesday',
                'total_tasks_created': 5,
                'total_tasks_earnings': 300
            },
            'top_tasks': [
                {
                    'type': 'LIKE',
                    'earnings': 200,
                    'completion_rate': '95%'
                },
                {
                    'type': 'REPOST',
                    'earnings': 150,
                    'completion_rate': '85%'
                }
            ],
            'week_dates': {
                'start': '2024-01-01',
                'end': '2024-01-07'
            },
            'site_url': settings.SITE_URL,
            'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/test-token/"
        }
    }
}