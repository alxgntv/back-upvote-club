import tweepy
from django.conf import settings
import logging
from django.db.models import F, Q
from django.utils import timezone
import time
from .models import UserProfile, Task, TwitterServiceAccount, TaskCompletion, TwitterUserMapping
from twitter_auth.models import TwitterUserAuthorization, TwitterActionLog
import random
from .models import Task, TaskCompletion, TwitterServiceAccount, TwitterUserMapping

logger = logging.getLogger('api.auto_actions')

class TwitterAutoActions:
    def __init__(self, user_profile: UserProfile):
        self.user_profile = user_profile
        self.client = None
        self.current_api_account = None

    def initialize_client(self) -> bool:
        try:
            current_time = timezone.now()
            
            # Получаем только активные авторизации
            # Изменяем проверку rate_limit_reset - аккаунт доступен если:
            # - rate_limit_reset не установлен (None)
            # - rate_limit_reset в прошлом
            auths = TwitterUserAuthorization.objects.filter(
                user_profile=self.user_profile,
                service_account__is_active=True
            ).filter(
                Q(service_account__rate_limit_reset__isnull=True) |
                Q(service_account__rate_limit_reset__lt=current_time)
            ).select_related('service_account')
            
            if not auths.exists():
                next_reset = TwitterUserAuthorization.objects.filter(
                    user_profile=self.user_profile,
                    service_account__is_active=True,
                    service_account__rate_limit_reset__gt=current_time
                ).order_by('service_account__rate_limit_reset').first()
                
                if next_reset:
                    logger.info(f"""
                        All accounts are rate limited
                        Next reset at: {next_reset.service_account.rate_limit_reset}
                        Current time: {current_time}
                        Waiting time: {next_reset.service_account.rate_limit_reset - current_time}
                    """)
                return False
                
            # Берем авторизацию с самым старым использованием
            auth = auths.order_by('service_account__last_used_at').first()
            
            if not auth:
                logger.error(f"No available API accounts for user {self.user_profile.id}")
                return False
            
            self.current_api_account = auth.service_account
            self.current_api_account.last_used_at = current_time
            self.current_api_account.save()
            
            self.client = tweepy.Client(
                consumer_key=self.current_api_account.api_key,
                consumer_secret=self.current_api_account.api_secret,
                access_token=auth.oauth_token,
                access_token_secret=auth.oauth_token_secret
            )

            logger.info(f"""
                Initialized client:
                User Profile: {self.user_profile.id}
                API Account: {self.current_api_account.id}
                Last used: {self.current_api_account.last_used_at}
                Rate limit reset: {self.current_api_account.rate_limit_reset}
            """)

            return True

        except Exception as e:
            logger.error(f"Error initializing client: {str(e)}")
            return False

    def handle_rate_limit(self, e: Exception) -> bool:
        """
        Обрабатывает rate limit и ошибки авторизации
        """
        if hasattr(e, 'response'):
            if e.response.status_code == 429:
                headers = e.response.headers
                reset_time = headers.get('x-rate-limit-reset')
                
                if reset_time and self.current_api_account:
                    try:
                        reset_timestamp = int(reset_time)
                        reset_datetime = timezone.datetime.fromtimestamp(
                            reset_timestamp, 
                            tz=timezone.utc
                        )
                        
                        # Обновляем rate_limit_reset
                        self.current_api_account.rate_limit_reset = reset_datetime
                        self.current_api_account.save()
                        
                        logger.info(f"""
                            Rate limit updated:
                            API Account: {self.current_api_account.id}
                            Reset time: {reset_datetime}
                        """)
                        
                        time.sleep(5)  # Добавляем задержку перед повторной инициализацией
                        return self.initialize_client()
                        
                    except ValueError as ve:
                        logger.error(f"Error parsing rate limit reset time: {ve}")
                        
            elif e.response.status_code == 401:
                logger.error(f"""
                    Unauthorized error - deactivating authorization:
                    API Account: {self.current_api_account.id}
                    User Profile: {self.user_profile.id}
                """)
                
                # Деактивируем авторизацию
                auth = TwitterUserAuthorization.objects.filter(
                    user_profile=self.user_profile,
                    service_account=self.current_api_account
                ).first()
                
                if auth:
                    auth.delete()
                    
                # Логируем количество оставшихся авторизаций
                active_auths = TwitterUserAuthorization.objects.filter(
                    user_profile=self.user_profile,
                    service_account__is_active=True
                ).count()
                
                logger.info(f"""
                    Remaining active authorizations after deactivation:
                    User Profile: {self.user_profile.id}
                    Active authorizations: {active_auths}
                """)
                
                time.sleep(5)  # Добавляем задержку перед повторной инициализацией
                return self.initialize_client()
                    
        return False

    def perform_action(self, task: Task) -> bool:
        """
        Выполняет одно действие для задания
        """
        if not self.current_api_account:
            logger.error("No API account available")
            return False
        
        try:
            if task.type == 'FOLLOW':
                logger.info(f"""
                    Performing FOLLOW action:
                    API Account: {self.current_api_account.id}
                    Task ID: {task.id}
                    User: {self.user_profile.twitter_account}
                    Target User ID: {task.target_user_id}
                """)
                
                response = self.client.follow_user(target_user_id=task.target_user_id)
                
                if not response or not hasattr(response, 'data'):
                    logger.error(f"""
                        Invalid response:
                        Task ID: {task.id}
                        Response: {response}
                    """)
                    return False
                    
                TaskCompletion.objects.create(
                    task=task,
                    user=self.user_profile.user,
                    action=task.type,
                    completed_at=timezone.now(),
                    metadata={
                        'api_account_id': self.current_api_account.id,
                        'response_data': response.data,
                        'target_user_id': task.target_user_id
                    },
                    is_auto=True
                )
                
                task.actions_completed = F('actions_completed') + 1
                task.save()
                task.refresh_from_db()
                
                self.current_api_account.last_used_at = timezone.now()
                self.current_api_account.save()
                
                logger.info(f"""
                    Action completed:
                    Task ID: {task.id}
                    Actions completed: {task.actions_completed}/{task.actions_required}
                """)
                
                if task.actions_completed >= task.actions_required:
                    task.status = 'COMPLETED'
                    task.completed_at = timezone.now()
                    task.completion_duration = task.completed_at - task.created_at
                    task.save()
                    logger.info(f"Task {task.id} completed fully")
                
                # Логируем попытку
                TwitterActionLog.objects.create(
                    user_profile=self.user_profile,
                    service_account=self.current_api_account,
                    task=task,
                    action_type=task.type,
                    status='SUCCESS',
                    target_user=task.twitter_url
                )
                
                return True
                
        except tweepy.errors.TweepyException as e:
            logger.error(f"""
                Action failed:
                Task ID: {task.id}
                Error: {e.response.status_code if hasattr(e, 'response') else str(e)}
                {str(e)}
            """)
            
            if self.handle_rate_limit(e):
                return self.perform_action(task)
            
            return False
            
        except Exception as e:
            status = 'RATE_LIMIT' if 'Rate limit exceeded' in str(e) else 'ERROR'
            
            # Логируем ошибку
            TwitterActionLog.objects.create(
                user_profile=self.user_profile,
                service_account=self.current_api_account,
                task=task,
                action_type=task.type,
                status=status,
                error_message=str(e),
                target_user=task.twitter_url
            )
            
            logger.error(f"Error performing action: {str(e)}")
            return False
            
        return False

