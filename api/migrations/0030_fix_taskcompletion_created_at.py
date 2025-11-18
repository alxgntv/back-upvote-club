from django.db import migrations, models
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def backfill_created_at(apps, schema_editor):
    TaskCompletion = apps.get_model('api', 'TaskCompletion')
    
    # Заполняем created_at для существующих записей
    for completion in TaskCompletion.objects.filter(created_at__isnull=True):
        # Если есть completed_at, используем его, иначе текущее время
        completion.created_at = completion.completed_at or timezone.now()
        completion.save()
        logger.info(f"[Migration] Set created_at for TaskCompletion {completion.id} to {completion.created_at}")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0029_merge_20241113_0435'),
    ]

    operations = [
        # Сначала заполняем существующие null значения
        migrations.RunPython(backfill_created_at, reverse_code=migrations.RunPython.noop),
        
        # Затем изменяем поле, делая его обязательным с значением по умолчанию
        migrations.AlterField(
            model_name='taskcompletion',
            name='created_at',
            field=models.DateTimeField(default=timezone.now),
        ),
    ]