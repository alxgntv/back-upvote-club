import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from api.models import Task, TaskCompletion, PaymentTransaction
import logging
from django.db.models import Avg
from datetime import timedelta
import math

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = '8045516781:AAFdnzHGd78LIeCyW5ygkO8yVk1jY3p5J1Y'
TELEGRAM_CHAT_ID = '133814301'  # Замените на свой chat_id

class Command(BaseCommand):
    help = 'Send daily platform stats to Telegram bot'

    def handle(self, *args, **options):
        logger.info('[TelegramStats] Starting daily stats calculation')
        now = timezone.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timezone.timedelta(days=1)
        end = start + timezone.timedelta(days=1)
        logger.info(f'[TelegramStats] Calculating stats for period: {start} - {end}')

        # Форматируем среднее/медиану времени выполнения в человекочитаемый вид
        def format_timedelta(td):
            if not td:
                return 'N/A'
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"

        # 1. Сколько выполенно заданий за прошлые сутки
        completed_tasks_count = TaskCompletion.objects.filter(
            created_at__gte=start,
            created_at__lt=end
        ).count()
        logger.info(f'[TelegramStats] Completed tasks in last day: {completed_tasks_count}')

        # 2. Сколько пользователей было зарегано
        new_users_count = User.objects.filter(
            date_joined__gte=start,
            date_joined__lt=end
        ).count()
        logger.info(f'[TelegramStats] New users registered in last day: {new_users_count}')

        # 3. Сколько новых заданий было созданно
        new_tasks_count = Task.objects.filter(
            created_at__gte=start,
            created_at__lt=end
        ).count()
        logger.info(f'[TelegramStats] New tasks created in last day: {new_tasks_count}')

        # 4. Сколько заданий в статусе Complete (всего)
        total_completed_tasks = Task.objects.filter(status='COMPLETED').count()
        logger.info(f'[TelegramStats] Total tasks in status COMPLETED: {total_completed_tasks}')

        # 4.1. Сколько заданий перешли в статус complete за прошедшие сутки
        completed_yesterday_qs = Task.objects.filter(
            status='COMPLETED',
            completed_at__gte=start,
            completed_at__lt=end
        )
        completed_yesterday_count = completed_yesterday_qs.count()
        logger.info(f'[TelegramStats] Tasks completed (COMPLETED) yesterday: {completed_yesterday_count}')

        # 4.2. Среднее время выполнения задач, завершённых за сутки
        completed_yesterday_with_duration = completed_yesterday_qs.exclude(completion_duration__isnull=True)
        avg_completion_time_yesterday = completed_yesterday_with_duration.aggregate(avg=Avg('completion_duration'))['avg']
        logger.info(f'[TelegramStats] Tasks with completion_duration yesterday: {completed_yesterday_with_duration.count()}')
        logger.info(f'[TelegramStats] Avg completion time for tasks completed yesterday: {avg_completion_time_yesterday}')

        # 4.2.1. Медиана времени выполнения задач, завершённых за сутки
        durations = list(completed_yesterday_with_duration.values_list('completion_duration', flat=True))
        durations = [d for d in durations if d is not None]
        durations_sorted = sorted(durations, key=lambda x: x.total_seconds())
        median_completion_time_yesterday = None
        if durations_sorted:
            n = len(durations_sorted)
            mid = n // 2
            if n % 2 == 1:
                median_completion_time_yesterday = durations_sorted[mid]
            else:
                median_completion_time_yesterday = durations_sorted[mid - 1] + (durations_sorted[mid] - durations_sorted[mid - 1]) / 2
        logger.info(f'[TelegramStats] Median completion time for tasks completed yesterday: {median_completion_time_yesterday}')
        median_completion_time_yesterday_str = format_timedelta(median_completion_time_yesterday)

        # Форматируем среднее время выполнения в человекочитаемый вид
        avg_completion_time_yesterday_str = format_timedelta(avg_completion_time_yesterday)

        # 4.3. Сколько заданий ещё не завершено (статус ACTIVE)
        active_tasks_count = Task.objects.filter(status='ACTIVE').count()
        logger.info(f'[TelegramStats] Tasks in status ACTIVE (not completed): {active_tasks_count}')

        # 4.4. Сколько новых ACTIVE задач появилось за прошедшие сутки
        active_tasks_yesterday_count = Task.objects.filter(
            status='ACTIVE',
            created_at__gte=start,
            created_at__lt=end
        ).count()
        logger.info(f'[TelegramStats] New ACTIVE tasks created yesterday: {active_tasks_yesterday_count}')

        # 5. Подписки TRIAL
        total_trial_subs = PaymentTransaction.objects.filter(status='TRIAL').count()
        trial_subs_yesterday = PaymentTransaction.objects.filter(
            status='TRIAL',
            created_at__gte=start,
            created_at__lt=end
        ).count()
        logger.info(f'[TelegramStats] Total TRIAL subscriptions: {total_trial_subs}')
        logger.info(f'[TelegramStats] TRIAL subscriptions yesterday: {trial_subs_yesterday}')

        # 6. Подписки ACTIVE
        total_active_subs = PaymentTransaction.objects.filter(status='ACTIVE').count()
        active_subs_yesterday = PaymentTransaction.objects.filter(
            status='ACTIVE',
            created_at__gte=start,
            created_at__lt=end
        ).count()
        logger.info(f'[TelegramStats] Total ACTIVE subscriptions: {total_active_subs}')
        logger.info(f'[TelegramStats] ACTIVE subscriptions yesterday: {active_subs_yesterday}')

        # 7. Tasks that need exactly 1 action to complete
        almost_completed_tasks = Task.objects.filter(
            status='ACTIVE',
            actions_required__gt=0
        ).extra(where=['actions_required - actions_completed = 1']).count()
        logger.info(f'[TelegramStats] Tasks needing exactly 1 action to complete: {almost_completed_tasks}')

        # Формируем сообщение
        message = (
            f"🧗‍♀️ Daily Platform Stats (for {start.strftime('%Y-%m-%d')}):\n"
            f"1. Tasks completed yesterday: <b>{completed_tasks_count}</b>\n"
            f"2. New users registered: <b>{new_users_count}</b>\n"
            f"3. New tasks created: <b>{new_tasks_count}</b>\n"
            f"4. Total tasks in status COMPLETED: <b>{total_completed_tasks}</b> (+{completed_yesterday_count} yesterday)\n"
            f"5. Avg completion time for tasks completed yesterday: <b>{avg_completion_time_yesterday_str}</b>\n"
            f"6. Median completion time for tasks completed yesterday: <b>{median_completion_time_yesterday_str}</b>\n"
            f"7. Tasks in status ACTIVE (not completed): <b>{active_tasks_count}</b> (+{active_tasks_yesterday_count} yesterday)\n"
            f"8. Subscriptions TRIAL: <b>{total_trial_subs}</b> (+{trial_subs_yesterday} yesterday)\n"
            f"9. Subscriptions ACTIVE: <b>{total_active_subs}</b> (+{active_subs_yesterday} yesterday)\n"
            f"10. Tasks needing 1 action to complete: <b>{almost_completed_tasks}</b>\n"
        )
        logger.info(f'[TelegramStats] Message to send: {message}')

        # Отправляем в Telegram
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        try:
            response = requests.post(url, data=payload, timeout=10)
            logger.info(f'[TelegramStats] Telegram response: {response.status_code} {response.text}')
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS('Stats sent to Telegram successfully'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed to send stats to Telegram: {response.text}'))
        except Exception as e:
            logger.error(f'[TelegramStats] Exception while sending to Telegram: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Exception while sending to Telegram: {str(e)}')) 