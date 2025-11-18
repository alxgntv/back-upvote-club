from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Avg, Count, F, Q, Sum, Exists, OuterRef
from django.utils import timezone
from datetime import timedelta, datetime
from .models import Task, TaskCompletion, UserProfile
import logging
import csv
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from django.utils.decorators import method_decorator
from django.views import View
from django.core.paginator import Paginator
from .forms import UserFilterForm
from .utils.email_utils import get_firebase_email

logger = logging.getLogger(__name__)

@staff_member_required
def business_metrics(request):
    try:
        # Получаем завершенные задания
        completed_tasks = Task.objects.filter(
            Q(status='COMPLETED') & 
            Q(completed_at__isnull=False) & 
            Q(completion_duration__isnull=False)
        )
        
        # Общая статистика
        ttv_stats = completed_tasks.aggregate(
            avg_completion_time=Avg('completion_duration'),
            total_completed=Count('id')
        )
        
        # Статистика по периодам
        now = timezone.now()
        periods = {
            'last_24h': now - timedelta(hours=24),
            'last_week': now - timedelta(days=7),
            'last_month': now - timedelta(days=30),
        }
        
        period_stats = {}
        for period_name, start_date in periods.items():
            stats = completed_tasks.filter(
                completed_at__gte=start_date
            ).aggregate(
                avg_completion_time=Avg('completion_duration'),
                total_completed=Count('id')
            )
            period_stats[period_name] = stats

        # Статистика по типам заданий
        task_type_stats = completed_tasks.values(
            'type'
        ).annotate(
            avg_completion_time=Avg('completion_duration'),
            total_tasks=Count('id'),
            avg_price=Avg('price'),
            total_actions=Sum('actions_required')
        ).order_by('type')

        # Добавляем статистику автоматических действий
        auto_stats = TaskCompletion.objects.filter(
            is_auto=True,
            completed_at__isnull=False
        ).aggregate(
            total_auto_actions=Count('id'),
            auto_actions_last_24h=Count(
                'id',
                filter=Q(completed_at__gte=now - timedelta(hours=24))
            )
        )

        logger.info(f"""Calculated business metrics:
            Overall TTV: {ttv_stats['avg_completion_time']}
            Total completed tasks: {ttv_stats['total_completed']}
            Period stats: {period_stats}
            Task type stats: {task_type_stats}
            Auto actions: {auto_stats}
        """)

        context = {
            'title': 'Business Metrics',
            'ttv_stats': ttv_stats,
            'period_stats': period_stats,
            'task_type_stats': task_type_stats,
            'auto_stats': auto_stats,
        }
        
        return render(request, 'admin/business_metrics.html', context)
        
    except Exception as e:
        logger.error(f"Error calculating business metrics: {str(e)}")
        context = {
            'title': 'Business Metrics',
            'error': str(e)
        }
        return render(request, 'admin/business_metrics.html', context)

