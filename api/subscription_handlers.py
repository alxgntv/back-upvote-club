import logging
from django.db import transaction
from django.utils import timezone
from .models import UserProfile, PaymentTransaction
from .constants import SUBSCRIPTION_PLAN_CONFIG
import uuid
from datetime import datetime
import stripe

logger = logging.getLogger('api')

def get_plan_from_price_id(price_id):
    """
    Определяет план подписки по price_id из Stripe
    """
    try:
        for plan, config in SUBSCRIPTION_PLAN_CONFIG.items():
            if plan == 'FREE':
                continue
                
            # Проверяем price_id в monthly и annual конфигурациях
            if config.get('monthly', {}).get('price_id') == price_id or config.get('annual', {}).get('price_id') == price_id:
                return plan
                
        logger.warning(f"[get_plan_from_price_id] Plan not found for price_id: {price_id}")
        return None
        
    except Exception as e:
        logger.error(f"[get_plan_from_price_id] Error while getting plan: {str(e)}")
        return None

def handle_subscription_payment(event_data):
    """
    Обрабатывает успешный платеж подписки
    """
    try:
        logger.info(f"[handle_subscription_payment] Processing event data: {event_data}")

        # Получаем данные из события
        subscription_id = event_data.get('subscription')
        customer_id = event_data.get('customer')
        session_id = event_data.get('checkout_session')
        price_id = event_data['lines']['data'][0]['price']['id'] if event_data.get('lines', {}).get('data') else None
        amount_paid = event_data.get('amount_paid', 0)
        
        subscription_metadata = event_data.get('subscription_details', {}).get('metadata', {})
        lines = event_data.get('lines', {}).get('data', [])
        line_metadata = lines[0].get('metadata', {}) if lines else {}

        # Универсальная проверка
        is_trial = (
            str(subscription_metadata.get('is_trial', '')).lower() == 'true'
            or str(line_metadata.get('is_trial', '')).lower() == 'true'
        )

        logger.info(f"""
            [handle_subscription_payment] Extracted data:
            subscription_id: {subscription_id}
            customer_id: {customer_id}
            session_id: {session_id}
            price_id: {price_id}
            amount_paid: {amount_paid}
            is_trial: {is_trial}
        """)

        if not any([subscription_id, customer_id, price_id]):
            logger.error(f"[handle_subscription_payment] Missing required data")
            return False

        # Если это триальный период, обновляем существующую транзакцию
        if is_trial:
            with transaction.atomic():
                try:
                    # Сначала ищем по session_id
                    payment_transaction = PaymentTransaction.objects.select_for_update().filter(
                        stripe_session_id=session_id,
                        status__in=['PENDING', 'TRIAL']
                    ).first()
                    
                    # Если не нашли - ищем по subscription_id
                    if not payment_transaction and subscription_id:
                        payment_transaction = PaymentTransaction.objects.select_for_update().filter(
                            stripe_subscription_id=subscription_id,
                            status__in=['PENDING', 'TRIAL']
                        ).first()
                    
                    if not payment_transaction:
                        logger.error(f"[handle_subscription_payment] Transaction not found for trial period with PENDING or TRIAL status. Session ID: {session_id}, Subscription ID: {subscription_id}")
                        return False
                    
                    # Обновляем статус на TRIAL
                    payment_transaction.status = 'TRIAL'
                    payment_transaction.save()
                    
                    # Обновляем статус пользователя
                    user_profile = payment_transaction.user.userprofile
                    user_profile.status = get_plan_from_price_id(price_id)
                    user_profile.save()
                    
                    logger.info(f"""
                        [handle_subscription_payment] Updated trial transaction:
                        ID: {payment_transaction.id}
                        Status: {payment_transaction.status}
                        User Status: {user_profile.status}
                    """)
                    
                    return True
                    
                except PaymentTransaction.DoesNotExist:
                    logger.error(f"[handle_subscription_payment] Transaction not found for trial period. Session ID: {session_id}, Subscription ID: {subscription_id}")
                    return False

        # Проверяем, нет ли уже транзакции с таким subscription_id и статусом TRIAL
        existing_trial = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id,
            status='TRIAL'
        ).exists()

        # Если это платный платеж после триала, создаем новую транзакцию
        if existing_trial and amount_paid > 0:
            logger.info(f"[handle_subscription_payment] Creating new ACTIVE transaction after trial for subscription {subscription_id}")
            
            # Находим предыдущую транзакцию для получения данных пользователя
            previous_transaction = PaymentTransaction.objects.filter(
                stripe_subscription_id=subscription_id
            ).select_related('user__userprofile').order_by('-created_at').first()
            
            if not previous_transaction:
                logger.error(f"[handle_subscription_payment] No previous transaction found for subscription {subscription_id}")
                return False

            user_profile = previous_transaction.user.userprofile
            plan = get_plan_from_price_id(price_id)

            if not plan:
                logger.error(f"[handle_subscription_payment] Plan not found for price_id {price_id}")
                return False

            # Определяем период подписки из price_id
            period = None
            for p in ['monthly', 'annual']:
                if SUBSCRIPTION_PLAN_CONFIG[plan].get(p, {}).get('price_id') == price_id:
                    period = p
                    break

            if not period:
                logger.error(f"[handle_subscription_payment] Could not determine period for price_id {price_id}")
                return False

            with transaction.atomic():
                logger.info(f"""
                    [handle_subscription_payment] Starting transaction processing:
                    Previous balance: {user_profile.balance}
                    Current status: {user_profile.status}
                    Plan: {plan}
                    Period: {period}
                    Points to add: {SUBSCRIPTION_PLAN_CONFIG[plan][period]['points']}
                """)

                # Создаем новую транзакцию для платного периода
                payment_transaction = PaymentTransaction.objects.create(
                    user=previous_transaction.user,
                    points=SUBSCRIPTION_PLAN_CONFIG[plan][period]['points'],
                    amount=amount_paid/100,
                    payment_id=f"sub_{subscription_id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    status='ACTIVE',
                    payment_type='SUBSCRIPTION',
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    user_has_trial_before=True,
                    trial_end_date=previous_transaction.trial_end_date,
                    subscription_period_type='MONTHLY' if period == 'monthly' else 'ANNUAL'
                )

                logger.info(f"""
                    [handle_subscription_payment] Created payment transaction:
                    ID: {payment_transaction.id}
                    Points: {payment_transaction.points}
                    Status: {payment_transaction.status}
                """)

                # Начисляем баллы пользователю
                points = SUBSCRIPTION_PLAN_CONFIG[plan][period]['points']
                user_profile = UserProfile.objects.select_for_update().get(id=user_profile.id)
                
                logger.info(f"""
                    [handle_subscription_payment] Before updating user profile:
                    User ID: {user_profile.user.id}
                    Current balance: {user_profile.balance}
                    Current status: {user_profile.status}
                    Points to add: {points}
                """)

                old_balance = user_profile.balance
                old_status = user_profile.status
                
                user_profile.balance += points
                user_profile.status = plan
                user_profile.save()

                logger.info(f"""
                    [handle_subscription_payment] After updating user profile:
                    User ID: {user_profile.user.id}
                    Old balance: {old_balance}
                    New balance: {user_profile.balance}
                    Old status: {old_status}
                    New status: {user_profile.status}
                    Points added: {points}
                """)

                payment_transaction.stripe_metadata = event_data
                payment_transaction.last_webhook_received = timezone.now()
                payment_transaction.save()

                # Проверяем, что баллы действительно начислились
                updated_profile = UserProfile.objects.get(id=user_profile.id)
                logger.info(f"""
                    [handle_subscription_payment] Final profile check:
                    User ID: {updated_profile.user.id}
                    Final balance: {updated_profile.balance}
                    Final status: {updated_profile.status}
                    Expected balance: {old_balance + points}
                """)

                if updated_profile.balance != old_balance + points:
                    logger.error(f"""
                        [handle_subscription_payment] Balance mismatch:
                        Expected: {old_balance + points}
                        Actual: {updated_profile.balance}
                        Points not added correctly!
                    """)

                logger.info(f"""
                    [handle_subscription_payment] Created new ACTIVE transaction after trial:
                    User: {user_profile.user.id}
                    Plan: {plan}
                    Status: {payment_transaction.status}
                    Amount: {payment_transaction.amount}
                    Points: {payment_transaction.points}
                    Trial End: {payment_transaction.trial_end_date}
                    Period: {payment_transaction.subscription_period_start} - {payment_transaction.subscription_period_end}
                """)
                return True

        # Если это первая trial транзакция, возвращаем True
        if existing_trial:
            logger.info(f"[handle_subscription_payment] Trial transaction already exists for subscription {subscription_id}")
            return True

        # Находим предыдущую транзакцию
        previous_transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).select_related('user__userprofile').order_by('-created_at').first()

        if not previous_transaction and not session_id:
            logger.error(f"[handle_subscription_payment] No previous transaction found")
            return False

        # Для первого платежа ищем по session_id
        if not previous_transaction:
            previous_transaction = PaymentTransaction.objects.filter(
                stripe_session_id=session_id
            ).select_related('user__userprofile').first()

        if not previous_transaction:
            logger.error(f"[handle_subscription_payment] Transaction not found")
            return False

        user_profile = previous_transaction.user.userprofile
        plan = get_plan_from_price_id(price_id)

        if not plan:
            logger.error(f"[handle_subscription_payment] Plan not found for price_id {price_id}")
            return False

        # Определяем период подписки из price_id
        period = None
        for p in ['monthly', 'annual']:
            if SUBSCRIPTION_PLAN_CONFIG[plan].get(p, {}).get('price_id') == price_id:
                period = p
                break

        if not period:
            logger.error(f"[handle_subscription_payment] Could not determine period for price_id {price_id}")
            return False

        with transaction.atomic():
            user_profile = UserProfile.objects.select_for_update().get(id=user_profile.id)

            # Обновляем существующую транзакцию если она в статусе PENDING
            if previous_transaction.status == 'PENDING':
                payment_transaction = previous_transaction
            else:
                # Создаем новую транзакцию только если предыдущая не PENDING
                payment_transaction = PaymentTransaction.objects.create(
                    user=previous_transaction.user,
                    points=SUBSCRIPTION_PLAN_CONFIG[plan][period]['points'],
                    amount=amount_paid/100,
                    payment_id=f"sub_{subscription_id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    status='PENDING',
                    payment_type='SUBSCRIPTION',
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    user_has_trial_before=True,
                    trial_end_date=previous_transaction.trial_end_date,
                    subscription_period_type='MONTHLY' if period == 'monthly' else 'ANNUAL'
                )

            if is_trial:
                # Если это триал - обновляем статус и даты триала
                user_profile.status = plan
                user_profile.trial_start_date = timezone.now()
                
                # Вычисляем дату окончания триала
                trial_period_days = 7
                trial_end = timezone.now() + timezone.timedelta(days=trial_period_days)
                
                user_profile.trial_end_date = trial_end
                payment_transaction.trial_end_date = trial_end
                payment_transaction.status = 'TRIAL'
                logger.info(f"""[handle_subscription_payment] Starting trial for user {user_profile.user.id}:
                    Plan: {plan}
                    Trial Start: {user_profile.trial_start_date}
                    Trial End: {user_profile.trial_end_date}
                """)
            else:
                # Если это не триал - начисляем поинты и обновляем статус
                points = SUBSCRIPTION_PLAN_CONFIG[plan][period]['points']
                user_profile.balance += points
                user_profile.status = plan
                payment_transaction.status = 'ACTIVE'
                logger.info(f"[handle_subscription_payment] Added {points} points to user {user_profile.user.id}")

            user_profile.save()
            
            # Обновляем период подписки
            if 'lines' in event_data and 'data' in event_data['lines']:
                period_data = event_data['lines']['data'][0].get('period', {})
                if period_data.get('start'):
                    payment_transaction.subscription_period_start = timezone.datetime.fromtimestamp(period_data['start'])
                if period_data.get('end'):
                    payment_transaction.subscription_period_end = timezone.datetime.fromtimestamp(period_data['end'])
            
            payment_transaction.stripe_metadata = event_data
            payment_transaction.last_webhook_received = timezone.now()
            payment_transaction.save()

            logger.info(f"""
                [handle_subscription_payment] Successfully processed payment:
                User: {user_profile.user.id}
                Plan: {plan}
                Status: {payment_transaction.status}
                Amount: {payment_transaction.amount}
                Points: {payment_transaction.points}
                Trial End: {payment_transaction.trial_end_date}
                Period: {payment_transaction.subscription_period_start} - {payment_transaction.subscription_period_end}
            """)
            return True

    except Exception as e:
        logger.error(f"[handle_subscription_payment] Error processing payment: {str(e)}")
        return False

