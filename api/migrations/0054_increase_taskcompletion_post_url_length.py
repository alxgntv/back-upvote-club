from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0053_increase_post_url_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskcompletion',
            name='post_url',
            field=models.CharField(max_length=1000, null=True, blank=True),
        ),
    ] 