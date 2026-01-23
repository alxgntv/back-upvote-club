from django.contrib import admin
from .models import Task, TaskCompletion, UserProfile, InviteCode, EmailCampaign, EmailSubscriptionType, UserEmailSubscription, SocialNetwork, UserSocialProfile, PostCategory, PostTag, BlogPost, TwitterServiceAccount, ActionType, TwitterUserMapping, PaymentTransaction, TaskReport, ActionLanding, BuyLanding, Landing, Withdrawal, OnboardingProgress, Review, ApiKey, CrowdTask, CacheEntry
from django.utils import timezone
import logging
from django.template import Template, Context
from .email_service import EmailService
from django.conf import settings
from django.utils.html import format_html
from django.db import models
from django.db.models import Count, Q, Subquery, OuterRef, IntegerField
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from markdownx.admin import MarkdownxModelAdmin
from django.forms import forms, Form
from django.forms.widgets import FileInput
from django.urls import path
from .admin_views import business_metrics
import uuid
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.template.loader import render_to_string
from firebase_admin import auth
from django.contrib.auth.admin import UserAdmin
import random
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import csv
from django.http import HttpResponse
from datetime import datetime


logger = logging.getLogger(__name__)

# Register your models here.

@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user',
        'task',
        'action',
        'completed_at',
        'post_url',
        'get_social_network',
        'get_profile_url',
        'get_chosen_country'
    ]
    
    list_filter = [
        'action',
        'is_auto',
        'completed_at',
        'task__social_network'
    ]
    
    search_fields = [
        'user__username',
        'task__post_url',
        'post_url'
    ]
    
    readonly_fields = [
        'created_at',
    ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "task":
            kwargs["queryset"] = Task.objects.filter(
                status='ACTIVE'
            ).order_by('-created_at')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_social_network(self, obj):
        return obj.task.social_network if obj.task else '-'
    get_social_network.short_description = 'Social Network'
    get_social_network.admin_order_field = 'task__social_network'

    def get_profile_url(self, obj):
        """Получает profile_url из UserSocialProfile для пользователя и соцсети задания"""
        try:
            if obj.task and obj.task.social_network:
                # Используем prefetch_related данные если доступны, иначе делаем запрос
                social_profile = next(
                    (p for p in obj.user.social_profiles.all() if p.social_network_id == obj.task.social_network.id),
                    None
                )
                
                if social_profile and social_profile.profile_url:
                    url = social_profile.profile_url
                    display_url = url[:50] + '...' if len(url) > 50 else url
                    return format_html(
                        '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                        url,
                        display_url
                    )
            return '-'
        except Exception:
            return '-'
    get_profile_url.short_description = 'Profile URL'

    def get_chosen_country(self, obj):
        """Получает chosen_country из OnboardingProgress для пользователя"""
        try:
            if hasattr(obj.user, 'onboarding_progress') and obj.user.onboarding_progress:
                country = obj.user.onboarding_progress.chosen_country
                return country if country else '-'
            return '-'
        except Exception:
            return '-'
    get_chosen_country.short_description = 'Chosen Country'
    get_chosen_country.admin_order_field = 'user__onboarding_progress__chosen_country'

    def get_queryset(self, request):
        """Оптимизация запросов для админки"""
        return super().get_queryset(request).select_related(
            'user',
            'user__onboarding_progress',
            'task',
            'task__social_network'
        ).prefetch_related(
            'user__social_profiles'
        )

    def save_model(self, request, obj, form, change):
        """Логика сохранения и обработки выполнения задания"""
        try:
            with transaction.atomic():
                # Проверяем статус задания
                task = Task.objects.select_for_update().get(pk=obj.task.pk)
                
                if task.status != 'ACTIVE':
                    messages.error(request, 'Task is not active')
                    return

                # Проверяем уникальность выполнения
                if not change and TaskCompletion.objects.filter(
                    task=task,
                    user=obj.user,
                    action=obj.action
                ).exists():
                    messages.error(request, 'This user has already completed this action for this task')
                    return

                # Проверяем соответствие типа действия
                if obj.action.upper() != task.type.upper():
                    messages.error(request, f'Invalid action type. Expected: {task.type}')
                    return

                # Если это новое выполнение
                if not change:
                    # Устанавливаем completed_at если не установлено
                    if not obj.completed_at:
                        obj.completed_at = timezone.now()

                    # Устанавливаем post_url если не установлен
                    if not obj.post_url:
                        obj.post_url = task.post_url

                    # Сохраняем объект TaskCompletion
                    super().save_model(request, obj, form, change)

                    # Чередование: Основное -> Бонусное -> Основное ...
                    main_required = task.actions_required or 0
                    bonus_required = task.bonus_actions or 0
                    main_done = task.actions_completed or 0
                    bonus_done = task.bonus_actions_completed or 0
                    total_required = main_required + bonus_required
                    total_done = main_done + bonus_done

                    total_remaining = max(0, total_required - total_done)
                    main_remaining = max(0, main_required - main_done)
                    bonus_remaining = max(0, bonus_required - bonus_done)

                    if total_remaining == 1:
                        if main_remaining > 0:
                            task.actions_completed = main_done + 1
                        else:
                            task.actions_completed = main_done + 1
                    elif main_done == bonus_done:
                        task.actions_completed = main_done + 1
                    elif bonus_remaining > 0 and main_done > bonus_done:
                        task.bonus_actions_completed = bonus_done + 1
                    else:
                        task.actions_completed = main_done + 1

                    # Завершение: только после выполнения и основных, и бонусных
                    if (task.actions_completed >= main_required) and (task.bonus_actions_completed >= bonus_required) and total_required > 0:
                        task.status = 'COMPLETED'
                        task.completed_at = timezone.now()
                        task.completion_duration = task.completed_at - task.created_at
                        
                        # Отправляем письмо создателю задания
                        if not task.email_sent:
                            try:
                                email_service = EmailService()
                                
                                # Подготавливаем данные для письма
                                context = {
                                    'task': task,
                                    'user': task.creator,
                                    'completion_time': task.completion_duration,
                                    'site_url': settings.SITE_URL
                                }
                                
                                # Отправляем письмо
                                success = email_service.send_email(
                                    to_email=task.creator.email,
                                    subject='Task completed',
                                    html_content=render_to_string('email/task_completed.html', context)
                                )
                                
                                # Обновляем статус отправки письма
                                task.log_email_status(success, None if success else "Error sending email")
                                
                                if success:
                                    logger.info(f"[Admin] Sent completion email for task {task.id}")
                                    messages.success(request, 'Task completion email sent successfully')
                                else:
                                    logger.warning(f"[Admin] Failed to send completion email for task {task.id}")
                                    messages.warning(request, 'Failed to send task completion email')
                                    
                            except Exception as e:
                                logger.error(f"[Admin] Error sending completion email: {str(e)}")
                                task.log_email_status(False, str(e))
                                messages.error(request, f'Error sending completion email: {str(e)}')

                    task.save()

                    # Начисляем награду пользователю
                    reward = task.original_price / task.actions_required / 2
                    user_profile = obj.user.userprofile
                    user_profile.balance += reward
                    user_profile.completed_tasks_count += 1
                    user_profile.bonus_tasks_completed += 1
                    user_profile.save()

                    messages.success(
                        request, 
                        f'Task completion created successfully. Reward: {reward} points'
                    )
                else:
                    # Если это редактирование существующего выполнения
                    super().save_model(request, obj, form, change)

                logger.info(f"[Admin] Saved TaskCompletion: {obj.id} - User: {obj.user_id}, Action: {obj.action}")

        except Exception as e:
            logger.error(f"[Admin] Error saving TaskCompletion: {str(e)}")
            messages.error(request, f'Error saving task completion: {str(e)}')
            raise

admin.site.register(InviteCode)

class CrowdTaskInline(admin.StackedInline):
    """Inline для управления CrowdTask в админке Task"""
    model = CrowdTask
    extra = 1
    fields = (
        'text',
        'url',
        'status',
        'sent',
        'assigned_to',
        ('confirmed_by_parser', 'parser_log'),
        ('confirmed_by_user', 'user_log'),
    )
    verbose_name = 'Crowd Task'
    verbose_name_plural = 'Crowd Tasks'
    can_delete = True
    show_change_link = True
    ordering = ['created_at']
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('assigned_to',)

@admin.register(CrowdTask)
class CrowdTaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'task',
        'text_preview',
        'url_preview',
        'status',
        'sent',
        'confirmed_by_parser',
        'confirmed_by_user',
        'assigned_to_firebase_id',
        'created_at',
        'updated_at'
    )
    list_filter = (
        'status',
        'sent',
        'confirmed_by_parser',
        'confirmed_by_user',
        'assigned_to',
        'created_at',
        'task__type',
        'task__social_network'
    )
    search_fields = (
        'text',
        'url',
        'parser_log',
        'user_log',
        'task__id',
        'task__post_url',
        'assigned_to__username'
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'assigned_to_firebase_id'
    )
    raw_id_fields = ('task', 'assigned_to')
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'task',
                'text',
                'url',
                'status',
                'sent',
            )
        }),
        ('Assignment', {
            'fields': (
                'assigned_to',
                'assigned_to_firebase_id',
            )
        }),
        ('Verification', {
            'fields': (
                'confirmed_by_parser',
                'parser_log',
                'confirmed_by_user',
                'user_log',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )
    
    def text_preview(self, obj):
        """Показывает превью текста комментария"""
        if obj.text:
            preview = obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
            return preview
        return '-'
    text_preview.short_description = 'Comment Text'
    
    def url_preview(self, obj):
        """Показывает превью URL"""
        if obj.url:
            preview = obj.url[:50] + '...' if len(obj.url) > 50 else obj.url
            return format_html('<a href="{}" target="_blank">{}</a>', obj.url, preview)
        return '-'
    url_preview.short_description = 'URL'
    
    def assigned_to_firebase_id(self, obj):
        """Показывает Firebase ID пользователя, который перевел задание в PENDING_REVIEW"""
        if obj.assigned_to:
            return obj.assigned_to.username  # username в Django User = Firebase UID
        return '-'
    assigned_to_firebase_id.short_description = 'Assigned To (Firebase ID)'

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'type', 'task_type', 'social_network', 'post_url', 'original_price', 'price', 
        'actions_required', 'actions_completed', 'bonus_actions', 'bonus_actions_completed', 'status', 'creator', 
        'created_at', 'completion_info', 
        'completion_duration_display', 'email_status_display', 'creation_email_status_display',
        'longview',
        'is_pinned'  # добавляем поле для отображения в списке
    )
    
    list_filter = (
        'status', 
        'type',
        'task_type',
        'social_network',
        'created_at',
        'email_sent',
        'creation_email_sent',
        'promo_email_sent',
        'is_pinned'  # фильтр по закреплённым
    )
    
    search_fields = ('post_url', 'target_user_id', 'creator__username')
    
    readonly_fields = (
        'actions_completed', 
        'completion_percentage', 
        'created_at', 
        'completed_at', 
        'completion_duration', 
        'discount_display',
        'email_sent',
        'email_sent_at',
        'email_send_error',
        'creation_email_sent',
        'creation_email_sent_at',
        'creation_email_send_error',
        'promo_email_sent',
        'producthunt_campaign_button',
        'original_price'  # Добавляем original_price в readonly, он будет рассчитываться автоматически
    )

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'type',
                'task_type',
                'social_network',
                'post_url',
                'target_user_id',
                'creator',
                'price',
                'actions_required',
                'status',
                'deletion_reason',
                'original_price',
                'actions_completed',
                'bonus_actions',
                'bonus_actions_completed',
                'longview',
                'meaningful_comment',
                'completion_percentage',
                'is_pinned'  # добавляем галочку в основной блок
            )
        }),
        ('Email Information', {
            'fields': (
                'email_sent',
                'email_sent_at',
                'email_send_error',
                'creation_email_sent',
                'creation_email_sent_at',
                'creation_email_send_error',
                'promo_email_sent',
                'producthunt_campaign_button'
            )
        })
    )

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        # Условное отображение поля meaningful_comment только для COMMENT
        if obj and obj.type != 'COMMENT':
            try:
                fields = list(fields)
                if 'meaningful_comment' in fields:
                    fields.remove('meaningful_comment')
            except Exception:
                pass
        return fields
    
    inlines = [CrowdTaskInline]
    
    def get_inline_instances(self, request, obj=None):
        """Показываем inline для всех заданий, но редактирование доступно только для COMMENT"""
        inlines = super().get_inline_instances(request, obj)
        # Показываем inline для всех заданий, чтобы видеть привязанные Crowd Tasks
        return inlines

    def completion_percentage(self, obj):
        total_required = (obj.actions_required or 0) + (obj.bonus_actions or 0)
        if obj and total_required > 0:
            total_completed = (obj.actions_completed or 0) + (obj.bonus_actions_completed or 0)
            percentage = total_completed / total_required * 100
            return f"{percentage:.2f}%"
        return "0%"
    completion_percentage.short_description = "Completed (%)"

    def get_queryset(self, request):
        """Оптимизация запросов для админки"""
        return super().get_queryset(request).select_related('creator', 'social_network')

    def completion_info(self, obj):
        if obj.completed_at:
            return obj.completed_at.strftime("%Y-%m-%d %H:%M:%S")
        return '-'
    completion_info.short_description = 'Completed At'
    
    def completion_duration_display(self, obj):
        if obj.completion_duration:
            # Преобразуем продолжительность в более читаемый формат
            total_seconds = obj.completion_duration.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return '-'
    completion_duration_display.short_description = 'Completion Time'

    def discount_display(self, obj):
        """Отображает информацию о скидке"""
        try:
            if obj.original_price and obj.original_price != obj.price:
                discount_amount = obj.original_price - obj.price
                discount_percent = (discount_amount / obj.original_price) * 100
                return f"{discount_percent:.1f}% (saved {discount_amount} points)"
            return "No discount"
        except Exception as e:
            logger.error(f"Error calculating discount for task {obj.id}: {str(e)}")
            return "-"
    discount_display.short_description = "Applied Discount"

    def email_status_display(self, obj):
        """Отображение статуса отправки email"""
        if obj.email_sent:
            return format_html(
                '<span style="color: green;">✓ Sent at {}</span>',
                obj.email_sent_at.strftime('%Y-%m-%d %H:%M:%S')
            )
        elif obj.email_send_error:
            return format_html(
                '<span style="color: red;">✗ Error: {}</span>',
                obj.email_send_error
            )
        return format_html(
            '<span style="color: grey;">Not sent</span>'
        )
    email_status_display.short_description = 'Email Status'
    email_status_display.admin_order_field = 'email_sent'

    def creation_email_status_display(self, obj):
        """Статус письма о создании задачи"""
        if obj.creation_email_sent:
            ts = obj.creation_email_sent_at.strftime('%Y-%m-%d %H:%M:%S') if obj.creation_email_sent_at else ''
            return format_html('<span style="color: green;">✓ Sent {}</span>', ts)
        if obj.creation_email_send_error:
            return format_html('<span style="color: red;">✗ Error: {}</span>', obj.creation_email_send_error)
        return format_html('<span style="color: grey;">Not sent</span>')
    creation_email_status_display.short_description = 'Creation Email'
    creation_email_status_display.admin_order_field = 'creation_email_sent'

    def save_model(self, request, obj, form, change):
        """Обработка сохранения задания"""
        try:
            with transaction.atomic():
                if not change:  # Если это новое задание
                    # Проверяем баланс пользователя
                    creator_profile = obj.creator.userprofile
                    total_cost = obj.price * obj.actions_required

                    if total_cost > creator_profile.balance:
                        messages.error(request, f'Insufficient balance. Required: {total_cost}, Available: {creator_profile.balance}')
                        return

                    # Устанавливаем original_price равным полной стоимости
                    obj.original_price = total_cost

                    # Списываем баланс
                    creator_profile.balance -= total_cost
                    creator_profile.save()

                    # Проверяем available_tasks
                    if creator_profile.available_tasks <= 0:
                        messages.error(request, 'No available tasks left for this user')
                        return

                    # Уменьшаем количество доступных заданий
                    creator_profile.decrease_available_tasks()

                    # Специальная обработка для Twitter FOLLOW
                    if obj.social_network.code == 'TWITTER' and obj.type == 'FOLLOW':
                        try:
                            from .auto_actions import TwitterAutoActions
                            target_username = obj.post_url.split('/')[-1]
                            auto_actions = TwitterAutoActions(creator_profile)
                            user_id = auto_actions.get_user_id(target_username)
                            
                            if not user_id:
                                messages.error(request, 'Could not get Twitter user ID. Please check if the username is correct.')
                                return
                                
                            obj.target_user_id = user_id
                            
                        except Exception as e:
                            logger.error(f"[Admin] Error creating FOLLOW task: {str(e)}")
                            messages.error(request, 'Error creating FOLLOW task. Please try again later.')
                            return

                    messages.success(request, f'Task created successfully. Cost: {total_cost} points')

                elif 'status' in form.changed_data:
                    old_obj = Task.objects.get(pk=obj.pk)
                    
                    # Обработка статуса DELETED
                    if old_obj.status != 'DELETED' and obj.status == 'DELETED':
                        if not obj.deletion_reason:
                            messages.error(request, 'Please select a deletion reason')
                            return
                            
                        try:
                            # Возвращаем баланс создателю задания по формуле
                            creator_profile = obj.creator.userprofile
                            total_task_cost = obj.actions_required * obj.price
                            completed_cost = obj.actions_completed * obj.price
                            refund_amount = total_task_cost - completed_cost
                            
                            logger.info(f"""
                                [Task Deletion Refund Calculation]
                                Task ID: {obj.id}
                                Creator: {obj.creator.username}
                                Total Task Cost: {total_task_cost} points
                                - Actions Required: {obj.actions_required}
                                - Price per Action: {obj.price}
                                
                                Completed Actions Cost: {completed_cost} points
                                - Actions Completed: {obj.actions_completed}
                                - Price per Action: {obj.price}
                                
                                Final Refund Amount: {refund_amount} points
                                Current User Balance: {creator_profile.balance}
                                New Balance After Refund: {creator_profile.balance + refund_amount}
                            """)
                            
                            if refund_amount > 0:
                                creator_profile.balance += refund_amount
                                creator_profile.save()
                                messages.success(request, f'Successfully refunded {refund_amount} points to user balance')
                            else:
                                logger.warning(f"No refund needed for task {obj.id} as all actions were completed")
                                
                        except Exception as e:
                            logger.error(f"Error during refund calculation for task {obj.id}: {str(e)}")
                            messages.error(request, f'Error calculating refund: {str(e)}')
                            return
                        
                        # Отправляем email
                        try:
                            from .auto_actions import TwitterAutoActions
                            from firebase_admin import auth
                            
                            # Получаем email из Firebase по uid (который хранится в username)
                            firebase_user = auth.get_user(obj.creator.username)
                            user_email = firebase_user.email
                            
                            if not user_email:
                                logger.error(f"[Admin] No email found in Firebase for user {obj.creator.username}")
                                messages.error(request, 'Could not find user email')
                                return
                                
                            email_service = EmailService()
                            
                            if obj.deletion_reason == 'LINK_UNAVAILABLE':
                                email_text = "<p>Hello dear user. Users report that the link for completing the task is unavailable. Your task has been deleted and the points have been returned to your balance. Please <a href='https://upvote.club/dashboard/createtask'>create a new task with an active link</a>.</p>"
                            elif obj.deletion_reason == 'COMMUNITY_RULES':
                                email_text = "<p>Hello dear user. Your link violates community rules and users have reported this. We won't block your account, the post has just been deleted and points returned to your balance. Please <a href='https://upvote.club/dashboard/createtask'>create a new task</a>.</p>"
                            elif obj.deletion_reason == 'USER_REQUEST':
                                email_text = "<p>Your task has been deleted & points returned to your balance.</p>"
                            elif obj.deletion_reason == 'DOUBLE_ACCOUNT':
                                email_text = "<p>Hello, dear user.</p><p>This is the Upvote Club team. We truly appreciate that you enjoy our service and want to use it to promote your articles. However, our rules prohibit creating multiple accounts to promote the same profile. While this is technically possible, we monitor such attempts.</p><p>Therefore, we have remove your new tasks, but we have not blocked your old account so that you can continue using it freely.</p><p>If you wish to create multiple tasks, we recommend subscribing to our membership plan, which costs two times less than a Cup of coffee from Starbucks.</p><p>Thank you for your interest in Upvote Club!</p>"
                            else:
                                email_text = "<p>Hello dear user. Your task has been deleted.</p>"
                            
                            success = email_service.send_email(
                                to_email=user_email,  # Используем email из Firebase
                                subject='Your task has been deleted & points returned to your balance',
                                html_content=email_text
                            )
                            
                            obj.log_email_status(success, None if success else "Error sending email")
                            
                            if success:
                                logger.info(f"[Admin] Successfully sent deletion email for task {obj.id} to {user_email}")
                                messages.success(request, 'Task deletion email sent successfully')
                            else:
                                logger.warning(f"[Admin] Failed to send deletion email for task {obj.id} to {user_email}")
                                messages.warning(request, 'Failed to send task deletion email')
                                
                        except Exception as e:
                            logger.error(f"[Admin] Error sending deletion email for task {obj.id} to {user_email}: {str(e)}")
                            obj.log_email_status(False, str(e))
                            messages.error(request, f'Error sending deletion email: {str(e)}')
                    
                    # Обработка статуса COMPLETED
                    elif old_obj.status != 'COMPLETED' and obj.status == 'COMPLETED':
                        # Проверяем, нужно ли добавить автоматические выполнения
                        remaining_actions = obj.actions_required - obj.actions_completed
                        
                        if remaining_actions > 0:
                            logger.info(f"[Admin] Task {obj.id} needs {remaining_actions} more completions")
                            
                            # Получаем пользователей, которые еще не выполняли это задание
                            existing_users = TaskCompletion.objects.filter(
                                task=obj
                            ).values_list('user_id', flat=True)
                            
                            # Исключаем создателя задания и тех, кто уже выполнил
                            available_users = User.objects.exclude(
                                id__in=list(existing_users) + [obj.creator.id]
                            ).filter(
                                is_active=True
                            ).values_list('id', flat=True)
                            
                            # Получаем случайных пользователей
                            random_users = random.sample(
                                list(available_users), 
                                min(remaining_actions, len(available_users))
                            )
                            
                            for user_id in random_users:
                                try:
                                    user = User.objects.get(id=user_id)
                                    user_profile = user.userprofile
                                    
                                    # Создаем запись о выполнении
                                    completion = TaskCompletion.objects.create(
                                        task=obj,
                                        user=user,
                                        action=obj.type,
                                        completed_at=timezone.now(),
                                        post_url=obj.post_url,
                                        is_auto=True  # Помечаем как автоматическое выполнение
                                    )
                                    
                                    # Начисляем награду пользователю
                                    reward = obj.original_price / obj.actions_required / 2
                                    user_profile.balance += reward
                                    user_profile.completed_tasks_count += 1
                                    user_profile.bonus_tasks_completed += 1
                                    user_profile.save()
                                    
                                    obj.actions_completed += 1
                                    logger.info(f"[Admin] Added auto completion for user {user.id} on task {obj.id}")
                                    
                                except Exception as e:
                                    logger.error(f"[Admin] Error adding auto completion: {str(e)}")
                                    continue
                        
                        # Устанавливаем время завершения если не установлено
                        if not obj.completed_at:
                            obj.completed_at = timezone.now()
                            obj.completion_duration = obj.completed_at - obj.created_at
                        
                        # Отправляем письмо если еще не отправлено
                        if not obj.email_sent:
                            try:
                                email_service = EmailService()
                                
                                context = {
                                    'task': obj,
                                    'user': obj.creator,
                                    'completion_time': obj.completion_duration,
                                    'site_url': settings.SITE_URL
                                }
                                
                                success = email_service.send_email(
                                    to_email=obj.creator.email,
                                    subject='Task completed',
                                    html_content=render_to_string('email/task_completed.html', context)
                                )
                                
                                obj.log_email_status(success, None if success else "Error sending email")
                                
                                if success:
                                    logger.info(f"[Admin] Sent completion email for task {obj.id}")
                                    messages.success(request, 'Task completion email sent successfully')
                                else:
                                    logger.warning(f"[Admin] Failed to send completion email for task {obj.id}")
                                    messages.warning(request, 'Failed to send task completion email')
                                    
                            except Exception as e:
                                logger.error(f"[Admin] Error sending completion email: {str(e)}")
                                obj.log_email_status(False, str(e))
                                messages.error(request, f'Error sending completion email: {str(e)}')

                super().save_model(request, obj, form, change)
                
        except Exception as e:
            logger.error(f"[Admin] Error saving Task: {str(e)}")
            messages.error(request, f'Error saving task: {str(e)}')
            raise

    actions = ['send_producthunt_campaign']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:task_id>/send-producthunt-campaign/', 
                 self.admin_site.admin_view(self.send_single_producthunt_campaign_view), 
                 name='api_task_send_producthunt_campaign'),
        ]
        return custom_urls + urls
    
    def send_single_producthunt_campaign_view(self, request, task_id):
        """View для отправки ProductHunt кампании для одного задания"""
        from django.shortcuts import redirect
        from django.contrib import messages
        from .utils.email_utils import send_producthunt_campaign_emails
        
        try:
            task = Task.objects.select_related('social_network').get(pk=task_id)
            
            # Проверка что это ProductHunt задание
            if task.social_network.code.upper() != 'PRODUCTHUNT':
                messages.error(request, f"Task #{task_id} is not a ProductHunt task")
                return redirect('admin:api_task_change', task_id)
            
            # Проверка что задание активно
            if task.status != 'ACTIVE':
                messages.error(request, f"Task #{task_id} is not ACTIVE (current status: {task.status})")
                return redirect('admin:api_task_change', task_id)
            
            # Проверка: уже отправлено?
            if task.promo_email_sent:
                messages.warning(request, f"Campaign for task #{task_id} was already sent!")
                return redirect('admin:api_task_change', task_id)
            
            # Отправляем письма
            stats = send_producthunt_campaign_emails(task)
            
            # Проставляем галочку
            task.promo_email_sent = True
            task.save(update_fields=['promo_email_sent'])
            
            messages.success(
                request, 
                f"ProductHunt campaign sent! Sent: {stats['sent']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}"
            )
            
        except Task.DoesNotExist:
            messages.error(request, f"Task #{task_id} not found")
        except Exception as e:
            messages.error(request, f"Error sending campaign: {str(e)}")
        
        return redirect('admin:api_task_change', task_id)
    
    def producthunt_campaign_button(self, obj):
        """Кнопка для отправки ProductHunt кампании"""
        if obj and obj.pk:
            # Показываем кнопку только для ProductHunt заданий
            if obj.social_network and obj.social_network.code.upper() == 'PRODUCTHUNT':
                if obj.promo_email_sent:
                    return format_html(
                        '<div style="padding: 10px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; color: #155724;">'
                        '✓ Campaign already sent'
                        '</div>'
                    )
                else:
                    if obj.status == 'ACTIVE':
                        from django.urls import reverse
                        url = reverse('admin:api_task_send_producthunt_campaign', args=[obj.pk])
                        return format_html(
                            '<a href="{}" class="button" style="background: #DA552F; color: white; padding: 10px 15px; '
                            'text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;" '
                            'onclick="return confirm(\'Send ProductHunt campaign to all verified users?\');">'
                            '🚀 Send ProductHunt Campaign'
                            '</a>',
                            url
                        )
                    else:
                        return format_html(
                            '<div style="padding: 10px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; color: #856404;">'
                            'Task must be ACTIVE to send campaign (current: {})'
                            '</div>',
                            obj.status
                        )
        return '-'
    
    producthunt_campaign_button.short_description = 'ProductHunt Campaign'
    
    def send_producthunt_campaign(self, request, queryset):
        """
        Отправляет ProductHunt промо письма для выбранных заданий
        """
        from .utils.email_utils import send_producthunt_campaign_emails
        
        # Фильтруем только ProductHunt задания
        producthunt_tasks = queryset.filter(
            social_network__code='PRODUCTHUNT',
            status='ACTIVE'
        )
        
        if not producthunt_tasks.exists():
            self.message_user(
                request,
                "No active ProductHunt tasks selected",
                level=messages.WARNING
            )
            return
        
        total_sent = 0
        total_failed = 0
        total_skipped = 0
        already_sent_count = 0
        
        for task in producthunt_tasks:
            # Проверка: уже отправлено?
            if task.promo_email_sent:
                already_sent_count += 1
                self.message_user(
                    request,
                    f"Task #{task.id} - campaign already sent, skipping",
                    level=messages.WARNING
                )
                continue
            
            # Отправляем письма
            stats = send_producthunt_campaign_emails(task)
            
            # Проставляем галочку (ЗАЩИТА ОТ ДУБЛЕЙ)
            task.promo_email_sent = True
            task.save(update_fields=['promo_email_sent'])
            
            total_sent += stats['sent']
            total_failed += stats['failed']
            total_skipped += stats['skipped']
            
            self.message_user(
                request,
                f"Task #{task.id}: Sent {stats['sent']}, Failed {stats['failed']}, Skipped {stats['skipped']}",
                level=messages.SUCCESS
            )
        
        # Итоговое сообщение
        self.message_user(
            request,
            f"Campaign completed: {total_sent} sent, {total_failed} failed, {total_skipped} skipped, {already_sent_count} already sent",
            level=messages.SUCCESS
        )
    
    send_producthunt_campaign.short_description = "Promote this task"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Настройка полей для выбора из списка"""
        if db_field.name == "social_network":
            kwargs["queryset"] = SocialNetwork.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'status',
        'country_code',
        'chosen_country',
        'balance',
        'is_ambassador',
        'is_affiliate_partner',
        'available_tasks',
        'get_created_tasks_count',
        'get_last_action_time',
        'get_invited_users_count',
        'get_invited_by',
        'get_invite_code',
        'has_referrer_data',
        'black_friday_subscribed',
        'welcome_email_sent',
        'welcome_email_sent_at'
    ]
    
    list_filter = [
        'status',
        'country_code',
        'chosen_country',
        'twitter_verification_status',
        'auto_actions_enabled',
        'is_ambassador',
        'is_affiliate_partner',
        'black_friday_subscribed',
        'welcome_email_sent',
        'user__taskcompletion__action',
        'user__taskcompletion__is_auto',
    ]
    
    search_fields = [
        'user__username',
        'invited_by__username',
        'twitter_account',
        'country_code',
        'balance',
        'available_tasks',
        'game_rewards_claimed',
        'bonus_tasks_completed',
        'last_reward_at_task_count',
        'invite_code__code',
        'referrer_url',
        'landing_url',
    ]
    raw_id_fields = ['user', 'invited_by', 'invite_code']

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'user',
                'invited_by',
                'status',
                'country_code',
                'chosen_country',
                'balance',
                'available_tasks',
                'daily_task_limit',
                'last_tasks_update',
                'completed_tasks_count',
            )
        }),
        ('Роли и партнерство', {
            'fields': (
                'is_ambassador',
                'is_affiliate_partner',
            )
        }),
        ('Платежная информация', {
            'fields': (
                'paypal_address',
                'usdt_address',
                'stripe_client_id',
            )
        }),
        ('Referrer Tracking', {
            'fields': (
                'referrer_url',
                'landing_url',
                'referrer_timestamp',
                'referrer_user_agent',
                'device_type',
                'os_name',
                'os_version',
            ),
            'classes': ('collapse',)
        }),
        ('Twitter интеграция', {
            'fields': (
                'twitter_account',
                'twitter_verification_status',
                'twitter_verification_date',
                'twitter_oauth_token',
                'twitter_oauth_token_secret',
                'twitter_user_id',
                'twitter_screen_name',
            )
        }),
        ('Игровая механика', {
            'fields': (
                'game_rewards_claimed',
                'bonus_tasks_completed',
                'last_reward_at_task_count',
            )
        }),
        ('Автоматизация', {
            'fields': (
                'auto_actions_enabled',
                'last_auto_action_at',
            )
        }),
        ('Подписка и триал', {
            'fields': (
                'trial_start_date',
                'invite_code',
                'available_invites',
                'black_friday_subscribed',
                'welcome_email_sent',
                'welcome_email_sent_at',
            )
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).annotate(
            total_actions=Count('user__taskcompletion'),
            auto_actions=Count('user__taskcompletion', 
                filter=models.Q(user__taskcompletion__is_auto=True)),
            manual_actions=Count('user__taskcompletion', 
                filter=models.Q(user__taskcompletion__is_auto=False)),
            created_tasks_count=Count('user__created_tasks'),
            invited_users_count=Count(
                'user__created_invite_codes__used_by',
                distinct=True
            )
        )
        return queryset
    
    def get_total_actions(self, obj):
        return format_html('{}', obj.total_actions)
    get_total_actions.admin_order_field = 'total_actions'
    get_total_actions.short_description = 'Total Actions'
    
    def get_auto_actions(self, obj):
        return format_html('{}', obj.auto_actions)
    get_auto_actions.admin_order_field = 'auto_actions'
    get_auto_actions.short_description = 'Auto Actions'
    
    def get_manual_actions(self, obj):
        return format_html('{}', obj.manual_actions)
    get_manual_actions.admin_order_field = 'manual_actions'
    get_manual_actions.short_description = 'Manual Actions'
    
    def get_last_action_time(self, obj):
        last_action = TaskCompletion.objects.filter(
            user=obj.user
        ).order_by('-completed_at').first()
        
        if last_action:
            return last_action.completed_at
        return '-'
    get_last_action_time.short_description = 'Last Action'

    def get_created_tasks_count(self, obj):
        return format_html('{}', obj.created_tasks_count)
    get_created_tasks_count.admin_order_field = 'created_tasks_count'
    get_created_tasks_count.short_description = 'Created Tasks'

    def get_invited_users_count(self, obj):
        return format_html('{}', obj.invited_users_count)
    get_invited_users_count.admin_order_field = 'invited_users_count'
    get_invited_users_count.short_description = 'Invited Users'

    def get_invited_by(self, obj):
        if obj.invited_by:
            return format_html(
                '<a href="/admin/auth/user/{}/">{} (Firebase UID)</a>',
                obj.invited_by.id,
                obj.invited_by.username
            )
        return '-'
    get_invited_by.short_description = 'Invited By'
    get_invited_by.admin_order_field = 'invited_by__username'

    def get_invite_code(self, obj):
        if obj.invite_code:
            return format_html(
                '<a href="/admin/api/invitecode/{}/">{}</a>',
                obj.invite_code.id,
                obj.invite_code.code
            )
        return '-'
    get_invite_code.short_description = 'Invite Code'
    get_invite_code.admin_order_field = 'invite_code__code'

    def has_referrer_data(self, obj):
        """Показывает есть ли данные referrer tracking"""
        if obj.referrer_url or obj.landing_url:
            return format_html(
                '<span style="color: green;">✓ Yes</span><br/>'
                '<small>From: {}</small><br/>'
                '<small>To: {}</small>',
                obj.referrer_url[:50] + '...' if obj.referrer_url and len(obj.referrer_url) > 50 else obj.referrer_url or 'Direct',
                obj.landing_url[:50] + '...' if obj.landing_url and len(obj.landing_url) > 50 else obj.landing_url or '-'
            )
        return format_html('<span style="color: grey;">✗ No</span>')
    has_referrer_data.short_description = 'Referrer Data'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "invited_by":
            kwargs["queryset"] = User.objects.all().order_by('username')
            kwargs["help_text"] = "Select user by Firebase UID (stored in username field)"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    autocomplete_fields = ['invited_by']

    def save_model(self, request, obj, form, change):
        try:
            # Проверяем, изменилось ли поле black_friday_subscribed на True
            send_black_friday_email = False
            if change and 'black_friday_subscribed' in form.changed_data:
                old_obj = UserProfile.objects.get(pk=obj.pk)
                if not old_obj.black_friday_subscribed and obj.black_friday_subscribed:
                    send_black_friday_email = True
            elif not change and obj.black_friday_subscribed:
                send_black_friday_email = True
            
            # Проверяем, изменилось ли поле invited_by
            if 'invited_by' in form.changed_data and obj.invited_by:
                logger.info(f"[UserProfileAdmin] invited_by field changed for user {obj.user.username}")
                
                # Сначала сохраняем модель
                super().save_model(request, obj, form, change)
                
                # Затем пытаемся отправить уведомление
                try:
                    from api.utils.email_utils import send_inviter_notification_email
                    if send_inviter_notification_email(obj.invited_by, obj.user):
                        messages.success(request, 'Successfully sent notification to inviter')
                    else:
                        messages.warning(request, 'Failed to send notification to inviter')
                except Exception as e:
                    logger.error(f"[UserProfileAdmin] Error sending inviter notification: {str(e)}", exc_info=True)
                    messages.error(request, f'Error sending notification to inviter: {str(e)}')
            else:
                super().save_model(request, obj, form, change)
            
            # Отправляем письмо о подписке на Black Friday
            if send_black_friday_email:
                try:
                    from firebase_admin import auth
                    
                    # Получаем email из Firebase по uid (который хранится в username)
                    firebase_user = auth.get_user(obj.user.username)
                    user_email = firebase_user.email
                    
                    if not user_email:
                        logger.error(f"[Admin] No email found in Firebase for user {obj.user.username}")
                        messages.error(request, 'Could not find user email')
                        return
                    
                    email_service = EmailService()
                    
                    html_content = (
                        "<p>You received this discount earlier than others because you subscribed to the Black Friday notification.</p>"
                        "<p>😎🚨 MATE Plan: Only $219 (down from $439) – includes 15,000 points and unlimited tasks creation.</p>"
                        "<p>🤜🤛 Buddy Plan: Only $74 (down from $149) – includes 5,000 points and unlimited tasks.</p>"
                        "<p>Locked-in pricing: Your subscription price is guaranteed for the entire year.</p>"
                    )
                    
                    success = email_service.send_email(
                        to_email=user_email,
                        subject='🚨🦩🎁 Early Bird Black Friday Deal 50% Discount on All Annual Plans in your in your box',
                        html_content=html_content
                    )
                    
                    if success:
                        logger.info(f"[Admin] Successfully sent Black Friday subscription email to {user_email}")
                        messages.success(request, 'Black Friday subscription email sent successfully')
                    else:
                        logger.warning(f"[Admin] Failed to send Black Friday subscription email to {user_email}")
                        messages.warning(request, 'Failed to send Black Friday subscription email')
                        
                except Exception as e:
                    logger.error(f"[Admin] Error sending Black Friday subscription email: {str(e)}")
                    messages.error(request, f'Error sending Black Friday subscription email: {str(e)}')
                
        except Exception as e:
            logger.error(f"[UserProfileAdmin] Error saving UserProfile: {str(e)}", exc_info=True)
            messages.error(request, f'Error saving user profile: {str(e)}')
            super().save_model(request, obj, form, change)

    actions = ['export_users_with_firebase_email']
    
    def export_users_with_firebase_email(self, request, queryset):
        """Экспортирует пользователей с email из Firebase и пометкой об отключенных email"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="users_export_{timestamp}.csv"'
        
        writer = csv.writer(response)
        
        # Заголовки CSV
        headers = [
            'User ID',
            'Firebase UID (Username)',
            'Firebase Email',
            'Email Disabled in Firebase',
            'Email Verified',
            'User Status',
            'Country Code',
            'Chosen Country',
            'Balance',
            'Available Tasks',
            'Completed Tasks Count',
            'Is Ambassador',
            'Is Affiliate Partner',
            'Black Friday Subscribed',
            'Auto Actions Enabled',
            'Twitter Account',
            'Twitter Verification Status',
            'Referrer URL',
            'Landing URL',
            'Device Type',
            'OS Name',
            'OS Version',
            'Created At',
        ]
        writer.writerow(headers)
        
        # Оптимизируем запросы
        profiles = queryset.select_related('user', 'invited_by', 'invite_code')
        
        count = 0
        error_count = 0
        
        for profile in profiles:
            try:
                user = profile.user
                firebase_uid = user.username
                
                # Получаем данные из Firebase
                firebase_email = ''
                email_disabled = False
                email_verified = False
                firebase_error = ''
                
                if firebase_uid:
                    try:
                        from firebase_admin import auth
                        firebase_user = auth.get_user(firebase_uid)
                        firebase_email = firebase_user.email or ''
                        email_disabled = firebase_user.disabled if hasattr(firebase_user, 'disabled') else False
                        email_verified = firebase_user.email_verified if hasattr(firebase_user, 'email_verified') else False
                    except auth.UserNotFoundError:
                        firebase_error = 'User not found in Firebase'
                        logger.warning(f"[export_users] Firebase user not found: {firebase_uid}")
                    except Exception as e:
                        firebase_error = f'Error: {str(e)[:50]}'
                        logger.error(f"[export_users] Error getting Firebase user {firebase_uid}: {str(e)}")
                
                # Если email отключен, добавляем пометку
                email_display = firebase_email
                if email_disabled:
                    email_display = f"{firebase_email} [DISABLED - DO NOT SEND EMAIL]"
                elif firebase_error:
                    email_display = f"[ERROR: {firebase_error}]"
                
                # Формируем строку данных
                row = [
                    user.id,
                    firebase_uid,
                    email_display,
                    'YES' if email_disabled else 'NO',
                    'YES' if email_verified else 'NO',
                    profile.status or '',
                    profile.country_code or '',
                    profile.chosen_country or '',
                    profile.balance or 0,
                    profile.available_tasks or 0,
                    profile.completed_tasks_count or 0,
                    'YES' if profile.is_ambassador else 'NO',
                    'YES' if profile.is_affiliate_partner else 'NO',
                    'YES' if profile.black_friday_subscribed else 'NO',
                    'YES' if profile.auto_actions_enabled else 'NO',
                    profile.twitter_account or '',
                    profile.twitter_verification_status or '',
                    profile.referrer_url or '',
                    profile.landing_url or '',
                    profile.device_type or '',
                    profile.os_name or '',
                    profile.os_version or '',
                    user.date_joined.strftime('%Y-%m-%d %H:%M:%S') if user.date_joined else '',
                ]
                
                writer.writerow(row)
                count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(f"[export_users] Error exporting user profile {getattr(profile, 'id', '?')}: {str(e)}")
                continue
        
        logger.info(f"[export_users] Exported {count} user profiles to CSV (errors: {error_count})")
        if error_count > 0:
            self.message_user(
                request, 
                f'Successfully exported {count} user profiles to CSV. {error_count} errors occurred.', 
                messages.WARNING
            )
        else:
            self.message_user(
                request, 
                f'Successfully exported {count} user profiles to CSV', 
                messages.SUCCESS
            )
        return response
    
    export_users_with_firebase_email.short_description = "📥 Download selected users with Firebase email (includes disabled email warning)"

