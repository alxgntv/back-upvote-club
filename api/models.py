from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver
import logging
from django.db import transaction
import uuid
import tweepy
from django.conf import settings
from django.template.loader import render_to_string
from django.db import models

class UserProfile(models.Model):
    DISCOUNT_RATES = {
        'FREE': 0,
        'MEMBER': 0,
        'BUDDY': 20,
        'MATE': 40
    }
    
    _is_updating = False
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    twitter_account = models.CharField(max_length=255, null=True, blank=True, unique=True)
    balance = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=[
        ('FREE', 'Free'),
        ('MEMBER', 'Member'),
        ('BUDDY', 'Buddy'),
        ('MATE', 'Mate')
    ], default='FREE')
    country_code = models.CharField(max_length=10, null=True, blank=True, help_text='ISO 3166-1 alpha-2 country code')
    chrome_extension_status = models.BooleanField(default=False)
    twitter_verification_status = models.CharField(max_length=256, choices=[
        ('NOT_CONFIRMED', 'Not Confirmed'),
        ('NOT_MATCHING_CRITERIA', 'Not Matching Criteria'),
        ('CONFIRMED', 'Confirmed')
    ], default='NOT_CONFIRMED')
    twitter_verification_date = models.DateTimeField(null=True, blank=True)
    twitter_oauth_token = models.CharField(max_length=255, blank=True, null=True)
    twitter_oauth_token_secret = models.CharField(max_length=255, blank=True, null=True)
    twitter_user_id = models.CharField(max_length=255, blank=True, null=True)
    twitter_screen_name = models.CharField(max_length=255, blank=True, null=True)
    invite_code = models.ForeignKey('InviteCode', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profile')
    available_invites = models.IntegerField(default=2)
    trial_start_date = models.DateTimeField(null=True, blank=True)
    available_tasks = models.IntegerField(default=0)
    last_tasks_update = models.DateTimeField(default=timezone.now)
    daily_task_limit = models.IntegerField(default=0)
    auto_actions_enabled = models.BooleanField(default=False)
    last_auto_action_at = models.DateTimeField(null=True, blank=True)
    completed_tasks_count = models.IntegerField(default=0)
    bonus_tasks_completed = models.IntegerField(default=0, help_text='Number of bonus tasks completed')
    game_rewards_claimed = models.IntegerField(default=0, help_text='Number of game rewards claimed by user')
    last_reward_at_task_count = models.IntegerField(default=0, help_text='Number of completed bonus tasks when last reward was claimed')
    invited_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='invited_users',
        help_text='User who invited this user'
    )
    is_ambassador = models.BooleanField(
        default=False,
        verbose_name='Ambassador',
        help_text='Whether user is an ambassador'
    )
    paypal_address = models.EmailField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='PayPal Address',
        help_text='PayPal email address for payments'
    )
    usdt_address = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='USDT Address',
        help_text='USDT wallet address for payments'
    )
    is_affiliate_partner = models.BooleanField(
        default=False,
        verbose_name='Affiliate Partner',
        help_text='Whether user is an affiliate partner'
    )
    chosen_country = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        verbose_name='Chosen Country',
        help_text='Country chosen by user (ISO 3166-1 alpha-2 country code)'
    )
    stripe_client_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Stripe Client ID',
        help_text='Stripe client identifier'
    )
    
    # Referrer tracking fields
    referrer_url = models.TextField(
        null=True,
        blank=True,
        verbose_name='Referrer URL',
        help_text='URL where user came from'
    )
    landing_url = models.TextField(
        null=True,
        blank=True,
        verbose_name='Landing URL',
        help_text='First page user visited on the site'
    )
    referrer_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Referrer Timestamp',
        help_text='When user first visited the site'
    )
    referrer_user_agent = models.TextField(
        null=True,
        blank=True,
        verbose_name='Referrer User Agent',
        help_text='User agent when user first visited'
    )

    # Device/OS tracking fields
    device_type = models.TextField(
        null=True,
        blank=True,
        verbose_name='Device Type',
        help_text='Device category: mobile, tablet, desktop'
    )
    os_name = models.TextField(
        null=True,
        blank=True,
        verbose_name='OS Name',
        help_text='Operating system name'
    )
    os_version = models.TextField(
        null=True,
        blank=True,
        verbose_name='OS Version',
        help_text='Operating system version'
    )
    black_friday_subscribed = models.BooleanField(
        default=False,
        verbose_name='Black Friday Subscribed',
        help_text='Whether user subscribed to Black Friday deal notifications'
    )
    welcome_email_sent = models.BooleanField(
        default=False,
        verbose_name='Welcome email sent',
        help_text='Whether welcome/confirmation email was sent'
    )
    welcome_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Welcome email sent at',
        help_text='Timestamp when welcome/confirmation email was sent'
    )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if not self._is_updating:
            try:
                self._is_updating = True
                
                if is_new:
                    self.available_tasks = self.get_daily_task_limit()
                    self.last_tasks_update = timezone.now()
                    
                super().save(*args, **kwargs)
            finally:
                self._is_updating = False
        else:
            super().save(*args, **kwargs)

    def get_daily_task_limit(self):
        if self.status == 'FREE':
            return 2
        elif self.status == 'MEMBER':
            return 1
        elif self.status == 'BUDDY':
            return 10
        elif self.status == 'MATE':
            return 10000
        return 0

    def update_available_tasks(self, save=True):
        if self.status == 'FREE':
            return False
        
        daily_limit = self.get_daily_task_limit()
        self.available_tasks = daily_limit
        
        if save:
            try:
                self._is_updating = True
                self.save(update_fields=['available_tasks'])
            finally:
                self._is_updating = False
            
        return True

    def __str__(self):
        return self.user.username

    def decrease_available_tasks(self):
        if self.available_tasks <= 0:
            return False
        
        try:
            with transaction.atomic():
                profile = UserProfile.objects.select_for_update().get(pk=self.pk)
                profile.available_tasks -= 1
                profile.save(update_fields=['available_tasks'])
                
                self.available_tasks = profile.available_tasks
                return True
        except Exception:
            return False

    def create_unlimited_invite_code(self):
        try:
            existing_invite = InviteCode.objects.filter(
                creator=self.user,
                status='ACTIVE'
            ).first()
            
            if existing_invite:
                return existing_invite
                
            invite_code = InviteCode.objects.create(
                code=str(uuid.uuid4())[:8],
                creator=self.user,
                status='ACTIVE',
                max_uses=0
            )
            return invite_code
            
        except Exception:
            return None

    def get_discount_rate(self):
        return self.DISCOUNT_RATES.get(self.status, 0)
    
    def calculate_task_cost(self, base_price, actions_required):
        original_cost = base_price * actions_required
        discount_rate = self.get_discount_rate()
        discount_amount = (original_cost * discount_rate) / 100
        final_cost = original_cost - discount_amount
        
        return final_cost, original_cost

    def get_completed_tasks_count(self):
        """Возвращает общее количество выполненных заданий пользователем"""
        return TaskCompletion.objects.filter(user=self.user).count()

    def get_available_tasks_for_completion(self):
        """Возвращает количество доступных для выполнения заданий"""
        from django.db.models import Exists, OuterRef
        
        # Получаем задания, которые пользователь еще не выполнял
        available_tasks = Task.objects.filter(
            status='ACTIVE'
        ).exclude(
            creator=self.user
        ).exclude(
            Exists(
                TaskCompletion.objects.filter(
                    task=OuterRef('pk'),
                    user=self.user
                )
            )
        ).exclude(
            Exists(
                TaskReport.objects.filter(
                    task=OuterRef('pk'),
                    user=self.user
                )
            )
        ).count()
        
        return available_tasks

    def get_potential_earnings(self):
        """Возвращает сумму возможного заработка за выполнение доступных заданий"""
        from django.db.models import Exists, OuterRef, Sum
        
        # Получаем задания, которые пользователь еще не выполнял
        available_tasks = Task.objects.filter(
            status='ACTIVE'
        ).exclude(
            creator=self.user
        ).exclude(
            Exists(
                TaskCompletion.objects.filter(
                    task=OuterRef('pk'),
                    user=self.user
                )
            )
        ).exclude(
            Exists(
                TaskReport.objects.filter(
                    task=OuterRef('pk'),
                    user=self.user
                )
            )
        )
        
        # Считаем потенциальный заработок (половина от цены за каждое задание)
        total_potential = available_tasks.aggregate(
            total=Sum('price')
        )['total'] or 0
        
        return total_potential / 2  # Делим на 2, так как награда - половина от цены задания

