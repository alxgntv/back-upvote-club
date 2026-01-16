from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, EmailSubscriptionType, UserEmailSubscription, Task
import logging
from django.utils import timezone
from .utils.email_utils import send_welcome_email
import uuid

logger = logging.getLogger(__name__)

@receiver(post_save, sender=UserProfile)
def setup_user_profile_extras(sender, instance, created, **kwargs):
    """
    Выполняет неприоритетные операции после создания профиля:
    - Создает email подписки
    - Отправляет приветственное письмо
    - Отправляет уведомление пригласившему пользователю
    """
    if created:
        try:
            # 1. Создаем email подписки
            subscription_types = EmailSubscriptionType.objects.all()
            for subscription_type in subscription_types:
                UserEmailSubscription.objects.create(
                    user=instance.user,
                    subscription_type=subscription_type,
                    is_subscribed=True,
                    unsubscribe_token=str(uuid.uuid4())
                )
                logger.info(f"[setup_user_profile_extras] Created {subscription_type.name} subscription for user {instance.user.username}")
            
            # 2. Приветственное письмо отключено - будет отправляться через команды
            logger.info(f"[setup_user_profile_extras] Welcome email disabled for user: {instance.user.username} - will be sent via management command")
            
            # 3. Уведомление пригласившему пользователю отключено - будет отправляться через команды
            if instance.invited_by:
                logger.info(f"[setup_user_profile_extras] Inviter notification disabled for {instance.invited_by.username} about new user {instance.user.username} - will be sent via management command")
            
        except Exception as e:
            logger.error(f"[setup_user_profile_extras] Error setting up extras for user {instance.user.username}: {str(e)}", exc_info=True)

@receiver(pre_save, sender=Task)
def handle_task_status_change(sender, instance, **kwargs):
    try:
        if instance.pk:
            old_instance = Task.objects.get(pk=instance.pk)
            logger.info(f"""
                Task status check:
                Task ID: {instance.id}
                Old status: {old_instance.status}
                New status: {instance.status}
                Creator: {instance.creator.email}
                Type: {instance.type}
                Actions: {instance.actions_completed}/{instance.actions_required}
            """)
            
            if old_instance.status != instance.status and instance.status == 'COMPLETED':
                logger.info(f"""
                    Task status changed to COMPLETED:
                    Task ID: {instance.id}
                    Old status: {old_instance.status}
                    New status: {instance.status}
                    Actions completed: {instance.actions_completed}
                    Actions required: {instance.actions_required}
                    Time to complete: {timezone.now() - instance.created_at}
                """)
                
                instance.completion_duration = timezone.now() - instance.created_at
                
    except Task.DoesNotExist:
        logger.error(f"Task {instance.id} not found in database")
    except Exception as e:
        logger.error(f"Error in handle_task_status_change signal: {str(e)}")

@receiver(post_save, sender=Task)
def send_task_completion_email(sender, instance, created, **kwargs):
    """
    Отправляет email автору задания сразу после завершения задания.
    Если отправка не удалась, задание будет обработано management командой.
    """
    if not created and instance.status == 'COMPLETED' and not instance.email_sent:
        try:
            from .utils.email_utils import send_task_completed_author_email
            logger.info(f"Attempting to send completion email for task {instance.id} immediately after completion")
            send_task_completed_author_email(instance)
        except Exception as e:
            logger.error(f"Failed to send completion email for task {instance.id} in signal: {str(e)}")
            logger.info(f"Task {instance.id} - email will be retried by management command")

@receiver(post_save, sender=Task)
def send_producthunt_promo_email(sender, instance, created, **kwargs):
    """
    Отправляет промо письма всем пользователям с ProductHunt при создании ProductHunt задания.
    Вызывается один раз при создании задания со статусом ACTIVE.
    """
    # Отправляем только если:
    # 1. Новое задание (created=True)
    # 2. Это ProductHunt
    # 3. Статус ACTIVE
    # 4. Письмо еще не отправлено
    
    should_send = (
        created and 
        instance.status == 'ACTIVE' and 
        not instance.promo_email_sent and
        instance.social_network and 
        instance.social_network.code.upper() == 'PRODUCTHUNT'
    )
    
    if should_send:
        logger.info(f"New ProductHunt task {instance.id} created with ACTIVE status - will send promo emails")
        try:
            # Импортируем функцию отправки
            from .utils.email_utils import send_producthunt_campaign_emails
            
            logger.info(f"Starting ProductHunt promo campaign for task {instance.id}")
            
            # Отправляем письма
            stats = send_producthunt_campaign_emails(instance)
            
            # Устанавливаем флаг что письмо отправлено
            Task.objects.filter(pk=instance.pk).update(promo_email_sent=True)
            
            logger.info(f"""
                ProductHunt promo campaign completed for task {instance.id}:
                Sent: {stats['sent']}
                Failed: {stats['failed']}
                Skipped: {stats['skipped']}
            """)
            
        except Exception as e:
            logger.error(f"Failed to send ProductHunt promo emails for task {instance.id}: {str(e)}", exc_info=True)