def handle_failed_payment(event_data):
    """
    Обрабатывает неудачный платеж подписки
    """
    try:
        logger.info(f"[handle_failed_payment] Processing event data: {event_data}")

        subscription_id = event_data.get('subscription')
        customer_id = event_data.get('customer')
        amount_attempted = event_data.get('amount_due', 0)
        attempt_count = event_data.get('attempt_count', 1)
        next_payment_attempt = event_data.get('next_payment_attempt')
        payment_error = event_data.get('last_payment_error', {}).get('message', '')

        # Находим последнюю транзакцию для этой подписки
        payment_transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).order_by('-created_at').first()

        if not payment_transaction:
            logger.error(f"[handle_failed_payment] No transaction found for subscription {subscription_id}")
            return {'status': 'error'}, 500

        user_profile = payment_transaction.user.userprofile

        with transaction.atomic():
            # Обновляем существующую транзакцию
            payment_transaction.status = 'PAYMENT_PENDING' if next_payment_attempt else 'FAILED'
            payment_transaction.attempt_count = attempt_count
            payment_transaction.last_payment_error = payment_error
            
            if next_payment_attempt:
                payment_transaction.next_payment_attempt = timezone.datetime.fromtimestamp(next_payment_attempt)
            
            payment_transaction.stripe_metadata = event_data
            payment_transaction.last_webhook_received = timezone.now()
            payment_transaction.save()

            # Если это последняя попытка или следующей не будет
            if attempt_count >= 4 or not next_payment_attempt:
                user_profile.status = 'FREE'
                user_profile.save()
                logger.info(f"""
                    [handle_failed_payment] Final payment attempt failed:
                    User: {user_profile.user.id}
                    Subscription: {subscription_id}
                    Attempts made: {attempt_count}
                    Status changed to: FREE
                """)
            else:
                logger.info(f"""
                    [handle_failed_payment] Payment attempt {attempt_count} failed:
                    User: {user_profile.user.id}
                    Subscription: {subscription_id}
                    Next attempt at: {payment_transaction.next_payment_attempt}
                    Current status: {user_profile.status}
                """)

            return {'status': 'success'}, 200

    except Exception as e:
        logger.error(f"[handle_failed_payment] Error processing failed payment: {str(e)}")
        return {'status': 'error'}, 500

