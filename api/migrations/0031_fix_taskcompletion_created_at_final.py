from django.db import migrations, models
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0030_fix_taskcompletion_created_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskcompletion',
            name='created_at',
            field=models.DateTimeField(default=timezone.now),
        ),
    ]