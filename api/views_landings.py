from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from .models import ActionLanding, SocialNetwork
from .serializers import ActionLandingSerializer
import logging

logger = logging.getLogger('api')

class ActionLandingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с лендингами действий.
    Поддерживает фильтрацию по:
    - social_network (код социальной сети)
    - action (тип действия)
    """
    serializer_class = ActionLandingSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        queryset = ActionLanding.objects.all().select_related(
            'social_network'
        ).prefetch_related(
            'reviews',
            'reviews__social_network',
            'reviews__action',
            'reviews__user'
        ).order_by('-created_at')
        
        # Фильтрация по query параметрам
        social_network_code = self.request.query_params.get('social_network')
        action_code = self.request.query_params.get('action')
        
        if social_network_code:
            try:
                social_network = SocialNetwork.objects.get(code__iexact=social_network_code)
                queryset = queryset.filter(social_network=social_network)
            except SocialNetwork.DoesNotExist:
                queryset = queryset.none()
        
        if action_code:
            queryset = queryset.filter(action__iexact=action_code)
        elif action_code == '':
            # Явно указано, что action должен быть NULL
            queryset = queryset.filter(action__isnull=True)
        
        return queryset

    @action(detail=False, methods=['get'], url_path='by-path')
    def by_path(self, request):
        """
        Получить лендинг по полному пути URL.
        
        Query параметр: path (например: twitter, twitter/like, twitter/buy-twitter-landing)
        
        Примеры:
        - /api/landings/by-path/?path=twitter → запись для /twitter
        - /api/landings/by-path/?path=twitter/like → запись для /twitter/like
        - /api/landings/by-path/?path=twitter/buy-twitter-landing → запись для /twitter/buy-twitter-landing
        """
        path = request.query_params.get('path')
        
        if not path:
            return Response(
                {'error': 'Path query parameter is required (e.g., ?path=twitter or ?path=twitter/like)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Убираем ведущий и trailing слэш
        path = path.strip('/')
        parts = [p for p in path.split('/') if p]
        
        if not parts:
            return Response(
                {'error': 'Invalid path format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        platform_code = parts[0].upper()
        
        try:
            social_network = SocialNetwork.objects.get(code__iexact=platform_code)
        except SocialNetwork.DoesNotExist:
            return Response(
                {'error': f'Social network "{platform_code}" not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Случай 1: /twitter → platform only, action=None, slug='twitter'
        if len(parts) == 1:
            landing = ActionLanding.objects.filter(
                social_network=social_network,
                action__isnull=True,
                slug=parts[0].lower()
            ).first()
            
            if landing:
                serializer = self.get_serializer(landing)
                return Response(serializer.data)
            
            return Response(
                {'error': f'Landing not found for path: /{path}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Случай 2: /twitter/like или /twitter/buy-twitter-landing
        if len(parts) == 2:
            second_part = parts[1].lower()
            expected_action_slug = f"{parts[0].lower()}-{second_part}"
            action_code = parts[1].upper()
            
            # Вариант 2a: /twitter/like → ищем экшеновый лендинг (slug='twitter-like', action='LIKE')
            landing = ActionLanding.objects.filter(
                social_network=social_network,
                action__iexact=action_code,
                slug=expected_action_slug
            ).first()
            
            if landing:
                serializer = self.get_serializer(landing)
                return Response(serializer.data)
            
            # Вариант 2b: /twitter/buy-twitter-landing → ищем кастомный slug под платформой (action=None)
            landing = ActionLanding.objects.filter(
                social_network=social_network,
                action__isnull=True,
                slug=second_part
            ).first()
            
            if landing:
                serializer = self.get_serializer(landing)
                return Response(serializer.data)
            
            return Response(
                {'error': f'Landing not found for path: /{path}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(
            {'error': 'Invalid path format'},
            status=status.HTTP_400_BAD_REQUEST
        ) 