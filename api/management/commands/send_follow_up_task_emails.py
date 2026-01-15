from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task, UserEmailSubscription, EmailSubscriptionType
from api.utils.email_utils import get_firebase_email, format_duration
from api.email_service import EmailService
from django.template.loader import render_to_string
from django.conf import settings
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Отправляет повторные письма о завершении заданий в зависимости от времени'

    def handle(self, *args, **options):
        logger.info("Starting follow-up task completion emails")
        
        now = timezone.now()
        
        # Определяем интервалы для отправки писем
        intervals = [
            {
                'hours': 24,
                'tolerance': 1,  # ±1 час
                'subscription_name': 'task_follow_up_24h',
                'subject': 'Your task has been completed!',
                'description': 'Follow-up emails sent 24h after task completion'
            },
            {
                'hours': 72,  # 3 дня
                'tolerance': 2,  # ±2 часа
                'subscription_name': 'task_follow_up_3days',
                'subject': '72 hours left since your task was completed. Create a new one!',
                'description': 'Follow-up emails sent 3 days after task completion'
            },
            {
                'hours': 168,  # 7 days (1 week)
                'tolerance': 4,  # ±4 hours
                'subscription_name': 'task_follow_up_1week',
                'subject': 'Don’t miss out – get your next post trending now!',
                'description': 'Follow-up emails sent 1 week after task completion'
            },
            {
                'hours': 336,  # 14 days (2 weeks)
                'tolerance': 6,  # ±6 hours
                'subscription_name': 'task_follow_up_2weeks',
                'subject': 'Boost your reach: your next viral moment is waiting!',
                'description': 'Follow-up emails sent 2 weeks after task completion'
            },
            {
                'hours': 504,  # 21 days (3 weeks)
                'tolerance': 8,  # ±8 hours
                'subscription_name': 'task_follow_up_3weeks',
                'subject': 'Stay on top: launch a new task and grow your audience!',
                'description': 'Follow-up emails sent 3 weeks after task completion'
            },
            {
                'hours': 720,  # 30 days (1 month)
                'tolerance': 12,  # ±12 hours
                'subscription_name': 'task_follow_up_1month',
                'subject': 'Ready to ignite new engagement? Start your next task!',
                'description': 'Follow-up emails sent 1 month after task completion'
            },
            {
                'hours': 960,  # 40 days
                'tolerance': 16,  # ±16 hours
                'subscription_name': 'task_follow_up_40days',
                'subject': 'Get noticed again – create your next viral campaign!',
                'description': 'Follow-up emails sent 40 days after task completion'
            },
            {
                'hours': 1440,  # 60 days (2 months)
                'tolerance': 24,  # ±24 hours
                'subscription_name': 'task_follow_up_2months',
                'subject': 'Your audience is waiting — give your content a fresh boost!',
                'description': 'Follow-up emails sent 2 months after task completion'
            }
        ]
        
        total_sent = 0
        
        for interval in intervals:
            hours = interval['hours']
            tolerance = interval['tolerance']
            subscription_name = interval['subscription_name']
            subject = interval['subject']
            description = interval['description']
            
            logger.info(f"Processing {hours}h interval with ±{tolerance}h tolerance")
            
            # Вычисляем временной диапазон
            target_time = now - timedelta(hours=hours)
            time_range_start = target_time - timedelta(hours=tolerance)
            time_range_end = target_time + timedelta(hours=tolerance)
            
            # Находим задания в этом временном диапазоне
            completed_tasks = Task.objects.filter(
                status='COMPLETED',
                completed_at__gte=time_range_start,
                completed_at__lte=time_range_end,
                email_sent=True  # Только те, кому уже отправили первое письмо
            )
            
            task_count = completed_tasks.count()
            logger.info(f"Found {task_count} tasks completed around {hours}h ago")
            
            if task_count == 0:
                logger.info(f"No tasks found for {hours}h follow-up emails")
                continue
            
            # Получаем или создаем тип подписки
            subscription_type, created = EmailSubscriptionType.objects.get_or_create(
                name=subscription_name,
                defaults={'description': description}
            )
            
            email_service = EmailService()
            success_count = 0
            failed_count = 0
            
            for task in completed_tasks:
                try:
                    logger.info(f"Sending {hours}h follow-up email for task {task.id} to {task.creator.username}")
                    
                    # Получаем email из Firebase
                    firebase_uid = task.creator.username
                    creator_email = get_firebase_email(firebase_uid)
                    
                    if not creator_email:
                        logger.error(f"Could not get Firebase email for user {task.creator.username}")
                        failed_count += 1
                        continue
                    
                    # Проверяем подписку на повторные письма
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=task.creator,
                        subscription_type=subscription_type,
                        defaults={'is_subscribed': True}
                    )
                    
                    if not subscription.is_subscribed:
                        logger.info(f"User {task.creator.username} unsubscribed from {hours}h follow-up emails")
                        failed_count += 1
                        continue
                    
                    unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
                    formatted_completion_time = format_duration(task.completion_duration)
                    completion_hours = task.completion_duration.total_seconds() / 3600 if task.completion_duration else 0
                    
                    context = {
                        'task': task,
                        'user': task.creator,
                        'completion_time': formatted_completion_time,
                        'completion_hours': completion_hours,
                        'user_email': creator_email,
                        'unsubscribe_url': unsubscribe_url
                    }
                    
                    # Рендерим HTML контент (используем тот же шаблон)
                    html_content = render_to_string('email/task_completed_author.html', context)
                    
                    # Отправляем письмо с соответствующим заголовком
                    result = email_service.send_email(
                        to_email=creator_email,
                        subject=subject,
                        html_content=html_content,
                        unsubscribe_url=unsubscribe_url,
                        bcc_email=['yes@upvote.club', 'yesupvote@gmail.com']
                    )
                    
                    if result:
                        success_count += 1
                        logger.info(f"Successfully sent {hours}h follow-up email for task {task.id}")
                        self.stdout.write(f"✓ Sent {hours}h follow-up email for task {task.id}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to send {hours}h follow-up email for task {task.id}")
                        self.stdout.write(self.style.WARNING(f"✗ Failed to send {hours}h follow-up email for task {task.id}"))
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing task {task.id}: {str(e)}")
                    self.stdout.write(self.style.ERROR(f"Error processing task {task.id}: {str(e)}"))
            
            interval_summary = f"""
            {hours}h follow-up emails completed:
            Total tasks: {task_count}
            Successfully sent: {success_count}
            Failed: {failed_count}
            """
            
            logger.info(interval_summary)
            self.stdout.write(self.style.SUCCESS(interval_summary))
            total_sent += success_count
        
        final_summary = f"""
        All follow-up emails completed:
        Total emails sent: {total_sent}
        """
        
        logger.info(final_summary)
        self.stdout.write(self.style.SUCCESS(final_summary))