def handle_subscription_deleted(event_data):
    """
    Обрабатывает отмену подписки от Stripe
    """
    try:
        logger.info(f"[handle_subscription_deleted] Processing event data: {event_data}")

        subscription_id = event_data.get('id')
        customer_id = event_data.get('customer')

        # Находим последнюю транзакцию для этой подписки
        previous_transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).order_by('-created_at').first()

        if not previous_transaction:
            logger.error(f"[handle_subscription_deleted] No transaction found for subscription {subscription_id}")
            return False

        user_profile = previous_transaction.user.userprofile

        with transaction.atomic():
            if previous_transaction.status in ['TRIAL', 'ACTIVE']:
                # Если отмена во время trial или active — просто меняем статус
                previous_transaction.status = 'CANCELLED'
                previous_transaction.stripe_metadata = event_data
                previous_transaction.last_webhook_received = timezone.now()
                previous_transaction.save()
                user_profile.status = 'FREE'
                user_profile.save()
                logger.info(f"""
                    [handle_subscription_deleted] Cancelled during TRIAL or ACTIVE:
                    User: {user_profile.user.id}
                    Subscription: {subscription_id}
                    Transaction ID: {previous_transaction.id}
                    Status changed to: CANCELLED
                    User Plan changed to: FREE
                """)
                return True
            else:
                # Старое поведение для отмены после trial/active
                payment_transaction = PaymentTransaction.objects.create(
                    user=previous_transaction.user,
                    points=0,
                    amount=0,
                    payment_id=f"cancel_sub_{subscription_id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    status='CANCELLED',
                    payment_type='SUBSCRIPTION',
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    user_has_trial_before=previous_transaction.user_has_trial_before,
                    trial_end_date=previous_transaction.trial_end_date,
                    subscription_period_start=timezone.now(),
                    subscription_period_end=None
                )
                user_profile.status = 'FREE'
                user_profile.save()
                payment_transaction.stripe_metadata = event_data
                payment_transaction.last_webhook_received = timezone.now()
                payment_transaction.save()
                return True

    except Exception as e:
        logger.error(f"[handle_subscription_deleted] Error processing subscription deletion: {str(e)}")
        return False 

