from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from .models import UserProfile, PaymentTransaction, Task
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_points_purchase(request):
    try:
        points = request.data.get('points')
        amount = request.data.get('amount')
        payment_id = request.data.get('payment_id')
        task_purchase = request.data.get('task_purchase', False)
        
        logger.info(f"[Payment Processing] Received data: {request.data}")
        logger.info(f"[Payment Processing] task_purchase value: {task_purchase} (type: {type(task_purchase)})")
        
        if not all([points, amount, payment_id]):
            logger.error(f"Missing required fields: points={points}, amount={amount}, payment_id={payment_id}")
            return Response({
                'error': 'Missing required fields'
            }, status=400)

        # Проверяем, не обработан ли уже этот платеж
        if PaymentTransaction.objects.filter(payment_id=payment_id).exists():
            logger.info(f"[Payment Processing] Payment {payment_id} already processed")
            return Response({
                'success': True,
                'message': 'Payment already processed',
                'new_balance': request.user.userprofile.balance,
                'available_tasks': request.user.userprofile.available_tasks
            }, status=200)

        user_profile = UserProfile.objects.get(user=request.user)
        
        # Создаем запись о транзакции
        logger.info(f"[Payment Processing] Creating transaction with is_task_purchase={task_purchase}")
        transaction = PaymentTransaction.objects.create(
            user=request.user,
            points=points,
            amount=amount,
            payment_id=payment_id,
            status='COMPLETED',
            payment_type='ONE_TIME',
            is_task_purchase=task_purchase
        )
        logger.info(f"[Payment Processing] PaymentTransaction created with status: {transaction.status} (id={transaction.id})")
        logger.info(f"[Payment Processing] Transaction is_task_purchase field: {transaction.is_task_purchase}")
        
        # Начисляем поинты пользователю
        user_profile.balance += points
        
        # Если это покупка создания задания, создаем задание (но НЕ начисляем задачу)
        if task_purchase:
            # Автоматически создаем задание из переданных данных
            task_data = request.data.get('task_data')
            if task_data:
                try:
                    from .models import SocialNetwork
                    
                    # Получаем социальную сеть
                    social_network = SocialNetwork.objects.get(code=task_data.get('social_network_code'))
                    
                    # Создаем задание
                    created_task = Task.objects.create(
                        creator=request.user,
                        type=task_data.get('type'),
                        post_url=task_data.get('post_url'),
                        price=task_data.get('price'),
                        actions_required=task_data.get('actions_required'),
                        social_network=social_network,
                        meaningful_comment=task_data.get('meaningful_comment', False),
                        status='ACTIVE',
                        original_price=task_data.get('price') * task_data.get('actions_required')
                    )
                    
                    # Связываем транзакцию с созданным заданием
                    transaction.task = created_task
                    transaction.save()
                    
                    logger.info(f"[Payment Processing] Task created automatically: {created_task.id}")
                    
                except Exception as e:
                    logger.error(f"[Payment Processing] Error creating task: {str(e)}")
                    # Не прерываем процесс оплаты, если создание задания не удалось
        
        user_profile.save()
        

        return Response({
            'success': True,
            'new_balance': user_profile.balance,
            'transaction_id': transaction.id,
            'available_tasks': user_profile.available_tasks
        })

    except Exception as e:
        logger.error(f"Error processing points purchase: {str(e)}")
        return Response({
            'error': 'Failed to process payment'
        }, status=500) 