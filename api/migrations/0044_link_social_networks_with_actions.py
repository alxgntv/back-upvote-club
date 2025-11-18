from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def link_networks_with_actions(apps, schema_editor):
    SocialNetwork = apps.get_model('api', 'SocialNetwork')
    ActionType = apps.get_model('api', 'ActionType')
    
    # Словарь соответствия соц. сетей и их действий
    network_actions = {
        'TWITTER': ['LIKE', 'COMMENT', 'REPOST', 'FOLLOW', 'SAVE'],
        'BLUESKY': ['LIKE', 'COMMENT', 'REPOST', 'FOLLOW'],
        'DEVTO': ['LIKE', 'COMMENT', 'SAVE', 'FOLLOW', 'UNICORN'],
        'MASTODON': ['BOOST', 'FAVORITE', 'REPLY', 'FOLLOW', 'SAVE'],
        'MEDIUM': ['CLAP', 'COMMENT', 'FOLLOW', 'SAVE'],
        'SUBSTACK': ['RESTACK', 'COMMENT', 'SAVE', 'FOLLOW'],
        'PRODUCTHUNT': ['UPVOTE', 'FOLLOW', 'COMMENT'],
        'HACKERNEWS': ['UP', 'DOWN', 'COMMENT'],
        'QUORA': ['UPVOTE', 'DOWNVOTE', 'COMMENT', 'FOLLOW', 'SHARE'],
        'REDDIT': ['LIKE', 'COMMENT', 'SAVE', 'FOLLOW'],
        'LINKEDIN': ['LIKE', 'COMMENT', 'REPOST', 'CONNECT', 'SAVE'],
        'GITHUB': ['STAR', 'FOLLOW', 'WATCH'],
        'INDIEHACKERS': ['UP', 'DOWN', 'COMMENT'],
        'CHROMESOCIAL': ['COMMENT', 'INSTALL']
    }

    for network_code, action_codes in network_actions.items():
        try:
            network = SocialNetwork.objects.get(code=network_code)
            actions = ActionType.objects.filter(code__in=action_codes)
            
            # Очищаем существующие связи
            network.available_actions.clear()
            
            # Добавляем новые связи
            for action in actions:
                network.available_actions.add(action)
                logger.info(f"Added action {action.code} to network {network_code}")
                
        except SocialNetwork.DoesNotExist:
            logger.warning(f"Social network {network_code} not found")
        except Exception as e:
            logger.error(f"Error linking actions for {network_code}: {str(e)}")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0043_socialnetwork_available_actions'),
    ]

    operations = [
        migrations.RunPython(link_networks_with_actions),
    ]
