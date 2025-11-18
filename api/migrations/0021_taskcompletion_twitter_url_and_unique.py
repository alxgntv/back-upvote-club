from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

def cleanup_duplicates(apps, schema_editor):
    TaskCompletion = apps.get_model('api', 'TaskCompletion')
    Task = apps.get_model('api', 'Task')
    
    logger.info("Starting TaskCompletion cleanup")
    
    # Обновляем twitter_url из связанных задач
    for completion in TaskCompletion.objects.all():
        try:
            task = Task.objects.get(id=completion.task_id)
            completion.twitter_url = task.twitter_url
            completion.save()
            logger.info(f"Updated TaskCompletion {completion.id} with URL {task.twitter_url}")
        except Task.DoesNotExist:
            logger.error(f"Task not found for TaskCompletion {completion.id}")
    
    # Удаляем дубликаты
    duplicates = (
        TaskCompletion.objects
        .values('user_id', 'action', 'twitter_url')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
    )
    
    for duplicate in duplicates:
        completions = TaskCompletion.objects.filter(
            user_id=duplicate['user_id'],
            action=duplicate['action'],
            twitter_url=duplicate['twitter_url']
        ).order_by('completed_at')
        
        first = completions.first()
        if first:
            completions.exclude(id=first.id).delete()
            logger.info(f"Removed duplicates for user {duplicate['user_id']}, action {duplicate['action']}")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0019_task_completed_at_task_completion_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskcompletion',
            name='twitter_url',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.RunPython(cleanup_duplicates),
    ] 