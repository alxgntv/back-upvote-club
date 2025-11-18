from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import EmailSubscriptionType, UserEmailSubscription
import logging
import uuid

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Subscribe users to new task notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Subscribe only test user (your UID) for testing'
        )
        parser.add_argument(
            '--test-uid',
            type=str,
            help='Firebase UID for test user'
        )

    def handle(self, *args, **options):
        try:
            # Получаем или создаем тип подписки
            subscription_type, created = EmailSubscriptionType.objects.get_or_create(
                name='new_task',
                defaults={
                    'description': 'Notifications about new tasks available on the platform',
                    'created_at': '2024-01-01T00:00:00Z'
                }
            )

            if created:
                logger.info("Created new subscription type: new_task")
            else:
                logger.info("Found existing subscription type: new_task")

            # Определяем пользователей для подписки
            if options['test_mode']:
                if not options['test_uid']:
                    logger.error("Test UID is required in test mode")
                    return
                users = User.objects.filter(username=options['test_uid'])
                logger.info(f"Test mode enabled, subscribing only user with UID: {options['test_uid']}")
            else:
                users = User.objects.filter(is_active=True)
                logger.info("Production mode, subscribing all active users")

            total_users = users.count()
            subscribed = 0
            skipped = 0

            for user in users:
                try:
                    # Проверяем, существует ли уже подписка
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=subscription_type,
                        defaults={
                            'is_subscribed': True,
                            'unsubscribe_token': str(uuid.uuid4())
                        }
                    )

                    if created:
                        subscribed += 1
                        logger.info(f"Subscribed user {user.username} to new task notifications")
                    else:
                        skipped += 1
                        logger.info(f"User {user.username} already subscribed to new task notifications")

                except Exception as e:
                    logger.error(f"Error subscribing user {user.username}: {str(e)}")

            logger.info(f"""
                Subscription process completed:
                Total users processed: {total_users}
                Successfully subscribed: {subscribed}
                Already subscribed/skipped: {skipped}
                Mode: {'Test' if options['test_mode'] else 'Production'}
            """)

        except Exception as e:
            logger.error(f"General error in subscribe_users_to_new_task_emails: {str(e)}") 