@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ('subject', 'subscription_type', 'status', 'created_at', 'sent_at')
    list_filter = ('status', 'subscription_type')
    actions = ['send_campaign']

    def send_campaign(self, request, queryset):
        email_service = EmailService()
        
        for campaign in queryset:
            if campaign.status != 'DRAFT':
                continue

            subscribers = UserEmailSubscription.objects.filter(
                subscription_type=campaign.subscription_type,
                is_subscribed=True
            ).select_related('user')

            campaign.status = 'SENDING'
            campaign.save()

            total = subscribers.count()
            success = 0
            failed = 0

            for subscription in subscribers:
                unsubscribe_url = f"{settings.SITE_URL}/unsubscribe/{subscription.unsubscribe_token}/"
                
                context = {
                    'user': subscription.user,
                    'unsubscribe_url': unsubscribe_url,
                    'campaign': campaign
                }
                
                html_content = Template(campaign.body_html).render(Context(context))
                
                if email_service.send_email(
                    subscription.user.email,
                    campaign.subject,
                    html_content,
                    campaign.id
                ):
                    success += 1
                else:
                    failed += 1

            campaign.status = 'COMPLETED'
            campaign.total_recipients = total
            campaign.successful_sends = success
            campaign.failed_sends = failed
            campaign.sent_at = timezone.now()
            campaign.save()

    send_campaign.short_description = "Send selected campaigns"