def process_auto_actions():
    """
    Обработка автоматических действий - только последнее активное задание
    """
    logger.info(f"Starting auto actions processing: {timezone.now()}")
    time.sleep(17)
    
    try:
        current_time = timezone.now()
        
        # Проверяем есть ли доступные аккаунты не под rate limit
        available_accounts = TwitterServiceAccount.objects.filter(
            Q(rate_limit_reset__isnull=True) |
            Q(rate_limit_reset__lt=current_time),
            is_active=True
        ).exists()
        
        if not available_accounts:
            next_reset = TwitterServiceAccount.objects.filter(
                rate_limit_reset__gt=current_time,
                is_active=True
            ).order_by('rate_limit_reset').first()
            
            if next_reset:
                logger.info(f"""
                    All service accounts are rate limited
                    Current time: {current_time}
                    Next reset at: {next_reset.rate_limit_reset}
                    Waiting time: {next_reset.rate_limit_reset - current_time}
                """)
            return

        # Получаем только последнее активное незавершенное задание
        latest_task = Task.objects.filter(
            status='ACTIVE',
            type='FOLLOW',
            actions_completed__lt=F('actions_required')
        ).order_by('-created_at').first()
        
        if not latest_task:
            logger.info("No active incomplete tasks found")
            return
            
        logger.info(f"""
            Processing latest task:
            Task ID: {latest_task.id}
            Type: {latest_task.type}
            URL: {latest_task.post_url}
            Target User ID: {latest_task.target_user_id}
            Remaining actions: {latest_task.actions_required - latest_task.actions_completed}
        """)
        
        # Если нет target_user_id, пытаемся получить его
        if not latest_task.target_user_id:
            username = latest_task.post_url.split('/')[-1]
            
            # Проверяем существующий маппинг
            mapping = TwitterUserMapping.objects.filter(username=username).first()
            if mapping:
                latest_task.target_user_id = mapping.twitter_id
                latest_task.save()
                logger.info(f"Updated task {latest_task.id} with cached Twitter ID {mapping.twitter_id}")
            else:
                # Находим подходящего пользователя для получения ID
                available_user = UserProfile.objects.filter(
                    auto_actions_enabled=True,
                    twitter_verification_status='CONFIRMED',
                    twitteruserauthorization__isnull=False,
                    twitteruserauthorization__service_account__is_active=True
                ).order_by('last_auto_action_at').first()
                
                if not available_user:
                    logger.error("No available users found for getting Twitter ID")
                    return
                    
                handler = TwitterAutoActions(available_user)
                if not handler.initialize_client():
                    logger.error(f"Could not initialize client for user {available_user.id}")
                    return
                    
                try:
                    response = handler.client.get_user(username=username)
                    if response and response.data:
                        user_id = str(response.data.id)
                        
                        # Сохраняем маппинг
                        TwitterUserMapping.objects.create(
                            username=username,
                            twitter_id=user_id
                        )
                        
                        # Обновляем задание
                        latest_task.target_user_id = user_id
                        latest_task.save()
                        
                        # Обновляем last_auto_action_at
                        available_user.last_auto_action_at = timezone.now()
                        available_user.save()
                        
                        time.sleep(5)
                    else:
                        logger.error(f"Could not get Twitter ID for task {latest_task.id}, username: {username}")
                        return
                        
                except Exception as e:
                    logger.error(f"Error getting Twitter ID: {str(e)}")
                    return

        if not latest_task.target_user_id:
            logger.error(f"Could not get target_user_id for task {latest_task.id}")
            return

        # Получаем всех доступных пользователей для задания
        available_users = UserProfile.objects.filter(
            auto_actions_enabled=True,
            twitter_verification_status='CONFIRMED',
            twitteruserauthorization__isnull=False,
            twitteruserauthorization__service_account__is_active=True
        ).exclude(
            user__taskcompletion__task=latest_task
        ).exclude(
            twitter_account=latest_task.post_url.split('/')[-1]
        ).order_by('last_auto_action_at')
        
        if not available_users.exists():
            logger.info(f"No available users found for task {latest_task.id}")
            return
            
        logger.info(f"Found {available_users.count()} available users for task {latest_task.id}")
        
        # Пытаемся выполнить задание каждым доступным пользователем
        for available_user in available_users:
            handler = TwitterAutoActions(available_user)
            if not handler.initialize_client():
                logger.error(f"Could not initialize client for user {available_user.id}")
                time.sleep(2)
                continue
                
            success = handler.perform_action(latest_task)
            if success:
                available_user.last_auto_action_at = timezone.now()
                available_user.save()
                logger.info(f"Action completed successfully for task {latest_task.id} by user {available_user.id}")
                time.sleep(5)
            else:
                logger.error(f"Failed to complete action for task {latest_task.id} by user {available_user.id}")
                continue
                
    except Exception as e:
        logger.error(f"Error in auto actions processing: {str(e)}")