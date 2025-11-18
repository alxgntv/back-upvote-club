from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ...utils.email_utils import send_daily_tasks_email
from ...template_contexts import EMAIL_TEMPLATE_CONTEXTS
from ...models import EmailSubscriptionType, UserEmailSubscription
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test email sending functionality'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email address to send test email to')
        parser.add_argument(
            '--template',
            type=str,
            default='daily_tasks',
            choices=EMAIL_TEMPLATE_CONTEXTS.keys(),
            help='Template to use for test email'
        )

    def handle(self, *args, **options):
        email = options['email']
        template_name = options['template']
        
        logger.info(f"""
            Starting test email sending:
            Template: {template_name}
            Email: {email}
        """)

        try:
            # Получаем или создаем тестового пользователя
            user, created = User.objects.get_or_create(
                email=email,
                defaults={'username': email.split('@')[0]}
            )

            # Получаем или создаем тип подписки
            subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
                name=template_name,
                defaults={
                    'description': f'Subscription for {template_name} emails'
                }
            )

            # Создаем подписку для пользователя
            UserEmailSubscription.objects.get_or_create(
                user=user,
                subscription_type=subscription_type,
                defaults={'is_subscribed': True}
            )

            template_info = EMAIL_TEMPLATE_CONTEXTS.get(template_name)
            if send_daily_tasks_email(user, template_info['context']['tasks']):
                self.stdout.write(self.style.SUCCESS(f'Successfully sent {template_name} email to {email}'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed to send email to {email}'))

        except Exception as e:
            logger.error(f'Error in test_email command: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))