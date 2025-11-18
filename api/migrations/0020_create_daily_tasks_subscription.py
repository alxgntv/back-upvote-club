from django.db import migrations

def create_subscription_type(apps, schema_editor):
    EmailSubscriptionType = apps.get_model('api', 'EmailSubscriptionType')
    EmailSubscriptionType.objects.get_or_create(
        name='daily_tasks',
        defaults={
            'description': 'Daily notifications about available tasks'
        }
    )

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0019_task_completed_at_task_completion_duration'),
    ]

    operations = [
        migrations.RunPython(create_subscription_type),
    ]