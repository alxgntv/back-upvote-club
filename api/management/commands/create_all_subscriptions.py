from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import EmailSubscriptionType, UserEmailSubscription
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates all subscription types for all existing users'

    def handle(self, *args, **options):
        logger.info("Starting creation of all subscription types for existing users")
        
        # Получаем всех активных пользователей
        users = User.objects.filter(is_active=True)
        total_users = users.count()
        
        logger.info(f"Found {total_users} active users")
        subscriptions_created = 0
        
        # Получаем все типы подписок
        subscription_types = EmailSubscriptionType.objects.all()
        logger.info(f"Found {subscription_types.count()} subscription types")
        
        # Для каждого пользователя создаем все типы подписок
        for user in users:
            logger.info(f"Processing user: {user.username}")
            
            for subscription_type in subscription_types:
                subscription, created = UserEmailSubscription.objects.get_or_create(
                    user=user,
                    subscription_type=subscription_type,
                    defaults={'is_subscribed': True}
                )
                
                if created:
                    subscriptions_created += 1
                    logger.info(f"Created {subscription_type.name} subscription for user {user.username}")
                else:
                    logger.info(f"Subscription {subscription_type.name} already exists for user {user.username}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Email subscriptions creation completed:\n"
                f"Total users processed: {total_users}\n"
                f"Total subscriptions created: {subscriptions_created}"
            )
        )
