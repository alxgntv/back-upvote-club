from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

def create_initial_data(apps, schema_editor):
    ActionType = apps.get_model('api', 'ActionType')
    SocialNetwork = apps.get_model('api', 'SocialNetwork')
    
    # Создаем все типы действий
    action_types = {
        'LIKE': 'Like',
        'COMMENT': 'Comment',
        'REPOST': 'Repost',
        'REPLY': 'Reply',
        'FOLLOW': 'Follow',
        'SAVE': 'Save',
        'UPVOTE': 'Upvote',
        'DOWNVOTE': 'Downvote',
        'STAR': 'Star',
        'WATCH': 'Watch',
        'CLAP': 'Clap',
        'CONNECT': 'Connect',
        'SUBSCRIBE': 'Subscribe',
        'RESTACK': 'Restack',
        'UP': 'Up',
        'DOWN': 'Down',
        'INSTALL': 'Install',
        'UNICORN': 'Unicorn',
        'FAVORITE': 'Favorite',
        'BOOST': 'Boost',
        'SHARE': 'Share'
    }
    
    for code, name in action_types.items():
        ActionType.objects.create(
            name=name,
            code=code
        )
        logger.info(f"Created action type: {code}")

    # Связываем действия с существующими соц. сетями
    social_network_actions = {
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

    for network_code, action_codes in social_network_actions.items():
        try:
            network = SocialNetwork.objects.get(code=network_code)
            actions = ActionType.objects.filter(code__in=action_codes)
            network.available_actions.set(actions)
            logger.info(f"Added actions for {network_code}: {action_codes}")
        except SocialNetwork.DoesNotExist:
            logger.warning(f"Social network {network_code} not found")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0039_twitterserviceaccount'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Action Type',
                'verbose_name_plural': 'Action Types',
            },
        ),
        migrations.AddField(
            model_name='socialnetwork',
            name='available_actions',
            field=models.ManyToManyField(related_name='social_networks', to='api.actiontype'),
        ),
        migrations.RunPython(create_initial_data),
    ]
