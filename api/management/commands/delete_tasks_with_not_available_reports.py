import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task, UserProfile, TaskReport, EmailSubscriptionType, UserEmailSubscription
from api.utils.email_utils import get_firebase_email
from api.email_service import EmailService
from django.db.models import Count

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Переводит задания в статус DELETED, если на них есть хотя бы 1 репорт с причиной not_available, возвращает баллы и слот, отправляет email.'

    def handle(self, *args, **options):
        logger.info('[delete_tasks_with_not_available_reports] Start command')
        self.stdout.write('[INFO] Запуск команды удаления задач с репортами not_available')

        # Получаем задачи с хотя бы 1 репортом с причиной 'not_available'
        reported_tasks = (
            TaskReport.objects
            .filter(reason='not_available')
            .values('task')
            .annotate(report_count=Count('id'))
            .filter(report_count__gte=1)
        )
        task_ids = [item['task'] for item in reported_tasks]
        logger.info(f'[delete_tasks_with_not_available_reports] Найдено {len(task_ids)} задач с >=1 репортом not_available')
        self.stdout.write(f'[INFO] Найдено {len(task_ids)} задач для обработки')

        # Получаем/создаём тип подписки для этого уведомления
        subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
            name='task_link_unavailable',
            defaults={'description': 'Notifications about tasks deleted due to unavailable link'}
        )

        processed = 0
        for task_id in task_ids:
            try:
                task = Task.objects.get(id=task_id)
                logger.info(f'[delete_tasks_with_not_available_reports] Обработка задачи {task.id} (creator: {task.creator.username})')
                if task.status != 'ACTIVE':
                    logger.info(f'[delete_tasks_with_not_available_reports] Пропуск задачи {task.id}, статус: {task.status}')
                    continue
                profile = UserProfile.objects.get(user=task.creator)
                actions_completed = task.actions_completed
                actions_required = task.actions_required
                price = task.price
                refund = max(0, (actions_required - actions_completed) * price)
                old_balance = profile.balance
                old_available_tasks = profile.available_tasks

                # Переводим задачу в DELETED
                task.status = 'DELETED'
                task.deletion_reason = 'LINK_UNAVAILABLE'
                task.save(update_fields=['status', 'deletion_reason'])
                logger.info(f'[delete_tasks_with_not_available_reports] Task {task.id} set to DELETED')

                # Возвращаем баланс
                if refund > 0:
                    profile.balance += refund
                    logger.info(f'[delete_tasks_with_not_available_reports] Refunded {refund} to user {profile.user.username}')
                else:
                    logger.info(f'[delete_tasks_with_not_available_reports] No refund needed for task {task.id}')

                # Возвращаем слот задания
                profile.available_tasks += 1
                logger.info(f'[delete_tasks_with_not_available_reports] Returned 1 available_task to user {profile.user.username}')
                profile.save(update_fields=['balance', 'available_tasks'])
                logger.info(f'[delete_tasks_with_not_available_reports] User {profile.user.username} balance: {old_balance} -> {profile.balance}, available_tasks: {old_available_tasks} -> {profile.available_tasks}')

                # Получаем email через Firebase
                email = get_firebase_email(task.creator.username)
                if not email:
                    logger.error(f'[delete_tasks_with_not_available_reports] No email for user {profile.user.username}')
                    continue

                # Проверяем подписку
                subscription, _ = UserEmailSubscription.objects.get_or_create(
                    user=task.creator,
                    subscription_type=subscription_type,
                    defaults={'is_subscribed': True}
                )
                if not subscription.is_subscribed:
                    logger.info(f'[delete_tasks_with_not_available_reports] User {profile.user.username} unsubscribed from task_link_unavailable emails')
                    continue

                unsubscribe_url = f"https://upvote.club/api/unsubscribe/{subscription.unsubscribe_token}/"

                # Получаем человекочитаемый тип действия и соцсети
                action_type_display = task.get_type_display()
                social_name = task.social_network.name if task.social_network else 'Social Network'

                subject = f'Your {social_name} task was deleted due to unavailable link and +{refund} points are back'
                html_content = (
                    f"<p>Hello! Your {social_name} task was <b>deleted</b> because the link in your task is unavailable. Users reported that the link does not work or is not accessible, so we removed this task from the platform. No worries, we have returned <b>+{refund}</b> points to <a href='https://upvote.club/dashboard/'>your balance</a> and restored <b>+1 free task slot</b>, so you can create it again with a working link. You can create a new task again <a href='https://upvote.club/dashboard/createtask?linkunavailable'>completely free</a>.</p>"
                    f"<p>Your UpvoteClub Team</p>"
                )
                try:
                    email_service = EmailService()
                    result = email_service.send_email(
                        to_email=email,
                        subject=subject,
                        html_content=html_content,
                        unsubscribe_url=unsubscribe_url
                    )
                    if result:
                        logger.info(f'[delete_tasks_with_not_available_reports] Email sent to {email} for task {task.id}')
                    else:
                        logger.error(f'[delete_tasks_with_not_available_reports] Failed to send email to {email} for task {task.id}')
                except Exception as e:
                    logger.error(f'[delete_tasks_with_not_available_reports] Error sending email to {email}: {str(e)}')

                self.stdout.write(self.style.SUCCESS(f"Task {task.id} deleted, user {profile.user.username} notified, refund: {refund}"))
                processed += 1
            except Exception as e:
                logger.error(f'[delete_tasks_with_not_available_reports] Error processing task {task_id}: {str(e)}')
                self.stdout.write(self.style.ERROR(f"Error processing task {task_id}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f'[delete_tasks_with_not_available_reports] Completed. Processed: {processed}'))
        logger.info(f'[delete_tasks_with_not_available_reports] Completed. Processed: {processed}') 