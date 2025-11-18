import os
import json
from django.core.management.base import BaseCommand
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
from django.conf import settings
from api.models import ActionLanding
import logging
import time
from django.utils import timezone
from django.db.models import Q

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет URL\'ы лендингов в Google Indexing API для мгновенной индексации'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать URL\'ы без отправки в Google'
        )
        parser.add_argument(
            '--domain',
            type=str,
            default='https://upvote.club',
            help='Домен для URL\'ов (по умолчанию: https://upvote.club)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно отправить все URL\'ы, даже если они уже были проиндексированы'
        )

    def get_landings_to_index(self, force=False):
        """Получает список лендингов для индексации"""
        query = Q(is_indexed=False) | Q(indexing_error__isnull=False)
        
        if force:
            # Если force=True, берем все лендинги
            query = Q()
            
        return ActionLanding.objects.filter(query)

    def submit_url(self, service, landing, domain):
        """Отправляет один URL в Google Indexing API"""
        # Формируем URL по той же логике, что и в сериализаторе
        if not landing.social_network:
            url = f"{domain}/{landing.slug}"
        else:
            sn_code = landing.social_network.code.lower()
            if not landing.action:
                # Родительский лендинг соцсети
                if landing.slug == sn_code:
                    url = f"{domain}/{sn_code}"
                else:
                    url = f"{domain}/{sn_code}/{landing.slug}"
            else:
                action_code = landing.action.lower()
                expected_slug = f"{sn_code}-{action_code}"
                if landing.slug == expected_slug:
                    # Экшеновый лендинг
                    url = f"{domain}/{sn_code}/{action_code}"
                else:
                    # Обычный лендинг
                    url = f"{domain}/{sn_code}/{action_code}/{landing.slug}"
        
        try:
            # Если у лендинга есть redirect_url, отправляем на удаление
            if landing.redirect_url:
                response = service.urlNotifications().publish(
                    body={
                        'url': url,
                        'type': 'URL_DELETED'
                    }
                ).execute()
                logger.info(f"Successfully submitted for deletion: {url} (redirects to {landing.redirect_url})")
            else:
                # Обычная индексация
                response = service.urlNotifications().publish(
                    body={
                        'url': url,
                        'type': 'URL_UPDATED'
                    }
                ).execute()
                logger.info(f"Successfully indexed landing: {url}")
            
            # Если успешно, обновляем статус индексации
            landing.mark_as_indexed(success=True)
            
            return True, None
            
        except Exception as e:
            error_message = str(e)
            # Записываем ошибку в лендинг
            landing.mark_as_indexed(success=False, error_message=error_message)
            logger.error(f"Error submitting URL {url}: {error_message}")
            
            return False, error_message

    def handle(self, *args, **options):
        try:
            domain = options['domain'].rstrip('/')
            force = options['force']
            
            # Получаем лендинги для индексации
            landings = self.get_landings_to_index(force)
            total_landings = landings.count()
            
            if total_landings == 0:
                self.stdout.write("No landings to index")
                return
                
            self.stdout.write(f"Found {total_landings} landings to index")
            
            if options['dry_run']:
                self.stdout.write("\nURLs to be submitted:")
                for landing in landings:
                    # Формируем URL по той же логике, что и в сериализаторе
                    if not landing.social_network:
                        url = f"{domain}/{landing.slug}"
                    else:
                        sn_code = landing.social_network.code.lower()
                        if not landing.action:
                            # Родительский лендинг соцсети
                            if landing.slug == sn_code:
                                url = f"{domain}/{sn_code}"
                            else:
                                url = f"{domain}/{sn_code}/{landing.slug}"
                        else:
                            action_code = landing.action.lower()
                            expected_slug = f"{sn_code}-{action_code}"
                            if landing.slug == expected_slug:
                                # Экшеновый лендинг
                                url = f"{domain}/{sn_code}/{action_code}"
                            else:
                                # Обычный лендинг
                                url = f"{domain}/{sn_code}/{action_code}/{landing.slug}"
                    
                    # Показываем тип операции
                    if landing.redirect_url:
                        self.stdout.write(f"  DELETE: {url} (redirects to {landing.redirect_url})")
                    else:
                        self.stdout.write(f"  INDEX:  {url}")
                return

            # Загружаем учетные данные из env JSON (Heroku) или из файла (dev)
            if getattr(settings, 'GOOGLE_INDEXING_CREDENTIALS_INFO', None):
                credentials = service_account.Credentials.from_service_account_info(
                    settings.GOOGLE_INDEXING_CREDENTIALS_INFO,
                    scopes=['https://www.googleapis.com/auth/indexing']
                )
            else:
                credentials = service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_API_CREDENTIALS_PATH,
                    scopes=['https://www.googleapis.com/auth/indexing']
                )

            # Создаем сервис
            service = build('indexing', 'v3', credentials=credentials)

            success_count = 0
            error_count = 0

            # Отправляем URL'ы по одному с задержкой
            for i, landing in enumerate(landings, 1):
                success, error = self.submit_url(service, landing, domain)
                
                if success:
                    success_count += 1
                    action_type = "deleted" if landing.redirect_url else "indexed"
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[{i}/{total_landings}] Successfully {action_type}: {landing.slug}'
                        )
                    )
                else:
                    error_count += 1
                    action_type = "deleting" if landing.redirect_url else "indexing"
                    self.stdout.write(
                        self.style.ERROR(
                            f'[{i}/{total_landings}] Error {action_type} {landing.slug}: {error}'
                        )
                    )

                # Добавляем небольшую задержку между запросами
                if i < total_landings:
                    time.sleep(1)

            self.stdout.write(
                self.style.SUCCESS(
                    f'\nProcessing completed:\n'
                    f'Total processed: {total_landings}\n'
                    f'Successfully processed: {success_count}\n'
                    f'Errors: {error_count}'
                )
            )

        except Exception as e:
            logger.error(f"Error in submit_landings_to_google command: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            ) 