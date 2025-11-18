from django.core.management.base import BaseCommand
from api.models import UserProfile, SocialNetwork, UserSocialProfile
from django.utils import timezone
import logging
import tweepy
from django.conf import settings
from time import sleep
import time
import signal
from django.db import connection
import os

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Migrates verified Twitter profiles to UserSocialProfile model with full data'
    
    def __init__(self):
        super().__init__()
        signal.signal(signal.SIGTERM, self.handle_timeout)
        self.is_running = True
        self.BATCH_SIZE = 1
        self.RATE_LIMIT_PAUSE = 910  # ~15 минут

    def handle_timeout(self, signum, frame):
        """Обработчик таймаута Heroku"""
        logger.warning("Received SIGTERM signal. Gracefully shutting down...")
        self.is_running = False
        connection.close()

    def is_profile_complete(self, profile):
        """Проверяет, полностью ли заполнен профиль"""
        return all([
            profile.social_id,
            profile.username,
            profile.profile_url,
            profile.followers_count > 0,
            profile.following_count > 0,
            profile.posts_count > 0,
            profile.account_created_at,
            profile.last_sync_at
        ])

    def handle_rate_limit(self, error, username):
        """Обрабатывает rate limit ошибки"""
        logger.warning(f"Rate limit hit while processing @{username}")
        
        if hasattr(error, 'response') and error.response is not None:
            reset_time = error.response.headers.get('x-rate-limit-reset')
            if reset_time:
                wait_seconds = int(reset_time) - int(time.time()) + 10
                logger.info(f"Rate limit will reset in {wait_seconds} seconds for @{username}")
                return max(wait_seconds, 60)
        return 920

    def process_twitter_profile(self, profile, client, retries=0):
        """Обрабатывает Twitter профиль с поддержкой повторных попыток"""
        max_retries = 10
        
        while retries < max_retries:
            try:
                logger.info(f"Attempting to fetch data for @{profile.twitter_account} (attempt {retries + 1}/{max_retries})")
                
                user_response = client.get_user(
                    username=profile.twitter_account,
                    user_fields=['public_metrics,profile_image_url,created_at']
                )
                
                if user_response and hasattr(user_response, 'data'):
                    return user_response
                    
            except tweepy.TooManyRequests as e:
                wait_time = self.handle_rate_limit(e, profile.twitter_account)
                logger.info(f"Waiting {wait_time} seconds before retry...")
                sleep(wait_time)
                retries += 1
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error for @{profile.twitter_account}: {str(e)}")
                if retries < max_retries - 1:
                    sleep(60)
                    retries += 1
                    continue
                raise e
        
        raise Exception(f"Max retries ({max_retries}) exceeded for @{profile.twitter_account}")

    def handle(self, *args, **options):
        start_time = timezone.now()
        logger.info(f"""
        Starting migration on Heroku:
        Dyno: {os.environ.get('DYNO', 'unknown')}
        App Name: {os.environ.get('HEROKU_APP_NAME', 'unknown')}
        """)
        
        try:
            # Проверка креденшелов
            if not all([
                settings.TWITTER_API_KEY and len(settings.TWITTER_API_KEY) >= 10,
                settings.TWITTER_API_SECRET_KEY and len(settings.TWITTER_API_SECRET_KEY) >= 10,
                settings.TWITTER_BEARER_TOKEN and len(settings.TWITTER_BEARER_TOKEN) >= 10
            ]):
                raise ValueError("Invalid Twitter API credentials")

            twitter_network = SocialNetwork.objects.get_or_create(
                code='TWITTER',
                defaults={
                    'name': 'Twitter',
                    'icon': 'twitter',
                    'is_active': True
                }
            )[0]

            # Получаем только необработанные профили
            verified_profiles = UserProfile.objects.filter(
                twitter_verification_status='CONFIRMED',
                twitter_account__isnull=False
            ).exclude(
                user__in=UserSocialProfile.objects.filter(
                    social_network=twitter_network,
                    is_verified=True
                ).values('user')
            ).select_related('user')
            
            total_count = verified_profiles.count()
            logger.info(f"Found {total_count} verified Twitter profiles to process")

            stats = {
                'migrated': 0,
                'skipped': 0,
                'errors': 0,
                'updated': 0
            }

            client = tweepy.Client(
                bearer_token=settings.TWITTER_BEARER_TOKEN,
                consumer_key=settings.TWITTER_API_KEY,
                consumer_secret=settings.TWITTER_API_SECRET_KEY,
                wait_on_rate_limit=True
            )

            # Тестовый запрос
            try:
                test_user = client.get_user(username="twitter")
                logger.info("Twitter API test successful")
            except Exception as e:
                logger.error(f"Twitter API test failed: {str(e)}")
                raise

            profiles_list = list(verified_profiles)
            profile_batches = [profiles_list[i:i + self.BATCH_SIZE] for i in range(0, len(profiles_list), self.BATCH_SIZE)]
            
            logger.info(f"Processing {len(profiles_list)} profiles in {len(profile_batches)} batches")

            for batch_index, batch in enumerate(profile_batches, 1):
                # Проверяем время выполнения (28 минут)
                if (timezone.now() - start_time).total_seconds() > 1680:
                    logger.warning("Approaching Heroku timeout limit (28 minutes), stopping processing")
                    break
                
                for profile in batch:
                    try:
                        logger.info(f"Processing user: @{profile.twitter_account} (Batch: {batch_index}/{len(profile_batches)})")

                        social_profile, created = UserSocialProfile.objects.get_or_create(
                            user=profile.user,
                            social_network=twitter_network,
                            username=profile.twitter_account,
                            defaults={
                                'verification_status': 'VERIFIED',
                                'is_verified': True,
                                'verification_date': profile.twitter_verification_date or timezone.now()
                            }
                        )

                        if not created:
                            logger.info(f"Updating existing profile for @{profile.twitter_account}")
                            stats['updated'] += 1
                        else:
                            stats['migrated'] += 1

                        user_response = self.process_twitter_profile(profile, client)
                        
                        if user_response and hasattr(user_response, 'data'):
                            user_data = user_response.data
                            
                            social_profile.social_id = str(user_data.id)
                            social_profile.profile_url = f"https://twitter.com/{user_data.username}"
                            
                            if hasattr(user_data, 'profile_image_url'):
                                social_profile.avatar_url = user_data.profile_image_url.replace('_normal', '_400x400')
                            
                            if hasattr(user_data, 'public_metrics'):
                                metrics = user_data.public_metrics
                                social_profile.followers_count = metrics.get('followers_count', 0)
                                social_profile.following_count = metrics.get('following_count', 0)
                                social_profile.posts_count = metrics.get('tweet_count', 0)
                            
                            if hasattr(user_data, 'created_at'):
                                social_profile.account_created_at = user_data.created_at
                            
                            social_profile.last_sync_at = timezone.now()
                            social_profile.save()

                            logger.info(f"""Successfully updated profile:
                                Username: @{profile.twitter_account}
                                Followers: {social_profile.followers_count}
                                Following: {social_profile.following_count}
                                Posts: {social_profile.posts_count}
                            """)
                        else:
                            logger.error(f"No data received for @{profile.twitter_account}")
                            stats['errors'] += 1

                        sleep(30)  # Пауза между профилями

                    except Exception as e:
                        logger.error(f"Error processing @{profile.twitter_account}: {str(e)}")
                        stats['errors'] += 1
                        continue
                
                if batch_index < len(profile_batches):
                    logger.info(f"Batch complete. Waiting {self.RATE_LIMIT_PAUSE} seconds...")
                    sleep(self.RATE_LIMIT_PAUSE)

            execution_time = timezone.now() - start_time
            
            summary = f"""
            Migration session completed:
            Execution time: {execution_time}
            Profiles processed in this session: {stats['migrated'] + stats['updated']}
            New profiles: {stats['migrated']}
            Updated: {stats['updated']}
            Errors: {stats['errors']}
            """
            
            logger.info(summary)
            self.stdout.write(self.style.SUCCESS(summary))

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            self.stdout.write(self.style.ERROR(f'Migration failed: {str(e)}'))
