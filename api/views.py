from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from django.contrib.auth.models import User
import json
from .models import (
    UserProfile, 
    Task, 
    TaskCompletion, 
    InviteCode, 
    EmailSubscriptionType, 
    UserEmailSubscription, 
    BlogPost, 
    SocialNetwork, 
    TaskReport, 
    PaymentTransaction, 
    ActionLanding,
    BuyLanding,
    Withdrawal,
    OnboardingProgress,
    Review,
    UserSocialProfile
)
from firebase_admin import auth
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from .serializers import UserProfileSerializer, TaskSerializer, BlogPostSerializer, TaskReportSerializer, SocialNetworkWithActionsSerializer, ActionLandingSerializer, BuyLandingSerializer, InvitedUserSerializer, UserSocialProfileSerializer, CreateUserSocialProfileSerializer, WithdrawalSerializer, CreateWithdrawalSerializer, WithdrawalStatsSerializer, OnboardingProgressSerializer, ReviewSerializer, ReferrerTrackingSerializer
from .constants import BONUS_ACTION_COUNTRIES, BONUS_ACTION_RATE
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
import requests
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.db import transaction
from django.shortcuts import redirect
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
import tweepy
from django.http import HttpResponseBadRequest, HttpResponseRedirect, HttpResponse
import uuid
from rest_framework.decorators import action
from django.db.models import Case, When, IntegerField, F
from django.db.models import Prefetch
from .models import UserSocialProfile
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters import rest_framework as filters
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .auto_actions import TwitterAutoActions
from django.db import connection
import logging
from .utils.email_utils import send_welcome_email, send_task_deleted_due_to_link_email, send_task_created_email
import time
import stripe
from .constants import SUBSCRIPTION_PLAN_CONFIG, SUBSCRIPTION_PERIODS
from .views_landings import ActionLandingViewSet
import traceback
import random
from django.db.models import Sum, Count
from django.db.models.functions import TruncHour, TruncDay, TruncMonth
from django.db.models import Value
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .email_service import EmailService
from django.core.mail import send_mail
from decimal import Decimal
from .helpers.linkedin_helper import verify_linkedin_profile_by_url