@receiver(pre_save, sender=UserProfile)
def update_tasks_on_status_change(sender, instance, **kwargs):
    try:
        if instance.pk:
            old_instance = UserProfile.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                new_daily_limit = instance.get_daily_task_limit()
                
                if new_daily_limit < old_instance.available_tasks:
                    instance.available_tasks = new_daily_limit
                else:
                    instance.update_available_tasks(save=False)
                
                instance.daily_task_limit = new_daily_limit
                
    except UserProfile.DoesNotExist:
        instance.update_available_tasks(save=False)
        instance.daily_task_limit = instance.get_daily_task_limit()
    except Exception:
        pass

class InviteCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=[('ACTIVE', 'Active'), ('USED', 'Used')], default='ACTIVE')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_invite_codes')
    used_by = models.ManyToManyField(User, related_name='used_invite_codes', blank=True)
    max_uses = models.IntegerField(default=2)
    uses_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite Code: {self.code} (Status: {self.status}, Uses: {self.uses_count}/{self.max_uses})"

    def is_valid(self):
        return self.status == 'ACTIVE' and (self.max_uses == 0 or self.uses_count < self.max_uses)

class Task(models.Model):
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks')
    social_network = models.ForeignKey('SocialNetwork', on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=[
        ('LIKE', 'Like'),
        ('REPOST', 'Repost'),
        ('COMMENT', 'Comment'),
        ('FOLLOW', 'Follow'),
        ('SAVE', 'Save'),
        ('BOOST', 'Boost'),
        ('FAVORITE', 'Favorite'),
        ('REPLY', 'Reply'),
        ('CLAP', 'Clap'),
        ('RESTACK', 'Restack'),
        ('UPVOTE', 'Upvote'),
        ('DOWNVOTE', 'Downvote'),
        ('UP', 'Up'),
        ('DOWN', 'Down'),
        ('STAR', 'Star'),
        ('WATCH', 'Watch'),
        ('CONNECT', 'Connect'),
        ('UNICORN', 'Unicorn'),
        ('INSTALL', 'Install'),
        ('SHARE', 'Share'),
    ])
    task_type = models.CharField(
        max_length=20,
        choices=[
            ('ENGAGEMENT', 'Engagement'),
            ('CROWD', 'Crowd'),
        ],
        null=True,
        blank=True,
        verbose_name='Task Type',
        help_text='Type of task: Engagement or Crowd'
    )
    post_url = models.URLField(max_length=1000)
    price = models.IntegerField()
    actions_required = models.IntegerField()
    actions_completed = models.IntegerField(default=0)
    # Бонусные действия, добавляемые системой (бесплатные для создателя)
    bonus_actions = models.IntegerField(default=0)
    bonus_actions_completed = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=[
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('DELETED', 'Deleted')
    ], default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_duration = models.DurationField(null=True, blank=True)
    original_price = models.IntegerField()
    target_user_id = models.CharField(max_length=50, null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_send_error = models.TextField(null=True, blank=True)
    creation_email_sent = models.BooleanField(
        default=False,
        verbose_name='Creation email sent',
        help_text='Whether task creation email was sent'
    )
    creation_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Creation email sent at',
        help_text='Timestamp when task creation email was sent'
    )
    creation_email_send_error = models.TextField(
        null=True,
        blank=True,
        verbose_name='Creation email send error',
        help_text='Last error while sending creation email'
    )
    is_pinned = models.BooleanField(default=False, verbose_name='Pin at the top', help_text='If checked, this task will always be shown at the top of the list')
    # Показывать ли расширенный вид задачи на фронте
    longview = models.BooleanField(default=False, verbose_name='Long view', help_text='If checked, show extended task view in UI')

    # Для задач типа COMMENT: использовать осмысленные комментарии от заказчика
    meaningful_comment = models.BooleanField(default=False, verbose_name='Meaningful comment', help_text='If enabled, use provided comments list for users to post')
    meaningful_comments = models.JSONField(null=True, blank=True, verbose_name='Comments list (JSON)', help_text='JSON array of comments: [{"id": "unique", "text": "comment text", "sent": false}]')
    
    DELETION_REASONS = [
        ('LINK_UNAVAILABLE', 'Link Unavailable'),
        ('COMMUNITY_RULES', 'Violates Community Rules'),
        ('USER_REQUEST', 'User Request'),
        ('DOUBLE_ACCOUNT', 'Double Account'),
        ('AUTO_CLOSE_24H', 'Auto closed after 24h (system)'),
    ]
    
    deletion_reason = models.CharField(
        max_length=50,
        choices=DELETION_REASONS,
        null=True,
        blank=True,
        help_text='Reason for task deletion'
    )

    def log_email_status(self, success: bool, error_message: str = None):
        try:
            self.email_sent = success
            self.email_sent_at = timezone.now() if success else None
            self.email_send_error = error_message if not success else None
            self.save(update_fields=['email_sent', 'email_sent_at', 'email_send_error'])
        except Exception:
            pass

    def log_creation_email_status(self, success: bool, error_message: str = None):
        try:
            self.creation_email_sent = success
            self.creation_email_sent_at = timezone.now() if success else None
            self.creation_email_send_error = error_message if not success else None
            self.save(update_fields=['creation_email_sent', 'creation_email_sent_at', 'creation_email_send_error'])
        except Exception:
            pass

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['social_network', 'type']),
            models.Index(fields=['post_url']),
            models.Index(fields=['task_type']),
        ]

    def complete(self):
        now = timezone.now()
        self.status = 'COMPLETED'
        self.completed_at = now
        if self.created_at:
            self.completion_duration = now - self.created_at
        self.save()

    def save(self, *args, **kwargs):
        # Отключили автопин: теперь is_pinned управляется только явным выбором на фронте/админке
        super().save(*args, **kwargs)

