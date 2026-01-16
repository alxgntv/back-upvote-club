from django.core.management.base import BaseCommand
from api.models import Task
from api.utils.email_utils import send_producthunt_campaign_emails
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manually send ProductHunt campaign emails for a specific task'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task-id',
            type=int,
            required=True,
            help='ProductHunt task ID to promote'
        )

    def handle(self, *args, **options):
        task_id = options['task_id']
        
        # Получаем ProductHunt задание
        try:
            task = Task.objects.select_related('social_network', 'creator').get(id=task_id)
            
            # Проверяем что это ProductHunt задание
            if task.social_network.code.upper() != 'PRODUCTHUNT':
                self.stdout.write(self.style.ERROR(f'Task {task_id} is not a ProductHunt task. Social network: {task.social_network.name}'))
                return
            
            # Проверяем что задание активно
            if task.status != 'ACTIVE':
                self.stdout.write(self.style.ERROR(f'Task {task_id} is not ACTIVE. Current status: {task.status}'))
                return
                
        except Task.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Task {task_id} does not exist'))
            return
        
        self.stdout.write(self.style.SUCCESS(f"""
========================================
ProductHunt Campaign:
========================================
Task ID: {task.id}
Task Type: {task.type}
Task URL: {task.post_url}
Creator: {task.creator.username}
Promo email already sent: {task.promo_email_sent}
========================================
        """))
        
        if task.promo_email_sent:
            self.stdout.write(self.style.WARNING(f'Promo emails were already sent for this task!'))
            user_input = input('Do you want to send again? (yes/no): ')
            if user_input.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Campaign cancelled'))
                return
        
        self.stdout.write(self.style.SUCCESS('Sending ProductHunt campaign emails...'))
        
        # Отправляем письма
        stats = send_producthunt_campaign_emails(task)
        
        # Устанавливаем флаг
        task.promo_email_sent = True
        task.save(update_fields=['promo_email_sent'])
        
        # Итоговая статистика
        self.stdout.write(self.style.SUCCESS(f"""
========================================
Campaign Completed:
========================================
Emails sent: {stats['sent']}
Failed: {stats['failed']}
Skipped: {stats['skipped']}
========================================
        """))
        
        logger.info(f"""
            ProductHunt campaign completed for task {task_id}:
            Sent: {stats['sent']}
            Failed: {stats['failed']}
            Skipped: {stats['skipped']}
        """)
