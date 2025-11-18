import logging
import json
import stripe
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.conf import settings
from django.contrib.auth.models import User
from .models import PaymentTransaction
from .subscription_handlers import (
    handle_subscription_updated,
    handle_subscription_payment,
    handle_subscription_deleted,
    handle_failed_payment,
    handle_invoice_payment_succeeded,
    handle_setup_intent_succeeded,
    handle_subscription_created_inline
)

logger = logging.getLogger(__name__)

@csrf_exempt
def stripe_webhook(request):
    """
    Обработчик webhook'ов от Stripe с диспетчеризацией событий
    """
    if request.method != 'POST':
        logger.error("[Stripe Webhook] Non-POST request received")
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        if settings.DEBUG:  # Убираем проверку sig_header для режима отладки
            # В режиме разработки парсим данные напрямую
            logger.info(f"[Stripe Webhook] Running in DEBUG mode, signature check skipped")
            event = json.loads(payload)
            logger.info(f"[Stripe Webhook] DEBUG mode: Processing unsigned event: {event.get('type')}")
        else:
            # В продакшене проверяем подпись
            logger.info(f"[Stripe Webhook] Running in PROD mode")
            if not sig_header:
                logger.error("[Stripe Webhook] No signature header")
                return JsonResponse({'error': 'No Stripe signature header'}, status=400)
                
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=webhook_secret
            )
            
        data = event['data']
        event_type = event['type']
        data_object = data['object']

        logger.info(f"[Stripe Webhook] Successfully received event: {event_type}")
        
        # Диспетчеризация события
        response, status = stripe_dispatch_event(event_type, data_object)
        return JsonResponse(response, status=status)

    except ValueError as e:
        logger.error(f"[Stripe Webhook] Invalid payload: {str(e)}")
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"[Stripe Webhook] Invalid signature: {str(e)}")
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e:
        logger.error(f"[Stripe Webhook] Error processing webhook: {str(e)}")
        return JsonResponse({'error': 'Error processing webhook'}, status=400)

def stripe_dispatch_event(event_type, data):
    """
    Диспетчер событий Stripe
    """
    stripe_event_dispatch_map = {
        'customer.subscription.updated': handle_subscription_updated,
        'customer.subscription.created': handle_subscription_created_or_payment,
        'invoice.payment_succeeded': handle_invoice_payment_succeeded,
        'customer.subscription.deleted': handle_subscription_deleted,
        'invoice.payment_failed': handle_failed_payment,
        'checkout.session.completed': handle_checkout_session_completed,
        'invoice.upcoming': handle_invoice_upcoming,
        'invoice.finalized': handle_invoice_finalized,
        'setup_intent.succeeded': handle_setup_intent_succeeded_webhook,
        'payment_intent.succeeded': handle_payment_intent_succeeded,
    }

    handler = stripe_event_dispatch_map.get(event_type)
    if handler:
        logger.info(f"[Stripe Webhook] Processing event: {event_type}")
        return handler(data)
    else:
        logger.warning(f"[Stripe Webhook] Unhandled event type: {event_type}")
        return {'message': f'Unhandled event type: {event_type}'}, 200

def handle_subscription_created_or_payment(data):
    """
    Обрабатывает создание подписки - определяет, это inline или checkout
    """
    try:
        # Проверяем метаданные чтобы понять тип подписки
        metadata = data.get('metadata', {})
        transaction_id = metadata.get('transaction_id')
        
        if transaction_id:
            # Это inline подписка с transaction_id
            logger.info(f"[handle_subscription_created_or_payment] Routing to inline handler for transaction {transaction_id}")
            return handle_subscription_created_inline(data)
        else:
            # Это checkout подписка
            logger.info(f"[handle_subscription_created_or_payment] Routing to checkout handler")
            return handle_subscription_payment(data)
            
    except Exception as e:
        logger.error(f"[handle_subscription_created_or_payment] Error routing subscription: {str(e)}")
        return {'status': 'error'}, 500

def handle_setup_intent_succeeded_webhook(data):
    """
    Webhook обработчик для setup_intent.succeeded
    """
    try:
        logger.info(f"[handle_setup_intent_succeeded_webhook] Processing setup intent webhook: {data.get('id')}")
        return handle_setup_intent_succeeded(data)
    except Exception as e:
        logger.error(f"[handle_setup_intent_succeeded_webhook] Error: {str(e)}")
        return {'status': 'error'}, 500

def handle_subscription_created(data):
    """Обработка создания подписки"""
    logger.info(f"[Stripe Webhook] Subscription created: {data.get('id')}")
    return {'status': 'success'}, 200

def handle_subscription_deleted_webhook(data):
    """Обработка удаления подписки"""
    logger.info(f"[Stripe Webhook] Subscription deleted: {data.get('id')}")
    
    if handle_subscription_deleted(data):
        return {'status': 'success'}, 200
    else:
        return {'status': 'error', 'message': 'Failed to process subscription deletion'}, 500

