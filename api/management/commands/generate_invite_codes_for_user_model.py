from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import UserProfile, InviteCode
import uuid
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate invite codes for existing users without one'

    def handle(self, *args, **kwargs):
        users_without_invite_code = UserProfile.objects.filter(invite_code__isnull=True)
        
        for user_profile in users_without_invite_code:
            invite_code = InviteCode.objects.create(
                code=str(uuid.uuid4())[:8],
                creator=user_profile.user,
                status='ACTIVE',
                max_uses=0  # Устанавливаем 0 для бесконечного использования
            )
            user_profile.invite_code = invite_code
            user_profile.save()
            
            logger.info(f"Generated invite code {invite_code.code} for user {user_profile.user.username}")

        self.stdout.write(self.style.SUCCESS('Successfully generated invite codes for all users without one'))