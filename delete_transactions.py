import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')
django.setup()

from api.models import Transaction

transactions = Transaction.objects.filter(created_at__date=timezone.now().date())
print(f"Found {transactions.count()} transactions today")
for t in transactions:
    print(f"Transaction ID: {t.id}, Created at: {t.created_at}, Status: {t.status}")

delete_count, _ = transactions.delete()
print(f"Deleted {delete_count} transactions") 