class CrowdTask(models.Model):
    """
    Модель для комментариев, привязанных к заданию.
    Используется для задач типа COMMENT с meaningful_comment=True.
    """
    STATUS_CHOICES = [
        ('SEARCHING', 'Searching'),
        ('IN_PROGRESS', 'In Progress'),
        ('PENDING_REVIEW', 'Pending Review'),
        ('COMPLETED', 'Completed'),
    ]
    
    task = models.ForeignKey(
        'Task',
        on_delete=models.CASCADE,
        related_name='crowd_tasks',
        verbose_name='Task',
        help_text='Task this comment belongs to'
    )
    text = models.TextField(
        verbose_name='Comment Text',
        help_text='Text of the comment'
    )
    url = models.URLField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name='URL',
        help_text='URL to verify task completion'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SEARCHING',
        verbose_name='Status',
        help_text='Status of the crowd task'
    )
    sent = models.BooleanField(
        default=False,
        verbose_name='Sent',
        help_text='Whether this comment has been used/sent'
    )
    confirmed_by_parser = models.BooleanField(
        default=False,
        verbose_name='Confirmed by Parser',
        help_text='Whether this task was confirmed by parser'
    )
    parser_log = models.TextField(
        null=True,
        blank=True,
        verbose_name='Parser Log',
        help_text='Log message from parser verification'
    )
    confirmed_by_user = models.BooleanField(
        default=False,
        verbose_name='Confirmed by User',
        help_text='Whether this task was confirmed by user'
    )
    user_log = models.TextField(
        null=True,
        blank=True,
        verbose_name='User Log',
        help_text='Log message from user verification'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_crowd_tasks',
        verbose_name='Assigned To',
        help_text='User who assigned this task to PENDING_REVIEW status'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )

    class Meta:
        verbose_name = 'Crowd Task'
        verbose_name_plural = 'Crowd Tasks'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['task', 'sent']),
            models.Index(fields=['task', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['confirmed_by_parser']),
            models.Index(fields=['confirmed_by_user']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        task_id = self.task.id if self.task else 'N/A'
        text_preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        return f"CrowdTask for Task #{task_id}: {text_preview}"

class TaskCompletion(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='completions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    post_url = models.CharField(max_length=1000, null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    is_auto = models.BooleanField(default=False)

    class Meta:
        unique_together = ('task', 'user', 'action')
        indexes = [
            models.Index(fields=['user', 'task']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.task.id}"

class EmailSubscriptionType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    subscribe_all_users = models.BooleanField(
        default=False,
        verbose_name="Subscribe all users",
        help_text="If checked, all active users who haven't unsubscribed from any mailing will be subscribed"
    )
    users_to_subscribe = models.ManyToManyField(
        User,
        blank=True,
        verbose_name="Users to subscribe",
        help_text="Select users to subscribe to this mailing type",
        related_name='subscription_types_to_subscribe'
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Email Subscription Type"
        verbose_name_plural = "Email Subscription Types"

class UserEmailSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subscription_type = models.ForeignKey(EmailSubscriptionType, on_delete=models.CASCADE)
    is_subscribed = models.BooleanField(default=True)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'subscription_type')

class EmailCampaign(models.Model):
    subject = models.CharField(max_length=200)
    body_html = models.TextField()
    subscription_type = models.ForeignKey(EmailSubscriptionType, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[
        ('DRAFT', 'Draft'),
        ('SENDING', 'Sending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed')
    ], default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    total_recipients = models.IntegerField(default=0)
    successful_sends = models.IntegerField(default=0)
    failed_sends = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.subject} ({self.status})"

class SocialNetwork(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    icon = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    available_actions = models.ManyToManyField('ActionType', related_name='social_networks')
    
    class Meta:
        verbose_name = "Social Network"
        verbose_name_plural = "Social Networks"
    
    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"

class UserSocialProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_profiles')
    social_network = models.ForeignKey(SocialNetwork, on_delete=models.CASCADE)
    
    social_id = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255)
    profile_url = models.URLField(null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True)
    
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=50, choices=[
        ('NOT_VERIFIED', 'Not Verified'),
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ], default='NOT_VERIFIED')
    verification_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=50, choices=[
        ('NO_EMOJI', 'No Emoji'),
        ('DOES_NOT_MEET_CRITERIA', 'Profile does not meet criteria'),
        ('URL_UNAVAILABLE', 'URL Unavailable'),
    ], null=True, blank=True, help_text='Reason for rejection if profile was rejected')
    
    oauth_token = models.CharField(max_length=255, null=True, blank=True)
    oauth_token_secret = models.CharField(max_length=255, null=True, blank=True)
    
    followers_count = models.IntegerField(default=0)
    following_count = models.IntegerField(default=0)
    posts_count = models.IntegerField(default=0)
    account_created_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "User Social Profile"
        verbose_name_plural = "User Social Profiles"
        unique_together = ['user', 'social_network', 'username']
        indexes = [
            models.Index(fields=['user', 'social_network']),
            models.Index(fields=['username']),
            models.Index(fields=['verification_status']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.social_network.name} ({self.username})"

    def sync_profile_data(self):
        if self.social_network.code == 'TWITTER':
            self._sync_twitter_profile()
        self.last_sync_at = timezone.now()
        self.save()

    def _sync_twitter_profile(self):
        try:
            auth = tweepy.OAuthHandler(
                settings.TWITTER_API_KEY,
                settings.TWITTER_API_SECRET_KEY
            )
            auth.set_access_token(self.oauth_token, self.oauth_token_secret)
            api = tweepy.API(auth)
            user_info = api.verify_credentials()
            
            self.username = user_info.screen_name
            self.avatar_url = user_info.profile_image_url_https.replace('_normal', '_400x400')
            self.profile_url = f"https://twitter.com/{self.username}"
            
            self.save()
        except Exception:
            pass

class PostCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Post Category"
        verbose_name_plural = "Post Categories"
        
    def __str__(self):
        return self.name

class PostTag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Post Tag"
        verbose_name_plural = "Post Tags"
        
    def __str__(self):
        return self.name
    

from .email_service import EmailService

class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    content = models.TextField()
    image = models.ImageField(upload_to='blog/images/', null=True, blank=True)
    category = models.ForeignKey('PostCategory', on_delete=models.PROTECT)
    tags = models.ManyToManyField('PostTag', blank=True)
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    
    status = models.CharField(max_length=20, choices=[
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('ARCHIVED', 'Archived')
    ], default='DRAFT')
    
    send_email = models.BooleanField(default=False, verbose_name="Send email notification")
    email_sent = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['category', '-published_at']),
        ]
    
    def __str__(self):
        return self.title
        
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_instance = None
        
        if not is_new:
            try:
                old_instance = BlogPost.objects.get(pk=self.pk)
            except BlogPost.DoesNotExist:
                pass
        
        if self.status == 'PUBLISHED' and not self.published_at:
            self.published_at = timezone.now()
            
            if self.send_email and not self.email_sent:
                try:
                    from .models import EmailSubscriptionType, UserEmailSubscription
                    
                    subscription_type, _ = EmailSubscriptionType.objects.get_or_create(
                        name='blog_updates',
                        defaults={'description': 'New blog post notifications'}
                    )
                    
                    subscribers = UserEmailSubscription.objects.filter(
                        subscription_type=subscription_type,
                        is_subscribed=True
                    ).select_related('user')
                    
                    email_service = EmailService()
                    success_count = 0
                    
                    for subscription in subscribers:
                        try:
                            unsubscribe_url = f"{settings.SITE_URL}/api/unsubscribe/{subscription.unsubscribe_token}/"
                            
                            context = {
                                'post': {
                                    'title': self.title,
                                    'content': self.content,
                                    'category': self.category.name,
                                    'author': self.author.username,
                                    'published_at': self.published_at,
                                    'tags': [tag.name for tag in self.tags.all()]
                                },
                                'user': subscription.user,
                                'unsubscribe_url': unsubscribe_url,
                                'site_url': settings.SITE_URL
                            }
                            
                            html_content = render_to_string('email/new_blog_post.html', context)
                            
                            if email_service.send_email(
                                to_email=subscription.user.email,
                                subject=f'New Post: {self.title}',
                                html_content=html_content,
                                unsubscribe_url=unsubscribe_url
                            ):
                                success_count += 1
                                
                        except Exception:
                            pass
                    
                    if success_count > 0:
                        self.email_sent = True
                    
                except Exception:
                    pass
        
        super().save(*args, **kwargs)

class TwitterServiceAccount(models.Model):
    api_key = models.CharField(max_length=100, default='', blank=True)
    api_secret = models.CharField(max_length=100, default='', blank=True)
    bearer_token = models.CharField(max_length=200, default='', blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    rate_limit_reset = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['last_used_at']
    
    def __str__(self):
        return f"Twitter API Account {self.id}"

class ActionType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)
    name_plural = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='Name Plural',
        help_text='Plural form of the action name (e.g., "Likes", "Followers")'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Action Type"
        verbose_name_plural = "Action Types"
        
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

class TwitterUserMapping(models.Model):
    username = models.CharField(max_length=255, unique=True, db_index=True)
    twitter_id = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'twitter_user_mapping'
        indexes = [
            models.Index(fields=['username']),
        ]

    def __str__(self):
        return f"{self.username} -> {self.twitter_id}"

class PaymentTransaction(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ('SUBSCRIPTION', 'Subscription'),
        ('ONE_TIME', 'One Time Purchase')
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('TRIAL', 'Trial'),
        ('TRIAL_ENDED', 'Trial Ended'),
        ('ACTIVE', 'Active'),
        ('PAYMENT_PENDING', 'Payment Pending'),
        ('PAST_DUE', 'Past Due'),
        ('SETUP_COMPLETED', 'Setup Completed')
    ]

    SUBSCRIPTION_PERIOD_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('ANNUAL', 'Annual')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    points = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_id = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Stripe fields
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    
    payment_type = models.CharField(
        max_length=20, 
        choices=PAYMENT_TYPE_CHOICES,
        default='ONE_TIME'
    )
    
    subscription_period_type = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_PERIOD_CHOICES,
        null=True,
        blank=True,
        help_text='Type of subscription period (monthly/annual)'
    )
    
    user_has_trial_before = models.BooleanField(default=False)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    subscription_period_start = models.DateTimeField(null=True, blank=True)
    subscription_period_end = models.DateTimeField(null=True, blank=True)
    
    # Stripe metadata
    stripe_metadata = models.JSONField(null=True, blank=True)
    last_webhook_received = models.DateTimeField(null=True, blank=True)
    
    # Task purchase flag
    is_task_purchase = models.BooleanField(
        default=False,
        verbose_name='Task Purchase',
        help_text='Whether this payment is for task creation purchase'
    )
    
    # Связь с созданным заданием
    task = models.ForeignKey(
        'Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Created Task',
        help_text='Task created after successful payment'
    )

    # Payment retry fields
    attempt_count = models.IntegerField(default=1)
    next_payment_attempt = models.DateTimeField(null=True, blank=True)
    last_payment_error = models.TextField(null=True, blank=True)

    # Notification fields
    pending_notification_sent = models.BooleanField(
        default=False,
        help_text='Whether notification about pending payment was sent'
    )
    pending_notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When notification about pending payment was sent'
    )

    class Meta:
        db_table = 'payment_transactions'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['stripe_session_id']),
            models.Index(fields=['stripe_subscription_id']),
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['payment_type']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        return f"Payment {self.payment_id} - {self.points} points for ${self.amount}"

    def update_from_stripe_event(self, event_data):
        """
        Обновляет транзакцию данными из webhook события Stripe
        """
        try:
            self.stripe_metadata = event_data
            self.last_webhook_received = timezone.now()
            
            if 'subscription' in event_data:
                self.stripe_subscription_id = event_data['subscription'].get('id')
                current_period = event_data['subscription'].get('current_period')
                if current_period:
                    self.subscription_period_start = timezone.datetime.fromtimestamp(
                        current_period.get('start', 0)
                    )
                    self.subscription_period_end = timezone.datetime.fromtimestamp(
                        current_period.get('end', 0)
                    )
            
            if 'payment_intent' in event_data:
                self.stripe_payment_intent_id = event_data['payment_intent'].get('id')
            
            self.save()
            logging.info(f"[PaymentTransaction] Updated from Stripe event: {self.payment_id}")
            
        except Exception as e:
            logging.error(f"[PaymentTransaction] Error updating from Stripe event: {str(e)}")
            raise

