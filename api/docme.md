# Документация по процессу регистрации и авторизации

## Общее описание

Система использует Firebase Authentication для аутентификации пользователей и JWT токены для авторизации API запросов. Процесс состоит из двух основных этапов:
1. Регистрация/авторизация через Firebase
2. Создание/обновление пользователя в Django и получение JWT токенов

## Процесс регистрации

### 1. Регистрация через Firebase

**Эндпоинт:** `POST /api/register/`

**Параметры запроса:**
```json
{
    "idToken": "string", // Firebase ID токен
    "task_data": {       // Опционально, данные для создания задачи
        "social_network_code": "string",
        "type": "string",
        "post_url": "string",
        "price": number,
        "actions_required": number
    },
    "country_code": "string", // Опционально, код страны
    "inviteCode": "string"    // Опционально, код приглашения
}
```

**Процесс регистрации:**

1. Верификация Firebase ID токена
2. Создание пользователя Django (если не существует)
3. Создание профиля пользователя (UserProfile) со следующими полями:
   - balance: 13 (начальный баланс)
   - status: 'FREE'
   - country_code: из запроса или заголовка x-vercel-ip-country
   - invite_code: если предоставлен код приглашения
   - invited_by: пользователь, создавший код приглашения

4. Создание безлимитного инвайт-кода для нового пользователя
5. Если предоставлены task_data, создание задачи
6. Генерация JWT токенов

**Ответ:**
```json
{
    "refresh": "string", // JWT refresh токен
    "access": "string",  // JWT access токен
    "is_new_user": boolean,
    "has_task": boolean
}
```

### 2. Обработка инвайт-кода

Если при регистрации предоставлен инвайт-код:
1. Проверка валидности кода
2. Увеличение баланса на 30 поинтов для обоих пользователей
3. Связывание пользователей через invited_by
4. Увеличение счетчика использований кода

## Процесс авторизации

### 1. Авторизация через Firebase

**Эндпоинт:** `POST /api/login/`

**Параметры запроса:**
```json
{
    "idToken": "string" // Firebase ID токен
}
```

**Процесс авторизации:**
1. Верификация Firebase ID токена
2. Получение или создание пользователя Django
3. Генерация JWT токенов

**Ответ:**
```json
{
    "refresh": "string", // JWT refresh токен
    "access": "string"   // JWT access токен
}
```

### 2. Обновление токенов

**Эндпоинт:** `POST /api/refresh-token/`

**Параметры запроса:**
```json
{
    "idToken": "string" // Firebase ID токен
}
```

**Процесс обновления:**
1. Верификация Firebase ID токена
2. Поиск пользователя по Firebase UID
3. Генерация новых JWT токенов

**Ответ:**
```json
{
    "refresh": "string", // Новый JWT refresh токен
    "access": "string"   // Новый JWT access токен
}
```

## Модели данных

### UserProfile
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    twitter_account = models.CharField(max_length=255, null=True, blank=True)
    balance = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=[
        ('FREE', 'Free'),
        ('MEMBER', 'Member'),
        ('BUDDY', 'Buddy'),
        ('MATE', 'Mate')
    ], default='FREE')
    country_code = models.CharField(max_length=10, null=True, blank=True)
    invite_code = models.ForeignKey('InviteCode', null=True, blank=True)
    available_invites = models.IntegerField(default=2)
    invited_by = models.ForeignKey(User, null=True, blank=True)
```

### InviteCode
```python
class InviteCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=10, choices=[
        ('ACTIVE', 'Active'),
        ('USED', 'Used')
    ], default='ACTIVE')
    creator = models.ForeignKey(User)
    used_by = models.ManyToManyField(User)
    max_uses = models.IntegerField(default=2)
    uses_count = models.IntegerField(default=0)
