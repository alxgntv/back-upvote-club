from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import UserProfile, Task
from api.utils.email_utils import send_daily_tasks_email
import logging
import time
from firebase_admin import auth
from django.db import models
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send daily tasks emails to users with available tasks'

    def get_firebase_email(self, firebase_uid):
        try:
            user = auth.get_user(firebase_uid)
            return user.email
        except Exception as e:
            logger.error(f"Error getting Firebase email for UID {firebase_uid}: {str(e)}")
            return None

    def get_available_tasks(self):
        """Получает список всех доступных заданий"""
        try:
            # Получаем все активные и незавершенные задания
            tasks = Task.objects.filter(
                status='ACTIVE',
                actions_completed__lt=models.F('actions_required')
            ).order_by('-created_at').values('type', 'price', 'post_url')
            
            tasks_list = list(tasks)
            
            logger.info(f"""
                Getting all available tasks:
                Total found: {len(tasks_list)}
                Fields: {list(tasks_list[0].keys()) if tasks_list else 'No tasks'}
                Price range: {tasks_list[0]['price'] if tasks_list else 0} - {tasks_list[-1]['price'] if tasks_list and len(tasks_list) > 0 else 0}
                First task example: {tasks_list[0] if tasks_list else 'No tasks'}
            """)
            
            return tasks_list
            
        except Exception as e:
            logger.error(f"Error getting available tasks: {str(e)}")
            return []

    def handle(self, *args, **options):
        logger.info("Starting daily tasks email sending")
        
        # Проверяем, является ли текущий день будним
        current_weekday = timezone.now().weekday()
        if current_weekday >= 5:  # 5 = суббота, 6 = воскресенье
            logger.info("Today is weekend. Skipping email sending.")
            return
        
        # Получаем список доступных заданий
        available_tasks = self.get_available_tasks()
        if not available_tasks:
            logger.info("No available tasks found, stopping email sending")
            return
            
        logger.info(f"Found {len(available_tasks)} available tasks for today")
        
        # Получаем профили с доступными задачами
        profiles = UserProfile.objects.filter(
            available_tasks__gt=0,
            user__is_active=True
        ).select_related('user')
        
        logger.info(f"Found {profiles.count()} active profiles with tasks")
            
        users_with_email = []
        for profile in profiles:
            firebase_uid = profile.user.username
            email = self.get_firebase_email(firebase_uid)
            
            if email and not any(domain in email.lower() for domain in ['@inbox.ondmarc.com', '@test.com']):
                profile.user.email = email
                users_with_email.append(profile.user)
                logger.info(f"Added user to sending list: {email}")
        
        total_users = len(users_with_email)
        success_count = 0
        failed_count = 0
        
        logger.info(f"Starting to send emails to {total_users} users")
        
        for i, user in enumerate(users_with_email, 1):
            try:
                if send_daily_tasks_email(user, available_tasks):
                    success_count += 1
                    logger.info(f"Successfully sent email to {user.email}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to send email to {user.email}")
                
                if i < total_users:
                    logger.info("Waiting 10 seconds before next email...")
                    time.sleep(10)
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error sending email to {user.email}: {str(e)}")
        
        logger.info(f"""Email sending completed:
            Total users: {total_users}
            Success: {success_count}
            Failed: {failed_count}
        """)