class TaskReport(models.Model):
    REASON_CHOICES = [
        ('i_dont_want_to_do_it', 'Just Hide'),
        ('not_available', 'Url Not Available'),
        ('not_working', 'Not Working'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_reports')
    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='reports')
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('user', 'task')
        ordering = ['-created_at']
        verbose_name = 'Task Report'
        verbose_name_plural = 'Task Reports'

    def __str__(self):
        return f"Report by {self.user.username} on task {self.task.id} - {self.reason}"

class Landing(models.Model):
    # Основные SEO поля
    title = models.CharField(max_length=255, verbose_name='Title')
    slug = models.SlugField(max_length=255, unique=True, verbose_name='URL Slug')
    meta_title = models.CharField(max_length=255, verbose_name='Meta Title')
    meta_description = models.TextField(verbose_name='Meta Description')
    h1 = models.CharField(max_length=255, verbose_name='H1')
    content = models.TextField(verbose_name='Content')

    # Open Graph поля
    og_title = models.CharField(max_length=255, verbose_name='OG Title', help_text='Title for social media sharing', null=True, blank=True)
    og_description = models.TextField(verbose_name='OG Description', help_text='Description for social media sharing', null=True, blank=True)
    
    # Дополнительные SEO поля
    page_type = models.CharField(max_length=50, verbose_name='Page Type', help_text='Type of the landing page', null=True, blank=True)
    cluster_name = models.CharField(max_length=255, verbose_name='Cluster Name', help_text='Name of the SEO cluster', null=True, blank=True)
    cluster_description = models.TextField(verbose_name='Cluster Description', help_text='Description of the SEO cluster', null=True, blank=True)
    page_idea = models.TextField(verbose_name='Page Idea', help_text='Main idea and purpose of the page', null=True, blank=True)
    user_behavior = models.TextField(verbose_name='User Behavior', help_text='Expected user behavior on the page', null=True, blank=True)
    article_structure = models.TextField(verbose_name='Article Structure', help_text='Structure of the article content', null=True, blank=True)
    page_blocks = models.TextField(verbose_name='Page Blocks', help_text='Main blocks/sections of the page', null=True, blank=True)
    
    # Поля для категоризации
    social_network = models.CharField(max_length=50, verbose_name='Social Network', blank=True, null=True)
    action = models.CharField(max_length=50, verbose_name='Action', blank=True, null=True)
    
    # Поля для отслеживания индексации Google
    is_indexed = models.BooleanField(default=False, verbose_name='Indexed in Google', help_text='Whether this page was submitted to Google Indexing API')
    indexed_at = models.DateTimeField(null=True, blank=True, verbose_name='Indexed At', help_text='When this page was submitted to Google Indexing API')
    indexing_error = models.TextField(null=True, blank=True, verbose_name='Indexing Error', help_text='Error message if indexing failed')
    
    # Служебные поля
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Landing Page'
        verbose_name_plural = 'Landing Pages'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['social_network', 'action']),
            models.Index(fields=['is_indexed']),
        ]

    def __str__(self):
        return self.title

    def mark_as_indexed(self, success=True, error_message=None):
        """Отмечает страницу как проиндексированную"""
        self.is_indexed = success
        self.indexed_at = timezone.now() if success else None
        self.indexing_error = error_message if not success else None
        self.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])

