from django.core.management.base import BaseCommand
from api.models import Task
from api.utils.email_utils import send_new_task_notifications
import logging

logger = logging.getLogger('api')

class Command(BaseCommand):
    help = 'Send notifications for a newly created task'

    def add_arguments(self, parser):
        parser.add_argument('task_id', type=str, help='ID of the task to send notifications for')

    def handle(self, *args, **options):
        task_id = options['task_id']
        logger.info(f"[send_task_notifications] Starting notifications for task {task_id}")
        
        try:
            task = Task.objects.get(id=task_id)
            send_new_task_notifications(task)
            logger.info(f"[send_task_notifications] Successfully sent notifications for task {task_id}")
        except Task.DoesNotExist:
            logger.error(f"[send_task_notifications] Task {task_id} not found")
        except Exception as e:
            logger.error(f"[send_task_notifications] Error sending notifications for task {task_id}: {str(e)}") 