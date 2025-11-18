from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import UserEmailSubscription, EmailSubscriptionType
from api.email_service import EmailService
from django.template.loader import render_to_string
from django.conf import settings
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет массовую рассылку всем зарегистрированным пользователям'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, help='Email subject')
        parser.add_argument('--template', type=str, help='Path to email template')
        parser.add_argument('--test', action='store_true', help='Send test email only to first user')
        parser.add_argument('--delay', type=int, default=1, help='Delay between emails in seconds')

    def handle(self, *args, **options):
        start_time = datetime.now()
        subject = options['subject']
        template_path = options['template']
        is_test = options['test']
        delay = options['delay']

        if not subject or not template_path:
            self.stdout.write(self.style.ERROR('Subject and template path are required'))
            return

        try:
            # Создаем тип рассылки
            subscription_type, created = EmailSubscriptionType.objects.get_or_create(
                name='mass_email',
                defaults={'description': 'Mass email campaigns'}
            )

            # Получаем всех пользователей с email
            users = User.objects.exclude(email='').filter(is_active=True)
            
            if is_test:
                users = users[:1]
                self.stdout.write(self.style.WARNING('Running in test mode - sending only to first user'))

            total_users = users.count()
            successful = 0
            failed = 0

            self.stdout.write(f"Starting email campaign to {total_users} users")
            logger.info(f"Starting mass email campaign. Subject: {subject}, Total users: {total_users}")

            email_service = EmailService()

            for user in users:
                try:
                    # Проверяем/создаем подписку для пользователя
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=subscription_type,
                        defaults={'is_subscribed': True}
                    )

                    if not subscription.is_subscribed:
                        logger.info(f"Skipping unsubscribed user: {user.email}")
                        continue

                    unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"

                    # Подготавливаем контекст для шаблона
                    context = {
                        'user': user,
                        'site_url': settings.SITE_URL,
                        'unsubscribe_url': unsubscribe_url,
                    }

                    # Рендерим HTML контент
                    html_content = render_to_string(template_path, context)

                    # Отправляем email
                    result = email_service.send_email(
                        to_email=user.email,
                        subject=subject,
                        html_content=html_content,
                        unsubscribe_url=unsubscribe_url
                    )

                    if result:
                        successful += 1
                        self.stdout.write(f"Successfully sent to {user.email}")
                    else:
                        failed += 1
                        self.stdout.write(self.style.WARNING(f"Failed to send to {user.email}"))

                    # Добавляем задержку между отправками
                    if delay > 0:
                        time.sleep(delay)

                except Exception as e:
                    failed += 1
                    logger.error(f"Error sending to {user.email}: {str(e)}")
                    self.stdout.write(self.style.ERROR(f"Error sending to {user.email}: {str(e)}"))

            end_time = datetime.now()
            duration = end_time - start_time

            # Выводим итоговую статистику
            summary = f"""
            Email Campaign Summary:
            ---------------------
            Total users: {total_users}
            Successful: {successful}
            Failed: {failed}
            Duration: {duration}
            """
            
            self.stdout.write(self.style.SUCCESS(summary))
            logger.info(f"Mass email campaign completed. {summary}")

        except Exception as e:
            logger.error(f"Campaign failed: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Campaign failed: {str(e)}"))
