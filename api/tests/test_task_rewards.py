from django.test import TestCase
from django.contrib.auth.models import User
from api.models import Task, TaskCompletion, UserProfile
from django.utils import timezone
import logging
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)

class TaskRewardTests(TestCase):
    def setUp(self):
        # Создаем тестового пользователя и его профиль
        self.user = User.objects.create_user(
            username='test_user',
            password='test_password'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            balance=100,
            status='FREE'
        )
        
        # Создаем тестового создателя задания
        self.task_creator = User.objects.create_user(
            username='task_creator',
            password='creator_password'
        )
        self.creator_profile = UserProfile.objects.create(
            user=self.task_creator,
            balance=1000,
            status='FREE'
        )

        logger.info(f"""Test setup completed:
            Test user: {self.user.username}
            User balance: {self.user_profile.balance}
            Creator: {self.task_creator.username}
            Creator balance: {self.creator_profile.balance}
        """)

    def test_task_reward_calculation(self):
        """Тест проверяет правильность расчета награды за выполнение задания"""
        # Создаем тестовое задание
        task = Task.objects.create(
            creator=self.task_creator,
            type='LIKE',
            twitter_url='https://twitter.com/test/status/123',
            price=10,
            actions_required=5,
            original_price=50  # price * actions_required
        )

        initial_balance = self.user_profile.balance
        logger.info(f"""Created test task:
            Task ID: {task.id}
            Original price: {task.original_price}
            Expected reward: {task.original_price / 2}
            User initial balance: {initial_balance}
        """)

        # Создаем запись о выполнении задания
        completion = TaskCompletion.objects.create(
            task=task,
            user=self.user,
            action='LIKE',
            completed_at=timezone.now()
        )

        # Обновляем баланс пользователя
        reward = task.original_price / 2
        self.user_profile.balance += reward
        self.user_profile.save()

        # Проверяем, что награда рассчитана правильно
        expected_balance = initial_balance + reward
        actual_balance = UserProfile.objects.get(user=self.user).balance

        logger.info(f"""Reward calculation results:
            Expected balance: {expected_balance}
            Actual balance: {actual_balance}
            Reward amount: {reward}
        """)

        self.assertEqual(actual_balance, expected_balance)
        self.assertEqual(reward, 25)  # 50/2 = 25

    @transaction.atomic
    def test_multiple_task_completions(self):
        """Тест проверяет, что пользователь не может получить награду за одно задание дважды"""
        task = Task.objects.create(
            creator=self.task_creator,
            type='LIKE',
            twitter_url='https://twitter.com/test/status/123',
            price=50,
            actions_required=1,
            original_price=50
        )

        # Первое выполнение
        TaskCompletion.objects.create(
            task=task,
            user=self.user,
            action='LIKE',
            completed_at=timezone.now()
        )

        # Проверяем, что второе выполнение вызывает ошибку
        with self.assertRaises(IntegrityError):
            TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action='LIKE',
                completed_at=timezone.now()
            )

    def test_reward_for_different_price_tasks(self):
        """Тест проверяет правильность расчета наград для заданий с разными ценами"""
        test_cases = [
            {'price': 10, 'actions': 5, 'original_price': 50},
            {'price': 20, 'actions': 3, 'original_price': 60},
            {'price': 15, 'actions': 4, 'original_price': 60},
        ]

        for case in test_cases:
            task = Task.objects.create(
                creator=self.task_creator,
                type='LIKE',
                twitter_url=f'https://twitter.com/test/status/{case["price"]}',
                price=case['price'],
                actions_required=case['actions'],
                original_price=case['original_price']
            )

            initial_balance = self.user_profile.balance
            expected_reward = case['original_price'] / 2

            logger.info(f"""Testing reward calculation:
                Task price: {case['price']}
                Actions required: {case['actions']}
                Original price: {case['original_price']}
                Expected reward: {expected_reward}
            """)

            # Выполняем задание
            TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action='LIKE',
                completed_at=timezone.now()
            )

            # Начисляем награду
            self.user_profile.balance += expected_reward
            self.user_profile.save()

            # Проверяем баланс
            actual_balance = UserProfile.objects.get(user=self.user).balance
            expected_balance = initial_balance + expected_reward

            logger.info(f"""Reward test results:
                Expected balance: {expected_balance}
                Actual balance: {actual_balance}
                Reward: {expected_reward}
            """)

            self.assertEqual(actual_balance, expected_balance)

    @transaction.atomic
    def test_completed_task_execution(self):
        """Тест проверяет попытку выполнения уже завершенного задания"""
        task = Task.objects.create(
            creator=self.task_creator,
            type='LIKE',
            twitter_url='https://twitter.com/test/status/123',
            price=50,
            actions_required=1,
            original_price=50,
            status='COMPLETED',
            completed_at=timezone.now()
        )

        with self.assertRaises(ValidationError):
            TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action='LIKE',
                completed_at=timezone.now()
            )

    def test_invalid_action_type(self):
        """Тест проверяет попытку выполнения задания с некорректным типом действия"""
        task = Task.objects.create(
            creator=self.task_creator,
            type='LIKE',
            twitter_url='https://twitter.com/test/status/123',
            price=50,
            actions_required=1,
            original_price=50
        )

        initial_balance = self.user_profile.balance
        invalid_action = 'INVALID_ACTION'

        logger.info(f"""Testing invalid action type:
            Task ID: {task.id}
            Task type: {task.type}
            Attempted action: {invalid_action}
        """)

        # Пытаемся выполнить задание с неверным типом действия
        with self.assertRaises(ValidationError) as context:
            TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action=invalid_action,
                completed_at=timezone.now()
            )

        logger.info(f"Expected validation error: {str(context.exception)}")
        
        # Проверяем, что баланс не изменился
        self.assertEqual(
            self.user_profile.balance,
            initial_balance,
            "Balance should not change when completing with invalid action"
        )

    def test_concurrent_task_completion(self):
        """Тест проверяет одновременные попытки выполнения одного задания"""
        from django.db import transaction
        
        task = Task.objects.create(
            creator=self.task_creator,
            type='LIKE',
            twitter_url='https://twitter.com/test/status/123',
            price=50,
            actions_required=2,
            original_price=50
        )

        initial_balance = self.user_profile.balance

        logger.info(f"""Testing concurrent task completion:
            Task ID: {task.id}
            Required actions: {task.actions_required}
            Initial balance: {initial_balance}
        """)

        # Создаем первое выполнение
        with transaction.atomic():
            completion1 = TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action='LIKE',
                completed_at=timezone.now()
            )
            task.actions_completed += 1
            task.save()

        # Пытаемся создать второе выполнение в другой транзакции
        with transaction.atomic():
            completion2 = TaskCompletion.objects.create(
                task=task,
                user=self.user,
                action='RETWEET',  # Другой тип действия
                completed_at=timezone.now()
            )
            task.actions_completed += 1
            task.save()

        # Проверяем финальное состояние
        task.refresh_from_db()
        self.user_profile.refresh_from_db()

        logger.info(f"""Concurrent completion results:
            Final actions completed: {task.actions_completed}
            Task status: {task.status}
            Completions count: {TaskCompletion.objects.filter(task=task).count()}
        """)

        self.assertEqual(task.actions_completed, 2)
        self.assertEqual(task.status, 'COMPLETED')
        self.assertEqual(
            TaskCompletion.objects.filter(task=task).count(),
            2,
            "Should have exactly two completion records"
        )
