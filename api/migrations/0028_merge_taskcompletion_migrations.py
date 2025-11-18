from django.db import migrations
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0027_add_taskcompletion_metadata'),
        ('api', '0027_taskcompletion_created_at_default'),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        logger.info("Applying merge migration for TaskCompletion metadata and created_at")
        return super().apply(project_state, schema_editor, collect_sql)

    operations = [
        # Пустые операции, так как это merge-миграция
    ] 