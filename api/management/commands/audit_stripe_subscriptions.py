from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from api.models import UserProfile
from firebase_admin import auth
import stripe
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Audit Stripe subscriptions and sync user statuses with Firebase emails'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making any changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        logger.info(f"""
            ═══════════════════════════════════════════════════
            Starting Stripe Subscription Audit
            Time: {timezone.now()}
            Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE MODE'}
            ═══════════════════════════════════════════════════
        """)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY RUN mode - no changes will be made'))
        
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            
            # Step 1: Get all active and trialing subscriptions from Stripe
            self.stdout.write('Step 1: Fetching subscriptions from Stripe (active + trialing)...')
            stripe_subscriptions = self.get_active_stripe_subscriptions()
            
            active_count = sum(1 for status in stripe_subscriptions.values() if status == 'active')
            trialing_count = sum(1 for status in stripe_subscriptions.values() if status == 'trialing')
            
            logger.info(f"Found {len(stripe_subscriptions)} subscriptions in Stripe ({active_count} active + {trialing_count} trialing)")
            self.stdout.write(self.style.SUCCESS(f'✓ Found {len(stripe_subscriptions)} subscriptions ({active_count} active + {trialing_count} trialing)'))
            
            # Step 2: Get all users from database and their Firebase emails
            self.stdout.write('\nStep 2: Fetching users from database and Firebase...')
            user_data = self.get_users_with_firebase_emails()
            
            logger.info(f"Found {len(user_data)} users in database")
            self.stdout.write(self.style.SUCCESS(f'✓ Found {len(user_data)} users in database'))
            
            # Step 3: Compare and update
            self.stdout.write('\nStep 3: Comparing and updating user statuses...')
            stats = self.sync_user_statuses(user_data, stripe_subscriptions, dry_run)
            
            # Step 4: Print summary
            self.print_summary(stats, stripe_subscriptions, user_data, dry_run)
            
        except Exception as e:
            error_msg = f"Error during subscription audit: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(f'✗ {error_msg}'))

    def get_active_stripe_subscriptions(self):
        """Get all active and trialing subscriptions from Stripe and return dict of emails with statuses"""
        stripe_subscriptions = {}  # {email: status}
        
        try:
            # Get all active and trialing subscriptions
            # past_due and canceled are NOT included - those users should be downgraded to FREE
            active_subscriptions = stripe.Subscription.list(
                status='active',
                limit=100
            )
            trialing_subscriptions = stripe.Subscription.list(
                status='trialing',
                limit=100
            )
            
            # Process active subscriptions
            active_list = list(active_subscriptions.auto_paging_iter())
            for subscription in active_list:
                try:
                    customer_id = subscription.customer
                    customer = stripe.Customer.retrieve(customer_id)
                    email = customer.email
                    
                    if email:
                        stripe_subscriptions[email.lower()] = 'active'
                        logger.info(f"Stripe ACTIVE subscription: {email} (Customer: {customer_id})")
                    else:
                        logger.warning(f"Stripe subscription without email: Customer {customer_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing Stripe subscription {subscription.id}: {str(e)}")
            
            # Process trialing subscriptions
            trialing_list = list(trialing_subscriptions.auto_paging_iter())
            for subscription in trialing_list:
                try:
                    customer_id = subscription.customer
                    customer = stripe.Customer.retrieve(customer_id)
                    email = customer.email
                    
                    if email:
                        stripe_subscriptions[email.lower()] = 'trialing'
                        logger.info(f"Stripe TRIALING subscription: {email} (Customer: {customer_id})")
                    else:
                        logger.warning(f"Stripe subscription without email: Customer {customer_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing Stripe subscription {subscription.id}: {str(e)}")
            
            logger.info(f"Total subscriptions: {len(stripe_subscriptions)} ({len(active_list)} active + {len(trialing_list)} trialing)")
                    
        except Exception as e:
            logger.error(f"Error fetching Stripe subscriptions: {str(e)}")
            raise
            
        return stripe_subscriptions

    def get_users_with_firebase_emails(self):
        """Get all users from database with their Firebase emails"""
        user_data = []
        
        # Optimization: Only check users with paid status (not FREE)
        # FREE users don't need to be checked against Stripe
        users = User.objects.select_related('userprofile').exclude(
            userprofile__status='FREE'
        )
        
        total_users = users.count()
        self.stdout.write(f'  Processing {total_users} non-FREE users (skipping FREE users)...')
        logger.info(f"Processing {total_users} non-FREE users")
        
        processed = 0
        for user in users:
            processed += 1
            if processed % 10 == 0:
                self.stdout.write(f'  Progress: {processed}/{total_users} users processed...', ending='\r')
                self.stdout.flush()
            try:
                firebase_uid = user.username
                
                # Get email from Firebase
                try:
                    firebase_user = auth.get_user(firebase_uid)
                    email = firebase_user.email
                except Exception as e:
                    logger.warning(f"Could not get Firebase email for UID {firebase_uid}: {str(e)}")
                    email = None
                
                user_data.append({
                    'user': user,
                    'profile': user.userprofile,
                    'firebase_uid': firebase_uid,
                    'email': email.lower() if email else None,
                    'current_status': user.userprofile.status
                })
                
            except UserProfile.DoesNotExist:
                logger.warning(f"User {user.username} has no profile")
            except Exception as e:
                logger.error(f"Error processing user {user.username}: {str(e)}")
        
        self.stdout.write(f'\n  Completed processing {processed} users')
        return user_data

    def sync_user_statuses(self, user_data, stripe_subscriptions, dry_run):
        """Compare users with Stripe subscriptions and update statuses"""
        stats = {
            'kept_paid': 0,
            'kept_active': 0,
            'kept_trialing': 0,
            'downgraded_to_free': 0,
            'already_free': 0,
            'errors': 0,
            'no_email': 0
        }
        
        for user_info in user_data:
            user = user_info['user']
            profile = user_info['profile']
            email = user_info['email']
            current_status = user_info['current_status']
            firebase_uid = user_info['firebase_uid']
            
            # Skip users without email
            if not email:
                stats['no_email'] += 1
                logger.warning(f"User {firebase_uid} has no email in Firebase")
                self.stdout.write(self.style.WARNING(f'  ⚠ {firebase_uid}: No email in Firebase'))
                continue
            
            # Check if user has active or trialing Stripe subscription
            subscription_status = stripe_subscriptions.get(email)
            
            if subscription_status:
                # User has active or trialing subscription - keep current status
                stats['kept_paid'] += 1
                
                if subscription_status == 'active':
                    stats['kept_active'] += 1
                    logger.info(f"User {email} (UID: {firebase_uid}): Has ACTIVE subscription, keeping status {current_status}")
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {email}: Active subscription, status={current_status}'))
                elif subscription_status == 'trialing':
                    stats['kept_trialing'] += 1
                    logger.info(f"User {email} (UID: {firebase_uid}): Has TRIALING subscription, keeping status {current_status}")
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {email}: Trialing subscription, status={current_status}'))
                
            else:
                # User has NO active subscription
                if current_status == 'FREE':
                    # Already FREE
                    stats['already_free'] += 1
                    logger.info(f"User {email} (UID: {firebase_uid}): No subscription, already FREE")
                    self.stdout.write(f'  • {email}: No subscription, already FREE')
                else:
                    # Needs to be downgraded to FREE
                    stats['downgraded_to_free'] += 1
                    logger.warning(f"User {email} (UID: {firebase_uid}): No subscription, changing {current_status} → FREE")
                    self.stdout.write(self.style.ERROR(f'  ✗ {email}: No subscription, {current_status} → FREE'))
                    
                    if not dry_run:
                        try:
                            old_status = profile.status
                            profile.status = 'FREE'
                            profile.save(update_fields=['status'])
                            logger.info(f"Updated user {email} from {old_status} to FREE")
                        except Exception as e:
                            stats['errors'] += 1
                            logger.error(f"Error updating user {email}: {str(e)}")
                            self.stdout.write(self.style.ERROR(f'    Error updating: {str(e)}'))
        
        return stats

    def print_summary(self, stats, stripe_subscriptions, user_data, dry_run):
        """Print summary of the audit"""
        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS('AUDIT SUMMARY'))
        self.stdout.write('═' * 60)
        
        active_count = sum(1 for status in stripe_subscriptions.values() if status == 'active')
        trialing_count = sum(1 for status in stripe_subscriptions.values() if status == 'trialing')
        
        self.stdout.write(f'\nStripe Statistics:')
        self.stdout.write(f'  • Total subscriptions in Stripe: {len(stripe_subscriptions)}')
        self.stdout.write(f'    - Active: {active_count}')
        self.stdout.write(f'    - Trialing: {trialing_count}')
        
        self.stdout.write(f'\nDatabase Statistics:')
        self.stdout.write(f'  • Total users in database: {len(user_data)}')
        
        self.stdout.write(f'\nSync Results:')
        self.stdout.write(self.style.SUCCESS(f'  ✓ Users with valid subscriptions (kept): {stats["kept_paid"]}'))
        self.stdout.write(f'    - Active subscriptions: {stats["kept_active"]}')
        self.stdout.write(f'    - Trialing subscriptions: {stats["kept_trialing"]}')
        self.stdout.write(f'  • Users already FREE: {stats["already_free"]}')
        
        if stats['downgraded_to_free'] > 0:
            status_msg = f'  ✗ Users downgraded to FREE: {stats["downgraded_to_free"]}'
            if dry_run:
                self.stdout.write(self.style.WARNING(status_msg + ' (would be changed)'))
            else:
                self.stdout.write(self.style.ERROR(status_msg + ' (changed)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  ✓ No downgrades needed'))
        
        if stats['no_email'] > 0:
            self.stdout.write(self.style.WARNING(f'  ⚠ Users without email: {stats["no_email"]}'))
        
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f'  ✗ Errors: {stats["errors"]}'))
        
        self.stdout.write('\n' + '═' * 60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN MODE - No changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('\nAudit completed successfully!'))
        
        logger.info(f"""
            Audit completed:
            - Total Stripe subscriptions: {len(stripe_subscriptions)} ({active_count} active + {trialing_count} trialing)
            - Total users checked: {len(user_data)}
            - Kept paid: {stats['kept_paid']} (active: {stats['kept_active']}, trialing: {stats['kept_trialing']})
            - Downgraded to FREE: {stats['downgraded_to_free']}
            - Already FREE: {stats['already_free']}
            - No email: {stats['no_email']}
            - Errors: {stats['errors']}
            - Mode: {'DRY RUN' if dry_run else 'LIVE'}
        """)
