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
            
            # Step 1: Get all active subscriptions from Stripe
            self.stdout.write('Step 1: Fetching active subscriptions from Stripe...')
            active_stripe_emails = self.get_active_stripe_subscriptions()
            
            logger.info(f"Found {len(active_stripe_emails)} active subscriptions in Stripe")
            self.stdout.write(self.style.SUCCESS(f'✓ Found {len(active_stripe_emails)} active subscriptions in Stripe'))
            
            # Step 2: Get all users from database and their Firebase emails
            self.stdout.write('\nStep 2: Fetching users from database and Firebase...')
            user_data = self.get_users_with_firebase_emails()
            
            logger.info(f"Found {len(user_data)} users in database")
            self.stdout.write(self.style.SUCCESS(f'✓ Found {len(user_data)} users in database'))
            
            # Step 3: Compare and update
            self.stdout.write('\nStep 3: Comparing and updating user statuses...')
            stats = self.sync_user_statuses(user_data, active_stripe_emails, dry_run)
            
            # Step 4: Print summary
            self.print_summary(stats, active_stripe_emails, user_data, dry_run)
            
        except Exception as e:
            error_msg = f"Error during subscription audit: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(f'✗ {error_msg}'))

    def get_active_stripe_subscriptions(self):
        """Get all active subscriptions from Stripe and return set of emails"""
        active_emails = set()
        
        try:
            # Get all active subscriptions
            subscriptions = stripe.Subscription.list(
                status='active',
                limit=100
            )
            
            for subscription in subscriptions.auto_paging_iter():
                try:
                    customer_id = subscription.customer
                    customer = stripe.Customer.retrieve(customer_id)
                    email = customer.email
                    
                    if email:
                        active_emails.add(email.lower())
                        logger.info(f"Stripe active subscription: {email} (Customer: {customer_id})")
                    else:
                        logger.warning(f"Stripe subscription without email: Customer {customer_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing Stripe subscription {subscription.id}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error fetching Stripe subscriptions: {str(e)}")
            raise
            
        return active_emails

    def get_users_with_firebase_emails(self):
        """Get all users from database with their Firebase emails"""
        user_data = []
        
        users = User.objects.select_related('userprofile').all()
        
        for user in users:
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
                
        return user_data

    def sync_user_statuses(self, user_data, active_stripe_emails, dry_run):
        """Compare users with Stripe subscriptions and update statuses"""
        stats = {
            'kept_paid': 0,
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
            
            # Check if user has active Stripe subscription
            has_active_subscription = email in active_stripe_emails
            
            if has_active_subscription:
                # User has active subscription - keep current status
                stats['kept_paid'] += 1
                logger.info(f"User {email} (UID: {firebase_uid}): Has active subscription, keeping status {current_status}")
                self.stdout.write(self.style.SUCCESS(f'  ✓ {email}: Active subscription, status={current_status}'))
                
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

    def print_summary(self, stats, active_stripe_emails, user_data, dry_run):
        """Print summary of the audit"""
        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS('AUDIT SUMMARY'))
        self.stdout.write('═' * 60)
        
        self.stdout.write(f'\nStripe Statistics:')
        self.stdout.write(f'  • Active subscriptions in Stripe: {len(active_stripe_emails)}')
        
        self.stdout.write(f'\nDatabase Statistics:')
        self.stdout.write(f'  • Total users in database: {len(user_data)}')
        
        self.stdout.write(f'\nSync Results:')
        self.stdout.write(self.style.SUCCESS(f'  ✓ Users with active subscriptions (kept): {stats["kept_paid"]}'))
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
            - Active Stripe subscriptions: {len(active_stripe_emails)}
            - Total users: {len(user_data)}
            - Kept paid: {stats['kept_paid']}
            - Downgraded to FREE: {stats['downgraded_to_free']}
            - Already FREE: {stats['already_free']}
            - No email: {stats['no_email']}
            - Errors: {stats['errors']}
            - Mode: {'DRY RUN' if dry_run else 'LIVE'}
        """)
