from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from .models import ActionLanding
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
        return ActionLanding.objects.all().order_by('-created_at') 