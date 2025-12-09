from .config.subscription_plans import get_plan_price_id, SUBSCRIPTION_PLANS
from django.conf import settings

SUBSCRIPTION_PLAN_CONFIG = {
    'FREE': {
        'stripe_price_id': None,
        'points_per_period': 0,
        'trial_days': 0,
        'daily_task_limit': 1,
        'initial_points': 13,
        'discount_rate': 0
    },
    'MEMBER': {
        'monthly': {
            'price_id': settings.STRIPE_MEMBER_MONTHLY_PRICE_ID,
            'points': 0
        },
        'annual': {
            'price_id': settings.STRIPE_MEMBER_ANNUAL_PRICE_ID,
            'points': 0
        },
        'trial_days': 7,
        'purchase_points_discount': 0,
        'create_task_discount': 0,
        'daily_task_limit': 1
    },
    'BUDDY': {
        'monthly': {
            'price_id': settings.STRIPE_BUDDY_MONTHLY_PRICE_ID,
            'points': 250
        },
        'annual': {
            'price_id': settings.STRIPE_BUDDY_ANNUAL_PRICE_ID,
            'points': 5000
        },
        'trial_days': 7,
        'purchase_points_discount': 20,
        'create_task_discount': 20,
        'daily_task_limit': 10
    },
    'MATE': {
        'monthly': {
            'price_id': settings.STRIPE_MATE_MONTHLY_PRICE_ID,
            'points': 1000
        },
        'annual': {
            'price_id': settings.STRIPE_MATE_ANNUAL_PRICE_ID,
            'points': 15000
        },
        'trial_days': 7,
        'purchase_points_discount': 40,
        'create_task_discount': 40,
        'daily_task_limit': 100000
    }
}

# Добавим также константы для типов периодов
SUBSCRIPTION_PERIODS = {
    'monthly': 'month',
    'annual': 'year'
}

# И константы для статусов транзакций
TRANSACTION_STATUSES = {
    'PENDING_PAYMENT': 'Pending Payment',
    'TRIAL_STARTED': 'Trial Started',
    'TRIAL_ENDED': 'Trial Ended',
    'PAID': 'Paid',
    'FAILED': 'Failed',
    'CANCELLED': 'Cancelled',
    'REFUNDED': 'Refunded'
} 

# --- Bonus actions config ---
# Список стран (ISO 3166-1 alpha-2), для которых при создании задания
# добавляются бонусные действия бесплатно для создателя
BONUS_ACTION_COUNTRIES = {
    # Северная Америка
    'US', 'CA',

    # Центральная Европа
    'AT', 'CH', 'DE', 'LI', 'LU', 'PL', 'CZ', 'HU', 'SK', 'SI',

    # Западная Европа
    'FR', 'BE', 'NL', 'IE',

    # UK countries (Великобритания полностью: England, Scotland, Wales, Northern Ireland)
    'GB', 'IM', 'JE', 'GG',

    # Северная Европа (ограничено основными странами из оригинала)
    'NO', 'SE', 'DK', 'FI', 'IS',

    # Южная Европа (по контексту, только основные страны западной/центральной европы)
    'IT', 'ES', 'PT',

    # Австралия, Новая Зеландия
    'AU', 'NZ',

    # Южная Корея, Япония, Сингапур, Гонконг
    'KR', 'JP', 'SG', 'HK'
}

# Процент дополнительных бонусных действий (0.3 = +30%)
BONUS_ACTION_RATE = 0.3