def handle_subscription_updated(data):
    try:
        logger.info(f"[Stripe Webhook] Processing subscription update: {data}")
        
        subscription_id = data.get('id')
        status = data.get('status')
        customer_id = data.get('customer')
        latest_invoice_id = data.get('latest_invoice')
        
        # Получаем invoice для amount и payment_intent
        invoice_data = None
        payment_intent = None
        amount = 0
        if latest_invoice_id:
            try:
                invoice = stripe.Invoice.retrieve(latest_invoice_id)
                payment_intent = invoice.payment_intent
                # Конвертируем из центов в доллары
                amount = float(invoice.amount_paid) / 100 if invoice.amount_paid else 0
                invoice_data = invoice
                
            except Exception as e:
                logger.error(f"[handle_subscription_updated] Error retrieving invoice: {str(e)}")
        
        # Находим последнюю транзакцию по subscription_id (любого статуса)
        previous_transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).order_by('-created_at').first()
        
        if not previous_transaction:
            logger.error(f"[handle_subscription_updated] No transaction found for subscription {subscription_id}")
            return {'status': 'error'}, 404
            
        current_period_end = data.get('current_period_end')
        current_period_start = data.get('current_period_start')
    
        
        if status == 'active' and (
            previous_transaction.status == 'TRIAL' or 
            (previous_transaction.status == 'ACTIVE' and current_period_start)
        ):
            with transaction.atomic():
                user_profile = UserProfile.objects.select_for_update().get(
                    user=previous_transaction.user
                )
                
                if previous_transaction.status == 'TRIAL':
                    previous_transaction.status = 'TRIAL_ENDED'
                    previous_transaction.save()
                
                # Создаем новую транзакцию со статусом ACTIVE
                new_transaction = PaymentTransaction.objects.create(
                    user=previous_transaction.user,
                    points=previous_transaction.points,
                    amount=amount,  # Теперь устанавливаем правильную сумму
                    payment_id=f"sub_{uuid.uuid4().hex[:8]}",
                    status='ACTIVE',
                    payment_type='SUBSCRIPTION',
                    subscription_period_type=previous_transaction.subscription_period_type,
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    stripe_payment_intent_id=payment_intent,
                    stripe_metadata={
                        **data,
                        'invoice_data': invoice_data
                    } if invoice_data else data,
                    user_has_trial_before=True
                )
                
                if current_period_end:
                    new_transaction.subscription_period_end = datetime.fromtimestamp(current_period_end)
                if current_period_start:
                    new_transaction.subscription_period_start = datetime.fromtimestamp(current_period_start)
                    
                new_transaction.save()
                
                # Начисляем баллы пользователю
                old_balance = user_profile.balance
                user_profile.balance += new_transaction.points
                user_profile.save()
            
            return {'status': 'success'}, 200
            
        logger.info(f"[handle_subscription_updated] No action needed for status: {status}")
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[handle_subscription_updated] Error: {str(e)}")
        return {'status': 'error'}, 500

