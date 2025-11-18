from django.apps import AppConfig
import os
from django.conf import settings
import firebase_admin
from firebase_admin import credentials
import logging

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
            firebase_admin.initialize_app(cred)
        import api.signals  # Импортируем сигналы при запуске приложения