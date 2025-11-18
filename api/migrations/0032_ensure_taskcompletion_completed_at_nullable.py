from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

def make_completed_at_nullable(apps, schema_editor):
    # Получаем историческую модель
    TaskCompletion = apps.get_model('api', 'TaskCompletion')
    
    # Создаем временную таблицу
    schema_editor.execute("""
        CREATE TABLE api_taskcompletion_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME NOT NULL,
            completed_at DATETIME NULL,
            task_id INTEGER NOT NULL REFERENCES api_task (id),
            user_id INTEGER NOT NULL REFERENCES auth_user (id),
            action VARCHAR(50) NOT NULL,
            twitter_url VARCHAR(200) NULL,
            metadata JSON NULL
        )
    """)
    
    # Копируем данные
    schema_editor.execute("""
        INSERT INTO api_taskcompletion_new 
        SELECT id, created_at, completed_at, task_id, user_id, action, twitter_url, metadata
        FROM api_taskcompletion
    """)
    
    # Удаляем старую таблицу
    schema_editor.execute("DROP TABLE api_taskcompletion")
    
    # Переименовываем новую таблицу
    schema_editor.execute("ALTER TABLE api_taskcompletion_new RENAME TO api_taskcompletion")
    
    logger.info("[Migration] Successfully made completed_at nullable")

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0031_fix_taskcompletion_created_at_final'),
    ]

    operations = [
        migrations.RunPython(make_completed_at_nullable, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='taskcompletion',
            name='completed_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]