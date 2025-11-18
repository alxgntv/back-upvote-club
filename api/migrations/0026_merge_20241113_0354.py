from django.db import migrations
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0020_create_daily_tasks_subscription'),
        ('api', '0021_taskcompletion_twitter_url_and_unique'),
        ('api', '0024_taskcompletion_structure'),
        ('api', '0025_restore_taskcompletion_twitter_url'),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        logger.info("Applying merge migration for TaskCompletion model")
        return super().apply(project_state, schema_editor, collect_sql)

    operations = [
        # Пустые операции, так как это merge-миграция
    ]
