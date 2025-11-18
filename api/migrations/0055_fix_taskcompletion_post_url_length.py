from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0054_increase_taskcompletion_post_url_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskcompletion',
            name='post_url',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ] 