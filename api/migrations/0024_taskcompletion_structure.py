from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0023_socialnetwork_usersocialprofile_and_more'),
    ]

    operations = [
        # Восстанавливаем правильную структуру unique_together
        migrations.AlterUniqueTogether(
            name='taskcompletion',
            unique_together={('task', 'user', 'action')},
        ),
        
        # Добавляем новый оптимизированный индекс
        migrations.AddIndex(
            model_name='taskcompletion',
            index=models.Index(fields=['user', 'action'], name='tc_user_action_idx'),
        ),
    ]