@admin.register(EmailSubscriptionType)
class EmailSubscriptionTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'subscribe_all_users')
    actions = ['subscribe_selected_users']
    
    def get_fields(self, request, obj=None):
        fields = ['name', 'description', 'created_at', 'subscribe_all_users', 'users_to_subscribe']
        if not obj:  # Если создаем новый объект
            fields.remove('created_at')  # created_at автоматически заполняется
        return fields
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Если редактируем существующий объект
            return ['name', 'created_at']
        return ['created_at']
    
    def save_model(self, request, obj, form, change):
        logger.info(f"""
            Saving EmailSubscriptionType:
            Name: {obj.name}
            Subscribe all users: {obj.subscribe_all_users}
            Changed fields: {form.changed_data}
        """)
        
        super().save_model(request, obj, form, change)
        
        try:
            if 'subscribe_all_users' in form.changed_data and obj.subscribe_all_users:
                # Получаем пользователей, которые не отписывались от рассылок
                active_users = User.objects.filter(is_active=True).exclude(
                    id__in=UserEmailSubscription.objects.filter(
                        is_subscribed=False
                    ).values('user_id')
                )
                
                logger.info(f"Found {active_users.count()} active users to subscribe")
                
                # Подписываем всех активных пользователей
                for user in active_users:
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=obj,
                        defaults={'is_subscribed': True, 'unsubscribe_token': str(uuid.uuid4())}
                    )
                    if created:
                        logger.info(f"Created subscription for user {user.username} to {obj.name}")
                    else:
                        subscription.is_subscribed = True
                        subscription.save()
                        logger.info(f"Updated subscription for user {user.username} to {obj.name}")
                        
            if 'users_to_subscribe' in form.changed_data and obj.users_to_subscribe:
                selected_users = obj.users_to_subscribe.all()
                logger.info(f"Subscribing {selected_users.count()} selected users")
                
                # Подписываем выбранных пользователей
                for user in selected_users:
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=obj,
                        defaults={'is_subscribed': True, 'unsubscribe_token': str(uuid.uuid4())}
                    )
                    if created:
                        logger.info(f"Created subscription for selected user {user.username} to {obj.name}")
                    else:
                        subscription.is_subscribed = True
                        subscription.save()
                        logger.info(f"Updated subscription for selected user {user.username} to {obj.name}")
                
                # Очищаем поле после подписки
                obj.users_to_subscribe.clear()
                
        except Exception as e:
            logger.error(f"Error while subscribing users: {str(e)}", exc_info=True)
            messages.error(request, f"Error while subscribing users: {str(e)}")
            
    def subscribe_selected_users(self, request, queryset):
        """Action для подписки выбранных пользователей на выбранные типы рассылок"""
        try:
            total_subscribed = 0
            for subscription_type in queryset:
                # Получаем всех активных пользователей
                active_users = User.objects.filter(is_active=True)
                
                for user in active_users:
                    subscription, created = UserEmailSubscription.objects.get_or_create(
                        user=user,
                        subscription_type=subscription_type,
                        defaults={'is_subscribed': True, 'unsubscribe_token': str(uuid.uuid4())}
                    )
                    if created or not subscription.is_subscribed:
                        subscription.is_subscribed = True
                        subscription.save()
                        total_subscribed += 1
                        
            self.message_user(
                request,
                f"Successfully subscribed {total_subscribed} users to selected subscription types",
                messages.SUCCESS
            )
        except Exception as e:
            logger.error(f"Error in subscribe_selected_users action: {str(e)}", exc_info=True)
            self.message_user(
                request,
                f"Error subscribing users: {str(e)}",
                messages.ERROR
            )
    
    subscribe_selected_users.short_description = "Subscribe all active users to selected types"

