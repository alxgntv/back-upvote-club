from django.db import migrations
import logging
import time
from tweepy import Client
from django.conf import settings
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def update_follow_tasks(apps, schema_editor):
    Task = apps.get_model('api', 'Task')
    TwitterUserMapping = apps.get_model('api', 'TwitterUserMapping')
    UserProfile = apps.get_model('api', 'UserProfile')

    # Получаем все FOLLOW задания без target_user_id
    tasks = Task.objects.filter(
        type='FOLLOW',
        target_user_id__isnull=True,
        status='ACTIVE'
    )

    logger.info(f"Found {tasks.count()} FOLLOW tasks without target_user_id")

    # Берем первый рабочий токен из UserProfile
    profile = UserProfile.objects.filter(
        twitter_verification_status='CONFIRMED',
        twitter_oauth_token__isnull=False
    ).first()

    if not profile:
        logger.error("No verified Twitter profiles found for migration")
        return

    client = Client(
        bearer_token=os.environ.get('TWITTER_BEARER_TOKEN'),
        consumer_key=os.environ.get('TWITTER_CONSUMER_KEY'),
        consumer_secret=os.environ.get('TWITTER_CONSUMER_SECRET'),
        access_token=profile.twitter_oauth_token,
        access_token_secret=profile.twitter_oauth_token_secret
    )

    for task in tasks:
        try:
            username = task.twitter_url.split('/')[-1]
            
            # Проверяем существующий маппинг
            mapping = TwitterUserMapping.objects.filter(username=username).first()
            if mapping:
                task.target_user_id = mapping.twitter_id
                task.save()
                logger.info(f"Updated task {task.id} with cached Twitter ID {mapping.twitter_id}")
                continue

            # Делаем запрос к API
            response = client.get_user(username=username)
            
            if response and response.data:
                user_id = str(response.data.id)
                
                # Сохраняем маппинг
                TwitterUserMapping.objects.create(
                    username=username,
                    twitter_id=user_id
                )
                
                # Обновляем задание
                task.target_user_id = user_id
                task.save()
                
                logger.info(f"""
                    Updated task:
                    Task ID: {task.id}
                    Username: {username}
                    Twitter ID: {user_id}
                """)
                
                # Ждем чтобы не превысить лимиты
                time.sleep(60)  # 1 минута между запросами
            else:
                logger.error(f"Could not get Twitter ID for task {task.id}, username: {username}")

        except Exception as e:
            logger.error(f"""
                Error updating task {task.id}:
                Error: {str(e)}
                URL: {task.twitter_url}
            """)
            # Продолжаем со следующим заданием
            continue

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0045_task_target_user_id_twitterusermapping'),  # Укажите предыдущую миграцию
    ]

    operations = [
        migrations.RunPython(update_follow_tasks, reverse_code=migrations.RunPython.noop),
    ]