def handle_checkout_session_completed(data):
    """Обработка успешного завершения сессии оплаты"""
    try:
        logger.info(f"[Stripe Webhook] Checkout session completed: {data.get('id')}")
        
        # Получаем данные из сессии
        session_id = data.get('id')
        payment_intent_id = data.get('payment_intent')
        subscription_id = data.get('subscription')
        customer_id = data.get('customer')
        
        if not session_id:
            logger.error("[Stripe Webhook] No session ID in checkout.session.completed event")
            return {'status': 'error'}, 400

        # Находим транзакцию по session_id
        from .models import PaymentTransaction
        transaction = PaymentTransaction.objects.filter(
            stripe_session_id=session_id
        ).first()

        if transaction:
            # Обновляем данные транзакции
            transaction.stripe_payment_intent_id = payment_intent_id
            transaction.stripe_subscription_id = subscription_id
            transaction.stripe_customer_id = customer_id
            transaction.save()
            
            logger.info(f"""
                [Stripe Webhook] Updated transaction:
                ID: {transaction.id}
                Session ID: {session_id}
                Subscription ID: {subscription_id}
                Customer ID: {customer_id}
            """)
            
            return {'status': 'success'}, 200
        else:
            logger.error(f"[Stripe Webhook] Transaction not found for session {session_id}")
            return {'status': 'error'}, 404

    except Exception as e:
        logger.error(f"[Stripe Webhook] Error processing checkout.session.completed: {str(e)}")
        return {'status': 'error'}, 500

def handle_invoice_upcoming(data):
    """Обработка предстоящего счета (уведомление о скором окончании триала)"""
    try:
        logger.info(f"[Stripe Webhook] Invoice upcoming: {data.get('id')}")
        
        subscription_id = data.get('subscription')
        if not subscription_id:
            logger.error("[Stripe Webhook] No subscription ID in invoice.upcoming event")
            return {'status': 'error'}, 400
            
        # Находим транзакцию
        from .models import PaymentTransaction
        transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id,
            status='TRIAL'
        ).first()
        
        if transaction:
            logger.info(f"""
                [Stripe Webhook] Trial ending soon:
                User: {transaction.user.id}
                Trial End: {transaction.trial_end_date}
                Next Payment: {data.get('next_payment_attempt')}
            """)
            
            # Здесь можно добавить логику для уведомления пользователя
            # о скором окончании триала
            
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[Stripe Webhook] Error processing invoice.upcoming: {str(e)}")
        return {'status': 'error'}, 500

def handle_invoice_finalized(data):
    """Обработка финализации счета"""
    try:
        logger.info(f"[Stripe Webhook] Invoice finalized: {data.get('id')}")
        
        subscription_id = data.get('subscription')
        if not subscription_id:
            logger.error("[Stripe Webhook] No subscription ID in invoice.finalized event")
            return {'status': 'error'}, 400
            
        # Находим транзакцию
        from .models import PaymentTransaction
        transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).first()
        
        if transaction:
            # Проверяем, есть ли метод оплаты
            customer_id = data.get('customer')
            if customer_id:
                try:
                    # Получаем данные клиента
                    customer = stripe.Customer.retrieve(customer_id)
                    default_payment_method = customer.get('invoice_settings', {}).get('default_payment_method')
                    
                    if default_payment_method:
                        # Если есть метод оплаты, пытаемся оплатить счет
                        invoice = stripe.Invoice.pay(data.get('id'))
                        logger.info(f"""
                            [Stripe Webhook] Auto-paying invoice:
                            Invoice ID: {data.get('id')}
                            Subscription: {subscription_id}
                            Customer: {customer_id}
                        """)
                    else:
                        logger.warning(f"[Stripe Webhook] No default payment method for customer {customer_id}")
                except Exception as e:
                    logger.error(f"[Stripe Webhook] Error paying invoice: {str(e)}")
            
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[Stripe Webhook] Error processing invoice.finalized: {str(e)}")
        return {'status': 'error'}, 500

def handle_payment_intent_succeeded(data):
    """
    Обрабатывает успешный платеж через PaymentIntent (для покупки поинтов и создания заданий)
    """
    try:
        payment_intent_id = data.get('id')
        metadata = data.get('metadata', {})
        user_id = metadata.get('user_id')
        points = metadata.get('points')
        task_purchase = metadata.get('task_purchase') == 'true'
        
        logger.info(f"[handle_payment_intent_succeeded] Processing payment {payment_intent_id} for user {user_id}")
        
        if not user_id or not points:
            logger.error(f"[handle_payment_intent_succeeded] Missing user_id or points in metadata")
            return {'status': 'error', 'message': 'Missing required metadata'}, 400
            
        # Проверяем, не обработан ли уже этот платеж
        if PaymentTransaction.objects.filter(stripe_payment_intent_id=payment_intent_id).exists():
            logger.info(f"[handle_payment_intent_succeeded] Payment {payment_intent_id} already processed")
            return {'status': 'success', 'message': 'Payment already processed'}, 200
            
        # Получаем пользователя
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"[handle_payment_intent_succeeded] User {user_id} not found")
            return {'status': 'error', 'message': 'User not found'}, 400
            
        # Создаем транзакцию
        amount = data.get('amount', 0) / 100  # Конвертируем из центов
        transaction = PaymentTransaction.objects.create(
            user=user,
            points=int(points),
            amount=amount,
            payment_id=f"pi_{payment_intent_id}",
            status='COMPLETED',
            payment_type='ONE_TIME',
            stripe_payment_intent_id=payment_intent_id,
            is_task_purchase=task_purchase
        )
        
        # Обновляем баланс пользователя
        user_profile = user.userprofile
        user_profile.balance += int(points)
        
        # Если это покупка создания задания, НЕ начисляем задачу
        # (задание создается в основном процессе обработки платежа)
        if task_purchase:
            logger.info(f"[handle_payment_intent_succeeded] Task purchase detected for user {user_id}")
            
        user_profile.save()
        
        logger.info(f"[handle_payment_intent_succeeded] Successfully processed payment {payment_intent_id}")
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[handle_payment_intent_succeeded] Error processing payment: {str(e)}")
        return {'status': 'error'}, 500 