class ActionLanding(models.Model):
    # Основные поля
    title = models.CharField(
        max_length=255, 
        verbose_name='Title',
        help_text='Main title of the landing page'
    )
    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        verbose_name='URL',
        help_text='URL-friendly version of the title'
    )
    social_network = models.ForeignKey(
        'SocialNetwork',
        on_delete=models.SET_NULL,
        verbose_name='Social Network',
        help_text='Related social network for this landing',
        null=True,
        blank=True
    )
    action = models.CharField(
        max_length=50,
        verbose_name='Action',
        help_text='Type of action for this landing page',
        null=True,
        blank=True
    )

    # SEO поля
    meta_title = models.CharField(
        max_length=255, 
        verbose_name='Meta Title',
        help_text='Title for search engines',
        null=True,
        blank=True
    )
    meta_description = models.TextField(
        verbose_name='Meta Description',
        help_text='Description for search engines',
        null=True,
        blank=True
    )
    h1 = models.CharField(
        max_length=255,
        verbose_name='H1',
        help_text='Main heading of the page',
        null=True,
        blank=True
    )
    content = models.TextField(
        verbose_name='Content',
        help_text='Main content of the page',
        null=True,
        blank=True
    )

    # FAQ в формате JSON
    faq_section_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='FAQ Section Title',
        help_text='Title for FAQ section'
    )
    faq = models.JSONField(
        verbose_name='FAQ',
        help_text='List of Q&A items, e.g. [{"q": "Question", "a": "Answer"}]',
        null=True,
        blank=True
    )

    # Описания
    short_description = models.TextField(
        verbose_name='Short Description',
        help_text='Brief description for meta tags and previews',
        null=True,
        blank=True
    )

    # Новое поле для 301 редиректа
    redirect_url = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        verbose_name='301 Redirect URL',
        help_text='If set, this landing will redirect (301) to the specified URL'
    )

    # Поля для отслеживания индексации Google
    is_indexed = models.BooleanField(
        default=False,
        verbose_name='Indexed in Google',
        help_text='Whether this page was submitted to Google Indexing API'
    )
    indexed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Indexed At',
        help_text='When this page was submitted to Google Indexing API'
    )
    indexing_error = models.TextField(
        null=True,
        blank=True,
        verbose_name='Indexing Error',
        help_text='Error message if indexing failed'
    )

    # Связь с отзывами
    reviews_section_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Reviews Section Title',
        help_text='Title for Reviews section'
    )
    reviews = models.ManyToManyField(
        'Review',
        blank=True,
        verbose_name='Reviews',
        help_text='Select reviews to display on this landing page',
        related_name='action_landings'
    )

    # JSON поля для контента
    how_it_works_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='How It Works Title',
        help_text='Title for "How It Works" section'
    )
    how_it_works = models.JSONField(
        null=True,
        blank=True,
        verbose_name='How It Works',
        help_text='JSON structure: [{"title": "Step Title", "text": "Step description text", "image": "image_url"}]'
    )
    why_upvote_club_best_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Why Upvote Club Best Title',
        help_text='Title for "Why Upvote Club Best" section'
    )
    why_upvote_club_best = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Why Upvote Club Best',
        help_text='JSON structure: [{"title": "Feature title", "text": "Feature description", "image": "image_url"}]'
    )

    # Служебные поля
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Action Landing'
        verbose_name_plural = 'Action Landings'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['social_network', 'action']),
            models.Index(fields=['is_indexed']),
        ]

    def __str__(self):
        network_name = self.social_network.name if self.social_network else 'No Network'
        action_name = self.action if self.action else 'No Action'
        return f"{self.title} ({network_name} - {action_name})"

    def mark_as_indexed(self, success=True, error_message=None):
        """Отмечает страницу как проиндексированную"""
        self.is_indexed = success
        self.indexed_at = timezone.now() if success else None
        self.indexing_error = error_message if not success else None
        self.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])

    def save(self, *args, **kwargs):
        # Логируем создание/обновление лендинга
        is_new = self.pk is None
        network_name = self.social_network.name if self.social_network else 'No Network'
        action_name = self.action if self.action else 'No Action'
        logging.info(
            f"{'Creating' if is_new else 'Updating'} ActionLanding: {self.title} "
            f"for {network_name} - {action_name}"
        )
        super().save(*args, **kwargs)

