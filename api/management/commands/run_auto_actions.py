from django.core.management.base import BaseCommand
from api.auto_actions import process_auto_actions
import logging

logger = logging.getLogger('api.management.commands.run_auto_actions')

class Command(BaseCommand):
    help = 'Runs auto actions processing once'

    def handle(self, *args, **options):
        try:
            logger.info("Starting one-time auto actions processing")
            process_auto_actions()
            logger.info("One-time auto actions processing completed")
            self.stdout.write(self.style.SUCCESS('Successfully ran auto actions'))
        except Exception as e:
            logger.error(f"Error running auto actions: {str(e)}")
            self.stdout.write(self.style.ERROR(f'Error running auto actions: {str(e)}')) 