import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from api.models import PaymentTransaction
from api.utils.email_utils import get_firebase_email
from django.db.models import Sum
from collections import defaultdict
from django.contrib.auth.models import User
from firebase_admin import auth
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends follow-up notifications to users with pending payment transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=5,
            help='Максимальное количество писем для отправки за один запуск'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Задержка в секундах между отправками писем'
        )

    def handle(self, *args, **options):
        try:
            batch_size = options['batch_size']
            delay = options['delay']
            
            logger.info(f"[PendingPaymentNotification] Starting follow-up notifications (batch size: {batch_size}, delay: {delay}s)")
            
            now = timezone.now()
            
            # Определяем интервалы для отправки follow-up писем
            intervals = [
                {
                    'hours': 24,
                    'tolerance': 2,  # ±2 часа
                    'subject': 'Complete your subscription – 50% discount still available!',
                    'description': 'Follow-up emails sent 24h after payment attempt',
                    'email_text': 'You started your subscription process but didn\'t complete it. Don\'t miss out on our amazing features! Complete your subscription now and get 50% off with code 🎁 NEW50!'
                },
                {
                    'hours': 72,  # 3 дня
                    'tolerance': 4,  # ±4 часа
                    'subject': 'Don\'t miss out – your subscription is waiting!',
                    'description': 'Follow-up emails sent 3 days after payment attempt',
                    'email_text': 'Your subscription is still waiting for you! We\'ve saved your spot and the 50% discount is still active. Use code 🎁 NEW50 to complete your payment and unlock unlimited tasks!'
                },
                {
                    'hours': 168,  # 7 дней (1 неделя)
                    'tolerance': 6,  # ±6 часов
                    'subject': 'Last chance: complete your subscription now!',
                    'description': 'Follow-up emails sent 1 week after payment attempt',
                    'email_text': 'This is your last chance! Your subscription is about to expire. Complete it now with code 🎁 NEW50 and get 50% off. Don\'t let this opportunity slip away!'
                },
                {
                    'hours': 336,  # 14 дней (2 недели)
                    'tolerance': 12,  # ±12 часов
                    'subject': 'Your subscription is still pending – complete it today!',
                    'description': 'Follow-up emails sent 2 weeks after payment attempt',
                    'email_text': 'We noticed you haven\'t completed your subscription yet. Your account is still waiting for activation. Complete it today with code 🎁 NEW50 and start growing your audience!'
                },
                {
                    'hours': 720,  # 30 дней (1 месяц)
                    'tolerance': 24,  # ±24 часа
                    'subject': 'Final reminder: complete your subscription!',
                    'description': 'Follow-up emails sent 1 month after payment attempt',
                    'email_text': 'This is our final reminder! Your subscription has been pending for a month. Complete it now with code 🎁 NEW50 and join thousands of successful creators who are growing their audience with Upvote.Club!'
                }
            ]
            
            total_sent = 0
            
            for interval in intervals:
                hours = interval['hours']
                tolerance = interval['tolerance']
                subject = interval['subject']
                description = interval['description']
                email_text_template = interval['email_text']
                
                logger.info(f"Processing {hours}h interval with ±{tolerance}h tolerance")
                
                # Вычисляем временной диапазон
                target_time = now - timedelta(hours=hours)
                time_range_start = target_time - timedelta(hours=tolerance)
                time_range_end = target_time + timedelta(hours=tolerance)
                
                # Получаем pending транзакции в этом временном диапазоне
                pending_transactions = PaymentTransaction.objects.filter(
                    status='PENDING',
                    created_at__gte=time_range_start,
                    created_at__lte=time_range_end,
                    stripe_session_id__isnull=False
                ).select_related('user').order_by('user', 'created_at')
                
                # Группируем транзакции по пользователям и берем только самую старую транзакцию для каждого пользователя
                user_transactions = {}
                for transaction in pending_transactions:
                    if transaction.user not in user_transactions:
                        user_transactions[transaction.user] = transaction
                
                task_count = len(user_transactions)
                logger.info(f"Found {task_count} users with pending transactions around {hours}h ago")
                
                if task_count == 0:
                    logger.info(f"No pending transactions found for {hours}h follow-up emails")
                    continue
                
                success_count = 0
                failed_count = 0
                
                # Обрабатываем пользователей батчами
                all_users = list(user_transactions.keys())
                processed_users = 0
                
                while processed_users < len(all_users):
                    # Определяем текущий батч пользователей
                    current_batch = all_users[processed_users:processed_users + batch_size]
                    
                    for i, user in enumerate(current_batch):
                        transaction = user_transactions[user]  # Теперь это одна транзакция, а не список
                        try:
                            logger.info(f"Sending {hours}h follow-up email for user {user.username}")
                            
                            # Получаем email пользователя из Firebase
                            user_email = get_firebase_email(user.username)
                            
                            if not user_email:
                                # Пробуем получить email из профиля пользователя, если он есть
                                try:
                                    from api.models import UserProfile
                                    profile = UserProfile.objects.filter(user=user).first()
                                    if profile and profile.email:
                                        user_email = profile.email
                                        logger.info(f"[PendingPaymentNotification] Using email from UserProfile for user {user.username}: {user_email}")
                                except Exception as e:
                                    logger.error(f"[PendingPaymentNotification] Error getting email from profile: {str(e)}")
                                
                                # Если у нас все еще нет email, но есть email в транзакции
                                if not user_email:
                                    if hasattr(transaction, 'email') and transaction.email:
                                        user_email = transaction.email
                                        logger.info(f"[PendingPaymentNotification] Using email from transaction for user {user.username}: {user_email}")
                            
                            if not user_email:
                                logger.error(f"Could not get email for user {user.username}")
                                failed_count += 1
                                continue
                            
                            # Получаем данные пользователя из Firebase и его имя
                            user_name = "dear user"
                            try:
                                firebase_user = auth.get_user(user.username)
                                if firebase_user.display_name:
                                    user_name = firebase_user.display_name
                            except Exception as e:
                                logger.error(f"Error getting display_name: {e}")
                            
                            # Формируем текст письма с именем пользователя и соответствующим текстом для интервала
                            email_text = f"""Hello {user_name}! This is the Upvote.Club team.
                            
{email_text_template}

Here is the link to complete your subscription: https://upvote.club/dashboard/subscribe

Best regards,
Upvote.Club Team"""

                            # Отправляем письмо
                            send_mail(
                                subject=subject,
                                message=email_text,
                                from_email=f"🧗‍♀️ Upvote Club <{settings.DEFAULT_FROM_EMAIL}>",
                                recipient_list=[user_email],
                                fail_silently=False,
                            )
                            
                            success_count += 1
                            logger.info(f"Successfully sent {hours}h follow-up email for user {user.username}")
                            self.stdout.write(f"✓ Sent {hours}h follow-up email for user {user.username}")
                            
                            # Добавляем задержку между отправками (кроме последней в батче)
                            if i < len(current_batch) - 1 and delay > 0:
                                logger.info(f"[PendingPaymentNotification] Waiting {delay}s before next email")
                                time.sleep(delay)
                            
                        except Exception as e:
                            failed_count += 1
                            logger.error(f"Error processing user {user.username}: {str(e)}")
                            self.stdout.write(self.style.ERROR(f"Error processing user {user.username}: {str(e)}"))
                    
                    # Увеличиваем счетчик обработанных пользователей
                    processed_users += len(current_batch)
                
                interval_summary = f"""
                {hours}h follow-up emails completed:
                Total users: {task_count}
                Successfully sent: {success_count}
                Failed: {failed_count}
                """
                
                logger.info(interval_summary)
                self.stdout.write(self.style.SUCCESS(interval_summary))
                total_sent += success_count
            
            final_summary = f"""
            All pending payment follow-up emails completed:
            Total emails sent: {total_sent}
            """
            
            logger.info(final_summary)
            self.stdout.write(self.style.SUCCESS(final_summary))
            
        except Exception as e:
            logger.error(f"[PendingPaymentNotification] General error: {str(e)}") 