from django.core.management.base import BaseCommand
from api.models import UserProfile
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Обновляет available_tasks для всех пользователей до их дневного лимита'

    def handle(self, *args, **options):
        
        # Получаем всех пользователей
        profiles = UserProfile.objects.all()
        total_users = profiles.count()
        updated = 0
        skipped = 0

        for profile in profiles:
            try:
                old_tasks = profile.available_tasks
                daily_limit = 0

                # Определяем дневной лимит в зависимости от статуса
                if profile.status == 'FREE':
                    # Для FREE пользователей: 1 задание в день, если страна выбрана
                    if profile.chosen_country:
                        daily_limit = 1
                    else:
                        daily_limit = 0  # Если страна не выбрана
                elif profile.status == 'MEMBER':
                    daily_limit = 1
                elif profile.status == 'BUDDY':
                    daily_limit = 10
                elif profile.status == 'MATE':
                    daily_limit = 1000000

                # Если текущее количество меньше лимита, поднимаем до лимита
                if profile.available_tasks < daily_limit:
                    profile.available_tasks = daily_limit
                    profile.save()
                    updated += 1
                    
                else:
                    skipped += 1


            except Exception as e:
                logger.error(f"Error updating user {profile.user.username}: {str(e)}")

        summary = f"""
        Task update completed:
        Total users: {total_users}
        Updated to limit: {updated}
        Already at limit: {skipped}
        """
        
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))