logger = logging.getLogger('api')

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_user(request):
    id_token = request.data.get('idToken')
    task_data = request.data.get('task_data')
    country_code = request.data.get('country_code') or request.headers.get('x-vercel-ip-country')
    invite_code_string = request.data.get('inviteCode')

    if not id_token:
        return Response({'error': 'No ID token provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        with transaction.atomic():
            # 1. Создаем пользователя
            user, created = User.objects.get_or_create(username=uid)
            
            if created:
                # Ищем пригласившего пользователя по инвайт-коду
                inviter_user = None
                invite_code_obj = None
                
                if invite_code_string:
                    try:
                        invite_code_obj = InviteCode.objects.select_related('creator').get(
                            code=invite_code_string,
                            status='ACTIVE'
                        )
                        
                        if invite_code_obj.is_valid():
                            inviter_user = invite_code_obj.creator
                            
                            # Регистрируем использование кода
                            invite_code_obj.used_by.add(user)
                            invite_code_obj.uses_count += 1
                            invite_code_obj.save(update_fields=['uses_count'])
                        else:
                            pass
                            
                    except InviteCode.DoesNotExist:
                        pass
                    except Exception as e:
                        pass
                
                # 2. Создаем профиль с базовыми настройками
                user_profile = UserProfile.objects.create(
                    user=user,
                    balance=13,
                    status='FREE',
                    country_code=country_code,
                    invite_code=invite_code_obj,
                    invited_by=inviter_user  # Устанавливаем связь с пригласившим
                )
                
                # Создаем безлимитный инвайт-код для нового пользователя
                user_profile.update_available_tasks()
                new_invite_code = user_profile.create_unlimited_invite_code()
                
                # 3. Если есть данные для задачи - создаем её
                if task_data:
                    social_network_code = task_data.get('social_network_code', 'TWITTER')

                    social_network = SocialNetwork.objects.get(code=social_network_code)

                    # Рассчитываем бонусные действия — по тем же правилам, что и в create_task
                    try:
                        base_actions_required = int(task_data['actions_required'])
                    except Exception:
                        base_actions_required = task_data['actions_required']

                    chosen_country = (user_profile.chosen_country or user_profile.country_code or '').upper()
                    bonus_actions = 0
                    if chosen_country and chosen_country in BONUS_ACTION_COUNTRIES:
                        try:
                            bonus_actions = int(round(base_actions_required * BONUS_ACTION_RATE))
                        except Exception:
                            bonus_actions = 0

                    task = Task.objects.create(
                        creator=user,
                        type=task_data['type'],
                        post_url=task_data['post_url'],
                        price=task_data['price'],
                        actions_required=base_actions_required,
                        original_price=task_data['price'] * base_actions_required,
                        social_network=social_network,
                        status='ACTIVE',
                        bonus_actions=bonus_actions,
                        bonus_actions_completed=0
                    )

                    total_cost = task_data['price'] * base_actions_required
                    user_profile.balance -= total_cost
                    user_profile.decrease_available_tasks()
                    user_profile.save(update_fields=['balance'])
                    
                    # Отправляем email о создании задания
                    try:
                        send_task_created_email(task)
                    except Exception as e:
                        logger.error(f"[register_user] Error sending task created email: {str(e)}")

        # 4. Создаем токены
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'is_new_user': created,
            'has_task': bool(task_data and created)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all().prefetch_related(
        'completions',
        'completions__user',
        'social_network',
        Prefetch(
            'completions__user__social_profiles',
            queryset=UserSocialProfile.objects.all(),
            to_attr='user_social_profiles'
        )
    )
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        try:
            user = self.request.user

            social_network_code = self.request.query_params.get('social_network')

            # --- PINNED TASKS ---
            # Получаем id задач, которые пользователь уже выполнял
            completed_task_ids = set(TaskCompletion.objects.filter(user=user).values_list('task_id', flat=True))

            pinned_tasks_qs = Task.objects.filter(
                status='ACTIVE',
                is_pinned=True
            ).exclude(creator=user)
            if social_network_code:
                pinned_tasks_qs = pinned_tasks_qs.filter(social_network__code=social_network_code.upper())
            if completed_task_ids:
                pinned_tasks_qs = pinned_tasks_qs.exclude(id__in=completed_task_ids)
            pinned_tasks_qs = pinned_tasks_qs.order_by('-created_at')
            pinned_tasks = list(pinned_tasks_qs)

            # --- ORDINARY TASKS ---
            completed_combinations = TaskCompletion.objects.filter(
                user=user
            ).values_list(
                'task__post_url',
                'task__type',
                'task__social_network'
            ).distinct()

            # Нормализация URL: убрать query/fragment, нижний регистр хоста, убрать финальный '/'
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

            # Собираем множество завершённых комбинаций с нормализованным post_url
            completed_combo_set = set(
                (
                    _normalize_url(url or ''),
                    t_type,
                    sn_id,
                )
                for (url, t_type, sn_id) in completed_combinations
            )

            # Дополнительно исключаем закреплённые задания по нормализованной комбинации
            try:
                before_pinned_count = len(pinned_tasks)
                pinned_tasks = [
                    t for t in pinned_tasks
                    if (
                        _normalize_url(getattr(t, 'post_url', '') or ''),
                        getattr(t, 'type', None),
                        getattr(t, 'social_network_id', None),
                    ) not in completed_combo_set
                ]
                # Ограничиваем количество закрепленных задач до 10
                pinned_tasks = pinned_tasks[:10]
            except Exception as e:
                pass

            reported_tasks = TaskReport.objects.filter(
                user=user
            ).values_list('task_id', flat=True)

            available_tasks = Task.objects.filter(
                status='ACTIVE',
                is_pinned=False  # исключаем закреплённые
            ).exclude(
                creator=user
            ).exclude(
                id__in=reported_tasks
            )

            # Исключаем обычные задания по нормализованной комбинации
            try:
                if completed_combo_set:
                    # Ограничим кандидатов по типам и соцсетям для эффективности
                    types_set = list({t for (_, t, _) in completed_combo_set if t is not None})
                    sn_ids_set = list({sn for (_, _, sn) in completed_combo_set if sn is not None})

                    candidates = available_tasks.filter(
                        type__in=types_set,
                        social_network_id__in=sn_ids_set
                    ).values('id', 'post_url', 'type', 'social_network_id')

                    ids_to_exclude = []
                    for c in candidates:
                        if (
                            _normalize_url(c.get('post_url') or ''),
                            c.get('type'),
                            c.get('social_network_id'),
                        ) in completed_combo_set:
                            ids_to_exclude.append(c['id'])

                    if ids_to_exclude:
                        available_tasks = available_tasks.exclude(id__in=ids_to_exclude)
            except Exception as e:
                pass

            if social_network_code:
                available_tasks = available_tasks.filter(
                    social_network__code=social_network_code.upper()
                )

            available_tasks = available_tasks.prefetch_related(
                'completions',
                'completions__user',
                'social_network',
                Prefetch(
                    'completions__user__social_profiles',
                    queryset=UserSocialProfile.objects.all(),
                    to_attr='user_social_profiles'
                )
            )

            now = timezone.now()
            available_tasks = available_tasks.annotate(
                remaining_actions=F('actions_required') - F('actions_completed'),
                is_fresh=Case(
                    When(created_at__gte=now - timezone.timedelta(days=1), then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                is_almost_done=Case(
                    When(remaining_actions__lte=2, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                is_completed=Case(
                    When(actions_completed__gte=F('actions_required'), then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            )

            # 1. Свежие задания (<24ч, не завершённые)
            fresh_tasks = list(
                available_tasks.filter(is_fresh=1, is_completed=0)
                .order_by('remaining_actions', '-created_at')
            )

            # 2. Почти завершённые старые (не свежие)
            almost_done_tasks = list(
                available_tasks.filter(is_fresh=0, is_almost_done=1, is_completed=0)
                .order_by('remaining_actions', '-created_at')
            )

            # 3. Остальные
            other_tasks = list(
                available_tasks.exclude(id__in=[t.id for t in fresh_tasks + almost_done_tasks])
                .filter(is_completed=0)
                .order_by('-created_at')
            )

            # --- АННОТИРУЕМ статус создателя задачи ---
            available_tasks = available_tasks.select_related('creator__userprofile').annotate(
                creator_status=F('creator__userprofile__status')
            )

            # --- МАППИНГ ПРИОРИТЕТОВ ---
            STATUS_PRIORITY = {
                'MATE': 0,
                'BUDDY': 1,
                'MEMBER': 2,
                'FREE': 3
            }

            def status_priority(task):
                status = getattr(task, 'creator_status', None)
                prio = STATUS_PRIORITY.get(status, 4)
                return prio

            # --- СОРТИРОВКА ВНУТРИ КАЖДОГО БЛОКА ---
            def sort_by_status(tasks, block_name):
                sorted_tasks = sorted(
                    tasks,
                    key=lambda t: (status_priority(t),
                                   t.remaining_actions if hasattr(t, 'remaining_actions') else 0,
                                   -t.created_at.timestamp() if hasattr(t, 'created_at') else 0)
                )
                return sorted_tasks

            fresh_tasks = sort_by_status(fresh_tasks, 'fresh_tasks')
            almost_done_tasks = sort_by_status(almost_done_tasks, 'almost_done_tasks')
            other_tasks = sort_by_status(other_tasks, 'other_tasks')

            # Собираем выдачу с лимитом
            mixed_tasks = []
            for t in fresh_tasks:
                if len(mixed_tasks) >= settings.TASKS_PER_REQUEST:
                    break
                mixed_tasks.append(t)
            if len(mixed_tasks) < settings.TASKS_PER_REQUEST:
                for t in almost_done_tasks:
                    if len(mixed_tasks) >= settings.TASKS_PER_REQUEST:
                        break
                    mixed_tasks.append(t)
            if len(mixed_tasks) < settings.TASKS_PER_REQUEST:
                for t in other_tasks:
                    if len(mixed_tasks) >= settings.TASKS_PER_REQUEST:
                        break
                    mixed_tasks.append(t)

            # --- ФИНАЛЬНАЯ СБОРКА: pinned + обычные ---
            final_tasks = pinned_tasks + mixed_tasks
            return final_tasks

        except Exception as e:
            return Task.objects.none()

    def list(self, request, *args, **kwargs):
        """
        Переопределенный метод list для добавления статистики по социальным сетям. 1
        Возвращает объект с полями:
        - stats_by_network: список статистики по каждой соц. сети
        - total_available: общее количество доступных задач
        - tasks: список задач (обработанный через get_queryset)
        """
        try:
            from django.db.models import Count
            
            user = request.user
            social_network_code = request.query_params.get('social_network')
            
            # Получаем задачи через get_queryset (это уже отфильтрованный список)
            queryset = self.filter_queryset(self.get_queryset())
            
            # Теперь нужно получить полную статистику для фильтров
            # Строим базовый queryset для подсчета статистики (без пагинации и лимитов)
            
            # Получаем id задач, которые пользователь уже выполнял
            completed_task_ids = set(TaskCompletion.objects.filter(user=user).values_list('task_id', flat=True))
            
            # Получаем id репортнутых задач
            reported_tasks = TaskReport.objects.filter(user=user).values_list('task_id', flat=True)
            
            # Базовый queryset для статистики
            stats_queryset = Task.objects.filter(
                status='ACTIVE'
            ).exclude(
                creator=user
            ).exclude(
                id__in=reported_tasks
            )
            
            # Исключаем выполненные задания по ID
            if completed_task_ids:
                stats_queryset = stats_queryset.exclude(id__in=completed_task_ids)
            
            # Исключаем задания с таким же нормализованным URL (аналогично логике в get_queryset)
            completed_combinations = TaskCompletion.objects.filter(
                user=user
            ).values_list(
                'task__post_url',
                'task__type',
                'task__social_network'
            ).distinct()
            
            # Функция нормализации URL (та же, что в get_queryset)
            def _normalize_url(raw_url: str) -> str:
                """Normalize URL for duplicate detection."""
                try:
                    from urllib.parse import urlsplit
                    parts = urlsplit(raw_url)
                    netloc = parts.netloc.lower()
                    for prefix in ('www.', 'm.', 'mobile.', 'vm.'):
                        if netloc.startswith(prefix):
                            netloc = netloc[len(prefix):]
                            break
                    if netloc in {'youtu.be', 'youtube-nocookie.com'}:
                        netloc = 'youtube.com'
                    path = parts.path.rstrip('/') if parts.path != '/' else ''
                    return f"{netloc}{path}"
                except Exception:
                    safe = (raw_url or '')
                    if '://' in safe:
                        safe = safe.split('://', 1)[1]
                    safe = safe.split('#')[0].split('?')[0]
                    safe = safe.rstrip('/')
                    for prefix in ('www.', 'm.', 'mobile.', 'vm.'):
                        if safe.startswith(prefix):
                            safe = safe[len(prefix):]
                            break
                    safe = safe.lower()
                    host, _, rest = safe.partition('/')
                    if host in {'youtu.be', 'youtube-nocookie.com'}:
                        host = 'youtube.com'
                    return host + (('/' + rest) if rest else '')
            
            # Собираем множество завершённых комбинаций
            completed_combo_set = set(
                (
                    _normalize_url(url or ''),
                    t_type,
                    sn_id,
                )
                for (url, t_type, sn_id) in completed_combinations
            )
            
            # Исключаем задания по нормализованной комбинации
            if completed_combo_set:
                try:
                    types_set = list({t for (_, t, _) in completed_combo_set if t is not None})
                    sn_ids_set = list({sn for (_, _, sn) in completed_combo_set if sn is not None})
                    
                    if types_set and sn_ids_set:
                        candidates = stats_queryset.filter(
                            type__in=types_set,
                            social_network_id__in=sn_ids_set
                        ).values('id', 'post_url', 'type', 'social_network_id')
                        
                        ids_to_exclude = []
                        for c in candidates:
                            if (
                                _normalize_url(c.get('post_url') or ''),
                                c.get('type'),
                                c.get('social_network_id'),
                            ) in completed_combo_set:
                                ids_to_exclude.append(c['id'])
                        
                        if ids_to_exclude:
                            stats_queryset = stats_queryset.exclude(id__in=ids_to_exclude)
                except Exception:
                    pass
            
            # Подсчитываем статистику по социальным сетям
            stats_by_network = stats_queryset.values(
                'social_network__id',
                'social_network__name',
                'social_network__code',
                'social_network__icon'
            ).annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Формируем список статистики
            stats_list = []
            total_tasks = 0
            
            print(f"[TaskViewSet.list] Building stats for available tasks (user: {user.id})")
            
            for stat in stats_by_network:
                network_data = {
                    'social_network_id': stat['social_network__id'],
                    'social_network_name': stat['social_network__name'],
                    'social_network_code': stat['social_network__code'],
                    'social_network_icon': stat['social_network__icon'],
                    'available_count': stat['count']
                }
                stats_list.append(network_data)
                total_tasks += stat['count']
                print(f"[TaskViewSet.list] Network: {stat['social_network__name']}, Available: {stat['count']}")
            
            print(f"[TaskViewSet.list] Total available tasks across all networks: {total_tasks}")
            
            # Сериализуем задачи
            serializer = self.get_serializer(queryset, many=True)
            
            # Возвращаем статистику и задания
            return Response({
                'stats_by_network': stats_list,
                'total_available': total_tasks,
                'tasks': serializer.data
            })
            
        except Exception as e:
            print(f"[TaskViewSet.list] Error building stats: {str(e)}")
            import traceback
            traceback.print_exc()
            # В случае ошибки возвращаем стандартный формат
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        tasks = Task.objects.filter(creator=request.user).prefetch_related(
            'completions',
            'completions__user',
            'social_network',
            'completions__user__social_profiles',
            'completions__user__social_profiles__social_network'
        )
        
        tasks = tasks.annotate(
            status_order=Case(
                When(status='ACTIVE', then=0),
                When(status='PAUSED', then=1),
                When(status='COMPLETED', then=2),
                default=3,
                output_field=IntegerField(),
            )
        ).order_by('status_order', '-created_at')
        
        serializer = self.get_serializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)

    def perform_create(self, serializer):
        social_network = serializer.validated_data.get('social_network')
        task_type = serializer.validated_data.get('type')
        post_url = serializer.validated_data.get('post_url')
        price = serializer.validated_data.get('price')
        actions_required = serializer.validated_data.get('actions_required')
        
        # Проверяем, что тип действия доступен для данной социальной сети
        if not social_network.available_actions.filter(code=task_type).exists():
            raise ValidationError(f"Action type {task_type} is not available for {social_network.name}")

        user_profile = self.request.user.userprofile
        
        # Вычисляем стоимость с учетом скидки и оригинальную стоимость
        discounted_cost, original_cost = user_profile.calculate_task_cost(price, actions_required)
        
        # Проверяем баланс с учетом скидки
        if discounted_cost > user_profile.balance:
            raise ValidationError("Insufficient balance to create task")
        
        try:
            with transaction.atomic():
                # Получаем свежую версию профиля для атомарного обновления
                user_profile = UserProfile.objects.select_for_update().get(pk=user_profile.pk)
                
                # Проверяем баланс еще раз после блокировки
                if discounted_cost > user_profile.balance:
                    raise ValidationError("Insufficient balance to create task")
                
                # Специальная обработка для Twitter FOLLOW
                if social_network.code == 'TWITTER' and task_type == 'FOLLOW':
                    try:
                        target_username = post_url.split('/')[-1]
                        auto_actions = TwitterAutoActions(user_profile)
                        user_id = auto_actions.get_user_id(target_username)
                        
                        if not user_id:
                            raise ValidationError("Could not get Twitter user ID. Please check if the username is correct.")
                            
                        # Списываем баланс с учетом скидки
                        user_profile.balance -= discounted_cost
                        user_profile.save(update_fields=['balance'])
                        
                        task = serializer.save(
                            creator=self.request.user,
                            target_user_id=user_id,
                            original_price=original_cost,
                            price=price,  # Устанавливаем базовую цену
                            status='ACTIVE'  # Явно указываем статус
                        )
                        
                    except Exception as e:
                        raise ValidationError("Error creating FOLLOW task. Please try again later.")
                else:
                    # Списываем баланс с учетом скидки
                    user_profile.balance -= discounted_cost
                    user_profile.save(update_fields=['balance'])
                    
                    task = serializer.save(
                        creator=self.request.user,
                        original_price=original_cost,
                        price=price,  # Устанавливаем базовую цену
                        status='ACTIVE'  # Явно указываем статус
                    )
                
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError("Error creating task. Please try again later.")


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def tasks1(request):
    """
    Возвращает задания только от авторов из tier1 стран (BONUS_ACTION_COUNTRIES).
    Сортировка: сначала закрепленные (is_pinned=True), потом по дате создания (created_at).
    Страна определяется по chosen_country в UserProfile.
    Поддерживает фильтрацию по social_network через query параметр.
    Исключает задания, которые пользователь уже выполнил (по ID и по нормализованному URL).
    """
    try:
        social_network_code = request.query_params.get('social_network')
        
        # Фильтруем задания от авторов из tier1 стран
        # Исключаем случаи, когда chosen_country равен NULL или не входит в BONUS_ACTION_COUNTRIES
        tasks = Task.objects.filter(
            status='ACTIVE',
            creator__userprofile__chosen_country__in=BONUS_ACTION_COUNTRIES,
            creator__userprofile__chosen_country__isnull=False
        )
        
        # Применяем фильтрацию по социальной сети, если указана
        if social_network_code:
            tasks = tasks.filter(social_network__code=social_network_code.upper())
        
        # Фильтрация выполненных заданий (если пользователь авторизован)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            # 1. Исключаем задания по ID (которые пользователь уже выполнил)
            completed_task_ids = set(TaskCompletion.objects.filter(user=user).values_list('task_id', flat=True))
            if completed_task_ids:
                tasks = tasks.exclude(id__in=completed_task_ids)
            
            # 2. Исключаем задания с таким же нормализованным URL
            # Получаем комбинации выполненных заданий
            completed_combinations = TaskCompletion.objects.filter(
                user=user
            ).values_list(
                'task__post_url',
                'task__type',
                'task__social_network_id'
            ).distinct()
            
            # Функция нормализации URL (та же, что в TaskViewSet)
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
            
            # Собираем множество завершённых комбинаций с нормализованным post_url
            completed_combo_set = set(
                (
                    _normalize_url(url or ''),
                    t_type,
                    sn_id,
                )
                for (url, t_type, sn_id) in completed_combinations
            )
            
            # Исключаем задания по нормализованной комбинации
            if completed_combo_set:
                try:
                    # Ограничим кандидатов по типам и соцсетям для эффективности
                    types_set = list({t for (_, t, _) in completed_combo_set if t is not None})
                    sn_ids_set = list({sn for (_, _, sn) in completed_combo_set if sn is not None})
                    
                    if types_set and sn_ids_set:
                        candidates = tasks.filter(
                            type__in=types_set,
                            social_network_id__in=sn_ids_set
                        ).values('id', 'post_url', 'type', 'social_network_id')
                        
                        ids_to_exclude = []
                        for c in candidates:
                            if (
                                _normalize_url(c.get('post_url') or ''),
                                c.get('type'),
                                c.get('social_network_id'),
                            ) in completed_combo_set:
                                ids_to_exclude.append(c['id'])
                        
                        if ids_to_exclude:
                            tasks = tasks.exclude(id__in=ids_to_exclude)
                except Exception:
                    pass
        
        # Подсчитываем статистику по социальным сетям ДО применения лимита
        # Группируем по social_network и считаем количество
        from django.db.models import Count
        
        stats_by_network = tasks.values(
            'social_network__id',
            'social_network__name',
            'social_network__code',
            'social_network__icon'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Формируем список статистики
        stats_list = []
        total_tasks = 0
        
        print(f"[tasks1] Building stats for available tasks")
        
        for stat in stats_by_network:
            network_data = {
                'social_network_id': stat['social_network__id'],
                'social_network_name': stat['social_network__name'],
                'social_network_code': stat['social_network__code'],
                'social_network_icon': stat['social_network__icon'],
                'available_count': stat['count']
            }
            stats_list.append(network_data)
            total_tasks += stat['count']
            print(f"[tasks1] Network: {stat['social_network__name']}, Available: {stat['count']}")
        
        print(f"[tasks1] Total available tasks across all networks: {total_tasks}")
        
        tasks = tasks.select_related(
            'creator',
            'creator__userprofile',
            'social_network'
        ).prefetch_related(
            'completions',
            'completions__user',
            Prefetch(
                'completions__user__social_profiles',
                queryset=UserSocialProfile.objects.all(),
                to_attr='user_social_profiles'
            )
        )
        
        # Сортировка: сначала закрепленные, потом по дате создания
        tasks = tasks.order_by('-is_pinned', '-created_at')
        
        # Ограничиваем количество заданий до 20
        tasks = tasks[:20]
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        
        # Возвращаем статистику и задания
        return Response({
            'stats_by_network': stats_list,
            'total_available': total_tasks,
            'tasks': serializer.data
        })
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated if settings.COMPLETE_TASK_REQUIRES_AUTH else permissions.AllowAny])
@authentication_classes([JWTAuthentication] if settings.COMPLETE_TASK_REQUIRES_AUTH else [])
def complete_task(request, task_id):
    try:
        
        action = request.data.get('action')
        user_id = request.data.get('user')
        metadata = request.data.get('metadata')
        
        try:
            user_id = int(user_id)
            user_profile = UserProfile.objects.get(id=user_id)
            user = user_profile.user
            print(f"Found user: {user.id}, through profile: {user_profile.id}")
        except (ValueError, TypeError) as e:
            print(f"Error converting user_id: {e}")
            return Response({'error': 'Invalid user ID format'}, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            print(f"UserProfile not found with id: {user_id}")
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if not action:
            return Response({'error': 'Action parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        task = get_object_or_404(Task, id=task_id)
        
        if task.status != 'ACTIVE':
            return Response({'error': 'Task is not active'}, status=status.HTTP_400_BAD_REQUEST)

        if TaskCompletion.objects.filter(task=task, user=user, action=action).exists():
            return Response({'error': 'Already completed this action'}, status=status.HTTP_400_BAD_REQUEST)

        if action.upper() != task.type.upper():
            return Response({'error': f'Invalid action type. Expected: {task.type}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with db_transaction.atomic():
                task.refresh_from_db()
                
                if task.status != 'ACTIVE':
                    raise ValidationError('Task is no longer active')

                # Безопасно парсим metadata, если пришла строка
                try:
                    if isinstance(metadata, str):
                        metadata_parsed = json.loads(metadata)
                    else:
                        metadata_parsed = metadata
                except Exception:
                    metadata_parsed = {'raw': metadata}

                completion = TaskCompletion.objects.create(
                    task=task,
                    user=user,
                    action=action,
                    completed_at=timezone.now(),
                    post_url=task.post_url,
                    metadata=metadata_parsed
                )

                # Чередование: Основное -> Бонусное -> Основное ...
                main_required = task.actions_required or 0
                bonus_required = task.bonus_actions or 0
                main_done = task.actions_completed or 0
                bonus_done = task.bonus_actions_completed or 0
                total_required = main_required + bonus_required
                total_done = main_done + bonus_done

                # Осталось выполнить
                total_remaining = max(0, total_required - total_done)
                main_remaining = max(0, main_required - main_done)
                bonus_remaining = max(0, bonus_required - bonus_done)

                # Правило выбора следующего инкремента:
                # 1) Если остался только один шаг — он всегда основной
                # 2) Иначе, если main_done == bonus_done — делаем основной
                # 3) Иначе, если бонусы ещё остались и main_done > bonus_done — делаем бонус
                # 4) Иначе — основной
                if total_remaining == 1:
                    if main_remaining > 0:
                        task.actions_completed = main_done + 1
                    else:
                        # На всякий случай: не позволяем завершать последним бонусом
                        task.actions_completed = main_done + 1
                elif main_done == bonus_done:
                    task.actions_completed = main_done + 1
                elif bonus_remaining > 0 and main_done > bonus_done:
                    task.bonus_actions_completed = bonus_done + 1
                else:
                    task.actions_completed = main_done + 1

                # Завершение задачи только после выполнения и основных, и бонусных
                if (task.actions_completed >= main_required) and (task.bonus_actions_completed >= bonus_required) and total_required > 0:
                    task.status = 'COMPLETED'
                    task.completed_at = timezone.now()
                    task.completion_duration = task.completed_at - task.created_at

                task.save()

                # Награда начисляется только за основные действия, бонусы бесплатные для автора
                reward = task.original_price / task.actions_required / 2
                
                user_profile.balance += reward
                user_profile.completed_tasks_count += 1
                user_profile.bonus_tasks_completed += 1
                user_profile.save()
                return Response({
                    'message': 'Task completed successfully',
                    'reward': reward,
                    'new_balance': user_profile.balance,
                    'task_status': task.status
                }, status=status.HTTP_200_OK)

        except IntegrityError as e:
            return Response({'error': 'Duplicate completion'}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def get_balance(request):
    user_profile = request.user.userprofile
    return Response({'balance': user_profile.balance})

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_user(request):
    id_token = request.data.get('idToken')
    if not id_token:
        return Response({'error': 'No ID token provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        user, created = User.objects.get_or_create(username=uid)
        
        if created:
            UserProfile.objects.create(user=user)
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def create_task(request):
    # Проверяем наличие всех необходимых полей
    required_fields = ['post_url', 'type', 'price', 'actions_required', 'social_network_code']
    for field in required_fields:
        if field not in request.data:
            error_msg = f"Missing required field: {field}"
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
    
    # Проверяем доступные задания
    user_profile = request.user.userprofile
    if user_profile.available_tasks <= 0:
        error_msg = "No available tasks left"
        return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
    
    # Проверяем, нет ли уже активного задания с таким URL + TYPE + SOCIAL_NETWORK
    post_url = request.data.get('post_url')
    task_type = request.data.get('type')
    social_network_code = request.data.get('social_network_code')
    
    # Функция нормализации URL (та же, что в TaskViewSet)
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
    
    # Нормализуем входящий URL
    normalized_post_url = _normalize_url(post_url)
    
    # Получаем социальную сеть для проверки
    try:
        social_network = SocialNetwork.objects.get(code=social_network_code)
    except SocialNetwork.DoesNotExist:
        pass  # Ошибку валидации обработает сериализатор позже
    else:
        # Ищем активные задания с той же комбинацией URL + TYPE + SOCIAL_NETWORK
        active_tasks = Task.objects.filter(
            status='ACTIVE',
            type=task_type,
            social_network=social_network
        ).only('id', 'post_url')
        
        for task in active_tasks:
            if _normalize_url(task.post_url) == normalized_post_url:
                return Response({
                    'detail': 'A task with this URL and action type already exists and is being completed by our community',
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
                raise ValidationError("Insufficient balance to create task")
            
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
                    {'detail': error_detail}, 
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
                creator=request.user,
                original_price=original_cost,
                price=price,  # Устанавливаем базовую цену
                status='ACTIVE',  # Явно указываем статус
                bonus_actions=bonus_actions,
                bonus_actions_completed=0
            )
            
            # Уменьшаем количество доступных заданий
            user_profile.decrease_available_tasks()

            # Отправляем email о создании задания
            try:
                send_task_created_email(task)
            except Exception as e:
                logger.error(f"[create_task] Error sending task created email: {str(e)}")
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
    except ValidationError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {'detail': 'Error creating task. Please try again later.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def add_balance(request):
    amount = request.data.get('amount')
    if not amount or amount <= 0:
        return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
    
    user_profile = request.user.userprofile
    user_profile.balance += amount
    user_profile.save()
    
    return Response({
        'message': 'Balance successfully added',
        'new_balance': user_profile.balance
    }, status=status.HTTP_200_OK)

def invalidate_all_tokens():
    tokens = OutstandingToken.objects.filter(expires_at__gt=timezone.now())
    for token in tokens:
        BlacklistedToken.objects.get_or_create(token=token)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def verify_invite_code(request):
    invite_code = request.data.get('inviteCode')
    user = request.user

    if not invite_code:
        return Response({'error': 'Invite code is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with db_transaction.atomic():
            invite = InviteCode.objects.select_for_update().get(code=invite_code)
            
            if not invite.is_valid():
                return Response({'error': 'Invalid or used invite code'}, status=status.HTTP_400_BAD_REQUEST)

            if invite.creator == user:
                return Response({'error': 'Cannot use your own invite code'}, status=status.HTTP_400_BAD_REQUEST)
            
            if user.userprofile.invite_code:
                return Response({'error': 'You have already used an invite code'}, status=status.HTTP_400_BAD_REQUEST)
            
            invite.uses_count += 1
            if invite.max_uses != 0 and invite.uses_count >= invite.max_uses:
                invite.status = 'USED'
            invite.used_by.add(user)
            invite.save()

            user_profile = user.userprofile
            user_profile.invite_code = invite
            user_profile.balance += 30
            user_profile.save()

            creator_profile = invite.creator.userprofile
            creator_profile.balance += 30
            creator_profile.save()

        return Response({
            'valid': True,
            'message': 'Invite code applied successfully',
            'new_balance': user_profile.balance
        }, status=status.HTTP_200_OK)
    except InviteCode.DoesNotExist:
        return Response({'valid': False, 'error': 'Invalid invite code'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': 'An error occurred while processing the invite code'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_plan(request):
    plan_name = request.data.get('planName')
    is_trial = request.data.get('isTrial', False)
    session_id = request.data.get('session_id')
    user = request.user
    
    logger.info(f'[update_user_plan] Starting plan update. Data: plan_name={plan_name}, is_trial={is_trial}, session_id={session_id}, user_id={user.id}')
    
    try:
        with db_transaction.atomic():
            user_profile = UserProfile.objects.select_for_update().get(user=user)
            logger.info(f'[update_user_plan] Current user profile status: {user_profile.status}')
            
            if is_trial:
                if not user_profile.trial_start_date:
                    user_profile.trial_start_date = timezone.now()
                    logger.info(f'[update_user_plan] Starting trial period for user {user.id}')
                else:
                    logger.warning(f'[update_user_plan] Trial period already used for user {user.id}')
                    return Response({'success': False, 'message': 'Trial period already used'}, status=400)
            
            if plan_name == 'Member':
                user_profile.status = 'MEMBER'
            elif plan_name == 'Buddy':
                user_profile.status = 'BUDDY'
            elif plan_name == 'Mate':
                user_profile.status = 'MATE'
            else:
                logger.error(f'[update_user_plan] Invalid plan name: {plan_name}')
                return Response({'success': False, 'message': 'Invalid plan name'}, status=400)
            
            logger.info(f'[update_user_plan] Creating/updating transaction for session_id: {session_id}')
            
            if not session_id:
                logger.error('[update_user_plan] No session_id provided')
                return Response({'success': False, 'message': 'No session ID provided'}, status=400)
            
            transaction_obj, created = PaymentTransaction.objects.get_or_create(
                stripe_session_id=session_id,
                defaults={
                    'user': user,
                    'amount': 0,
                    'type': 'SUBSCRIPTION',
                    'status': 'COMPLETED'
                }
            )
            
            if not created:
                if transaction_obj.status == 'COMPLETED':
                    logger.warning(f'[update_user_plan] Payment already processed for session_id: {session_id}')
                    return Response({'success': False, 'message': 'Payment already processed'}, status=400)
                else:
                    transaction_obj.status = 'COMPLETED'
                    transaction_obj.save()
                    logger.info(f'[update_user_plan] Updated existing transaction status to COMPLETED')
            
            user_profile.save()
            logger.info(f'[update_user_plan] Successfully updated user plan to {plan_name}')
            
            return Response({'success': True, 'message': 'User plan updated successfully'})
    except Exception as e:
        logger.error(f'[update_user_plan] Error updating user plan: {str(e)}')
        return Response({'success': False, 'message': 'Error updating user plan', 'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def generate_invite_code(request):
    user_profile = request.user.userprofile
    active_invite = InviteCode.objects.filter(creator=request.user, status='ACTIVE').first()

    if active_invite:
        return Response({'inviteCode': active_invite.code}, status=status.HTTP_200_OK)

    if user_profile.available_invites > 0:
        invite_code = InviteCode.objects.create(
            code=str(uuid.uuid4())[:8],
            creator=request.user,
            status='ACTIVE',
            max_uses=2
        )
        user_profile.available_invites -= 1
        user_profile.save()
        return Response({'inviteCode': invite_code.code}, status=status.HTTP_201_CREATED)
    else:
        return Response({'error': 'No invites available'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def get_active_invite_code(request):
    active_invite = InviteCode.objects.filter(creator=request.user, status='ACTIVE').order_by('-created_at').first()
    user_profile = request.user.userprofile
    
    response_data = {
        'inviteCode': active_invite.code if active_invite else None,
        'availableInvites': user_profile.available_invites
    }
    
    return Response(response_data, status=status.HTTP_200_OK)

class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user_profile = queryset.first()
        
        serializer = self.get_serializer(user_profile)
        return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_points(request):
    amount = request.data.get('amount')
    points = request.data.get('points')
    payment_id = request.data.get('payment_id')
    task_purchase = request.data.get('task_purchase', False)
    
    if not amount or int(amount) <= 0:
        return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Проверяем, не обработан ли уже этот платеж
    if payment_id and PaymentTransaction.objects.filter(payment_id=payment_id).exists():
        return Response({'error': 'Payment already processed'}, status=status.HTTP_200_OK)
    
    amount = int(amount)
    points_to_add = points if points else amount  # Если points не указаны, используем amount
    
    transaction = PaymentTransaction.objects.create(
        user=request.user,
        points=points_to_add,
        amount=amount,
        payment_id=payment_id or f"purchase_{uuid.uuid4().hex[:8]}",
        status='COMPLETED',
        payment_type='ONE_TIME',
        is_task_purchase=task_purchase
    )
    
    user_profile = request.user.userprofile
    user_profile.balance += points_to_add
    
    # Если это покупка создания задания, НЕ начисляем задачу
    # (задание создается в основном процессе обработки платежа)
    if task_purchase:
        logger.info(f"[purchase_points] Task purchase detected for user {request.user.id}")
    
    user_profile.save()
    
    return Response({
        'success': True,
        'message': 'Points purchased successfully',
        'new_balance': user_profile.balance,
        'transaction_id': transaction.id,
        'available_tasks': user_profile.available_tasks
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def unsubscribe(request, token):
    try:
        subscription = UserEmailSubscription.objects.get(unsubscribe_token=token)
        subscription.is_subscribed = False
        subscription.save()
        
        html_content = f"""
        <html>
            <head>
                <title>Unsubscribe Successful</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }}
                    .container {{
                        text-align: center;
                        padding: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Successfully Unsubscribed</h1>
                    <p>You have been unsubscribed from {subscription.subscription_type.name} emails.</p>
                </div>
            </body>
        </html>
        """
        return HttpResponse(html_content, content_type='text/html')
        
    except UserEmailSubscription.DoesNotExist:
        return HttpResponse(
            '<h1>Invalid unsubscribe token</h1>',
            content_type='text/html',
            status=400
        )

class BlogPostFilter(filters.FilterSet):
    category = filters.CharFilter(field_name='category__slug')
    tags = filters.CharFilter(method='filter_tags')
    
    def filter_tags(self, queryset, name, value):
        tag_slugs = value.split(',')
        return queryset.filter(tags__slug__in=tag_slugs).distinct()

    class Meta:
        model = BlogPost
        fields = ['category', 'tags']

class BlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlogPost.objects.filter(
        status='PUBLISHED'
    ).select_related(
        'category', 
        'author'
    ).prefetch_related(
        'tags'
    ).order_by('-published_at')
    
    serializer_class = BlogPostSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = BlogPostFilter
    search_fields = ['title', 'content']
    ordering_fields = ['published_at', 'title']
    lookup_field = 'slug'

    def get_object(self):
        """
        Переопределяем метод для добавления логирования
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Получаем slug из URL
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug = self.kwargs[lookup_url_kwarg]
        
        # Проверяем существование поста без фильтра status
        all_posts = BlogPost.objects.filter(slug=slug)
        if all_posts.exists():
            post = all_posts.first()
            logger.info(f"""[BlogPostViewSet] Found post in DB (might be unpublished):
                ID: {post.id}
                Title: {post.title}
                Slug: {post.slug}
                Status: {post.status}
                Published At: {post.published_at}
                Created At: {post.created_at}
                Updated At: {post.updated_at}
                Category: {post.category.name if post.category else 'No category'}
                Author: {post.author.username if post.author else 'No author'}
                Tags: {[tag.name for tag in post.tags.all()]}
            """)
        else:
            logger.error(f"""[BlogPostViewSet] No post found with slug: {slug}
                Raw slug from URL: {slug}
                All available slugs: {list(BlogPost.objects.values_list('slug', flat=True))}
            """)
            
        try:
            obj = queryset.get(slug=slug)
            logger.info(f"""[BlogPostViewSet] Successfully found published post:
                ID: {obj.id}
                Title: {obj.title}
                Slug: {obj.slug}
                Status: {obj.status}
                Published At: {obj.published_at}
                Created At: {obj.created_at}
                Updated At: {obj.updated_at}
                Category: {obj.category.name if obj.category else 'No category'}
                Author: {obj.author.username if obj.author else 'No author'}
                Tags: {[tag.name for tag in obj.tags.all()]}
            """)
            return obj
        except BlogPost.DoesNotExist:
            logger.error(f"""[BlogPostViewSet] Post not found with slug: {slug}
                Queryset filter: status='PUBLISHED' AND slug='{slug}'
                Raw slug from URL: {slug}
                All published posts slugs: {list(queryset.values_list('slug', flat=True))}
            """)
            raise

    def retrieve(self, request, *args, **kwargs):
        logger.info(f"""[BlogPostViewSet] Retrieving blog post:
            Slug: {kwargs.get('slug')}
            URL: {request.path}
            Method: {request.method}
            Headers: {request.headers}
        """)
        
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"""[BlogPostViewSet] Error retrieving blog post:
                Error: {str(e)}
                Traceback: {traceback.format_exc()}
            """)
            raise

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token(request):
    """
    Endpoint для обновления токенов через Firebase ID token
    """
    id_token = request.data.get('idToken')
    
    if not id_token:
        return Response({'error': 'No ID token provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Верифицируем Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        # Получаем или создаем пользователя
        user = User.objects.filter(username=uid).first()
        
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Создаем новые JWT токены
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }, status=status.HTTP_200_OK)
        
    except auth.InvalidIdTokenError:
        return Response({'error': 'Invalid ID token'}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        logger.error(f'Error refreshing token: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def report_task(request):
    logger.info(f'[report_task] Received request data: {request.data}')
    task_id = request.data.get('task_id')
    reason = request.data.get('reason')
    details = request.data.get('details', '')

    if not task_id or not reason:
        logger.warning(f'[report_task] Missing required fields: task_id={task_id}, reason={reason}')
        return Response(
            {'error': 'task_id and reason are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        logger.warning(f'[report_task] Task not found: {task_id}')
        return Response(
            {'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

    # Проверяем, не репортил ли уже пользователь это задание
    if TaskReport.objects.filter(user=request.user, task=task).exists():
        logger.warning(f'[report_task] User {request.user.id} already reported task {task_id}')
        return Response(
            {'error': 'You have already reported this task'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Создаем репорт напрямую
        report = TaskReport.objects.create(
            user=request.user,
            task=task,
            reason=reason,
            details=details
        )

        # Если это первый репорт "not_working" или "not_available"
        if reason == 'not_available':
            # --- Логика удаления задания и возврата поинтов/слота ---
            from django.db import transaction
            with transaction.atomic():
                task = Task.objects.select_for_update().get(id=task.id)
                if task.status == 'ACTIVE':
                    user_profile = task.creator.userprofile
                    remaining_actions = task.actions_required - task.actions_completed
                    if remaining_actions > 0:
                        discount_rate = user_profile.get_discount_rate()
                        original_cost = task.original_price
                        discounted_cost = int(original_cost - (original_cost * discount_rate / 100))
                        cost_per_action = discounted_cost / task.actions_required
                        refund_points = int(cost_per_action * remaining_actions)
                        user_profile.balance += refund_points
                    else:
                        refund_points = 0
                    user_profile.available_tasks += 1
                    task.status = 'DELETED'
                    task.deletion_reason = 'LINK_UNAVAILABLE'
                    task.save(update_fields=['status', 'deletion_reason'])
                    user_profile.save(update_fields=['balance', 'available_tasks'])
                    # Отправляем email автору задания
                    send_task_deleted_due_to_link_email(task, refund_points)
        elif reason == 'not_working':
            task.status = 'ACTIVE'
            task.save(update_fields=['status'])

        logger.info(f'Task {task_id} reported by user {request.user.id} for reason: {reason}')

        return Response(
            TaskReportSerializer(report).data, 
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        logger.error(f'[report_task] Error creating task report: {str(e)}')
        return Response(
            {'error': 'Failed to create report'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_sitemap_data(request):
    """
    Получение всех доступных URL для sitemap.xml:
    1. Комбинации социальных сетей и типов действий
    2. URL лендингов в формате /{social_network}/{action}/{landing-slug}
    Возвращает информацию о редиректах для фильтрации в sitemap.
    """
    logger.info('[get_sitemap_data] Getting sitemap data')
    
    try:
        paths = []
        
        # 1. Получаем все активные социальные сети и их действия
        social_networks = SocialNetwork.objects.filter(
            is_active=True
        ).prefetch_related('available_actions')
        
        # 2. Получаем все лендинги с их соц.сетями, действиями и redirect_url
        landings = ActionLanding.objects.all().values('slug', 'social_network', 'action', 'redirect_url')
        
        # 3. Получаем все BuyLanding с предзагрузкой социальных сетей
        buy_landings = BuyLanding.objects.all().select_related('social_network')
        
        # Создаем словарь для быстрого доступа к кодам социальных сетей
        network_code_map = {network.id: network.code.lower() for network in social_networks}
        
        for network in social_networks:
            network_code = network.code.lower()
            
            # Добавляем основной путь соц. сети
            paths.append(f'/{network_code}')
            
            # Для каждого действия
            for action in network.available_actions.all():
                action_code = action.code.lower()
                action_path = f'/{network_code}/{action_code}'
                paths.append(action_path)
                
                # Добавляем лендинги для этой комбинации соц.сети и действия
                network_landings = [
                    landing for landing in landings 
                    if landing['social_network'] and landing['action'] and
                    landing['social_network'] == network.id and 
                    landing['action'].lower() == action_code
                ]
                
                for landing in network_landings:
                    landing_path = f'{action_path}/{landing["slug"]}'
                    # Добавляем информацию о редиректе для лендингов
                    paths.append({
                        'path': landing_path,
                        'has_redirect': bool(landing.get('redirect_url'))
                    })
        
        # 4. Добавляем все BuyLanding в формате /{social_network}/{slug}
        for buy_landing in buy_landings:
            if buy_landing.social_network_id and buy_landing.social_network_id in network_code_map:
                network_code = network_code_map[buy_landing.social_network_id]
                buy_landing_path = f'/{network_code}/{buy_landing.slug}'
                # Помечаем BuyLanding пути как объекты для идентификации
                paths.append({
                    'path': buy_landing_path,
                    'is_buy_landing': True
                })
        
        return Response({
            'paths': paths,
            'total': len(paths)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'[get_sitemap_data] Error getting sitemap data: {str(e)}\nTraceback: {traceback.format_exc()}')
        return Response(
            {'error': 'Failed to get sitemap data'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def game(request):
    """
    Endpoint for handling game rewards
    Accepts:
    - user_id: number (required) - ID профиля пользователя
    - type: str (required) - 'tasks' or 'points'
    - amount: int (required) - amount to add
    """
    logger.info(f'[game] Received request data: {request.data}')
    
    # Константы для наград
    TASKS_FOR_REWARD = 5  # Количество заданий для получения награды
    POINTS_REWARD_AMOUNT = 5  # Количество поинтов за награду
    TASKS_REWARD_AMOUNT = 2  # Количество заданий за награду
    DAILY_TASKS_REWARD_AMOUNT = 1  # Количество ежедневных заданий за награду
    
    user_id = request.data.get('user_id')
    reward_type = request.data.get('type')
    amount = request.data.get('amount')
    
    # Validate input parameters
    if not all([user_id, reward_type, amount]):
        logger.warning(f'[game] Missing required fields: user_id={user_id}, type={reward_type}, amount={amount}')
        return Response(
            {'error': 'user_id, type and amount are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
            
        # Проверяем соответствие amount типу награды
        if reward_type == 'points' and amount != POINTS_REWARD_AMOUNT:
            raise ValueError(f"Invalid points amount. Expected: {POINTS_REWARD_AMOUNT}")
        elif reward_type == 'tasks' and amount != TASKS_REWARD_AMOUNT:
            raise ValueError(f"Invalid tasks amount. Expected: {TASKS_REWARD_AMOUNT}")
            
    except ValueError as e:
        logger.warning(f'[game] Invalid amount value: {amount}')
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get user profile directly by id
        user_profile = UserProfile.objects.filter(id=user_id).first()
        if not user_profile:
            logger.warning(f'[game] UserProfile not found with id: {user_id}')
            return Response(
                {'error': 'User not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем, может ли пользователь получить награду
        tasks_after_last_reward = user_profile.bonus_tasks_completed - user_profile.last_reward_at_task_count
        if tasks_after_last_reward < TASKS_FOR_REWARD:
            logger.warning(f'[game] User {user_id} trying to claim reward too early. Tasks after last reward: {tasks_after_last_reward}, Required: {TASKS_FOR_REWARD}')
            return Response(
                {'error': 'Cannot claim reward yet'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем соответствие типа награды текущему состоянию
        rewards_received = user_profile.game_rewards_claimed
        is_points_reward = rewards_received % 2 == 0  # Первая награда (0) - поинты, вторая (1) - таски
        expected_type = 'points' if is_points_reward else 'tasks'
        if reward_type != expected_type:
            logger.warning(f'[game] Invalid reward type for current state. Expected: {expected_type}, Got: {reward_type}. Rewards received: {rewards_received}')
            return Response(
                {'error': f'Invalid reward type. Expected: {expected_type}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            user_profile = UserProfile.objects.select_for_update().get(id=user_id)
            
            if reward_type == 'tasks':
                user_profile.available_tasks += amount
                user_profile.daily_task_limit += DAILY_TASKS_REWARD_AMOUNT
                message = f'Successfully added {amount} available tasks and {DAILY_TASKS_REWARD_AMOUNT} daily task limit'
                logger.info(f'[game] Added {amount} tasks and {DAILY_TASKS_REWARD_AMOUNT} daily task limit for user profile {user_id}. New total: available_tasks={user_profile.available_tasks}, daily_task_limit={user_profile.daily_task_limit}')
            elif reward_type == 'points':
                user_profile.balance += amount
                message = f'Successfully added {amount} points'
                logger.info(f'[game] Added {amount} points for user profile {user_id}. New balance: {user_profile.balance}')
            else:
                logger.warning(f'[game] Invalid reward type: {reward_type}')
                return Response(
                    {'error': 'Invalid reward type. Must be either "tasks" or "points"'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Обновляем счетчики наград
            user_profile.game_rewards_claimed += 1
            user_profile.last_reward_at_task_count = user_profile.bonus_tasks_completed
            logger.info(f'[game] Updated reward counters for user {user_id}. Rewards claimed: {user_profile.game_rewards_claimed}, Last reward at: {user_profile.last_reward_at_task_count}, Bonus tasks: {user_profile.bonus_tasks_completed}')
            
            user_profile.save(update_fields=[
                'balance', 
                'available_tasks',
                'daily_task_limit',
                'game_rewards_claimed',
                'last_reward_at_task_count'
            ])
            
            return Response({
                'message': message,
                'reward_type': reward_type,
                'amount': amount,
                'new_balance': user_profile.balance,
                'new_available_tasks': user_profile.available_tasks,
                'new_daily_task_limit': user_profile.daily_task_limit,
                'game_rewards_claimed': user_profile.game_rewards_claimed,
                'next_reward_at': user_profile.last_reward_at_task_count + TASKS_FOR_REWARD,
                'bonus_tasks_completed': user_profile.bonus_tasks_completed
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f'[game] Error processing game reward: {str(e)}')
        return Response(
            {'error': 'Failed to process reward'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stripe_session(request):
    """
    Создает сессию оплаты Stripe и возвращает URL для оплаты
    """
    try:
        payment_type = request.data.get('payment_type', 'ONE_TIME')
        price_id = request.data.get('price_id')
        
        if not price_id:
            return Response(
                {'error': 'Price ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверяем, был ли у пользователя триал раньше
        had_trial = PaymentTransaction.objects.filter(
            user=request.user,
            payment_type='SUBSCRIPTION',
            user_has_trial_before=True
        ).exists()

        # Создаем сессию Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        success_url = settings.STRIPE_SUCCESS_URL
        cancel_url = settings.STRIPE_CANCEL_URL

        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': 'subscription',
            'subscription_data': {
                'trial_period_days': None if had_trial else 7,
                'payment_behavior': 'allow_incomplete',
                'metadata': {
                    'had_trial_before': str(had_trial),
                    'is_trial': str(not had_trial)
                }
            },
            'success_url': success_url,
            'cancel_url': cancel_url,
            'payment_method_collection': 'always',
            'allow_promotion_codes': True, 
            'metadata': {
                'had_trial_before': str(had_trial),
                'is_trial': str(not had_trial)
            }
        }

        if request.user.stripe_customer_id:
            session_params['customer'] = request.user.stripe_customer_id
        else:
            session_params['customer_email'] = request.user.email

        session = stripe.checkout.Session.create(**session_params)

        # Создаем запись о транзакции
        transaction = PaymentTransaction.objects.create(
            user=request.user,
            points=0,  # Будет обновлено после успешной оплаты
            amount=0,  # Будет обновлено после успешной оплаты
            payment_id=str(uuid.uuid4()),
            status='PENDING',
            payment_type=payment_type,
            stripe_session_id=session.id,
            user_has_trial_before=had_trial
            
        )

        logger.info(f"[create_stripe_session] Created session for user {request.user.id}: {session.id}")
        
        return Response({
            'session_id': session.id,
            'session_url': session.url
        })

    except Exception as e:
        logger.error(f"[create_stripe_session] Error creating session: {str(e)}")
        return Response(
            {'error': 'Failed to create payment session'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscription_status(request):
    """
    Возвращает статус подписки пользователя
    """
    try:
        latest_subscription = PaymentTransaction.objects.filter(
            user=request.user,
            payment_type='SUBSCRIPTION',
            status__in=['ACTIVE', 'TRIAL']
        ).order_by('-created_at').first()

        if not latest_subscription:
            return Response({
                'has_active_subscription': False,
                'subscription_data': None
            })

        subscription_data = {
            'status': latest_subscription.status,
            'trial_end_date': latest_subscription.trial_end_date,
            'period_end': latest_subscription.subscription_period_end,
            'period_start': latest_subscription.subscription_period_start,
            'had_trial_before': latest_subscription.user_has_trial_before
        }

        return Response({
            'has_active_subscription': True,
            'subscription_data': subscription_data
        })

    except Exception as e:
        logger.error(f"[get_subscription_status] Error: {str(e)}")
        return Response(
            {'error': 'Failed to get subscription status'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def create_subscription(request):
    """
    Создает подписку Stripe для пользователя по его Firebase UID
    """
    try:
        # Получаем и валидируем входные данные
        firebase_uid = request.data.get('firebase_uid')
        plan = request.data.get('plan')
        subscription_type = request.data.get('subscription_type', '').upper()
        is_trial = request.data.get('is_trial', False)
        
        logger.info(f"""[create_subscription] Received request data:
            firebase_uid: {firebase_uid}
            plan: {plan}
            subscription_type: {subscription_type}
            is_trial: {is_trial}
            raw_data: {request.data}
        """)
        
        if not all([firebase_uid, plan, subscription_type]):
            logger.error(f"""[create_subscription] Missing required fields:
                firebase_uid: {bool(firebase_uid)}
                plan: {bool(plan)}
                subscription_type: {bool(subscription_type)}
            """)
            return Response(
                {'error': 'firebase_uid, plan and subscription_type are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if plan not in SUBSCRIPTION_PLAN_CONFIG:
            logger.error(f"""[create_subscription] Invalid plan:
                received plan: {plan}
                available plans: {list(SUBSCRIPTION_PLAN_CONFIG.keys())}
            """)
            return Response(
                {'error': 'Invalid plan'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        period = 'monthly' if subscription_type == 'MONTHLY' else 'annual'
        if period not in SUBSCRIPTION_PERIODS:
            logger.error(f"""[create_subscription] Invalid subscription_type:
                received type: {subscription_type}
                period: {period}
                available periods: {list(SUBSCRIPTION_PERIODS.keys())}
            """)
            return Response(
                {'error': 'Invalid subscription_type. Must be MONTHLY or ANNUAL'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем данные пользователя из Firebase
        try:
            firebase_user = auth.get_user(firebase_uid)
            logger.info(f"[create_subscription] Got Firebase user data: {firebase_user.uid}")
        except Exception as e:
            logger.error(f"[create_subscription] Error getting Firebase user: {str(e)}")
            return Response(
                {'error': 'Invalid Firebase user ID'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем или создаем пользователя Django
        try:
            user = User.objects.get(username=firebase_uid)
        except User.DoesNotExist:
            user = User.objects.create(username=firebase_uid)
            UserProfile.objects.create(user=user)
            logger.info(f"[create_subscription] Created new user for Firebase UID: {firebase_uid}")

        # Проверяем, был ли у пользователя триал раньше
        previous_subscription = PaymentTransaction.objects.filter(
            user=user,
            payment_type='SUBSCRIPTION',
            stripe_customer_id__isnull=False
        ).order_by('-created_at').first()

        had_trial = PaymentTransaction.objects.filter(
            user=user,
            payment_type='SUBSCRIPTION',
            user_has_trial_before=True
        ).exists()

        if had_trial and is_trial:
            logger.warning(f"[create_subscription] User {user.id} already used trial period, proceeding with regular subscription")
            is_trial = False
            trial_period_days = None
        else:
            trial_period_days = 7 if is_trial else None
        
        # Создаем сессию Stripe
        try:
            price_id = SUBSCRIPTION_PLAN_CONFIG[plan][period]['price_id']
            logger.info(f"""[create_subscription] Getting price_id:
                plan: {plan}
                period: {period}
                price_id: {price_id}
                config: {SUBSCRIPTION_PLAN_CONFIG[plan][period]}
            """)
        except Exception as e:
            logger.error(f"""[create_subscription] Error getting price_id:
                plan: {plan}
                period: {period}
                error: {str(e)}
                config: {SUBSCRIPTION_PLAN_CONFIG.get(plan, {})}
            """)
            return Response(
                {'error': f'Error getting price_id: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': 'subscription',
            'subscription_data': {
                'trial_period_days': trial_period_days,
                'payment_behavior': 'allow_incomplete',
                'metadata': {
                    'had_trial_before': str(had_trial),
                    'is_trial': str(bool(trial_period_days))
                }
            },
            'success_url': settings.STRIPE_SUCCESS_URL,
            'cancel_url': settings.STRIPE_CANCEL_URL,
            'payment_method_collection': 'always',
            'allow_promotion_codes': True, 
            'metadata': {
                'had_trial_before': str(had_trial),
                'is_trial': str(bool(trial_period_days))
            }
        }

        if previous_subscription and previous_subscription.stripe_customer_id:
            session_params['customer'] = previous_subscription.stripe_customer_id
            logger.info(f"[create_subscription] Using existing Stripe customer: {previous_subscription.stripe_customer_id}")
        else:
            session_params['customer_email'] = firebase_user.email

        session = stripe.checkout.Session.create(**session_params)
        logger.info(f"[create_subscription] Created Stripe session: {session.id}")

        # Создаем запись о транзакции
        try:
            points = SUBSCRIPTION_PLAN_CONFIG[plan][period]['points']
            transaction = PaymentTransaction.objects.create(
                user=user,
                points=points,
                amount=0,  # Сумма будет обновлена после успешного платежа
                payment_id=f"sub_{uuid.uuid4().hex[:8]}",
                status='PENDING',
                payment_type='SUBSCRIPTION',
                stripe_session_id=session.id,
                user_has_trial_before=had_trial,
                subscription_period_type='MONTHLY' if subscription_type == 'MONTHLY' else 'ANNUAL'
            )
            logger.info(f"""[create_subscription] Created transaction:
                ID: {transaction.id}
                Points: {points}
                Session ID: {session.id}
                Period Type: {transaction.subscription_period_type}
            """)
        except Exception as e:
            logger.error(f"[create_subscription] Error creating transaction: {str(e)}")
            return Response(
                {'error': f'Error creating transaction: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"""[create_subscription] Successfully created subscription:
            Plan: {plan}
            Period: {subscription_type}
            Session ID: {session.id}
            Transaction ID: {transaction.payment_id}
        """)
        
        return Response({
            'session_id': session.id,
            'session_url': session.url
        })

    except stripe.error.StripeError as e:
        logger.error(f"[create_subscription] Stripe error: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"[create_subscription] Error creating subscription: {str(e)}")
        return Response(
            {'error': 'Failed to create subscription'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def subscription_info(request):
    """
    Возвращает детальную информацию о подписке пользователя
    """
    logger.info(f"[subscription_info] Getting subscription info for user {request.user.id}")
    
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        # Получаем информацию о последней транзакции подписки
        latest_subscription = PaymentTransaction.objects.filter(
            user=request.user,
            payment_type='SUBSCRIPTION',
            status__in=['ACTIVE', 'TRIAL']
        ).order_by('-created_at').first()
        
        # Если нет активной подписки, устанавливаем статус FREE
        if not latest_subscription:
            user_profile.status = 'FREE'
            user_profile.save(update_fields=['status'])
        
        # Получаем конфигурацию текущего плана
        plan_config = SUBSCRIPTION_PLAN_CONFIG.get(user_profile.status, SUBSCRIPTION_PLAN_CONFIG['FREE'])
        
        # Определяем период подписки
        subscription_period = 'monthly'
        if latest_subscription and latest_subscription.subscription_period_type:
            subscription_period = latest_subscription.subscription_period_type.lower()
        
        # Получаем points в зависимости от периода
        points_per_period = 0
        if user_profile.status != 'FREE' and subscription_period:
            points_per_period = plan_config[subscription_period]['points']
        
        response_data = {
            'plan': {
                'name': user_profile.status,
                'daily_task_limit': user_profile.get_daily_task_limit(),
                'discount_rate': user_profile.get_discount_rate(),
                'points_per_period': points_per_period,
                'initial_points': plan_config.get('initial_points', 0),
                'trial_days': plan_config.get('trial_days', 0)
            },
            'current_points': user_profile.balance,
            'available_tasks': user_profile.available_tasks,
            'is_trial': False,
            'trial_end_date': None,
            'next_payment_date': None,
            'subscription_created_at': None,
            'subscription_period': None
        }
        
        if latest_subscription:
            response_data.update({
                'is_trial': latest_subscription.status == 'TRIAL',
                'trial_end_date': latest_subscription.trial_end_date,
                'next_payment_date': latest_subscription.subscription_period_end,
                'subscription_created_at': latest_subscription.created_at,
                'subscription_period': latest_subscription.subscription_period_type.lower() if latest_subscription.subscription_period_type else None
            })
            
            logger.info(f"""
                [subscription_info] Subscription details:
                User: {request.user.id}
                Plan: {user_profile.status}
                Period: {latest_subscription.subscription_period_type}
                Trial: {latest_subscription.status == 'TRIAL'}
                Trial End: {latest_subscription.trial_end_date}
                Next Payment: {latest_subscription.subscription_period_end}
            """)
        else:
            logger.info(f"""
                [subscription_info] No active subscription, using FREE plan:
                User: {request.user.id}
                Plan: FREE
                Daily Task Limit: {response_data['plan']['daily_task_limit']}
                Initial Points: {response_data['plan']['initial_points']}
            """)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except UserProfile.DoesNotExist:
        logger.error(f"[subscription_info] UserProfile not found for user {request.user.id}")
        return Response(
            {'error': 'User profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"[subscription_info] Error getting subscription info: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intent(request):
    """
    Создает платежное намерение Stripe для покупки поинтов или создания задания
    """
    try:
        data = request.data
        points = data.get('points') or data.get('packageId')  # Поддержка обоих параметров
        amount = data.get('amount')
        task_purchase = data.get('task_purchase', False)
        
        if not points or not amount:
            return Response({
                'error': 'Points and amount are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Создаем платежное намерение
        metadata = {
            'points': points,
            'user_id': request.user.id
        }
        
        if task_purchase:
            metadata['task_purchase'] = 'true'
            
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Конвертируем в центы
            currency='usd',
            automatic_payment_methods={
                'enabled': True,
            },
            metadata=metadata
        )
        
        # Возвращаем client_secret для подтверждения платежа на фронтенде
        return Response({
            'clientSecret': intent.client_secret,
            'billingDetails': {
                'name': request.user.username,
                'email': request.user.email
            }
        })
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subscription_intent(request):
    """
    Создает Stripe customer, setup intent и подписку для inline формы
    """
    logger.info(f"[create_subscription_intent] Starting subscription intent creation for user {request.user.id}")
    logger.info(f"[create_subscription_intent] Request data: {request.data}")
    
    try:
        # Получаем данные из запроса
        price_id = request.data.get('price_id')
        is_trial = request.data.get('is_trial', False)
        billing_details = request.data.get('billing_details', {})
        promo_code = request.data.get('promo_code', None)
        
        logger.info(f"""[create_subscription_intent] Extracted data:
            price_id: {price_id}
            is_trial: {is_trial}
            billing_details: {billing_details}
            promo_code: {promo_code}
        """)
        
        # Валидация входных данных
        if not price_id:
            logger.error("[create_subscription_intent] price_id is required")
            return Response(
                {'error': 'price_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Инициализируем Stripe для получения информации о price
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        try:
            stripe_price = stripe.Price.retrieve(price_id)
            logger.info(f"[create_subscription_intent] Retrieved Stripe price: {stripe_price}")
            
            amount = stripe_price.unit_amount / 100  # конвертируем из центов в доллары
            interval = stripe_price.recurring.interval if stripe_price.recurring else 'month'
            
            # Определяем plan и subscription_type из metadata или по price_id
            plan = None
            if interval == 'month':
                subscription_type = 'MONTHLY'
            elif interval == 'year':
                subscription_type = 'ANNUAL'
            else:
                logger.error(f"[create_subscription_intent] Unsupported interval: {interval}")
                return Response(
                    {'error': f'Unsupported subscription interval: {interval}. Only monthly and annual are supported.'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            points = 0
            
            # Ищем соответствующий план в конфигурации
            logger.info(f"[create_subscription_intent] Searching for price_id: {price_id}")
            logger.info(f"[create_subscription_intent] Available plans: {list(SUBSCRIPTION_PLAN_CONFIG.keys())}")
            
            for plan_name, plan_config in SUBSCRIPTION_PLAN_CONFIG.items():
                logger.info(f"[create_subscription_intent] Checking plan: {plan_name}")
                for period, period_config in plan_config.items():
                    if isinstance(period_config, dict):
                        current_price_id = period_config.get('price_id')
                        logger.info(f"[create_subscription_intent] Period {period}: price_id = {current_price_id}")
                        if current_price_id == price_id:
                            plan = plan_name
                            points = period_config.get('points', 0)
                            logger.info(f"[create_subscription_intent] Found matching plan: {plan}, points: {points}")
                            break
                if plan:
                    break
            
            if not plan:
                logger.error(f"[create_subscription_intent] Could not find plan for price_id: {price_id}")
                return Response(
                    {'error': 'Invalid price_id'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            logger.info(f"""[create_subscription_intent] Plan configuration:
                plan: {plan}
                subscription_type: {subscription_type}
                amount: {amount}
                points: {points}
                interval: {interval}
            """)
            
        except stripe.error.StripeError as e:
            logger.error(f"[create_subscription_intent] Error retrieving Stripe price: {str(e)}")
            return Response(
                {'error': f'Invalid price_id: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверяем, был ли у пользователя триал раньше
        had_trial = PaymentTransaction.objects.filter(
            user=request.user,
            payment_type='SUBSCRIPTION',
            user_has_trial_before=True
        ).exists()

        if had_trial and is_trial:
            logger.warning(f"[create_subscription_intent] User {request.user.id} already used trial period")
            return Response(
                {'error': 'Trial period already used'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # 1. Создаем или получаем существующего Stripe customer
            existing_transaction = PaymentTransaction.objects.filter(
                user=request.user,
                stripe_customer_id__isnull=False
            ).order_by('-created_at').first()

            if existing_transaction and existing_transaction.stripe_customer_id:
                customer_id = existing_transaction.stripe_customer_id
                logger.info(f"[create_subscription_intent] Using existing customer: {customer_id}")
            else:
                # Создаем нового customer
                customer = stripe.Customer.create(
                    email=billing_details.get('email') or request.user.email,
                    name=billing_details.get('name'),
                    phone=billing_details.get('phone'),
                    address={
                        'line1': billing_details.get('address', {}).get('line1'),
                        'line2': billing_details.get('address', {}).get('line2'),
                        'city': billing_details.get('address', {}).get('city'),
                        'state': billing_details.get('address', {}).get('state'),
                        'postal_code': billing_details.get('address', {}).get('postal_code'),
                        'country': billing_details.get('address', {}).get('country', 'US'),
                    },
                    metadata={
                        'user_id': str(request.user.id),
                        'plan': plan,
                        'subscription_type': subscription_type
                    }
                )
                customer_id = customer.id
                logger.info(f"[create_subscription_intent] Created new customer: {customer_id}")

            # 2. Создаем Setup Intent для сохранения карты
            setup_intent = stripe.SetupIntent.create(
                customer=customer_id,
                payment_method_types=['card'],
                usage='off_session',
                payment_method_options={
                    'card': {
                        'request_three_d_secure': 'any',
                    }
                },
                metadata={
                    'user_id': str(request.user.id),
                    'plan': plan,
                    'subscription_type': subscription_type,
                    'is_trial': str(is_trial)
                }
            )
            
            logger.info(f"[create_subscription_intent] Created setup intent: {setup_intent.id}")

            # 3. Создаем транзакцию для отслеживания
            payment_transaction = PaymentTransaction.objects.create(
                user=request.user,
                points=points,
                amount=0 if is_trial else amount,
                payment_id=f"setup_{setup_intent.id}",
                status='PENDING',
                payment_type='SUBSCRIPTION',
                stripe_customer_id=customer_id,
                stripe_payment_intent_id=setup_intent.id,
                user_has_trial_before=had_trial,
                subscription_period_type=subscription_type,
                stripe_metadata={
                    'setup_intent_id': setup_intent.id,
                    'price_id': price_id,
                    'plan': plan,
                    'is_trial': is_trial,
                    'billing_details': billing_details,
                    'promo_code': promo_code if promo_code else ''
                }
            )

            logger.info(f"""[create_subscription_intent] Created payment transaction:
                ID: {payment_transaction.id}
                Setup Intent: {setup_intent.id}
                Customer: {customer_id}
                Plan: {plan}
                Is Trial: {is_trial}
            """)

            # 4. Возвращаем данные для фронтенда
            return Response({
                'client_secret': setup_intent.client_secret,
                'customer_id': customer_id,
                'setup_intent_id': setup_intent.id,
                'transaction_id': payment_transaction.id,
                'price_id': price_id,
                'points': points,
                'is_trial': is_trial,
                'billing_details': {
                    'name': billing_details.get('name') or request.user.username,
                    'email': billing_details.get('email') or request.user.email
                }
            }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error(f"[create_subscription_intent] Stripe error: {str(e)}")
        return Response(
            {'error': f'Stripe error: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"[create_subscription_intent] Error creating subscription intent: {str(e)}")
        return Response(
            {'error': 'Failed to create subscription intent'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_subscription(request):
    """
    Подтверждает подписку после успешного сохранения карты
    """
    logger.info(f"[confirm_subscription] Confirming subscription for user {request.user.id}")
    logger.info(f"[confirm_subscription] Request data: {request.data}")
    
    try:
        setup_intent_id = request.data.get('setup_intent_id')
        transaction_id = request.data.get('transaction_id')
        
        if not setup_intent_id or not transaction_id:
            logger.error("[confirm_subscription] setup_intent_id and transaction_id are required")
            return Response(
                {'error': 'setup_intent_id and transaction_id are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем транзакцию
        try:
            payment_transaction = PaymentTransaction.objects.get(
                id=transaction_id,
                user=request.user,
                status='PENDING'
            )
        except PaymentTransaction.DoesNotExist:
            logger.error(f"[confirm_subscription] Transaction not found: {transaction_id}")
            return Response(
                {'error': 'Transaction not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Инициализируем Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        # Получаем setup intent
        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
        
        if setup_intent.status != 'succeeded':
            logger.error(f"[confirm_subscription] Setup intent not succeeded: {setup_intent.status}")
            return Response(
                {'error': 'Setup intent not completed'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Получаем промокод из запроса или из метаданных транзакции
        promo_code = request.data.get('promo_code', None)
        
        # Получаем данные из метаданных транзакции
        metadata = payment_transaction.stripe_metadata
        price_id = metadata.get('price_id')
        plan = metadata.get('plan')
        is_trial = metadata.get('is_trial', False)
        
        # Если промокод не передан в запросе, берем из метаданных
        if not promo_code:
            promo_code = metadata.get('promo_code', None)
        
        logger.info(f"""[confirm_subscription] Retrieved metadata:
            price_id: {price_id}
            plan: {plan}
            is_trial: {is_trial}
            promo_code: {promo_code}
            customer_id: {payment_transaction.stripe_customer_id}
        """)
        
        if is_trial:
            logger.info(f"[confirm_subscription] Trial selected - will perform $1 verification charge")
        else:
            logger.info(f"[confirm_subscription] No trial selected - will skip $1 verification charge and charge full amount immediately")

        with transaction.atomic():
            # 1) Проводим верификационный платёж $1 только для триала
            if is_trial:
                try:
                    verification_intent = stripe.PaymentIntent.create(
                        amount=100,  # $1.00 в центах
                        currency='usd',
                        customer=payment_transaction.stripe_customer_id,
                        payment_method=setup_intent.payment_method,
                        confirm=True,
                        off_session=True,
                        automatic_payment_methods={
                            'enabled': True,
                            'allow_redirects': 'never'
                        },
                        description='Subscription card verification $1',
                        metadata={
                            'user_id': str(request.user.id),
                            'transaction_id': str(payment_transaction.id),
                            'type': 'VERIFICATION_CHARGE'
                        },
                        idempotency_key=f"verify_{payment_transaction.id}"
                    )
                except stripe.error.CardError as e:
                    logger.error(f"[confirm_subscription] $1 verification charge failed (card): {str(e)}")
                    return Response(
                        {'error': 'Verification $1 charge failed. Please try another card.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except stripe.error.StripeError as e:
                    logger.error(f"[confirm_subscription] $1 verification charge failed (stripe): {str(e)}")
                    return Response(
                        {'error': 'Verification $1 charge failed. Please try again later.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    logger.error(f"[confirm_subscription] $1 verification charge failed (unknown): {str(e)}")
                    return Response(
                        {'error': 'Verification $1 charge failed due to an unexpected error.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if verification_intent.status != 'succeeded':
                    logger.error(f"[confirm_subscription] $1 verification charge did not succeed. Status: {verification_intent.status}")
                    return Response(
                        {'error': 'Verification $1 charge did not succeed.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Записываем транзакцию верификационного списания $1
                try:
                    PaymentTransaction.objects.create(
                        user=request.user,
                        points=0,
                        amount=Decimal('1.00'),
                        payment_id=f"verify_{verification_intent.id}",
                        status='COMPLETED',
                        payment_type='ONE_TIME',
                        stripe_payment_intent_id=verification_intent.id,
                        stripe_customer_id=payment_transaction.stripe_customer_id,
                    )
                    logger.info(f"[confirm_subscription] $1 verification charge recorded. PI: {verification_intent.id}")
                except Exception as e:
                    logger.error(f"[confirm_subscription] Failed to record $1 verification payment: {str(e)}")
                    return Response(
                        {'error': 'Failed to record verification payment'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                logger.info(f"[confirm_subscription] Skipping $1 verification charge - no trial selected")

            # 2) Создаем подписку в Stripe
            subscription_params = {
                'customer': payment_transaction.stripe_customer_id,
                'items': [{
                    'price': price_id,
                }],
                'default_payment_method': setup_intent.payment_method,
                'expand': ['latest_invoice.payment_intent'],
                'metadata': {
                    'user_id': str(request.user.id),
                    'plan': plan,
                    'transaction_id': str(payment_transaction.id),
                    'is_trial': str(is_trial),
                    'promo_code': promo_code if promo_code else ''
                }
            }

            # Добавляем триал если нужно
            if is_trial:
                subscription_params['trial_period_days'] = 7

            # Применяем промокод если он есть
            promo_applied = False
            if promo_code:
                try:
                    # Пытаемся найти promotion code по коду
                    promotion_codes = stripe.PromotionCode.list(active=True, code=promo_code, limit=1)
                    if promotion_codes.data:
                        promotion_code_id = promotion_codes.data[0].id
                        subscription_params['discounts'] = [{
                            'promotion_code': promotion_code_id
                        }]
                        promo_applied = True
                        logger.info(f"[confirm_subscription] Applying promotion code: {promo_code} (ID: {promotion_code_id})")
                    else:
                        # Если promotion code не найден, пытаемся использовать как coupon ID
                        try:
                            coupon = stripe.Coupon.retrieve(promo_code)
                            subscription_params['coupon'] = promo_code
                            promo_applied = True
                            logger.info(f"[confirm_subscription] Applying coupon by ID: {promo_code}")
                        except stripe.error.InvalidRequestError:
                            # Если не найден по ID, пытаемся найти по имени (name)
                            try:
                                all_coupons = stripe.Coupon.list(limit=100)
                                coupon = None
                                for c in all_coupons.data:
                                    if c.name and c.name.upper() == promo_code.upper():
                                        coupon = c
                                        break
                                
                                if coupon:
                                    subscription_params['coupon'] = coupon.id
                                    promo_applied = True
                                    logger.info(f"[confirm_subscription] Applying coupon by name: {promo_code} (ID: {coupon.id})")
                                else:
                                    logger.warning(f"[confirm_subscription] Promo code/coupon not found: {promo_code}")
                            except Exception as e:
                                logger.error(f"[confirm_subscription] Error searching coupon by name: {str(e)}")
                                logger.warning(f"[confirm_subscription] Promo code/coupon not found: {promo_code}")
                except stripe.error.StripeError as e:
                    logger.error(f"[confirm_subscription] Error applying promo code: {str(e)}")
                    # Продолжаем создание подписки без промокода

            subscription = stripe.Subscription.create(**subscription_params)
            
            # Логируем информацию о промокоде и скидке
            invoice_discount = 0
            invoice_subtotal = 0
            invoice_total = 0
            
            if promo_applied and subscription.latest_invoice:
                try:
                    invoice = stripe.Invoice.retrieve(subscription.latest_invoice)
                    invoice_subtotal = invoice.subtotal / 100 if invoice.subtotal else 0
                    invoice_total = invoice.total / 100 if invoice.total else 0
                    amount_due = invoice.amount_due / 100 if invoice.amount_due else 0
                    invoice_discount = invoice_subtotal - invoice_total
                    discounts = invoice.discounts or []
                    discount_info = []
                    for disc in discounts:
                        if disc.coupon:
                            discount_info.append({
                                'coupon_id': disc.coupon.id,
                                'percent_off': disc.coupon.percent_off,
                                'amount_off': disc.coupon.amount_off / 100 if disc.coupon.amount_off else 0
                            })
                    
                    logger.info(f"""[confirm_subscription] Promo code applied:
                        Promo Code: {promo_code}
                        Subtotal: ${invoice_subtotal}
                        Total: ${invoice_total}
                        Amount Due: ${amount_due}
                        Discount: ${invoice_discount}
                        Discount Details: {discount_info}
                    """)
                except Exception as e:
                    logger.warning(f"[confirm_subscription] Could not retrieve invoice details: {str(e)}")
            elif promo_code and not promo_applied:
                logger.warning(f"[confirm_subscription] Promo code {promo_code} was provided but could not be applied")
            
            logger.info(f"""[confirm_subscription] Created subscription:
                ID: {subscription.id}
                Status: {subscription.status}
                Trial End: {subscription.trial_end}
                Current Period End: {subscription.current_period_end}
                Promo Code: {promo_code if promo_code else 'None'}
                Promo Applied: {promo_applied}
            """)

            # Обновляем транзакцию
            payment_transaction.stripe_subscription_id = subscription.id
            payment_transaction.status = 'TRIAL' if is_trial else 'ACTIVE'
            
            if subscription.trial_end:
                payment_transaction.trial_end_date = timezone.datetime.fromtimestamp(subscription.trial_end)
            if subscription.current_period_start:
                payment_transaction.subscription_period_start = timezone.datetime.fromtimestamp(subscription.current_period_start)
            if subscription.current_period_end:
                payment_transaction.subscription_period_end = timezone.datetime.fromtimestamp(subscription.current_period_end)
            
            # Сохраняем промокод и информацию о скидке в метаданные транзакции
            if payment_transaction.stripe_metadata:
                payment_transaction.stripe_metadata.update({
                    'promo_code': promo_code if promo_code else '',
                    'promo_applied': promo_applied,
                    'discount_amount': invoice_discount,
                    'subtotal': invoice_subtotal,
                    'total': invoice_total
                })
            else:
                payment_transaction.stripe_metadata = {
                    'promo_code': promo_code if promo_code else '',
                    'promo_applied': promo_applied,
                    'discount_amount': invoice_discount,
                    'subtotal': invoice_subtotal,
                    'total': invoice_total
                }
            
            payment_transaction.save()

            # Обновляем профиль пользователя
            user_profile = UserProfile.objects.select_for_update().get(user=request.user)
            
            if is_trial:
                # Для триала обновляем статус и даты триала
                user_profile.status = plan
                user_profile.trial_start_date = timezone.now()
                user_profile.trial_end_date = payment_transaction.trial_end_date
                logger.info(f"[confirm_subscription] Started trial for user {request.user.id}: {plan}")
            else:
                # Для обычной подписки начисляем поинты и обновляем статус
                user_profile.balance += payment_transaction.points
                user_profile.status = plan
                logger.info(f"[confirm_subscription] Added {payment_transaction.points} points and set status to {plan} for user {request.user.id}")

            user_profile.save()

            logger.info(f"""[confirm_subscription] Successfully confirmed subscription:
                User: {request.user.id}
                Plan: {plan}
                Status: {payment_transaction.status}
                Subscription ID: {subscription.id}
                Trial End: {payment_transaction.trial_end_date}
                New Balance: {user_profile.balance}
                User Status: {user_profile.status}
            """)

            return Response({
                'success': True,
                'subscription_id': subscription.id,
                'status': payment_transaction.status,
                'plan': plan,
                'trial_end_date': payment_transaction.trial_end_date,
                'new_balance': user_profile.balance,
                'user_status': user_profile.status
            }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error(f"[confirm_subscription] Stripe error: {str(e)}")
        return Response(
            {'error': f'Stripe error: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"[confirm_subscription] Error confirming subscription: {str(e)}")
        return Response(
            {'error': 'Failed to confirm subscription'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_promo_code_info(request):
    """
    Возвращает информацию о промокоде из Stripe (скидка, тип скидки)
    """
    try:
        promo_code = request.GET.get('promo_code')
        
        if not promo_code:
            return Response(
                {'error': 'promo_code parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        try:
            # Пытаемся найти promotion code по коду
            promotion_codes = stripe.PromotionCode.list(active=True, code=promo_code, limit=1)
            
            if promotion_codes.data and len(promotion_codes.data) > 0:
                promotion_code_obj = promotion_codes.data[0]
                coupon = promotion_code_obj.coupon
                
                discount_info = {
                    'valid': True,
                    'code': promo_code,
                    'percent_off': coupon.percent_off,
                    'amount_off': coupon.amount_off / 100 if coupon.amount_off else None,
                    'currency': coupon.currency if coupon.amount_off else None,
                    'duration': coupon.duration,
                    'name': coupon.name if hasattr(coupon, 'name') else None
                }
                
                logger.info(f"[get_promo_code_info] Found promotion code: {promo_code}, discount: {discount_info}")
                return Response(discount_info, status=status.HTTP_200_OK)
            else:
                # Пытаемся использовать как coupon ID
                try:
                    coupon = stripe.Coupon.retrieve(promo_code)
                    discount_info = {
                        'valid': True,
                        'code': promo_code,
                        'percent_off': coupon.percent_off,
                        'amount_off': coupon.amount_off / 100 if coupon.amount_off else None,
                        'currency': coupon.currency if coupon.amount_off else None,
                        'duration': coupon.duration,
                        'name': coupon.name if hasattr(coupon, 'name') else None
                    }
                    
                    logger.info(f"[get_promo_code_info] Found coupon by ID: {promo_code}, discount: {discount_info}")
                    return Response(discount_info, status=status.HTTP_200_OK)
                except stripe.error.InvalidRequestError:
                    # Если не найден по ID, пытаемся найти по имени (name)
                    try:
                        all_coupons = stripe.Coupon.list(limit=100)
                        coupon = None
                        for c in all_coupons.data:
                            if c.name and c.name.upper() == promo_code.upper():
                                coupon = c
                                break
                        
                        if coupon:
                            discount_info = {
                                'valid': True,
                                'code': promo_code,
                                'percent_off': coupon.percent_off,
                                'amount_off': coupon.amount_off / 100 if coupon.amount_off else None,
                                'currency': coupon.currency if coupon.amount_off else None,
                                'duration': coupon.duration,
                                'name': coupon.name if hasattr(coupon, 'name') else None
                            }
                            
                            logger.info(f"[get_promo_code_info] Found coupon by name: {promo_code}, discount: {discount_info}")
                            return Response(discount_info, status=status.HTTP_200_OK)
                        else:
                            logger.warning(f"[get_promo_code_info] Promo code/coupon not found: {promo_code}")
                            return Response(
                                {'valid': False, 'error': 'Promo code not found'}, 
                                status=status.HTTP_404_NOT_FOUND
                            )
                    except Exception as e:
                        logger.error(f"[get_promo_code_info] Error searching coupon by name: {str(e)}")
                        return Response(
                            {'valid': False, 'error': 'Promo code not found'}, 
                            status=status.HTTP_404_NOT_FOUND
                        )
                    
        except stripe.error.StripeError as e:
            logger.error(f"[get_promo_code_info] Stripe error: {str(e)}")
            return Response(
                {'valid': False, 'error': f'Stripe error: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"[get_promo_code_info] Error: {str(e)}")
        return Response(
            {'valid': False, 'error': 'Failed to get promo code info'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def get_invited_users(request):
    """
    Получение списка приглашенных пользователей с их статистикой
    """
    try:
        logger.info(f"[get_invited_users] Starting request for user: {request.user.id}")
        
        # Получаем всех пользователей, приглашенных текущим пользователем
        invited_profiles = UserProfile.objects.filter(
            invited_by=request.user
        ).select_related(
            'user'
        ).order_by('-user__date_joined')  # Убрали prefetch_related payment_set

        logger.info(f"[get_invited_users] Found {invited_profiles.count()} invited profiles")

        serializer = InvitedUserSerializer(invited_profiles, many=True)
        
        # Добавляем общую статистику
        total_stats = {
            'total_users': invited_profiles.count(),
            'total_spent': sum(item['total_spent'] for item in serializer.data),
            'total_potential_earnings': sum(item['potential_earnings'] for item in serializer.data),
            'total_completed_tasks': sum(item['completed_tasks'] for item in serializer.data)
        }
        
        logger.info(f"[get_invited_users] Calculated stats: {total_stats}")
        
        return Response({
            'users': serializer.data,
            'stats': total_stats
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[get_invited_users] Error getting invited users: {str(e)}")
        logger.error(f"[get_invited_users] Full traceback:", exc_info=True)
        return Response(
            {'error': 'Failed to get invited users', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def update_user_profile(request):
    """
    Универсальный эндпоинт для обновления данных пользователя
    """
    logger.info(f'[update_user_profile] Updating user profile. User ID: {request.user.id}, Data: {request.data}')
    
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        # Получаем все доступные поля модели UserProfile
        allowed_fields = [f.name for f in UserProfile._meta.fields 
                         if f.name not in ['id', 'user', '_is_updating']]
        
        # Фильтруем входящие данные, оставляя только разрешенные поля
        update_data = {
            key: value for key, value in request.data.items() 
            if key in allowed_fields
        }
        
        if not update_data:
            logger.warning(f'[update_user_profile] No valid fields to update: {request.data}')
            return Response(
                {'error': 'No valid fields to update'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Обновляем только указанные поля
        for field, value in update_data.items():
            setattr(user_profile, field, value)
            
        user_profile.save()
        
        logger.info(f'[update_user_profile] Successfully updated fields: {update_data}')
        
        return Response({
            'message': 'Profile updated successfully',
            'updated_fields': update_data
        }, status=status.HTTP_200_OK)
        
    except UserProfile.DoesNotExist:
        logger.error(f'[update_user_profile] Profile not found for user {request.user.id}')
        return Response(
            {'error': 'User profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'[update_user_profile] Error updating profile: {str(e)}')
        return Response(
            {'error': 'Failed to update profile'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class UserSocialProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserSocialProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return UserSocialProfile.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        logger.info(f"[UserSocialProfileViewSet] Creating social profile. User: {request.user.id}, Data: {request.data}")
        
        try:
            serializer = CreateUserSocialProfileSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"[UserSocialProfileViewSet] Validation error: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # Проверяем, не существует ли уже профиль для этой соц.сети
            existing_profile = UserSocialProfile.objects.filter(
                user=request.user,
                social_network=serializer.validated_data['social_network']
            ).first()
            
            if existing_profile:
                logger.warning(f"[UserSocialProfileViewSet] Profile already exists for user {request.user.id} and network {serializer.validated_data['social_network'].code}")
                return Response(
                    {'error': 'Profile for this social network already exists'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Создаем профиль
            profile = UserSocialProfile.objects.create(
                user=request.user,
                social_network=serializer.validated_data['social_network'],
                profile_url=serializer.validated_data['profile_url']
            )
            
            logger.info(f"[UserSocialProfileViewSet] Created profile: {profile.id}")
            
            return Response(
                UserSocialProfileSerializer(profile).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"[UserSocialProfileViewSet] Error creating profile: {str(e)}")
            return Response(
                {'error': 'Failed to create social profile'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Массовое создание социальных профилей
        """
        logger.info(f"[UserSocialProfileViewSet] Bulk creating social profiles. User: {request.user.id}, Data: {request.data}")
        
        try:
            serializer = BulkCreateUserSocialProfileSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"[UserSocialProfileViewSet] Validation error: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            created_profiles = []
            errors = []
            
            # Проверяем существующие профили
            existing_profiles = UserSocialProfile.objects.filter(
                user=request.user,
                social_network__in=[p['social_network'] for p in serializer.validated_data['profiles']]
            ).values_list('social_network__code', flat=True)
            
            # Создаем новые профили
            for profile_data in serializer.validated_data['profiles']:
                if profile_data['social_network'].code in existing_profiles:
                    errors.append({
                        'social_network': profile_data['social_network'].code,
                        'error': 'Profile for this social network already exists'
                    })
                    continue
                    
                try:
                    profile = UserSocialProfile.objects.create(
                        user=request.user,
                        social_network=profile_data['social_network'],
                        username=profile_data['username'],
                        profile_url=profile_data['profile_url'],
                        verification_status='PENDING'
                    )
                    created_profiles.append(profile)
                    logger.info(f"[UserSocialProfileViewSet] Created profile: {profile.id} for network {profile.social_network.code}")
                except Exception as e:
                    errors.append({
                        'social_network': profile_data['social_network'].code,
                        'error': str(e)
                    })
            
            response_data = {
                'created_profiles': UserSocialProfileSerializer(created_profiles, many=True).data,
                'errors': errors
            }
            
            if created_profiles:
                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"[UserSocialProfileViewSet] Error in bulk create: {str(e)}")
            return Response(
                {'error': 'Failed to create social profiles'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def withdrawal_info(request):
    """
    Возвращает информацию о выводах средств пользователя и общую статистику
    """
    logger.info(f"[withdrawal_info] Getting withdrawal info for user {request.user.id}")
    
    try:
        user = request.user
        
        # Получаем все withdrawals пользователя
        withdrawals = Withdrawal.objects.filter(user=user).order_by('-created_at')
        
        # Подсчитываем статистику только по COMPLETED
        completed_withdrawals_qs = withdrawals.filter(status='COMPLETED')
        total_withdrawals = withdrawals.count()
        total_amount_usd = completed_withdrawals_qs.aggregate(
            total=Sum('amount_usd')
        )['total'] or 0
        total_points_sold = completed_withdrawals_qs.aggregate(
            total=Sum('points_sold')
        )['total'] or 0
        pending_withdrawals = withdrawals.filter(status='PENDING').count()
        completed_withdrawals = completed_withdrawals_qs.count()
        
        # Получаем константы
        min_withdrawal_amount = Withdrawal.get_min_withdrawal_amount()
        points_needed_for_min_withdrawal = Withdrawal.get_points_needed_for_min_withdrawal()
        conversion_rate = 0.01  # 1 поинт = $0.01
        
        # Получаем текущий баланс пользователя
        user_profile = user.userprofile
        current_balance = user_profile.balance
        max_withdrawal_amount = current_balance * conversion_rate
        
        # Проверяем, есть ли сохраненные адреса для вывода
        has_paypal_address = bool(user_profile.paypal_address)
        has_usdt_address = bool(user_profile.usdt_address)
        
        # Сериализуем withdrawals
        withdrawals_data = WithdrawalSerializer(withdrawals, many=True).data
        
        # Формируем статистику
        stats = {
            'total_withdrawals': total_withdrawals,
            'total_amount_usd': float(total_amount_usd),
            'total_points_sold': total_points_sold,
            'pending_withdrawals': pending_withdrawals,
            'completed_withdrawals': completed_withdrawals,
            'min_withdrawal_amount': min_withdrawal_amount,
            'conversion_rate': conversion_rate,
            'points_needed_for_min_withdrawal': points_needed_for_min_withdrawal,
            'current_balance': current_balance,
            'max_withdrawal_amount': max_withdrawal_amount,
            'has_paypal_address': has_paypal_address,
            'has_usdt_address': has_usdt_address
        }
        
        logger.info(f"""
            [withdrawal_info] Withdrawal info for user {user.id}:
            Total withdrawals: {total_withdrawals}
            Total amount (COMPLETED only): ${total_amount_usd}
            Current balance: {current_balance} points
            Max withdrawal: ${max_withdrawal_amount}
        """)
        
        return Response({
            'withdrawals': withdrawals_data,
            'stats': stats
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[withdrawal_info] Error getting withdrawal info: {str(e)}")
        return Response(
            {'error': 'Failed to get withdrawal info'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def create_withdrawal(request):
    """
    Создает новый withdrawal запрос
    """
    logger.info(f"[create_withdrawal] Creating withdrawal for user {request.user.id}. Data: {request.data}")
    
    try:
        serializer = CreateWithdrawalSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(f"[create_withdrawal] Validation error: {serializer.errors}")
            return Response(
                {'errors': serializer.errors}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создаем withdrawal
        withdrawal = serializer.save()
        
        # Возвращаем созданный withdrawal
        response_data = WithdrawalSerializer(withdrawal).data
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"[create_withdrawal] Error creating withdrawal: {str(e)}")
        return Response(
            {'error': 'Failed to create withdrawal request'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def cancel_withdrawal(request, withdrawal_id):
    """
    Отменяет withdrawal запрос и возвращает поинты пользователю
    """
    logger.info(f"[cancel_withdrawal] Cancelling withdrawal {withdrawal_id} for user {request.user.id}")
    
    try:
        # Получаем withdrawal
        withdrawal = get_object_or_404(
            Withdrawal, 
            id=withdrawal_id, 
            user=request.user
        )
        
        # Проверяем, можно ли отменить
        if not withdrawal.can_be_cancelled():
            logger.warning(f"[cancel_withdrawal] Cannot cancel withdrawal {withdrawal_id} with status {withdrawal.status}")
            return Response(
                {'error': 'Cannot cancel withdrawal with current status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Возвращаем поинты пользователю
            user_profile = UserProfile.objects.select_for_update().get(user=request.user)
            user_profile.balance += withdrawal.points_sold
            user_profile.save(update_fields=['balance'])
            
            # Обновляем статус withdrawal
            withdrawal.status = 'CANCELLED'
            withdrawal.save(update_fields=['status'])
            
            logger.info(f"""
                [cancel_withdrawal] Cancelled withdrawal {withdrawal_id}:
                Points returned: {withdrawal.points_sold}
                New balance: {user_profile.balance}
            """)
        
        # Возвращаем обновленный withdrawal
        response_data = WithdrawalSerializer(withdrawal).data
        response_data['new_balance'] = user_profile.balance
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Withdrawal.DoesNotExist:
        logger.warning(f"[cancel_withdrawal] Withdrawal {withdrawal_id} not found for user {request.user.id}")
        return Response(
            {'error': 'Withdrawal not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"[cancel_withdrawal] Error cancelling withdrawal: {str(e)}")
        return Response(
            {'error': 'Failed to cancel withdrawal'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def update_withdrawal_addresses(request):
    """
    Обновляет адреса для вывода средств в профиле пользователя
    """
    logger.info(f"[update_withdrawal_addresses] Updating addresses for user {request.user.id}. Data: {request.data}")
    
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        paypal_address = request.data.get('paypal_address')
        usdt_address = request.data.get('usdt_address')
        
        # Валидация PayPal адреса
        if paypal_address is not None:
            if paypal_address and paypal_address.strip():
                from django.core.validators import EmailValidator
                validator = EmailValidator()
                try:
                    validator(paypal_address.strip())
                    user_profile.paypal_address = paypal_address.strip()
                except ValidationError:
                    return Response(
                        {'error': 'Invalid PayPal email address format'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                user_profile.paypal_address = None
        
        # Валидация USDT адреса
        if usdt_address is not None:
            if usdt_address and usdt_address.strip():
                usdt_clean = usdt_address.strip()
                if len(usdt_clean) < 20:
                    return Response(
                        {'error': 'Invalid USDT address format'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                user_profile.usdt_address = usdt_clean
            else:
                user_profile.usdt_address = None
        
        user_profile.save(update_fields=['paypal_address', 'usdt_address'])
        
        logger.info(f"""
            [update_withdrawal_addresses] Updated addresses for user {request.user.id}:
            PayPal: {bool(user_profile.paypal_address)}
            USDT: {bool(user_profile.usdt_address)}
        """)
        
        return Response({
            'message': 'Withdrawal addresses updated successfully',
            'paypal_address': user_profile.paypal_address,
            'usdt_address': user_profile.usdt_address
        }, status=status.HTTP_200_OK)
        
    except UserProfile.DoesNotExist:
        logger.error(f"[update_withdrawal_addresses] UserProfile not found for user {request.user.id}")
        return Response(
            {'error': 'User profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"[update_withdrawal_addresses] Error updating addresses: {str(e)}")
        return Response(
            {'error': 'Failed to update withdrawal addresses'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def task_completion_stats(request):
    """
    Возвращает статистику выполнения заданий пользователя по периодам
    """
    logger.info(f"[task_completion_stats] Getting task completion stats for user {request.user.id}")
    
    try:
        # Получаем параметры запроса
        period = request.GET.get('period', 'week')  # day, week, month, quarter, year, custom
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        logger.info(f"[task_completion_stats] Request params: period={period}, start_date={start_date}, end_date={end_date}")
        
        # Базовый queryset для выполненных заданий пользователя
        user_id = request.user.id
        logger.info(f"[task_completion_stats] Looking for completions for user_id: {user_id}")
        
        # Сначала проверим все записи для пользователя без фильтров
        all_completions_count = TaskCompletion.objects.filter(user=request.user).count()
        completed_completions_count = TaskCompletion.objects.filter(
            user=request.user,
            completed_at__isnull=False
        ).count()
        
        logger.info(f"""
            [task_completion_stats] User {user_id} task completions:
            Total completions: {all_completions_count}
            Completions with completed_at: {completed_completions_count}
        """)
        
        completions = TaskCompletion.objects.filter(
            user=request.user
        ).select_related('task')
        
        # Определяем диапазон дат
        now = timezone.now()
        
        if period == 'custom' and start_date and end_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                
                # Конвертируем в timezone-aware если нужно
                if timezone.is_naive(start_dt):
                    start_dt = timezone.make_aware(start_dt)
                if timezone.is_naive(end_dt):
                    end_dt = timezone.make_aware(end_dt)
                    
            except (ValueError, TypeError) as e:
                logger.error(f"[task_completion_stats] Invalid date format: {str(e)}")
                return Response(
                    {'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif period == 'day':
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif period == 'week':
            # Неделя назад
            start_dt = now - timedelta(days=7)
            end_dt = now
        elif period == 'month':
            # Месяц назад
            start_dt = now - relativedelta(months=1)
            end_dt = now
        elif period == 'quarter':
            # Квартал (3 месяца) назад
            start_dt = now - relativedelta(months=3)
            end_dt = now
        elif period == 'year':
            # Год назад
            start_dt = now - relativedelta(years=1)
            end_dt = now
        else:
            return Response(
                {'error': 'Invalid period. Use: day, week, month, quarter, year, or custom'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Фильтруем по диапазону дат
        completions_before_date_filter = completions.count()
        logger.info(f"[task_completion_stats] Completions before date filter: {completions_before_date_filter}")
        
        completions = completions.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt
        )
        
        completions_after_date_filter = completions.count()
        logger.info(f"""
            [task_completion_stats] Date filtering results:
            Start date: {start_dt}
            End date: {end_dt}
            Completions before filter: {completions_before_date_filter}
            Completions after filter: {completions_after_date_filter}
        """)
        
        # Определяем функцию группировки в зависимости от периода
        # Используем created_at для группировки, так как completed_at может быть пустым
        if period == 'day':
            # Группируем по часам
            trunc_func = TruncHour('created_at')
            date_format = '%Y-%m-%d %H:00'
        elif period in ['week', 'month']:
            # Группируем по дням
            trunc_func = TruncDay('created_at')
            date_format = '%Y-%m-%d'
        elif period in ['quarter', 'year']:
            # Группируем по месяцам
            trunc_func = TruncMonth('created_at')
            date_format = '%Y-%m'
        elif period == 'custom':
            # Для кастомного периода определяем группировку по разности дат
            days_diff = (end_dt - start_dt).days
            if days_diff <= 1:
                trunc_func = TruncHour('created_at')
                date_format = '%Y-%m-%d %H:00'
            elif days_diff <= 31:
                trunc_func = TruncDay('created_at')
                date_format = '%Y-%m-%d'
            else:
                trunc_func = TruncMonth('created_at')
                date_format = '%Y-%m'
        
        # Группируем и агрегируем данные
        # Для каждого completion вычисляем reward в поинтах: (original_price / actions_required) / 2
        # Затем конвертируем в доллары через conversion_rate
        stats = completions.annotate(
            period_date=trunc_func,
            task_reward_points=F('task__original_price') / F('task__actions_required') / 2,
            task_reward_usd=F('task__original_price') / F('task__actions_required') / 2 * Value(0.01)
        ).values('period_date').annotate(
            tasks_completed=Count('id'),
            total_earnings_points=Sum('task_reward_points'),
            total_earnings_usd=Sum('task_reward_usd')
        ).order_by('period_date')
        
        logger.info(f"[task_completion_stats] Aggregation query result count: {stats.count()}")
        if stats.count() > 0:
            logger.info(f"[task_completion_stats] First few aggregated records: {list(stats[:3])}")
        
        # Форматируем результат
        chart_data = []
        for stat in stats:
            if stat['period_date']:
                chart_data.append({
                    'date': stat['period_date'].strftime(date_format),
                    'tasks_completed': stat['tasks_completed'],
                    'total_earnings_points': float(stat['total_earnings_points'] or 0),
                    'total_earnings_usd': float(stat['total_earnings_usd'] or 0)
                })
        
        # Подсчитываем общую статистику за период
        # Используем ту же формулу что и при начислении: (original_price / actions_required) / 2
        # Рассчитываем как в поинтах, так и в долларах
        total_stats = completions.annotate(
            task_reward_points=F('task__original_price') / F('task__actions_required') / 2,
            task_reward_usd=F('task__original_price') / F('task__actions_required') / 2 * Value(0.01)
        ).aggregate(
            total_tasks=Count('id'),
            total_earnings_points=Sum('task_reward_points'),
            total_earnings_usd=Sum('task_reward_usd')
        )
        
        total_earnings_points = float(total_stats['total_earnings_points'] or 0)
        total_earnings_usd = float(total_stats['total_earnings_usd'] or 0)
        
        response_data = {
            'period': period,
            'start_date': start_dt.isoformat(),
            'end_date': end_dt.isoformat(),
            'chart_data': chart_data,
            'summary': {
                'total_tasks_completed': total_stats['total_tasks'] or 0,
                'total_earnings_points': total_earnings_points,
                'total_earnings_usd': total_earnings_usd,
                'average_earnings_per_task_points': total_earnings_points / (total_stats['total_tasks'] or 1) if total_stats['total_tasks'] else 0,
                'average_earnings_per_task_usd': total_earnings_usd / (total_stats['total_tasks'] or 1) if total_stats['total_tasks'] else 0
            }
        }
        
        logger.info(f"""
            [task_completion_stats] Stats for user {request.user.id}:
            Period: {period}
            Total tasks: {total_stats['total_tasks']}
            Total earnings: {total_earnings_points} points (${total_earnings_usd:.2f})
            Chart data points: {len(chart_data)}
        """)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[task_completion_stats] Error getting task completion stats: {str(e)}")
        return Response(
            {'error': 'Failed to get task completion statistics'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def verify_social_profile(request):
    user = request.user
    social_network_code = request.data.get('social_network')
    profile_url = request.data.get('profile_url')

    logger.info(f"[verify_social_profile] Called by user: id={getattr(user, 'id', None)}, username={getattr(user, 'username', None)}, is_authenticated={getattr(user, 'is_authenticated', False)}")
    logger.info(f"[verify_social_profile] social_network_code={social_network_code}, profile_url={profile_url}")

    if not social_network_code or not profile_url:
        logger.error(f"[verify_social_profile] Missing social_network or profile_url. user={getattr(user, 'id', None)}")
        return Response({'error': 'Missing social_network or profile_url'}, status=400)

    # --- Нормализация profile_url ---
    profile_url_normalized = profile_url.strip().lower()
    logger.info(f"[verify_social_profile] Normalized profile_url: '{profile_url_normalized}' (original: '{profile_url}')")

    try:
        social_network = SocialNetwork.objects.get(code=social_network_code)
        # Проверка на фрод: profile_url уже есть у другого пользователя (без учета регистра)
        existing = UserSocialProfile.objects.filter(
            social_network=social_network,
            profile_url__iexact=profile_url_normalized
        ).exclude(user=user).first()
        if existing:
            logger.warning(f"[verify_social_profile] Fraud attempt: profile_url (case-insensitive) already used by user_id={existing.user.id}, username={existing.user.username}, url={existing.profile_url}")
            return Response({'error': 'This social profile is already used by another user.'}, status=400)

        profile, created = UserSocialProfile.objects.get_or_create(
            user=user,
            social_network=social_network,
            defaults={
                'profile_url': profile_url_normalized,
                'username': user.username,  # UID из Firebase
                'verification_status': 'PENDING'
            }
        )
        logger.info(f"[verify_social_profile] UserSocialProfile {'created' if created else 'updated'}: id={profile.id}, user_id={profile.user.id}, username={profile.username}, social_network={social_network.code}")
        if not created:
            # Если уже есть профиль — обновляем ссылку и статус
            logger.info(f"[verify_social_profile] Updating existing profile id={profile.id} for user_id={user.id}")
            profile.profile_url = profile_url_normalized
            profile.username = user.username  # UID из Firebase
            profile.verification_status = 'PENDING'
            profile.save()
            logger.info(f"[verify_social_profile] Profile updated: id={profile.id}, user_id={profile.user.id}, username={profile.username}")

        # Для LinkedIn используем автоматическую верификацию через Apify
        if social_network_code == 'LINKEDIN':
            logger.info(f"[verify_social_profile] LinkedIn profile detected, starting Apify verification for: {profile_url}")
            # Используем оригинальный URL для Apify, так как он чувствителен к регистру
            is_valid, profile_data, validation_result = verify_linkedin_profile_by_url(profile_url.strip())
            
            if not is_valid:
                # Профиль не прошел проверку
                failed_criteria = validation_result.get('failed_criteria', [])
                details = validation_result.get('details', {})
                
                logger.warning(f"[verify_social_profile] LinkedIn profile verification failed. Failed criteria: {failed_criteria}")
                
                # Обновляем статус профиля на REJECTED
                profile.verification_status = 'REJECTED'
                if 'PROFILE_MUST_HAVE_EMOJI_FINGERPRINT' in failed_criteria:
                    profile.rejection_reason = 'NO_EMOJI'
                else:
                    profile.rejection_reason = 'DOES_NOT_MEET_CRITERIA'
                profile.save()
                
                # Формируем детальное сообщение об ошибке
                error_messages = []
                if 'FAILED_TO_FETCH_PROFILE_DATA' in failed_criteria:
                    apify_error = details.get('error', '')
                    if 'free Apify plan' in apify_error:
                        error_messages.append("Apify service is currently unavailable. Please contact support at yes@upvote.club for manual verification.")
                    else:
                        error_messages.append("Failed to fetch profile data from Apify. Please try again later or contact support at yes@upvote.club.")
                if 'MINIMUM_CONNECTIONS_OR_FOLLOWERS' in failed_criteria:
                    error_messages.append(f"Minimum 100 connections or followers required. You have {details.get('total_connections_followers', 0)}.")
                if 'PROFILE_MUST_HAVE_AVATAR' in failed_criteria:
                    error_messages.append("Profile must have an avatar.")
                if 'CLEAR_PROFILE_DESCRIPTION' in failed_criteria:
                    error_messages.append("Profile must have a clear description (who you are, what you do).")
                if 'PROFILE_MUST_HAVE_EMOJI_FINGERPRINT' in failed_criteria:
                    error_messages.append(f"Profile must contain all emoji fingerprint: {', '.join(['🧗‍♂️', '😄', '🤩', '🤖', '😛'])}")
                if 'PROFILE_MUST_HAVE_1_PLACE_OF_WORK' in failed_criteria:
                    error_messages.append("Profile must have at least 1 place of work.")
                
                return Response({
                    'success': False,
                    'error': 'Profile does not meet verification criteria',
                    'failed_criteria': failed_criteria,
                    'details': details,
                    'messages': error_messages
                }, status=400)
            
            # Профиль прошел проверку - автоматически верифицируем
            logger.info(f"[verify_social_profile] LinkedIn profile verification passed. Auto-verifying profile id={profile.id}")
            profile.verification_status = 'VERIFIED'
            profile.is_verified = True
            profile.verification_date = timezone.now()
            
            # Сохраняем дополнительные данные из Apify, если они есть
            if profile_data:
                if profile_data.get('profilePic') or profile_data.get('profilePicHighQuality'):
                    profile.avatar_url = profile_data.get('profilePic') or profile_data.get('profilePicHighQuality')
                if profile_data.get('followers'):
                    profile.followers_count = profile_data.get('followers', 0) or 0
                if profile_data.get('connections'):
                    profile.following_count = profile_data.get('connections', 0) or 0
            
            profile.save()
            logger.info(f"[verify_social_profile] LinkedIn profile verified successfully: id={profile.id}")
            
            return Response({
                'success': True,
                'profile_id': profile.id,
                'message': 'Your LinkedIn profile has been verified successfully!',
                'verified': True
            }, status=200)

        # Отправляем письмо админу (один раз, не в цикле)
        admin_email = getattr(settings, 'ADMIN_EMAIL', 'yes@upvote.club')
        email_service = EmailService()
        admin_link = f"{settings.BACKEND_ADMIN_URL}/admin/api/usersocialprofile/{profile.id}/change/"
        html_content = f"""
        <h2>New profile for verification</h2>
        <p>User: {user.username} (ID: {user.id})</p>
        <p>Social Network: {social_network.name}</p>
        <p>Profile URL: <a href='{profile_url_normalized}'>{profile_url_normalized}</a></p>
        <p><a href='{admin_link}'>Moderate in admin</a></p>
        """
        email_service.send_email(
            to_email=admin_email,
            subject='New Social Profile Pending Verification',
            html_content=html_content
        )
        logger.info(f"[verify_social_profile] Notification email sent to admin: {admin_email}")

        # Отправляем уведомление в Telegram с кнопками
        try:
            TELEGRAM_BOT_TOKEN = '8045516781:AAFdnzHGd78LIeCyW5ygkO8yVk1jY3p5J1Y'
            TELEGRAM_CHAT_ID = '133814301'
            telegram_message = (
                f"🔔 New profile for moderation!\n"
                f"User: {user.username} (ID: {user.id})\n"
                f"Social Network: {social_network.name}\n"
                f"Profile URL: {profile_url_normalized}\n"
                f"Admin link: {admin_link}"
            )
            
            # Создаем inline клавиатуру с кнопками
            keyboard = {
                'inline_keyboard': [
                    [
                        {
                            'text': '✅ Verify',
                            'callback_data': f'moderate_profile_{profile.id}_verify'
                        }
                    ],
                    [
                        {
                            'text': '❌ Reject - No Emoji',
                            'callback_data': f'moderate_profile_{profile.id}_reject_no_emoji'
                        },
                        {
                            'text': '❌ Reject - Does not meet criteria',
                            'callback_data': f'moderate_profile_{profile.id}_reject_criteria'
                        }
                    ]
                ]
            }
            
            telegram_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
            telegram_payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': telegram_message,
                'parse_mode': 'HTML',
                'reply_markup': json.dumps(keyboard)
            }
            response = requests.post(telegram_url, data=telegram_payload, timeout=10)
            logger.info(f"[verify_social_profile] Telegram notify response: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"[verify_social_profile] Exception while sending Telegram notify: {str(e)}")

        return Response({
            'success': True,
            'profile_id': profile.id,
            'message': 'Your profile has been submitted for moderation. You will receive a response by email from a moderator.'
        }, status=201)
    except SocialNetwork.DoesNotExist:
        logger.error(f"[verify_social_profile] Social network not found: {social_network_code}")
        return Response({'error': 'Social network not found'}, status=404)
    except Exception as e:
        logger.error(f"[verify_social_profile] Exception: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def delete_task(request, task_id):
    """
    Переводит задачу в статус 'DELETED', возвращает пользователю поинты за невыполненные действия и бесплатное задание.
    """
    logger.info(f"[delete_task] Request to delete task {task_id} by user {request.user.id}")
    try:
        with transaction.atomic():
            task = Task.objects.select_for_update().get(id=task_id, creator=request.user)
            logger.info(f"[delete_task] Task found: id={task.id}, status={task.status}, actions_required={task.actions_required}, actions_completed={task.actions_completed}")

            if task.status == 'DELETED':
                logger.warning(f"[delete_task] Task {task_id} is already deleted.")
                return Response({'error': 'Task is already deleted.'}, status=status.HTTP_400_BAD_REQUEST)
            if task.status == 'COMPLETED':
                logger.warning(f"[delete_task] Task {task_id} is already completed and cannot be deleted.")
                return Response({'error': 'Task is already completed and cannot be deleted.'}, status=status.HTTP_400_BAD_REQUEST)

            user_profile = request.user.userprofile
            logger.info(f"[delete_task] User profile found: id={user_profile.id}, balance={user_profile.balance}, available_tasks={user_profile.available_tasks}")

            # Считаем невыполненные действия
            remaining_actions = task.actions_required - task.actions_completed
            logger.info(f"[delete_task] Remaining actions: {remaining_actions}")
            if remaining_actions > 0:
                # Считаем возврат поинтов с учетом скидки пользователя
                discount_rate = user_profile.get_discount_rate()
                logger.info(f"[delete_task] User discount rate: {discount_rate}% (status: {user_profile.status})")
                original_cost = task.original_price
                discounted_cost = int(original_cost - (original_cost * discount_rate / 100))
                # Сколько реально потрачено на одно действие
                cost_per_action = discounted_cost / task.actions_required
                refund_points = int(cost_per_action * remaining_actions)
                logger.info(f"[delete_task] Calculated refund points with discount: {refund_points}")
                user_profile.balance += refund_points
                logger.info(f"[delete_task] New user balance after refund: {user_profile.balance}")
            else:
                refund_points = 0
                logger.info(f"[delete_task] No points to refund.")

            # Возвращаем бесплатное задание
            user_profile.available_tasks += 1
            logger.info(f"[delete_task] New available_tasks after refund: {user_profile.available_tasks}")

            # Переводим задачу в статус DELETED
            task.status = 'DELETED'
            task.save(update_fields=['status'])
            user_profile.save(update_fields=['balance', 'available_tasks'])
            logger.info(f"[delete_task] Task {task_id} marked as DELETED. User profile updated.")

        return Response({
            'success': True,
            'refunded_points': refund_points,
            'new_balance': user_profile.balance,
            'new_available_tasks': user_profile.available_tasks,
            'task_id': task.id,
            'task_status': task.status
        }, status=status.HTTP_200_OK)
    except Task.DoesNotExist:
        logger.error(f"[delete_task] Task {task_id} not found or not owned by user {request.user.id}")
        return Response({'error': 'Task not found or not owned by user.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"[delete_task] Error: {str(e)}", exc_info=True)
        return Response({'error': 'Failed to delete task', 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def points_available_for_purchase(request):
    """
    Возвращает количество поинтов, доступных для покупки в системе.
    Это разница между всеми проданными поинтами (withdrawal COMPLETED) и всеми купленными поинтами (PaymentTransaction ONE_TIME COMPLETED).
    Дельта не может быть отрицательной.
    Доступно всем (для отображения на фронте).
    """
    logger.info('[points_available_for_purchase] Запрос на получение доступных поинтов для покупки')
    try:
        # Сумма проданных поинтов (COMPLETED withdrawals)
        total_points_sold = Withdrawal.objects.filter(status='COMPLETED').aggregate(total=Sum('points_sold'))['total'] or 0
        logger.info(f'[points_available_for_purchase] Всего продано поинтов (withdrawal COMPLETED): {total_points_sold}')

        # Сумма купленных поинтов (COMPLETED ONE_TIME purchases)
        total_points_bought = PaymentTransaction.objects.filter(
            status='COMPLETED',
            payment_type='ONE_TIME'
        ).aggregate(total=Sum('points'))['total'] or 0
        logger.info(f'[points_available_for_purchase] Всего куплено поинтов (payment COMPLETED ONE_TIME): {total_points_bought}')

        # Дельта
        available_points = total_points_sold - total_points_bought
        if available_points < 0:
            logger.warning(f'[points_available_for_purchase] Дельта отрицательная! Ставим 0. (delta={available_points})')
            available_points = 0
        else:
            logger.info(f'[points_available_for_purchase] Доступно для покупки: {available_points}')

        return Response({
            'points_available_for_purchase': available_points,
            'total_points_sold': total_points_sold,
            'total_points_bought': total_points_bought
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f'[points_available_for_purchase] Ошибка: {str(e)}', exc_info=True)
        return Response({'error': 'Failed to get available points', 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_verified_accounts_count(request):
    """
    Возвращает количество верифицированных аккаунтов по каждой социальной сети
    """
    logger.info('[get_verified_accounts_count] Запрос количества верифицированных аккаунтов')
    try:
        # Получаем количество верифицированных аккаунтов по каждой соц.сети
        verified_counts = UserSocialProfile.objects.filter(
            verification_status='VERIFIED'
        ).values(
            'social_network__code',
            'social_network__name'
        ).annotate(
            count=Count('id')
        ).order_by('social_network__code')
        
        # Формируем ответ в виде словаря
        result = {}
        for item in verified_counts:
            network_code = item['social_network__code']
            network_name = item['social_network__name']
            count = item['count']
            result[network_code] = {
                'name': network_name,
                'count': count
            }
        
        # Добавляем соц.сети, у которых нет верифицированных аккаунтов (count = 0)
        all_networks = SocialNetwork.objects.filter(is_active=True)
        for network in all_networks:
            if network.code not in result:
                result[network.code] = {
                    'name': network.name,
                    'count': 0
                }
        
        logger.info(f'[get_verified_accounts_count] Найдено верифицированных аккаунтов: {result}')
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'[get_verified_accounts_count] Ошибка: {str(e)}', exc_info=True)
        return Response(
            {'error': 'Failed to get verified accounts count', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_platform_stats(request):
    """
    Возвращает статистику по соцсетям и действиям для лендингов:
    1. Всего завершённых действий на платформе + за вчера (по всем соцсетям и по каждой отдельно)
    2. Всего каждого действия на платформе + за вчера (по всем соцсетям и по каждой отдельно, не показывать если 0)
    3. Охват = количество действий * 100
    """
    logger.info('[get_platform_stats] Запрос статистики платформы')
    try:
        from django.db.models import Q
        from collections import defaultdict
        now = timezone.now()
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)

        # Получаем все соцсети
        social_networks = SocialNetwork.objects.all()
        logger.info(f'[get_platform_stats] Найдено соцсетей: {social_networks.count()}')

        # Получаем все действия (action)
        all_action_types = list(TaskCompletion.objects.values_list('action', flat=True).distinct())
        logger.info(f'[get_platform_stats] Найдено типов действий: {all_action_types}')

        # --- 1. Всего завершённых действий на платформе ---
        total_actions = TaskCompletion.objects.count()
        total_actions_yesterday = TaskCompletion.objects.filter(
            created_at__gte=yesterday_start, created_at__lt=yesterday_end
        ).count()
        logger.info(f'[get_platform_stats] Всего действий: {total_actions}, за вчера: {total_actions_yesterday}')

        # --- 2. По каждой соцсети и по каждому действию ---
        # Формируем структуру: {network_code: {action: {total, yesterday}}}
        stats_by_network = {}
        for network in social_networks:
            network_code = network.code
            # Всего действий по соцсети
            network_total = TaskCompletion.objects.filter(task__social_network=network).count()
            network_yesterday = TaskCompletion.objects.filter(
                task__social_network=network,
                created_at__gte=yesterday_start, created_at__lt=yesterday_end
            ).count()
            logger.info(f'[get_platform_stats] Соцсеть {network_code}: всего={network_total}, вчера={network_yesterday}')
            # По каждому действию
            actions_stats = []
            for action in all_action_types:
                action_total = TaskCompletion.objects.filter(
                    task__social_network=network, action=action
                ).count()
                action_yesterday = TaskCompletion.objects.filter(
                    task__social_network=network, action=action,
                    created_at__gte=yesterday_start, created_at__lt=yesterday_end
                ).count()
                if action_total > 0:
                    logger.info(f'[get_platform_stats]   Действие {action}: всего={action_total}, вчера={action_yesterday}')
                    actions_stats.append({
                        'action': action,
                        'total': action_total,
                        'yesterday': action_yesterday,
                        'reach': action_total * 100,
                        'reach_yesterday': action_yesterday * 100
                    })
            stats_by_network[network_code] = {
                'network_name': network.name,
                'total': network_total,
                'yesterday': network_yesterday,
                'reach': network_total * 100,
                'reach_yesterday': network_yesterday * 100,
                'actions': actions_stats
            }

        # --- 3. По каждому действию на платформе (без соцсети) ---
        actions_platform_stats = []
        for action in all_action_types:
            action_total = TaskCompletion.objects.filter(action=action).count()
            action_yesterday = TaskCompletion.objects.filter(
                action=action,
                created_at__gte=yesterday_start, created_at__lt=yesterday_end
            ).count()
            if action_total > 0:
                logger.info(f'[get_platform_stats] Платформа: действие {action}: всего={action_total}, вчера={action_yesterday}')
                actions_platform_stats.append({
                    'action': action,
                    'total': action_total,
                    'yesterday': action_yesterday,
                    'reach': action_total * 100,
                    'reach_yesterday': action_yesterday * 100
                })

        # --- Формируем финальный ответ ---
        response = {
            'total_actions': total_actions,
            'total_actions_yesterday': total_actions_yesterday,
            'reach': total_actions * 100,
            'reach_yesterday': total_actions_yesterday * 100,
            'by_network': stats_by_network,
            'by_action': actions_platform_stats
        }
        logger.info(f'[get_platform_stats] Финальный ответ: {response}')
        return Response(response, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f'[get_platform_stats] Ошибка: {str(e)}', exc_info=True)
        return Response({'error': 'Failed to get platform stats', 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_exempt
def telegram_webhook(request):
    """Обработка webhook от Telegram для кнопок модерации профилей"""
    try:
        data = json.loads(request.body)
        callback_query = data.get('callback_query')
        
        if not callback_query:
            return Response({'status': 'ok'})
        
        callback_query_id = callback_query.get('id')
        callback_data = callback_query.get('data', '')
        message = callback_query.get('message', {})
        message_id = message.get('message_id')
        chat_id = message.get('chat', {}).get('id')
        
        # Функция для ответа на callback_query
        def answer_callback_query(text=''):
            """Отвечает на callback_query, чтобы Telegram не отправлял повторные запросы"""
            if not callback_query_id:
                return
            try:
                TELEGRAM_BOT_TOKEN = '8045516781:AAFdnzHGd78LIeCyW5ygkO8yVk1jY3p5J1Y'
                answer_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery'
                requests.post(answer_url, json={'callback_query_id': callback_query_id, 'text': text}, timeout=5)
            except Exception:
                pass
        
        # Парсим callback_data: "moderate_profile_{profile_id}_{action}"
        if callback_data.startswith('moderate_profile_'):
            parts = callback_data.split('_')
            if len(parts) >= 4:
                profile_id = parts[2]
                action = '_'.join(parts[3:])  # На случай если action содержит подчеркивания
                
                try:
                    profile = UserSocialProfile.objects.get(id=profile_id)
                    
                    if action == 'verify':
                        # Проверяем, что профиль еще не верифицирован (защита от дублирования)
                        if profile.verification_status == 'VERIFIED':
                            answer_callback_query('Profile already verified')
                            return Response({'status': 'ok'})
                        
                        # Верифицируем профиль
                        profile.verification_status = 'VERIFIED'
                        profile.is_verified = True
                        profile.verification_date = timezone.now()
                        profile.rejection_reason = None
                        profile.save()
                        
                        # Отправляем email пользователю
                        try:
                            user_email = profile.user.email
                            if not user_email:
                                from firebase_admin import auth
                                firebase_user = auth.get_user(profile.user.username)
                                user_email = firebase_user.email
                            
                            if user_email:
                                email_service = EmailService()
                                plain_text = (
                                    'Congratulations! Your profile has been approved!\n'
                                    'PLEASE REMOVE EMOJI FROM YOUR BIO: 🧗‍♂️😄🤩🤖😛 !IMPORTANT!'
                                )
                                email_service.send_email(
                                    to_email=user_email,
                                    subject='Your profile has been approved!',
                                    html_content=plain_text
                                )
                        except Exception:
                            pass
                        
                        # Отвечаем на callback_query
                        answer_callback_query('Profile verified')
                        
                        # Отправляем ответ в Telegram
                        send_telegram_message(chat_id, f"✅ Profile {profile.username} has been verified!", message_id)
                        
                    elif action == 'reject_no_emoji':
                        # Проверяем, что профиль еще не отклонен с этой причиной (защита от дублирования)
                        if profile.verification_status == 'REJECTED' and profile.rejection_reason == 'NO_EMOJI':
                            answer_callback_query('Profile already rejected')
                            return Response({'status': 'ok'})
                        
                        # Отклоняем профиль - нет эмоджи
                        profile.verification_status = 'REJECTED'
                        profile.is_verified = False
                        profile.verification_date = timezone.now()
                        profile.rejection_reason = 'NO_EMOJI'
                        profile.save()
                        
                        # Отправляем email пользователю
                        try:
                            user_email = profile.user.email
                            if not user_email:
                                from firebase_admin import auth
                                firebase_user = auth.get_user(profile.user.username)
                                user_email = firebase_user.email
                            
                            if user_email:
                                email_service = EmailService()
                                html_content = (
                                    '<p>Your social profile was <b>soft-rejected</b> because we could not find a finger print emoji 🧗‍♂️😄🤩🤖😛 on your BIO at profile page.</p>'
                                    '<p>Please add emoji finger print 🧗‍♂️😄🤩🤖😛 to your profile BIO or display name and submit it again</p>'
                                    '<br>'
                                    '<p>After verification, you can remove the EMOJI finger print from your BIO</p>'
                                )
                                email_service.send_email(
                                    to_email=user_email,
                                    subject=f'Profile was soft-rejected - No Emoji 🧗‍♂️😄🤩🤖😛 found in your BIO',
                                    html_content=html_content
                                )
                        except Exception:
                            pass
                        
                        # Отвечаем на callback_query
                        answer_callback_query('Profile rejected')
                        
                        # Отправляем ответ в Telegram
                        send_telegram_message(chat_id, f"❌ Profile {profile.username} rejected - No Emoji", message_id)
                        
                    elif action == 'reject_criteria':
                        # Проверяем, что профиль еще не отклонен с этой причиной (защита от дублирования)
                        if profile.verification_status == 'REJECTED' and profile.rejection_reason == 'DOES_NOT_MEET_CRITERIA':
                            answer_callback_query('Profile already rejected')
                            return Response({'status': 'ok'})
                        
                        # Отклоняем профиль - не соответствует критериям
                        profile.verification_status = 'REJECTED'
                        profile.is_verified = False
                        profile.verification_date = timezone.now()
                        profile.rejection_reason = 'DOES_NOT_MEET_CRITERIA'
                        profile.save()
                        
                        # Отправляем email пользователю
                        try:
                            user_email = profile.user.email
                            if not user_email:
                                from firebase_admin import auth
                                firebase_user = auth.get_user(profile.user.username)
                                user_email = firebase_user.email
                            
                            if user_email:
                                email_service = EmailService()
                                html_content = (
                                    '<p>Your social profile was <b>rejected</b> because it does not meet our criteria. For detailed moderation criteria for each social network, please check our <a href="https://upvote.club/dashboard/moderation-criteria">moderation criteria</a></p>'
                                )
                                email_service.send_email(
                                    to_email=user_email,
                                    subject='Your social profile was rejected - Does not meet criteria',
                                    html_content=html_content
                                )
                        except Exception:
                            pass
                        
                        # Отвечаем на callback_query
                        answer_callback_query('Profile rejected')
                        
                        # Отправляем ответ в Telegram
                        send_telegram_message(chat_id, f"❌ Profile {profile.username} rejected - Does not meet criteria", message_id)
                    
                except UserSocialProfile.DoesNotExist:
                    answer_callback_query('Profile not found')
                    send_telegram_message(chat_id, "❌ Profile not found", message_id)
                except Exception as e:
                    answer_callback_query('Error occurred')
                    send_telegram_message(chat_id, f"❌ Error: {str(e)}", message_id)
        
        return Response({'status': 'ok'})
        
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


def send_telegram_message(chat_id, text, reply_to_message_id=None):
    """Отправка сообщения в Telegram"""
    try:
        TELEGRAM_BOT_TOKEN = '8045516781:AAFdnzHGd78LIeCyW5ygkO8yVk1jY3p5J1Y'
        telegram_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        
        response = requests.post(telegram_url, data=payload, timeout=10)
        logger.info(f"[Telegram] Send message response: {response.status_code} {response.text}")
        return response
    except Exception as e:
        logger.error(f"[Telegram] Error sending message: {str(e)}")
        return None


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def save_referrer_tracking(request):
    """Сохраняет данные referrer tracking для пользователя"""
    try:
        logger.info(f"[save_referrer_tracking] Attempt by user_id={getattr(request.user, 'id', None)} data_keys={list(request.data.keys())}")
        serializer = ReferrerTrackingSerializer(data=request.data)
        if serializer.is_valid():
            user_profile = request.user.userprofile
            
            # Сохраняем данные только если они еще не были сохранены
            if not user_profile.referrer_url and not user_profile.landing_url:
                user_profile.referrer_url = serializer.validated_data.get('referrer', '')
                user_profile.landing_url = serializer.validated_data['landing_url']
                user_profile.referrer_timestamp = serializer.validated_data['timestamp']
                user_profile.referrer_user_agent = serializer.validated_data['user_agent']
                user_profile.device_type = serializer.validated_data.get('device_type') or user_profile.device_type
                user_profile.os_name = serializer.validated_data.get('os_name') or user_profile.os_name
                user_profile.os_version = serializer.validated_data.get('os_version') or user_profile.os_version
                user_profile.save()
                logger.info(f"[save_referrer_tracking] Saved for user_id={request.user.id} device={user_profile.device_type} os={user_profile.os_name} {user_profile.os_version}")
                
                return Response({
                    'success': True,
                    'message': 'Referrer tracking data saved successfully'
                }, status=200)
            else:
                logger.info(f"[save_referrer_tracking] Skip save (already exists) for user_id={request.user.id}")
                return Response({
                    'success': True,
                    'message': 'Referrer tracking data already exists'
                }, status=200)
        else:
            logger.warning(f"[save_referrer_tracking] Validation failed for user_id={getattr(request.user, 'id', None)} errors={serializer.errors}")
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=400)
    except Exception as e:
        logger.error(f"[save_referrer_tracking] Exception for user_id={getattr(request.user, 'id', None)} error={str(e)}")
        return Response({
            'success': False,
            'message': f'Error saving referrer tracking data: {str(e)}'
        }, status=500)

@api_view(['GET', 'POST', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def onboarding_progress(request):
    user = request.user
    try:
        onboarding, created = OnboardingProgress.objects.get_or_create(user=user)
    except OnboardingProgress.MultipleObjectsReturned:
        onboarding = OnboardingProgress.objects.filter(user=user).first()
        created = False

    if request.method == 'GET':
        serializer = OnboardingProgressSerializer(onboarding)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = OnboardingProgressSerializer(onboarding, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'PATCH':
        serializer = OnboardingProgressSerializer(onboarding, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([JWTAuthentication])
def subscribe_black_friday(request):
    """
    Подписка пользователя на уведомления о Black Friday deal
    """
    logger.info(f"[subscribe_black_friday] User {request.user.id} subscribing to Black Friday notifications")
    
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        # Проверяем, не подписан ли уже пользователь
        was_subscribed = user_profile.black_friday_subscribed
        
        user_profile.black_friday_subscribed = True
        user_profile.save(update_fields=['black_friday_subscribed'])
        
        logger.info(f"[subscribe_black_friday] User {request.user.id} successfully subscribed to Black Friday notifications")
        
        # Отправляем письмо только если пользователь еще не был подписан
        if not was_subscribed:
            try:
                # Получаем email из Firebase по uid (который хранится в username)
                firebase_user = auth.get_user(request.user.username)
                user_email = firebase_user.email
                
                if user_email:
                    email_service = EmailService()
                    
                    html_content = (
                        "<p>You received this discount earlier than others because you subscribed to the Black Friday Deal notification.</p>"
                        "<p>😎🚨 <a href='https://upvote.club/dashboard/subscribe?blackfriday=true&notrial=1' target='_blank'>MATE Plan: Only $219 (down from $439)</a> – includes 15,000 points and unlimited tasks creation.</p>"
                        "<p>🤜🤛 <a href='https://upvote.club/dashboard/subscribe?blackfriday=true&notrial=1' target='_blank'>Buddy Plan: Only $74 (down from $149)</a> – includes 5,000 points and unlimited tasks.</p>"
                        "<p>Locked-in pricing: Your subscription price is guaranteed for the entire year.</p>"
                    )
                    
                    success = email_service.send_email(
                        to_email=user_email,
                        subject='🚨🦩🎁 Early Bird Black Friday Deal 50% Discount on All Annual Plans in your in your box',
                        html_content=html_content
                    )
                    
                    if success:
                        logger.info(f"[subscribe_black_friday] Successfully sent Black Friday subscription email to {user_email}")
                    else:
                        logger.warning(f"[subscribe_black_friday] Failed to send Black Friday subscription email to {user_email}")
                else:
                    logger.error(f"[subscribe_black_friday] No email found in Firebase for user {request.user.username}")
                    
            except Exception as e:
                logger.error(f"[subscribe_black_friday] Error sending Black Friday subscription email: {str(e)}")
        
        return Response({
            'success': True,
            'message': 'Successfully subscribed to Black Friday deal notifications',
            'black_friday_subscribed': user_profile.black_friday_subscribed
        }, status=status.HTTP_200_OK)
        
    except UserProfile.DoesNotExist:
        logger.error(f"[subscribe_black_friday] UserProfile not found for user {request.user.id}")
        return Response(
            {'error': 'User profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"[subscribe_black_friday] Error subscribing to Black Friday: {str(e)}")
        return Response(
            {'error': 'Failed to subscribe to Black Friday notifications'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Можно фильтровать по пользователю, если нужно:
        # return Review.objects.filter(user=self.request.user)
        return super().get_queryset()

class BuyLandingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с buy лендингами.
    Поддерживает получение всех лендингов и получение по slug.
    """
    queryset = BuyLanding.objects.all().select_related('social_network', 'action').order_by('-created_at')
    serializer_class = BuyLandingSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    @action(detail=False, methods=['get'])
    def all(self, request):
        """
        Возвращает все buy лендинги с полным контентом
        """
        landings = self.get_queryset()
        serializer = self.get_serializer(landings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)