from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import ActionLanding
import csv
import os
import json
from datetime import datetime, date


class Command(BaseCommand):
    help = 'Экспортирует все поля модели ActionLanding в CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='actionlandings_export.csv',
            help='Путь к выходному CSV-файлу (по умолчанию в BASE_DIR)'
        )

    def _serialize_value(self, value):
        if value is None:
            return ''
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def handle(self, *args, **options):
        output_name = options['output']
        output_path = output_name if os.path.isabs(output_name) else os.path.join(settings.BASE_DIR, output_name)

        # Собираем список полей модели (исключая авто-созданные/реверсные/M2M)
        model_fields = [
            f for f in ActionLanding._meta.get_fields()
            if getattr(f, 'concrete', False) and not getattr(f, 'many_to_many', False) and not getattr(f, 'auto_created', False)
        ]

        # Готовим заголовки CSV: для FK social_network делаем отдельные колонки
        header = []
        for field in model_fields:
            if field.name == 'social_network':
                header.extend(['social_network_id', 'social_network_code', 'social_network_name'])
            else:
                header.append(field.name)

        # Пишем CSV
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=header)
            writer.writeheader()

            for landing in ActionLanding.objects.all().select_related('social_network'):
                row = {}
                for field in model_fields:
                    fname = field.name
                    if fname == 'social_network':
                        sn = landing.social_network
                        row['social_network_id'] = getattr(landing, 'social_network_id', '') or ''
                        row['social_network_code'] = getattr(sn, 'code', '') if sn else ''
                        row['social_network_name'] = getattr(sn, 'name', '') if sn else ''
                    else:
                        value = getattr(landing, fname, None)
                        row[fname] = self._serialize_value(value)

                # Очищаем значения в CSV для short_description и long_description
                if 'short_description' in row:
                    row['short_description'] = ''
                if 'long_description' in row:
                    row['long_description'] = ''

                writer.writerow(row)

        self.stdout.write(self.style.SUCCESS(f'Экспортировано {ActionLanding.objects.count()} записей в {output_path}')) 