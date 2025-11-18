from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.cache import cache
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import timedelta
import logging
from .models import TaskCompletion, Task, SocialNetwork, ActionType
import json

logger = logging.getLogger(__name__)

class MedianSpeedView(View):
    """
    API эндпоинт для получения медианной скорости выполнения заданий
    Кэширует результат на 24 часа
    """
    
    def get(self, request):
        try:
            # Получаем параметры из запроса
            social_network_code = request.GET.get('social_network')
            action_type = request.GET.get('action')
            actions_count = request.GET.get('actions_count')
            
            # Валидация параметров
            if not social_network_code:
                return JsonResponse({'error': 'social_network parameter is required'}, status=400)
            
            if not action_type:
                return JsonResponse({'error': 'action parameter is required'}, status=400)
            
            if not actions_count:
                return JsonResponse({'error': 'actions_count parameter is required'}, status=400)
            
            try:
                actions_count = int(actions_count)
                if actions_count <= 0:
                    return JsonResponse({'error': 'actions_count must be positive integer'}, status=400)
            except ValueError:
                return JsonResponse({'error': 'actions_count must be valid integer'}, status=400)
            
            # Проверяем существование социальной сети
            try:
                social_network = SocialNetwork.objects.get(code=social_network_code)
            except SocialNetwork.DoesNotExist:
                return JsonResponse({'error': f'Social network {social_network_code} not found'}, status=404)
            
            # Проверяем существование типа действия
            try:
                action_type_obj = ActionType.objects.get(code=action_type)
            except ActionType.DoesNotExist:
                return JsonResponse({'error': f'Action type {action_type} not found'}, status=404)
            
            # Формируем ключ кэша
            cache_key = f"median_speed_{social_network_code}_{action_type}_{actions_count}"
            
            # Проверяем кэш
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.info(f"Returning cached median speed for {social_network_code}/{action_type}/{actions_count}")
                return JsonResponse(cached_result)
            
            # Вычисляем медианную скорость
            median_speed = self.calculate_median_speed(social_network, action_type_obj, actions_count)
            
            # Формируем ответ
            result = {
                'social_network': social_network_code,
                'action': action_type,
                'actions_count': actions_count,
                'median_speed_minutes': median_speed,
                'cached_at': timezone.now().isoformat(),
                'cache_expires_in': '24 hours'
            }
            
            # Кэшируем результат на 24 часа
            cache.set(cache_key, result, 86400)  # 86400 секунд = 24 часа
            
            logger.info(f"Calculated and cached median speed for {social_network_code}/{action_type}/{actions_count}: {median_speed} minutes")
            
            return JsonResponse(result)
            
        except Exception as e:
            logger.error(f"Error in MedianSpeedView: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)
    
    def calculate_median_speed(self, social_network, action_type_obj, actions_count):
        """
        Вычисляет медианную скорость выполнения заданий
        """
        # Дата вчера
        yesterday = timezone.now().date() - timedelta(days=1)
        
        # Ищем задания с точным количеством действий
        exact_tasks = Task.objects.filter(
            social_network=social_network,
            type=action_type_obj.code,
            actions_required=actions_count,
            status='COMPLETED',
            completed_at__date=yesterday
        )
        
        if exact_tasks.exists():
            # Если есть задания с точным количеством действий, считаем медиану
            speeds = []
            for task in exact_tasks:
                if task.created_at and task.completed_at:
                    duration = task.completed_at - task.created_at
                    speed_minutes = duration.total_seconds() / 60
                    speeds.append(speed_minutes)
            
            if speeds:
                speeds.sort()
                n = len(speeds)
                if n % 2 == 0:
                    median = (speeds[n//2 - 1] + speeds[n//2]) / 2
                else:
                    median = speeds[n//2]
                
                logger.info(f"Found {len(speeds)} exact matches for {social_network.code}/{action_type_obj.code}/{actions_count}, median: {median:.2f} minutes")
                return round(median, 2)
        
        # Если точных совпадений нет, считаем среднее по социальной сети
        logger.info(f"No exact matches for {social_network.code}/{action_type_obj.code}/{actions_count}, calculating average for social network")
        
        all_tasks = Task.objects.filter(
            social_network=social_network,
            type=action_type_obj.code,
            status='COMPLETED',
            completed_at__date=yesterday
        )
        
        speeds = []
        for task in all_tasks:
            if task.created_at and task.completed_at:
                duration = task.completed_at - task.created_at
                speed_minutes = duration.total_seconds() / 60
                speeds.append(speed_minutes)
        
        if speeds:
            speeds.sort()
            n = len(speeds)
            if n % 2 == 0:
                median = (speeds[n//2 - 1] + speeds[n//2]) / 2
            else:
                median = speeds[n//2]
            
            logger.info(f"Found {len(speeds)} tasks for {social_network.code}/{action_type_obj.code}, median: {median:.2f} minutes")
            return round(median, 2)
        
        # Если вообще нет данных, возвращаем дефолтное значение
        logger.warning(f"No completed tasks found for {social_network.code}/{action_type_obj.code} on {yesterday}")
        return 60.0  # Дефолт: 60 минут

# Декоратор для отключения CSRF (если нужно)
@method_decorator(csrf_exempt, name='dispatch')
class MedianSpeedViewCSRFExempt(MedianSpeedView):
    """Версия с отключенным CSRF для внешних API"""
    pass
