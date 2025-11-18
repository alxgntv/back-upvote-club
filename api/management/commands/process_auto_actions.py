from django.core.management.base import BaseCommand
from django.utils import timezone
import logging
import os
from api.auto_actions import process_auto_actions

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process auto actions for users with enabled auto actions'

    def handle(self, *args, **options):
        logger.info(f"""
            Starting auto actions processing:
            Time: {timezone.now()}
        """)
        
        try:
            process_auto_actions()
        except Exception as e:
            logger.error(f"Error in auto actions processing: {str(e)}")
