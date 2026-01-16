# ProductHunt Campaign - Simple Implementation

## Как работает

### 1. Автоматическая отправка через сигнал

При создании ProductHunt задания автоматически отправляются письма всем пользователям с подтвержденным ProductHunt.

**Условия срабатывания:**
- Новое задание (`created=True`)
- Соцсеть = ProductHunt
- Статус = ACTIVE
- Письмо еще не отправлено (`promo_email_sent=False`)

**Что происходит:**
1. Сигнал `send_producthunt_promo_email` в `api/signals.py` срабатывает
2. Вызывается функция `send_producthunt_campaign_emails(task)` из `api/utils/email_utils.py`
3. Функция находит всех пользователей с `verification_status='VERIFIED'` для ProductHunt
4. Пропускает:
   - Автора задания
   - Тех, кто уже выполнил это задание
   - Тех, кто отписался от `new_task` уведомлений
5. Отправляет письма всем остальным (с задержкой 1 сек между письмами)
6. Устанавливает `task.promo_email_sent = True`

**Результат:** Письма отправляются **ОДИН РАЗ**, автоматически, без расписаний и команд.

---

## Изменения в коде

### 1. Новое поле в модели Task
**Файл:** `api/models.py`

```python
promo_email_sent = models.BooleanField(
    default=False,
    verbose_name='Promo email sent',
    help_text='Whether promotional campaign email was sent (for ProductHunt tasks)'
)
```

**Защита от дублей:** Если `promo_email_sent=True`, письма не отправятся повторно.

### 2. Функция отправки кампании
**Файл:** `api/utils/email_utils.py`

```python
def send_producthunt_campaign_emails(task):
    """
    Отправляет промо письма всем пользователям с подтвержденным ProductHunt
    Вызывается один раз при создании ProductHunt задания
    """
    # 1. Находит всех verified ProductHunt пользователей
    # 2. Пропускает автора, выполнивших, отписавшихся
    # 3. Отправляет письма
    # 4. Возвращает статистику
```

### 3. Сигнал post_save
**Файл:** `api/signals.py`

```python
@receiver(post_save, sender=Task)
def send_producthunt_promo_email(sender, instance, created, **kwargs):
    """
    Автоматически отправляет промо письма при создании ProductHunt задания
    """
    if (created and 
        instance.status == 'ACTIVE' and 
        not instance.promo_email_sent and
        instance.social_network.code == 'PRODUCTHUNT'):
        
        # Отправляем письма
        send_producthunt_campaign_emails(instance)
        
        # Устанавливаем флаг
        Task.objects.filter(pk=instance.pk).update(promo_email_sent=True)
```

### 4. Упрощенная команда (опциональная)
**Файл:** `api/management/commands/send_producthunt_campaign.py`

Для ручной отправки если нужно:
```bash
python manage.py send_producthunt_campaign --task-id=28500
```

Команда проверяет `promo_email_sent` и спрашивает подтверждение если уже отправлялось.

---

## Что нужно сделать

### 1. Создать и применить миграцию

```bash
cd back-upvote-club
python manage.py makemigrations
python manage.py migrate
```

### 2. Тестирование

#### Вариант А: Создать тестовое ProductHunt задание

Просто создайте ProductHunt задание со статусом ACTIVE через админку или API:
- Письма отправятся **автоматически**
- Проверьте логи: увидите статистику отправки
- Проверьте `task.promo_email_sent = True`

#### Вариант Б: Ручная отправка для существующего задания

```bash
python manage.py send_producthunt_campaign --task-id=TASK_ID
```

---

## Защиты

### 1. От повторной отправки
✅ Флаг `promo_email_sent` - если `True`, письма не отправятся

### 2. От отправки автору
✅ Пропускает `user.id == task.creator.id`

### 3. От отправки тем, кто уже выполнил
✅ Проверяет `task.taskcompletion_set.filter(user=user).exists()`

### 4. От отправки отписавшимся
✅ Проверяет `UserEmailSubscription` для типа `new_task`

### 5. От дублей при нескольких профилях
✅ Использует `.distinct('user')` при выборке профилей

### 6. От циклических зависимостей
✅ Локальные импорты в `send_producthunt_campaign_emails`
✅ Использует `Task.objects.filter().update()` вместо `task.save()` для установки флага

---

## Логи

Все действия логируются:

```
[INFO] New ProductHunt task 28500 created with ACTIVE status - will send promo emails
[INFO] Starting ProductHunt campaign for task 28500
[INFO] Found 150 users with verified ProductHunt profiles
[INFO] Skipping task creator: john_doe
[INFO] User alice unsubscribed from new_task emails
[INFO] Sent ProductHunt campaign email to bob
[INFO] ProductHunt campaign completed for task 28500:
       Total users: 150
       Sent: 145
       Failed: 2
       Skipped: 3
```

---

## Преимущества решения

✅ **Простота:** Нет сложных моделей, нет расписаний, нет команд  
✅ **Автоматизация:** Создал задание → письма отправились  
✅ **Один раз:** Защита от дублей через флаг  
✅ **Гибкость:** Можно отправить вручную через команду если нужно  
✅ **Безопасность:** Множественные проверки и защиты  
✅ **Прозрачность:** Полное логирование всех действий  

---

## Готово к использованию!

После миграции система готова. Просто создавайте ProductHunt задания и письма будут отправляться автоматически.
