import logging
import random
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.models import User
from urllib.parse import urlencode
from ..models import UserEmailSubscription, EmailSubscriptionType, Task
from ..email_service import EmailService
from firebase_admin import auth
from ..models import TaskCompletion
from rest_framework_simplejwt.tokens import RefreshToken
import time

logger = logging.getLogger(__name__)

def get_firebase_email(firebase_uid):
    try:
        user = auth.get_user(firebase_uid)
        logger.info(f"Retrieved Firebase email for UID {firebase_uid}: {user.email}")
        return user.email
    except Exception as e:
        logger.error(f"Error getting Firebase email for UID {firebase_uid}: {str(e)}")
        return None

def send_daily_tasks_email(user, tasks):
    """Отправляет email с доступными заданиями через SMTP"""
    try:
        # Проверяем, есть ли задания
        if not tasks:
            logger.info(f"No tasks available for user {user.username}, skipping email")
            return True  # Возвращаем True, так как это не ошибка
            
        logger.info(f"Starting email preparation for user {user.username}")
        
        # Получаем email из Firebase
        user_email = get_firebase_email(user.username)
        if not user_email:
            logger.error(f"Could not get Firebase email for user {user.username}")
            return False
            
        # Проверяем подписку пользователя
        subscription_type = EmailSubscriptionType.objects.get(name='daily_tasks')
        subscription = UserEmailSubscription.objects.get(
            user=user,
            subscription_type=subscription_type,
            is_subscribed=True
        )
        
        unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        
        logger.info(f"Subscription found for user {user.username}")

        # Подсчитываем общую сумму баллов за все задания
        total_points = sum(task['price'] for task in tasks)
        total_tasks = len(tasks)

        # Выбираем 5 случайных заданий для показа в письме
        sample_size = min(5, total_tasks)
        random_tasks = random.sample(tasks, sample_size)

        logger.info(f"""
            Email stats for user {user.username}:
            Total available tasks: {total_tasks}
            Sample tasks for email: {sample_size}
            Total possible points: {total_points}
            Points per task range: {min(t['price'] for t in tasks) if tasks else 0} - {max(t['price'] for t in tasks) if tasks else 0}
        """)

        # Определяем тип задания (Post или Profile) на основе URL
        def get_task_type(url):
            # Если URL содержит status/ или post/ - это пост
            if 'status/' in url or 'post/' in url or 'pulse/' in url:
                return 'Post'
            return 'Profile'

        # Определяем социальную сеть на основе URL
        def get_social_network(url):
            if 'twitter.com' in url or 'x.com' in url:
                return 'Twitter'
            elif 'linkedin.com' in url:
                return 'LinkedIn'
            elif 'substack.com' in url:
                return 'Substack'
            return 'Social'

        # Получаем эмоджи для типа задания
        def get_task_emoji(task_type):
            emoji_map = {
                'FOLLOW': '👥',    # Люди/подписчики
                'LIKE': '❤️',      # Сердце для лайков
                'REPOST': '🔄',    # Репост/ретвит
                'COMMENT': '💬',   # Комментарий
                'SAVE': '🔖',      # Закладка
                'CONNECT': '🤝',   # Рукопожатие для соединения
                'RESTACK': '📢',   # Мегафон для рестака
                'UPVOTE': '⬆️',    # Стрелка вверх для апвоута
            }
            return emoji_map.get(task_type, '🎯')  # Если тип не найден, возвращаем цель

        # Формируем контекст для шаблона
        context = {
            'tasks': [{
                'type': task['type'],
                'price': task['price'],
                'post_url': task['post_url'],
                'display_type': f"{get_task_emoji(task['type'])} {task['type']} {get_social_network(task['post_url'])} {get_task_type(task['post_url'])}",
                'task_url': f"https://upvote.club/dashboard?email={user_email}"
            } for task in random_tasks],  # Используем только случайные задания для показа
            'site_url': settings.SITE_URL,
            'unsubscribe_url': unsubscribe_url,
            'user_email': user_email,
            'header': f'{total_tasks} Tasks & {total_points} Points available for you',
            'subheader': f'Complete all {total_tasks} tasks to earn {total_points} points! Here are {sample_size} random tasks for you.'
        }

        logger.info("Rendering email template")
        html_content = render_to_string('email/daily_tasks.html', context)
        
        email_service = EmailService()
        return email_service.send_email(
            to_email=user_email,
            subject=f'{total_tasks} Tasks & {total_points} Points available for you | upvote.club',
            html_content=html_content,
            unsubscribe_url=unsubscribe_url
        )

    except Exception as e:
        logger.error(f"General error in send_daily_tasks_email: {str(e)}")
        return False

