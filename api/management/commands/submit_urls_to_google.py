import os
import json
from django.core.management.base import BaseCommand
from google.oauth2 import service_account
from googleapiclient.discovery import build
from django.conf import settings
from api.models import SocialNetwork, ActionType
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет URL\'ы страниц в Google Indexing API для мгновенной индексации'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать URL\'ы без отправки в Google'
        )
        parser.add_argument(
            '--domain',
            type=str,
            default=(getattr(settings, 'FRONTEND_URL', None) or 'https://upvote.club'),
            help='Домен для URL\'ов (по умолчанию берётся из settings.FRONTEND_URL, иначе https://upvote.club)'
        )

    def get_urls_to_index(self, domain):
        """Получает все возможные комбинации URL'ов для индексации"""
        urls = []
        base_url = domain.rstrip('/')

        # Получаем все активные социальные сети
        social_networks = SocialNetwork.objects.filter(is_active=True).prefetch_related('available_actions')

        for network in social_networks:
            # Добавляем основной URL соц. сети
            network_url = f"{base_url}/{network.code.lower()}"
            urls.append(network_url)
            logger.info(f"Added network URL: {network_url}")

            # Добавляем URL'ы для каждого доступного действия
            for action in network.available_actions.all():
                action_url = f"{base_url}/{network.code.lower()}/{action.code.lower()}"
                urls.append(action_url)
                logger.info(f"Added action URL: {action_url}")

        return urls

    def submit_url(self, service, url):
        """Отправляет один URL в Google Indexing API"""
        try:
            response = service.urlNotifications().publish(
                body={
                    'url': url,
                    'type': 'URL_UPDATED'
                }
            ).execute()
            
            logger.info(f"URL submission response for {url}: {response}")
            return response
        except Exception as e:
            logger.error(f"Error submitting URL {url}: {str(e)}")
            raise

    def handle(self, *args, **options):
        try:
            domain = options['domain']
            # Получаем все URL'ы для индексации
            urls = self.get_urls_to_index(domain)
            
            if options['dry_run']:
                self.stdout.write("URLs to be submitted:")
                for url in urls:
                    self.stdout.write(f"  {url}")
                self.stdout.write(f"\nTotal URLs: {len(urls)}")
                return

            # Загружаем учетные данные из JSON-файла
            credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_API_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/indexing']
            )

            # Создаем сервис
            service = build('indexing', 'v3', credentials=credentials)

            # Отправляем URL'ы по одному с задержкой
            for i, url in enumerate(urls, 1):
                try:
                    self.submit_url(service, url)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Successfully submitted URL {i}/{len(urls)}: {url}'
                        )
                    )
                    # Добавляем небольшую задержку между запросами
                    if i < len(urls):
                        time.sleep(1)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error submitting URL {url}: {str(e)}'
                        )
                    )
                    continue

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully submitted all {len(urls)} URLs to Google Indexing API'
                )
            )

        except Exception as e:
            logger.error(f"Error in submit_urls_to_google command: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            ) 