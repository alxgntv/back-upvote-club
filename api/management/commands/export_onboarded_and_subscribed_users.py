import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import OnboardingProgress, PaymentTransaction
from api.email_service import EmailService
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Выгружает пользователей, прошедших онбординг и оформивших триал или подписку в тот же день. Присылает .csv на DEFAULT_FROM_EMAIL.'

    def handle(self, *args, **options):
        self.stdout.write('Начинаю поиск пользователей, прошедших онбординг и оформивших триал/подписку в тот же день...')
        # Получаем все онбординги
        progresses = OnboardingProgress.objects.select_related('user').all()
        result = []
        for onboarding in progresses:
            user = onboarding.user
            # Ищем транзакции с типом SUBSCRIPTION и статусом TRIAL или ACTIVE в тот же день
            same_day_transactions = PaymentTransaction.objects.filter(
                user=user,
                payment_type='SUBSCRIPTION',
                status__in=['TRIAL', 'ACTIVE'],
                created_at__date=onboarding.created_at.date()
            ).order_by('created_at')
            if same_day_transactions.exists():
                for tx in same_day_transactions:
                    result.append({
                        'user_id': user.id,
                        'user_email': user.email,
                        'onboarding_date': onboarding.created_at,
                        'subscription_date': tx.created_at,
                        'subscription_status': tx.status,
                        'subscription_amount': tx.amount,
                        'subscription_id': tx.id,
                    })
        if not result:
            self.stdout.write(self.style.WARNING('Нет пользователей, прошедших онбординг и оформивших триал/подписку в тот же день.'))
            return
        # Формируем .csv
        csv_filename = 'onboarded_and_subscribed_users.csv'
        csv_path = os.path.join(settings.BASE_DIR, csv_filename)
        fieldnames = [
            'user_id', 'user_email', 'onboarding_date', 'subscription_date',
            'subscription_status', 'subscription_amount', 'subscription_id'
        ]
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in result:
                    writer.writerow(row)
            self.stdout.write(self.style.SUCCESS(f'CSV файл создан: {csv_path}'))
        except Exception as e:
            logger.error(f'Ошибка при создании CSV: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Ошибка при создании CSV: {str(e)}'))
            return
        # Отправляем email с вложением
        email_service = EmailService()
        to_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not to_email:
            self.stdout.write(self.style.ERROR('DEFAULT_FROM_EMAIL не задан в настройках!'))
            return
        subject = 'Onboarded & Subscribed Users Export'
        html_content = '<p>Список пользователей, прошедших онбординг и оформивших триал/подписку в тот же день, во вложении.</p>'
        attachments = [(csv_filename, open(csv_path, 'rb').read(), 'text/csv')]
        success = email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            attachments=attachments
        )
        if success:
            self.stdout.write(self.style.SUCCESS(f'Email с выгрузкой отправлен на {to_email}'))
        else:
            self.stdout.write(self.style.ERROR('Ошибка при отправке email с выгрузкой!'))
        # Удаляем файл после отправки
        try:
            os.remove(csv_path)
            self.stdout.write('Временный CSV файл удалён.')
        except Exception as e:
            logger.warning(f'Не удалось удалить временный файл: {str(e)}')
            self.stdout.write(self.style.WARNING(f'Не удалось удалить временный файл: {str(e)}')) 