@admin.register(UserEmailSubscription)
class UserEmailSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription_type', 'is_subscribed', 'updated_at')
    list_filter = ('subscription_type', 'is_subscribed')

@admin.register(SocialNetwork)
class SocialNetworkAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'icon')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name',
                'code',
                'is_active',
                'icon',
            )
        }),
        ('Действия', {
            'fields': (
                'available_actions',
            )
        }),
        ('Системная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    def save_model(self, request, obj, form, change):
        logger.info(f"""
            Saving SocialNetwork:
            Name: {obj.name}
            Code: {obj.code}
            Icon: {obj.icon}
            Is Active: {obj.is_active}
            Changed fields: {form.changed_data}
        """)
        super().save_model(request, obj, form, change)

        # --- Автосоздание ActionLanding для каждой связки SocialNetwork + ActionType ---
        from .models import ActionLanding
        from django.utils.text import slugify
        from django.db import transaction
        # Словарь правильных множественных форм
        action_plural = {
            'LIKE': 'Likes',
            'COMMENT': 'Comments',
            'REPOST': 'Reposts',
            'REPLY': 'Replies',
            'FOLLOW': 'Followers',
            'SAVE': 'Saves',
            'UPVOTE': 'Upvotes',
            'DOWNVOTE': 'Downvotes',
            'STAR': 'Stars',
            'WATCH': 'Watches',
            'CLAP': 'Claps',
            'CONNECT': 'Connects',
            'SUBSCRIBE': 'Subscribers',
            'RESTACK': 'Restacks',
            'UP': 'Ups',
            'DOWN': 'Downs',
            'INSTALL': 'Installs',
            'UNICORN': 'Unicorns',
            'FAVORITE': 'Favorites',
            'BOOST': 'Boosts',
            'SHARE': 'Shares',
        }
        def plural_action_name(action):
            return action_plural.get(action.code.upper(), action.name + 's')
        with transaction.atomic():
            # Получаем все выбранные available_actions
            actions = obj.available_actions.all()
            # --- Родительская страница (только соцсеть, без экшена) ---
            if actions:
                actions_names = [plural_action_name(a) for a in actions]
                actions_str = ', '.join(actions_names)
                parent_slug = slugify(obj.name)
                if not ActionLanding.objects.filter(social_network=obj, action__isnull=True).exists():
                    ActionLanding.objects.create(
                        title=f"Free {obj.name} Growth Tool - Get {actions_str} for free",
                        slug=parent_slug,
                        social_network=obj,
                        action=None
                    )
            # --- Для каждого экшена ---
            for action in actions:
                slug = f"{slugify(obj.name)}-{slugify(action.code)}"
                if ActionLanding.objects.filter(social_network=obj, action=action.code).exists():
                    continue
                plural_name = plural_action_name(action)
                ActionLanding.objects.create(
                    title=f"Get Free {obj.name} {plural_name} – Grow {obj.name} Tool – Safe, Instant, Totally Free",
                    slug=slug,
                    social_network=obj,
                    action=action.code
                )
        # Если нет экшенов, но родительской страницы тоже нет — создать только её
        if not actions:
            parent_slug = slugify(obj.name)
            if not ActionLanding.objects.filter(social_network=obj, action__isnull=True).exists():
                ActionLanding.objects.create(
                    title=f"Free {obj.name} Growth Tool",
                    slug=parent_slug,
                    social_network=obj,
                    action=None
                )

@admin.register(UserSocialProfile)
class UserSocialProfileAdmin(admin.ModelAdmin):
    list_display = (
        'username',
        'social_network',
        'is_verified',
        'followers_count',
        'following_count',
        'posts_count',
        'account_created_at',
        'last_sync_at'
    )
    list_filter = ('social_network', 'is_verified', 'verification_status')
    search_fields = ('username', 'user__email', 'social_id')
    readonly_fields = ('last_sync_at', 'created_at', 'updated_at')
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'user',
                'social_network',
                'username',
                'social_id',
                'profile_url',
                'avatar_url',
            )
        }),
        ('Верификация', {
            'fields': (
                'is_verified',
                'verification_status',
                'verification_date',
                'rejection_reason',
            )
        }),
        ('Статистика', {
            'fields': (
                'followers_count',
                'following_count',
                'posts_count',
                'account_created_at',
            )
        }),
        ('OAuth данные', {
            'fields': (
                'oauth_token',
                'oauth_token_secret',
            ),
            'classes': ('collapse',)  # Можно свернуть этот раздел
        }),
        ('Системная информация', {
            'fields': (
                'created_at',
                'updated_at',
                'last_sync_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def sync_profiles(self, request, queryset):
        for profile in queryset:
            try:
                profile.sync_profile_data()
            except Exception as e:
                self.message_user(
                    request,
                    f"Error syncing {profile}: {str(e)}",
                    level='ERROR'
                )
    sync_profiles.short_description = "Sync selected profiles"

    actions = ['export_unique_users_firebase_data', 'sync_profiles']
    
    def export_unique_users_firebase_data(self, request, queryset):
        """Экспортирует email и имена из Firebase для всех уникальных пользователей выбранных профилей"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="unique_users_firebase_data_{timestamp}.csv"'
        
        writer = csv.writer(response)
        
        # Заголовки CSV
        headers = [
            'User ID',
            'Firebase UID (Username)',
            'Firebase Email',
            'Firebase Display Name',
            'Email Disabled in Firebase',
            'Email Verified',
            'Chosen Country',
            'Social Profiles Count',
            'Social Networks',
            'Verified Profile URL',
        ]
        writer.writerow(headers)
        
        # Получаем уникальных пользователей из выбранных профилей
        unique_user_ids = queryset.values_list('user_id', flat=True).distinct()
        unique_users = User.objects.filter(id__in=unique_user_ids).select_related('userprofile')
        
        count = 0
        error_count = 0
        
        for user in unique_users:
            try:
                firebase_uid = user.username
                
                # Получаем данные из Firebase
                firebase_email = ''
                firebase_display_name = ''
                email_disabled = False
                email_verified = False
                firebase_error = ''
                
                if firebase_uid:
                    try:
                        firebase_user = auth.get_user(firebase_uid)
                        firebase_email = firebase_user.email or ''
                        firebase_display_name = firebase_user.display_name or ''
                        email_disabled = firebase_user.disabled if hasattr(firebase_user, 'disabled') else False
                        email_verified = firebase_user.email_verified if hasattr(firebase_user, 'email_verified') else False
                    except auth.UserNotFoundError:
                        firebase_error = 'User not found in Firebase'
                        logger.warning(f"[export_unique_users_firebase_data] Firebase user not found: {firebase_uid}")
                    except Exception as e:
                        firebase_error = f'Error: {str(e)[:50]}'
                        logger.error(f"[export_unique_users_firebase_data] Error getting Firebase user {firebase_uid}: {str(e)}")
                
                # Получаем информацию о социальных профилях пользователя
                user_profiles = queryset.filter(user=user)
                social_profiles_count = user_profiles.count()
                social_networks = ', '.join(user_profiles.values_list('social_network__name', flat=True).distinct())
                
                # Получаем chosen_country из UserProfile
                chosen_country = ''
                try:
                    if hasattr(user, 'userprofile') and user.userprofile:
                        chosen_country = user.userprofile.chosen_country or ''
                except Exception:
                    pass
                
                # Получаем ссылку на верифицированный профиль
                verified_profile_url = ''
                try:
                    verified_profile = user_profiles.filter(verification_status='VERIFIED').first()
                    if verified_profile and verified_profile.profile_url:
                        verified_profile_url = verified_profile.profile_url
                except Exception:
                    pass
                
                # Если email отключен, добавляем пометку
                email_display = firebase_email
                if email_disabled:
                    email_display = f"{firebase_email} [DISABLED - DO NOT SEND EMAIL]"
                elif firebase_error:
                    email_display = f"[ERROR: {firebase_error}]"
                
                # Формируем строку данных
                row = [
                    user.id,
                    firebase_uid,
                    email_display,
                    firebase_display_name,
                    'YES' if email_disabled else 'NO',
                    'YES' if email_verified else 'NO',
                    chosen_country,
                    social_profiles_count,
                    social_networks,
                    verified_profile_url,
                ]
                
                writer.writerow(row)
                count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(f"[export_unique_users_firebase_data] Error exporting user {getattr(user, 'id', '?')}: {str(e)}")
                continue
        
        logger.info(f"[export_unique_users_firebase_data] Exported {count} unique users to CSV (errors: {error_count})")
        if error_count > 0:
            self.message_user(
                request, 
                f'Successfully exported {count} unique users to CSV. {error_count} errors occurred.', 
                messages.WARNING
            )
        else:
            self.message_user(
                request, 
                f'Successfully exported {count} unique users to CSV', 
                messages.SUCCESS
            )
        return response
    
    export_unique_users_firebase_data.short_description = "📥 Export unique users Firebase data (email & name)"

    def save_model(self, request, obj, form, change):
        # Проверяем, был ли статус изменён на VERIFIED или REJECTED
        send_approval_email = False
        send_reject_email = False
        if change:
            old_obj = UserSocialProfile.objects.get(pk=obj.pk)
            if old_obj.verification_status != 'VERIFIED' and obj.verification_status == 'VERIFIED':
                send_approval_email = True
            if old_obj.verification_status != 'REJECTED' and obj.verification_status == 'REJECTED':
                send_reject_email = True
        elif obj.verification_status == 'VERIFIED':
            send_approval_email = True
        elif obj.verification_status == 'REJECTED':
            send_reject_email = True

        super().save_model(request, obj, form, change)

        if send_approval_email:
            try:
                user_email = obj.user.email
                if not user_email:
                    # Пробуем получить email из Firebase, если не заполнен
                    from firebase_admin import auth
                    firebase_user = auth.get_user(obj.user.username)
                    user_email = firebase_user.email
                if user_email:
                    email_service = EmailService()
                    plain_text = (
                        'Your profile has been approved!\n'
                        'You can now complete tasks and earn points: https://upvote.club/dashboard'
                    )
                    email_service.send_email(
                        to_email=user_email,
                        subject='Your profile has been approved!',
                        html_content=plain_text
                    )
                    logger.info(f"[Admin] Sent approval email to user {obj.user.username} ({user_email}) for social profile {obj.id}")
            except Exception as e:
                logger.error(f"[Admin] Error sending approval email for social profile {obj.id}: {str(e)}")

        if send_reject_email:
            try:
                user_email = obj.user.email
                if not user_email:
                    # Пробуем получить email из Firebase, если не заполнен
                    from firebase_admin import auth
                    firebase_user = auth.get_user(obj.user.username)
                    user_email = firebase_user.email
                if user_email:
                    email_service = EmailService()
                    
                    # Формируем текст письма в зависимости от причины отклонения
                    if obj.rejection_reason == 'NO_EMOJI':
                        html_content = (
                            '<p>Your social profile was <b>soft-rejected</b> because we could not find a finger print emoji 🧗‍♂️😄🤩🤖😛 on your BIO at profile page.</p>'
                            '<p>Please add emoji finger print 🧗‍♂️😄🤩🤖😛 to your profile BIO or display name and submit it again</p>'
                        )
                        subject = 'Your social profile was soft-rejected - No Emoji Finger Print added'
                    elif obj.rejection_reason == 'DOES_NOT_MEET_CRITERIA':
                        html_content = (
                            '<p>Your social profile was <b>rejected</b> because it does not meet our criteria. For detailed moderation criteria for each social network, please check our <a href="https://upvote.club/dashboard/moderation-criteria">moderation criteria</a></p>'
                        )
                        subject = 'Your social profile was rejected - Does not meet criteria'
                    else:
                        # Fallback для старых записей без указанной причины
                        html_content = (
                            '<p>Your social profile was <b>soft-rejected</b> for one or more of the following reasons:</p>'
                            '<ul>'
                            '<li>Your account is less than 3 months (90 days) old</li>'
                            '<li>Your account does not have an avatar</li>'
                            '<li>Your profile does not look like a real person, but rather a bot.</li>'
                            '<li>We could not find a finger print emoji 🧗‍♂️😄🤩🤖😛 on your profile page</li>'
                            '</ul>'
                            '<p>We value real accounts of real users. This gives the most impact for promotion. If an account is created just for liking, it does not provide any boost to our users. That is why we ask you to participate only with real accounts that you actually use.</p>'
                            '<p><b>Tip:</b> If your account is small but real and you are actively using it, you can also promote it on Upvote Club and grow it!</p>'
                            '<p>For detailed moderation criteria for each social network, please check our <a href="https://upvote.club/dashboard/moderation-criteria">moderation criteria page</a>.</p>'
                        )
                        subject = 'Your social profile was soft-rejected'
                    
                    email_service.send_email(
                        to_email=user_email,
                        subject=subject,
                        html_content=html_content
                    )
                    logger.info(f"[Admin] Sent rejection email to user {obj.user.username} ({user_email}) for social profile {obj.id} with reason: {obj.rejection_reason}")
                else:
                    logger.error(f"[Admin] No email found for user {obj.user.username} when trying to send rejection email for social profile {obj.id}")
            except Exception as e:
                logger.error(f"[Admin] Error sending rejection email for social profile {obj.id}: {str(e)}")

class LoggingModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        logger.info(f"""
        Admin saving model: {obj.__class__.__name__}
        User: {request.user}
        Changed fields: {form.changed_data}
        """)
        super().save_model(request, obj, form, change)

@admin.register(PostCategory)
class PostCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'post_count', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'description']
    
    def post_count(self, obj):
        return obj.blogpost_set.count()
    post_count.short_description = 'Posts'

@admin.register(BlogPost)
class BlogPostAdmin(MarkdownxModelAdmin):
    list_display = [
        'title',
        'category',
        'author',
        'status',
        'published_at',
        'email_sent',
        'image_preview'
    ]
    list_filter = ['status', 'category', 'tags', 'email_sent']
    search_fields = ['title', 'content', 'author__username']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['tags']
    readonly_fields = ['created_at', 'updated_at', 'email_sent']
    
    fieldsets = (
        ('Content', {
            'fields': ('title', 'slug', 'content', 'image')
        }),
        ('Classification', {
            'fields': ('category', 'tags')
        }),
        ('Publication', {
            'fields': ('status', 'author', 'published_at', 'send_email')
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at', 'email_sent'),
            'classes': ('collapse',)
        }),
    )
    
    class Media:
        css = {
            'all': ('admin/css/markdown-help.css',)
        }
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not obj:  # Если создается новый объект
            form.base_fields['author'].initial = request.user
            logger.info(f"Setting default author in form: {request.user.username}")
        return form
    
    def render_change_form(self, request, context, *args, **kwargs):
        # Добавляем markdown help в контекст
        markdown_help = """
        <div class="markdown-help">
            <h3>Markdown Guide</h3>
            <hr>
            <h4>Headers</h4>
            <pre>
# H1 Header
## H2 Header
### H3 Header</pre>
            
            <h4>Emphasis</h4>
            <pre>
*italic*
**bold**
***bold italic***</pre>
            
            <h4>Lists</h4>
            <pre>
- Unordered item
1. Ordered item</pre>
            
            <h4>Links</h4>
            <pre>[Link text](URL)</pre>
            
            <h4>Images</h4>
            <pre>![Alt text](image URL)</pre>
            
            <h4>Code</h4>
            <pre>`inline code`</pre>
            
            <h4>Blockquotes</h4>
            <pre>> This is a blockquote</pre>
        </div>
        """
        if 'media' not in context:
            context['media'] = forms.Media()
        
        context['media'] += forms.Media(css={
            'all': ('admin/css/markdown-help.css',)
        })
        
        extra = context.get('extra_context', {})
        extra['markdown_help'] = markdown_help
        context['extra_context'] = extra
        
        return super().render_change_form(request, context, *args, **kwargs)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px;"/>',
                obj.image.url
            )
        return '-'
    image_preview.short_description = 'Image'
    
    def save_model(self, request, obj, form, change):
        logger.info(f"""
            Saving blog post in admin:
            Title: {obj.title}
            Status: {obj.status}
            Author: {obj.author}
            Changed fields: {form.changed_data}
        """)
        super().save_model(request, obj, form, change)

@admin.register(TwitterServiceAccount)
class TwitterServiceAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'api_key_masked', 'is_active', 'last_used_at', 'rate_limit_reset')
    list_filter = ('is_active',)
    readonly_fields = ('last_used_at', 'rate_limit_reset')
    
    fields = (
        'api_key',
        'api_secret',
        'bearer_token',
        'is_active',
        'last_used_at',
        'rate_limit_reset'
    )

    def api_key_masked(self, obj):
        """Показывает замаскированный API ключ в списке"""
        if obj.api_key:
            return f"{obj.api_key[:6]}...{obj.api_key[-4:]}"
        return "-"
    api_key_masked.short_description = "API Key"

@admin.register(ActionType)
class ActionTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at']

@admin.register(TwitterUserMapping)
class TwitterUserMappingAdmin(admin.ModelAdmin):
    list_display = ('username', 'twitter_id', 'created_at', 'last_used_at')
    search_fields = ('username', 'twitter_id')
    readonly_fields = ('created_at', 'last_used_at')

class CustomAdminSite(admin.AdminSite):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('metrics/', self.admin_view(business_metrics), name='business_metrics'),
        ]
        return custom_urls + urls

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['business_metrics_url'] = 'admin/metrics/'
        return super().index(request, extra_context)

# Заменяем стандартный AdminSite на наш кастомный
admin.site.__class__ = CustomAdminSite

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'points',
        'amount',
        'status',
        'created_at',
        'notification_status',
        'payment_type',
        'subscription_period_type',
        'is_task_purchase',
        'get_created_task',
        'get_referrer_url',
        'get_landing_url',
        'get_device_type',
        'get_os_info',
        'get_first_task_social_network',
        'payment_id',
        'stripe_session_id',
        'stripe_subscription_id',
        'attempt_count',
    )
    
    list_filter = (
        'status',
        'payment_type',
        'subscription_period_type',
        'is_task_purchase',
        'user_has_trial_before',
        'created_at',
        'attempt_count',
        'pending_notification_sent',
    )
    
    search_fields = (
        'user__username',
        'payment_id',
        'stripe_session_id',
        'stripe_subscription_id',
        'stripe_payment_intent_id',
        'stripe_customer_id',
        'last_payment_error',
        'user__userprofile__referrer_url',
        'user__userprofile__landing_url',
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user',
                'points',
                'amount',
                'status',
                'payment_type',
                'subscription_period_type',
                'is_task_purchase',
                'task',
                'payment_id',
            )
        }),
        ('Stripe Information', {
            'fields': (
                'stripe_session_id',
                'stripe_subscription_id',
                'stripe_payment_intent_id',
                'stripe_customer_id',
                'stripe_metadata',
            )
        }),
        ('Subscription Details', {
            'fields': (
                'user_has_trial_before',
                'trial_end_date',
                'subscription_period_start',
                'subscription_period_end',
            )
        }),
        ('Payment Retry Information', {
            'fields': (
                'attempt_count',
                'next_payment_attempt',
                'last_payment_error',
                'last_webhook_received',
            )
        }),
        ('User Tracking Info', {
            'fields': (
                'get_referrer_url_display',
                'get_landing_url_display',
                'get_device_type_display',
                'get_os_info_display',
                'get_first_task_social_network_display',
            ),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = (
        'created_at',
        'get_referrer_url_display',
        'get_landing_url_display',
        'get_device_type_display',
        'get_os_info_display',
        'get_first_task_social_network_display',
    )
    ordering = ('-created_at',)
    
    def get_queryset(self, request):
        """Оптимизация запросов для админки"""
        return super().get_queryset(request).select_related(
            'user',
            'user__userprofile',
            'task',
            'task__social_network'
        )

    def get_readonly_fields(self, request, obj=None):
        # Делаем поля только для чтения, если объект уже существует
        if obj:
            return self.readonly_fields + (
                'subscription_period_type',
                'subscription_period_start',
                'subscription_period_end',
                'user_has_trial_before',
                'trial_end_date',
                'stripe_session_id',
                'stripe_subscription_id',
                'stripe_payment_intent_id',
                'stripe_customer_id',
                'stripe_metadata',
            )
        return self.readonly_fields

    def notification_status(self, obj):
        """
        Показывает статус отправки уведомления о платеже
        """
        if obj.pending_notification_sent:
            sent_time = obj.pending_notification_sent_at
            if sent_time:
                sent_time_str = sent_time.strftime("%d-%m-%Y %H:%M")
                return format_html('<span style="color: green;">✓ Sent at {}</span>', sent_time_str)
            else:
                return format_html('<span style="color: green;">✓ Sent</span>')
        else:
            if obj.status == 'PENDING':
                return format_html('<span style="color: orange;">⚠️ Not sent</span>')
            else:
                return format_html('<span style="color: grey;">N/A</span>')
    
    notification_status.short_description = 'Notification'
    notification_status.admin_order_field = 'pending_notification_sent'
    
    def get_created_task(self, obj):
        """Отображает информацию о созданном задании"""
        if obj.task:
            return format_html(
                '<a href="/admin/api/task/{}/change/" target="_blank">Task #{}</a><br/>'
                '<small>{} - {} ({})</small>',
                obj.task.id,
                obj.task.id,
                obj.task.social_network.name,
                obj.task.type,
                obj.task.status
            )
        return '-'
    get_created_task.short_description = 'Created Task'
    get_created_task.admin_order_field = 'task__id'
    
    def get_referrer_url(self, obj):
        """Получаем referrer_url из UserProfile пользователя"""
        try:
            referrer = obj.user.userprofile.referrer_url
            if referrer:
                truncated = referrer[:50] + '...' if len(referrer) > 50 else referrer
                return format_html('<span title="{}">{}</span>', referrer, truncated)
            return '-'
        except Exception:
            return '-'
    get_referrer_url.short_description = 'Referrer URL'
    get_referrer_url.admin_order_field = 'user__userprofile__referrer_url'
    
    def get_landing_url(self, obj):
        """Получаем landing_url из UserProfile пользователя"""
        try:
            landing = obj.user.userprofile.landing_url
            if landing:
                truncated = landing[:50] + '...' if len(landing) > 50 else landing
                return format_html('<span title="{}">{}</span>', landing, truncated)
            return '-'
        except Exception:
            return '-'
    get_landing_url.short_description = 'Landing URL'
    get_landing_url.admin_order_field = 'user__userprofile__landing_url'
    
    def get_device_type(self, obj):
        """Получаем device_type из UserProfile пользователя"""
        try:
            device = obj.user.userprofile.device_type
            return device if device else '-'
        except Exception:
            return '-'
    get_device_type.short_description = 'Device'
    get_device_type.admin_order_field = 'user__userprofile__device_type'
    
    def get_os_info(self, obj):
        """Получаем OS информацию из UserProfile пользователя"""
        try:
            os_name = obj.user.userprofile.os_name or '-'
            os_version = obj.user.userprofile.os_version or '-'
            if os_name != '-' or os_version != '-':
                return format_html('{} {}', os_name, os_version)
            return '-'
        except Exception:
            return '-'
    get_os_info.short_description = 'OS'
    
    def get_first_task_social_network(self, obj):
        """Получаем социальную сеть первого задания, созданного пользователем"""
        try:
            from .models import Task
            first_task = Task.objects.filter(
                creator=obj.user
            ).order_by('created_at').select_related('social_network').first()
            
            if first_task and first_task.social_network:
                return format_html(
                    '<strong>{}</strong><br/><small>{}</small>',
                    first_task.social_network.name,
                    first_task.social_network.code
                )
            return '-'
        except Exception:
            return '-'
    get_first_task_social_network.short_description = 'First Task SN'
    
    def get_referrer_url_display(self, obj):
        """Отображение referrer_url на странице редактирования"""
        try:
            referrer = obj.user.userprofile.referrer_url
            if referrer:
                return format_html('<a href="{}" target="_blank">{}</a>', referrer, referrer)
            return 'Not set'
        except Exception:
            return 'Not set'
    get_referrer_url_display.short_description = 'Referrer URL'
    
    def get_landing_url_display(self, obj):
        """Отображение landing_url на странице редактирования"""
        try:
            landing = obj.user.userprofile.landing_url
            if landing:
                return format_html('<a href="{}" target="_blank">{}</a>', landing, landing)
            return 'Not set'
        except Exception:
            return 'Not set'
    get_landing_url_display.short_description = 'Landing URL'
    
    def get_device_type_display(self, obj):
        """Отображение device_type на странице редактирования"""
        try:
            device = obj.user.userprofile.device_type
            return device if device else 'Not set'
        except Exception:
            return 'Not set'
    get_device_type_display.short_description = 'Device Type'
    
    def get_os_info_display(self, obj):
        """Отображение OS информации на странице редактирования"""
        try:
            os_name = obj.user.userprofile.os_name or 'Unknown'
            os_version = obj.user.userprofile.os_version or ''
            if os_version:
                return f'{os_name} {os_version}'
            return os_name
        except Exception:
            return 'Not set'
    get_os_info_display.short_description = 'OS Information'
    
    def get_first_task_social_network_display(self, obj):
        """Отображение социальной сети первого задания на странице редактирования"""
        try:
            from .models import Task
            first_task = Task.objects.filter(
                creator=obj.user
            ).order_by('created_at').select_related('social_network').first()
            
            if first_task and first_task.social_network:
                return format_html(
                    '<strong>{}</strong> ({})',
                    first_task.social_network.name,
                    first_task.social_network.code
                )
            return 'No tasks created'
        except Exception:
            return 'Not set'
    get_first_task_social_network_display.short_description = 'First Task Social Network'
    
    actions = ['export_to_csv']
    
    def export_to_csv(self, request, queryset):
        """Экспортирует выбранные PaymentTransaction в CSV"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="payment_transactions_export_{timestamp}.csv"'
        
        writer = csv.writer(response)
        
        # Заголовки CSV
        headers = [
            'ID',
            'User ID',
            'User Username',
            'Points',
            'Amount',
            'Payment ID',
            'Status',
            'Created At',
            'Stripe Session ID',
            'Stripe Subscription ID',
            'Stripe Payment Intent ID',
            'Stripe Customer ID',
            'Payment Type',
            'Subscription Period Type',
            'User Has Trial Before',
            'Trial End Date',
            'Subscription Period Start',
            'Subscription Period End',
            'Is Task Purchase',
            'Task ID',
            'Task Social Network',
            'Task Type',
            'Attempt Count',
            'Next Payment Attempt',
            'Last Payment Error',
            'Pending Notification Sent',
            'Pending Notification Sent At',
            'Last Webhook Received',
            # User Tracking Info
            'Referrer URL',
            'Landing URL',
            'Device Type',
            'OS Name',
            'OS Version',
            'First Task Social Network Name',
            'First Task Social Network Code',
        ]
        writer.writerow(headers)
        
        # Оптимизируем запросы
        transactions = queryset.select_related(
            'user',
            'user__userprofile',
            'task',
            'task__social_network'
        )
        
        # Получаем первые задачи пользователей для оптимизации
        from .models import Task as TaskModel
        user_ids = list(transactions.values_list('user_id', flat=True).distinct())
        first_tasks = {}
        if user_ids:
            # Используем distinct с ordering для получения первой задачи каждого пользователя
            for user_id in user_ids:
                first_task = TaskModel.objects.filter(
                    creator_id=user_id
                ).order_by('created_at').select_related('social_network').first()
                if first_task:
                    first_tasks[user_id] = first_task
        
        count = 0
        for transaction in transactions:
            try:
                # Получаем данные пользователя
                user = transaction.user
                user_profile = getattr(user, 'userprofile', None)
                
                # Получаем данные задачи
                task = transaction.task
                task_sn_name = ''
                task_type = ''
                if task:
                    task_sn_name = task.social_network.name if task.social_network else ''
                    task_type = task.type
                
                # Получаем первую задачу пользователя
                first_task_sn_name = ''
                first_task_sn_code = ''
                first_task = first_tasks.get(user.id)
                if first_task and first_task.social_network:
                    first_task_sn_name = first_task.social_network.name
                    first_task_sn_code = first_task.social_network.code
                
                # Формируем строку данных
                row = [
                    transaction.id,
                    user.id,
                    user.username,
                    transaction.points,
                    str(transaction.amount),
                    transaction.payment_id,
                    transaction.status,
                    transaction.created_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.created_at else '',
                    transaction.stripe_session_id or '',
                    transaction.stripe_subscription_id or '',
                    transaction.stripe_payment_intent_id or '',
                    transaction.stripe_customer_id or '',
                    transaction.payment_type,
                    transaction.subscription_period_type or '',
                    transaction.user_has_trial_before,
                    transaction.trial_end_date.strftime('%Y-%m-%d %H:%M:%S') if transaction.trial_end_date else '',
                    transaction.subscription_period_start.strftime('%Y-%m-%d %H:%M:%S') if transaction.subscription_period_start else '',
                    transaction.subscription_period_end.strftime('%Y-%m-%d %H:%M:%S') if transaction.subscription_period_end else '',
                    transaction.is_task_purchase,
                    task.id if task else '',
                    task_sn_name,
                    task_type,
                    transaction.attempt_count,
                    transaction.next_payment_attempt.strftime('%Y-%m-%d %H:%M:%S') if transaction.next_payment_attempt else '',
                    transaction.last_payment_error or '',
                    transaction.pending_notification_sent,
                    transaction.pending_notification_sent_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.pending_notification_sent_at else '',
                    transaction.last_webhook_received.strftime('%Y-%m-%d %H:%M:%S') if transaction.last_webhook_received else '',
                    # User Tracking Info
                    user_profile.referrer_url if user_profile and user_profile.referrer_url else '',
                    user_profile.landing_url if user_profile and user_profile.landing_url else '',
                    user_profile.device_type if user_profile and user_profile.device_type else '',
                    user_profile.os_name if user_profile and user_profile.os_name else '',
                    user_profile.os_version if user_profile and user_profile.os_version else '',
                    first_task_sn_name,
                    first_task_sn_code,
                ]
                
                writer.writerow(row)
                count += 1
                
            except Exception as e:
                logger.error(f"[export_to_csv] Error exporting transaction {getattr(transaction, 'id', '?')}: {str(e)}")
                continue
        
        logger.info(f"[export_to_csv] Exported {count} payment transactions to CSV")
        self.message_user(request, f'Successfully exported {count} payment transactions to CSV', messages.SUCCESS)
        return response
    
    export_to_csv.short_description = "📥 Download selected payment transactions as CSV"

@admin.register(TaskReport)
class TaskReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'task', 'reason', 'created_at')
    list_filter = ('reason', 'created_at')
    search_fields = ('user__username', 'task__id', 'reason')
    raw_id_fields = ('user', 'task')
    date_hierarchy = 'created_at'

# --- Утилита для отправки одного лендинга в Google Indexing API ---
def submit_actionlanding_to_google(landing, domain=None):
    """
    Отправляет только корректный URL текущего лендинга в Google Indexing API.
    - /{social_network_code}
    - /{social_network_code}/{action}
    - /{social_network_code}/{action}/{slug}
    """
    from django.conf import settings
    from django.utils import timezone
    if not domain:
        domain = (
            getattr(settings, 'FRONTEND_URL', None)
            or 'https://upvote.club'
        ).rstrip('/')
    if not landing.social_network:
        return False, 'Landing missing social_network'
    sn_code = landing.social_network.code.lower()
    if not landing.action:
        # Родительский лендинг соцсети
        url = f"{domain}/{sn_code}"
    else:
        action_code = landing.action.lower()
        # Если слаг совпадает с самим action или со формой "{social}-{action}",
        # считаем это экшеновым лендингом без дополнительного слага
        is_action_page_slug = (
            landing.slug == action_code or
            landing.slug == f"{sn_code}-{action_code}"
        )
        if is_action_page_slug:
            # Экшеновый лендинг
            url = f"{domain}/{sn_code}/{action_code}"
        else:
            # Конкретный лендинг
            url = f"{domain}/{sn_code}/{action_code}/{landing.slug}"
    try:
        if getattr(settings, 'GOOGLE_INDEXING_CREDENTIALS_INFO', None):
            credentials = service_account.Credentials.from_service_account_info(
                settings.GOOGLE_INDEXING_CREDENTIALS_INFO,
                scopes=['https://www.googleapis.com/auth/indexing']
            )
        else:
            credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_API_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/indexing']
            )
        service = build('indexing', 'v3', credentials=credentials)
        service.urlNotifications().publish(
            body={'url': url, 'type': 'URL_UPDATED'}
        ).execute()
        landing.is_indexed = True
        landing.indexed_at = timezone.now()
        landing.indexing_error = None
        landing.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])
        return [(url, True, None)], None
    except Exception as e:
        landing.is_indexed = False
        landing.indexed_at = None
        landing.indexing_error = str(e)
        landing.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])
        return [(url, False, str(e))], str(e)

