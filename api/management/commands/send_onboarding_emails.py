from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.utils.email_utils import send_onboarding_email, get_firebase_email
from api.models import EmailSubscriptionType, UserEmailSubscription, UserProfile
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет онбординг email всем существующим пользователям'

    def add_arguments(self, parser):
        parser.add_argument('--test', action='store_true', help='Send test email only to first user')
        parser.add_argument('--delay', type=int, default=1, help='Delay between emails in seconds')

    def handle(self, *args, **options):
        start_time = datetime.now()
        is_test = options['test']
        delay = options['delay']

        try:
            # Получаем или создаем тип подписки для онбординга
            subscription_type, created = EmailSubscriptionType.objects.get_or_create(
                name='complete_registration',
                defaults={'description': 'Registration completion reminders'}
            )
            
            logger.info(f"Using subscription type: {subscription_type.name}")

            # Получаем всех пользователей с профилями
            users = User.objects.filter(is_active=True)
            
            if is_test:
                users = users[:1]
                self.stdout.write(self.style.WARNING('Running in test mode - sending only to first user'))

            total_users = users.count()
            successful = 0
            failed = 0

            self.stdout.write(f"Starting onboarding email campaign to {total_users} users")
            logger.info(f"Starting onboarding email campaign. Total users: {total_users}")

            for user in users:
                try:
                    # Получаем email из Firebase
                    firebase_uid = user.username
                    user_email = get_firebase_email(firebase_uid)
                    
                    if not user_email:
                        logger.error(f"Could not get Firebase email for user {user.username}")
                        failed += 1
                        continue

                    # Проверяем/создаем профиль пользователя
                    user_profile, created = UserProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'status': 'FREE',
                            'balance': 0
                        }
                    )
                    
                    if created:
                        logger.info(f"Created new profile for user {user.username}")

                    # Создаем подписку если её нет
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=subscription_type,
                        defaults={'is_subscribed': True}
                    )

                    if not subscription.is_subscribed:
                        logger.info(f"Skipping unsubscribed user: {user.username}")
                        continue

                    # Отправляем онбординг email
                    result = send_onboarding_email(user)

                    if result:
                        successful += 1
                        logger.info(f"""
                            Email sent successfully:
                            Firebase UID: {user.username}
                            Email: {user_email}
                            Profile status: {user_profile.status}
                        """)
                        self.stdout.write(f"Successfully sent to {user_email}")
                    else:
                        failed += 1
                        logger.error(f"""
                            Failed to send email:
                            Firebase UID: {user.username}
                            Email: {user_email}
                            Profile status: {user_profile.status}
                        """)
                        self.stdout.write(self.style.WARNING(f"Failed to send to {user_email}"))

                    if delay > 0:
                        time.sleep(delay)

                except Exception as e:
                    failed += 1
                    logger.error(f"Error processing user {user.username}: {str(e)}")
                    self.stdout.write(self.style.ERROR(f"Error processing user {user.username}: {str(e)}"))

            end_time = datetime.now()
            duration = end_time - start_time

            summary = f"""
            Onboarding Email Campaign Summary:
            ------------------------------
            Total users: {total_users}
            Successful: {successful}
            Failed: {failed}
            Duration: {duration}
            """
            
            self.stdout.write(self.style.SUCCESS(summary))
            logger.info(f"Onboarding email campaign completed. {summary}")

        except Exception as e:
            logger.error(f"Campaign failed: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Campaign failed: {str(e)}"))