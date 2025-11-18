import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import PaymentTransaction

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Удаляет PaymentTransaction со статусом PENDING, которым больше 60 дней от текущей даты'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет удалено, но не удалять',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=60,
            help='Количество дней для определения старых транзакций (по умолчанию 60)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days = options['days']
        
        now = timezone.now()
        cutoff_date = now - timedelta(days=days)
        
        self.stdout.write(f"[INFO] Запуск команды удаления старых транзакций PENDING")
        self.stdout.write(f"[INFO] Cutoff date: {cutoff_date} (транзакции старше {days} дней)")
        logger.info(f"[delete_old_pending_transactions] Start. Cutoff date: {cutoff_date}, days: {days}")

        # Находим все транзакции PENDING старше cutoff_date
        old_transactions = PaymentTransaction.objects.filter(
            status='PENDING',
            created_at__lt=cutoff_date
        )
        
        total_count = old_transactions.count()
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS(f"[SUCCESS] Не найдено транзакций для удаления"))
            logger.info(f"[delete_old_pending_transactions] No transactions found to delete")
            return
        
        self.stdout.write(f"[INFO] Найдено {total_count} транзакций PENDING старше {days} дней")
        logger.info(f"[delete_old_pending_transactions] Found {total_count} transactions to delete")
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Следующие транзакции будут удалены:"))
            for transaction in old_transactions[:10]:  # Показываем первые 10
                self.stdout.write(
                    f"  - ID: {transaction.id}, User: {transaction.user.username}, "
                    f"Amount: ${transaction.amount}, Created: {transaction.created_at}"
                )
            if total_count > 10:
                self.stdout.write(f"  ... и еще {total_count - 10} транзакций")
            
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Для реального удаления запустите команду без --dry-run"))
            logger.info(f"[delete_old_pending_transactions] DRY RUN: {total_count} transactions would be deleted")
            return
        
        # Удаляем транзакции
        deleted_count = 0
        for transaction in old_transactions.iterator(chunk_size=100):
            try:
                transaction_id = transaction.id
                user_username = transaction.user.username
                amount = transaction.amount
                created_at = transaction.created_at
                
                transaction.delete()
                deleted_count += 1
                
                logger.info(
                    f"[delete_old_pending_transactions] Deleted transaction ID: {transaction_id}, "
                    f"User: {user_username}, Amount: ${amount}, Created: {created_at}"
                )
                
                if deleted_count % 100 == 0:
                    self.stdout.write(f"[INFO] Удалено {deleted_count}/{total_count} транзакций...")
                    
            except Exception as e:
                logger.error(
                    f"[delete_old_pending_transactions] Error deleting transaction {getattr(transaction, 'id', '?')}: {str(e)}"
                )
                self.stdout.write(
                    self.style.ERROR(f"Error deleting transaction {getattr(transaction, 'id', '?')}: {str(e)}")
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"[SUCCESS] Удалено {deleted_count} из {total_count} транзакций PENDING старше {days} дней"
            )
        )
        logger.info(
            f"[delete_old_pending_transactions] Completed. Deleted: {deleted_count} out of {total_count} transactions"
        )

