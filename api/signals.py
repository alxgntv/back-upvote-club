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
                
                # Email отправка отключена - будет выполняться через команды
                logger.info(f"Task {instance.id} completed - email will be sent via management command")
                
    except Task.DoesNotExist:
        logger.error(f"Task {instance.id} not found in database")
    except Exception as e:
        logger.error(f"Error in handle_task_status_change signal: {str(e)}")
