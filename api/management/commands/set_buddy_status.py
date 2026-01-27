from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import UserProfile
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Set Buddy status for specific account if it is Free'

    def handle(self, *args, **options):
        firebase_uid = 'JXUSHCwLTHVDCPAivRh8HlMqfac2'
        
        try:
            user_profile = UserProfile.objects.select_related('user').get(
                user__username=firebase_uid
            )
            
            if user_profile.status == 'FREE':
                old_status = user_profile.status
                user_profile.status = 'BUDDY'
                user_profile.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Status updated for user {firebase_uid}: {old_status} -> BUDDY at {timezone.now()}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'User {firebase_uid} already has status: {user_profile.status}. No changes made.'
                    )
                )
                
        except UserProfile.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'User profile not found for Firebase UID: {firebase_uid}'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error updating status: {str(e)}'
                )
            )