# --- Утилита для отправки BuyLanding в Google Indexing API ---
def submit_buylanding_to_google(landing, domain=None):
    """
    Отправляет URL BuyLanding в Google Indexing API.
    Формат URL: /{social_network_code}/{slug}
    """
    from django.conf import settings
    from django.utils import timezone
    if not domain:
        domain = (
            getattr(settings, 'FRONTEND_URL', None)
            or 'https://upvote.club'
        ).rstrip('/')
    if not landing.social_network:
        return False, 'Landing missing social_network'
    sn_code = landing.social_network.code.lower()
    url = f"{domain}/{sn_code}/{landing.slug}"
    
    try:
        if getattr(settings, 'GOOGLE_INDEXING_CREDENTIALS_INFO', None):
            credentials = service_account.Credentials.from_service_account_info(
                settings.GOOGLE_INDEXING_CREDENTIALS_INFO,
                scopes=['https://www.googleapis.com/auth/indexing']
            )
        else:
            credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_API_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/indexing']
            )
        service = build('indexing', 'v3', credentials=credentials)
        service.urlNotifications().publish(
            body={'url': url, 'type': 'URL_UPDATED'}
        ).execute()
        landing.is_indexed = True
        landing.indexed_at = timezone.now()
        landing.indexing_error = None
        landing.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])
        return True, None
    except Exception as e:
        landing.is_indexed = False
        landing.indexed_at = None
        landing.indexing_error = str(e)
        landing.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])
        return False, str(e)

