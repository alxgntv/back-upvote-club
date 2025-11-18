from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task, TaskCompletion
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates completion times for tasks based on their last completion'

    def handle(self, *args, **options):
        # Получаем все завершенные задания
        completed_tasks = Task.objects.filter(
            status='COMPLETED',
            completion_duration__isnull=True
        )
        
        logger.info(f"Starting completion time update for {completed_tasks.count()} tasks")
        self.stdout.write(f"Found {completed_tasks.count()} tasks to update")
        
        updated_count = 0
        for task in completed_tasks:
            try:
                # Находим время последнего выполнения для этого задания
                last_completion = TaskCompletion.objects.filter(
                    task=task
                ).order_by('-completed_at').first()
                
                if last_completion:
                    # Устанавливаем время завершения
                    task.completed_at = last_completion.completed_at
                    # Вычисляем длительность выполнения
                    task.completion_duration = last_completion.completed_at - task.created_at
                    task.save()
                    
                    updated_count += 1
                    
                    logger.info(f"""
                        Updated task {task.id}:
                        Created at: {task.created_at}
                        Completed at: {task.completed_at}
                        Duration: {task.completion_duration}
                        Required actions: {task.actions_required}
                        Completed actions: {task.actions_completed}
                    """)
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"Updated task {task.id} - Duration: {task.completion_duration}"
                    ))
            except Exception as e:
                error_msg = f"Error updating completion time for task {task.id}: {str(e)}"
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                
        success_msg = f"Successfully updated {updated_count} tasks"
        logger.info(success_msg)
        self.stdout.write(self.style.SUCCESS(success_msg))