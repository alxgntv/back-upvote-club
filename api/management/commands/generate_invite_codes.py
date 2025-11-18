from django.core.management.base import BaseCommand
from api.models import UserProfile

class Command(BaseCommand):
    help = 'Генерирует инвайт-коды для существующих пользователей'

    def handle(self, *args, **options):
        profiles = UserProfile.objects.filter(personal_invite_code__isnull=True)
        for profile in profiles:
            profile.save()  # Это вызовет генерацию инвайт-кода
        self.stdout.write(self.style.SUCCESS(f'Успешно сгенерированы инвайт-коды для {profiles.count()} пользователей'))