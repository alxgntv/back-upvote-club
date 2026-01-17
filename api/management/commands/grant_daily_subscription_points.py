from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import UserProfile
from calendar import monthrange
import logging
import math

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Grant daily subscription points to BUDDY and MATE users based on their monthly allocation'

    def handle(self, *args, **options):
        now = timezone.now()
        current_year = now.year
        current_month = now.month
        
        days_in_month = monthrange(current_year, current_month)[1]
        
        buddy_daily_points = 250 / days_in_month
        mate_daily_points = 1000 / days_in_month
        
        logger.info(f"""
            Starting daily subscription points grant:
            Time: {now}
            Days in current month: {days_in_month}
            BUDDY daily allocation: {buddy_daily_points:.2f} points
            MATE daily allocation: {mate_daily_points:.2f} points
        """)
        
        try:
            buddy_users = UserProfile.objects.filter(status='BUDDY')
            mate_users = UserProfile.objects.filter(status='MATE')
            
            buddy_count = 0
            mate_count = 0
            
            for profile in buddy_users:
                old_balance = profile.balance
                points_to_add = math.ceil(buddy_daily_points)
                profile.balance += points_to_add
                profile.save(update_fields=['balance'])
                
                buddy_count += 1
                logger.info(f"""
                    Granted points to BUDDY user:
                    User ID: {profile.user.id}
                    Username: {profile.user.username}
                    Email: {profile.user.email}
                    Old balance: {old_balance}
                    Points added: {points_to_add}
                    New balance: {profile.balance}
                """)
            
            for profile in mate_users:
                old_balance = profile.balance
                points_to_add = math.ceil(mate_daily_points)
                profile.balance += points_to_add
                profile.save(update_fields=['balance'])
                
                mate_count += 1
                logger.info(f"""
                    Granted points to MATE user:
                    User ID: {profile.user.id}
                    Username: {profile.user.username}
                    Email: {profile.user.email}
                    Old balance: {old_balance}
                    Points added: {points_to_add}
                    New balance: {profile.balance}
                """)
            
            success_message = f"""
                Successfully granted daily subscription points:
                - BUDDY users: {buddy_count} users received {math.ceil(buddy_daily_points)} points each
                - MATE users: {mate_count} users received {math.ceil(mate_daily_points)} points each
                - Total users processed: {buddy_count + mate_count}
            """
            
            self.stdout.write(self.style.SUCCESS(success_message))
            logger.info(success_message)
            
        except Exception as e:
            error_msg = f"Error granting daily subscription points: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(error_msg))
