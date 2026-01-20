from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import BuyLanding, ActionLanding
import logging

logger = logging.getLogger('api')


@receiver([post_save, post_delete], sender=BuyLanding)
def clear_buy_landing_cache_on_change(sender, instance, **kwargs):
    """
    Automatically clear cache when BuyLanding is saved or deleted
    """
    try:
        cache.delete('buy_landings_list')
        cache.delete('buy_landings_all')
        cache.delete(f'buy_landing_{instance.slug}')
    except Exception as e:
        logger.error(f"Error clearing BuyLanding cache: {str(e)}")


@receiver([post_save, post_delete], sender=ActionLanding)
def clear_action_landing_cache_on_change(sender, instance, **kwargs):
    """
    Automatically clear cache when ActionLanding is saved or deleted
    """
    try:
        cache.delete('action_landings_list_all_all')
        cache.delete(f'action_landing_{instance.slug}')
        cache.delete(f'action_landing_by_path_{instance.slug}')
        
        if instance.social_network and instance.action:
            social_code = instance.social_network.code.lower()
            action_code = instance.action.upper()
            path_key = f'{social_code}/{action_code.lower()}'
            cache.delete(f'action_landing_by_path_{path_key}')
            cache.delete(f'action_landings_list_{social_code}_{action_code}')
        
    except Exception as e:
        logger.error(f"Error clearing ActionLanding cache: {str(e)}")