def handle_invoice_payment_succeeded(data):
    """
    Обрабатывает успешный платеж по инвойсу
    """
    try:
        logger.info(f"[handle_invoice_payment_succeeded] Processing invoice payment: {data}")
        
        subscription_id = data.get('subscription')
        customer_id = data.get('customer')
        payment_intent = data.get('payment_intent')
        amount_paid = float(data.get('amount_paid', 0)) / 100  # конвертируем центы в доллары
        
        # Получаем данные о периоде подписки
        period_start = data.get('period_start')
        period_end = data.get('period_end')
        
        # Получаем метаданные подписки
        subscription_details = data.get('subscription_details', {})
        subscription_metadata = subscription_details.get('metadata', {})
        
        # Находим последнюю транзакцию для этой подписки
        previous_transaction = PaymentTransaction.objects.filter(
            stripe_subscription_id=subscription_id
        ).order_by('-created_at').first()
        
        if not previous_transaction:
            logger.error(f"[handle_invoice_payment_succeeded] No transaction found for subscription {subscription_id}")
            return {'status': 'error'}, 404
        
        logger.info(f"""
            [handle_invoice_payment_succeeded] Processing payment:
            Subscription ID: {subscription_id}
            Previous Transaction Status: {previous_transaction.status if previous_transaction else 'None'}
            Amount Paid: {amount_paid}
            Period: {period_start} - {period_end}
        """)
        
        with transaction.atomic():
            user_profile = UserProfile.objects.select_for_update().get(
                user=previous_transaction.user
            )
            
            # Если это первый платёж после trial, переводим транзакцию в ACTIVE и начисляем баллы
            if previous_transaction.status == 'TRIAL' and amount_paid > 0:
                previous_transaction.status = 'ACTIVE'
                previous_transaction.amount = amount_paid
                if period_end:
                    previous_transaction.subscription_period_end = datetime.fromtimestamp(period_end)
                if period_start:
                    previous_transaction.subscription_period_start = datetime.fromtimestamp(period_start)
                previous_transaction.stripe_metadata = data
                previous_transaction.save()
                
                # Начисляем баллы пользователю
                old_balance = user_profile.balance
                user_profile.balance += previous_transaction.points
                user_profile.save()
                
                logger.info(f"""
                    [handle_invoice_payment_succeeded] Upgraded TRIAL to ACTIVE:
                    Transaction ID: {previous_transaction.id}
                    User: {user_profile.user.id}
                    Subscription: {subscription_id}
                    Points: {previous_transaction.points}
                    Amount: {amount_paid}
                    Old Balance: {old_balance}
                    New Balance: {user_profile.balance}
                    Period: {previous_transaction.subscription_period_start} - {previous_transaction.subscription_period_end}
                """)
                return {'status': 'success'}, 200
            else:
                # Старое поведение для новых периодов (если нужно)
                return {'status': 'noop'}, 200
    
    except Exception as e:
        logger.error(f"[handle_invoice_payment_succeeded] Error: {str(e)}")
        return {'status': 'error'}, 500

