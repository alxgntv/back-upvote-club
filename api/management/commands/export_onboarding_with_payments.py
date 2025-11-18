import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import OnboardingProgress, PaymentTransaction, Task
from api.email_service import EmailService
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Выгружает данные из OnboardingProgress с добавлением всех PaymentTransaction по user_id и первой задачи (соцсеть, экшен, время выполнения) в CSV и отправляет на email.'

    def handle(self, *args, **options):
        self.stdout.write('Начинаю выгрузку данных из OnboardingProgress, PaymentTransaction и Tasks...')
        progresses = OnboardingProgress.objects.select_related('user').all()
        if not progresses:
            self.stdout.write(self.style.WARNING('Нет данных в OnboardingProgress.'))
            return

        # Получаем все поля PaymentTransaction
        payment_fields = [f.name for f in PaymentTransaction._meta.fields]
        # Поля из OnboardingProgress + новые
        onboarding_fields = [
            'user_id', 'user_email', 'chosen_country', 'account_type', 'social_networks',
            'actions', 'created_at', 'first_task_social_network', 'first_task_action', 'first_task_completion_duration'
        ]
        # Итоговые поля для CSV
        fieldnames = onboarding_fields + payment_fields

        csv_filename = 'onboarding_with_payments_export.csv'
        csv_path = os.path.join(settings.BASE_DIR, csv_filename)
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for obj in progresses:
                    user = obj.user
                    # Поиск первой задачи
                    first_task = Task.objects.filter(creator=user).order_by('created_at').first()
                    if first_task:
                        social_network = first_task.social_network.name if first_task.social_network else ''
                        action = first_task.type or ''
                        completion_duration = str(first_task.completion_duration) if first_task.completion_duration else ''
                    else:
                        social_network = ''
                        action = ''
                        completion_duration = ''
                    onboarding_row = {
                        'user_id': user.id,
                        'user_email': user.email,
                        'chosen_country': obj.chosen_country or '',
                        'account_type': obj.account_type or '',
                        'social_networks': obj.social_networks if obj.social_networks is not None else '',
                        'actions': obj.actions if obj.actions is not None else '',
                        'created_at': obj.created_at,
                        'first_task_social_network': social_network,
                        'first_task_action': action,
                        'first_task_completion_duration': completion_duration,
                    }
                    # Получаем все платежи пользователя
                    payments = PaymentTransaction.objects.filter(user=user)
                    if payments.exists():
                        for payment in payments:
                            payment_row = {f: getattr(payment, f) for f in payment_fields}
                            row = {**onboarding_row, **payment_row}
                            writer.writerow(row)
                    else:
                        # Если платежей нет, пишем только онбординг
                        row = {**onboarding_row}
                        for f in payment_fields:
                            row[f] = ''
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
        subject = 'Onboarding With Payments Export'
        html_content = '<p>Выгрузка данных из OnboardingProgress + PaymentTransaction во вложении.</p>'
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