class BuyLanding(models.Model):
    title = models.CharField(
        max_length=255,
        verbose_name='Title',
        help_text='Main title of the buy landing page'
    )
    h1 = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='H1',
        help_text='Main heading of the page'
    )
    description = models.TextField(
        verbose_name='Description',
        help_text='Full description of the buy landing page'
    )
    short_description = models.TextField(
        verbose_name='Short Description',
        help_text='Brief description for previews'
    )
    social_network = models.ForeignKey(
        'SocialNetwork',
        on_delete=models.CASCADE,
        verbose_name='Social Network',
        help_text='Related social network for this buy landing',
        related_name='buy_landings'
    )
    action = models.ForeignKey(
        'ActionType',
        on_delete=models.CASCADE,
        verbose_name='Action',
        help_text='Type of action for this buy landing page',
        related_name='buy_landings'
    )
    reviews = models.ManyToManyField(
        'Review',
        blank=True,
        related_name='buy_landings',
        verbose_name='Reviews',
        help_text='Select reviews to display on this buy landing'
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name='Slug',
        help_text='URL-friendly identifier for this landing'
    )
    
    # Поля для отслеживания индексации Google
    is_indexed = models.BooleanField(
        default=False,
        verbose_name='Indexed in Google',
        help_text='Whether this page was submitted to Google Indexing API'
    )
    indexed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Indexed At',
        help_text='When this page was submitted to Google Indexing API'
    )
    indexing_error = models.TextField(
        null=True,
        blank=True,
        verbose_name='Indexing Error',
        help_text='Error message if indexing failed'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Buy Landing'
        verbose_name_plural = 'Buy Landings'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['social_network', 'action']),
            models.Index(fields=['is_indexed']),
        ]
        unique_together = [['social_network', 'action']]

    def __str__(self):
        return f"{self.title} ({self.social_network.name} - {self.action.name})"
    
    def mark_as_indexed(self, success=True, error_message=None):
        """Отмечает страницу как проиндексированную"""
        self.is_indexed = success
        self.indexed_at = timezone.now() if success else None
        self.indexing_error = error_message if not success else None
        self.save(update_fields=['is_indexed', 'indexed_at', 'indexing_error'])

