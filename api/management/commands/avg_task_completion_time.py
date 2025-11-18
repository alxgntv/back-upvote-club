from django.core.management.base import BaseCommand
from api.models import Task
from django.db.models import Avg
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Показывает среднее время выполнения задания для всех COMPLETED задач, можно фильтровать по actions_required'

    def add_arguments(self, parser):
        parser.add_argument(
            '-a', '--actions_required',
            type=int,
            default=None,
            help='Считать только задания с actions_required=X'
        )

    def handle(self, *args, **options):
        actions_required = options.get('actions_required')
        qs = Task.objects.filter(status='COMPLETED', completion_duration__isnull=False)
        if actions_required is not None:
            qs = qs.filter(actions_required=actions_required)
        avg_duration = qs.aggregate(avg=Avg('completion_duration'))['avg']
        count = qs.count()

        if avg_duration is not None:
            # avg_duration — это timedelta
            total_seconds = avg_duration.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
            filter_info = f' (actions_required={actions_required})' if actions_required is not None else ''
            self.stdout.write(self.style.SUCCESS(
                f'Среднее время выполнения задания{filter_info} (по {count} задачам): {hours}ч {minutes}м {seconds}с'
            ))
        else:
            self.stdout.write(self.style.WARNING('Нет завершённых задач с заполненным временем выполнения по заданному фильтру.')) 