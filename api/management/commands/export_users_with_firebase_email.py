import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth.models import User
from firebase_admin import auth
from api.models import UserProfile
from api.email_service import EmailService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Экспортирует всех пользователей из UserProfile с email из Firebase и пометкой об отключенных email. Отправляет CSV на DEFAULT_FROM_EMAIL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            help='Ограничить количество экспортируемых пользователей (для тестирования)'
        )
        parser.add_argument(
            '--skip-email',
            action='store_true',
            help='Не отправлять email, только создать CSV файл'
        )

    def handle(self, *args, **options):
        self.stdout.write('Начинаю выгрузку пользователей с Firebase email...')
        
        # Получаем все профили пользователей
        profiles = UserProfile.objects.select_related('user', 'invited_by', 'invite_code').all()
        
        limit = options.get('limit')
        if limit:
            profiles = profiles[:limit]
            self.stdout.write(f'Ограничение: экспортирую только {limit} пользователей')
        
        total_count = profiles.count()
        self.stdout.write(f'Найдено пользователей для экспорта: {total_count}')
        
        if total_count == 0:
            self.stdout.write(self.style.WARNING('Пользователи не найдены.'))
            return
        
        # Создаем CSV файл
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_filename = f'users_export_{timestamp}.csv'
        csv_path = os.path.join(settings.BASE_DIR, csv_filename)
        
        count = 0
        error_count = 0
        disabled_count = 0
        
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Заголовки CSV
                headers = [
                    'User ID',
                    'Firebase UID (Username)',
                    'Firebase Email',
                    'Email Disabled in Firebase',
                    'Email Verified',
                    'User Status',
                    'Country Code',
                    'Chosen Country',
                    'Balance',
                    'Available Tasks',
                    'Completed Tasks Count',
                    'Is Ambassador',
                    'Is Affiliate Partner',
                    'Black Friday Subscribed',
                    'Auto Actions Enabled',
                    'Twitter Account',
                    'Twitter Verification Status',
                    'Referrer URL',
                    'Landing URL',
                    'Device Type',
                    'OS Name',
                    'OS Version',
                    'Created At',
                ]
                writer.writerow(headers)
                
                # Обрабатываем каждого пользователя
                for index, profile in enumerate(profiles, 1):
                    try:
                        user = profile.user
                        firebase_uid = user.username
                        
                        # Получаем данные из Firebase
                        firebase_email = ''
                        email_disabled = False
                        email_verified = False
                        firebase_error = ''
                        
                        if firebase_uid:
                            try:
                                firebase_user = auth.get_user(firebase_uid)
                                firebase_email = firebase_user.email or ''
                                email_disabled = firebase_user.disabled if hasattr(firebase_user, 'disabled') else False
                                email_verified = firebase_user.email_verified if hasattr(firebase_user, 'email_verified') else False
                                
                                if email_disabled:
                                    disabled_count += 1
                                    
                            except auth.UserNotFoundError:
                                firebase_error = 'User not found in Firebase'
                                logger.warning(f"[export_users] Firebase user not found: {firebase_uid}")
                            except Exception as e:
                                firebase_error = f'Error: {str(e)[:50]}'
                                logger.error(f"[export_users] Error getting Firebase user {firebase_uid}: {str(e)}")
                        
                        # Если email отключен, добавляем пометку
                        email_display = firebase_email
                        if email_disabled:
                            email_display = f"{firebase_email} [DISABLED - DO NOT SEND EMAIL]"
                        elif firebase_error:
                            email_display = f"[ERROR: {firebase_error}]"
                        
                        # Формируем строку данных
                        row = [
                            user.id,
                            firebase_uid,
                            email_display,
                            'YES' if email_disabled else 'NO',
                            'YES' if email_verified else 'NO',
                            profile.status or '',
                            profile.country_code or '',
                            profile.chosen_country or '',
                            profile.balance or 0,
                            profile.available_tasks or 0,
                            profile.completed_tasks_count or 0,
                            'YES' if profile.is_ambassador else 'NO',
                            'YES' if profile.is_affiliate_partner else 'NO',
                            'YES' if profile.black_friday_subscribed else 'NO',
                            'YES' if profile.auto_actions_enabled else 'NO',
                            profile.twitter_account or '',
                            profile.twitter_verification_status or '',
                            profile.referrer_url or '',
                            profile.landing_url or '',
                            profile.device_type or '',
                            profile.os_name or '',
                            profile.os_version or '',
                            user.date_joined.strftime('%Y-%m-%d %H:%M:%S') if user.date_joined else '',
                        ]
                        
                        writer.writerow(row)
                        count += 1
                        
                        # Показываем прогресс каждые 100 пользователей
                        if index % 100 == 0:
                            self.stdout.write(f'Обработано: {index}/{total_count} пользователей...')
                        
                    except Exception as e:
                        error_count += 1
                        logger.error(f"[export_users] Error exporting user profile {getattr(profile, 'id', '?')}: {str(e)}")
                        continue
                
            self.stdout.write(self.style.SUCCESS(f'CSV файл создан: {csv_path}'))
            self.stdout.write(f'Успешно экспортировано: {count} пользователей')
            self.stdout.write(f'Найдено отключенных email: {disabled_count}')
            if error_count > 0:
                self.stdout.write(self.style.WARNING(f'Ошибок при экспорте: {error_count}'))
                
        except Exception as e:
            logger.error(f'Ошибка при создании CSV: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Ошибка при создании CSV: {str(e)}'))
            return
        
        # Отправляем email с вложением (если не указан флаг --skip-email)
        if not options.get('skip_email'):
            email_service = EmailService()
            to_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            if not to_email:
                self.stdout.write(self.style.ERROR('DEFAULT_FROM_EMAIL не задан в настройках!'))
                self.stdout.write(f'CSV файл сохранен локально: {csv_path}')
                return
            
            subject = f'Users Export with Firebase Email - {timestamp}'
            html_content = f'''
                <p>Выгрузка пользователей с Firebase email во вложении.</p>
                <p><strong>Статистика:</strong></p>
                <ul>
                    <li>Всего экспортировано: {count}</li>
                    <li>Отключенных email: {disabled_count}</li>
                    <li>Ошибок: {error_count}</li>
                </ul>
                <p><strong>Внимание:</strong> Email с пометкой [DISABLED - DO NOT SEND EMAIL] не должны использоваться для рассылок!</p>
            '''
            
            try:
                with open(csv_path, 'rb') as f:
                    csv_content = f.read()
                attachments = [(csv_filename, csv_content, 'text/csv')]
                
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
                    self.stdout.write(f'CSV файл сохранен локально: {csv_path}')
            except Exception as e:
                logger.error(f'Ошибка при отправке email: {str(e)}')
                self.stdout.write(self.style.ERROR(f'Ошибка при отправке email: {str(e)}'))
                self.stdout.write(f'CSV файл сохранен локально: {csv_path}')
        else:
            self.stdout.write(self.style.SUCCESS('Пропущена отправка email (--skip-email)'))
            self.stdout.write(f'CSV файл сохранен: {csv_path}')
        
        # Удаляем файл после отправки (только если email был отправлен успешно)
        if not options.get('skip_email'):
            try:
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                    self.stdout.write('Временный CSV файл удалён.')
            except Exception as e:
                logger.warning(f'Не удалось удалить временный файл: {str(e)}')
                self.stdout.write(self.style.WARNING(f'Не удалось удалить временный файл: {str(e)}'))
        
        logger.info(f"[export_users] Exported {count} user profiles to CSV (disabled: {disabled_count}, errors: {error_count})")