@admin.register(ActionLanding)
class ActionLandingAdmin(admin.ModelAdmin):
    change_list_template = 'admin/actionlanding_change_list.html'
    
    list_display = (
        'title',
        'slug',
        'social_network',
        'action',
        'redirect_url',
        'is_indexed',
        'created_at',
        'has_meta_title',
        'has_meta_description',
        'has_h1',
        'has_content',
        'has_short_description',
        'has_faq',
        'has_how_it_works',
        'has_why_upvote_club_best'
    )
    search_fields = ('title', 'slug', 'short_description')
    list_filter = ('social_network', 'action', 'is_indexed')
    readonly_fields = ('created_at', 'updated_at', 'indexed_at')
    filter_horizontal = ('reviews',)
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'social_network', 'action', 'redirect_url')
        }),
        ('Hero Landing', {
            'fields': ('h1', 'short_description', 'content')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description')
        }),
        ('Why Upvote Club Best', {
            'fields': ('why_upvote_club_best_title', 'why_upvote_club_best')
        }),
        ('How It Works', {
            'fields': ('how_it_works_title', 'how_it_works')
        }),
        ('Reviews', {
            'fields': ('reviews_section_title', 'reviews')
        }),
        ('FAQ', {
            'fields': ('faq_section_title', 'faq')
        }),
        ('Indexing', {
            'fields': ('is_indexed', 'indexed_at', 'indexing_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    save_on_top = True
    prepopulated_fields = {'slug': ('title',)}
    actions = ['clear_cache_for_selected']

    def has_meta_title(self, obj):
        """Проверяет заполненность meta_title"""
        return format_html('✓' if obj.meta_title else '✗')
    has_meta_title.short_description = 'Meta Title'

    def has_meta_description(self, obj):
        """Проверяет заполненность meta_description"""
        return format_html('✓' if obj.meta_description else '✗')
    has_meta_description.short_description = 'Meta Desc'

    def has_h1(self, obj):
        """Проверяет заполненность h1"""
        return format_html('✓' if obj.h1 else '✗')
    has_h1.short_description = 'H1'

    def has_content(self, obj):
        """Проверяет заполненность content"""
        return format_html('✓' if obj.content else '✗')
    has_content.short_description = 'Content'

    def has_short_description(self, obj):
        """Проверяет заполненность short_description"""
        return format_html('✓' if obj.short_description else '✗')
    has_short_description.short_description = 'Short Desc'

    def has_faq(self, obj):
        """Проверяет заполненность faq"""
        return format_html('✓' if obj.faq else '✗')
    has_faq.short_description = 'FAQ'

    def has_how_it_works(self, obj):
        """Проверяет заполненность how_it_works"""
        return format_html('✓' if obj.how_it_works else '✗')
    has_how_it_works.short_description = 'How It Works'

    def has_why_upvote_club_best(self, obj):
        """Проверяет заполненность why_upvote_club_best"""
        return format_html('✓' if obj.why_upvote_club_best else '✗')
    has_why_upvote_club_best.short_description = 'Why Best'

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Фильтрует отзывы по социальной сети лендинга"""
        if db_field.name == "reviews":
            # Получаем текущий объект из request (если редактируем)
            obj_id = request.resolver_match.kwargs.get('object_id')
            social_network_id = None
            
            if obj_id:
                try:
                    landing = ActionLanding.objects.get(pk=obj_id)
                    if landing.social_network:
                        social_network_id = landing.social_network.id
                except ActionLanding.DoesNotExist:
                    pass
            
            # Проверяем данные из POST запроса (при создании/редактировании)
            if request.method == 'POST' and not social_network_id:
                social_network_id = request.POST.get('social_network')
                if social_network_id:
                    try:
                        social_network_id = int(social_network_id)
                    except (ValueError, TypeError):
                        social_network_id = None
            
            if social_network_id:
                # Фильтруем отзывы только по этой социальной сети
                kwargs["queryset"] = Review.objects.filter(
                    social_network_id=social_network_id
                ).select_related('user', 'social_network', 'action', 'task').order_by('-created_at')
            else:
                # Если социальная сеть не выбрана, показываем все отзывы
                kwargs["queryset"] = Review.objects.all().select_related('user', 'social_network', 'action', 'task').order_by('-created_at')
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-csv/', self.admin_site.admin_view(self.import_csv_view), name='api_actionlanding_import_csv'),
        ]
        return custom_urls + urls
    
    def import_csv_view(self, request):
        """View для импорта CSV файла"""
        from django.shortcuts import render, redirect
        
        if request.method == 'POST':
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                messages.error(request, 'Please select a CSV file')
                return redirect('admin:api_actionlanding_changelist')
            
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File must be a CSV file')
                return redirect('admin:api_actionlanding_changelist')
            
            try:
                # Читаем CSV файл
                decoded_file = csv_file.read().decode('utf-8-sig')  # utf-8-sig для правильной обработки BOM
                csv_reader = csv.DictReader(decoded_file.splitlines())
                
                created_count = 0
                updated_count = 0
                error_count = 0
                errors = []
                
                # Все доступные поля ActionLanding
                available_fields = [
                    'title', 'slug', 'social_network', 'action',
                    'meta_title', 'meta_description', 'h1', 'content',
                    'short_description',
                    'redirect_url', 'faq'
                ]
                
                for row_num, row in enumerate(csv_reader, start=2):  # Начинаем с 2, т.к. строка 1 - заголовки
                    try:
                        slug = row.get('slug', '').strip()
                        if not slug:
                            errors.append(f"Row {row_num}: slug is required")
                            error_count += 1
                            continue
                        
                        # Получаем или создаем запись по slug
                        landing, created = ActionLanding.objects.get_or_create(
                            slug=slug,
                            defaults={}
                        )
                        
                        # Обновляем поля из CSV
                        for field in available_fields:
                            if field in row:
                                value = row[field].strip() if row[field] else None
                                
                                # Специальная обработка для social_network
                                if field == 'social_network':
                                    if value:
                                        try:
                                            # Может быть ID, code или name
                                            if value.isdigit():
                                                social_network = SocialNetwork.objects.get(id=int(value))
                                            else:
                                                social_network = SocialNetwork.objects.filter(
                                                    Q(code=value) | Q(name=value)
                                                ).first()
                                            if social_network:
                                                landing.social_network = social_network
                                            else:
                                                errors.append(f"Row {row_num}: Social network '{value}' not found")
                                        except Exception as e:
                                            errors.append(f"Row {row_num}: Error setting social_network '{value}': {str(e)}")
                                    else:
                                        landing.social_network = None
                                
                                # Специальная обработка для FAQ (JSON)
                                elif field == 'faq':
                                    if value:
                                        try:
                                            landing.faq = json.loads(value)
                                        except json.JSONDecodeError:
                                            errors.append(f"Row {row_num}: Invalid JSON in FAQ field")
                                            landing.faq = None
                                    else:
                                        landing.faq = None
                                
                                # Для остальных полей просто устанавливаем значение
                                elif hasattr(landing, field):
                                    # Для пустых значений устанавливаем None для nullable полей
                                    if value == '':
                                        # Проверяем, является ли поле nullable
                                        field_obj = ActionLanding._meta.get_field(field)
                                        if field_obj.null or field_obj.blank:
                                            setattr(landing, field, None)
                                        else:
                                            # Для обязательных полей оставляем как есть или устанавливаем значение по умолчанию
                                            if field == 'title' and not landing.title:
                                                setattr(landing, field, slug)  # Используем slug как fallback для title
                                    else:
                                        setattr(landing, field, value)
                        
                        # Если title не установлен, используем slug
                        if not landing.title:
                            landing.title = slug
                        
                        landing.save()
                        
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                            
                    except Exception as e:
                        error_count += 1
                        errors.append(f"Row {row_num}: {str(e)}")
                        logger.error(f"[import_csv] Error processing row {row_num}: {str(e)}")
                
                # Формируем сообщение об успехе
                success_msg = f'Import completed: {created_count} created, {updated_count} updated'
                if error_count > 0:
                    success_msg += f', {error_count} errors'
                if errors:
                    errors_msg = 'Errors:\n' + '\n'.join(errors[:10])  # Показываем только первые 10 ошибок
                    if len(errors) > 10:
                        errors_msg += f'\n... and {len(errors) - 10} more errors'
                    messages.warning(request, errors_msg)
                
                messages.success(request, success_msg)
                logger.info(f"[import_csv] Import completed: {created_count} created, {updated_count} updated, {error_count} errors")
                
            except Exception as e:
                logger.error(f"[import_csv] Error importing CSV: {str(e)}")
                messages.error(request, f'Error importing CSV: {str(e)}')
            
            return redirect('admin:api_actionlanding_changelist')
        
        # GET запрос - показываем форму загрузки
        context = {
            **self.admin_site.each_context(request),
            'title': 'Import ActionLanding from CSV',
            'opts': ActionLanding._meta,
            'has_change_permission': self.has_change_permission(request),
        }
        return render(request, 'admin/actionlanding_import_csv.html', context)
    
    def clear_cache_for_selected(self, request, queryset):
        """
        Clear cache for selected ActionLanding entries
        """
        from django.core.cache import cache
        
        cache.delete('action_landings_list_all_all')
        
        count = 0
        for landing in queryset:
            cache.delete(f'action_landing_{landing.slug}')
            cache.delete(f'action_landing_by_path_{landing.slug}')
            
            if landing.social_network and landing.action:
                social_code = landing.social_network.code.lower()
                action_code = landing.action.upper()
                path_key = f'{social_code}/{action_code.lower()}'
                cache.delete(f'action_landing_by_path_{path_key}')
                cache.delete(f'action_landings_list_{social_code}_{action_code}')
            
            count += 1
        
        self.message_user(
            request,
            f'Cache cleared for {count} action landing(s).',
            level=messages.SUCCESS
        )
    
    clear_cache_for_selected.short_description = 'Clear cache for selected landings'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        results, global_error = submit_actionlanding_to_google(obj)
        if global_error:
            self.message_user(request, f'Google Indexing API error: {global_error}', level=messages.ERROR)
        else:
            msg = 'Google Indexing API result:\n'
            for url, ok, err in results:
                if ok:
                    msg += f'✓ {url}\n'
                else:
                    msg += f'✗ {url} — {err}\n'
            self.message_user(request, msg, level=messages.INFO)

@admin.register(BuyLanding)
class BuyLandingAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'slug',
        'social_network',
        'action',
        'price_per_action',
        'is_indexed',
        'created_at',
        'updated_at'
    )
    search_fields = (
        'title', 
        'slug', 
        'description', 
        'short_description',
        'meta_title',
        'meta_description',
        'h1'
    )
    list_filter = ('social_network', 'action', 'is_indexed', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'indexed_at')
    filter_horizontal = ('reviews',)
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'social_network', 'action')
        }),
        ('Content', {
            'fields': ('h1', 'description', 'short_description')
        }),
        ('Price & Quantity', {
            'fields': ('price_per_action', 'quantity_steps'),
            'description': 'Configure pricing and available quantity options'
        }),
        ('SEO Meta Data', {
            'fields': ('meta_title', 'meta_description', 'og_title', 'og_description'),
            'classes': ('collapse',),
            'description': 'SEO and Open Graph metadata for search engines and social media'
        }),
        ('How It Works Section', {
            'fields': ('how_it_works_title', 'how_it_works'),
            'classes': ('collapse',),
            'description': 'JSON format: [{"emoji": "🧗‍♂️", "title": "Title", "text": "Description"}]'
        }),
        ('FAQ Section', {
            'fields': ('faq_section_title', 'faq'),
            'classes': ('collapse',),
            'description': 'JSON format: [{"q": "Question?", "a": "Answer"}]'
        }),
        ('Reviews', {
            'fields': ('reviews_section_title', 'reviews'),
            'classes': ('collapse',)
        }),
        ('Indexing', {
            'fields': ('is_indexed', 'indexed_at', 'indexing_error'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    save_on_top = True
    prepopulated_fields = {'slug': ('title',)}
    actions = ['submit_to_google_index', 'clear_cache_for_selected']
    
    def clear_cache_for_selected(self, request, queryset):
        """
        Clear cache for selected BuyLanding entries
        """
        from django.core.cache import cache
        
        cache.delete('buy_landings_list')
        cache.delete('buy_landings_all')
        
        count = 0
        for landing in queryset:
            cache.delete(f'buy_landing_{landing.slug}')
            count += 1
        
        self.message_user(
            request,
            f'Cache cleared for {count} buy landing(s).',
            level=messages.SUCCESS
        )
    
    clear_cache_for_selected.short_description = 'Clear cache for selected landings'
    
    def submit_to_google_index(self, request, queryset):
        """
        Отправляет выбранные BuyLanding в Google Indexing API
        """
        from django.conf import settings
        domain = (
            getattr(settings, 'FRONTEND_URL', None)
            or 'https://upvote.club'
        ).rstrip('/')
        
        import time
        
        success_count = 0
        error_count = 0
        errors = []
        total = queryset.count()
        
        for i, landing in enumerate(queryset, 1):
            success, error = submit_buylanding_to_google(landing, domain)
            if success:
                success_count += 1
                logger.info(f"[BuyLandingAdmin] [{i}/{total}] Successfully submitted to Google Index: {landing.slug}")
            else:
                error_count += 1
                error_msg = f"{landing.slug}: {error}"
                errors.append(error_msg)
                logger.error(f"[BuyLandingAdmin] [{i}/{total}] Error submitting to Google Index: {error_msg}")
            
            # Добавляем задержку между запросами (кроме последнего)
            if i < total:
                time.sleep(1)
        
        if success_count > 0:
            self.message_user(
                request,
                f'Successfully submitted {success_count} landing(s) to Google Index.',
                level=messages.SUCCESS
            )
        
        if error_count > 0:
            error_message = f'Failed to submit {error_count} landing(s):\n' + '\n'.join(errors[:10])
            if len(errors) > 10:
                error_message += f'\n... and {len(errors) - 10} more errors'
            self.message_user(
                request,
                error_message,
                level=messages.ERROR
            )
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Фильтруем отзывы по социальной сети buy лендинга."""
        if db_field.name == "reviews":
            obj_id = request.resolver_match.kwargs.get('object_id')
            social_network_id = None
            if obj_id:
                try:
                    landing = BuyLanding.objects.get(pk=obj_id)
                    social_network_id = landing.social_network_id
                except BuyLanding.DoesNotExist:
                    social_network_id = None
            if request.method == 'POST' and not social_network_id:
                social_network_id = request.POST.get('social_network')
                try:
                    social_network_id = int(social_network_id)
                except (TypeError, ValueError):
                    social_network_id = None
            if social_network_id:
                kwargs["queryset"] = Review.objects.filter(
                    social_network_id=social_network_id
                ).select_related('user', 'social_network', 'action', 'task').order_by('-created_at')
            else:
                kwargs["queryset"] = Review.objects.all().select_related('user', 'social_network', 'action', 'task').order_by('-created_at')
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    submit_to_google_index.short_description = 'Submit selected landings to Google Index'

# Можно закомментировать существующую регистрацию
# @admin.register(Landing)
# class LandingAdmin(admin.ModelAdmin):
#     ...

# Расширяем стандартную админку User
class CustomUserAdmin(UserAdmin):
    search_fields = ['username']  # Поиск по Firebase UID
    ordering = ['username']

# Перерегистрируем модель User с нашей кастомной админкой
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user',
        'get_completed_tasks_count',
        'get_verified_social_profiles_count',
        'amount_usd',
        'points_sold', 
        'withdrawal_method',
        'withdrawal_address',
        'status',
        'created_at',
        'processed_at'
    ]
    
    list_filter = [
        'status',
        'withdrawal_method',
        'created_at',
        'processed_at'
    ]
    
    search_fields = [
        'user__username',
        'withdrawal_address',
        'transaction_id',
        'id'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'points_sold',
        'amount_usd'
    ]
    
    # Оптимизация: select_related для связанных объектов
    list_select_related = ['user', 'user__userprofile']
    
    # Оптимизация: уменьшаем количество записей на странице
    list_per_page = 50
    
    # Оптимизация: показываем "Показать все" только для небольших списков
    list_max_show_all = 200
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user',
                'amount_usd',
                'points_sold',
                'withdrawal_method',
                'withdrawal_address'
            )
        }),
        ('Status & Processing', {
            'fields': (
                'status',
                'created_at',
                'updated_at',
                'processed_at',
                'transaction_id'
            )
        }),
        ('Admin Notes', {
            'fields': (
                'admin_notes',
            )
        })
    )
    
    actions = ['mark_as_processing', 'mark_as_completed', 'mark_as_failed']
    
    def get_queryset(self, request):
        """Оптимизация запросов для админки"""
        qs = super().get_queryset(request)
        
        # Используем select_related для user и userprofile
        qs = qs.select_related('user', 'user__userprofile')
        
        # Добавляем аннотации только для списка (не для детальной страницы)
        if not request.resolver_match.kwargs.get('object_id'):
            qs = qs.annotate(
                completed_tasks_count=Count('user__taskcompletion', distinct=True),
                verified_social_profiles_count=Count(
                    'user__social_profiles',
                    filter=Q(user__social_profiles__verification_status='VERIFIED'),
                    distinct=True
                )
            )
        
        return qs
    
    def get_completed_tasks_count(self, obj):
        """Получает количество выполненных заданий для пользователя"""
        if hasattr(obj, 'completed_tasks_count'):
            return obj.completed_tasks_count
        # Fallback для детальной страницы
        return TaskCompletion.objects.filter(user=obj.user).count()
    get_completed_tasks_count.short_description = 'Completed Tasks'
    get_completed_tasks_count.admin_order_field = 'completed_tasks_count'
    
    def get_verified_social_profiles_count(self, obj):
        """Получает количество верифицированных социальных сетей для пользователя"""
        if hasattr(obj, 'verified_social_profiles_count'):
            return obj.verified_social_profiles_count
        # Fallback для детальной страницы
        return UserSocialProfile.objects.filter(
            user=obj.user,
            verification_status='VERIFIED'
        ).count()
    get_verified_social_profiles_count.short_description = 'Verified Social Networks'
    get_verified_social_profiles_count.admin_order_field = 'verified_social_profiles_count'
    
    def mark_as_processing(self, request, queryset):
        """Отметить как обрабатывается"""
        updated = queryset.filter(status='PENDING').update(status='PROCESSING')
        self.message_user(request, f'{updated} withdrawal(s) marked as processing.')
    mark_as_processing.short_description = 'Mark selected withdrawals as processing'
    
    def mark_as_completed(self, request, queryset):
        """Отметить как завершено"""
        from api.utils.email_utils import send_withdrawal_completed_email
        
        updated_count = 0
        email_sent_count = 0
        email_failed_count = 0
        
        # Фильтруем только PENDING и PROCESSING
        queryset = queryset.filter(status__in=['PENDING', 'PROCESSING'])
        
        for withdrawal in queryset:
            old_status = withdrawal.status
            withdrawal.status = 'COMPLETED'
            if not withdrawal.processed_at:
                withdrawal.processed_at = timezone.now()
            withdrawal.save()
            updated_count += 1
            
            # Отправляем email
            try:
                if send_withdrawal_completed_email(withdrawal):
                    email_sent_count += 1
                    logger.info(f"Email sent for withdrawal #{withdrawal.id}")
                else:
                    email_failed_count += 1
                    logger.warning(f"Email failed for withdrawal #{withdrawal.id}")
            except Exception as e:
                email_failed_count += 1
                logger.error(f"Email error for withdrawal #{withdrawal.id}: {str(e)}")
        
        # Сообщение с детальной статистикой
        message = f'{updated_count} withdrawal(s) marked as completed. '
        if email_sent_count > 0:
            message += f'✅ {email_sent_count} email(s) sent. '
        if email_failed_count > 0:
            message += f'⚠️ {email_failed_count} email(s) failed.'
        
        self.message_user(request, message)
    mark_as_completed.short_description = 'Mark selected withdrawals as completed'
    
    def mark_as_failed(self, request, queryset):
        """Отметить как неудачно"""
        updated = queryset.filter(status__in=['PENDING', 'PROCESSING']).update(status='FAILED')
        self.message_user(request, f'{updated} withdrawal(s) marked as failed.')
    mark_as_failed.short_description = 'Mark selected withdrawals as failed'


