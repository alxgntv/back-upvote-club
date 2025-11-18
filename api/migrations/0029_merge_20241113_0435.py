from django.db import migrations
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0027_add_taskcompletion_metadata'),
        ('api', '0027_taskcompletion_created_at_default'),
        ('api', '0028_merge_taskcompletion_migrations'),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        logger.info("[Migration] Applying merge migration for TaskCompletion metadata and created_at fields")
        return super().apply(project_state, schema_editor, collect_sql)

    operations = [
        # Пустые операции, так как это merge-миграция
    ]