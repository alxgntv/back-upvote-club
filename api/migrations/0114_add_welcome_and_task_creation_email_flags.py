from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0113_buylanding_reviews'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='welcome_email_sent',
            field=models.BooleanField(
                default=False,
                help_text='Whether welcome/confirmation email was sent',
                verbose_name='Welcome email sent'
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='welcome_email_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp when welcome/confirmation email was sent',
                null=True,
                verbose_name='Welcome email sent at'
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='creation_email_sent',
            field=models.BooleanField(
                default=False,
                help_text='Whether task creation email was sent',
                verbose_name='Creation email sent'
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='creation_email_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp when task creation email was sent',
                null=True,
                verbose_name='Creation email sent at'
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='creation_email_send_error',
            field=models.TextField(
                blank=True,
                help_text='Last error while sending creation email',
                null=True,
                verbose_name='Creation email send error'
            ),
        ),
    ]

