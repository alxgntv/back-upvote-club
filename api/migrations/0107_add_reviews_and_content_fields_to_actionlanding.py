# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0106_add_assigned_to_crowd_task'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlanding',
            name='reviews',
            field=models.ManyToManyField(
                blank=True,
                help_text='Select reviews to display on this landing page',
                related_name='action_landings',
                to='api.review',
                verbose_name='Reviews'
            ),
        ),
        migrations.AddField(
            model_name='actionlanding',
            name='how_it_works',
            field=models.JSONField(
                blank=True,
                help_text='JSON structure with text and image keys for "How It Works" section',
                null=True,
                verbose_name='How It Works'
            ),
        ),
        migrations.AddField(
            model_name='actionlanding',
            name='why_upvote_club_best',
            field=models.JSONField(
                blank=True,
                help_text='JSON structure with text and image keys for "Why Upvote Club Best" section',
                null=True,
                verbose_name='Why Upvote Club Best'
            ),
        ),
    ]