def handle_webhook(event_type, event_data):
    """
    Обрабатывает вебхук от Stripe
    """
    try:
        if event_type == 'customer.subscription.updated':
            return handle_subscription_updated(event_data)

        # Остальные обработчики вебхука
        if event_type == 'customer.subscription.created':
            return handle_subscription_payment(event_data)
        elif event_type == 'invoice.payment_succeeded':
            return handle_invoice_payment_succeeded(event_data)
        elif event_type == 'customer.subscription.deleted':
            return handle_subscription_deleted(event_data)
        elif event_type == 'invoice.payment_failed':
            return handle_failed_payment(event_data)
        else:
            logger.info(f"[handle_webhook] Unhandled event type: {event_type}")
            return True

    except Exception as e:
        logger.error(f"[handle_webhook] Error processing webhook: {str(e)}")
        return False

def handle_setup_intent_succeeded(event_data):
    """
    Обрабатывает успешное завершение Setup Intent для inline подписок
    """
    try:
        logger.info(f"[handle_setup_intent_succeeded] Processing setup intent: {event_data}")
        
        setup_intent_id = event_data.get('id')
        customer_id = event_data.get('customer')
        payment_method_id = event_data.get('payment_method')
        
        if not setup_intent_id:
            logger.error("[handle_setup_intent_succeeded] No setup intent ID")
            return {'status': 'error'}, 400
            
        # Находим транзакцию по setup intent ID
        from .models import PaymentTransaction
        payment_transaction = PaymentTransaction.objects.filter(
            stripe_payment_intent_id=setup_intent_id,
            status='PENDING'
        ).first()
        
        if not payment_transaction:
            logger.error(f"[handle_setup_intent_succeeded] Transaction not found for setup intent {setup_intent_id}")
            return {'status': 'error'}, 404
            
        # Получаем метаданные
        metadata = payment_transaction.stripe_metadata
        if not metadata:
            logger.error(f"[handle_setup_intent_succeeded] No metadata in transaction {payment_transaction.id}")
            return {'status': 'error'}, 400
            
        price_id = metadata.get('price_id')
        plan = metadata.get('plan')
        is_trial = metadata.get('is_trial', False)
        
        logger.info(f"""[handle_setup_intent_succeeded] Transaction metadata:
            price_id: {price_id}
            plan: {plan}
            is_trial: {is_trial}
            customer_id: {customer_id}
            payment_method: {payment_method_id}
        """)
        
        # Обновляем статус транзакции
        payment_transaction.status = 'SETUP_COMPLETED'
        payment_transaction.save()
        
        logger.info(f"""[handle_setup_intent_succeeded] Setup intent completed successfully:
            Setup Intent: {setup_intent_id}
            Transaction: {payment_transaction.id}
            Customer: {customer_id}
            Payment Method: {payment_method_id}
            Ready for subscription creation
        """)
        
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[handle_setup_intent_succeeded] Error: {str(e)}")
        return {'status': 'error'}, 500

