from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Count, Q
from datetime import timedelta
import logging
from ...models import TaskCompletion, UserEmailSubscription, EmailSubscriptionType
from ...utils.email_utils import send_weekly_recap_email

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends weekly recap emails to users (should be run on Mondays)'

    def get_tasks_stats(self, user, current_week_start, previous_week_start):
        """
        Получает статистику по заданиям за текущую и предыдущую неделю
        """
        # Текущая неделя
        current_week_tasks = TaskCompletion.objects.filter(
            user=user,
            created_at__gte=current_week_start,
            created_at__lt=current_week_start + timedelta(days=7)
        ).count()

        previous_week_tasks = TaskCompletion.objects.filter(
            user=user,
            created_at__gte=previous_week_start,
            created_at__lt=current_week_start
        ).count()

        # Вычисляем процент изменения
        if previous_week_tasks > 0:
            change_percentage = ((current_week_tasks - previous_week_tasks) / previous_week_tasks) * 100
        else:
            change_percentage = 100 if current_week_tasks > 0 else 0

        return current_week_tasks, change_percentage

    def get_network_stats(self, user, current_week_start):
        """
        Получает статистику по действиям в разных соцсетях
        """
        # Получаем статистику по типам действий для каждой соцсети
        network_stats = TaskCompletion.objects.filter(
            user=user,
            created_at__gte=current_week_start,
            created_at__lt=current_week_start + timedelta(days=7)
        ).values(
            'task__social_network__name',
            'task__type'
        ).annotate(
            count=Count('id')
        ).order_by('task__social_network__name', '-count')

        # Группируем по соцсетям
        networks = {}
        emoji_map = {
            'LIKE': '❤️',
            'REPOST': '🔄',
            'COMMENT': '💬',
            'FOLLOW': '👥',
            'SAVE': '🔖',
            'CONNECT': '🤝',
            'RESTACK': '📢',
            'UPVOTE': '⬆️',
        }

        for stat in network_stats:
            network_name = stat['task__social_network__name']
            if network_name not in networks:
                networks[network_name] = {
                    'name': network_name,
                    'actions': []
                }
            
            networks[network_name]['actions'].append({
                'name': stat['task__type'],
                'count': stat['count'],
                'emoji': emoji_map.get(stat['task__type'], '🎯')
            })

        return list(networks.values())

    def get_leaderboard(self, current_week_start):
        """
        Получает топ-10 пользователей по заработанным очкам за неделю
        """
        return User.objects.filter(
            taskcompletion__created_at__gte=current_week_start,
            taskcompletion__created_at__lt=current_week_start + timedelta(days=7)
        ).annotate(
            points=Count('taskcompletion')
        ).order_by('-points')[:10].values('username', 'points')

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Проверяем, что сегодня понедельник (0 = понедельник в datetime.weekday())
        if now.weekday() != 0:
            self.stdout.write(self.style.WARNING('Today is not Monday. Skipping weekly recap.'))
            return

        logger.info("Starting weekly recap email sending")

        # Получаем начало текущей и предыдущей недели
        current_week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
        previous_week_start = current_week_start - timedelta(days=7)

        # Получаем тип подписки
        subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
            name='weekly_recap',
            defaults={'description': 'Weekly performance recap emails'}
        )

        # Получаем всех подписанных пользователей
        subscribed_users = UserEmailSubscription.objects.filter(
            subscription_type=subscription_type,
            is_subscribed=True
        ).select_related('user')

        total_users = subscribed_users.count()
        success_count = 0
        error_count = 0

        logger.info(f"Found {total_users} subscribed users")

        for subscription in subscribed_users:
            try:
                user = subscription.user
                logger.info(f"Processing user {user.username}")

                # Собираем статистику
                total_tasks, change_percentage = self.get_tasks_stats(
                    user, 
                    current_week_start, 
                    previous_week_start
                )

                # Если у пользователя нет активности за две недели, пропускаем
                if total_tasks == 0 and change_percentage == 0:
                    logger.info(f"No activity for user {user.username}, skipping")
                    continue

                data = {
                    'total_tasks': total_tasks,
                    'tasks_change_percentage': round(change_percentage, 1),
                    'networks': self.get_network_stats(user, current_week_start),
                    'leaderboard': self.get_leaderboard(current_week_start)
                }

                if send_weekly_recap_email(user, data):
                    success_count += 1
                    logger.info(f"Successfully sent recap to {user.username}")
                else:
                    error_count += 1
                    logger.error(f"Failed to send recap to {user.username}")

            except Exception as e:
                error_count += 1
                logger.error(f"Error processing user {user.username}: {str(e)}")

        # Выводим итоговую статистику
        self.stdout.write(self.style.SUCCESS(
            f"""Weekly recap sending completed:
            Total users: {total_users}
            Successful: {success_count}
            Failed: {error_count}"""
        ))

        logger.info(f"""
            Weekly recap completed:
            Total users: {total_users}
            Successful: {success_count}
            Failed: {error_count}
        """) 