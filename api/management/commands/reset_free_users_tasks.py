from django.core.management.base import BaseCommand
from api.models import UserProfile, Task
from django.db.models import Count
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reset available tasks to 0 for FREE users who created at least 1 task'

    def handle(self, *args, **options):
        try:
            # Находим FREE пользователей, которые создали хотя бы 1 задание
            free_users_with_tasks = UserProfile.objects.filter(
                status='FREE',
                user__created_tasks__isnull=False
            ).distinct()

            total_users = free_users_with_tasks.count()
            logger.info(f"Found {total_users} FREE users with tasks")

            # Обновляем количество доступных заданий
            updated_count = 0
            for profile in free_users_with_tasks:
                tasks_created = Task.objects.filter(creator=profile.user).count()
                old_available_tasks = profile.available_tasks
                
                profile.available_tasks = 0
                profile.save(update_fields=['available_tasks'])
                
                updated_count += 1
                logger.info(f"""Reset tasks for user:
                    Username: {profile.user.username}
                    Tasks created: {tasks_created}
                    Old available tasks: {old_available_tasks}
                    New available tasks: 0
                """)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully reset available tasks to 0 for {updated_count} FREE users with tasks'
                )
            )
            logger.info(f'Successfully reset available tasks to 0 for {updated_count} FREE users with tasks')

        except Exception as e:
            error_msg = f"Error resetting tasks for FREE users: {str(e)}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
