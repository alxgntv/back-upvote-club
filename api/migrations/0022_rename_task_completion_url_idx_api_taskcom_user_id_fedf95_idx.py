from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0021_taskcompletion_twitter_url_and_unique'),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        logger.info("Creating index api_taskcom_user_id_fedf95_idx for TaskCompletion model")
        return super().apply(project_state, schema_editor, collect_sql)

    operations = [
        migrations.AddIndex(
            model_name='taskcompletion',
            index=models.Index(fields=['user'], name='api_taskcom_user_id_fedf95_idx'),
        ),
    ]