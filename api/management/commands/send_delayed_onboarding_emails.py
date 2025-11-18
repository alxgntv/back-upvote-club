from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import logging
from ...utils.email_utils import send_onboarding_email

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends onboarding emails to users who registered within last hour'

    def handle(self, *args, **options):
        try:
            # Получаем пользователей, зарегистрированных за последний час
            one_hour_ago = timezone.now() - timedelta(hours=1)
            users = User.objects.filter(
                date_joined__gte=one_hour_ago,
                is_active=True
            )

            logger.info(f"Found {users.count()} users registered in the last hour")

            successful = 0
            failed = 0

            for user in users:
                try:
                    logger.info(f"Attempting to send delayed onboarding email to user {user.username}")
                    result = send_onboarding_email(user)
                    
                    if result:
                        successful += 1
                        logger.info(f"Successfully sent delayed onboarding email to user {user.username}")
                    else:
                        failed += 1
                        logger.error(f"Failed to send delayed onboarding email to user {user.username}")

                except Exception as e:
                    failed += 1
                    logger.error(f"Error processing user {user.username}: {str(e)}")

            logger.info(f"""
                Delayed Onboarding Email Summary:
                Total users found: {users.count()}
                Successfully sent: {successful}
                Failed: {failed}
                Time range: {one_hour_ago} to {timezone.now()}
            """)

        except Exception as e:
            logger.error(f"Error in send_delayed_onboarding_emails command: {str(e)}")
