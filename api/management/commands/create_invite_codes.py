from django.core.management.base import BaseCommand
from api.models import UserProfile, InviteCode
import logging
import uuid

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates unlimited invite codes for all existing users who don\'t have one'

    def handle(self, *args, **options):
        logger.info("Starting creation of invite codes for existing users")
        
        # Получаем всех пользователей
        user_profiles = UserProfile.objects.select_related('user').all()
        total_users = user_profiles.count()
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        self.stdout.write(f"Found {total_users} total users")
        
        for profile in user_profiles:
            try:
                # Проверяем, есть ли уже активный инвайт-код
                existing_invite = InviteCode.objects.filter(
                    creator=profile.user,
                    status='ACTIVE'
                ).first()
                
                if existing_invite:
                    logger.info(f"User {profile.user.username} already has active invite code: {existing_invite.code}")
                    skipped_count += 1
                    continue
                
                # Создаем новый безлимитный инвайт-код
                invite_code = InviteCode.objects.create(
                    code=str(uuid.uuid4())[:8],
                    creator=profile.user,
                    status='ACTIVE',
                    max_uses=0  # Безлимитный
                )
                
                logger.info(f"Created unlimited invite code: {invite_code.code} for user: {profile.user.username}")
                created_count += 1
                
            except Exception as e:
                logger.error(f"Error creating invite code for user {profile.user.username}: {str(e)}")
                error_count += 1
        
        summary = f"""
        Invite codes creation completed:
        Total users processed: {total_users}
        New codes created: {created_count}
        Users skipped (already had codes): {skipped_count}
        Errors encountered: {error_count}
        """
        
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))