# Кастомизация главной страницы админки для добавления ссылки на фильтр пользователей
from django.template.response import TemplateResponse

original_index = admin.site.index

def custom_admin_index(request, extra_context=None):
    """Кастомная главная страница админки с дополнительными ссылками"""
    try:
        response = original_index(request, extra_context)
        
        if isinstance(response, TemplateResponse):
            custom_links = [
                {
                    'title': '🔍 Фильтрация пользователей', 
                    'url': '/admin/user-filter/',
                    'description': 'Расширенная фильтрация пользователей с экспортом в CSV'
                }
            ]
            
            if not hasattr(response, 'context_data') or response.context_data is None:
                response.context_data = {}
            response.context_data['custom_tools'] = custom_links
        
        return response
    except Exception as e:
        logger.error(f"[custom_admin_index] Error in custom admin index: {str(e)}", exc_info=True)
        return original_index(request, extra_context)

@admin.register(OnboardingProgress)
class OnboardingProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'chosen_country', 'account_type', 'created_at', 'updated_at')
    search_fields = ('user__username', 'chosen_country', 'account_type')
    list_filter = ('account_type',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['export_to_csv_and_email']

    def export_to_csv_and_email(self, request, queryset):
        """
        Экспортирует выбранные OnboardingProgress в CSV и отправляет по email.
        Оптимизирован для работы с большими объемами данных (20k-50k записей).
        """
        import csv
        import io
        from django.utils import timezone
        
        try:
            # Создаем CSV в памяти
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Заголовки CSV
            headers = [
                'Chosen Country',
                'Account Type',
                'Social Networks',
                'Actions',
                'Goal Description',
                'Created At',
                'Updated At'
            ]
            writer.writerow(headers)
            
            # Записываем данные итеративно для экономии памяти
            records_count = 0
            for progress in queryset.select_related('user').iterator(chunk_size=1000):
                
                # Форматируем social_networks
                social_networks_str = ''
                if progress.social_networks:
                    if isinstance(progress.social_networks, list):
                        social_networks_str = ', '.join(progress.social_networks)
                    else:
                        social_networks_str = str(progress.social_networks)
                
                # Форматируем actions
                actions_str = ''
                if progress.actions:
                    if isinstance(progress.actions, dict):
                        actions_list = []
                        for network, action_list in progress.actions.items():
                            actions_list.append(f"{network}: {', '.join(action_list)}")
                        actions_str = '; '.join(actions_list)
                    else:
                        actions_str = str(progress.actions)
                
                row = [
                    progress.chosen_country or '',
                    progress.account_type or '',
                    social_networks_str,
                    actions_str,
                    (progress.goal_description or '').replace('\n', ' ').replace('\r', ''),
                    progress.created_at.strftime('%Y-%m-%d %H:%M:%S') if progress.created_at else '',
                    progress.updated_at.strftime('%Y-%m-%d %H:%M:%S') if progress.updated_at else ''
                ]
                writer.writerow(row)
                records_count += 1
            
            # Получаем CSV контент
            csv_content = output.getvalue()
            output.close()
            
            # Отправляем email
            email_service = EmailService()
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = f'onboarding_progress_{timestamp}.csv'
            
            subject = f'Onboarding Progress Export - {records_count} records'
            html_content = f"""
            <html>
            <body>
                <h2>Onboarding Progress Export</h2>
                <p>Export completed successfully.</p>
                <ul>
                    <li><strong>Records exported:</strong> {records_count}</li>
                    <li><strong>Export date:</strong> {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
                    <li><strong>Exported by:</strong> {request.user.username}</li>
                </ul>
                <p>The CSV file is attached to this email.</p>
                <br>
                <p>Best regards,<br>Upvote.Club Team</p>
            </body>
            </html>
            """
            
            # Список получателей
            recipients = [
                'yesupvote@gmail.com',
                'alexey.guberman@gmail.com',
                'yes@upvote.club'
            ]
            
            # Отправляем каждому получателю
            success_count = 0
            for recipient in recipients:
                attachments = [(filename, csv_content, 'text/csv')]
                if email_service.send_email(
                    to_email=recipient,
                    subject=subject,
                    html_content=html_content,
                    attachments=attachments
                ):
                    success_count += 1
                    logger.info(f"CSV exported and sent to {recipient}")
                else:
                    logger.error(f"Failed to send CSV to {recipient}")
            
            if success_count > 0:
                self.message_user(
                    request,
                    f'Successfully exported {records_count} records and sent to {success_count}/{len(recipients)} recipients.',
                    messages.SUCCESS
                )
            else:
                self.message_user(
                    request,
                    f'Exported {records_count} records but failed to send emails.',
                    messages.ERROR
                )
            
        except Exception as e:
            logger.error(f"Error exporting OnboardingProgress: {e}", exc_info=True)
            self.message_user(
                request,
                f'Error during export: {str(e)}',
                messages.ERROR
            )
    
    export_to_csv_and_email.short_description = "Export selected to CSV and send via email"

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'social_network', 'action', 'actions_count', 'task', 
        'get_rating_display', 'comment', 'get_user_country',
        'created_at', 'updated_at'
    ]
    list_filter = ['social_network', 'action', 'rating', 'created_at']
    search_fields = ['user__username', 'task__id', 'comment']
    readonly_fields = ['created_at', 'updated_at']

    def get_rating_display(self, obj):
        """Отображает рейтинг в виде звезд"""
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: gold;">{}</span> ({})', stars, obj.rating)
    get_rating_display.short_description = 'Rating'
    get_rating_display.admin_order_field = 'rating'
    
    def get_user_country(self, obj):
        try:
            country = getattr(getattr(obj.user, 'userprofile', None), 'chosen_country', None)
            return country or '-'
        except Exception:
            return '-'
    get_user_country.short_description = 'Country'
    get_user_country.admin_order_field = 'user__userprofile__chosen_country'