class Withdrawal(models.Model):
    WITHDRAWAL_METHOD_CHOICES = [
        ('PAYPAL', 'PayPal'),
        ('USDT', 'USDT'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='withdrawals',
        verbose_name='User'
    )
    amount_usd = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        verbose_name='Amount (USD)',
        help_text='Amount to withdraw in USD'
    )
    points_sold = models.IntegerField(
        verbose_name='Points Sold',
        help_text='Number of points converted to USD'
    )
    withdrawal_method = models.CharField(
        max_length=10,
        choices=WITHDRAWAL_METHOD_CHOICES,
        verbose_name='Withdrawal Method'
    )
    withdrawal_address = models.CharField(
        max_length=255,
        verbose_name='Withdrawal Address',
        help_text='PayPal email or USDT wallet address'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        verbose_name='Status'
    )
    
    # Системные поля
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    processed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name='Processed At',
        help_text='When the withdrawal was processed'
    )
    
    # Административные поля
    admin_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name='Admin Notes',
        help_text='Internal notes for administrators'
    )
    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Transaction ID',
        help_text='External transaction ID (PayPal transaction ID, USDT tx hash, etc.)'
    )
    
    class Meta:
        verbose_name = 'Withdrawal'
        verbose_name_plural = 'Withdrawals'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['withdrawal_method']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Withdrawal #{self.id} - {self.user.username} - ${self.amount_usd} via {self.withdrawal_method}"
    
    def save(self, *args, **kwargs):
        # Логируем изменения статуса
        send_email = False
        if self.pk:
            try:
                old_instance = Withdrawal.objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    logging.info(f"""
                        [Withdrawal] Status changed for withdrawal #{self.pk}:
                        User: {self.user.username}
                        Amount: ${self.amount_usd}
                        Old Status: {old_instance.status}
                        New Status: {self.status}
                        Method: {self.withdrawal_method}
                        Address: {self.withdrawal_address}
                    """)
                    
                    # Если статус изменился на PROCESSING или COMPLETED, обновляем processed_at
                    if self.status in ['PROCESSING', 'COMPLETED'] and not self.processed_at:
                        self.processed_at = timezone.now()
                    
                    # Если статус изменился на COMPLETED, отправляем email
                    if self.status == 'COMPLETED' and old_instance.status != 'COMPLETED':
                        send_email = True
                        
            except Withdrawal.DoesNotExist:
                pass
        else:
            logging.info(f"""
                [Withdrawal] Creating new withdrawal:
                User: {self.user.username}
                Amount: ${self.amount_usd}
                Points: {self.points_sold}
                Method: {self.withdrawal_method}
                Address: {self.withdrawal_address}
            """)
            
        super().save(*args, **kwargs)
        
        # Отправляем email после сохранения
        if send_email:
            try:
                from api.utils.email_utils import send_withdrawal_completed_email
                send_withdrawal_completed_email(self)
            except Exception as e:
                logging.error(f"Error sending withdrawal completed email: {str(e)}", exc_info=True)
    
    @property
    def conversion_rate(self):
        """Возвращает курс конвертации поинтов в доллары (1 поинт = $0.01)"""
        return 0.01
    
    @classmethod
    def get_min_withdrawal_amount(cls):
        """Возвращает минимальную сумму для вывода в долларах"""
        return 3.00
    
    @classmethod
    def get_points_needed_for_min_withdrawal(cls):
        """Возвращает количество поинтов, необходимых для минимального вывода"""
        return int(cls.get_min_withdrawal_amount() / 0.01)  # 300 поинтов
    
    def can_be_cancelled(self):
        """Проверяет, можно ли отменить withdrawal"""
        return self.status == 'PENDING'
    
    def calculate_points_for_amount(self, amount_usd):
        """Вычисляет количество поинтов для заданной суммы в долларах"""
        return int(amount_usd / self.conversion_rate)

