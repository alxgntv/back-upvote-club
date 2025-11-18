import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import OnboardingProgress
from api.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Выгружает все данные из OnboardingProgress, отправляет .csv на DEFAULT_FROM_EMAIL'

    def handle(self, *args, **options):
        self.stdout.write('Начинаю выгрузку данных из OnboardingProgress...')
        progresses = OnboardingProgress.objects.select_related('user').all()
        if not progresses:
            self.stdout.write(self.style.WARNING('Нет данных в OnboardingProgress.'))
            return

        # Формируем .csv
        csv_filename = 'onboarding_progress_export.csv'
        csv_path = os.path.join(settings.BASE_DIR, csv_filename)
        fieldnames = [
            'user_id', 'user_email', 'chosen_country', 'account_type', 'social_networks',
            'actions', 'goal_description', 'created_at', 'updated_at'
        ]
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for obj in progresses:
                    writer.writerow({
                        'user_id': obj.user.id,
                        'user_email': obj.user.email,
                        'chosen_country': obj.chosen_country or '',
                        'account_type': obj.account_type or '',
                        'social_networks': obj.social_networks if obj.social_networks is not None else '',
                        'actions': obj.actions if obj.actions is not None else '',
                        'goal_description': obj.goal_description or '',
                        'created_at': obj.created_at,
                        'updated_at': obj.updated_at,
                    })
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
        subject = 'Onboarding Progress Export'
        html_content = '<p>Выгрузка данных из OnboardingProgress во вложении.</p>'
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