@method_decorator(staff_member_required, name='dispatch')
class UserFilterView(View):
    """View для фильтрации пользователей и экспорта в CSV"""
    
    template_name = 'admin/user_filter.html'
    
    def get(self, request):
        """Отображение формы фильтрации"""
        form = UserFilterForm()
        return render(request, self.template_name, {
            'form': form,
            'title': 'Фильтрация пользователей',
            'results': None,
            'stats': None
        })
    
    def post(self, request):
        """Обработка формы и отображение результатов"""
        form = UserFilterForm(request.POST)
        results = []
        stats = {}
        
        if form.is_valid():
            logger.info(f"User filter request from {request.user.username}: {form.cleaned_data}")
            
            # Получаем базовый queryset
            queryset = self.build_queryset(form.cleaned_data)
            
            # Проверяем экспорт в CSV
            if 'export_csv' in request.POST:
                return self.export_csv(queryset, form.cleaned_data)
            
            # Получаем статистику
            stats = self.get_stats(queryset)
            
            # Пагинация
            limit = form.cleaned_data.get('limit_results', 1000)
            paginator = Paginator(queryset, min(limit, 100))  # Не больше 100 за раз
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            # Преобразуем в список для отображения
            results = self.prepare_results(page_obj, form.cleaned_data.get('include_firebase_email', False))
            
            logger.info(f"Filter results: {len(results)} users found")
        return render(request, self.template_name, {
            'form': form,
            'results': results,
            'stats': stats,
            'title': 'Фильтрация пользователей'
        })
    
    def build_queryset(self, filters):
        """Строит QuerySet на основе фильтров"""
        logger.info(f"Building queryset with filters: {filters}")
        
        # Начинаем с базового queryset
        queryset = User.objects.select_related('userprofile')
        initial_count = queryset.count()
        logger.info(f"Initial queryset count: {initial_count}")
        
        # Применяем фильтры по User
        if filters.get('username_contains'):
            queryset = queryset.filter(username__icontains=filters['username_contains'])
        
        if filters.get('date_joined_from'):
            queryset = queryset.filter(date_joined__gte=filters['date_joined_from'])
        
        if filters.get('date_joined_to'):
            queryset = queryset.filter(date_joined__lte=filters['date_joined_to'])
        
        # Применяем фильтры по UserProfile
        profile_filters = Q()
        
        if filters.get('status'):
            profile_filters &= Q(userprofile__status__in=filters['status'])
        
        if filters.get('twitter_verification_status'):
            profile_filters &= Q(userprofile__twitter_verification_status__in=filters['twitter_verification_status'])
        
        # Фильтры по стране
        if filters.get('has_country_code') == 'yes':
            profile_filters &= Q(userprofile__country_code__isnull=False) & ~Q(userprofile__country_code='')
        elif filters.get('has_country_code') == 'no':
            profile_filters &= Q(userprofile__country_code__isnull=True) | Q(userprofile__country_code='')
        
        if filters.get('has_chosen_country') == 'yes':
            profile_filters &= Q(userprofile__chosen_country__isnull=False) & ~Q(userprofile__chosen_country='')
        elif filters.get('has_chosen_country') == 'no':
            profile_filters &= Q(userprofile__chosen_country__isnull=True) | Q(userprofile__chosen_country='')
        
        # Фильтры по Twitter
        if filters.get('has_twitter_account') == 'yes':
            profile_filters &= Q(userprofile__twitter_account__isnull=False) & ~Q(userprofile__twitter_account='')
        elif filters.get('has_twitter_account') == 'no':
            profile_filters &= Q(userprofile__twitter_account__isnull=True) | Q(userprofile__twitter_account='')
        
        if filters.get('twitter_account_contains'):
            profile_filters &= Q(userprofile__twitter_account__icontains=filters['twitter_account_contains'])
        
        # Фильтры по балансу
        if filters.get('balance_min') is not None:
            profile_filters &= Q(userprofile__balance__gte=filters['balance_min'])
        
        if filters.get('balance_max') is not None:
            profile_filters &= Q(userprofile__balance__lte=filters['balance_max'])
        
        # Фильтры по выполненным заданиям
        if filters.get('completed_tasks_min') is not None:
            profile_filters &= Q(userprofile__completed_tasks_count__gte=filters['completed_tasks_min'])
        
        if filters.get('completed_tasks_max') is not None:
            profile_filters &= Q(userprofile__completed_tasks_count__lte=filters['completed_tasks_max'])
        
        # Фильтры по доступным заданиям
        if filters.get('available_tasks_min') is not None:
            profile_filters &= Q(userprofile__available_tasks__gte=filters['available_tasks_min'])
        
        if filters.get('available_tasks_max') is not None:
            profile_filters &= Q(userprofile__available_tasks__lte=filters['available_tasks_max'])
        
        # Фильтр по наличию выполненных заданий
        if filters.get('has_completed_tasks') == 'yes':
            queryset = queryset.filter(Exists(TaskCompletion.objects.filter(user=OuterRef('pk'))))
        elif filters.get('has_completed_tasks') == 'no':
            queryset = queryset.exclude(Exists(TaskCompletion.objects.filter(user=OuterRef('pk'))))
        
        # Фильтры по инвайт коду
        if filters.get('has_invite_code') == 'yes':
            profile_filters &= Q(userprofile__used_invite_code__isnull=False) & ~Q(userprofile__used_invite_code='')
        elif filters.get('has_invite_code') == 'no':
            profile_filters &= Q(userprofile__used_invite_code__isnull=True) | Q(userprofile__used_invite_code='')
        
        # Фильтр по пробному периоду
        if filters.get('has_trial') == 'yes':
            profile_filters &= Q(userprofile__trial_start_date__isnull=False)
        elif filters.get('has_trial') == 'no':
            profile_filters &= Q(userprofile__trial_start_date__isnull=True)
        
        # Остальные булевые фильтры
        bool_filters = {
            'is_ambassador': 'userprofile__is_ambassador',
            'is_affiliate_partner': 'userprofile__is_affiliate_partner',
            'chrome_extension_status': 'userprofile__chrome_extension_status'
        }
        
        for filter_name, field_name in bool_filters.items():
            if filters.get(filter_name) == 'yes':
                profile_filters &= Q(**{field_name: True})
            elif filters.get(filter_name) == 'no':
                profile_filters &= Q(**{field_name: False})
        
        # Фильтры по адресам
        if filters.get('has_paypal_address') == 'yes':
            profile_filters &= Q(userprofile__paypal_address__isnull=False) & ~Q(userprofile__paypal_address='')
        elif filters.get('has_paypal_address') == 'no':
            profile_filters &= Q(userprofile__paypal_address__isnull=True) | Q(userprofile__paypal_address='')
        
        if filters.get('has_usdt_address') == 'yes':
            profile_filters &= Q(userprofile__usdt_address__isnull=False) & ~Q(userprofile__usdt_address='')
        elif filters.get('has_usdt_address') == 'no':
            profile_filters &= Q(userprofile__usdt_address__isnull=True) | Q(userprofile__usdt_address='')
        
        # Применяем все фильтры профиля
        if profile_filters:
            before_profile_count = queryset.count()
            queryset = queryset.filter(profile_filters)
            after_profile_count = queryset.count()
            logger.info(f"Profile filters applied: {before_profile_count} -> {after_profile_count} users")
        
        final_count = queryset.count()
        distinct_count = queryset.distinct().count()
        logger.info(f"Queryset built: {final_count} users, after distinct: {distinct_count}")
        
        # Если результатов мало, выведем несколько примеров для отладки
        if distinct_count <= 5:
            sample_users = list(queryset.distinct()[:5])
            for user in sample_users:
                logger.info(f"Sample user: ID={user.id}, username={user.username}, has_profile={hasattr(user, 'userprofile')}")
        
        return queryset.distinct()
    
    def get_stats(self, queryset):
        """Получает статистику по отфильтрованным пользователям"""
        logger.info("Calculating statistics")
        
        try:
            total_users = queryset.count()
            
            if total_users == 0:
                return {'total_users': 0}
            
            # Агрегированная статистика
            profile_stats = queryset.aggregate(
                total_balance=Count('userprofile__balance'),
                avg_balance=Count('userprofile__balance'),  # Временно, нужно использовать Avg
                total_completed_tasks=Count('userprofile__completed_tasks_count'),
                avg_completed_tasks=Count('userprofile__completed_tasks_count')  # Временно
            )
            
            # Статистика по статусам
            status_stats = {}
            for status_choice in UserProfile._meta.get_field('status').choices:
                status_code = status_choice[0]
                status_count = queryset.filter(userprofile__status=status_code).count()
                status_stats[status_choice[1]] = status_count
            
            stats = {
                'total_users': total_users,
                'status_distribution': status_stats,
                **profile_stats
            }
            
            logger.info(f"Statistics calculated: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating stats: {e}")
            return {'error': str(e)}
    
    def prepare_results(self, page_obj, include_firebase_email=False):
        """Подготавливает результаты для отображения"""
        logger.info(f"Preparing {len(page_obj)} results for display")
        
        results = []
        for user in page_obj:
            try:
                profile = user.userprofile
                
                # Подсчет выполненных заданий
                actual_completed_tasks = TaskCompletion.objects.filter(user=user).count()
                
                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email or '',
                    'date_joined': user.date_joined,
                    'status': profile.get_status_display(),
                    'balance': profile.balance,
                    'twitter_account': profile.twitter_account or '',
                    'twitter_verification': profile.get_twitter_verification_status_display(),
                    'country_code': profile.country_code or '',
                    'chosen_country': profile.chosen_country or '',
                    'completed_tasks_count': profile.completed_tasks_count,
                    'actual_completed_tasks': actual_completed_tasks,
                    'available_tasks_count': profile.available_tasks,
                    'is_ambassador': profile.is_ambassador,
                    'is_affiliate_partner': profile.is_affiliate_partner,
                    'paypal_address': profile.paypal_address or '',
                    'usdt_address': profile.usdt_address or '',
                }
                
                # Получаем email из Firebase
                firebase_email = ''
                if user.username:
                    try:
                        firebase_email = get_firebase_email(user.username) or ''
                        logger.debug(f"Firebase email for {user.username}: {firebase_email}")
                    except Exception as e:
                        firebase_email = f'Error: {str(e)[:30]}...' if len(str(e)) > 30 else f'Error: {e}'
                        logger.warning(f"Failed to get Firebase email for {user.username}: {e}")
                user_data['firebase_email'] = firebase_email
                
                results.append(user_data)
                
            except Exception as e:
                logger.error(f"Error preparing user {user.id}: {e}")
                continue
        logger.info(f"Prepared {len(results)} results")
        return results
    
    def export_csv(self, queryset, filters):
        """Экспортирует результаты в CSV"""
        total_users = queryset.count()
        logger.info(f"Starting CSV export for {total_users} users")
        
        if total_users == 0:
            logger.warning("No users to export - queryset is empty")
        
        response = HttpResponse(content_type='text/csv')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="users_export_{timestamp}.csv"'
        
        writer = csv.writer(response)
        
        # Заголовки
        headers = [
            'ID', 'Username', 'Email', 'Firebase Email', 'Date Joined',
            'Status', 'Balance', 'Twitter Account', 'Twitter Verification',
            'Country Code', 'Chosen Country', 'Completed Tasks (Profile)',
            'Actual Completed Tasks', 'Available Tasks', 'Is Ambassador',
            'Is Affiliate Partner', 'PayPal Address', 'USDT Address'
        ]
        writer.writerow(headers)
        
        include_firebase_email = filters.get('include_firebase_email', False)
        limit = filters.get('limit_results', 1000)
        
        logger.info(f"CSV export settings: include_firebase_email={include_firebase_email}, limit={limit}")
        
        # Записываем данные пользователей
        count = 0
        error_count = 0
        
        # Получаем пользователей с профилями
        users_with_profiles = queryset.select_related('userprofile')[:limit]
        logger.info(f"Processing {users_with_profiles.count()} users with profiles")
        
        for user in users_with_profiles:
            try:
                # Проверяем наличие профиля
                if not hasattr(user, 'userprofile'):
                    logger.warning(f"User {user.id} ({user.username}) has no UserProfile - skipping")
                    error_count += 1
                    continue
                
                profile = user.userprofile
                actual_completed_tasks = TaskCompletion.objects.filter(user=user).count()
                
                firebase_email = ''
                if include_firebase_email and user.username:
                    try:
                        firebase_email = get_firebase_email(user.username) or ''
                        logger.debug(f"Firebase email for CSV export {user.username}: {firebase_email}")
                    except Exception as e:
                        firebase_email = f'Error: {e}'
                        logger.warning(f"Failed to get Firebase email for CSV export {user.username}: {e}")
                
                row = [
                    user.id,
                    user.username,
                    user.email or '',
                    firebase_email,
                    user.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
                    profile.get_status_display() if profile.status else '',
                    profile.balance if profile.balance is not None else 0,
                    profile.twitter_account or '',
                    profile.get_twitter_verification_status_display() if profile.twitter_verification_status else '',
                    profile.country_code or '',
                    profile.chosen_country or '',
                    profile.completed_tasks_count if profile.completed_tasks_count is not None else 0,
                    actual_completed_tasks,
                    profile.available_tasks if profile.available_tasks is not None else 0,
                    profile.is_ambassador if profile.is_ambassador is not None else False,
                    profile.is_affiliate_partner if profile.is_affiliate_partner is not None else False,
                    profile.paypal_address or '',
                    profile.usdt_address or '',
                ]
                
                writer.writerow(row)
                count += 1
                
                # Логируем прогресс каждые 100 записей
                if count % 100 == 0:
                    logger.info(f"Exported {count} users to CSV")
                    
            except Exception as e:
                logger.error(f"Error exporting user {user.id} ({getattr(user, 'username', 'unknown')}) to CSV: {e}")
                error_count += 1
                continue
                
        logger.info(f"CSV export completed: {count} users exported successfully, {error_count} errors")
        
        # Если не экспортировано ни одного пользователя, добавляем строку с информацией
        if count == 0 and total_users > 0:
            writer.writerow(['No data exported', f'Processed {total_users} users but all failed', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
            logger.error(f"CSV export failed: 0 users exported from {total_users} total users")
        
        return response