class OnboardingProgress(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='onboarding_progress')
    chosen_country = models.CharField(max_length=10, null=True, blank=True, help_text='Country chosen by user (ISO 3166-1 alpha-2 code)')
    account_type = models.CharField(max_length=20, null=True, blank=True, help_text='Account type: business or individual')
    social_networks = models.JSONField(null=True, blank=True, help_text='List of selected social networks (codes)')
    actions = models.JSONField(null=True, blank=True, help_text='Dict: {social_network_code: [action_codes]}')
    goal_description = models.TextField(null=True, blank=True, help_text='User description after social networks and actions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Onboarding for {self.user.username}"

    class Meta:
        verbose_name = 'Onboarding Progress'
        verbose_name_plural = 'Onboarding Progresses'

class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews', help_text='Firebase UID (User)')
    social_network = models.ForeignKey(SocialNetwork, on_delete=models.CASCADE, related_name='reviews', help_text='Social network')
    action = models.ForeignKey(ActionType, on_delete=models.CASCADE, related_name='reviews', help_text='Action type')
    actions_count = models.IntegerField(help_text='Number of actions in the task')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='reviews', help_text='Task ID')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)], help_text='Rating from 1 to 5')
    comment = models.TextField(blank=True, null=True, help_text='User comment for the review')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Review'
        verbose_name_plural = 'Reviews'
        indexes = [
            models.Index(fields=['user', 'task', 'social_network', 'action']),
        ]

    def __str__(self):
        action_name = self.action.name if self.action else 'Unknown'
        comment_text = (self.comment or '').strip()
        base = f"{action_name} ({self.rating}★)"
        return f"{base} - {comment_text}" if comment_text else base

class ApiKey(models.Model):
    """
    Модель для хранения API ключей пользователей для публичного API.
    Оригинальный ключ не хранится - только хеш для безопасности.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys', help_text='User who owns this API key')
    key_hash = models.CharField(max_length=128, unique=True, db_index=True, help_text='Hashed API key for verification')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Optional name/description for the API key')
    is_active = models.BooleanField(default=True, help_text='Whether the API key is active')
    last_used_at = models.DateTimeField(null=True, blank=True, help_text='Last time the API key was used')
    created_at = models.DateTimeField(auto_now_add=True, help_text='When the API key was created')
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Optional expiration date for the API key')
    
    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'
        indexes = [
            models.Index(fields=['key_hash', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"API Key for {self.user.username} ({'active' if self.is_active else 'inactive'})"
    
    def is_expired(self):
        """Проверяет, истек ли срок действия ключа"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Проверяет, валиден ли ключ (активен и не истек)"""
        return self.is_active and not self.is_expired()