```

## Безопасность

1. Все эндпоинты аутентификации требуют валидный Firebase ID токен
2. JWT токены имеют ограниченный срок действия
3. Refresh токены могут быть инвалидированы
4. Все API запросы после авторизации требуют JWT токен в заголовке Authorization

## Логирование

Система ведет подробное логирование всех действий:
- Создание новых пользователей
- Использование инвайт-кодов
- Создание задач при регистрации
- Ошибки аутентификации

## Обработка ошибок

Основные ошибки:
- 400: Неверный формат данных или отсутствие обязательных полей
- 401: Невалидный токен
- 404: Пользователь не найден
- 500: Внутренние ошибки сервера

## Корнеркейсы

1. Повторная регистрация с тем же Firebase UID
2. Использование невалидного инвайт-кода
3. Попытка использовать свой собственный инвайт-код
4. Попытка использовать инвайт-код повторно
5. Отсутствие кода страны
6. Ошибки при создании задачи при регистрации

## Управление социальными профилями пользователя

### Создание одного социального профиля

**Эндпоинт:** `POST /api/social-profiles/`

**Описание:**
Позволяет пользователю добавить ссылку на свой профиль в выбранной социальной сети. После создания профиль получает статус "Pending Verification" (ожидает проверки) по умолчанию. Проверка и верификация профиля осуществляется вручную через админку.

**Требуется авторизация:** JWT access token в заголовке `Authorization: Bearer <token>`

**Формат запроса:**
```json
{
    "social_network_code": "TWITTER", // Код социальной сети (строго в верхнем регистре)
    "profile_url": "https://twitter.com/username" // Ссылка на профиль
}
```

**Пример успешного ответа:**
```json
{
    "id": 1,
    "user": {
        "id": 123,
        "username": "firebase_uid",
        "email": "user@email.com"
    },
    "social_network": {
        "id": 2,
        "name": "Twitter",
        "code": "TWITTER",
        "icon": "twitter",
        "is_active": true,
        "created_at": "2023-01-01T00:00:00Z"
    },
    "social_id": null,
    "username": "",
    "profile_url": "https://twitter.com/username",
    "avatar_url": null,
    "is_verified": false,
    "verification_status": "PENDING",
    "verification_date": null,
    "followers_count": 0,
    "following_count": 0,
    "posts_count": 0,
    "account_created_at": null,
    "created_at": "2024-06-01 12:00:00",
    "updated_at": "2024-06-01 12:00:00",
    "last_sync_at": null,
    "verification_status_display": "Pending Verification",
    "metrics": {
        "followers": 0,
        "following": 0,
        "posts": 0
    }
}
```

**Ошибки:**
- 400: Некорректный формат данных, невалидный код соцсети или ссылка
- 400: Профиль для этой соцсети уже существует
- 401: Нет авторизации
- 500: Внутренняя ошибка сервера

---

### Массовое создание социальных профилей

**Эндпоинт:** `POST /api/social-profiles/bulk_create/`

**Описание:**
Позволяет добавить сразу несколько социальных профилей одним запросом. Каждый профиль должен содержать только код соцсети и ссылку на профиль. Все профили создаются со статусом "Pending Verification".

**Требуется авторизация:** JWT access token в заголовке `Authorization: Bearer <token>`

**Формат запроса:**
```json
{
    "profiles": [
        {
            "social_network_code": "TWITTER",
            "profile_url": "https://twitter.com/username1"
        },
        {
            "social_network_code": "GITHUB",
            "profile_url": "https://github.com/username2"
        },
        {
            "social_network_code": "LINKEDIN",
            "profile_url": "https://linkedin.com/in/username3"
        }
    ]
}
```

**Пример успешного ответа:**
```json
{
    "created_profiles": [
        {
            "id": 1,
            "user": { ... },
            "social_network": { ... },
            "profile_url": "https://twitter.com/username1",
            "verification_status": "PENDING",
            ...
        },
        {
            "id": 2,
            "user": { ... },
            "social_network": { ... },
            "profile_url": "https://github.com/username2",
            "verification_status": "PENDING",
            ...
        }
    ],
    "errors": [
        {
            "social_network": "LINKEDIN",
            "error": "Profile for this social network already exists"
        }
    ]
}
```

**Ошибки:**
- 400: Некорректный формат данных, невалидный код соцсети или ссылка
- 400: Профиль для одной из соцсетей уже существует (ошибка будет только для конкретного профиля, остальные создадутся)
- 401: Нет авторизации
- 500: Внутренняя ошибка сервера

---

### Требования к данным от фронтенда
- Всегда передавайте только два поля для каждого профиля: `social_network_code` (строка, верхний регистр, например, "TWITTER") и `profile_url` (валидная ссылка на профиль).
- Не передавайте поля `username`, `verification_status`, `is_verified` и другие — они выставляются и заполняются на бэкенде автоматически.
- Для массового создания используйте массив объектов в поле `profiles`.
- Все текстовые сообщения и ошибки в API — на английском языке.

---

### Примеры UI (frontend)

**Добавление одного профиля:**
```javascript
await axios.post('/api/social-profiles/', {
    social_network_code: 'TWITTER',
    profile_url: 'https://twitter.com/username'
}, { headers: { Authorization: `Bearer ${token}` } })
```

**Массовое добавление профилей:**
```javascript
await axios.post('/api/social-profiles/bulk_create/', {
    profiles: [
        { social_network_code: 'TWITTER', profile_url: 'https://twitter.com/username1' },
        { social_network_code: 'GITHUB', profile_url: 'https://github.com/username2' }
    ]
}, { headers: { Authorization: `Bearer ${token}` } })
```

---

### Корнеркейсы
- Если профиль для выбранной соцсети уже существует — будет возвращена ошибка только для этой соцсети, остальные профили создадутся.
- Если передан невалидный код соцсети или ссылка — будет возвращена ошибка 400.
- Все профили создаются со статусом "Pending Verification" и требуют ручной проверки в админке.
- Если пользователь не авторизован — будет ошибка 401.

---

### Логирование
- Все действия по созданию профилей логируются в консоль и в системный лог.
- Все ошибки и невалидные запросы также логируются.