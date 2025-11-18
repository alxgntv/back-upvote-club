from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0026_merge_20241113_0354'),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        logger.info("Adding metadata field to TaskCompletion model")
        return super().apply(project_state, schema_editor, collect_sql)

    operations = [
        migrations.AddField(
            model_name='taskcompletion',
            name='metadata',
            field=models.JSONField(blank=True, null=True),
        ),
    ] 