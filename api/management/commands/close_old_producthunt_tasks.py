from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task, UserProfile, EmailSubscriptionType, UserEmailSubscription
from api.utils.email_utils import get_firebase_email
from api.email_service import EmailService
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Переводит задания PRODUCTHUNT в статус DELETED через 24 часа, возвращает баланс и слот, отправляет email.'

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(hours=24)
        self.stdout.write(f"[INFO] Запуск команды закрытия PRODUCTHUNT задач. Cutoff: {cutoff}")
        logger.info(f"[close_old_producthunt_tasks] Start. Cutoff: {cutoff}")

        # Находим все подходящие задания
        tasks = Task.objects.filter(
            social_network__code='PRODUCTHUNT',
            status='ACTIVE',
            created_at__lte=cutoff
        )
        total = tasks.count()
        self.stdout.write(f"[INFO] Найдено {total} задач для обработки")
        logger.info(f"[close_old_producthunt_tasks] Found {total} tasks to process")

        # Получаем/создаём тип подписки для этого уведомления
        subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
            name='producthunt_task_closed',
            defaults={'description': 'Notifications about PRODUCTHUNT tasks closed by admin after 24h'}
        )

        for task in tasks:
            try:
                logger.info(f"[close_old_producthunt_tasks] Processing task {task.id} (creator: {task.creator.username})")
                profile = UserProfile.objects.get(user=task.creator)
                actions_completed = task.actions_completed
                actions_required = task.actions_required
                price = task.price
                refund = max(0, (actions_required - actions_completed) * price)
                old_balance = profile.balance
                old_available_tasks = profile.available_tasks

                # Переводим задачу в DELETED
                task.status = 'DELETED'
                task.deletion_reason = 'ADMIN_24H_CLOSE'
                task.save(update_fields=['status', 'deletion_reason'])
                logger.info(f"[close_old_producthunt_tasks] Task {task.id} set to DELETED")

                # Возвращаем баланс
                if refund > 0:
                    profile.balance += refund
                    logger.info(f"[close_old_producthunt_tasks] Refunded {refund} to user {profile.user.username}")
                else:
                    logger.info(f"[close_old_producthunt_tasks] No refund needed for task {task.id}")

                # Возвращаем слот задания
                profile.available_tasks += 1
                logger.info(f"[close_old_producthunt_tasks] Returned 1 available_task to user {profile.user.username}")
                profile.save(update_fields=['balance', 'available_tasks'])
                logger.info(f"[close_old_producthunt_tasks] User {profile.user.username} balance: {old_balance} -> {profile.balance}, available_tasks: {old_available_tasks} -> {profile.available_tasks}")

                # Получаем email через Firebase
                email = get_firebase_email(task.creator.username)
                if not email:
                    logger.error(f"[close_old_producthunt_tasks] No email for user {profile.user.username}")
                    continue

                # Проверяем подписку
                subscription, _ = UserEmailSubscription.objects.get_or_create(
                    user=task.creator,
                    subscription_type=subscription_type,
                    defaults={'is_subscribed': True}
                )
                if not subscription.is_subscribed:
                    logger.info(f"[close_old_producthunt_tasks] User {profile.user.username} unsubscribed from producthunt_task_closed emails")
                    continue

                unsubscribe_url = f"https://upvote.club/api/unsubscribe/{subscription.unsubscribe_token}/"

                # Получаем человекочитаемый тип действия
                action_type_display = task.get_type_display()

                subject = f'Your ProductHunt task moved to closed and +{refund} points are back'
                html_content = (
                    f"<p>Hello, we noticed that your upvote task for your Product Hunt launch had dropped down in the queue. Therefore, we changed its status to <b>closed</b>, returned <b>+{refund}</b> points back to your balance, and also restored <b>+1 free task slot</b>.</p> "
                    f"<p>We know that on Product Hunt, it's most important to get as many {actions_completed} as possible within the first 24 hours after launch. On the second day, it's no longer as effective. That’s why we decided to close your task and return your points to your balance.</p>"
                    f"<p>You can create a new task again <a href='https://upvote.club/dashboard/createtask'>completely free</a></p>"
                    f"<p>Your received: <b>+{actions_completed} {action_type_display.lower()}(s)</b> from the UpvoteClub community.</p>"
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
                        logger.info(f"[close_old_producthunt_tasks] Email sent to {email} for task {task.id}")
                    else:
                        logger.error(f"[close_old_producthunt_tasks] Failed to send email to {email} for task {task.id}")
                except Exception as e:
                    logger.error(f"[close_old_producthunt_tasks] Error sending email to {email}: {str(e)}")

                self.stdout.write(self.style.SUCCESS(f"Task {task.id} closed, user {profile.user.username} notified, refund: {refund}"))
            except Exception as e:
                logger.error(f"[close_old_producthunt_tasks] Error processing task {getattr(task, 'id', '?')}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"Error processing task {getattr(task, 'id', '?')}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"[close_old_producthunt_tasks] Completed. Processed: {total}"))
        logger.info(f"[close_old_producthunt_tasks] Completed. Processed: {total}") 