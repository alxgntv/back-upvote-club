# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0110_remove_long_description_from_actionlanding'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlanding',
            name='faq_section_title',
            field=models.CharField(
                blank=True,
                help_text='Title for FAQ section',
                max_length=255,
                null=True,
                verbose_name='FAQ Section Title'
            ),
        ),
        migrations.AddField(
            model_name='actionlanding',
            name='reviews_section_title',
            field=models.CharField(
                blank=True,
                help_text='Title for Reviews section',
                max_length=255,
                null=True,
                verbose_name='Reviews Section Title'
            ),
        ),
    ]

