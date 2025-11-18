import csv
import json
import logging
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.utils import timezone
import os
from ...models import ActionLanding, SocialNetwork

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates ActionLanding entries from SEO CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        if not os.path.exists(csv_file):
            self.stderr.write(self.style.ERROR(f'[ERROR] CSV file not found: {csv_file}'))
            return
        
        # Получаем словарь социальных сетей
        social_networks = {
            network.code: network 
            for network in SocialNetwork.objects.all()
        }
        
        created_count = 0
        skipped_count = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                logger.info(f'[INFO] Starting to read CSV file: {csv_file}')
                reader = csv.DictReader(file)
                
                for row in reader:
                    # Проверяем, является ли страница лендингом
                    page_type = row.get('Page Type', '').lower()
                    if 'лендинг' not in page_type:
                        logger.info(f'[INFO] Skipping non-landing page: {row.get("og:title", "")}')
                        skipped_count += 1
                        continue

                    logger.info(f'[INFO] Processing row: {row.get("og:title", "")}')
                    
                    # Получаем основные поля
                    title = row.get('og:title', '').strip()
                    seo_url = row.get('SEO URL', '').strip()
                    social_network_code = row.get('Social Network', '').strip()
                    action = row.get('Action', '').strip()
                    description = row.get('og:description', '').strip()
                    
                    # Проверяем обязательные поля
                    if not title or not description:
                        logger.warning(f'[WARNING] Missing required fields (title or description) for row: {seo_url}')
                        skipped_count += 1
                        continue
                    
                    # Создаем slug из SEO URL или из заголовка, если URL пустой
                    slug = seo_url if seo_url else slugify(title)
                    
                    # Получаем объект социальной сети
                    social_network = social_networks.get(social_network_code)
                    if not social_network and social_network_code:
                        logger.warning(f'[WARNING] Social network not found: {social_network_code}')
                        skipped_count += 1
                        continue
                    
                    try:
                        # Создаем или обновляем запись
                        landing, created = ActionLanding.objects.update_or_create(
                            slug=slug,
                            defaults={
                                'title': title,
                                'social_network': social_network,
                                'action': action,
                                'short_description': description,
                                'long_description': self.generate_long_description(row),
                                'updated_at': timezone.now()
                            }
                        )
                        
                        if created:
                            created_count += 1
                            logger.info(f'[INFO] Created landing page: {slug} with title: {title}')
                        else:
                            logger.info(f'[INFO] Updated landing page: {slug} with title: {title}')
                            
                    except Exception as e:
                        logger.error(f'[ERROR] Failed to create/update landing page {slug}: {str(e)}')
                        skipped_count += 1
                        continue

            self.stdout.write(self.style.SUCCESS(
                f'[SUCCESS] Process completed. Created: {created_count}, Skipped: {skipped_count}'
            ))

        except Exception as e:
            logger.error(f'[ERROR] Failed to process CSV file: {str(e)}')
            self.stderr.write(self.style.ERROR(f'[ERROR] Failed to process CSV file: {str(e)}'))

    def generate_long_description(self, row):
        """Генерирует длинное описание из различных полей CSV"""
        content_parts = []
        
        # Добавляем описание кластера
        cluster_desc = row.get('Cluster Description', '').strip()
        if cluster_desc:
            content_parts.append(f'# Overview\n\n{cluster_desc}\n\n')
        
        # Добавляем описание страницы
        page_idea = row.get('Page Idea', '').strip()
        if page_idea:
            content_parts.append(f'# Purpose\n\n{page_idea}\n\n')
        
        # Добавляем поведение пользователя
        user_behavior = row.get('User Behavior', '').strip()
        if user_behavior:
            content_parts.append(f'# User Experience\n\n{user_behavior}\n\n')
        
        # Добавляем структуру статьи
        article_structure = row.get('Article Structure', '').split('\n')
        if article_structure:
            content_parts.append('# Article Structure\n\n')
            for section in article_structure:
                if section.strip():
                    # Убираем цифры и точки в начале строки
                    clean_section = section.strip().split('. ', 1)[-1]
                    content_parts.append(f'## {clean_section}\n\n')
        
        # Добавляем блоки страницы
        page_blocks = row.get('Page Blocks', '').split(',')
        if page_blocks:
            content_parts.append('# Page Components\n\n')
            for block in page_blocks:
                if block.strip():
                    content_parts.append(f'- {block.strip()}\n')
            content_parts.append('\n')
        
        return '\n'.join(content_parts) 