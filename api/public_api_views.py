"""
Публичный API для создания заданий через API ключи
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import (
    ApiKey, 
    Task, 
    UserProfile, 
    SocialNetwork
)
from .serializers import TaskSerializer, CrowdTaskSerializer
from .utils.email_utils import send_task_created_email
from .constants import BONUS_ACTION_COUNTRIES, BONUS_ACTION_RATE
import logging
import hashlib
import secrets
import hmac

logger = logging.getLogger('api')


def _hash_api_key(key: str) -> str:
    """Хеширует API ключ для безопасного хранения"""
    return hashlib.sha256(key.encode()).hexdigest()


def _verify_api_key(key: str, key_hash: str) -> bool:
    """Проверяет соответствие ключа хешу"""
    return hmac.compare_digest(_hash_api_key(key), key_hash)


def _get_api_key_from_request(request):
    """
    Извлекает API ключ из запроса.
    Проверяет заголовок X-API-Key или параметр api_key
    """
    api_key = request.headers.get('X-API-Key') or request.data.get('api_key') or request.GET.get('api_key')
    return api_key


def _authenticate_api_key(api_key: str):
    """
    Аутентифицирует API ключ и возвращает связанный ApiKey объект
    """
    if not api_key:
        return None
    
    try:
        # Ищем ключ по хешу
        key_hash = _hash_api_key(api_key)
        api_key_obj = ApiKey.objects.select_related('user', 'user__userprofile').get(
            key_hash=key_hash,
            is_active=True
        )
        
        # Проверяем, не истек ли срок действия
        if api_key_obj.is_expired():
            logger.warning(f"[public_api] API key expired for user {api_key_obj.user.id}")
            return None
        
        # Обновляем время последнего использования
        api_key_obj.last_used_at = timezone.now()
        api_key_obj.save(update_fields=['last_used_at'])
        
        logger.info(f"[public_api] API key authenticated for user {api_key_obj.user.id}")
        return api_key_obj
    except ApiKey.DoesNotExist:
        logger.warning(f"[public_api] Invalid API key attempted")
        return None
    except Exception as e:
        logger.error(f"[public_api] Error authenticating API key: {str(e)}", exc_info=True)
        return None


def _normalize_url(raw_url: str) -> str:
    """Normalize URL for duplicate detection.
    Rules:
      - ignore query and fragment
      - lowercase hostname
      - drop trailing '/'
      - treat http/https as the same (ignore scheme)
      - strip leading 'www.'
    Returns a comparison key in the form 'host/path'.
    """
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(raw_url)
        netloc = parts.netloc.lower()
        # unify common mobile/bare subdomains
        for prefix in ('www.', 'm.', 'mobile.', 'vm.'):
            if netloc.startswith(prefix):
                netloc = netloc[len(prefix):]
                break
        # map known domain aliases to a canonical host
        if netloc in {'youtu.be', 'youtube-nocookie.com'}:
            netloc = 'youtube.com'
        path = parts.path.rstrip('/') if parts.path != '/' else ''
        return f"{netloc}{path}"
    except Exception:
        safe = (raw_url or '')
        # remove scheme
        if '://' in safe:
            safe = safe.split('://', 1)[1]
        # strip query/fragment
        safe = safe.split('#')[0].split('?')[0]
        safe = safe.rstrip('/')
        # strip common prefixes
        for prefix in ('www.', 'm.', 'mobile.', 'vm.'):
            if safe.startswith(prefix):
                safe = safe[len(prefix):]
                break
        # normalize known domain aliases without full parsing
        safe = safe.lower()
        host, _, rest = safe.partition('/')
        if host in {'youtu.be', 'youtube-nocookie.com'}:
            host = 'youtube.com'
        return host + (('/' + rest) if rest else '')


@api_view(['GET'])
@permission_classes([AllowAny])  # Разрешаем доступ, но проверяем аутентификацию внутри
def list_api_keys(request):
    """
    Возвращает список всех API ключей пользователя.
    Требует аутентификации через JWT токен в заголовке Authorization.
    """
    from rest_framework.permissions import IsAuthenticated
    from rest_framework_simplejwt.authentication import JWTAuthentication
    
    # Пытаемся аутентифицировать пользователя через JWT
    try:
        authenticator = JWTAuthentication()
        auth_result = authenticator.authenticate(request)
        if auth_result:
            user, token = auth_result
        else:
            # Если не удалось аутентифицировать через JWT, проверяем request.user
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                return Response(
                    {
                        'success': False,
                        'error': 'Authentication required. Please provide a valid JWT token in Authorization header.'
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            user = request.user
    except Exception as e:
        logger.error(f"[public_api] Error authenticating user for listing API keys: {str(e)}")
        return Response(
            {
                'success': False,
                'error': 'Authentication required. Please provide a valid JWT token.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Получаем только активный ключ пользователя (или последний созданный, если активных нет)
        # У пользователя может быть только один активный ключ
        active_key = ApiKey.objects.filter(user=user, is_active=True).order_by('-created_at').first()
        
        keys_data = []
        
        if active_key:
            # Показываем только часть хеша для идентификации (безопасно)
            key_hash_preview = active_key.key_hash[:8] + '...' + active_key.key_hash[-4:] if len(active_key.key_hash) > 12 else active_key.key_hash[:8] + '...'
            
            keys_data.append({
                'id': active_key.id,
                'name': active_key.name,
                'key_preview': key_hash_preview,
                'is_active': active_key.is_active,
                'is_expired': active_key.is_expired(),
                'created_at': active_key.created_at,
                'last_used_at': active_key.last_used_at,
                'expires_at': active_key.expires_at
            })
        
        logger.info(f"[public_api] Listed API key for user {user.id}: {'found' if active_key else 'not found'}")
        
        return Response({
            'success': True,
            'keys': keys_data,
            'count': len(keys_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[public_api] Error listing API keys: {str(e)}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Failed to list API keys'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Разрешаем доступ, но проверяем аутентификацию внутри
def generate_api_key(request):
    """
    Генерирует новый API ключ для пользователя.
    Требует аутентификации через JWT токен в заголовке Authorization.
    """
    from rest_framework.permissions import IsAuthenticated
    from rest_framework_simplejwt.authentication import JWTAuthentication
    
    # Пытаемся аутентифицировать пользователя через JWT
    try:
        authenticator = JWTAuthentication()
        auth_result = authenticator.authenticate(request)
        if auth_result:
            user, token = auth_result
        else:
            # Если не удалось аутентифицировать через JWT, проверяем request.user
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                return Response(
                    {
                        'success': False,
                        'error': 'Authentication required. Please provide a valid JWT token in Authorization header.'
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            user = request.user
    except Exception as e:
        logger.error(f"[public_api] Error authenticating user for API key generation: {str(e)}")
        return Response(
            {
                'success': False,
                'error': 'Authentication required. Please provide a valid JWT token.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        name = request.data.get('name', '')
        
        with transaction.atomic():
            # Проверяем, есть ли уже активный ключ у пользователя
            existing_active_key = ApiKey.objects.filter(
                user=user,
                is_active=True
            ).first()
            
            if existing_active_key:
                # Деактивируем существующий ключ
                existing_active_key.is_active = False
                existing_active_key.save(update_fields=['is_active'])
                logger.info(f"[public_api] Deactivated existing API key {existing_active_key.id} for user {user.id}")
            
            # Генерируем уникальный API ключ
            api_key = f"upv_{secrets.token_urlsafe(32)}"
            key_hash = _hash_api_key(api_key)
            
            # Проверяем уникальность хеша (на всякий случай)
            while ApiKey.objects.filter(key_hash=key_hash).exists():
                api_key = f"upv_{secrets.token_urlsafe(32)}"
                key_hash = _hash_api_key(api_key)
            
            # Создаем запись API ключа (сохраняем только хеш, оригинальный ключ не храним)
            api_key_obj = ApiKey.objects.create(
                user=user,
                key_hash=key_hash,
                name=name,
                is_active=True
            )
            
            logger.info(f"[public_api] Generated API key for user {user.id}, key_id={api_key_obj.id}")
            
            message = 'API key generated successfully. Save this key securely - it will not be shown again.'
            if existing_active_key:
                message += ' Your previous API key has been deactivated.'
            
            return Response({
                'success': True,
                'api_key': api_key,  # Возвращаем ключ только один раз при создании
                'key_id': api_key_obj.id,
                'name': api_key_obj.name,
                'created_at': api_key_obj.created_at,
                'message': message,
                'previous_key_deactivated': bool(existing_active_key)
            }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"[public_api] Error generating API key: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to generate API key'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def create_task_via_api(request):
    """
    Создает задание через публичный API используя API ключ.
    Требует заголовок X-API-Key или параметр api_key.
    """
    logger.info(f"[public_api] create_task_via_api called")
    
    # Аутентифицируем API ключ
    api_key_str = _get_api_key_from_request(request)
    api_key_obj = _authenticate_api_key(api_key_str)
    
    if not api_key_obj:
        return Response(
            {
                'success': False,
                'error': 'Invalid or missing API key. Provide X-API-Key header or api_key parameter.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    user = api_key_obj.user
    
    # Проверяем наличие всех необходимых полей
    required_fields = ['post_url', 'type', 'price', 'actions_required', 'social_network_code']
    missing_fields = [field for field in required_fields if field not in request.data]
    if missing_fields:
        return Response(
            {
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user_profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        logger.error(f"[public_api] UserProfile not found for user {user.id}")
        return Response(
            {'success': False, 'error': 'User profile not found'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Проверяем доступные задания
    if user_profile.available_tasks <= 0:
        return Response(
            {
                'success': False,
                'error': 'No available tasks left. Please purchase more tasks.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Проверяем, нет ли уже активного задания с таким URL + TYPE + SOCIAL_NETWORK
    post_url = request.data.get('post_url')
    task_type = request.data.get('type')
    social_network_code = request.data.get('social_network_code')
    
    # Нормализуем входящий URL
    normalized_post_url = _normalize_url(post_url)
    
    # Получаем социальную сеть для проверки
    try:
        social_network = SocialNetwork.objects.get(code=social_network_code)
    except SocialNetwork.DoesNotExist:
        return Response(
            {
                'success': False,
                'error': f'Social network with code {social_network_code} not found'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Ищем активные задания с той же комбинацией URL + TYPE + SOCIAL_NETWORK
    active_tasks = Task.objects.filter(
        status='ACTIVE',
        type=task_type,
        social_network=social_network
    ).only('id', 'post_url')
    
    for task in active_tasks:
        if _normalize_url(task.post_url) == normalized_post_url:
            return Response({
                'success': False,
                'error': 'A task with this URL and action type already exists and is being completed by our community',
                'existing_task_id': task.id
            }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Получаем свежую версию профиля для атомарного обновления
            user_profile = UserProfile.objects.select_for_update().get(pk=user_profile.pk)
            
            # Вычисляем стоимость с учетом скидки и оригинальную стоимость
            price = request.data.get('price')
            actions_required = request.data.get('actions_required')
            discounted_cost, original_cost = user_profile.calculate_task_cost(price, actions_required)
            
            # Проверяем баланс с учетом скидки
            if discounted_cost > user_profile.balance:
                return Response(
                    {
                        'success': False,
                        'error': 'Insufficient balance to create task',
                        'required_balance': discounted_cost,
                        'current_balance': user_profile.balance
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Создаем сериализатор с данными
            serializer = TaskSerializer(data=request.data)
            if not serializer.is_valid():
                # Форматируем ошибки в читаемую строку
                error_messages = []
                for field, errors in serializer.errors.items():
                    if isinstance(errors, list):
                        for error in errors:
                            if isinstance(error, dict):
                                error_messages.append(f"{field}: {', '.join(str(v) for v in error.values())}")
                            else:
                                error_messages.append(f"{field}: {str(error)}")
                    else:
                        error_messages.append(f"{field}: {str(errors)}")
                
                error_detail = '; '.join(error_messages) if error_messages else 'Validation error'
                return Response(
                    {
                        'success': False,
                        'error': error_detail
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Списываем баланс с учетом скидки
            user_profile.balance -= discounted_cost
            user_profile.save(update_fields=['balance'])
            
            # Рассчитываем бонусные действия для выбранных стран
            chosen_country = (user_profile.chosen_country or user_profile.country_code or '').upper()
            try:
                base_actions_required = int(actions_required)
            except Exception:
                base_actions_required = actions_required
            bonus_actions = 0
            if chosen_country and chosen_country in BONUS_ACTION_COUNTRIES:
                try:
                    bonus_actions = int(round(base_actions_required * BONUS_ACTION_RATE))
                except Exception:
                    bonus_actions = 0
            
            # Сохраняем задание с оригинальной ценой и бонусными действиями
            task = serializer.save(
                creator=user,
                original_price=original_cost,
                price=price,
                status='ACTIVE',
                bonus_actions=bonus_actions,
                bonus_actions_completed=0
            )
            
            # Уменьшаем количество доступных заданий
            user_profile.decrease_available_tasks()
            
            # Отправляем email о создании задания
            try:
                send_task_created_email(task)
            except Exception as e:
                logger.error(f"[public_api] Error sending task created email: {str(e)}")
            
            logger.info(f"[public_api] Task created successfully via API: task_id={task.id}, user_id={user.id}")
            
            # Получаем crowd_tasks если они есть
            crowd_tasks_data = []
            if task.task_type == 'CROWD' and task.crowd_tasks.exists():
                from .serializers import CrowdTaskSerializer
                crowd_tasks_data = CrowdTaskSerializer(task.crowd_tasks.all(), many=True).data
            
            response_data = {
                'success': True,
                'task_id': task.id,
                'message': 'Task created successfully',
                'task': {
                    'id': task.id,
                    'status': task.status,
                    'post_url': task.post_url,
                    'type': task.type,
                    'task_type': task.task_type,
                    'social_network_code': social_network_code,
                    'actions_required': task.actions_required,
                    'actions_completed': task.actions_completed,
                    'bonus_actions': task.bonus_actions,
                    'bonus_actions_completed': task.bonus_actions_completed,
                    'price': task.price,
                    'original_price': task.original_price,
                    'created_at': task.created_at
                }
            }
            
            # Добавляем crowd_tasks в ответ, если они есть
            if crowd_tasks_data:
                response_data['task']['crowd_tasks'] = crowd_tasks_data
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
    except ValidationError as e:
        logger.error(f"[public_api] Validation error creating task: {str(e)}")
        return Response(
            {
                'success': False,
                'error': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"[public_api] Error creating task via API: {str(e)}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Error creating task. Please try again later.'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def create_crowd_task_via_api(request):
    """
    Создает crowd-задачу через публичный API по API-ключу.
    Требуется X-API-Key или параметр api_key.
    Поддерживает только задачи типа COMMENT, автоматически проставляет task_type=CROWD.
    """
    logger.info("[public_api] create_crowd_task_via_api called")

    api_key_str = _get_api_key_from_request(request)
    api_key_obj = _authenticate_api_key(api_key_str)

    if not api_key_obj:
        return Response(
            {
                'success': False,
                'error': 'Invalid or missing API key. Provide X-API-Key header or api_key parameter.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    user = api_key_obj.user

    required_fields = ['post_url', 'price', 'social_network_code', 'crowd_tasks_data']
    missing_fields = [field for field in required_fields if field not in request.data]
    if missing_fields:
        return Response(
            {
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    post_url = request.data.get('post_url')
    social_network_code = request.data.get('social_network_code')
    crowd_tasks_data = request.data.get('crowd_tasks_data')
    is_pinned = bool(request.data.get('is_pinned', False))

    # Валидируем action type: разрешаем только COMMENT для крауд-задач
    action_type = str(request.data.get('type', 'COMMENT')).upper()
    if action_type != 'COMMENT':
        return Response(
            {
                'success': False,
                'error': 'Crowd tasks support only action type COMMENT'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Валидация crowd_tasks_data
    if not isinstance(crowd_tasks_data, list) or len(crowd_tasks_data) == 0:
        return Response(
            {
                'success': False,
                'error': 'crowd_tasks_data must be a non-empty list of items with "text"'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    for item in crowd_tasks_data:
        if not isinstance(item, dict) or 'text' not in item or not str(item['text']).strip():
            return Response(
                {
                    'success': False,
                    'error': 'Each crowd task must contain non-empty "text" field'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    try:
        price = int(request.data.get('price'))
    except (TypeError, ValueError):
        return Response(
            {
                'success': False,
                'error': 'price must be a positive integer'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if price <= 0:
        return Response(
            {
                'success': False,
                'error': 'price must be greater than 0'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        social_network = SocialNetwork.objects.get(code=social_network_code)
    except SocialNetwork.DoesNotExist:
        return Response(
            {
                'success': False,
                'error': f'Social network with code {social_network_code} not found'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        logger.error(f"[public_api] UserProfile not found for user {user.id}")
        return Response(
            {'success': False, 'error': 'User profile not found'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    if user_profile.available_tasks <= 0:
        return Response(
            {
                'success': False,
                'error': 'No available tasks left. Please purchase more tasks.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Рассчитываем actions_required: если не передан или <=0 — ставим по количеству crowd-комментариев
    actions_required_raw = request.data.get('actions_required')
    try:
        actions_required = int(actions_required_raw) if actions_required_raw is not None else len(crowd_tasks_data)
    except (TypeError, ValueError):
        actions_required = len(crowd_tasks_data)

    if actions_required <= 0:
        actions_required = len(crowd_tasks_data)

    # Проверяем дубликаты по URL + action + social_network
    normalized_post_url = _normalize_url(post_url)
    active_tasks = Task.objects.filter(
        status='ACTIVE',
        type=action_type,
        social_network=social_network
    ).only('id', 'post_url')

    for task in active_tasks:
        if _normalize_url(task.post_url) == normalized_post_url:
            return Response({
                'success': False,
                'error': 'A task with this URL and action type already exists and is being completed by our community',
                'existing_task_id': task.id
            }, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user_profile = UserProfile.objects.select_for_update().get(pk=user_profile.pk)

            discounted_cost, original_cost = user_profile.calculate_task_cost(price, actions_required)

            if discounted_cost > user_profile.balance:
                return Response(
                    {
                        'success': False,
                        'error': 'Insufficient balance to create task',
                        'required_balance': discounted_cost,
                        'current_balance': user_profile.balance
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            payload = {
                'post_url': post_url,
                'type': action_type,
                'price': price,
                'actions_required': actions_required,
                'social_network_code': social_network_code,
                'task_type': 'CROWD',
                'crowd_tasks_data': crowd_tasks_data,
                'meaningful_comment': True,
                'is_pinned': is_pinned,
            }

            serializer = TaskSerializer(data=payload)
            if not serializer.is_valid():
                error_messages = []
                for field, errors in serializer.errors.items():
                    if isinstance(errors, list):
                        for error in errors:
                            if isinstance(error, dict):
                                error_messages.append(f"{field}: {', '.join(str(v) for v in error.values())}")
                            else:
                                error_messages.append(f"{field}: {str(error)}")
                    else:
                        error_messages.append(f"{field}: {str(errors)}")

                error_detail = '; '.join(error_messages) if error_messages else 'Validation error'
                return Response(
                    {
                        'success': False,
                        'error': error_detail
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_profile.balance -= discounted_cost
            user_profile.save(update_fields=['balance'])

            chosen_country = (user_profile.chosen_country or user_profile.country_code or '').upper()
            try:
                base_actions_required = int(actions_required)
            except Exception:
                base_actions_required = actions_required
            bonus_actions = 0
            if chosen_country and chosen_country in BONUS_ACTION_COUNTRIES:
                try:
                    bonus_actions = int(round(base_actions_required * BONUS_ACTION_RATE))
                except Exception:
                    bonus_actions = 0

            task = serializer.save(
                creator=user,
                original_price=original_cost,
                price=price,
                status='ACTIVE',
                bonus_actions=bonus_actions,
                bonus_actions_completed=0
            )

            user_profile.decrease_available_tasks()

            try:
                send_task_created_email(task)
            except Exception as e:
                logger.error(f"[public_api] Error sending task created email: {str(e)}")

            crowd_tasks_data_serialized = []
            if task.crowd_tasks.exists():
                crowd_tasks_data_serialized = CrowdTaskSerializer(task.crowd_tasks.all(), many=True).data

            response_data = {
                'success': True,
                'task_id': task.id,
                'message': 'Crowd task created successfully',
                'task': {
                    'id': task.id,
                    'status': task.status,
                    'post_url': task.post_url,
                    'type': task.type,
                    'task_type': task.task_type,
                    'social_network_code': social_network_code,
                    'actions_required': task.actions_required,
                    'actions_completed': task.actions_completed,
                    'bonus_actions': task.bonus_actions,
                    'bonus_actions_completed': task.bonus_actions_completed,
                    'price': task.price,
                    'original_price': task.original_price,
                    'created_at': task.created_at,
                    'crowd_tasks': crowd_tasks_data_serialized
                }
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

    except ValidationError as e:
        logger.error(f"[public_api] Validation error creating crowd task: {str(e)}")
        return Response(
            {
                'success': False,
                'error': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"[public_api] Error creating crowd task via API: {str(e)}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Error creating crowd task. Please try again later.'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_task_status(request, task_id=None):
    """
    Возвращает статус задания по его ID.
    Требует заголовок X-API-Key или параметр api_key.
    Можно запросить статус одного задания или нескольких через параметр task_ids (через запятую).
    """
    logger.info(f"[public_api] get_task_status called, task_id={task_id}")
    
    # Аутентифицируем API ключ
    api_key_str = _get_api_key_from_request(request)
    api_key_obj = _authenticate_api_key(api_key_str)
    
    if not api_key_obj:
        return Response(
            {
                'success': False,
                'error': 'Invalid or missing API key. Provide X-API-Key header or api_key parameter.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    user = api_key_obj.user
    
    # Определяем, какие задания запрашиваются
    task_ids = []
    if task_id:
        task_ids.append(task_id)
    elif request.GET.get('task_ids'):
        try:
            task_ids = [int(tid.strip()) for tid in request.GET.get('task_ids').split(',') if tid.strip()]
        except ValueError:
            return Response(
                {
                    'success': False,
                    'error': 'Invalid task_ids format. Use comma-separated integers.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {
                'success': False,
                'error': 'task_id or task_ids parameter is required'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not task_ids:
        return Response(
            {
                'success': False,
                'error': 'No valid task IDs provided'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Получаем задания, принадлежащие пользователю
        tasks = Task.objects.filter(
            id__in=task_ids,
            creator=user
        ).select_related('social_network')
        
        if not tasks.exists():
            return Response(
                {
                    'success': False,
                    'error': 'Tasks not found or you do not have permission to view them'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Формируем ответ
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                'id': task.id,
                'status': task.status,
                'post_url': task.post_url,
                'type': task.type,
                'social_network_code': task.social_network.code if task.social_network else None,
                'actions_required': task.actions_required,
                'actions_completed': task.actions_completed,
                'bonus_actions': task.bonus_actions,
                'bonus_actions_completed': task.bonus_actions_completed,
                'price': task.price,
                'original_price': task.original_price,
                'created_at': task.created_at,
                'completed_at': task.completed_at,
                'completion_duration': str(task.completion_duration) if task.completion_duration else None,
                'is_pinned': task.is_pinned
            })
        
        logger.info(f"[public_api] Retrieved task status for {len(tasks_data)} tasks, user_id={user.id}")
        
        return Response({
            'success': True,
            'tasks': tasks_data,
            'count': len(tasks_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[public_api] Error getting task status: {str(e)}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Failed to get task status'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

