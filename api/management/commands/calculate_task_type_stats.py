from django.core.management.base import BaseCommand
from api.models import TaskCompletion
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Рассчитывает статистику выполненных действий'

    def handle(self, *args, **options):
        try:
            # Получаем все выполненные действия
            all_completions = TaskCompletion.objects.all()
            total_completions = all_completions.count()

            # Группируем по типу действия и считаем количество
            action_stats = all_completions.values('action').annotate(
                count=Count('id')
            ).order_by('action')

            # Вычисляем проценты для каждого типа
            action_percentages = {}
            for stat in action_stats:
                percentage = (stat['count'] / total_completions * 100)
                action_percentages[stat['action']] = percentage

            # Форматируем даты
            today = timezone.now().date()
            last_friday = today - timedelta(days=(today.weekday() - 4) % 7)
            date_range = f"{(last_friday - timedelta(days=7)).strftime('%B %d')}-{last_friday.strftime('%d, %Y')}"

            # Формируем сообщение
            twitter_message = f"""🧗‍♀️ Weekly Digest: {date_range}
👉 Tasks Completed: {total_completions}
🔁 Reposts: {action_percentages.get('REPOST', 0):.2f}%
➕ Follows: {action_percentages.get('FOLLOW', 0):.2f}%
❤️ Likes: {action_percentages.get('LIKE', 0):.2f}%
💬 Comments: {action_percentages.get('COMMENT', 0):.2f}% (due to maintanance)"""

            self.stdout.write(twitter_message)
            logger.info(f"Generated statistics message:\n{twitter_message}")

        except Exception as e:
            error_msg = f"Error calculating statistics: {str(e)}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
