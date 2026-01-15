from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task
from api.utils.email_utils import send_task_completed_author_email
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send completion emails for all completed tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back for completed tasks'
        )
        parser.add_argument(
            '--delay',
            type=int,
            default=5,
            help='Delay in seconds between sending emails'
        )

    def handle(self, *args, **options):
        days = options['days']
        delay = options['delay']
        
        # Получаем все завершенные задания за последние N дней, которым НЕ отправлено письмо
        completed_date = timezone.now() - timezone.timedelta(days=days)
        completed_tasks = Task.objects.filter(
            status='COMPLETED',
            completed_at__gte=completed_date,
            email_sent=False
        ).select_related('creator')
        
        logger.info(f"""
            Starting to send completion emails (retry for failed):
            Total tasks with unsent emails: {completed_tasks.count()}
            Looking back days: {days}
            Delay between emails: {delay} seconds
        """)
        
        success_count = 0
        failed_count = 0
        
        for i, task in enumerate(completed_tasks, 1):
            try:
                logger.info(f"""
                    Processing task {i}/{completed_tasks.count()}:
                    Task ID: {task.id}
                    Creator: {task.creator.username}
                    Type: {task.type}
                    Completed at: {task.completed_at}
                """)
                
                if send_task_completed_author_email(task):
                    success_count += 1
                    logger.info(f"Successfully sent email for task {task.id}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to send email for task {task.id}")
                
                if i < completed_tasks.count():
                    logger.info(f"Waiting {delay} seconds before next email...")
                    time.sleep(delay)
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"""
                    Error processing task:
                    Task ID: {task.id}
                    Error: {str(e)}
                """)
        
        logger.info(f"""
            Email sending completed:
            Total tasks: {completed_tasks.count()}
            Success: {success_count}
            Failed: {failed_count}
        """)