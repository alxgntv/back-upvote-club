# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0107_add_reviews_and_content_fields_to_actionlanding'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='actionlanding',
            name='page_type',
        ),
        migrations.RemoveField(
            model_name='actionlanding',
            name='page_blocks',
        ),
    ]

