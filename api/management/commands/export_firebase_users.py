import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from firebase_admin import auth
from api.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Выгружает email и first name всех пользователей из Firebase, отправляет .csv на DEFAULT_FROM_EMAIL'

    def handle(self, *args, **options):
        self.stdout.write('Начинаю выгрузку пользователей из Firebase...')
        users = []
        try:
            page = auth.list_users()
            while page:
                for user in page.users:
                    users.append({
                        'email': getattr(user, 'email', ''),
                        'first_name': getattr(user, 'display_name', '') or ''
                    })
                page = page.get_next_page() if hasattr(page, 'get_next_page') else None
        except Exception as e:
            logger.error(f'Ошибка при получении пользователей из Firebase: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Ошибка при получении пользователей из Firebase: {str(e)}'))
            return

        if not users:
            self.stdout.write(self.style.WARNING('Пользователи не найдены.'))
            return

        # Формируем .csv
        csv_filename = 'firebase_users_export.csv'
        csv_path = os.path.join(settings.BASE_DIR, csv_filename)
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['email', 'first_name'])
                writer.writeheader()
                for user in users:
                    writer.writerow(user)
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
        subject = 'Firebase Users Export'
        html_content = '<p>Выгрузка пользователей из Firebase во вложении.</p>'
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