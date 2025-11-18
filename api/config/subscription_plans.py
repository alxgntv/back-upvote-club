import logging
from django.conf import settings

logger = logging.getLogger(__name__)

SUBSCRIPTION_PLANS = {
    'FREE': {
        'stripe_price_id': {
            'monthly': None,
            'annually': None
        },
        'price': {
            'monthly': 0,
            'annually': 0
        },
        'features': {
            'initial_points': 23,
            'daily_task_limit': 5,
            'tasks_creation_discount': 0,
            'points_purchase_discount': 0,
            'daily_actions_limit': 5,
            'monthly_free_points': 0,
            'yearly_free_points': 0
        }
    },
    'MEMBER': {
        'stripe_price_id': {
            'monthly': 'price_1QDQguKSYevnzdasv3UJ2Ti2',  # $3.9/month
            'annually': 'price_1Qyz0FKSYevnzdasHbuJ7CqN'   # $29/year
        },
        'price': {
            'monthly': 3.9,
            'annually': 29
        },
        'features': {
            'initial_points': 0,
            'daily_task_limit': 1,
            'tasks_creation_discount': 0,
            'points_purchase_discount': 0,
            'daily_actions_limit': float('inf'),  # Unlimited
            'monthly_free_points': 0,
            'yearly_free_points': 0,
            'trial_days': 7
        }
    },
    'BUDDY': {
        'stripe_price_id': {
            'monthly': 'price_1QFDG7KSYevnzdasmQSpS0Dw',  # $15/month
            'annually': 'price_1QFDHIKSYevnzdassXXxCmtA'   # $149/year
        },
        'price': {
            'monthly': 15,
            'annually': 149
        },
        'features': {
            'initial_points': 0,
            'daily_task_limit': 10,
            'tasks_creation_discount': 20,
            'points_purchase_discount': 20,
            'daily_actions_limit': float('inf'),  # Unlimited
            'monthly_free_points': 250,
            'yearly_free_points': 5000,
            'trial_days': 7
        }
    },
    'MATE': {
        'stripe_price_id': {
            'monthly': 'price_1QP2LSKSYevnzdasUIS2qsoN',  # $49/month
            'annually': 'price_1QP2VuKSYevnzdasQbR2OKU2'   # $439/year
        },
        'price': {
            'monthly': 49,
            'annually': 439
        },
        'features': {
            'initial_points': 0,
            'daily_task_limit': float('inf'),  # Unlimited
            'tasks_creation_discount': 40,
            'points_purchase_discount': 40,
            'daily_actions_limit': float('inf'),  # Unlimited
            'monthly_free_points': 1000,
            'yearly_free_points': 15000,
            'trial_days': 7,
            'unlimited_accounts': True
        }
    }
}

def get_plan_feature(plan_name: str, feature: str, period: str = None):
    """
    Получить значение конкретной характеристики плана
    """
    try:
        plan = SUBSCRIPTION_PLANS[plan_name.upper()]
        if period and feature in ['stripe_price_id', 'price']:
            return plan[feature][period]
        return plan['features'].get(feature)
    except (KeyError, TypeError) as e:
        logger.error(f"Error getting plan feature: {str(e)}")
        return None

def get_plan_price_id(plan_name: str, period: str = 'monthly'):
    """
    Получить Stripe Price ID для конкретного плана и периода
    """
    return get_plan_feature(plan_name, 'stripe_price_id', period)

def get_free_points_for_plan(plan_name: str, period: str = 'monthly'):
    """
    Получить количество бесплатных поинтов для плана
    """
    if period == 'annually':
        return SUBSCRIPTION_PLANS[plan_name]['features']['yearly_free_points']
    return SUBSCRIPTION_PLANS[plan_name]['features']['monthly_free_points'] 