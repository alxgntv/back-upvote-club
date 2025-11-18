from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def migrate_transactions(apps, schema_editor):
    Transaction = apps.get_model('api', 'Transaction')
    PaymentTransaction = apps.get_model('api', 'PaymentTransaction')
    
    for old_transaction in Transaction.objects.all():
        try:
            # Создаем новую транзакцию на основе старой
            PaymentTransaction.objects.create(
                user=old_transaction.user,
                points=old_transaction.amount,  # В старой модели amount использовался как points
                amount=old_transaction.amount,  # Устанавливаем такое же значение
                payment_id=f"migrated_{old_transaction.id}",
                status='COMPLETED' if old_transaction.status == 'COMPLETED' else 'FAILED',
                payment_type='ONE_TIME',
                stripe_session_id=old_transaction.stripe_session_id if hasattr(old_transaction, 'stripe_session_id') else None,
                created_at=old_transaction.created_at
            )
            logger.info(f"Successfully migrated transaction {old_transaction.id}")
        except Exception as e:
            logger.error(f"Error migrating transaction {old_transaction.id}: {str(e)}")

def reverse_migrate(apps, schema_editor):
    PaymentTransaction = apps.get_model('api', 'PaymentTransaction')
    PaymentTransaction.objects.filter(payment_id__startswith='migrated_').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0060_paymenttransaction_attempt_count_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_transactions, reverse_migrate),
    ] 