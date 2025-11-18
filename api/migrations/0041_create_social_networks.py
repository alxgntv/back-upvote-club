from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def create_social_networks(apps, schema_editor):
    SocialNetwork = apps.get_model('api', 'SocialNetwork')
    
    networks = [
        {
            'name': 'Twitter',
            'code': 'TWITTER',
            'icon': 'twitter',
            'is_active': True
        },
        {
            'name': 'Bluesky',
            'code': 'BLUESKY',
            'icon': 'bluesky',
            'is_active': True
        },
        {
            'name': 'Dev.to',
            'code': 'DEVTO',
            'icon': 'devto',
            'is_active': True
        },
        {
            'name': 'Mastodon',
            'code': 'MASTODON',
            'icon': 'mastodon',
            'is_active': True
        },
        {
            'name': 'Medium',
            'code': 'MEDIUM',
            'icon': 'medium',
            'is_active': True
        },
        {
            'name': 'Substack',
            'code': 'SUBSTACK',
            'icon': 'substack',
            'is_active': True
        },
        {
            'name': 'Product Hunt',
            'code': 'PRODUCTHUNT',
            'icon': 'producthunt',
            'is_active': True
        },
        {
            'name': 'Hacker News',
            'code': 'HACKERNEWS',
            'icon': 'hackernews',
            'is_active': True
        },
        {
            'name': 'Quora',
            'code': 'QUORA',
            'icon': 'quora',
            'is_active': True
        },
        {
            'name': 'Reddit',
            'code': 'REDDIT',
            'icon': 'reddit',
            'is_active': True
        },
        {
            'name': 'LinkedIn',
            'code': 'LINKEDIN',
            'icon': 'linkedin',
            'is_active': True
        },
        {
            'name': 'GitHub',
            'code': 'GITHUB',
            'icon': 'github',
            'is_active': True
        },
        {
            'name': 'IndieHackers',
            'code': 'INDIEHACKERS',
            'icon': 'indiehackers',
            'is_active': True
        },
        {
            'name': 'Chrome Social',
            'code': 'CHROMESOCIAL',
            'icon': 'chrome',
            'is_active': True
        }
    ]
    
    for network_data in networks:
        network, created = SocialNetwork.objects.get_or_create(
            code=network_data['code'],
            defaults={
                'name': network_data['name'],
                'icon': network_data['icon'],
                'is_active': network_data['is_active']
            }
        )
        logger.info(f"Social network {'created' if created else 'already exists'}: {network.code}")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0040_create_action_types'),
    ]

    operations = [
        migrations.RunPython(create_social_networks),
    ]
