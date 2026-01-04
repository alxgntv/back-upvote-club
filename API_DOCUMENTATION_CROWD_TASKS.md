# API Documentation: Crowd Tasks (Simplified)

## Overview
- Crowd задачи вынесены в отдельный поток: создание через `create-crowd-task`, простые шаги апрува.
- Автопроверки комментариев убраны. Исполнитель прикладывает ссылку → задача ждёт апрува → заказчик подтверждает → награда начисляется.
- `PENDING_REVIEW` видит только пользователь, который перевёл задачу в этот статус (`assigned_to`). Заказчик видит все свои Crowd задачи.

## Endpoints (JWT)
- `POST /api/create-crowd-task/` — создаёт `Task` c `task_type='CROWD'`, `actions_required=1` и один `CrowdTask`. Поля: `social_network_code`, `post_url`, `price` (≥100), `text`; опционально `type` (по умолчанию `COMMENT`).
- `GET /api/crowd-tasks/` — список доступных Crowd задач (активные, не свои; `PENDING_REVIEW` только для `assigned_to`).
- `POST /api/crowd-tasks/<id>/save-comment-url/` — шаг 1: сохранить ссылку, проставить `PENDING_REVIEW` и `assigned_to`, уведомить заказчика (email) и админа (Telegram). Ответ исполнителю: ждём апрува.
- `POST /api/crowd-tasks/<id>/verify-comment-step2/` — шаг 2 без авто-проверок, просто фиксирует ожидание апрува.
- `POST /api/crowd-tasks/<id>/confirm-comment/` — шаг 3: только создатель задачи; подтверждает, переводит `CrowdTask` в `COMPLETED`, начисляет награду исполнителю, отправляет ему email. Если все дочерние CrowdTask завершены — родительский Task тоже `COMPLETED`.
- Legacy: `POST /api/crowd-tasks/<id>/verify-comment/` ведёт себя как упрощённый шаг 2.

## Правила и валидации
- Цена Crowd: минимум 100 поинтов.
- `text` обязателен в `create-crowd-task`.
- `comment_url` должен содержать `reddit.com`.
- В отдельном Crowd эндпоинте `actions_required` фиксирован в 1.
- Награда исполнителю: `price / 2`, начисляется при подтверждении заказчиком.

## Примеры

### Создание Crowd задачи
```json
POST /api/create-crowd-task/
Authorization: Bearer <token>
{
  "social_network_code": "REDDIT",
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/",
  "price": 120,
  "text": "Great post!",
  "type": "COMMENT"
}
```

### Сохранить ссылку (шаг 1)
```json
POST /api/crowd-tasks/123/save-comment-url/
Authorization: Bearer <token>
{
  "comment_url": "https://www.reddit.com/r/.../comment/xyz/"
}
```
Ответ: статус `pending_review`, сообщение об ожидании апрува.

### Подтвердить (шаг 3, заказчик)
```json
POST /api/crowd-tasks/123/confirm-comment/
Authorization: Bearer <creator_token>
{}
```
Ответ: `{ "success": true, "message": "Comment approved. Bounty credited.", "bounty_amount": <points> }`

## Публичное API
Не менялось: для упрощённого создания через публичное API используйте `/api/public-api/create-crowd-task/` (те же требования: цена ≥100, text обязателен).

## Статусы CrowdTask
- `SEARCHING` — создано, ждём ссылку.
- `PENDING_REVIEW` — ссылка сохранена, ждём апрува заказчика (assigned_to = исполнитель).
- `COMPLETED` — заказчик подтвердил, награда выдана.

