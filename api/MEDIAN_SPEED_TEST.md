# Тест для API медианной скорости выполнения заданий

## Тестирование через curl

### 1. Тест с корректными параметрами
```bash
curl "http://localhost:8000/api/median-speed/?social_network=TWITTER&action=LIKE&actions_count=10"
```

### 2. Тест с отсутствующими параметрами
```bash
curl "http://localhost:8000/api/median-speed/?social_network=TWITTER"
```

### 3. Тест с несуществующей социальной сетью
```bash
curl "http://localhost:8000/api/median-speed/?social_network=INVALID&action=LIKE&actions_count=10"
```

### 4. Тест с несуществующим типом действия
```bash
curl "http://localhost:8000/api/median-speed/?social_network=TWITTER&action=INVALID&actions_count=10"
```

### 5. Тест с некорректным количеством действий
```bash
curl "http://localhost:8000/api/median-speed/?social_network=TWITTER&action=LIKE&actions_count=abc"
```

## Ожидаемые результаты

### Успешный ответ (200)
```json
{
    "social_network": "TWITTER",
    "action": "LIKE", 
    "actions_count": 10,
    "median_speed_minutes": 45.5,
    "cached_at": "2024-01-15T10:30:00Z",
    "cache_expires_in": "24 hours"
}
```

### Ошибка валидации (400)
```json
{
    "error": "action parameter is required"
}
```

### Ошибка не найден (404)
```json
{
    "error": "Social network INVALID not found"
}
```

## Проверка кэширования

1. Выполните запрос первый раз - должен вернуть результат с вычислением
2. Выполните тот же запрос повторно - должен вернуть закэшированный результат
3. Проверьте логи - второй запрос должен содержать сообщение "Returning cached median speed"

## Проверка логики fallback

1. Запросите комбинацию, которой нет в базе данных
2. API должен вернуть медианную скорость по социальной сети
3. В логах должно быть сообщение "No exact matches... calculating average for social network"
