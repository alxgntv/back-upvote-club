from django.db import migrations
from django.utils import timezone
from django.db import models

def update_user_profiles(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    
    # Обновляем лимиты заданий для всех пользователей
    for profile in UserProfile.objects.all():
        # Устанавливаем лимиты в зависимости от статуса
        if profile.status == 'FREE':
            profile.available_tasks = 2
            profile.daily_task_limit = 2
        elif profile.status == 'MEMBER':
            profile.available_tasks = 2
            profile.daily_task_limit = 2
        elif profile.status == 'BUDDY':
            profile.available_tasks = 10
            profile.daily_task_limit = 10
        elif profile.status == 'MATE':
            profile.available_tasks = 10000
            profile.daily_task_limit = 10000
            
        profile.last_tasks_update = timezone.now()
        profile.save()

def cleanup_duplicate_twitter_accounts(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    
    # Находим все дубликаты twitter_account
    duplicates = (
        UserProfile.objects
        .exclude(twitter_account__isnull=True)
        .values('twitter_account')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
    )
    
    # Очищаем дубликаты
    for duplicate in duplicates:
        twitter_account = duplicate['twitter_account']
        profiles = UserProfile.objects.filter(twitter_account=twitter_account).order_by('id')
        
        # Оставляем первый профиль, у остальных очищаем twitter_account
        first_profile = profiles.first()
        if first_profile:
            profiles.exclude(id=first_profile.id).update(
                twitter_account=None,
                twitter_verification_status='NOT_CONFIRMED'
            )

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0016_rename_tasks_created_today_userprofile_daily_task_limit_and_more'),
    ]

    operations = [
        # Сначала очищаем дубликаты Twitter-аккаунтов
        migrations.RunPython(cleanup_duplicate_twitter_accounts),
        
        # Добавляем ограничение уникальности для twitter_account
        migrations.AlterField(
            model_name='userprofile',
            name='twitter_account',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        
        # Обновляем лимиты заданий
        migrations.RunPython(update_user_profiles),
    ]