@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """
    Админка для управления API ключами.
    Ключ показывается только в скрытом виде (первые 8 символов + ...)
    """
    list_display = [
        'id',
        'user',
        'get_masked_key',
        'name',
        'is_active',
        'last_used_at',
        'created_at',
        'expires_at',
        'is_expired_display'
    ]
    list_filter = [
        'is_active',
        'created_at',
        'last_used_at',
        'expires_at'
    ]
    search_fields = [
        'user__username',
        'name',
        'key_hash'
    ]
    readonly_fields = [
        'key_hash',
        'created_at',
        'last_used_at',
        'get_masked_key_full'
    ]
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'name', 'is_active')
        }),
        ('Ключ (скрыт)', {
            'fields': ('get_masked_key_full', 'key_hash'),
            'description': 'API ключ хранится в зашифрованном виде. Полный ключ показывается только при создании.'
        }),
        ('Даты', {
            'fields': ('created_at', 'last_used_at', 'expires_at')
        }),
    )
    
    def get_masked_key(self, obj):
        """Показывает замаскированный хеш в списке"""
        if obj.key_hash:
            # Показываем первые 8 символов хеша + ...
            masked = obj.key_hash[:8] + '...' + obj.key_hash[-4:] if len(obj.key_hash) > 12 else obj.key_hash[:8] + '...'
            return format_html('<code>{}</code>', masked)
        return '-'
    get_masked_key.short_description = 'Key Hash (masked)'
    
    def get_masked_key_full(self, obj):
        """Показывает замаскированный хеш в форме редактирования"""
        if obj.key_hash:
            # Показываем первые 8 символов хеша + ...
            masked = obj.key_hash[:8] + '...' + obj.key_hash[-4:] if len(obj.key_hash) > 12 else obj.key_hash[:8] + '...'
            return format_html(
                '<code style="font-size: 12px; background: #f5f5f5; padding: 5px; border-radius: 3px;">{}</code><br>'
                '<small style="color: #666;">Оригинальный ключ не хранится в базе данных (только хеш)</small>',
                masked
            )
        return format_html('<em>Хеш ключа не найден</em>')
    get_masked_key_full.short_description = 'Key Hash'
    
    def is_expired_display(self, obj):
        """Показывает статус истечения срока действия"""
        if obj.expires_at is None:
            return format_html('<span style="color: #666;">Never</span>')
        if obj.is_expired():
            return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Active</span>')
    is_expired_display.short_description = 'Expiration Status'
    
    def get_readonly_fields(self, request, obj=None):
        """Делаем key_hash всегда readonly"""
        readonly = list(self.readonly_fields)
        return readonly


@admin.register(CacheEntry)
class CacheEntryAdmin(admin.ModelAdmin):
    """
    Admin for viewing and managing cache entries
    """
    list_display = (
        'cache_key',
        'get_type',
        'get_size_display',
        'expires',
        'is_expired_display',
        'created_time'
    )
    list_filter = ('expires',)
    search_fields = ('cache_key',)
    readonly_fields = ('cache_key', 'value', 'expires')
    actions = ['delete_selected_cache']
    
    def get_type(self, obj):
        """Show cache type"""
        return obj.get_type()
    get_type.short_description = 'Type'
    
    def get_size_display(self, obj):
        """Show cache size in KB/MB"""
        size_kb = obj.get_size()
        if size_kb > 1024:
            return f'{size_kb/1024:.2f} MB'
        return f'{size_kb:.2f} KB'
    get_size_display.short_description = 'Size'
    
    def is_expired_display(self, obj):
        """Show if cache is expired"""
        is_expired = obj.is_expired()
        if is_expired:
            return format_html('<span style="color: red;">❌ Expired</span>')
        return format_html('<span style="color: green;">✅ Active</span>')
    is_expired_display.short_description = 'Status'
    
    def created_time(self, obj):
        """Calculate approximate creation time"""
        from django.utils import timezone
        created = obj.expires - timezone.timedelta(seconds=31536000)
        return created
    created_time.short_description = 'Created At'
    
    def delete_selected_cache(self, request, queryset):
        """
        Delete selected cache entries
        """
        count = queryset.count()
        queryset.delete()
        
        self.message_user(
            request,
            f'Successfully deleted {count} cache entry(ies).',
            level=messages.SUCCESS
        )
    
    delete_selected_cache.short_description = 'Delete selected cache entries'
    
    def has_add_permission(self, request):
        """Prevent manual creation of cache entries"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of cache entries"""
        return False