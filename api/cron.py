from .models import UserProfile
import logging

logger = logging.getLogger(__name__)

def update_all_user_tasks():
    """Ежедневное обновление доступных заданий ТОЛЬКО для платных пользователей"""
    logger.info("Starting daily task update for paid users")
    try:
        # Получаем только платные профили (явно исключаем FREE)
        profiles = UserProfile.objects.filter(status__in=['MEMBER', 'BUDDY', 'MATE'])
        total_profiles = profiles.count()
        
        logger.info(f"Found {total_profiles} paid profiles to update")
        
        updated_count = 0
        for profile in profiles:
            try:
                logger.debug(f"""Processing paid user:
                    Username: {profile.user.username}
                    Status: {profile.status}
                    Current tasks: {profile.available_tasks}
                """)
                
                if profile.update_available_tasks():  # Проверяем результат обновления
                    updated_count += 1
                
            except Exception as e:
                logger.error(f"Error updating tasks for user {profile.user.username}: {str(e)}")
        
        logger.info(f"Successfully updated {updated_count}/{total_profiles} paid user profiles")
        
    except Exception as e:
        logger.error(f"Error in update_all_user_tasks: {str(e)}")
