from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task
from django.db.models import Count, Q
import logging
from api.email_service import EmailService
from django.template.loader import render_to_string
from django.conf import settings
from firebase_admin import auth
from urllib.parse import urlparse, urlunparse, parse_qs
import re

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Detects and processes duplicate tasks from different users with the same post URL'

    def normalize_url(self, url):

        try:
            logger.info(f"[detect_duplicate_tasks] Normalizing URL: {url}")
            
            # Парсим URL
            parsed = urlparse(url.lower())
            
            # Убираем www из домена
            netloc = parsed.netloc
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            
            # Убираем trailing slash из пути
            path = parsed.path.rstrip('/')
            
            # Собираем нормализованный URL без параметров
            normalized_url = urlunparse((
                parsed.scheme,
                netloc,
                path,
                parsed.params,
                '',  # Убираем query parameters
                parsed.fragment
            ))
            
            logger.info(f"[detect_duplicate_tasks] Normalized URL: {normalized_url}")
            return normalized_url
            
        except Exception as e:
            logger.error(f"[detect_duplicate_tasks] Error normalizing URL {url}: {str(e)}")
            return url.lower()  # Fallback - просто приводим к нижнему регистру

    def handle(self, *args, **options):
        try:
            logger.info("[detect_duplicate_tasks] Starting duplicate detection process")
            
            # Получаем все задания (не только ACTIVE) для определения первого пользователя
            all_tasks = Task.objects.exclude(status='DELETED')
            
            # Получаем активные задания для обработки
            active_tasks = Task.objects.filter(status='ACTIVE')
            
            # Создаем словарь для определения первого пользователя по URL (все задания)
            first_user_by_url = {}
            
            # Определяем первого пользователя для каждого URL (по всем заданиям)
            for task in all_tasks:
                normalized_url = self.normalize_url(task.post_url)
                
                if normalized_url not in first_user_by_url:
                    first_user_by_url[normalized_url] = {
                        'user': task.creator,
                        'task': task,
                        'created_at': task.created_at
                    }
                else:
                    # Если нашли задание раньше по дате, обновляем
                    if task.created_at < first_user_by_url[normalized_url]['created_at']:
                        first_user_by_url[normalized_url] = {
                            'user': task.creator,
                            'task': task,
                            'created_at': task.created_at
                        }
            
            # Группируем активные задания по URL
            active_tasks_by_url = {}
            for task in active_tasks:
                normalized_url = self.normalize_url(task.post_url)
                
                if normalized_url not in active_tasks_by_url:
                    active_tasks_by_url[normalized_url] = []
                
                active_tasks_by_url[normalized_url].append(task)
            
            total_processed = 0
            email_service = EmailService()
            
            # Обрабатываем группы с дубликатами среди активных заданий
            for normalized_url, tasks in active_tasks_by_url.items():
                if len(tasks) > 1:
                    logger.info(f"[detect_duplicate_tasks] Found {len(tasks)} active tasks with normalized URL: {normalized_url}")
                    
                    # Проверяем, что все активные задания от разных пользователей
                    unique_users = set(task.creator.id for task in tasks)
                    if len(unique_users) == 1:
                        logger.info(f"[detect_duplicate_tasks] All {len(tasks)} active tasks for URL {normalized_url} belong to the same user {tasks[0].creator.username}, skipping (same user is allowed to have multiple tasks)")
                        continue
                    
                    # Получаем первого пользователя из истории всех заданий (включая COMPLETED)
                    if normalized_url not in first_user_by_url:
                        logger.warning(f"[detect_duplicate_tasks] No first user found for URL {normalized_url}, skipping")
                        continue
                    
                    first_user_info = first_user_by_url[normalized_url]
                    first_user = first_user_info['user']
                    
                    logger.info(f"[detect_duplicate_tasks] First user for URL {normalized_url}: {first_user.username} (from task {first_user_info['task'].id}, created at {first_user_info['created_at']})")
                    
                    # Находим все активные задания от других пользователей (не от первого)
                    duplicate_tasks = []
                    for task in tasks:
                        if task.creator.id != first_user.id:
                            duplicate_tasks.append(task)
                    
                    if duplicate_tasks:
                        logger.info(f"[detect_duplicate_tasks] Found {len(duplicate_tasks)} tasks from other users that will be deleted")
                        
                        for task in duplicate_tasks:
                            try:
                                # Получаем email пользователя из Firebase
                                firebase_user = auth.get_user(task.creator.username)
                                user_email = firebase_user.email
                                
                                if not user_email:
                                    logger.error(f"[detect_duplicate_tasks] No email found in Firebase for user {task.creator.username}")
                                    continue
                                
                                # Меняем статус на DELETED и указываем причину
                                task.status = 'DELETED'
                                task.deletion_reason = 'DOUBLE_ACCOUNT'
                                task.save()
                                
                                logger.info(f"[detect_duplicate_tasks] Marked task {task.id} as deleted for user {task.creator.username} (not the first user)")
                                
                                # Возвращаем баланс пользователю
                                creator_profile = task.creator.userprofile
                                total_task_cost = task.actions_required * task.price
                                completed_cost = task.actions_completed * task.price
                                refund_amount = total_task_cost - completed_cost
                                
                                if refund_amount > 0:
                                    creator_profile.balance += refund_amount
                                    creator_profile.save()
                                    
                                
                                # Отправляем email
                                email_text = "<p>Hello, dear user.</p><p>This is the Upvote Club team. We truly appreciate that you enjoy our service and want to use it to promote your articles. However, our rules prohibit creating multiple accounts to promote the same profile. While this is technically possible, we monitor such attempts.</p><p>Therefore, we have remove your new tasks, but we have not blocked your old account so that you can continue using it freely.</p><p>If you wish to create multiple tasks, we recommend subscribing to our membership plan, which costs two times less than a Cup of coffee from Starbucks.</p><p>Thank you for your interest in Upvote Club!</p>"
                                
                                success = email_service.send_email(
                                    to_email=user_email,
                                    subject='Your task has been deleted & points returned to your balance',
                                    html_content=email_text
                                )
                                
                                task.log_email_status(success, None if success else "Error sending email")
                                
                                if success:
                                    logger.info(f"[detect_duplicate_tasks] Successfully sent deletion email for task {task.id} to {user_email}")
                                else:
                                    logger.warning(f"[detect_duplicate_tasks] Failed to send deletion email for task {task.id} to {user_email}")
                                
                                total_processed += 1
                                
                            except Exception as e:
                                logger.error(f"[detect_duplicate_tasks] Error processing duplicate task {task.id}: {str(e)}")
                                continue

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully processed {total_processed} duplicate tasks'
                )
            )
            
            logger.info(f"[detect_duplicate_tasks] Completed processing {total_processed} duplicate tasks")

        except Exception as e:
            logger.error(f"[detect_duplicate_tasks] Error in command execution: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error executing command: {str(e)}')
            ) 