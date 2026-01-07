import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task
from api.utils.email_utils import send_task_created_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send task creation emails for tasks without a sent flag'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Look back N days for newly created tasks'
        )
        parser.add_argument(
            '--delay',
            type=int,
            default=5,
            help='Delay in seconds between emails'
        )

    def handle(self, *args, **options):
        days = options['days']
        delay = options['delay']

        cutoff = timezone.now() - timezone.timedelta(days=days)
        tasks = Task.objects.filter(
            creation_email_sent=False,
            created_at__gte=cutoff,
            status='ACTIVE'
        ).select_related('creator', 'social_network')

        total = tasks.count()
        logger.info(f"[send_task_created_emails] Tasks to process: {total}, days={days}, delay={delay}s")

        success_count = 0
        failed_count = 0

        for idx, task in enumerate(tasks, 1):
            try:
                logger.info(f"[send_task_created_emails] Processing task {idx}/{total} (id={task.id}, user={task.creator_id})")
                result = send_task_created_email(task)
                if result:
                    task.log_creation_email_status(True, None)
                    success_count += 1
                else:
                    task.log_creation_email_status(False, "send_task_created_email returned False")
                    failed_count += 1
                if idx < total and delay > 0:
                    time.sleep(delay)
            except Exception as exc:
                failed_count += 1
                logger.error(f"[send_task_created_emails] Error sending for task {task.id}: {str(exc)}", exc_info=True)
                try:
                    task.log_creation_email_status(False, str(exc))
                except Exception:
                    logger.error(f"[send_task_created_emails] Failed to update flags for task {task.id}", exc_info=True)

        logger.info(
            f"[send_task_created_emails] Completed. total={total}, success={success_count}, failed={failed_count}"
        )

