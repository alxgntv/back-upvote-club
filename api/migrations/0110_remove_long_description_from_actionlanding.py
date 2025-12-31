# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0109_add_how_it_works_and_why_best_titles_to_actionlanding'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='actionlanding',
            name='long_description',
        ),
    ]

