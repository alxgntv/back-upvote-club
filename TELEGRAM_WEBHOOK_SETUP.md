# Настройка Telegram Webhook для модерации профилей

## Что было добавлено

1. **Новое поле в модели UserSocialProfile:**
   - `rejection_reason` - причина отклонения профиля (NO_EMOJI, DOES_NOT_MEET_CRITERIA)

2. **Telegram webhook endpoint:**
   - URL: `/api/telegram/webhook/`
   - Обрабатывает нажатия кнопок модерации

3. **Кнопки в Telegram сообщениях:**
   - ✅ Verify - верифицирует профиль
   - ❌ Reject - No Emoji - отклоняет из-за отсутствия эмоджи
   - ❌ Reject - Does not meet criteria - отклоняет из-за несоответствия критериям

4. **Разные email шаблоны:**
   - Для верификации: стандартное письмо об одобрении
   - Для отклонения "No Emoji": инструкции по добавлению эмоджи
   - Для отклонения "Does not meet criteria": объяснение критериев

## Настройка Telegram Bot

1. **Установите webhook для вашего бота:**
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://yourdomain.com/api/telegram/webhook/"}'
```

2. **Проверьте webhook:**
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

## Как это работает

1. Пользователь отправляет профиль на верификацию через `/api/verify-social-profile/`
2. В Telegram приходит сообщение с 3 кнопками
3. При нажатии кнопки:
   - Обновляется статус профиля в базе данных
   - Отправляется соответствующий email пользователю
   - В Telegram приходит подтверждение действия

## Миграция

Не забудьте применить миграцию:
```bash
python manage.py migrate
```

## Тестирование

1. Отправьте профиль на верификацию
2. Проверьте, что в Telegram пришло сообщение с кнопками
3. Нажмите кнопку и проверьте:
   - Обновление статуса в админке Django
   - Отправку email пользователю
   - Ответ в Telegram
