from django.core.management.base import BaseCommand
from api.models import Task
from api.utils.email_utils import send_task_completed_author_email
from django.db.models import Q
import time
from django.utils import timezone

class Command(BaseCommand):
    help = 'Retry sending emails for tasks where previous attempts failed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=5,
            help='Number of emails to send in one batch'
        )
        parser.add_argument(
            '--batch-delay',
            type=int,
            default=60,
            help='Delay in seconds between batches'
        )

    def handle(self, *args, **options):
        # Получаем задачи с неотправленными письмами
        failed_tasks = Task.objects.filter(
            status='COMPLETED'
        ).filter(
            Q(email_sent=False) &
            (Q(email_send_error__isnull=True) | Q(email_send_error__isnull=False))
        ).order_by('completed_at')

        total_tasks = failed_tasks.count()
        
        if total_tasks == 0:
            self.stdout.write(self.style.SUCCESS("No emails to send. Job completed."))
            return

        batch_size = options['batch_size']
        batch_delay = options['batch_delay']
        
        self.stdout.write(self.style.WARNING(
            f"Starting email retry process: {total_tasks} tasks found. Batch size: {batch_size}, Batch delay: {batch_delay} seconds"
        ))

        # Разбиваем на батчи
        processed_count = 0
        success_count = 0
        batch_number = 1

        while processed_count < total_tasks:
            batch_start_time = timezone.now()
            
            # Получаем текущий батч
            current_batch = failed_tasks[processed_count:processed_count + batch_size]
            
            self.stdout.write(
                f"Processing batch #{batch_number}: Tasks in batch: {len(current_batch)} (processed: {processed_count}/{total_tasks})"
            )

            # Обрабатываем каждую задачу в батче
            batch_success = 0
            for task in current_batch:
                try:
                    # Для целей дебага можно раскомментировать следующую строку
                    # self.stdout.write(f"Sending email for task id {task.id}...")

                    if send_task_completed_author_email(task):
                        batch_success += 1
                        success_count += 1
                        # self.stdout.write(self.style.SUCCESS(f"Email sent for task {task.id}"))
                    else:
                        # self.stdout.write(self.style.ERROR(f"Failed to send email for task {task.id}"))
                        pass
                except Exception as e:
                    # self.stdout.write(self.style.ERROR(f"Error processing task {task.id}: {str(e)}"))
                    pass

            processed_count += len(current_batch)
            
            batch_duration = (timezone.now() - batch_start_time).total_seconds()
            self.stdout.write(
                f"Batch #{batch_number} completed: Success in batch: {batch_success}/{len(current_batch)}. Total success so far: {success_count}/{processed_count}"
            )

            # Если есть ещё задачи для обработки, делаем паузу
            if processed_count < total_tasks:
                sleep_time = max(0, batch_delay - batch_duration)
                if sleep_time > 0:
                    self.stdout.write(f"Waiting {sleep_time} seconds before next batch...")
                    time.sleep(sleep_time)

            batch_number += 1

        self.stdout.write(self.style.SUCCESS(
            f"Email retry process completed: {total_tasks} processed, {success_count} sent successfully, {total_tasks - success_count} failed."
        )) 