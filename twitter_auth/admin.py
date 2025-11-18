from django.contrib import admin
from .models import TwitterUserAuthorization, TwitterActionLog
from django.utils.html import format_html

@admin.register(TwitterUserAuthorization)
class TwitterUserAuthorizationAdmin(admin.ModelAdmin):
    list_display = (
        'user_profile',
        'service_account',
        'authorized_at',
        'twitter_account',
        'is_active'
    )
    list_filter = ('service_account', 'authorized_at')
    search_fields = ('user_profile__user__username', 'user_profile__twitter_account')
    readonly_fields = ('authorized_at',)

    def twitter_account(self, obj):
        return obj.user_profile.twitter_account
    twitter_account.short_description = "Twitter Account"

    def is_active(self, obj):
        return obj.service_account.is_active
    is_active.boolean = True
    is_active.short_description = "Service Account Active"

@admin.register(TwitterActionLog)
class TwitterActionLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'user_profile',
        'get_twitter_account',
        'action_type',
        'get_service_account',
        'status',
        'get_error_message',
        'get_target_user'
    )
    
    list_filter = (
        'status',
        'action_type',
        'service_account',
        'created_at'
    )
    
    search_fields = (
        'user_profile__twitter_account',
        'target_user',
        'error_message'
    )
    
    readonly_fields = ('created_at',)
    
    def get_twitter_account(self, obj):
        return obj.user_profile.twitter_account
    get_twitter_account.short_description = 'Twitter Account'
    
    def get_service_account(self, obj):
        return f"Twitter API Account {obj.service_account.id}"
    get_service_account.short_description = 'Service Account'
    
    def get_error_message(self, obj):
        if obj.status == 'ERROR' and obj.error_message:
            return format_html(
                '<span style="color: red;">{}</span>',
                obj.error_message[:100] + ('...' if len(obj.error_message) > 100 else '')
            )
        return '-'
    get_error_message.short_description = 'Error'
    
    def get_target_user(self, obj):
        if obj.target_user:
            if 'twitter.com' in obj.target_user or 'x.com' in obj.target_user:
                return format_html(
                    '<a href="{}" target="_blank">{}</a>',
                    obj.target_user,
                    obj.target_user.split('/')[-1]
                )
            return obj.target_user
        return '-'
    get_target_user.short_description = 'Target User'
