from django.db import migrations

def update_member_task_limits(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    
    # Обновляем лимиты для MEMBER пользователей
    updated = UserProfile.objects.filter(status='MEMBER').update(
        available_tasks=2,
        daily_task_limit=2
    )

def reverse_member_task_limits(apps, schema_editor):
    UserProfile = apps.get_model('api', 'UserProfile')
    
    # Возвращаем старые значения
    UserProfile.objects.filter(status='MEMBER').update(
        available_tasks=1,
        daily_task_limit=1
    )

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0033_add_auto_actions'),
    ]

    operations = [
        migrations.RunPython(
            update_member_task_limits,
            reverse_code=reverse_member_task_limits
        ),
    ]