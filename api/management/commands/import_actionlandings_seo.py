from django.core.management.base import BaseCommand
from django.conf import settings
from api.models import ActionLanding
import csv
import os
import json

FIELDS_TO_UPDATE = [
    'meta_title',
    'meta_description',
    'h1',
    'content',
    'page_type',
    'short_description',
    'long_description',
    'redirect_url',
]

class Command(BaseCommand):
    help = 'Импортирует SEO-поля из staticfiles/seo/seo-landings-content.csv в существующие ActionLanding по slug.'

    def handle(self, *args, **options):
        csv_path = os.path.join(settings.BASE_DIR, 'staticfiles', 'seo', 'seo-landings-content.csv')
        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f'Файл не найден: {csv_path}'))
            return

        updated = 0
        skipped = 0
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                slug = row.get('slug', '').strip()
                if not slug:
                    skipped += 1
                    continue
                try:
                    landing = ActionLanding.objects.get(slug=slug)
                except ActionLanding.DoesNotExist:
                    skipped += 1
                    continue
                for field in FIELDS_TO_UPDATE:
                    landing.__setattr__(field, row.get(field, ''))

                # Обработка поля FAQ (JSON)
                faq_raw = (row.get('faq') or '').strip()
                faq_value = None
                if faq_raw:
                    try:
                        faq_value = json.loads(faq_raw)
                    except Exception:
                        # Если JSON некорректный — очищаем поле, чтобы не хранить строку
                        faq_value = None

                landing.faq = faq_value

                update_fields = list(FIELDS_TO_UPDATE) + ['faq']
                landing.save(update_fields=update_fields)
                updated += 1
        self.stdout.write(self.style.SUCCESS(f'Обновлено лендингов: {updated}'))
        self.stdout.write(self.style.WARNING(f'Пропущено (не найдено по slug): {skipped}'))
