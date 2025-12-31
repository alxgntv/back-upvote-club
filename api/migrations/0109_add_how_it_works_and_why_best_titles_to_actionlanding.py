# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0108_remove_page_type_and_page_blocks_from_actionlanding'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlanding',
            name='how_it_works_title',
            field=models.CharField(
                blank=True,
                help_text='Title for "How It Works" section',
                max_length=255,
                null=True,
                verbose_name='How It Works Title'
            ),
        ),
        migrations.AddField(
            model_name='actionlanding',
            name='why_upvote_club_best_title',
            field=models.CharField(
                blank=True,
                help_text='Title for "Why Upvote Club Best" section',
                max_length=255,
                null=True,
                verbose_name='Why Upvote Club Best Title'
            ),
        ),
    ]

