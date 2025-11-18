from ..models import Transaction
import logging
from django.utils import timezone
from ..models import TaskCompletion

logger = logging.getLogger(__name__)

def get_user_available_tasks(profile):
    """
    Получает список доступных заданий для пользователя
    """
    try:
        logger.info(f"""
            Getting available tasks for user:
            Username: {profile.user.username}
            Status: {profile.status}
            Available tasks: {profile.available_tasks}
        """)

        # Получаем выполненные задания пользователя за сегодня
        completed_tasks = Transaction.objects.filter(
            user=profile.user,
            type='REWARD',
            status='COMPLETED',
            created_at__date=timezone.now().date()
        ).count()

        logger.info(f"User {profile.user.username} has completed {completed_tasks} tasks today")

        # Определяем количество оставшихся заданий
        remaining_tasks = min(
            profile.available_tasks,
            profile.daily_task_limit - completed_tasks
        )

        if remaining_tasks <= 0:
            logger.info(f"No available tasks for user {profile.user.username}")
            return []

        # Формируем список заданий
        tasks = []
        for i in range(remaining_tasks):
            task = {
                'type': 'Like & Retweet',
                'price': 10,
                'twitter_url': 'https://twitter.com/example/status/123456789',
            }
            tasks.append(task)

        logger.info(f"""
            Generated tasks for user {profile.user.username}:
            Total tasks: {len(tasks)}
            Daily limit: {profile.daily_task_limit}
            Completed today: {completed_tasks}
            Remaining: {remaining_tasks}
        """)

        return tasks

    except Exception as e:
        logger.error(f"Error getting available tasks for user {profile.user.username}: {str(e)}")
        return []

def get_completed_tasks_count(user):
    """
    Получает количество выполненных задач для пользователя
    """
    completed_tasks = TaskCompletion.objects.filter(
        user=user,
        completed_at__isnull=False
    ).count()
    
    return completed_tasks