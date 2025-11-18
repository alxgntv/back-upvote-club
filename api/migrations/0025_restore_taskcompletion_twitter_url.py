from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0024_taskcompletion_structure'),
    ]

    operations = [
        # Восстанавливаем поле twitter_url
        migrations.AddField(
            model_name='taskcompletion',
            name='twitter_url',
            field=models.CharField(max_length=200, null=True, blank=True),
        ),
    ] 