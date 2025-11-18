from django.db import migrations, models
import django.utils.timezone
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0026_merge_20241113_0354'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskcompletion',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]