def format_duration(duration):
    """
    Форматирует timedelta в строку вида '2d 22h 22m' или '22h 22m'
    Возвращает 'N/A' если duration is None
    """
    if not duration:
        return 'N/A'
        
    total_seconds = int(duration.total_seconds())
    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"

def send_task_completed_author_email(task):
    try:
        if task.email_sent:
            logger.info(f"Email already sent successfully for task {task.id}")
            return True
        
        if not task.creator:
            error_msg = f"No creator found for task {task.id}"
            logger.error(error_msg)
            task.log_email_status(False, error_msg)
            return False

        # Если есть предыдущая ошибка, логируем что пытаемся снова
        if task.email_send_error:
            logger.info(f"Retrying email send for task {task.id}. Previous error: {task.email_send_error}")

        # Получаем email из Firebase
        firebase_uid = task.creator.username
        creator_email = get_firebase_email(firebase_uid)
        
        if not creator_email:
            error_msg = f"Could not get Firebase email for user {task.creator.username} (task {task.id})"
            logger.error(error_msg)
            task.log_email_status(False, error_msg)
            return False

        # Проверяем подписку на уведомления
        subscription = UserEmailSubscription.objects.filter(
            user=task.creator,
            subscription_type__name='task_completed',
            is_subscribed=True
        ).first()
        
        if not subscription:
            error_msg = f"User {task.creator.username} not subscribed to task completion emails"
            logger.info(error_msg)
            task.log_email_status(False, error_msg)
            return False

        # Форматируем время завершения
        formatted_completion_time = format_duration(task.completion_duration)
        completion_hours = 0
        if task.completion_duration:
            completion_hours = task.completion_duration.total_seconds() / 3600
        logger.info(f"Formatted completion time for task {task.id}: {formatted_completion_time} ({completion_hours} hours)")

        # Формируем context для html шаблона
        context = {
            'task': task,
            'user': task.creator,
            'completion_time': formatted_completion_time,
            'completion_hours': completion_hours,
            'user_email': creator_email,
            'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        }
        logger.info(f"Rendering HTML email template for task completion (task_id={task.id})")
        html_content = render_to_string('email/task_completed_author.html', context)
        logger.info(f"HTML content rendered for task completion email (task_id={task.id}), length: {len(html_content)} chars")

        email_service = EmailService()
        result = email_service.send_email(
            to_email=creator_email,
            subject='Task completed',
            html_content=html_content,  # теперь html
            unsubscribe_url=context['unsubscribe_url'],
            bcc_email=['yes@upvote.club', 'yesupvote@gmail.com']
        )
        logger.info(f"BCC for task completion email will be sent to yes@upvote.club and yesupvote@gmail.com")
        
        if result:
            logger.info(f"Successfully sent plain text email for task {task.id}")
        
        task.log_email_status(result)
        return result

    except Exception as e:
        error_msg = f"Error sending completion email: {str(e)}"
        logger.error(error_msg)
        task.log_email_status(False, error_msg)
        return False

def send_task_deleted_due_to_link_email(task, refund_points):
    """
    Отправляет email автору задания, если оно удалено по причине недоступной ссылки (not_available)
    """
    try:
        if task.email_sent:
            logger.info(f"Email already sent successfully for task {task.id}")
            return True
        if not task.creator:
            error_msg = f"No creator found for task {task.id}"
            logger.error(error_msg)
            task.log_email_status(False, error_msg)
            return False
        # Получаем email из Firebase
        firebase_uid = task.creator.username
        creator_email = get_firebase_email(firebase_uid)
        if not creator_email:
            error_msg = f"Could not get Firebase email for user {task.creator.username} (task {task.id})"
            logger.error(error_msg)
            task.log_email_status(False, error_msg)
            return False
        # Проверяем подписку на уведомления
        subscription = UserEmailSubscription.objects.filter(
            user=task.creator,
            subscription_type__name='task_link_unavailable',
            is_subscribed=True
        ).first()
        if not subscription:
            error_msg = f"User {task.creator.username} not subscribed to task_link_unavailable emails"
            logger.info(error_msg)
            task.log_email_status(False, error_msg)
            return False
        unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        # Формируем context для html шаблона
        context = {
            'task': task,
            'user': task.creator,
            'refund_points': refund_points,
            'unsubscribe_url': unsubscribe_url
        }
        # Можно использовать отдельный шаблон, но для простоты пишем html прямо здесь
        html_content = (
            f"<p>Hello! This is upvote club team. Your task '<b>{task.get_type_display()}</b>' in <b>{task.social_network.name}</b> was <b>deleted</b> because the link in your task is unavailable. Users reported that the link does not work or is not accessible, so we removed this task from the platform. No worries, we have returned <b>+{refund_points}</b> points to <a href='https://upvote.club/dashboard/'>your balance</a> and restored <b>+1 free task slot</b>, so you can create it again with a working link. You can create a new task again <a href='https://upvote.club/dashboard/createtask?linkunavailable'>completely free</a>.</p>"
            f"<p>Your UpvoteClub Team</p>"
        )
        email_service = EmailService()
        result = email_service.send_email(
            to_email=creator_email,
            subject=f"Your {task.social_network.name} task was deleted due to unavailable link and +{refund_points} points are back",
            html_content=html_content,
            unsubscribe_url=unsubscribe_url,
            bcc_email=['yes@upvote.club', 'yesupvote@gmail.com']
        )
        if result:
            logger.info(f"Successfully sent task deleted email for task {task.id}")
        task.log_email_status(result)
        return result
    except Exception as e:
        error_msg = f"Error sending task deleted email: {str(e)}"
        logger.error(error_msg)
        task.log_email_status(False, error_msg)
        return False

def send_onboarding_email(user):
    """Отправляет plain text email с прогрессом онбординга"""
    try:
        logger.info(f"Starting onboarding email preparation for user {user.username}")
        
        # Получаем email из Firebase
        firebase_uid = user.username
        user_email = get_firebase_email(firebase_uid)
        
        if not user_email:
            logger.error(f"Could not get Firebase email for user {user.username}")
            return False
            
        logger.info(f"Retrieved email {user_email} for user {user.username}")
        
        # Получаем профиль пользователя
        user_profile = user.userprofile
        completed_tasks = TaskCompletion.objects.filter(user=user).count()
        
        # Создаем подписку для онбординг-писем если не существует
        subscription_type, created = EmailSubscriptionType.objects.get_or_create(
            name='onboarding',
            defaults={'description': 'Onboarding progress emails'}
        )
        
        subscription, created = UserEmailSubscription.objects.get_or_create(
            user=user,
            subscription_type=subscription_type,
            defaults={'is_subscribed': True}
        )
        
        unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        
        logger.info(f"Preparing plain text onboarding email for user: {user.username}")

        plain_text = (
            "Welcome to Upvote Club!\n\n"
            "Here you can:\n"
            "1. Create tasks to promote your accounts and posts on these social networks: Twitter, LinkedIn, Reddit, Medium, Quora, Substack, Product Hunt, Dev.to, Mastodon, GitHub, Indie Hackers and others.\n"
            "2. Get likes, reposts, comments, saves, upvotes and other actions (full list available on the platform).\n"
            "3. To create tasks, you need points (you can earn them by completing other users' tasks). You can also buy points from other users.\n"
            "4. Points can be sold within the system. If you don't need them — others do!\n\n"
            f"Start right now: https://upvote.club/dashboard\n\n"
            f"Unsubscribe from onboarding emails: {unsubscribe_url}\n"
            "yes@upvote.club"
        )

        email_service = EmailService()
        result = email_service.send_email(
            to_email=user_email,  # Используем email из Firebase
            subject='Welcome',
            html_content=plain_text,
            unsubscribe_url=unsubscribe_url
        )
        
        if result:
            logger.info(f"Onboarding plain text email sent successfully to {user_email}")
        else:
            logger.error(f"Failed to send onboarding plain text email to {user_email}")
            
        return result

    except Exception as e:
        logger.error(f"Error sending onboarding email for user {user.username}: {str(e)}")
        return False

def send_new_task_notification(task):
    """Отправляет уведомление о новом задании всем подписанным пользователям"""
    try:
        logger.info(f"""
            Starting new task notification process:
            Task ID: {task.id}
            Type: {task.type}
            Status: {task.status}
            Creator: {task.creator_id}
            URL: {task.post_url}
            Price: {task.price}
            Actions Required: {task.actions_required}
        """)

        # Получаем всех подписанных пользователей
        subscription_type = EmailSubscriptionType.objects.get(name='new_task')
        logger.info(f"Found subscription type 'new_task' with ID: {subscription_type.id}")

        subscriptions = UserEmailSubscription.objects.filter(
            subscription_type=subscription_type,
            is_subscribed=True
        ).select_related('user').exclude(user=task.creator)  # Исключаем создателя задания

        logger.info(f"Found {subscriptions.count()} subscribed users (excluding task creator)")

        success_count = 0
        failed_count = 0

        # Определяем тип задания (Post или Profile)
        def get_task_type(url):
            if 'status/' in url or 'post/' in url or 'pulse/' in url:
                return 'Post'
            return 'Profile'

        # Определяем социальную сеть
        def get_social_network(url):
            if 'twitter.com' in url or 'x.com' in url:
                return 'Twitter'
            elif 'linkedin.com' in url:
                return 'LinkedIn'
            elif 'substack.com' in url:
                return 'Substack'
            return 'Social'

        # Получаем эмоджи для типа задания
        def get_task_emoji(task_type):
            emoji_map = {
                'FOLLOW': '👥',
                'LIKE': '❤️',
                'REPOST': '🔄',
                'COMMENT': '💬',
                'SAVE': '🔖',
                'CONNECT': '🤝',
                'RESTACK': '📢',
                'UPVOTE': '⬆️',
            }
            return emoji_map.get(task_type, '🎯')

        for i, subscription in enumerate(subscriptions, 1):
            try:
                user = subscription.user
                logger.info(f"""
                    Processing user {i}/{subscriptions.count()}:
                    Username: {user.username}
                    Subscription ID: {subscription.id}
                """)

                user_email = get_firebase_email(user.username)

                if not user_email:
                    error_msg = f"Could not get Firebase email for user {user.username}"
                    logger.error(error_msg)
                    failed_count += 1
                    continue

                logger.info(f"Retrieved email {user_email} for user {user.username}")

                # Формируем контекст для шаблона
                context = {
                    'task': {
                        'type': task.type,
                        'price': task.price,
                        'post_url': task.post_url,
                        'display_type': f"{get_task_emoji(task.type)} {task.type} {get_social_network(task.post_url)} {get_task_type(task.post_url)}",
                        'task_url': f"https://upvote.club/dashboard?email={user_email}"
                    },
                    'user_email': user_email,
                    'unsubscribe_url': f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
                }

                logger.info(f"""
                    Email context prepared for user {user.username}:
                    Display Type: {context['task']['display_type']}
                    Task URL: {context['task']['task_url']}
                """)

                html_content = render_to_string('email/new_task.html', context)
                logger.info(f"Email template rendered for user {user.username}")

                email_service = EmailService()
                if email_service.send_email(
                    to_email=user_email,
                    subject=f'New Task & {task.price} points commes to you from upvote.club',
                    html_content=html_content,
                    unsubscribe_url=context['unsubscribe_url']
                ):
                    success_count += 1
                    logger.info(f"Successfully sent new task notification to {user_email}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to send new task notification to {user_email}")

                # Делаем паузу между отправками
                if i < subscriptions.count():
                    logger.info("Waiting 10 seconds before next email...")
                    time.sleep(10)

            except Exception as e:
                failed_count += 1
                logger.error(f"Error sending new task notification to user {user.username}: {str(e)}", exc_info=True)

        logger.info(f"""
            New task notification sending completed:
            Task ID: {task.id}
            Total subscribers: {subscriptions.count()}
            Successfully sent: {success_count}
            Failed: {failed_count}
        """)

        return True

    except Exception as e:
        logger.error(f"General error in send_new_task_notification: {str(e)}", exc_info=True)
        return False

def send_welcome_email(user):
    """Отправляет приветственное письмо с кнопкой подтверждения email"""
    try:
        logger.info(f"""
            Starting welcome email preparation:
            User ID: {user.id}
            Username: {user.username}
        """)
        
        # Получаем email из Firebase
        user_email = get_firebase_email(user.username)
        if not user_email:
            logger.error(f"Could not get Firebase email for user {user.username}")
            return False
            
        logger.info(f"Retrieved email {user_email} for user {user.username}")
        
        # Создаем подписку для welcome-писем если не существует
        subscription_type, created = EmailSubscriptionType.objects.get_or_create(
            name='welcome',
            defaults={'description': 'Welcome emails for new users'}
        )
        
        subscription, created = UserEmailSubscription.objects.get_or_create(
            user=user,
            subscription_type=subscription_type,
            defaults={'is_subscribed': True}
        )
        
        unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        
        logger.info(f"""
            Welcome email context preparation:
            User: {user.username}
            Email: {user_email}
            Subscription created: {created}
            Unsubscribe URL: {unsubscribe_url}
        """)

        # Формируем контекст для шаблона
        context = {
            'user': user,
            'user_email': user_email,
            'unsubscribe_url': unsubscribe_url
        }

        refresh_token = RefreshToken.for_user(user)
        tokenized_params = urlencode({
            'email': user_email,
            'confirm': 'true',
            'refresh': str(refresh_token),
            'access': str(refresh_token.access_token),
        })
        confirm_url = f"https://upvote.club/onboarding/country?{tokenized_params}"
        html_content = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827; background-color: #f9fafb; padding: 0; margin: 0;">
  <div style="max-width: 640px; margin: 0 auto; padding: 32px 24px;">
    <div style="background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); padding: 32px;">
      <h1 style="font-size: 16px; margin: 0 0 12px; color: #111827;">🧗‍♀️ Upvote Club: Confirm your email</h1>
      <p style="margin: 0 0 16px; color: #4b5563;">Click the button below to confirm your email and continue onboarding.</p>
      <div style="text-align: center; margin: 24px 0;">
        <a href="{confirm_url}" style="display: inline-block; padding: 14px 22px; background: #4f46e5; color: #fff; text-decoration: none; border-radius: 12px; font-weight: 600;">Confirm</a>
      </div>
            <p style="margin: 0 0 16px; color: #4b5563;">If this email in spam folder, please mark it as not spam.</p>
    </div>
  </div>
</body>
</html>
"""
        
        email_service = EmailService()
        result = email_service.send_email(
            to_email=user_email,
            subject='Upvote Club: Confirm your email',
            html_content=html_content,
            unsubscribe_url=unsubscribe_url
        )
        
        if result:
            logger.info(f"Welcome email sent successfully to {user_email}")
        else:
            logger.error(f"Failed to send welcome email to {user_email}")
            
        return result

    except Exception as e:
        logger.error(f"Error sending welcome email for user {user.username}: {str(e)}", exc_info=True)
        return False

def send_inviter_notification_email(inviter, invited_user):
    """
    Отправляет уведомление пользователю о том, что кто-то зарегистрировался по его инвайту
    
    Args:
        inviter: User object - пользователь, чей инвайт был использован
        invited_user: User object - новый зарегистрированный пользователь
    """
    try:
        from firebase_admin import auth
        email_service = EmailService()
        
        # Получаем email из Firebase по uid (который хранится в username)
        firebase_user = auth.get_user(inviter.username)
        inviter_email = firebase_user.email
        
        if not inviter_email:
            logger.error(f"[send_inviter_notification_email] No email found in Firebase for user {inviter.username}")
            return False
            
        context = {
            'inviter': inviter,
            'invited_user': invited_user,
            'site_url': settings.SITE_URL
        }
        
        success = email_service.send_email(
            to_email=inviter_email,
            subject='Someone joined Upvote Club using your invite!',
            html_content=render_to_string('email/new_invited_user.html', context)
        )
        
        if success:
            logger.info(f"[send_inviter_notification_email] Successfully sent notification to {inviter_email}")
        else:
            logger.warning(f"[send_inviter_notification_email] Failed to send notification to {inviter_email}")
            
        return success
        
    except Exception as e:
        logger.error(f"[send_inviter_notification_email] Error sending notification: {str(e)}", exc_info=True)
        return False

def send_weekly_recap_email(user, data):
    """
    Отправляет еженедельный отчет пользователю
    
    Args:
        user: User object
        data: dict с данными для шаблона:
            - total_tasks: int
            - tasks_change_percentage: float
            - networks: list[dict]
                - name: str
                - actions: list[dict]
                    - name: str
                    - count: int
                    - emoji: str
            - leaderboard: list[dict]
                - username: str
                - points: int
    """
    try:
        logger.info(f"Starting weekly recap email preparation for user {user.username}")
        
        # Получаем email из Firebase
        user_email = get_firebase_email(user.username)
        if not user_email:
            logger.error(f"Could not get Firebase email for user {user.username}")
            return False
            
        # Проверяем подписку пользователя
        subscription_type = EmailSubscriptionType.objects.get(name='weekly_recap')
        subscription = UserEmailSubscription.objects.get(
            user=user,
            subscription_type=subscription_type,
            is_subscribed=True
        )
        
        unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
        
        logger.info(f"""
            Weekly recap stats for user {user.username}:
            Total tasks: {data['total_tasks']}
            Change percentage: {data['tasks_change_percentage']}%
            Networks count: {len(data['networks'])}
            Leaderboard entries: {len(data['leaderboard'])}
        """)

        # Формируем контекст для шаблона
        context = {
            'user': user,
            'user_email': user_email,
            'unsubscribe_url': unsubscribe_url,
            **data  # Добавляем все данные из аргумента data
        }

        html_content = render_to_string('email/weekly_recap.html', context)
        
        email_service = EmailService()
        result = email_service.send_email(
            to_email=user_email,
            subject='Your Weekly Recap 📊',
            html_content=html_content,
            unsubscribe_url=unsubscribe_url
        )
        
        if result:
            logger.info(f"Successfully sent weekly recap to {user_email}")
        else:
            logger.error(f"Failed to send weekly recap to {user_email}")
            
        return result

    except Exception as e:
        logger.error(f"Error sending weekly recap for user {user.username}: {str(e)}")
        return False

def send_withdrawal_notification_email(withdrawal):
    """
    Отправляет уведомление администратору о новом запросе на вывод средств
    
    Args:
        withdrawal: Withdrawal object - объект запроса на вывод
    """
    try:
        logger.info(f"""
            Starting withdrawal notification email preparation:
            Withdrawal ID: {withdrawal.id}
            User: {withdrawal.user.username}
            Amount: ${withdrawal.amount_usd}
            Method: {withdrawal.withdrawal_method}
        """)
        
        # Получаем email пользователя из Firebase для дополнительной информации
        user_email = get_firebase_email(withdrawal.user.username)
        
        # Получаем текущий баланс пользователя
        current_balance = withdrawal.user.userprofile.balance
        
        # Формируем простое текстовое сообщение
        email_body = f"""
🔔 New Withdrawal Request

Withdrawal ID: #{withdrawal.id}
User: {withdrawal.user.username} (ID: {withdrawal.user.id})
User Email: {user_email or 'Not available'}

💰 Withdrawal Details:
Amount: ${withdrawal.amount_usd}
Points Sold: {withdrawal.points_sold} points
Method: {withdrawal.withdrawal_method}
Address: {withdrawal.withdrawal_address}
Status: {withdrawal.status}
Created: {withdrawal.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC

👤 User Info:
Current Balance: {current_balance} points
Conversion Rate: 1 point = $0.01 USD

⚠️ Action Required: Please review and process this withdrawal request in the admin panel.

---
This is an automated notification from Upvote.Club
"""

        logger.info(f"""
            Withdrawal notification details:
            Withdrawal ID: {withdrawal.id}
            User: {withdrawal.user.username} (ID: {withdrawal.user.id})
            User Email: {user_email}
            Amount: ${withdrawal.amount_usd}
            Points: {withdrawal.points_sold}
            Method: {withdrawal.withdrawal_method}
            Address: {withdrawal.withdrawal_address}
            Current Balance: {current_balance}
        """)

        email_service = EmailService()
        result = email_service.send_email(
            to_email='yes@upvote.club',
            subject=f'🔔 New Withdrawal Request #{withdrawal.id} - ${withdrawal.amount_usd} via {withdrawal.withdrawal_method}',
            html_content=email_body
        )
        
        if result:
            logger.info(f"Successfully sent withdrawal notification for withdrawal #{withdrawal.id} to yes@upvote.club")
        else:
            logger.error(f"Failed to send withdrawal notification for withdrawal #{withdrawal.id}")
            
        return result

    except Exception as e:
        logger.error(f"Error sending withdrawal notification for withdrawal #{withdrawal.id}: {str(e)}", exc_info=True)
        return False

def send_withdrawal_completed_email(withdrawal):
    """
    Отправляет пользователю письмо о том, что его вывод средств завершён
    Args:
        withdrawal: Withdrawal object - объект запроса на вывод
    """
    try:
        logger.info(f"""
            Starting withdrawal completed email preparation:
            Withdrawal ID: {withdrawal.id}
            User: {withdrawal.user.username}
            Amount: ${withdrawal.amount_usd}
            Method: {withdrawal.withdrawal_method}
        """)

        # Получаем email пользователя из Firebase
        user_email = get_firebase_email(withdrawal.user.username)
        if not user_email:
            logger.error(f"Could not get Firebase email for user {withdrawal.user.username}")
            return False

        # Проверяем подписку пользователя (если есть тип подписки, иначе просто отправляем)
        unsubscribe_url = None
        try:
            subscription_type = EmailSubscriptionType.objects.get(name='withdrawal_completed')
            subscription = UserEmailSubscription.objects.get(
                user=withdrawal.user,
                subscription_type=subscription_type,
                is_subscribed=True
            )
            unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
            logger.info(f"Unsubscribe URL found: {unsubscribe_url}")
        except Exception as e:
            logger.warning(f"No withdrawal_completed subscription found for user {withdrawal.user.username}: {str(e)}")

        # Формируем текст письма
        email_body = f"""
Your withdrawal of ${withdrawal.amount_usd} has been completed and the funds have been sent to you.

Thank you for using Upvote.Club!
"""
        logger.info(f"Prepared email body for withdrawal completed: {email_body.strip()}")

        email_service = EmailService()
        result = email_service.send_email(
            to_email=user_email,
            subject=f'Your withdrawal of ${withdrawal.amount_usd} is completed',
            html_content=email_body,
            unsubscribe_url=unsubscribe_url
        )

        if result:
            logger.info(f"Successfully sent withdrawal completed email to {user_email} for withdrawal #{withdrawal.id}")
        else:
            logger.error(f"Failed to send withdrawal completed email to {user_email} for withdrawal #{withdrawal.id}")

        return result

    except Exception as e:
        logger.error(f"Error sending withdrawal completed email for withdrawal #{withdrawal.id}: {str(e)}", exc_info=True)
        return False

def send_task_created_email(task):
    """
    Отправляет пользователю письмо о том, что его задание создано
    Args:
        task: Task object - объект созданного задания
    """
    try:
        logger.info(f"""
            Starting task created email preparation:
            Task ID: {task.id}
            User: {task.creator.username}
            Type: {task.type}
            Social Network: {task.social_network.name}
            Actions Required: {task.actions_required}
        """)

        # Получаем email пользователя из Firebase
        user_email = get_firebase_email(task.creator.username)
        if not user_email:
            logger.error(f"Could not get Firebase email for user {task.creator.username}")
            return False

        # Проверяем подписку пользователя (если есть тип подписки, иначе просто отправляем)
        unsubscribe_url = None
        try:
            subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
                name='task_created',
                defaults={'description': 'Task creation confirmation emails'}
            )
            subscription, _ = UserEmailSubscription.objects.get_or_create(
                user=task.creator,
                subscription_type=subscription_type,
                defaults={'is_subscribed': True}
            )
            unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
            logger.info(f"Unsubscribe URL found: {unsubscribe_url}")
        except Exception as e:
            logger.warning(f"No task_created subscription found for user {task.creator.username}: {str(e)}")

        # Получаем название действия в человекочитаемом виде
        action_name = task.type.upper()
        action_label = action_name.title()
        
        # Формируем subject и ссылки
        subject = f"Your task is live - {task.social_network.name} {action_name}"
        network = task.social_network.name
        qty = task.actions_required
        upgrade_url = f"{settings.SITE_URL}/dashboard/subscribe?plan=MATE&billing=monthly#payment"
        tasks_url = f"{settings.SITE_URL}/dashboard/tasks"
        
        # Формируем HTML контент письма
        html_content = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
      
      <h2 style="color: #2563eb; margin: 0 0 10px 0;">Your task is live 🎉</h2>
      <p style="margin: 0 0 16px 0; color: #374151;">
        We&apos;ve received your request and it&apos;s now visible to the Upvote Club community.
      </p>

      <div style="background-color: #f3f4f6; padding: 16px; border-radius: 10px; margin: 18px 0;">
        <p style="margin: 0 0 10px 0; font-weight: 700;">Task details</p>
        <p style="margin: 6px 0;"><b>Network:</b> {network}</p>
        <p style="margin: 6px 0;"><b>Action:</b> {action_label}</p>
        <p style="margin: 6px 0;"><b>Quantity:</b> {qty}</p>
        <p style="margin: 6px 0;"><b>Plan:</b> Free</p>

        <div style="margin-top: 12px;">
          <a href="{upgrade_url}" style="color: #2563eb; text-decoration: none; font-weight: 700;">
            Want more? Upgrade to Premium
          </a>
          <span style="color: #374151;">and get up to 7,500 {network} actions.</span>
        </div>
      </div>

      <div style="margin: 18px 0;">
        <p style="margin: 0 0 10px 0; font-weight: 700;">Upgrade for $1</p>
        <p style="margin: 0 0 14px 0; color: #374151;">
          Unlock unlimited task creation and get <b>15,000 bonus points</b> added to your balance.
        </p>

        <a href="{upgrade_url}"
           style="display: inline-block; background-color: #2563eb; color: #ffffff; padding: 12px 16px; border-radius: 10px; text-decoration: none; font-weight: 700;">
          Upgrade now
        </a>
      </div>

      <div style="margin-top: 22px;">
        <a href="{tasks_url}"
           style="display: inline-block; background-color: #111827; color: #ffffff; padding: 12px 16px; border-radius: 10px; text-decoration: none; font-weight: 700;">
          View your tasks
        </a>
      </div>

      <div style="margin-top: 26px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280;">
        <p style="margin: 0 0 8px 0;">Questions? Reply to this email or contact us at yes@upvote.club</p>
        {f'<p style="margin: 0;"><a href="{unsubscribe_url}" style="color: #6b7280;">Unsubscribe</a></p>' if unsubscribe_url else ''}
      </div>

    </div>
  </body>
</html>
"""
        
        logger.info(f"Prepared email for task created: {subject}")
        email_service = EmailService()
        result = email_service.send_email(
            to_email=user_email,
            subject=subject,
            html_content=html_content,
            unsubscribe_url=unsubscribe_url
        )

        if result:
            logger.info(f"Successfully sent task created email to {user_email} for task #{task.id}")
        else:
            logger.error(f"Failed to send task created email to {user_email} for task #{task.id}")

        return result

    except Exception as e:
        logger.error(f"Error sending task created email for task #{task.id}: {str(e)}", exc_info=True)
        return False