from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from api.views import UserProfileViewSet, TaskViewSet, BlogPostViewSet, UserSocialProfileViewSet
from api.views import ReviewViewSet, BuyLandingViewSet
from .admin_views import business_metrics
from .payment import process_points_purchase
from .views import (
    report_task, get_sitemap_data, create_subscription, withdrawal_info, 
    create_withdrawal, cancel_withdrawal, update_withdrawal_addresses, 
    task_completion_stats, create_subscription_intent, confirm_subscription,
    get_verified_accounts_count
)
from .stripe_webhooks import stripe_webhook
from .views_landings import ActionLandingViewSet
from .views_median_speed import MedianSpeedView

router = DefaultRouter()
router.register(r'profile', views.UserProfileViewSet)
router.register(r'tasks', views.TaskViewSet)
router.register(r'blog-posts', views.BlogPostViewSet)
router.register(r'landings', ActionLandingViewSet, basename='action-landing')
router.register(r'buy-landings', BuyLandingViewSet, basename='buy-landing')
router.register(r'social-profiles', views.UserSocialProfileViewSet, basename='social-profile')
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', views.register_user, name='register'),
    path('complete-task/<int:task_id>/', views.complete_task, name='complete-task'),
    path('balance/', views.get_balance, name='get-balance'),
    path('login/', views.login_user, name='login'),
    path('create-task/', views.create_task, name='create-task'),
    path('add-balance/', views.add_balance, name='add-balance'),
    # removed: verify-twitter endpoint
    path('verify-invite/', views.verify_invite_code, name='verify_invite_code'),
    path('update-user-plan/', views.update_user_plan, name='update_user_plan'),
    path('generate-invite-code/', views.generate_invite_code, name='generate_invite_code'),
    path('active-invite-code/', views.get_active_invite_code, name='get_active_invite_code'),
    path('tasks/my_tasks/', views.TaskViewSet.as_view({'get': 'my_tasks'}), name='my-tasks'),
    path('purchase-points/', views.purchase_points, name='purchase-points'),
    path('markdownx/', include('markdownx.urls')),
    path('admin/metrics/', business_metrics, name='business_metrics'),
    path('payments/points/purchase/', process_points_purchase, name='process_points_purchase'),
    path('refresh-token/', views.refresh_token, name='refresh-token'),
    path('report-task/', report_task, name='report-task'),
    path('sitemap-data/', get_sitemap_data, name='sitemap-data'),
    path('game/', views.game, name='game'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),
    path('create-payment-intent', views.create_payment_intent, name='create_payment_intent_legacy'),
    path('stripe/create-payment-intent', views.create_payment_intent, name='create_payment_intent'),
    path('stripe/create-subscription/', create_subscription, name='create_subscription'),
    path('stripe/create-subscription-intent/', create_subscription_intent, name='create_subscription_intent'),
    path('stripe/confirm-subscription/', confirm_subscription, name='confirm_subscription'),
    path('subscription/info/', views.subscription_info, name='subscription_info'),
    path('invited-users/', views.get_invited_users, name='invited-users'),
    path('update-profile/', views.update_user_profile, name='update_user_profile'),
    # Withdrawal endpoints
    path('withdrawal/info/', withdrawal_info, name='withdrawal_info'),
    path('withdrawal/create/', create_withdrawal, name='create_withdrawal'),
    path('withdrawal/<int:withdrawal_id>/cancel/', cancel_withdrawal, name='cancel_withdrawal'),
    path('withdrawal/addresses/', update_withdrawal_addresses, name='update_withdrawal_addresses'),
    path('withdrawal/addresses', update_withdrawal_addresses, name='update_withdrawal_addresses_no_slash'),
    
    # Task completion stats
    path('task-completion-stats/', task_completion_stats, name='task_completion_stats'),
    path('verify-social-profile/', views.verify_social_profile, name='verify_social_profile'),
    path('tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('points-available-for-purchase/', views.points_available_for_purchase, name='points_available_for_purchase'),
    path('verified-accounts-count/', get_verified_accounts_count, name='verified_accounts_count'),
    path('onboarding-progress/', views.onboarding_progress, name='onboarding_progress'),
    path('save-referrer-tracking/', views.save_referrer_tracking, name='save_referrer_tracking'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
    # Median speed API endpoint
    path('median-speed/', MedianSpeedView.as_view(), name='median_speed'),
]