from django.core.management.base import BaseCommand
from api.models import SocialNetwork, ActionType, BuyLanding
from django.utils.text import slugify
import logging

logger = logging.getLogger(__name__)

# Маппинг для name_plural на основе кодов действий
ACTION_PLURAL_MAPPING = {
    'LIKE': 'Likes',
    'REPOST': 'Reposts',
    'COMMENT': 'Comments',
    'FOLLOW': 'Followers',
    'SAVE': 'Saves',
    'BOOST': 'Boosts',
    'FAVORITE': 'Favorites',
    'REPLY': 'Replies',
    'CLAP': 'Claps',
    'RESTACK': 'Restacks',
    'UPVOTE': 'Upvotes',
    'DOWNVOTE': 'Downvotes',
    'UP': 'Ups',
    'DOWN': 'Downs',
    'STAR': 'Stars',
    'WATCH': 'Watchers',
    'CONNECT': 'Connections',
    'UNICORN': 'Unicorns',
    'INSTALL': 'Installs',
    'SHARE': 'Shares',
}

class Command(BaseCommand):
    help = 'Creates BuyLanding pages for all active SocialNetwork + ActionType combinations and fills name_plural for ActionTypes'

    def handle(self, *args, **options):
        logger.info("Starting creation of BuyLanding pages and filling name_plural")
        
        # 1. Заполняем name_plural для всех ActionType
        self.stdout.write("Filling name_plural for ActionTypes...")
        action_types = ActionType.objects.all()
        updated_actions = 0
        
        for action_type in action_types:
            if not action_type.name_plural and action_type.code in ACTION_PLURAL_MAPPING:
                action_type.name_plural = ACTION_PLURAL_MAPPING[action_type.code]
                action_type.save(update_fields=['name_plural'])
                updated_actions += 1
                logger.info(f"Updated {action_type.code}: {action_type.name_plural}")
            elif not action_type.name_plural:
                # Если нет в маппинге, пытаемся сгенерировать автоматически
                plural = action_type.name + 's' if not action_type.name.endswith('s') else action_type.name
                action_type.name_plural = plural
                action_type.save(update_fields=['name_plural'])
                updated_actions += 1
                logger.info(f"Auto-generated plural for {action_type.code}: {action_type.name_plural}")
        
        self.stdout.write(self.style.SUCCESS(f"Updated {updated_actions} ActionTypes with name_plural"))
        
        # 2. Создаем BuyLanding для всех активных комбинаций
        self.stdout.write("Creating BuyLanding pages...")
        active_networks = SocialNetwork.objects.filter(is_active=True).prefetch_related('available_actions')
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        for network in active_networks:
            available_actions = network.available_actions.all()
            self.stdout.write(f"Processing {network.name} ({network.code}) with {available_actions.count()} actions")
            
            for action in available_actions:
                try:
                    # Проверяем, существует ли уже такой лендинг
                    existing = BuyLanding.objects.filter(
                        social_network=network,
                        action=action
                    ).first()
                    
                    if existing:
                        logger.info(f"BuyLanding already exists for {network.name} - {action.name}")
                        skipped_count += 1
                        continue
                    
                    # Получаем name_plural или используем name
                    action_plural = action.name_plural or action.name
                    
                    # Формируем заголовок: "Buy {SocialNetwork} {ActionType Plural}"
                    title = f"Buy {network.name} {action_plural}"
                    
                    # Формируем slug: "buy-{network-code}-{action-plural}" (используем plural форму)
                    action_plural_slug = slugify(action_plural.lower())
                    slug = f"buy-{network.code.lower()}-{action_plural_slug}"
                    
                    # Проверяем уникальность slug
                    slug_base = slug
                    counter = 1
                    while BuyLanding.objects.filter(slug=slug).exists():
                        slug = f"{slug_base}-{counter}"
                        counter += 1
                    
                    # Создаем описание
                    description = f"Get {action_plural.lower()} for your {network.name} content. Boost your engagement and grow your audience with our reliable service."
                    short_description = f"Buy {action_plural.lower()} for {network.name} and increase your social media engagement."
                    
                    # Создаем BuyLanding
                    landing = BuyLanding.objects.create(
                        title=title,
                        description=description,
                        short_description=short_description,
                        social_network=network,
                        action=action,
                        slug=slug
                    )
                    
                    logger.info(f"Created BuyLanding: {title} (slug: {slug})")
                    created_count += 1
                    
                except Exception as e:
                    logger.error(f"Error creating BuyLanding for {network.name} - {action.name}: {str(e)}")
                    error_count += 1
        
        summary = f"""
        BuyLanding creation completed:
        ActionTypes updated with name_plural: {updated_actions}
        New BuyLanding pages created: {created_count}
        BuyLanding pages skipped (already exist): {skipped_count}
        Errors encountered: {error_count}
        """
        
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))

