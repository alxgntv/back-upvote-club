from django.db import models
from api.models import TwitterServiceAccount, UserProfile, Task

class TwitterUserAuthorization(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    service_account = models.ForeignKey(TwitterServiceAccount, on_delete=models.CASCADE)
    oauth_token = models.CharField(max_length=255)
    oauth_token_secret = models.CharField(max_length=255)
    authorized_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user_profile', 'service_account')
        
    def __str__(self):
        return f"{self.user_profile.user.username} - {self.service_account.id}"

class TwitterActionLog(models.Model):
    STATUS_CHOICES = (
        ('SUCCESS', 'Success'),
        ('ERROR', 'Error'),
        ('RATE_LIMIT', 'Rate Limit'),
    )

    user_profile = models.ForeignKey(
        UserProfile, 
        on_delete=models.CASCADE,
        related_name='twitter_action_logs'
    )
    service_account = models.ForeignKey(
        TwitterServiceAccount, 
        on_delete=models.CASCADE,
        related_name='action_logs'
    )
    task = models.ForeignKey(
        Task, 
        on_delete=models.CASCADE,
        related_name='action_logs',
        null=True,
        blank=True
    )
    action_type = models.CharField(max_length=50)  # FOLLOW, LIKE, REPOST
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES
    )
    error_message = models.TextField(
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    target_user = models.CharField(
        max_length=255, 
        null=True, 
        blank=True
    )  # Twitter username или URL

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Twitter Action Log'
        verbose_name_plural = 'Twitter Action Logs'

    def __str__(self):
        return f"{self.user_profile.twitter_account} - {self.action_type} - {self.status}"
