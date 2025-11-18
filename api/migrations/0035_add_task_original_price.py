from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

def backfill_original_price(apps, schema_editor):
    Task = apps.get_model('api', 'Task')
    UserProfile = apps.get_model('api', 'UserProfile')
    
    logger.info("Starting backfill of original prices for existing tasks")
    
    # Словарь скидок
    DISCOUNT_RATES = {
        'FREE': 0,
        'MEMBER': 0,
        'BUDDY': 20,
        'MATE': 40
    }
    
    tasks_updated = 0
    for task in Task.objects.select_related('creator__userprofile').iterator():
        try:
            status = task.creator.userprofile.status
            discount = DISCOUNT_RATES.get(status, 0)
            
            if discount > 0:
                # Если была скидка, восстанавливаем оригинальную цену
                original_price = int(task.price / (1 - discount/100))
            else:
                original_price = task.price
                
            task.original_price = original_price
            task.save(update_fields=['original_price'])
            tasks_updated += 1
            
            if tasks_updated % 1000 == 0:
                logger.info(f"Updated {tasks_updated} tasks with original prices")
                
        except Exception as e:
            logger.error(f"Error updating task {task.id}: {str(e)}")
    
    logger.info(f"Completed backfill of original prices. Total tasks updated: {tasks_updated}")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0034_update_free_users_limit'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='original_price',
            field=models.IntegerField(null=True),
        ),
        migrations.RunPython(
            backfill_original_price,
            reverse_code=migrations.RunPython.noop
        ),
        # После заполнения данных делаем поле обязательным
        migrations.AlterField(
            model_name='task',
            name='original_price',
            field=models.IntegerField(),
        ),
    ]