def handle_subscription_created_inline(event_data):
    """
    Обрабатывает создание подписки для inline формы
    """
    try:
        logger.info(f"[handle_subscription_created_inline] Processing subscription creation: {event_data}")
        
        subscription_id = event_data.get('id')
        customer_id = event_data.get('customer')
        status = event_data.get('status')
        trial_end = event_data.get('trial_end')
        current_period_start = event_data.get('current_period_start')
        current_period_end = event_data.get('current_period_end')
        
        # Получаем метаданные подписки
        metadata = event_data.get('metadata', {})
        transaction_id = metadata.get('transaction_id')
        plan = metadata.get('plan')
        is_trial = metadata.get('is_trial') == 'True'
        
        logger.info(f"""[handle_subscription_created_inline] Subscription data:
            ID: {subscription_id}
            Status: {status}
            Customer: {customer_id}
            Trial End: {trial_end}
            Transaction ID: {transaction_id}
            Plan: {plan}
            Is Trial: {is_trial}
        """)
        
        if not transaction_id:
            logger.error("[handle_subscription_created_inline] No transaction_id in metadata")
            return {'status': 'error'}, 400
            
        # Находим транзакцию
        from .models import PaymentTransaction, UserProfile
        try:
            payment_transaction = PaymentTransaction.objects.get(
                id=transaction_id,
                status__in=['PENDING', 'SETUP_COMPLETED']
            )
        except PaymentTransaction.DoesNotExist:
            logger.error(f"[handle_subscription_created_inline] Transaction not found: {transaction_id}")
            return {'status': 'error'}, 404
            
        with transaction.atomic():
            # Обновляем транзакцию
            payment_transaction.stripe_subscription_id = subscription_id
            payment_transaction.status = 'TRIAL' if is_trial else 'ACTIVE'
            
            if trial_end:
                payment_transaction.trial_end_date = timezone.datetime.fromtimestamp(trial_end)
            if current_period_start:
                payment_transaction.subscription_period_start = timezone.datetime.fromtimestamp(current_period_start)
            if current_period_end:
                payment_transaction.subscription_period_end = timezone.datetime.fromtimestamp(current_period_end)
                
            payment_transaction.save()
            
            # Обновляем профиль пользователя
            user_profile = UserProfile.objects.select_for_update().get(user=payment_transaction.user)
            
            if is_trial:
                # Для триала только обновляем статус и даты
                user_profile.status = plan
                user_profile.trial_start_date = timezone.now()
                if payment_transaction.trial_end_date:
                    user_profile.trial_end_date = payment_transaction.trial_end_date
                logger.info(f"[handle_subscription_created_inline] Started trial for user {payment_transaction.user.id}: {plan}")
            else:
                # Для обычной подписки начисляем поинты
                old_balance = user_profile.balance
                user_profile.balance += payment_transaction.points
                user_profile.status = plan
                logger.info(f"[handle_subscription_created_inline] Added {payment_transaction.points} points to user {payment_transaction.user.id}, new balance: {user_profile.balance}")
                
            user_profile.save()
            
            logger.info(f"""[handle_subscription_created_inline] Successfully processed subscription:
                Subscription ID: {subscription_id}
                User: {payment_transaction.user.id}
                Plan: {plan}
                Status: {payment_transaction.status}
                Trial End: {payment_transaction.trial_end_date}
                User Status: {user_profile.status}
                New Balance: {user_profile.balance}
            """)
            
        return {'status': 'success'}, 200
        
    except Exception as e:
        logger.error(f"[handle_subscription_created_inline] Error: {str(e)}")
        return {'status': 'error'}, 500 