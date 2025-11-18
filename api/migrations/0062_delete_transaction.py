from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0061_migrate_transactions'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Transaction',
        ),
    ] 