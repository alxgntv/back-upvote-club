from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Task, UserProfile, TaskReport, EmailSubscriptionType, UserEmailSubscription
from api.utils.email_utils import get_firebase_email
from api.email_service import EmailService
from django.db.models import Count

class Command(BaseCommand):
    help = 'Sets tasks to DELETED status if they have 2 or more reports with reason not_available, returns points and slot, and sends an email.'

    def handle(self, *args, **options):
        self.stdout.write('[INFO] Starting command to delete tasks with not_available reports')

        # Get tasks that have 2 or more reports with reason 'not_available'
        reported_tasks = (
            TaskReport.objects
            .filter(reason='not_available')
            .values('task')
            .annotate(report_count=Count('id'))
            .filter(report_count__gte=2)
        )
        task_ids = [item['task'] for item in reported_tasks]
        self.stdout.write(f'[INFO] Found {len(task_ids)} tasks to process')

        # Retrieve or create the subscription type for this notification
        subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
            name='task_link_unavailable',
            defaults={'description': 'Notifications about tasks deleted due to unavailable link'}
        )

        processed = 0
        for task_id in task_ids:
            try:
                task = Task.objects.get(id=task_id)
                if task.status != 'ACTIVE':
                    continue
                profile = UserProfile.objects.get(user=task.creator)
                actions_completed = task.actions_completed
                actions_required = task.actions_required
                price = task.price
                refund = max(0, (actions_required - actions_completed) * price)
                old_balance = profile.balance
                old_available_tasks = profile.available_tasks

                # Set task to DELETED status
                task.status = 'DELETED'
                task.deletion_reason = 'LINK_UNAVAILABLE'
                task.save(update_fields=['status', 'deletion_reason'])

                # Refund balance
                if refund > 0:
                    profile.balance += refund

                # Return task slot
                profile.available_tasks += 1
                profile.save(update_fields=['balance', 'available_tasks'])

                # Get email from Firebase
                email = get_firebase_email(task.creator.username)
                if not email:
                    continue

                # Check subscription
                subscription, _ = UserEmailSubscription.objects.get_or_create(
                    user=task.creator,
                    subscription_type=subscription_type,
                    defaults={'is_subscribed': True}
                )
                if not subscription.is_subscribed:
                    continue

                unsubscribe_url = f"https://upvote.club/api/unsubscribe/{subscription.unsubscribe_token}/"

                # Get human-readable action type and social network
                action_type_display = task.get_type_display()
                social_name = task.social_network.name if task.social_network else 'Social Network'

                subject = (
                    f'Your {social_name} task was deleted due to unavailable link and +{refund} points are back '
                    f'and you received {actions_completed} {action_type_display.lower()}(s) from the UpvoteClub community'
                )
                html_content = (
                    f"<p>Hello dear user! Your {social_name} task was deleted due to unavailable link.</b>."
                    f"<p>Please, check your link and create a new task again <a href='https://upvote.club/dashboard/createtask?linkunavailable'>here</a>.</p>"
                    f"<p>Upvote Club</p>"
                )
                try:
                    email_service = EmailService()
                    result = email_service.send_email(
                        to_email=email,
                        subject=subject,
                        html_content=html_content,
                        unsubscribe_url=unsubscribe_url
                    )
                    # No chat logging
                except Exception as e:
                    pass  # No chat logging

                self.stdout.write(self.style.SUCCESS(f"Task {task.id} deleted, user {profile.user.username} notified, refund: {refund}"))
                processed += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing task {task_id}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f'[delete_tasks_with_not_available_reports] Completed. Processed: {processed}'))