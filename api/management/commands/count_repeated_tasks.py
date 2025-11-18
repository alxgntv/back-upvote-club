from django.core.management.base import BaseCommand
from api.models import Task
from django.db.models import Count, Sum
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Подсчитывает количество пользователей, которые создавали задания 2 и более раз'

    def handle(self, *args, **options):
        try:
            # Используем original_price
            users_stats = Task.objects.values(
                'creator_id',
                'creator__username'
            ).annotate(
                tasks_created=Count('id'),
                total_price=Sum('original_price')  # используем original_price
            ).filter(
                tasks_created__gte=2  # только те, кто создал 2 и более заданий
            ).order_by('-tasks_created')

            total_repeated_users = users_stats.count()
            total_price = sum(user['total_price'] for user in users_stats)

            logger.info(f"""
                ====== USERS WITH MULTIPLE TASKS STATISTICS ======
                Total users who created 2+ tasks: {total_repeated_users}
                Total original price spent by these users: {total_price}
                
                Detailed statistics:
                -------------------------------
            """)

            # Выводим статистику по каждому пользователю
            for user in users_stats:
                logger.info(f"""
                    Creator ID: {user['creator_id']}
                    Username: {user['creator__username']}
                    Tasks Created: {user['tasks_created']}
                    Total Original Price Spent: {user['total_price']}
                    -------------------------------
                """)

            self.stdout.write(self.style.SUCCESS(f"""
                Analysis completed!
                Total users who created tasks 2 or more times: {total_repeated_users}
                Total original price spent by these users: {total_price}
            """))

        except Exception as e:
            error_msg = f"Error analyzing users with repeated tasks: {str(e)}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg)) 