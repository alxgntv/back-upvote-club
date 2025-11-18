from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def update_daily_task_limits(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    
    # Словарь лимитов для каждого статуса
    DAILY_LIMITS = {
        'FREE': 2,
        'MEMBER': 2,
        'BUDDY': 10,
        'MATE': 10000
    }
    
    total_updated = 0
    for status, limit in DAILY_LIMITS.items():
        updated = UserProfile.objects.filter(status=status).update(
            daily_task_limit=limit,
            available_tasks=limit  # Также обновляем available_tasks
        )
        total_updated += updated
        logger.info(f"""Updated {status} users:
            Count: {updated}
            New daily limit: {limit}
            New available tasks: {limit}
        """)
    
    logger.info(f"Total profiles updated: {total_updated}")

def reverse_daily_task_limits(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    UserProfile.objects.all().update(daily_task_limit=0)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0035_add_task_original_price'),
    ]

    operations = [
        migrations.RunPython(
            update_daily_task_limits,
            reverse_code=reverse_daily_task_limits
        ),
    ]
