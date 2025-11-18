from django.db import migrations, models
import django.db.models.deletion
import logging

logger = logging.getLogger(__name__)

def fill_invited_by_from_invite_codes(apps, schema_editor):
    """Заполняем поле invited_by на основе существующих invite_code"""
    UserProfile = apps.get_model('api', 'UserProfile')
    InviteCode = apps.get_model('api', 'InviteCode')
    
    try:
        # Для каждого профиля с инвайт-кодом
        for profile in UserProfile.objects.filter(invite_code__isnull=False):
            try:
                # Получаем создателя инвайт-кода
                if profile.invite_code and profile.invite_code.creator:
                    profile.invited_by = profile.invite_code.creator
                    profile.save(update_fields=['invited_by'])
                    logger.info(f"[Migration] Set invited_by for user {profile.user_id} from invite code {profile.invite_code.code}")
            except Exception as e:
                logger.error(f"[Migration] Error processing user {profile.user_id}: {str(e)}")
    except Exception as e:
        logger.error(f"[Migration] General error: {str(e)}")

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0069_alter_task_deletion_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='invited_by',
            field=models.ForeignKey(
                blank=True,
                help_text='User who invited this user',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invited_users',
                to='auth.user'
            ),
        ),
        # Заполняем поле на основе существующих данных
        migrations.RunPython(fill_invited_by_from_invite_codes, reverse_code=migrations.RunPython.noop),
    ] 